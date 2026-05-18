# Deluge CLI v0.1
"""Tests for sync_from_sd.py — manifest logic."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from deluge_lib.syncing import (
    build_post_sync_manifest,
)

from tests.conftest import _touch
from deluge_lib.scanning import FileEntry, ScanResult, normalise_mtime
from deluge_lib.syncing import FileRecord, SyncError, SyncPlan, SyncResult, execute_plan, read_manifest, write_manifest


# =============================================================================
# build_post_sync_manifest
# =============================================================================


class TestBuildPostSyncManifest:
    def test_creates_correct_entries_after_sync(self, tmp_path: Path) -> None:
        
        dest = tmp_path / "dst"
        kit_file = dest / "KITS" / "Kit.XML"
        _touch(kit_file, b"<kit/>", mtime=1_700_000_000.0)

        src_scan = ScanResult(
            files={
                "kits/kit.xml": FileEntry(
                    rel_path=Path("KITS/Kit.XML"),
                    size=6,
                    mtime=1_700_000_000.0,
                ),
            },
        )
        plan = SyncPlan(
            files_to_copy=[(tmp_path / "src" / "KITS" / "Kit.XML", kit_file)],
        )
        old_files: dict[str, FileRecord] = {}

        files = build_post_sync_manifest(plan, src_scan, dest, old_files, source_is_sd=True)

        assert "kits/kit.xml" in files
        entry = files["kits/kit.xml"]
        assert entry["sd_size"] == 6
        assert entry["sd_mtime"] == 1_700_000_000.0
        assert entry["local_size"] == kit_file.stat().st_size
        assert entry["local_mtime"] == normalise_mtime(kit_file.stat().st_mtime)

    def test_trashed_files_excluded(self, tmp_path: Path) -> None:
        
        dest = tmp_path / "dst"

        # Source scan has only one file (the surviving one)
        src_scan = ScanResult(
            files={
                "kits/kept.xml": FileEntry(
                    rel_path=Path("KITS/Kept.XML"),
                    size=6,
                    mtime=1_700_000_000.0,
                ),
            },
        )
        # Plan trashed a different file — but it's not in src_scan,
        # so it won't appear in the new manifest
        plan = SyncPlan(
            files_to_delete=[dest / "KITS" / "Trashed.XML"],
        )
        old_files: dict[str, FileRecord] = {
            "kits/kept.xml": {
                "sd_size": 6, "sd_mtime": 1_700_000_000.0,
                "local_size": 6, "local_mtime": 1_700_000_100.0,
            },
            "kits/trashed.xml": {
                "sd_size": 10, "sd_mtime": 1_600_000_000.0,
                "local_size": 10, "local_mtime": 1_600_000_100.0,
            },
        }

        files = build_post_sync_manifest(plan, src_scan, dest, old_files, source_is_sd=True)

        assert "kits/kept.xml" in files
        assert "kits/trashed.xml" not in files

    def test_unchanged_no_prior_entry_stats_dest(self, tmp_path: Path) -> None:
        """Unchanged file with no prior manifest entry gets local stats from stat()."""
        dest = tmp_path / "dst"
        kit_file = dest / "KITS" / "Kit.XML"
        _touch(kit_file, b"<kit/>", mtime=1_700_000_000.0)

        src_scan = ScanResult(
            files={
                "kits/kit.xml": FileEntry(
                    rel_path=Path("KITS/Kit.XML"),
                    size=6,
                    mtime=1_700_000_000.0,
                ),
            },
        )
        # Not in files_to_copy (unchanged) and not in old_files (no prior entry)
        plan = SyncPlan()
        old_files: dict[str, FileRecord] = {}

        files = build_post_sync_manifest(plan, src_scan, dest, old_files, source_is_sd=True)

        assert "kits/kit.xml" in files
        entry = files["kits/kit.xml"]
        assert entry["sd_size"] == 6
        assert entry["sd_mtime"] == 1_700_000_000.0
        assert entry["local_size"] == kit_file.stat().st_size
        assert entry["local_mtime"] == normalise_mtime(kit_file.stat().st_mtime)

    def test_manifest_not_written_on_failure(self, tmp_path: Path) -> None:
        
        """Verify the main() contract: manifest is only written on success.

        We test this at the unit level by confirming execute_plan raises
        SyncError on failure — the caller (main) uses this to skip
        write_manifest.
        """
        dest = tmp_path / "dst"
        bad_src = tmp_path / "src" / "missing.xml"
        bad_dst = dest / "missing.xml"

        plan = SyncPlan(files_to_copy=[(bad_src, bad_dst)])

        with pytest.raises(SyncError):
            execute_plan(plan, dest=dest)


# =============================================================================
# read_manifest / write_manifest
# =============================================================================


class TestReadManifest:
    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        
        files = read_manifest(tmp_path / "nonexistent.json")
        assert files == {}

    def test_corrupt_json_returns_empty(self, tmp_path: Path) -> None:
        
        bad = tmp_path / "manifest.json"
        bad.write_text("{invalid json!!!", encoding="utf-8")

        files = read_manifest(bad)

        assert files == {}

    def test_corrupt_json_prints_warning(self, tmp_path: Path, capsys: object) -> None:
        
        bad = tmp_path / "manifest.json"
        bad.write_text("{broken", encoding="utf-8")

        read_manifest(bad)

        import _pytest.capture

        assert isinstance(capsys, _pytest.capture.CaptureFixture)
        captured = capsys.readouterr()
        assert "Warning" in captured.out
        assert "corrupt" in captured.out.lower()

    def test_valid_manifest_round_trip(self, tmp_path: Path) -> None:
        
        mf = tmp_path / "manifest.json"
        files: dict[str, FileRecord] = {
            "kits/mykit.xml": {
                "sd_size": 1234, "sd_mtime": 1712600000.0,
                "local_size": 1234, "local_mtime": 1712600050.0,
            },
            "samples/kick.wav": {
                "sd_size": 56789, "sd_mtime": 1712600100.0,
                "local_size": 56789, "local_mtime": 1712600150.0,
            },
        }
        ts = "2026-04-09T12:00:00+00:00"

        write_manifest(mf, files=files)
        read_files = read_manifest(mf)

        assert len(read_files) == 2
        assert read_files["kits/mykit.xml"]["sd_size"] == 1234
        assert read_files["kits/mykit.xml"]["local_mtime"] == 1712600050.0
        assert read_files["samples/kick.wav"]["sd_mtime"] == 1712600100.0
        assert read_files["samples/kick.wav"]["local_size"] == 56789

    def test_old_format_entry_treated_as_missing(self, tmp_path: Path) -> None:
        """Manifest entries with only old-format fields (size/mtime) are silently dropped."""
        mf = tmp_path / "manifest.json"
        payload = {
            "last_sync_timestamp": "2026-04-09T12:00:00+00:00",
            "files": {
                "kits/old.xml": {"size": 1234, "mtime": 1712600000.0},
                "kits/new.xml": {
                    "sd_size": 5678, "sd_mtime": 1712600000.0,
                    "local_size": 5678, "local_mtime": 1712600100.0,
                },
            },
        }
        mf.write_text(json.dumps(payload), encoding="utf-8")

        files = read_manifest(mf)

        # Old-format entry dropped, new-format entry loaded
        assert "kits/old.xml" not in files
        assert "kits/new.xml" in files
        assert files["kits/new.xml"]["sd_size"] == 5678


class TestWriteManifest:
    def test_creates_file(self, tmp_path: Path) -> None:
        
        mf_path = tmp_path / "manifest.json"
        write_manifest(mf_path, files={})

        assert mf_path.exists()
        raw = json.loads(mf_path.read_text(encoding="utf-8"))
        assert "files" in raw

    def test_atomic_write_no_temp_file_lingers(self, tmp_path: Path) -> None:
        
        mf_path = tmp_path / "manifest.json"
        write_manifest(mf_path, files={})

        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == []

    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        
        mf_path = tmp_path / "scripts" / "data" / "manifest.json"
        write_manifest(mf_path, files={})

        assert mf_path.parent.is_dir()


# =============================================================================
# Manifest v2 schema and v1 migration
# =============================================================================


class TestManifestV2Format:
    """write_manifest always writes v2 format with version marker and hash."""

    def test_write_includes_version_2(self, tmp_path: Path) -> None:
        mf = tmp_path / "manifest.json"
        write_manifest(mf, files={})

        raw = json.loads(mf.read_text(encoding="utf-8"))
        assert raw["version"] == 2

    def test_write_includes_hash_field_null(self, tmp_path: Path) -> None:
        mf = tmp_path / "manifest.json"
        files: dict[str, FileRecord] = {
            "kits/kit.xml": {
                "sd_size": 100, "sd_mtime": 1.0,
                "local_size": 100, "local_mtime": 2.0,
            },
        }
        write_manifest(mf, files=files)

        raw = json.loads(mf.read_text(encoding="utf-8"))
        assert raw["files"]["kits/kit.xml"]["hash"] is None

    def test_write_includes_hash_field_with_value(self, tmp_path: Path) -> None:
        mf = tmp_path / "manifest.json"
        files: dict[str, FileRecord] = {
            "kits/kit.xml": {
                "sd_size": 100, "sd_mtime": 1.0,
                "local_size": 100, "local_mtime": 2.0,
                "hash": "abcdef1234567890",
            },
        }
        write_manifest(mf, files=files)

        raw = json.loads(mf.read_text(encoding="utf-8"))
        assert raw["files"]["kits/kit.xml"]["hash"] == "abcdef1234567890"


class TestManifestV2RoundTrip:
    """v2 manifests round-trip correctly including hash values."""

    def test_round_trip_with_hashes(self, tmp_path: Path) -> None:
        mf = tmp_path / "manifest.json"
        files: dict[str, FileRecord] = {
            "kits/kit.xml": {
                "sd_size": 100, "sd_mtime": 1.0,
                "local_size": 100, "local_mtime": 2.0,
                "hash": "abc123",
            },
            "samples/kick.wav": {
                "sd_size": 5000, "sd_mtime": 3.0,
                "local_size": 5000, "local_mtime": 4.0,
                "hash": None,
            },
        }

        write_manifest(mf, files=files)
        read_files = read_manifest(mf)

        assert len(read_files) == 2
        assert read_files["kits/kit.xml"]["hash"] == "abc123"
        assert read_files["kits/kit.xml"]["sd_size"] == 100
        assert read_files["samples/kick.wav"]["hash"] is None
        assert read_files["samples/kick.wav"]["sd_size"] == 5000

    def test_round_trip_without_hash_field(self, tmp_path: Path) -> None:
        """FileRecord without explicit hash round-trips with hash=None."""
        mf = tmp_path / "manifest.json"
        files: dict[str, FileRecord] = {
            "kits/kit.xml": {
                "sd_size": 100, "sd_mtime": 1.0,
                "local_size": 100, "local_mtime": 2.0,
            },
        }

        write_manifest(mf, files=files)
        read_files = read_manifest(mf)

        assert read_files["kits/kit.xml"]["hash"] is None


class TestManifestV1Migration:
    """v1 manifests (no version field) are migrated transparently."""

    def test_v1_manifest_reads_with_hash_none(self, tmp_path: Path) -> None:
        mf = tmp_path / "manifest.json"
        payload = {
            "last_sync_timestamp": "2026-01-01T00:00:00+00:00",
            "files": {
                "kits/kit.xml": {
                    "sd_size": 100, "sd_mtime": 1.0,
                    "local_size": 100, "local_mtime": 2.0,
                },
            },
        }
        mf.write_text(json.dumps(payload), encoding="utf-8")

        files = read_manifest(mf)

        assert files["kits/kit.xml"]["sd_size"] == 100
        assert files["kits/kit.xml"]["hash"] is None

    def test_v1_manifest_mixed_entry_quality(self, tmp_path: Path) -> None:
        """v1 manifest with mix of old-format and dual-stat entries."""
        mf = tmp_path / "manifest.json"
        payload = {
            "last_sync_timestamp": "ts",
            "files": {
                "kits/old.xml": {"size": 100, "mtime": 1.0},
                "kits/good.xml": {
                    "sd_size": 200, "sd_mtime": 2.0,
                    "local_size": 200, "local_mtime": 3.0,
                },
                "kits/also-old.xml": {"size": 50, "mtime": 0.5},
            },
        }
        mf.write_text(json.dumps(payload), encoding="utf-8")

        files = read_manifest(mf)

        # Old-format entries dropped, good entry migrated with hash=None
        assert "kits/old.xml" not in files
        assert "kits/also-old.xml" not in files
        assert "kits/good.xml" in files
        assert files["kits/good.xml"]["hash"] is None
        assert files["kits/good.xml"]["sd_size"] == 200

    def test_v2_manifest_preserves_hashes(self, tmp_path: Path) -> None:
        """v2 manifest hash values are preserved on read."""
        mf = tmp_path / "manifest.json"
        payload = {
            "version": 2,
            "last_sync_timestamp": "ts",
            "files": {
                "kits/hashed.xml": {
                    "sd_size": 100, "sd_mtime": 1.0,
                    "local_size": 100, "local_mtime": 2.0,
                    "hash": "deadbeef",
                },
                "kits/unhashed.xml": {
                    "sd_size": 200, "sd_mtime": 3.0,
                    "local_size": 200, "local_mtime": 4.0,
                    "hash": None,
                },
            },
        }
        mf.write_text(json.dumps(payload), encoding="utf-8")

        files = read_manifest(mf)

        assert files["kits/hashed.xml"]["hash"] == "deadbeef"
        assert files["kits/unhashed.xml"]["hash"] is None

    def test_v1_manifest_preserves_hash_field_if_present(self, tmp_path: Path) -> None:
        """v1 manifest (no version field) with a hash field → hash preserved by read_manifest."""
        mf = tmp_path / "manifest.json"
        payload = {
            "last_sync_timestamp": "ts",
            "files": {
                "kits/kit.xml": {
                    "sd_size": 100, "sd_mtime": 1.0,
                    "local_size": 100, "local_mtime": 2.0,
                    "hash": "should-be-ignored",
                },
            },
        }
        mf.write_text(json.dumps(payload), encoding="utf-8")

        files = read_manifest(mf)

        # read_manifest preserves the hash field regardless of manifest version
        assert files["kits/kit.xml"]["hash"] == "should-be-ignored"


# =============================================================================
# build_post_sync_manifest — hash population
# =============================================================================


class TestBuildPostSyncManifestHashing:
    """Hash population in build_post_sync_manifest."""

    def test_copied_files_get_hash(self, tmp_path: Path) -> None:
        """Copied files have hash computed from destination file."""
        dest = tmp_path / "dst"
        kit_file = dest / "KITS" / "Kit.XML"
        content = b"<kit>hashed</kit>"
        _touch(kit_file, content, mtime=1_700_000_000.0)

        import hashlib
        expected_hash = hashlib.sha256(content).hexdigest()

        src_scan = ScanResult(
            files={
                "kits/kit.xml": FileEntry(
                    rel_path=Path("KITS/Kit.XML"),
                    size=len(content),
                    mtime=1_700_000_000.0,
                ),
            },
        )
        plan = SyncPlan(
            files_to_copy=[(tmp_path / "src" / "KITS" / "Kit.XML", kit_file)],
        )
        old_files: dict[str, FileRecord] = {}

        files = build_post_sync_manifest(plan, src_scan, dest, old_files, source_is_sd=True)

        assert files["kits/kit.xml"]["hash"] == expected_hash

    def test_unchanged_files_preserve_hash(self, tmp_path: Path) -> None:
        """Unchanged files preserve their existing hash from old manifest."""
        dest = tmp_path / "dst"
        kit_file = dest / "KITS" / "Kit.XML"
        _touch(kit_file, b"<kit/>", mtime=1_700_000_000.0)

        src_scan = ScanResult(
            files={
                "kits/kit.xml": FileEntry(
                    rel_path=Path("KITS/Kit.XML"),
                    size=6,
                    mtime=1_700_000_000.0,
                ),
            },
        )
        plan = SyncPlan()  # Not in files_to_copy
        old_entry: FileRecord = {
            "sd_size": 6, "sd_mtime": 1_700_000_000.0,
            "local_size": 6, "local_mtime": 1_700_000_100.0,
            "hash": "preserved_hash_value",
        }
        old_files: dict[str, FileRecord] = {"kits/kit.xml": old_entry}

        files = build_post_sync_manifest(plan, src_scan, dest, old_files, source_is_sd=True)

        assert files["kits/kit.xml"]["hash"] == "preserved_hash_value"

    def test_unchanged_v1_entry_preserves_null_hash(self, tmp_path: Path) -> None:
        """Unchanged v1 entry (hash=None) still has hash=None — not re-hashed."""
        dest = tmp_path / "dst"
        kit_file = dest / "KITS" / "Kit.XML"
        _touch(kit_file, b"<kit/>", mtime=1_700_000_000.0)

        src_scan = ScanResult(
            files={
                "kits/kit.xml": FileEntry(
                    rel_path=Path("KITS/Kit.XML"),
                    size=6,
                    mtime=1_700_000_000.0,
                ),
            },
        )
        plan = SyncPlan()
        old_entry: FileRecord = {
            "sd_size": 6, "sd_mtime": 1_700_000_000.0,
            "local_size": 6, "local_mtime": 1_700_000_100.0,
            "hash": None,
        }
        old_files: dict[str, FileRecord] = {"kits/kit.xml": old_entry}

        files = build_post_sync_manifest(plan, src_scan, dest, old_files, source_is_sd=True)

        assert files["kits/kit.xml"]["hash"] is None

    def test_new_file_gets_hash(self, tmp_path: Path) -> None:
        """New file (no prior manifest entry) gets hash computed."""
        dest = tmp_path / "dst"
        kit_file = dest / "KITS" / "New.XML"
        content = b"<new/>"
        _touch(kit_file, content, mtime=1_700_000_000.0)

        import hashlib
        expected_hash = hashlib.sha256(content).hexdigest()

        src_scan = ScanResult(
            files={
                "kits/new.xml": FileEntry(
                    rel_path=Path("KITS/New.XML"),
                    size=len(content),
                    mtime=1_700_000_000.0,
                ),
            },
        )
        # Not in old_files and IS in files_to_copy
        plan = SyncPlan(
            files_to_copy=[(tmp_path / "src" / "KITS" / "New.XML", kit_file)],
        )
        old_files: dict[str, FileRecord] = {}

        files = build_post_sync_manifest(plan, src_scan, dest, old_files, source_is_sd=True)

        assert files["kits/new.xml"]["hash"] == expected_hash

    def test_filtered_sync_preserves_hashes_for_unscanned_types(self, tmp_path: Path) -> None:
        """Filtered sync (e.g. --xml) preserves entries and hashes for unscanned file types."""
        dest = tmp_path / "dst"
        kit_file = dest / "KITS" / "Kit.XML"
        content = b"<kit/>"
        _touch(kit_file, content, mtime=1_700_000_000.0)

        import hashlib
        xml_hash = hashlib.sha256(content).hexdigest()

        src_scan = ScanResult(
            files={
                "kits/kit.xml": FileEntry(
                    rel_path=Path("KITS/Kit.XML"),
                    size=len(content),
                    mtime=1_700_000_000.0,
                ),
            },
        )
        plan = SyncPlan(
            files_to_copy=[(tmp_path / "src" / "KITS" / "Kit.XML", kit_file)],
        )
        # Old manifest has a WAV entry with a hash
        old_files: dict[str, FileRecord] = {
            "samples/kick.wav": {
                "sd_size": 5000, "sd_mtime": 1_600_000_000.0,
                "local_size": 5000, "local_mtime": 1_600_000_100.0,
                "hash": "wav_hash_preserved",
            },
        }

        files = build_post_sync_manifest(
            plan, src_scan, dest, old_files, source_is_sd=True, file_filter="xml",
        )

        # XML file was copied → gets hash
        assert files["kits/kit.xml"]["hash"] == xml_hash
        # WAV file preserved with its hash intact
        assert files["samples/kick.wav"]["hash"] == "wav_hash_preserved"
