# Deluge CLI v0.1
"""Tests for fix_references.py."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fix_references import (
    AmbiguousRefWarning,
    BrokenRefError,
    ReferenceStatus,
    MAX_RECOVERY_CANDIDATES,
    MigrationResult,
    MissingRefError,
    PlannedChange,
    RecoveredRefChange,
    compute_migration_map,
    classify_ref_changes,
    path_similarity,
    preview_and_apply,
    update_manifest_keys,
)

from deluge_lib.deluge_sdk import SampleRef
from deluge_lib.scanning import normalise_key, normalise_mtime
from deluge_lib.syncing import FilesDict


def _make_deluge_tree(tmp_path: Path, wav_files: dict[str, bytes]) -> Path:
    """Helper: create a DELUGE/SAMPLES/ tree with given WAV files.

    Args:
        tmp_path: pytest tmp_path fixture.
        wav_files: Mapping of relative paths (under SAMPLES/) to file contents.

    Returns:
        Path to the DELUGE root directory.
    """
    deluge_root = tmp_path / "DELUGE"
    samples = deluge_root / "SAMPLES"
    for rel_path, content in wav_files.items():
        full = samples / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(content)
    return deluge_root


def _make_manifest(entries: dict[str, str | None]) -> FilesDict:
    """Create a manifest dict for testing.

    Args:
        entries: Mapping of normalised path keys to hash values (or None).
                 Stats are set to dummy values that won't match disk files.
    """
    result: FilesDict = {}
    for key, hash_val in entries.items():
        result[key] = {
            "sd_size": 100,
            "sd_mtime": 1000.0,
            "local_size": 100,
            "local_mtime": 1000.0,
            "hash": hash_val,
        }
    return result


def _write_minimal_kit_xml(path: Path, sample_paths: list[str]) -> None:
    """Write a minimal kit XML with fileName attributes for each sample path."""
    sounds = ""
    for sp in sample_paths:
        sounds += f"""
\t\t<sound name="S">
\t\t\t<osc1 type="sample" fileName="{sp}">
\t\t\t</osc1>
\t\t</sound>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n<kit>\n\t<soundSources>{sounds}\n\t</soundSources>\n</kit>\n',
        encoding="utf-8",
    )


def _write_manifest_file(path: Path, manifest: FilesDict) -> None:
    """Write a v2 manifest JSON file for testing."""
    payload = {
        "version": 2,
        "last_sync_timestamp": "2026-01-01T00:00:00",
        "files": {
            k: {
                "sd_size": v["sd_size"],
                "sd_mtime": v["sd_mtime"],
                "local_size": v["local_size"],
                "local_mtime": v["local_mtime"],
                "hash": v.get("hash"),
            }
            for k, v in manifest.items()
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class TestMain:
    """Tests for the CLI entry point."""

    def test_missing_manifest_degrades_gracefully(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """With a missing manifest, the tool runs with degraded move detection."""
        from fix_references import main

        deluge_root = _make_deluge_tree(tmp_path, {"kick.wav": b"audio"})
        _write_minimal_kit_xml(
            deluge_root / "KITS" / "KIT001.XML",
            ["SAMPLES/kick.wav"],
        )

        with patch("fix_references.get_deluge_root", return_value=deluge_root):
            main(["--manifest", str(tmp_path / "nonexistent.json")])

        captured = capsys.readouterr()
        assert "empty or missing" in captured.out

    def test_custom_manifest_path(self, tmp_path: Path) -> None:
        """--manifest flag uses the specified path."""
        from fix_references import main

        content = b"kick_audio"
        deluge_root = _make_deluge_tree(tmp_path, {"kick.wav": content})
        digest = hashlib.sha256(content).hexdigest()
        _write_minimal_kit_xml(
            deluge_root / "KITS" / "KIT001.XML",
            ["SAMPLES/kick.wav"],
        )
        manifest = _make_manifest({"samples/kick.wav": digest})
        manifest_file = tmp_path / "custom_manifest.json"
        _write_manifest_file(manifest_file, manifest)

        with patch("fix_references.get_deluge_root", return_value=deluge_root):
            main(["--manifest", str(manifest_file)])  # Should not raise


# ---------------------------------------------------------------------------
# compute_migration_map
# ---------------------------------------------------------------------------


class TestComputeMigrationMap:
    """Tests for compute_migration_map (manifest-based)."""

    def test_simple_move(self, tmp_path: Path) -> None:
        """File moved from old to new path appears in moved dict."""
        content = b"kick drum audio"
        deluge_root = _make_deluge_tree(tmp_path, {"DRUMS/NewKick.wav": content})
        digest = hashlib.sha256(content).hexdigest()
        manifest = _make_manifest({"samples/drums/oldkick.wav": digest})

        result = compute_migration_map(manifest, deluge_root)

        assert result.moved == {
            "samples/drums/oldkick.wav": "SAMPLES/DRUMS/NewKick.wav",
        }
        assert not result.deleted
        assert not result.added
        assert not result.ambiguous

    def test_deleted_file(self, tmp_path: Path) -> None:
        """Hash in manifest but not on disk is categorised as deleted."""
        deluge_root = tmp_path / "DELUGE"
        (deluge_root / "SAMPLES").mkdir(parents=True)
        digest = "ab" * 32
        manifest = _make_manifest({"samples/deleted.wav": digest})

        result = compute_migration_map(manifest, deluge_root)

        assert digest in result.deleted
        assert result.deleted[digest] == ["samples/deleted.wav"]
        assert not result.moved

    def test_added_file(self, tmp_path: Path) -> None:
        """Hash on disk but not in manifest is categorised as added."""
        content = b"new sample"
        deluge_root = _make_deluge_tree(tmp_path, {"new.wav": content})
        manifest: FilesDict = {}

        result = compute_migration_map(manifest, deluge_root)

        digest = hashlib.sha256(content).hexdigest()
        assert digest in result.added
        assert result.added[digest] == ["SAMPLES/new.wav"]
        assert not result.moved

    def test_ambiguous_multiple_before_paths(self, tmp_path: Path) -> None:
        """Hash with 2 before-paths, 1 after-path, no overlap: both moved."""
        content = b"shared content"
        deluge_root = _make_deluge_tree(tmp_path, {"current.wav": content})
        digest = hashlib.sha256(content).hexdigest()
        manifest = _make_manifest({
            "samples/a.wav": digest,
            "samples/b.wav": digest,
        })

        result = compute_migration_map(manifest, deluge_root)

        assert result.moved == {
            "samples/a.wav": "SAMPLES/current.wav",
            "samples/b.wav": "SAMPLES/current.wav",
        }
        assert not result.ambiguous

    def test_ambiguous_multiple_after_paths(self, tmp_path: Path) -> None:
        """Hash with 1 before-path, 2 after-paths, no overlap: moved + added."""
        content = b"duplicated content"
        deluge_root = _make_deluge_tree(tmp_path, {
            "copy1.wav": content,
            "copy2.wav": content,
        })
        digest = hashlib.sha256(content).hexdigest()
        manifest = _make_manifest({"samples/original.wav": digest})

        result = compute_migration_map(manifest, deluge_root)

        # Moved to best path_similarity match; the other is added
        assert "samples/original.wav" in result.moved
        assert result.moved["samples/original.wav"] in {
            "SAMPLES/copy1.wav", "SAMPLES/copy2.wav",
        }
        assert digest in result.added
        assert len(result.added[digest]) == 1
        assert not result.ambiguous

    def test_unchanged_file_not_in_results(self, tmp_path: Path) -> None:
        """Same hash and same normalised path produces no entries."""
        content = b"unchanged audio"
        deluge_root = _make_deluge_tree(tmp_path, {"same.wav": content})
        digest = hashlib.sha256(content).hexdigest()
        manifest = _make_manifest({"samples/same.wav": digest})

        result = compute_migration_map(manifest, deluge_root)

        assert not result.moved
        assert not result.deleted
        assert not result.added
        assert not result.ambiguous

    def test_empty_manifest_empty_filesystem(self, tmp_path: Path) -> None:
        """Empty manifest and empty SAMPLES dir produce an empty result."""
        deluge_root = tmp_path / "DELUGE"
        (deluge_root / "SAMPLES").mkdir(parents=True)

        result = compute_migration_map({}, deluge_root)

        assert result == MigrationResult()

    def test_empty_manifest_with_current_files(self, tmp_path: Path) -> None:
        """Empty manifest with files on disk reports all as added."""
        content = b"brand new"
        deluge_root = _make_deluge_tree(tmp_path, {"new.wav": content})

        result = compute_migration_map({}, deluge_root)

        assert not result.moved
        assert not result.deleted
        assert len(result.added) == 1

    def test_multiple_independent_moves(self, tmp_path: Path) -> None:
        """Multiple files each moved independently appear in moved dict."""
        content_a = b"audio a"
        content_b = b"audio b"
        deluge_root = _make_deluge_tree(tmp_path, {
            "new_a.wav": content_a,
            "new_b.wav": content_b,
        })
        hash_a = hashlib.sha256(content_a).hexdigest()
        hash_b = hashlib.sha256(content_b).hexdigest()
        manifest = _make_manifest({
            "samples/old_a.wav": hash_a,
            "samples/old_b.wav": hash_b,
        })

        result = compute_migration_map(manifest, deluge_root)

        assert result.moved == {
            "samples/old_a.wav": "SAMPLES/new_a.wav",
            "samples/old_b.wav": "SAMPLES/new_b.wav",
        }
        assert not result.deleted
        assert not result.added
        assert not result.ambiguous

    def test_mixed_categories(self, tmp_path: Path) -> None:
        """A single run can produce moved, deleted, added, and decomposed entries."""
        moved_content = b"moved file"
        added_content = b"added file"
        decomp_content = b"ambig file"

        deluge_root = _make_deluge_tree(tmp_path, {
            "new_location.wav": moved_content,
            "brand_new.wav": added_content,
            "dup1.wav": decomp_content,
            "dup2.wav": decomp_content,
        })

        moved_hash = hashlib.sha256(moved_content).hexdigest()
        deleted_hash = "cc" * 32
        decomp_hash = hashlib.sha256(decomp_content).hexdigest()

        manifest = _make_manifest({
            "samples/old_location.wav": moved_hash,
            "samples/gone.wav": deleted_hash,
            "samples/original.wav": decomp_hash,
        })

        result = compute_migration_map(manifest, deluge_root)

        assert "samples/old_location.wav" in result.moved
        assert deleted_hash in result.deleted
        # 1:M decomposition — moved + added, not ambiguous
        assert "samples/original.wav" in result.moved
        assert decomp_hash in result.added
        assert len(result.added[decomp_hash]) == 1
        assert not result.ambiguous

    def test_after_hashes_populated(self, tmp_path: Path) -> None:
        """after_hashes maps hashes to original-case filesystem paths."""
        content_a = b"audio a"
        content_b = b"audio b"
        deluge_root = _make_deluge_tree(tmp_path, {
            "DRUMS/Kick.wav": content_a,
            "SYNTH/Pad.wav": content_b,
        })
        hash_a = hashlib.sha256(content_a).hexdigest()
        hash_b = hashlib.sha256(content_b).hexdigest()
        manifest: FilesDict = {}

        result = compute_migration_map(manifest, deluge_root)

        assert hash_a in result.after_hashes
        assert result.after_hashes[hash_a] == ["SAMPLES/DRUMS/Kick.wav"]
        assert hash_b in result.after_hashes
        assert result.after_hashes[hash_b] == ["SAMPLES/SYNTH/Pad.wav"]

    def test_after_hashes_empty_when_no_samples(self, tmp_path: Path) -> None:
        """after_hashes is empty when SAMPLES dir has no files."""
        deluge_root = tmp_path / "DELUGE"
        (deluge_root / "SAMPLES").mkdir(parents=True)

        result = compute_migration_map({}, deluge_root)

        assert result.after_hashes == {}


# ---------------------------------------------------------------------------
# Decomposition sub-cases
# ---------------------------------------------------------------------------


class TestDecomposition:
    """Tests for overlap-removal decomposition in compute_migration_map."""

    def test_n1_no_overlap(self, tmp_path: Path) -> None:
        """N before-paths, 1 after-path, no normalised match: all moved."""
        content = b"shared audio"
        deluge_root = _make_deluge_tree(tmp_path, {"new.wav": content})
        digest = hashlib.sha256(content).hexdigest()
        manifest = _make_manifest({
            "samples/old_a.wav": digest,
            "samples/old_b.wav": digest,
            "samples/old_c.wav": digest,
        })

        result = compute_migration_map(manifest, deluge_root)

        assert result.moved == {
            "samples/old_a.wav": "SAMPLES/new.wav",
            "samples/old_b.wav": "SAMPLES/new.wav",
            "samples/old_c.wav": "SAMPLES/new.wav",
        }
        assert not result.ambiguous
        assert not result.deleted

    def test_n1_with_overlap(self, tmp_path: Path) -> None:
        """N before-paths, 1 after-path, one before matches after: overlap unchanged, others moved."""
        content = b"overlap audio"
        deluge_root = _make_deluge_tree(tmp_path, {"survivor.wav": content})
        digest = hashlib.sha256(content).hexdigest()
        manifest = _make_manifest({
            "samples/survivor.wav": digest,
            "samples/removed.wav": digest,
        })

        result = compute_migration_map(manifest, deluge_root)

        # survivor is unchanged (overlap), removed is moved to survivor
        assert result.moved == {
            "samples/removed.wav": "SAMPLES/survivor.wav",
        }
        assert not result.ambiguous

    def test_1m_no_overlap(self, tmp_path: Path) -> None:
        """1 before-path, M after-paths, no normalised match: moved + added."""
        content = b"duplicated audio"
        deluge_root = _make_deluge_tree(tmp_path, {
            "new_folder/kick.wav": content,
            "other/snare.wav": content,
        })
        digest = hashlib.sha256(content).hexdigest()
        manifest = _make_manifest({"samples/old_folder/kick.wav": digest})

        result = compute_migration_map(manifest, deluge_root)

        # path_similarity: "kick.wav" matches → new_folder/kick.wav wins
        assert result.moved == {
            "samples/old_folder/kick.wav": "SAMPLES/new_folder/kick.wav",
        }
        assert digest in result.added
        assert result.added[digest] == ["SAMPLES/other/snare.wav"]
        assert not result.ambiguous

    def test_1m_with_overlap(self, tmp_path: Path) -> None:
        """1 before-path matches one after-path: unchanged; other after-paths added."""
        content = b"overlap dup audio"
        deluge_root = _make_deluge_tree(tmp_path, {
            "existing.wav": content,
            "copy.wav": content,
        })
        digest = hashlib.sha256(content).hexdigest()
        manifest = _make_manifest({"samples/existing.wav": digest})

        result = compute_migration_map(manifest, deluge_root)

        # Before-path overlaps — unchanged; copy.wav is added
        assert not result.moved
        assert digest in result.added
        assert result.added[digest] == ["SAMPLES/copy.wav"]
        assert not result.ambiguous

    def test_nm_partial_overlap_reduces_to_1_1(self, tmp_path: Path) -> None:
        """N:M with overlaps that reduce residual to 1:1."""
        content = b"partial overlap audio"
        deluge_root = _make_deluge_tree(tmp_path, {
            "kept_a.wav": content,
            "kept_b.wav": content,
            "new_loc.wav": content,
        })
        digest = hashlib.sha256(content).hexdigest()
        manifest = _make_manifest({
            "samples/kept_a.wav": digest,
            "samples/kept_b.wav": digest,
            "samples/old_loc.wav": digest,
        })

        result = compute_migration_map(manifest, deluge_root)

        # kept_a and kept_b overlap; old_loc → new_loc is 1:1 residual
        assert result.moved == {
            "samples/old_loc.wav": "SAMPLES/new_loc.wav",
        }
        assert not result.ambiguous

    def test_nm_all_overlapping(self, tmp_path: Path) -> None:
        """All N:M pairs match normalised — nothing in any result dict."""
        content = b"all overlap audio"
        deluge_root = _make_deluge_tree(tmp_path, {
            "a.wav": content,
            "b.wav": content,
        })
        digest = hashlib.sha256(content).hexdigest()
        manifest = _make_manifest({
            "samples/a.wav": digest,
            "samples/b.wav": digest,
        })

        result = compute_migration_map(manifest, deluge_root)

        assert not result.moved
        assert not result.deleted
        assert not result.added
        assert not result.ambiguous

    def test_nm_no_overlap_truly_ambiguous(self, tmp_path: Path) -> None:
        """N>1 before, M>1 after, no overlap: truly ambiguous."""
        content = b"ambig audio"
        deluge_root = _make_deluge_tree(tmp_path, {
            "x.wav": content,
            "y.wav": content,
        })
        digest = hashlib.sha256(content).hexdigest()
        manifest = _make_manifest({
            "samples/a.wav": digest,
            "samples/b.wav": digest,
        })

        result = compute_migration_map(manifest, deluge_root)

        assert digest in result.ambiguous
        before_paths, after_paths = result.ambiguous[digest]
        assert set(before_paths) == {"samples/a.wav", "samples/b.wav"}
        assert set(after_paths) == {"SAMPLES/x.wav", "SAMPLES/y.wav"}
        assert not result.moved

    def test_n_before_zero_residual_after(self, tmp_path: Path) -> None:
        """N before-paths, all after-paths consumed by overlaps: moved to first survivor."""
        content = b"survivor audio"
        deluge_root = _make_deluge_tree(tmp_path, {
            "kept.wav": content,
        })
        digest = hashlib.sha256(content).hexdigest()
        manifest = _make_manifest({
            "samples/kept.wav": digest,
            "samples/removed_a.wav": digest,
            "samples/removed_b.wav": digest,
        })

        result = compute_migration_map(manifest, deluge_root)

        # kept.wav overlaps; removed_a and removed_b moved to survivor
        assert result.moved == {
            "samples/removed_a.wav": "SAMPLES/kept.wav",
            "samples/removed_b.wav": "SAMPLES/kept.wav",
        }
        assert not result.ambiguous
        assert not result.deleted


# ---------------------------------------------------------------------------
# Graceful degradation
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    """Tests for manifest graceful degradation in compute_migration_map."""

    def test_manifest_with_null_hashes(self, tmp_path: Path) -> None:
        """Manifest entries with null hashes can't participate in move detection."""
        content = b"some audio"
        deluge_root = _make_deluge_tree(tmp_path, {"new.wav": content})
        manifest = _make_manifest({"samples/old.wav": None})

        result = compute_migration_map(manifest, deluge_root)

        assert not result.moved
        assert not result.deleted
        assert len(result.added) == 1

    def test_missing_samples_dir(self, tmp_path: Path) -> None:
        """Missing SAMPLES directory returns empty result."""
        deluge_root = tmp_path / "DELUGE"
        deluge_root.mkdir(parents=True)
        manifest = _make_manifest({"samples/kick.wav": "ab" * 32})

        result = compute_migration_map(manifest, deluge_root)

        assert result == MigrationResult()

    def test_manifest_status_output_empty(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Empty manifest prints degradation warning."""
        deluge_root = tmp_path / "DELUGE"
        (deluge_root / "SAMPLES").mkdir(parents=True)

        compute_migration_map({}, deluge_root)

        captured = capsys.readouterr()
        assert "empty or missing" in captured.out

    def test_manifest_status_output_no_hashes(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Manifest with entries but no hashes prints warning."""
        deluge_root = tmp_path / "DELUGE"
        (deluge_root / "SAMPLES").mkdir(parents=True)
        manifest = _make_manifest({"samples/kick.wav": None})

        compute_migration_map(manifest, deluge_root)

        captured = capsys.readouterr()
        assert "No hashes in manifest" in captured.out


# ---------------------------------------------------------------------------
# Stat-cache optimisation
# ---------------------------------------------------------------------------


class TestStatCacheOptimization:
    """Tests for stat-cache fast-path in compute_migration_map."""

    def test_stat_cache_hit_avoids_rehash(self, tmp_path: Path) -> None:
        """Files whose stat matches manifest use cached hash without hashing."""
        content = b"cached content"
        deluge_root = _make_deluge_tree(tmp_path, {"kick.wav": content})
        digest = hashlib.sha256(content).hexdigest()

        file_path = deluge_root / "SAMPLES" / "kick.wav"
        st = file_path.stat()

        manifest: FilesDict = {
            "samples/kick.wav": {
                "sd_size": 100,
                "sd_mtime": 1000.0,
                "local_size": st.st_size,
                "local_mtime": normalise_mtime(st.st_mtime),
                "hash": digest,
            },
        }

        with patch("fix_references.hash_file") as mock_hash:
            result = compute_migration_map(manifest, deluge_root)

        mock_hash.assert_not_called()
        assert not result.moved
        assert not result.deleted
        assert not result.added
        assert not result.ambiguous

    def test_stat_cache_miss_triggers_hash(self, tmp_path: Path) -> None:
        """Files whose stat doesn't match manifest are hashed."""
        content = b"changed content"
        deluge_root = _make_deluge_tree(tmp_path, {"kick.wav": content})
        digest = hashlib.sha256(content).hexdigest()

        # Stats won't match because _make_manifest uses dummy values
        manifest = _make_manifest({"samples/kick.wav": digest})

        result = compute_migration_map(manifest, deluge_root)

        # File hashed and found at same normalised path â†’ unchanged
        assert not result.moved

    def test_new_path_triggers_hash(self, tmp_path: Path) -> None:
        """Files at paths not in manifest are always hashed."""
        content = b"moved file"
        deluge_root = _make_deluge_tree(tmp_path, {"NewDir/kick.wav": content})
        digest = hashlib.sha256(content).hexdigest()

        manifest = _make_manifest({"samples/olddir/kick.wav": digest})

        result = compute_migration_map(manifest, deluge_root)

        assert "samples/olddir/kick.wav" in result.moved
        assert result.moved["samples/olddir/kick.wav"] == "SAMPLES/NewDir/kick.wav"


# ---------------------------------------------------------------------------
# Manifest key update
# ---------------------------------------------------------------------------


class TestManifestKeyUpdate:
    """Tests for update_manifest_keys."""

    def test_moved_keys_renamed(self, tmp_path: Path) -> None:
        """Moved files have their manifest keys renamed."""
        manifest: FilesDict = {
            "samples/old.wav": {
                "sd_size": 100, "sd_mtime": 1000.0,
                "local_size": 100, "local_mtime": 1000.0, "hash": "abc123",
            },
            "samples/other.wav": {
                "sd_size": 200, "sd_mtime": 2000.0,
                "local_size": 200, "local_mtime": 2000.0, "hash": "def456",
            },
        }
        moved = {"samples/old.wav": "SAMPLES/NEW/Renamed.wav"}
        manifest_path = tmp_path / "manifest.json"

        update_manifest_keys(manifest, moved, manifest_path)

        assert "samples/old.wav" not in manifest
        assert "samples/new/renamed.wav" in manifest
        assert manifest["samples/new/renamed.wav"]["hash"] == "abc123"
        assert "samples/other.wav" in manifest
        assert manifest_path.is_file()

    def test_no_moves_no_write(self, tmp_path: Path) -> None:
        """No moves produces no manifest write."""
        manifest: FilesDict = {
            "samples/a.wav": {
                "sd_size": 100, "sd_mtime": 1000.0,
                "local_size": 100, "local_mtime": 1000.0, "hash": "abc",
            },
        }
        manifest_path = tmp_path / "manifest.json"

        update_manifest_keys(manifest, {}, manifest_path)

        assert not manifest_path.exists()

    def test_write_failure_prints_warning(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Write failure produces a warning, not an error."""
        manifest: FilesDict = {
            "samples/old.wav": {
                "sd_size": 100, "sd_mtime": 1000.0,
                "local_size": 100, "local_mtime": 1000.0, "hash": "abc",
            },
        }
        moved = {"samples/old.wav": "SAMPLES/New.wav"}
        manifest_path = tmp_path / "manifest.json"

        with patch("fix_references.write_manifest", side_effect=OSError("disk full")):
            update_manifest_keys(manifest, moved, manifest_path)

        captured = capsys.readouterr()
        assert "Warning" in captured.out

    def test_preserves_hash_and_stats(self, tmp_path: Path) -> None:
        """Renamed key preserves all original data."""
        manifest: FilesDict = {
            "samples/old.wav": {
                "sd_size": 42, "sd_mtime": 999.0,
                "local_size": 42, "local_mtime": 888.0, "hash": "deadbeef",
            },
        }
        moved = {"samples/old.wav": "SAMPLES/New.wav"}
        manifest_path = tmp_path / "manifest.json"

        update_manifest_keys(manifest, moved, manifest_path)

        entry = manifest["samples/new.wav"]
        assert entry["sd_size"] == 42
        assert entry["sd_mtime"] == 999.0
        assert entry["local_size"] == 42
        assert entry["local_mtime"] == 888.0
        assert entry["hash"] == "deadbeef"

    def test_recovered_ref_renames_manifest_key(self, tmp_path: Path) -> None:
        """Recovered ref mapping renames the corresponding manifest key."""
        manifest: FilesDict = {
            "samples/old.wav": {
                "sd_size": 100, "sd_mtime": 1000.0,
                "local_size": 100, "local_mtime": 1000.0, "hash": "aaa",
            },
        }
        recovered_moved = {normalise_key("SAMPLES/Old.wav"): "SAMPLES/NEW/Found.wav"}
        manifest_path = tmp_path / "manifest.json"

        update_manifest_keys(manifest, recovered_moved, manifest_path)

        assert "samples/old.wav" not in manifest
        assert "samples/new/found.wav" in manifest
        assert manifest["samples/new/found.wav"]["hash"] == "aaa"
        assert manifest_path.is_file()

    def test_combined_moved_and_recovered(self, tmp_path: Path) -> None:
        """Both moved and recovered mappings are applied to the manifest."""
        manifest: FilesDict = {
            "samples/moved.wav": {
                "sd_size": 10, "sd_mtime": 100.0,
                "local_size": 10, "local_mtime": 100.0, "hash": "h1",
            },
            "samples/recovered.wav": {
                "sd_size": 20, "sd_mtime": 200.0,
                "local_size": 20, "local_mtime": 200.0, "hash": "h2",
            },
        }
        # Simulate combined mapping: moved + recovered merged by caller
        combined = {
            normalise_key("SAMPLES/Moved.wav"): "SAMPLES/Moved-New.wav",
            normalise_key("SAMPLES/Recovered.wav"): "SAMPLES/Recovered-New.wav",
        }
        manifest_path = tmp_path / "manifest.json"

        update_manifest_keys(manifest, combined, manifest_path)

        assert "samples/moved.wav" not in manifest
        assert "samples/recovered.wav" not in manifest
        assert "samples/moved-new.wav" in manifest
        assert manifest["samples/moved-new.wav"]["hash"] == "h1"
        assert "samples/recovered-new.wav" in manifest
        assert manifest["samples/recovered-new.wav"]["hash"] == "h2"

    def test_no_recovered_refs_no_extra_changes(self, tmp_path: Path) -> None:
        """No recovered refs produces no additional manifest changes beyond moved."""
        manifest: FilesDict = {
            "samples/a.wav": {
                "sd_size": 10, "sd_mtime": 100.0,
                "local_size": 10, "local_mtime": 100.0, "hash": "h1",
            },
            "samples/b.wav": {
                "sd_size": 20, "sd_mtime": 200.0,
                "local_size": 20, "local_mtime": 200.0, "hash": "h2",
            },
        }
        # Only moved, no recovered refs merged
        moved = {normalise_key("SAMPLES/A.wav"): "SAMPLES/A-New.wav"}
        manifest_path = tmp_path / "manifest.json"

        update_manifest_keys(manifest, moved, manifest_path)

        assert "samples/a.wav" not in manifest
        assert "samples/a-new.wav" in manifest
        # b.wav is untouched
        assert "samples/b.wav" in manifest
        assert manifest["samples/b.wav"]["hash"] == "h2"


# ---------------------------------------------------------------------------
# classify_ref_changes
# ---------------------------------------------------------------------------


def _make_ref(xml_file: str = "KITS/KIT001.XML", path: str = "SAMPLES/old.wav") -> SampleRef:
    """Helper: create a minimal SampleRef for testing."""
    return SampleRef(
        path=path,
        xml_file=Path(xml_file),
        xml_type="kit",
        preset_name="KIT001",
        ref_type="fileName-attribute",
        element_tag="osc1",
    )


class TestClassifyRefChanges:
    """Tests for classify_ref_changes."""

    def test_ref_in_migration_map_is_planned_change(self, tmp_path: Path) -> None:
        """A reference whose normalised path is in moved dict appears as a planned change."""
        deluge_root = tmp_path / "DELUGE"
        _write_minimal_kit_xml(
            deluge_root / "KITS" / "KIT001.XML",
            ["SAMPLES/DRUMS/OldKick.wav"],
        )
        migration = MigrationResult(
            moved={"samples/drums/oldkick.wav": "SAMPLES/DRUMS/NewKick.wav"},
        )

        result = classify_ref_changes(migration, deluge_root)

        assert len(result.changes) == 1
        assert result.changes[0].old_path == "SAMPLES/DRUMS/OldKick.wav"
        assert result.changes[0].new_path == "SAMPLES/DRUMS/NewKick.wav"
        assert not result.errors
        assert not result.warnings

    def test_ref_in_deleted_set_is_error(self, tmp_path: Path) -> None:
        """A reference whose normalised path is in the deleted set appears as an error."""
        deluge_root = tmp_path / "DELUGE"
        _write_minimal_kit_xml(
            deluge_root / "KITS" / "KIT001.XML",
            ["SAMPLES/DRUMS/Gone.wav"],
        )
        migration = MigrationResult(
            deleted={"somehash": ["samples/drums/gone.wav"]},
        )

        result = classify_ref_changes(migration, deluge_root)

        assert not result.changes
        assert len(result.errors) == 1
        assert result.errors[0].deleted_path == "SAMPLES/DRUMS/Gone.wav"
        assert not result.warnings

    def test_ref_in_ambiguous_set_is_warning(self, tmp_path: Path) -> None:
        """A reference whose normalised path is in the ambiguous before-paths appears as a warning."""
        deluge_root = tmp_path / "DELUGE"
        _write_minimal_kit_xml(
            deluge_root / "KITS" / "KIT001.XML",
            ["SAMPLES/DRUMS/Ambig.wav"],
        )
        migration = MigrationResult(
            ambiguous={
                "somehash": (
                    ["samples/drums/ambig.wav", "samples/drums/other.wav"],
                    ["SAMPLES/DRUMS/New1.wav", "SAMPLES/DRUMS/New2.wav"],
                ),
            },
        )

        result = classify_ref_changes(migration, deluge_root)

        assert not result.changes
        assert not result.errors
        assert len(result.warnings) == 1
        assert result.warnings[0].ambiguous_path == "SAMPLES/DRUMS/Ambig.wav"

    def test_valid_ref_not_in_results(self, tmp_path: Path) -> None:
        """A reference not in any migration category does not appear in results."""
        deluge_root = _make_deluge_tree(tmp_path, {"DRUMS/StillHere.wav": b"audio"})
        _write_minimal_kit_xml(
            deluge_root / "KITS" / "KIT001.XML",
            ["SAMPLES/DRUMS/StillHere.wav"],
        )
        migration = MigrationResult(
            after_hashes={"dummyhash": ["SAMPLES/DRUMS/StillHere.wav"]},
        )

        result = classify_ref_changes(migration, deluge_root)

        assert not result.changes
        assert not result.errors
        assert not result.warnings
        assert not result.missing

    def test_multiple_refs_across_multiple_xmls(self, tmp_path: Path) -> None:
        """References from multiple XML files are all classified correctly."""
        deluge_root = _make_deluge_tree(tmp_path, {"DRUMS/OK.wav": b"audio"})
        _write_minimal_kit_xml(
            deluge_root / "KITS" / "KIT001.XML",
            ["SAMPLES/DRUMS/Moved.wav"],
        )
        _write_minimal_kit_xml(
            deluge_root / "KITS" / "KIT002.XML",
            ["SAMPLES/DRUMS/Deleted.wav", "SAMPLES/DRUMS/OK.wav"],
        )
        migration = MigrationResult(
            moved={"samples/drums/moved.wav": "SAMPLES/DRUMS/NewMoved.wav"},
            deleted={"delhash": ["samples/drums/deleted.wav"]},
            after_hashes={"okhash": ["SAMPLES/DRUMS/OK.wav"]},
        )

        result = classify_ref_changes(migration, deluge_root)

        assert len(result.changes) == 1
        assert result.changes[0].old_path == "SAMPLES/DRUMS/Moved.wav"
        assert len(result.errors) == 1
        assert result.errors[0].deleted_path == "SAMPLES/DRUMS/Deleted.wav"
        assert not result.warnings

    def test_no_broken_refs(self, tmp_path: Path) -> None:
        """When all references are valid, result is empty."""
        deluge_root = _make_deluge_tree(tmp_path, {
            "DRUMS/Fine.wav": b"audio",
            "DRUMS/AlsoFine.wav": b"audio",
        })
        _write_minimal_kit_xml(
            deluge_root / "KITS" / "KIT001.XML",
            ["SAMPLES/DRUMS/Fine.wav", "SAMPLES/DRUMS/AlsoFine.wav"],
        )
        migration = MigrationResult(
            after_hashes={
                "hash1": ["SAMPLES/DRUMS/Fine.wav"],
                "hash2": ["SAMPLES/DRUMS/AlsoFine.wav"],
            },
        )

        result = classify_ref_changes(migration, deluge_root)

        assert result == ReferenceStatus()

    def test_ref_carries_sample_ref_metadata(self, tmp_path: Path) -> None:
        """Planned change carries the full SampleRef with correct metadata."""
        deluge_root = tmp_path / "DELUGE"
        _write_minimal_kit_xml(
            deluge_root / "KITS" / "MyKit.XML",
            ["SAMPLES/OldPath.wav"],
        )
        migration = MigrationResult(
            moved={"samples/oldpath.wav": "SAMPLES/NewPath.wav"},
        )

        result = classify_ref_changes(migration, deluge_root)

        change = result.changes[0]
        assert change.ref.xml_type == "kit"
        assert change.ref.preset_name == "MyKit"
        assert change.ref.ref_type == "fileName-attribute"

    def test_deleted_multiple_paths_per_hash(self, tmp_path: Path) -> None:
        """Multiple deleted paths under the same hash are all detected."""
        deluge_root = tmp_path / "DELUGE"
        _write_minimal_kit_xml(
            deluge_root / "KITS" / "KIT001.XML",
            ["SAMPLES/A.wav", "SAMPLES/B.wav"],
        )
        migration = MigrationResult(
            deleted={"hash1": ["samples/a.wav", "samples/b.wav"]},
        )

        result = classify_ref_changes(migration, deluge_root)

        assert len(result.errors) == 2
        deleted_paths = {e.deleted_path for e in result.errors}
        assert deleted_paths == {"SAMPLES/A.wav", "SAMPLES/B.wav"}

    def test_missing_ref_not_on_disk(self, tmp_path: Path) -> None:
        """A reference not in migration map and not on disk appears as missing."""
        deluge_root = _make_deluge_tree(tmp_path, {"DRUMS/Other.wav": b"audio"})
        _write_minimal_kit_xml(
            deluge_root / "KITS" / "KIT001.XML",
            ["SAMPLES/DRUMS/CB1-BD~1.WAV"],
        )
        migration = MigrationResult(
            after_hashes={"otherhash": ["SAMPLES/DRUMS/Other.wav"]},
        )

        result = classify_ref_changes(migration, deluge_root)

        assert not result.changes
        assert not result.errors
        assert not result.warnings
        assert len(result.missing) == 1
        assert result.missing[0].missing_path == "SAMPLES/DRUMS/CB1-BD~1.WAV"

    def test_case_insensitive_ref_not_missing(self, tmp_path: Path) -> None:
        """A reference differing only in case from a current path is not missing."""
        deluge_root = _make_deluge_tree(tmp_path, {"Artists/Chaz/CB1-bdrum1.wav": b"audio"})
        _write_minimal_kit_xml(
            deluge_root / "KITS" / "KIT001.XML",
            ["SAMPLES/ARTISTS/CHAZ/CB1-BDRUM1.WAV"],
        )
        migration = MigrationResult(
            after_hashes={"dummyhash": ["SAMPLES/Artists/Chaz/CB1-bdrum1.wav"]},
        )

        result = classify_ref_changes(migration, deluge_root)

        assert not result.changes
        assert not result.errors
        assert not result.warnings
        assert not result.missing


# ---------------------------------------------------------------------------
# preview_and_apply
# ---------------------------------------------------------------------------


class TestPreviewAndApply:
    """Tests for the preview_and_apply function."""

    def test_empty_result_nothing_to_do(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Empty ReferenceStatus prints 'Nothing to do' and returns."""
        preview_and_apply(ReferenceStatus(), tmp_path)

        captured = capsys.readouterr()
        assert "Nothing to do" in captured.out

    def test_changes_grouped_by_xml_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Preview output groups changes by XML file."""
        result = ReferenceStatus(
            changes=[
                PlannedChange(
                    ref=_make_ref("KITS/KIT001.XML", "SAMPLES/a.wav"),
                    old_path="SAMPLES/a.wav",
                    new_path="SAMPLES/b.wav",
                ),
                PlannedChange(
                    ref=_make_ref("KITS/KIT002.XML", "SAMPLES/c.wav"),
                    old_path="SAMPLES/c.wav",
                    new_path="SAMPLES/d.wav",
                ),
            ],
        )

        with patch("fix_references.confirm_apply", return_value=False):
            preview_and_apply(result, tmp_path)

        captured = capsys.readouterr()
        assert 'KIT001.XML: "SAMPLES/a.wav" \u2192 "SAMPLES/b.wav"' in captured.out
        assert 'KIT002.XML: "SAMPLES/c.wav" \u2192 "SAMPLES/d.wav"' in captured.out

    def test_duplicate_refs_show_count(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Multiple refs with the same old\u2192new in one file show '\xd7 N refs'."""
        ref = _make_ref("KITS/KIT001.XML", "SAMPLES/a.wav")
        result = ReferenceStatus(
            changes=[
                PlannedChange(ref=ref, old_path="SAMPLES/a.wav", new_path="SAMPLES/b.wav"),
                PlannedChange(ref=ref, old_path="SAMPLES/a.wav", new_path="SAMPLES/b.wav"),
            ],
        )

        with patch("fix_references.confirm_apply", return_value=False):
            preview_and_apply(result, tmp_path)

        captured = capsys.readouterr()
        assert "\xd7 2 refs" in captured.out

    def test_error_section_displayed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Errors are displayed under the 'ERRORS' section header."""
        result = ReferenceStatus(
            errors=[
                BrokenRefError(
                    ref=_make_ref("KITS/KIT001.XML", "SAMPLES/gone.wav"),
                    deleted_path="SAMPLES/gone.wav",
                ),
            ],
        )

        preview_and_apply(result, tmp_path)

        captured = capsys.readouterr()
        assert "ERRORS \u2014 Requires Manual Resolution" in captured.out
        assert "SAMPLES/gone.wav" in captured.out
        assert "sample deleted" in captured.out

    def test_warning_section_displayed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Warnings are displayed under the 'WARNINGS' section header."""
        result = ReferenceStatus(
            warnings=[
                AmbiguousRefWarning(
                    ref=_make_ref("KITS/KIT001.XML", "SAMPLES/ambig.wav"),
                    ambiguous_path="SAMPLES/ambig.wav",
                ),
            ],
        )

        preview_and_apply(result, tmp_path)

        captured = capsys.readouterr()
        assert "WARNINGS \u2014 Ambiguous Mappings" in captured.out
        assert "SAMPLES/ambig.wav" in captured.out
        assert "multiple files share this hash" in captured.out

    def test_summary_line_counts(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Summary line shows correct counts for changes, files, errors, warnings."""
        result = ReferenceStatus(
            changes=[
                PlannedChange(
                    ref=_make_ref("KITS/KIT001.XML", "SAMPLES/a.wav"),
                    old_path="SAMPLES/a.wav",
                    new_path="SAMPLES/b.wav",
                ),
                PlannedChange(
                    ref=_make_ref("KITS/KIT002.XML", "SAMPLES/c.wav"),
                    old_path="SAMPLES/c.wav",
                    new_path="SAMPLES/d.wav",
                ),
            ],
            errors=[
                BrokenRefError(
                    ref=_make_ref("KITS/KIT001.XML", "SAMPLES/gone.wav"),
                    deleted_path="SAMPLES/gone.wav",
                ),
            ],
            warnings=[
                AmbiguousRefWarning(
                    ref=_make_ref("KITS/KIT001.XML", "SAMPLES/ambig.wav"),
                    ambiguous_path="SAMPLES/ambig.wav",
                ),
            ],
        )

        with patch("fix_references.confirm_apply", return_value=False):
            preview_and_apply(result, tmp_path)

        captured = capsys.readouterr()
        assert "2 changes, 0 recovered, 1 errors, 1 warnings, 0 missing." in captured.out

    def test_error_warning_recommends_resolution(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """When errors exist, a warning recommending resolution is shown."""
        result = ReferenceStatus(
            changes=[
                PlannedChange(
                    ref=_make_ref("KITS/KIT001.XML", "SAMPLES/a.wav"),
                    old_path="SAMPLES/a.wav",
                    new_path="SAMPLES/b.wav",
                ),
            ],
            errors=[
                BrokenRefError(
                    ref=_make_ref("KITS/KIT001.XML", "SAMPLES/gone.wav"),
                    deleted_path="SAMPLES/gone.wav",
                ),
            ],
        )

        with patch("fix_references.confirm_apply", return_value=False):
            preview_and_apply(result, tmp_path)

        captured = capsys.readouterr()
        assert "Resolve errors before applying" in captured.out

    def test_apply_calls_update_sample_refs(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """On confirm, update_sample_refs is called with correct mapping per XML file."""
        deluge_root = tmp_path / "DELUGE"
        result = ReferenceStatus(
            changes=[
                PlannedChange(
                    ref=_make_ref("KITS/KIT001.XML", "SAMPLES/a.wav"),
                    old_path="SAMPLES/a.wav",
                    new_path="SAMPLES/b.wav",
                ),
            ],
        )

        with patch("fix_references.confirm_apply", return_value=True), patch(
            "fix_references.update_sample_refs", return_value=1
        ) as mock_update:
            preview_and_apply(result, deluge_root)

        mock_update.assert_called_once_with(
            deluge_root / "KITS" / "KIT001.XML",
            {"SAMPLES/a.wav": "SAMPLES/b.wav"},
        )

        captured = capsys.readouterr()
        assert "1 files modified" in captured.out
        assert "1 references updated" in captured.out

    def test_no_apply_on_decline(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """On decline, no changes are applied and message is shown."""
        result = ReferenceStatus(
            changes=[
                PlannedChange(
                    ref=_make_ref("KITS/KIT001.XML", "SAMPLES/a.wav"),
                    old_path="SAMPLES/a.wav",
                    new_path="SAMPLES/b.wav",
                ),
            ],
        )

        with patch("fix_references.confirm_apply", return_value=False), patch(
            "fix_references.update_sample_refs"
        ) as mock_update:
            preview_and_apply(result, tmp_path)

        mock_update.assert_not_called()

        captured = capsys.readouterr()
        assert "No changes applied." in captured.out

    def test_auto_apply_skips_prompt(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """auto_apply=True skips the confirmation prompt."""
        deluge_root = tmp_path / "DELUGE"
        result = ReferenceStatus(
            changes=[
                PlannedChange(
                    ref=_make_ref("KITS/KIT001.XML", "SAMPLES/a.wav"),
                    old_path="SAMPLES/a.wav",
                    new_path="SAMPLES/b.wav",
                ),
            ],
        )

        with patch("fix_references.confirm_apply") as mock_confirm, patch(
            "fix_references.update_sample_refs", return_value=1
        ):
            preview_and_apply(result, deluge_root, auto_apply=True)

        mock_confirm.assert_not_called()

        captured = capsys.readouterr()
        assert "1 files modified" in captured.out

    def test_post_apply_summary(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Post-apply summary shows files modified and references updated."""
        deluge_root = tmp_path / "DELUGE"
        result = ReferenceStatus(
            changes=[
                PlannedChange(
                    ref=_make_ref("KITS/KIT001.XML", "SAMPLES/a.wav"),
                    old_path="SAMPLES/a.wav",
                    new_path="SAMPLES/b.wav",
                ),
                PlannedChange(
                    ref=_make_ref("KITS/KIT002.XML", "SAMPLES/c.wav"),
                    old_path="SAMPLES/c.wav",
                    new_path="SAMPLES/d.wav",
                ),
            ],
        )

        with patch("fix_references.confirm_apply", return_value=True), patch(
            "fix_references.update_sample_refs", return_value=1
        ):
            preview_and_apply(result, deluge_root)

        captured = capsys.readouterr()
        assert "2 files modified" in captured.out
        assert "2 references updated" in captured.out

    def test_missing_section_displayed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Missing refs are displayed under the 'MISSING' section header."""
        result = ReferenceStatus(
            missing=[
                MissingRefError(
                    ref=_make_ref("KITS/KIT001.XML", "SAMPLES/DRUMS/CB1-BD~1.WAV"),
                    missing_path="SAMPLES/DRUMS/CB1-BD~1.WAV",
                ),
            ],
        )

        preview_and_apply(result, tmp_path)

        captured = capsys.readouterr()
        assert "MISSING \u2014 Sample Path Not Found" in captured.out
        assert "SAMPLES/DRUMS/CB1-BD~1.WAV" in captured.out
        assert "no matching file on disk" in captured.out

    def test_returns_no_issues_no_apply_when_nothing(self, tmp_path: Path) -> None:
        """Returns (False, False) when no changes, errors, or warnings exist."""
        assert preview_and_apply(ReferenceStatus(), tmp_path) == (False, False)

    def test_returns_issues_true_when_missing(self, tmp_path: Path) -> None:
        """Returns (True, False) when missing refs exist."""
        result = ReferenceStatus(
            missing=[
                MissingRefError(
                    ref=_make_ref("KITS/KIT001.XML", "SAMPLES/DRUMS/CB1-BD~1.WAV"),
                    missing_path="SAMPLES/DRUMS/CB1-BD~1.WAV",
                ),
            ],
        )

        has_issues, applied = preview_and_apply(result, tmp_path)

        assert has_issues is True
        assert applied is False

    def test_only_errors_no_apply_prompt(self, tmp_path: Path) -> None:
        """When there are only errors (no changes), no apply prompt is shown."""
        result = ReferenceStatus(
            errors=[
                BrokenRefError(
                    ref=_make_ref("KITS/KIT001.XML", "SAMPLES/gone.wav"),
                    deleted_path="SAMPLES/gone.wav",
                ),
            ],
        )

        with patch("fix_references.confirm_apply") as mock_confirm:
            has_issues, applied = preview_and_apply(result, tmp_path)

        mock_confirm.assert_not_called()
        assert has_issues is True
        assert applied is False

    def test_returns_no_issues_applied_when_changes_only(self, tmp_path: Path) -> None:
        """Returns (False, True) when there are fixable changes but no errors."""
        deluge_root = tmp_path / "DELUGE"
        result = ReferenceStatus(
            changes=[
                PlannedChange(
                    ref=_make_ref("KITS/KIT001.XML", "SAMPLES/a.wav"),
                    old_path="SAMPLES/a.wav",
                    new_path="SAMPLES/b.wav",
                ),
            ],
        )

        with patch("fix_references.confirm_apply", return_value=True), patch(
            "fix_references.update_sample_refs", return_value=1
        ):
            has_issues, applied = preview_and_apply(result, deluge_root)

        assert has_issues is False
        assert applied is True

    def test_returns_issues_and_applied_when_errors_and_changes(self, tmp_path: Path) -> None:
        """Returns (True, True) when errors exist but fixable changes were applied."""
        deluge_root = tmp_path / "DELUGE"
        result = ReferenceStatus(
            changes=[
                PlannedChange(
                    ref=_make_ref("KITS/KIT001.XML", "SAMPLES/a.wav"),
                    old_path="SAMPLES/a.wav",
                    new_path="SAMPLES/b.wav",
                ),
            ],
            errors=[
                BrokenRefError(
                    ref=_make_ref("KITS/KIT001.XML", "SAMPLES/gone.wav"),
                    deleted_path="SAMPLES/gone.wav",
                ),
            ],
        )

        with patch("fix_references.confirm_apply", return_value=True), patch(
            "fix_references.update_sample_refs", return_value=1
        ):
            has_issues, applied = preview_and_apply(result, deluge_root)

        assert has_issues is True
        assert applied is True


# ---------------------------------------------------------------------------
# CLI integration (main)
# ---------------------------------------------------------------------------


class TestMainExitCodes:
    """Tests for CLI exit codes via main()."""

    def test_fix_exits_0_no_errors(self, tmp_path: Path) -> None:
        """Exits 0 when no broken references found."""
        from fix_references import main

        content = b"kick_audio"
        deluge_root = _make_deluge_tree(tmp_path, {"kick.wav": content})
        digest = hashlib.sha256(content).hexdigest()

        manifest = _make_manifest({"samples/kick.wav": digest})
        manifest_file = tmp_path / "test_manifest.json"
        _write_manifest_file(manifest_file, manifest)

        _write_minimal_kit_xml(
            deluge_root / "KITS" / "KIT001.XML",
            ["SAMPLES/kick.wav"],
        )

        with patch("fix_references.get_deluge_root", return_value=deluge_root):
            main(["--manifest", str(manifest_file)])  # Should not raise

    def test_fix_exits_1_when_errors(self, tmp_path: Path) -> None:
        """Exits 1 when deleted references are detected."""
        from fix_references import main

        deluge_root = tmp_path / "DELUGE"
        (deluge_root / "SAMPLES").mkdir(parents=True)
        _write_minimal_kit_xml(
            deluge_root / "KITS" / "KIT001.XML",
            ["SAMPLES/gone.wav"],
        )

        manifest = _make_manifest({"samples/gone.wav": "ab" * 32})
        manifest_file = tmp_path / "test_manifest.json"
        _write_manifest_file(manifest_file, manifest)

        with patch("fix_references.get_deluge_root", return_value=deluge_root):
            with pytest.raises(SystemExit) as exc_info:
                main(["--manifest", str(manifest_file)])
            assert exc_info.value.code == 1

    def test_fix_apply_skips_prompt(self, tmp_path: Path) -> None:
        """--apply skips the confirmation prompt and applies changes."""
        from fix_references import main

        content = b"kick_audio"
        deluge_root = _make_deluge_tree(tmp_path, {"NewKick.wav": content})
        digest = hashlib.sha256(content).hexdigest()
        _write_minimal_kit_xml(
            deluge_root / "KITS" / "KIT001.XML",
            ["SAMPLES/OldKick.wav"],
        )

        manifest = _make_manifest({"samples/oldkick.wav": digest})
        manifest_file = tmp_path / "test_manifest.json"
        _write_manifest_file(manifest_file, manifest)

        with patch("fix_references.get_deluge_root", return_value=deluge_root), patch(
            "fix_references.confirm_apply"
        ) as mock_confirm:
            main(["--manifest", str(manifest_file), "--apply"])

        mock_confirm.assert_not_called()


# ---------------------------------------------------------------------------
# Phase 4: Recovery tests
# ---------------------------------------------------------------------------


class TestAfterHashesExposure:
    """Task 4.1: Verify compute_migration_map returns after_hashes correctly."""

    def test_after_hashes_maps_hashes_to_original_case_paths(self, tmp_path: Path) -> None:
        """after_hashes maps SHA-256 hashes to original-case filesystem paths."""
        content = b"kick audio"
        deluge_root = _make_deluge_tree(tmp_path, {"DRUMS/Kick.wav": content})
        digest = hashlib.sha256(content).hexdigest()

        result = compute_migration_map({}, deluge_root)

        assert digest in result.after_hashes
        assert result.after_hashes[digest] == ["SAMPLES/DRUMS/Kick.wav"]

    def test_after_hashes_empty_for_empty_samples(self, tmp_path: Path) -> None:
        """after_hashes is empty when SAMPLES dir contains no WAV files."""
        deluge_root = tmp_path / "DELUGE"
        (deluge_root / "SAMPLES").mkdir(parents=True)

        result = compute_migration_map({}, deluge_root)

        assert result.after_hashes == {}

    def test_after_hashes_via_stat_cache_hit(self, tmp_path: Path) -> None:
        """Stat-cache hits produce correct after_hashes entries."""
        content = b"cached audio"
        deluge_root = _make_deluge_tree(tmp_path, {"Pad.wav": content})
        digest = hashlib.sha256(content).hexdigest()
        file_path = deluge_root / "SAMPLES" / "Pad.wav"
        st = file_path.stat()

        manifest: FilesDict = {
            "samples/pad.wav": {
                "sd_size": 100,
                "sd_mtime": 1000.0,
                "local_size": st.st_size,
                "local_mtime": normalise_mtime(st.st_mtime),
                "hash": digest,
            },
        }

        with patch("fix_references.hash_file") as mock_hash:
            result = compute_migration_map(manifest, deluge_root)

        mock_hash.assert_not_called()
        assert digest in result.after_hashes
        assert result.after_hashes[digest] == ["SAMPLES/Pad.wav"]


class TestSingleCandidateRecovery:
    """Task 4.2: Missing ref with one basename match is recovered."""

    def test_single_candidate_recovered(self, tmp_path: Path) -> None:
        """Ref whose basename matches exactly one file on disk is recovered."""
        deluge_root = _make_deluge_tree(tmp_path, {"NewDir/Kick.wav": b"audio"})
        _write_minimal_kit_xml(
            deluge_root / "KITS" / "KIT001.XML",
            ["SAMPLES/OldDir/Kick.wav"],
        )
        migration = MigrationResult(
            after_hashes={"hash1": ["SAMPLES/NewDir/Kick.wav"]},
        )

        result = classify_ref_changes(migration, deluge_root)

        assert len(result.recovered) == 1
        assert result.recovered[0].old_path == "SAMPLES/OldDir/Kick.wav"
        assert result.recovered[0].new_path == "SAMPLES/NewDir/Kick.wav"
        assert not result.missing

    def test_single_candidate_has_one_entry(self, tmp_path: Path) -> None:
        """Recovered ref's candidate list has exactly one entry."""
        deluge_root = _make_deluge_tree(tmp_path, {"NewDir/Kick.wav": b"audio"})
        _write_minimal_kit_xml(
            deluge_root / "KITS" / "KIT001.XML",
            ["SAMPLES/OldDir/Kick.wav"],
        )
        migration = MigrationResult(
            after_hashes={"hash1": ["SAMPLES/NewDir/Kick.wav"]},
        )

        result = classify_ref_changes(migration, deluge_root)

        assert len(result.recovered[0].candidates) == 1
        assert result.recovered[0].candidates[0] == ("SAMPLES/NewDir/Kick.wav", "hash1")

    def test_single_candidate_case_insensitive_basename(self, tmp_path: Path) -> None:
        """Basename matching is case-insensitive."""
        deluge_root = _make_deluge_tree(tmp_path, {"NewDir/kick.wav": b"audio"})
        _write_minimal_kit_xml(
            deluge_root / "KITS" / "KIT001.XML",
            ["SAMPLES/OldDir/KICK.WAV"],
        )
        migration = MigrationResult(
            after_hashes={"hash1": ["SAMPLES/NewDir/kick.wav"]},
        )

        result = classify_ref_changes(migration, deluge_root)

        assert len(result.recovered) == 1
        assert result.recovered[0].new_path == "SAMPLES/NewDir/kick.wav"
        assert not result.missing


class TestMultiCandidateSameHashRecovery:
    """Task 4.3: Multiple candidates with same hash — path similarity picks best."""

    def test_same_hash_picks_best_path_similarity(self, tmp_path: Path) -> None:
        """When all candidates share the same hash, the best path similarity wins."""
        deluge_root = _make_deluge_tree(tmp_path, {
            "DRUMS/Kicks/Kick.wav": b"audio",
            "OTHER/Kick.wav": b"audio",
        })
        _write_minimal_kit_xml(
            deluge_root / "KITS" / "KIT001.XML",
            ["SAMPLES/DRUMS/Kicks/OldKick/Kick.wav"],
        )
        same_hash = "aabb" * 16
        migration = MigrationResult(
            after_hashes={
                same_hash: [
                    "SAMPLES/DRUMS/Kicks/Kick.wav",
                    "SAMPLES/OTHER/Kick.wav",
                ],
            },
        )

        result = classify_ref_changes(migration, deluge_root)

        assert len(result.recovered) == 1
        # DRUMS/Kicks/Kick.wav shares more trailing components with the ref
        assert result.recovered[0].new_path == "SAMPLES/DRUMS/Kicks/Kick.wav"
        assert not result.missing

    def test_same_hash_candidates_all_listed(self, tmp_path: Path) -> None:
        """Candidates list contains all matches."""
        deluge_root = _make_deluge_tree(tmp_path, {
            "A/Snare.wav": b"audio",
            "B/Snare.wav": b"audio",
        })
        _write_minimal_kit_xml(
            deluge_root / "KITS" / "KIT001.XML",
            ["SAMPLES/OldDir/Snare.wav"],
        )
        same_hash = "ccdd" * 16
        migration = MigrationResult(
            after_hashes={same_hash: ["SAMPLES/A/Snare.wav", "SAMPLES/B/Snare.wav"]},
        )

        result = classify_ref_changes(migration, deluge_root)

        assert len(result.recovered) == 1
        assert len(result.recovered[0].candidates) == 2
        candidate_paths = {c[0] for c in result.recovered[0].candidates}
        assert candidate_paths == {"SAMPLES/A/Snare.wav", "SAMPLES/B/Snare.wav"}

    def test_same_hash_ref_in_recovered_not_missing(self, tmp_path: Path) -> None:
        """Same-hash multi-candidate ref is in recovered, not missing."""
        deluge_root = _make_deluge_tree(tmp_path, {
            "A/Hat.wav": b"audio",
            "B/Hat.wav": b"audio",
        })
        _write_minimal_kit_xml(
            deluge_root / "KITS" / "KIT001.XML",
            ["SAMPLES/Old/Hat.wav"],
        )
        same_hash = "eeff" * 16
        migration = MigrationResult(
            after_hashes={same_hash: ["SAMPLES/A/Hat.wav", "SAMPLES/B/Hat.wav"]},
        )

        result = classify_ref_changes(migration, deluge_root)

        assert len(result.recovered) == 1
        assert not result.missing


class TestMultiCandidateDifferentHash:
    """Task 4.4: Multiple candidates with different hashes — stays missing."""

    def test_different_hashes_not_recovered(self, tmp_path: Path) -> None:
        """Ref with multiple basename matches having different hashes stays missing."""
        deluge_root = _make_deluge_tree(tmp_path, {
            "A/Kick.wav": b"audio_a",
            "B/Kick.wav": b"audio_b",
        })
        _write_minimal_kit_xml(
            deluge_root / "KITS" / "KIT001.XML",
            ["SAMPLES/OldDir/Kick.wav"],
        )
        migration = MigrationResult(
            after_hashes={
                "hash_a": ["SAMPLES/A/Kick.wav"],
                "hash_b": ["SAMPLES/B/Kick.wav"],
            },
        )

        result = classify_ref_changes(migration, deluge_root)

        assert not result.recovered
        assert len(result.missing) == 1
        assert result.missing[0].missing_path == "SAMPLES/OldDir/Kick.wav"


class TestZeroCandidateRecovery:
    """Task 4.5: Missing ref with no basename match remains missing."""

    def test_no_basename_match_stays_missing(self, tmp_path: Path) -> None:
        """Ref whose basename matches no file on disk remains missing."""
        deluge_root = _make_deluge_tree(tmp_path, {"Other.wav": b"audio"})
        _write_minimal_kit_xml(
            deluge_root / "KITS" / "KIT001.XML",
            ["SAMPLES/DRUMS/NonExistent.wav"],
        )
        migration = MigrationResult(
            after_hashes={"somehash": ["SAMPLES/Other.wav"]},
        )

        result = classify_ref_changes(migration, deluge_root)

        assert not result.recovered
        assert len(result.missing) == 1
        assert result.missing[0].missing_path == "SAMPLES/DRUMS/NonExistent.wav"


class TestCandidateThresholdExceeded:
    """Task 4.6: More than MAX_RECOVERY_CANDIDATES matches → stays missing."""

    def test_exceeding_threshold_stays_missing(self, tmp_path: Path) -> None:
        """Ref exceeding the candidate threshold is not recovered."""
        # Create MAX_RECOVERY_CANDIDATES + 1 files with the same basename
        wav_files = {
            f"Dir{i}/Common.wav": b"audio" for i in range(MAX_RECOVERY_CANDIDATES + 1)
        }
        deluge_root = _make_deluge_tree(tmp_path, wav_files)
        _write_minimal_kit_xml(
            deluge_root / "KITS" / "KIT001.XML",
            ["SAMPLES/Missing/Common.wav"],
        )
        after_hashes: dict[str, list[str]] = {}
        for i in range(MAX_RECOVERY_CANDIDATES + 1):
            h = f"hash{i:02d}" + "00" * 30
            after_hashes[h] = [f"SAMPLES/Dir{i}/Common.wav"]

        migration = MigrationResult(after_hashes=after_hashes)

        result = classify_ref_changes(migration, deluge_root)

        assert not result.recovered
        assert len(result.missing) == 1

    def test_at_threshold_is_recovered(self, tmp_path: Path) -> None:
        """Ref with exactly MAX_RECOVERY_CANDIDATES candidates is still recovered."""
        wav_files = {
            f"Dir{i}/Common.wav": b"audio" for i in range(MAX_RECOVERY_CANDIDATES)
        }
        deluge_root = _make_deluge_tree(tmp_path, wav_files)
        _write_minimal_kit_xml(
            deluge_root / "KITS" / "KIT001.XML",
            ["SAMPLES/Missing/Common.wav"],
        )
        # All same hash so recovery via path similarity
        same_hash = "abcd" * 16
        after_hashes: dict[str, list[str]] = {
            same_hash: [f"SAMPLES/Dir{i}/Common.wav" for i in range(MAX_RECOVERY_CANDIDATES)],
        }

        migration = MigrationResult(after_hashes=after_hashes)

        result = classify_ref_changes(migration, deluge_root)

        assert len(result.recovered) == 1
        assert not result.missing


class TestPathSimilarity:
    """Task 4.7: Unit tests for path_similarity function."""

    def test_identical_paths(self) -> None:
        """Identical paths score the full component count."""
        score = path_similarity("SAMPLES/DRUMS/Kick.wav", "SAMPLES/DRUMS/Kick.wav")
        assert score == 3  # Kick.wav, DRUMS, SAMPLES

    def test_shared_parent_scores_higher(self) -> None:
        """Paths sharing parent directories score higher than those that don't."""
        score_shared = path_similarity(
            "SAMPLES/DRUMS/Kicks/Kick.wav", "SAMPLES/DRUMS/Kicks/Kick.wav"
        )
        score_not_shared = path_similarity(
            "SAMPLES/DRUMS/Kicks/Kick.wav", "SAMPLES/OTHER/Kick.wav"
        )
        assert score_shared > score_not_shared

    def test_case_insensitive(self) -> None:
        """Comparison is case-insensitive."""
        score = path_similarity("SAMPLES/DRUMS/Kick.wav", "samples/drums/kick.wav")
        assert score == 3

    def test_different_depth_paths(self) -> None:
        """Paths of different depths are handled correctly."""
        score = path_similarity(
            "SAMPLES/DRUMS/Sub/Kick.wav", "SAMPLES/DRUMS/Kick.wav"
        )
        # Kick.wav matches, then Sub != DRUMS → stops
        assert score == 1

    def test_no_matching_components(self) -> None:
        """Completely different paths score 0."""
        score = path_similarity("A/B/C.wav", "X/Y/Z.wav")
        assert score == 0

    def test_only_basename_matches(self) -> None:
        """When only the basename matches, score is 1."""
        score = path_similarity("A/B/Kick.wav", "X/Y/Kick.wav")
        assert score == 1


class TestRecoveredPreviewOutput:
    """Task 4.8: RECOVERED section in preview output."""

    def test_recovered_section_header(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """RECOVERED section header appears when recovered refs exist."""
        result = ReferenceStatus(
            recovered=[
                RecoveredRefChange(
                    ref=_make_ref("KITS/KIT001.XML", "SAMPLES/Old/Kick.wav"),
                    old_path="SAMPLES/Old/Kick.wav",
                    new_path="SAMPLES/New/Kick.wav",
                    candidates=[("SAMPLES/New/Kick.wav", "hash1")],
                ),
            ],
        )

        with patch("fix_references.confirm_apply", return_value=False):
            preview_and_apply(result, tmp_path)

        captured = capsys.readouterr()
        assert "RECOVERED" in captured.out

    def test_recovered_shows_old_to_new(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Recovered refs show old → new path."""
        result = ReferenceStatus(
            recovered=[
                RecoveredRefChange(
                    ref=_make_ref("KITS/KIT001.XML", "SAMPLES/Old/Kick.wav"),
                    old_path="SAMPLES/Old/Kick.wav",
                    new_path="SAMPLES/New/Kick.wav",
                    candidates=[("SAMPLES/New/Kick.wav", "hash1")],
                ),
            ],
        )

        with patch("fix_references.confirm_apply", return_value=False):
            preview_and_apply(result, tmp_path)

        captured = capsys.readouterr()
        assert '"SAMPLES/Old/Kick.wav" \u2192 "SAMPLES/New/Kick.wav"' in captured.out

    def test_summary_includes_recovered_count(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Summary line includes recovered count."""
        result = ReferenceStatus(
            recovered=[
                RecoveredRefChange(
                    ref=_make_ref("KITS/KIT001.XML", "SAMPLES/Old/Kick.wav"),
                    old_path="SAMPLES/Old/Kick.wav",
                    new_path="SAMPLES/New/Kick.wav",
                    candidates=[("SAMPLES/New/Kick.wav", "hash1")],
                ),
            ],
        )

        with patch("fix_references.confirm_apply", return_value=False):
            preview_and_apply(result, tmp_path)

        captured = capsys.readouterr()
        assert "0 changes, 1 recovered, 0 errors, 0 warnings, 0 missing." in captured.out

    def test_no_recovered_section_when_empty(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """No RECOVERED section when recovered list is empty."""
        result = ReferenceStatus(
            errors=[
                BrokenRefError(
                    ref=_make_ref("KITS/KIT001.XML", "SAMPLES/gone.wav"),
                    deleted_path="SAMPLES/gone.wav",
                ),
            ],
        )

        preview_and_apply(result, tmp_path)

        captured = capsys.readouterr()
        assert "RECOVERED" not in captured.out


class TestApplyIncludesRecovered:
    """Task 4.9: Apply includes recovered refs (XML updated)."""

    def test_recovered_refs_applied_to_xml(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Recovered refs update XML file contents after apply."""
        deluge_root = tmp_path / "DELUGE"
        xml_path = deluge_root / "KITS" / "KIT001.XML"
        _write_minimal_kit_xml(xml_path, ["SAMPLES/Old/Kick.wav"])

        result = ReferenceStatus(
            recovered=[
                RecoveredRefChange(
                    ref=SampleRef(
                        path="SAMPLES/Old/Kick.wav",
                        xml_file=Path("KITS/KIT001.XML"),
                        xml_type="kit",
                        preset_name="KIT001",
                        ref_type="fileName-attribute",
                        element_tag="osc1",
                    ),
                    old_path="SAMPLES/Old/Kick.wav",
                    new_path="SAMPLES/New/Kick.wav",
                    candidates=[("SAMPLES/New/Kick.wav", "hash1")],
                ),
            ],
        )

        with patch("fix_references.confirm_apply", return_value=True):
            has_issues, applied = preview_and_apply(result, deluge_root)

        xml_content = xml_path.read_text(encoding="utf-8")
        assert "SAMPLES/New/Kick.wav" in xml_content
        assert "SAMPLES/Old/Kick.wav" not in xml_content
        assert applied is True

    def test_apply_summary_includes_recovered(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Apply summary counts include recovered ref updates."""
        deluge_root = tmp_path / "DELUGE"
        result = ReferenceStatus(
            recovered=[
                RecoveredRefChange(
                    ref=_make_ref("KITS/KIT001.XML", "SAMPLES/Old/Kick.wav"),
                    old_path="SAMPLES/Old/Kick.wav",
                    new_path="SAMPLES/New/Kick.wav",
                    candidates=[("SAMPLES/New/Kick.wav", "hash1")],
                ),
            ],
        )

        with patch("fix_references.confirm_apply", return_value=True), patch(
            "fix_references.update_sample_refs", return_value=1
        ):
            preview_and_apply(result, deluge_root)

        captured = capsys.readouterr()
        assert "1 files modified" in captured.out
        assert "1 references updated" in captured.out


class TestGetExistingSamplesRemoved:
    """Task 4.10: classify_ref_changes no longer calls get_existing_samples."""

    def test_no_get_existing_samples_in_source(self) -> None:
        """classify_ref_changes source code does not reference get_existing_samples."""
        import inspect

        source = inspect.getsource(classify_ref_changes)
        assert "get_existing_samples" not in source

    def test_existing_files_still_valid(self, tmp_path: Path) -> None:
        """Refs to existing files are correctly identified as valid (not missing)."""
        deluge_root = _make_deluge_tree(tmp_path, {"DRUMS/Kick.wav": b"audio"})
        _write_minimal_kit_xml(
            deluge_root / "KITS" / "KIT001.XML",
            ["SAMPLES/DRUMS/Kick.wav"],
        )
        migration = MigrationResult(
            after_hashes={"hash1": ["SAMPLES/DRUMS/Kick.wav"]},
        )

        result = classify_ref_changes(migration, deluge_root)

        assert not result.changes
        assert not result.errors
        assert not result.warnings
        assert not result.missing
        assert not result.recovered

