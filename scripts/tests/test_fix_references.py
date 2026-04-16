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
    BrokenRefResult,
    MigrationResult,
    PlannedChange,
    compute_migration_map,
    detect_broken_refs,
    preview_and_apply,
)

from deluge_lib.deluge_sdk import SampleRef, find_all_wav_files


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


class TestMain:
    """Tests for the CLI entry point."""

    def test_missing_snapshot_file_exits(self) -> None:
        """Exits with error when snapshot file is missing."""
        from fix_references import main

        with pytest.raises(SystemExit, match="Snapshot file not found"):
            main(["--snapshot", "nonexistent-file.json"])


class TestComputeMigrationMap:
    """Tests for compute_migration_map."""

    @staticmethod
    def _make_snapshot(hashes: dict[str, list[str]]) -> dict[str, object]:
        """Create a minimal snapshot dict for testing."""
        return {
            "date": "2026-04-01",
            "deluge_root": "/fake",
            "hashes": hashes,
        }

    def test_simple_move(self, tmp_path: Path) -> None:
        """File moved from old to new path appears in moved dict."""
        content = b"kick drum audio"
        deluge_root = _make_deluge_tree(tmp_path, {"DRUMS/NewKick.wav": content})
        digest = hashlib.sha256(content).hexdigest()
        before = self._make_snapshot({digest: ["SAMPLES/DRUMS/OldKick.wav"]})

        result = compute_migration_map(before, deluge_root)

        assert result.moved == {
            "SAMPLES/DRUMS/OldKick.wav": "SAMPLES/DRUMS/NewKick.wav",
        }
        assert not result.deleted
        assert not result.added
        assert not result.ambiguous

    def test_deleted_file(self, tmp_path: Path) -> None:
        """Hash in before but not in after is categorised as deleted."""
        deluge_root = tmp_path / "DELUGE"
        (deluge_root / "SAMPLES").mkdir(parents=True)
        digest = "ab" * 32  # fake 64-char hex digest
        before = self._make_snapshot({digest: ["SAMPLES/deleted.wav"]})

        result = compute_migration_map(before, deluge_root)

        assert digest in result.deleted
        assert result.deleted[digest] == ["SAMPLES/deleted.wav"]
        assert not result.moved

    def test_added_file(self, tmp_path: Path) -> None:
        """Hash in after but not in before is categorised as added."""
        content = b"new sample"
        deluge_root = _make_deluge_tree(tmp_path, {"new.wav": content})
        before = self._make_snapshot({})

        result = compute_migration_map(before, deluge_root)

        digest = hashlib.sha256(content).hexdigest()
        assert digest in result.added
        assert result.added[digest] == ["SAMPLES/new.wav"]
        assert not result.moved

    def test_ambiguous_multiple_before_paths(self, tmp_path: Path) -> None:
        """Hash with multiple before paths is categorised as ambiguous."""
        content = b"shared content"
        deluge_root = _make_deluge_tree(tmp_path, {"current.wav": content})
        digest = hashlib.sha256(content).hexdigest()
        before = self._make_snapshot({digest: ["SAMPLES/a.wav", "SAMPLES/b.wav"]})

        result = compute_migration_map(before, deluge_root)

        assert digest in result.ambiguous
        before_paths, after_paths = result.ambiguous[digest]
        assert set(before_paths) == {"SAMPLES/a.wav", "SAMPLES/b.wav"}
        assert after_paths == ["SAMPLES/current.wav"]
        assert not result.moved

    def test_ambiguous_multiple_after_paths(self, tmp_path: Path) -> None:
        """Hash with multiple after paths is categorised as ambiguous."""
        content = b"duplicated content"
        deluge_root = _make_deluge_tree(tmp_path, {
            "copy1.wav": content,
            "copy2.wav": content,
        })
        digest = hashlib.sha256(content).hexdigest()
        before = self._make_snapshot({digest: ["SAMPLES/original.wav"]})

        result = compute_migration_map(before, deluge_root)

        assert digest in result.ambiguous
        before_paths, after_paths = result.ambiguous[digest]
        assert before_paths == ["SAMPLES/original.wav"]
        assert set(after_paths) == {"SAMPLES/copy1.wav", "SAMPLES/copy2.wav"}
        assert not result.moved

    def test_unchanged_file_not_in_results(self, tmp_path: Path) -> None:
        """Same hash and same path produces no entries in any category."""
        content = b"unchanged audio"
        deluge_root = _make_deluge_tree(tmp_path, {"same.wav": content})
        digest = hashlib.sha256(content).hexdigest()
        before = self._make_snapshot({digest: ["SAMPLES/same.wav"]})

        result = compute_migration_map(before, deluge_root)

        assert not result.moved
        assert not result.deleted
        assert not result.added
        assert not result.ambiguous

    def test_empty_snapshot_empty_filesystem(self, tmp_path: Path) -> None:
        """Empty before and after states produce an empty result."""
        deluge_root = tmp_path / "DELUGE"
        (deluge_root / "SAMPLES").mkdir(parents=True)
        before = self._make_snapshot({})

        result = compute_migration_map(before, deluge_root)

        assert result == MigrationResult()

    def test_empty_snapshot_with_current_files(self, tmp_path: Path) -> None:
        """Empty before snapshot with files on disk reports all as added."""
        content = b"brand new"
        deluge_root = _make_deluge_tree(tmp_path, {"new.wav": content})
        before = self._make_snapshot({})

        result = compute_migration_map(before, deluge_root)

        assert not result.moved
        assert not result.deleted
        assert len(result.added) == 1

    def test_multiple_independent_moves(self, tmp_path: Path) -> None:
        """Multiple files each moved independently all appear in moved dict."""
        content_a = b"audio a"
        content_b = b"audio b"
        deluge_root = _make_deluge_tree(tmp_path, {
            "new_a.wav": content_a,
            "new_b.wav": content_b,
        })
        hash_a = hashlib.sha256(content_a).hexdigest()
        hash_b = hashlib.sha256(content_b).hexdigest()
        before = self._make_snapshot({
            hash_a: ["SAMPLES/old_a.wav"],
            hash_b: ["SAMPLES/old_b.wav"],
        })

        result = compute_migration_map(before, deluge_root)

        assert result.moved == {
            "SAMPLES/old_a.wav": "SAMPLES/new_a.wav",
            "SAMPLES/old_b.wav": "SAMPLES/new_b.wav",
        }
        assert not result.deleted
        assert not result.added
        assert not result.ambiguous

    def test_mixed_categories(self, tmp_path: Path) -> None:
        """A single run can produce moved, deleted, added, and ambiguous entries."""
        moved_content = b"moved file"
        added_content = b"added file"
        ambig_content = b"ambig file"

        deluge_root = _make_deluge_tree(tmp_path, {
            "new_location.wav": moved_content,
            "brand_new.wav": added_content,
            "dup1.wav": ambig_content,
            "dup2.wav": ambig_content,
        })

        moved_hash = hashlib.sha256(moved_content).hexdigest()
        deleted_hash = "cc" * 32
        ambig_hash = hashlib.sha256(ambig_content).hexdigest()

        before = self._make_snapshot({
            moved_hash: ["SAMPLES/old_location.wav"],
            deleted_hash: ["SAMPLES/gone.wav"],
            ambig_hash: ["SAMPLES/original.wav"],
        })

        result = compute_migration_map(before, deluge_root)

        assert "SAMPLES/old_location.wav" in result.moved
        assert deleted_hash in result.deleted
        assert len(result.added) == 1  # added_content hash
        assert ambig_hash in result.ambiguous


def _write_minimal_kit_xml(path: Path, sample_paths: list[str]) -> None:
    """Write a minimal kit XML with fileName attributes for each sample path."""
    sounds = ""
    for sp in sample_paths:
        sounds += f"""
		<sound name="S">
			<osc1 type="sample" fileName="{sp}">
			</osc1>
		</sound>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n<kit>\n\t<soundSources>{sounds}\n\t</soundSources>\n</kit>\n',
        encoding="utf-8",
    )


class TestDetectBrokenRefs:
    """Tests for detect_broken_refs."""

    def test_ref_in_migration_map_is_planned_change(self, tmp_path: Path) -> None:
        """A reference whose path is in moved dict appears as a planned change."""
        deluge_root = tmp_path / "DELUGE"
        _write_minimal_kit_xml(
            deluge_root / "KITS" / "KIT001.XML",
            ["SAMPLES/DRUMS/OldKick.wav"],
        )
        migration = MigrationResult(
            moved={"SAMPLES/DRUMS/OldKick.wav": "SAMPLES/DRUMS/NewKick.wav"},
        )

        result = detect_broken_refs(migration, deluge_root)

        assert len(result.changes) == 1
        assert result.changes[0].old_path == "SAMPLES/DRUMS/OldKick.wav"
        assert result.changes[0].new_path == "SAMPLES/DRUMS/NewKick.wav"
        assert not result.errors
        assert not result.warnings

    def test_ref_in_deleted_set_is_error(self, tmp_path: Path) -> None:
        """A reference whose path is in the deleted set appears as an error."""
        deluge_root = tmp_path / "DELUGE"
        _write_minimal_kit_xml(
            deluge_root / "KITS" / "KIT001.XML",
            ["SAMPLES/DRUMS/Gone.wav"],
        )
        migration = MigrationResult(
            deleted={"somehash": ["SAMPLES/DRUMS/Gone.wav"]},
        )

        result = detect_broken_refs(migration, deluge_root)

        assert not result.changes
        assert len(result.errors) == 1
        assert result.errors[0].deleted_path == "SAMPLES/DRUMS/Gone.wav"
        assert not result.warnings

    def test_ref_in_ambiguous_set_is_warning(self, tmp_path: Path) -> None:
        """A reference whose path is in the ambiguous before-paths appears as a warning."""
        deluge_root = tmp_path / "DELUGE"
        _write_minimal_kit_xml(
            deluge_root / "KITS" / "KIT001.XML",
            ["SAMPLES/DRUMS/Ambig.wav"],
        )
        migration = MigrationResult(
            ambiguous={
                "somehash": (
                    ["SAMPLES/DRUMS/Ambig.wav", "SAMPLES/DRUMS/Other.wav"],
                    ["SAMPLES/DRUMS/New1.wav", "SAMPLES/DRUMS/New2.wav"],
                ),
            },
        )

        result = detect_broken_refs(migration, deluge_root)

        assert not result.changes
        assert not result.errors
        assert len(result.warnings) == 1
        assert result.warnings[0].ambiguous_path == "SAMPLES/DRUMS/Ambig.wav"

    def test_valid_ref_not_in_results(self, tmp_path: Path) -> None:
        """A reference not in any migration category does not appear in results."""
        deluge_root = tmp_path / "DELUGE"
        _write_minimal_kit_xml(
            deluge_root / "KITS" / "KIT001.XML",
            ["SAMPLES/DRUMS/StillHere.wav"],
        )
        migration = MigrationResult()

        result = detect_broken_refs(migration, deluge_root)

        assert not result.changes
        assert not result.errors
        assert not result.warnings

    def test_multiple_refs_across_multiple_xmls(self, tmp_path: Path) -> None:
        """References from multiple XML files are all classified correctly."""
        deluge_root = tmp_path / "DELUGE"
        _write_minimal_kit_xml(
            deluge_root / "KITS" / "KIT001.XML",
            ["SAMPLES/DRUMS/Moved.wav"],
        )
        _write_minimal_kit_xml(
            deluge_root / "KITS" / "KIT002.XML",
            ["SAMPLES/DRUMS/Deleted.wav", "SAMPLES/DRUMS/OK.wav"],
        )
        migration = MigrationResult(
            moved={"SAMPLES/DRUMS/Moved.wav": "SAMPLES/DRUMS/NewMoved.wav"},
            deleted={"delhash": ["SAMPLES/DRUMS/Deleted.wav"]},
        )

        result = detect_broken_refs(migration, deluge_root)

        assert len(result.changes) == 1
        assert result.changes[0].old_path == "SAMPLES/DRUMS/Moved.wav"
        assert len(result.errors) == 1
        assert result.errors[0].deleted_path == "SAMPLES/DRUMS/Deleted.wav"
        assert not result.warnings

    def test_no_broken_refs(self, tmp_path: Path) -> None:
        """When all references are valid, result is empty."""
        deluge_root = tmp_path / "DELUGE"
        _write_minimal_kit_xml(
            deluge_root / "KITS" / "KIT001.XML",
            ["SAMPLES/DRUMS/Fine.wav", "SAMPLES/DRUMS/AlsoFine.wav"],
        )
        migration = MigrationResult()

        result = detect_broken_refs(migration, deluge_root)

        assert result == BrokenRefResult()

    def test_ref_carries_sample_ref_metadata(self, tmp_path: Path) -> None:
        """Planned change carries the full SampleRef with correct metadata."""
        deluge_root = tmp_path / "DELUGE"
        _write_minimal_kit_xml(
            deluge_root / "KITS" / "MyKit.XML",
            ["SAMPLES/OldPath.wav"],
        )
        migration = MigrationResult(
            moved={"SAMPLES/OldPath.wav": "SAMPLES/NewPath.wav"},
        )

        result = detect_broken_refs(migration, deluge_root)

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
            deleted={"hash1": ["SAMPLES/A.wav", "SAMPLES/B.wav"]},
        )

        result = detect_broken_refs(migration, deluge_root)

        assert len(result.errors) == 2
        deleted_paths = {e.deleted_path for e in result.errors}
        assert deleted_paths == {"SAMPLES/A.wav", "SAMPLES/B.wav"}


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


class TestPreviewAndApply:
    """Tests for the preview_and_apply function."""

    def test_empty_result_nothing_to_do(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Empty BrokenRefResult prints 'Nothing to do' and returns."""
        preview_and_apply(BrokenRefResult(), tmp_path)

        captured = capsys.readouterr()
        assert "Nothing to do" in captured.out

    def test_changes_grouped_by_xml_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Preview output groups changes by XML file."""
        result = BrokenRefResult(
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
        assert 'KIT001.XML: "SAMPLES/a.wav" → "SAMPLES/b.wav"' in captured.out
        assert 'KIT002.XML: "SAMPLES/c.wav" → "SAMPLES/d.wav"' in captured.out

    def test_duplicate_refs_show_count(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Multiple refs with the same old→new in one file show '× N refs'."""
        ref = _make_ref("KITS/KIT001.XML", "SAMPLES/a.wav")
        result = BrokenRefResult(
            changes=[
                PlannedChange(ref=ref, old_path="SAMPLES/a.wav", new_path="SAMPLES/b.wav"),
                PlannedChange(ref=ref, old_path="SAMPLES/a.wav", new_path="SAMPLES/b.wav"),
            ],
        )

        with patch("fix_references.confirm_apply", return_value=False):
            preview_and_apply(result, tmp_path)

        captured = capsys.readouterr()
        assert "× 2 refs" in captured.out

    def test_error_section_displayed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Errors are displayed under the 'ERRORS' section header."""
        result = BrokenRefResult(
            errors=[
                BrokenRefError(
                    ref=_make_ref("KITS/KIT001.XML", "SAMPLES/gone.wav"),
                    deleted_path="SAMPLES/gone.wav",
                ),
            ],
        )

        preview_and_apply(result, tmp_path)

        captured = capsys.readouterr()
        assert "ERRORS — Requires Manual Resolution" in captured.out
        assert "SAMPLES/gone.wav" in captured.out
        assert "sample deleted" in captured.out

    def test_warning_section_displayed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Warnings are displayed under the 'WARNINGS' section header."""
        result = BrokenRefResult(
            warnings=[
                AmbiguousRefWarning(
                    ref=_make_ref("KITS/KIT001.XML", "SAMPLES/ambig.wav"),
                    ambiguous_path="SAMPLES/ambig.wav",
                ),
            ],
        )

        preview_and_apply(result, tmp_path)

        captured = capsys.readouterr()
        assert "WARNINGS — Ambiguous Mappings" in captured.out
        assert "SAMPLES/ambig.wav" in captured.out
        assert "multiple files share this hash" in captured.out

    def test_summary_line_counts(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Summary line shows correct counts for changes, files, errors, warnings."""
        result = BrokenRefResult(
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
        assert "2 changes across 2 files. 1 errors, 1 warnings." in captured.out

    def test_error_warning_recommends_resolution(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """When errors exist, a warning recommending resolution is shown."""
        result = BrokenRefResult(
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
        result = BrokenRefResult(
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
        result = BrokenRefResult(
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
        result = BrokenRefResult(
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
        result = BrokenRefResult(
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

    def test_only_errors_no_apply_prompt(self, tmp_path: Path) -> None:
        """When there are only errors (no changes), no apply prompt is shown."""
        result = BrokenRefResult(
            errors=[
                BrokenRefError(
                    ref=_make_ref("KITS/KIT001.XML", "SAMPLES/gone.wav"),
                    deleted_path="SAMPLES/gone.wav",
                ),
            ],
        )

        with patch("fix_references.confirm_apply") as mock_confirm:
            has_errors = preview_and_apply(result, tmp_path)

        mock_confirm.assert_not_called()
        assert has_errors is True

    def test_returns_false_when_nothing_to_do(self, tmp_path: Path) -> None:
        """Returns False when no changes, errors, or warnings exist."""
        assert preview_and_apply(BrokenRefResult(), tmp_path) is False

    def test_returns_false_when_changes_only(self, tmp_path: Path) -> None:
        """Returns False when there are fixable changes but no errors."""
        deluge_root = tmp_path / "DELUGE"
        result = BrokenRefResult(
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
            has_errors = preview_and_apply(result, deluge_root)

        assert has_errors is False

    def test_returns_true_when_errors_and_changes(self, tmp_path: Path) -> None:
        """Returns True when errors exist even if fixable changes also exist."""
        deluge_root = tmp_path / "DELUGE"
        result = BrokenRefResult(
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
            has_errors = preview_and_apply(result, deluge_root)

        assert has_errors is True


class TestMainExitCodes:
    """Tests for CLI exit codes via main()."""

    def test_fix_exits_0_no_errors(self, tmp_path: Path) -> None:
        """Exits 0 when no broken references found."""
        from fix_references import main

        # Create a DELUGE root with one sample, snapshot matches current state
        content = b"kick_audio"
        deluge_root = _make_deluge_tree(tmp_path, {"kick.wav": content})
        digest = hashlib.sha256(content).hexdigest()
        snap_data = {
            "date": "2026-04-01",
            "deluge_root": str(deluge_root),
            "hashes": {digest: ["SAMPLES/kick.wav"]},
        }
        snap_file = tmp_path / "snap.json"
        snap_file.write_text(json.dumps(snap_data), encoding="utf-8")

        with patch("fix_references.get_deluge_root", return_value=deluge_root):
            main(["--snapshot", str(snap_file)])  # Should not raise

    def test_fix_exits_1_when_errors(self, tmp_path: Path) -> None:
        """Exits 1 when deleted references are detected."""
        from fix_references import main

        deluge_root = tmp_path / "DELUGE"
        (deluge_root / "SAMPLES").mkdir(parents=True)
        # Kit referencing a sample that no longer exists
        _write_minimal_kit_xml(
            deluge_root / "KITS" / "KIT001.XML",
            ["SAMPLES/gone.wav"],
        )
        # Snapshot says file existed with a fake hash
        snap_data = {
            "date": "2026-04-01",
            "deluge_root": str(deluge_root),
            "hashes": {"ab" * 32: ["SAMPLES/gone.wav"]},
        }
        snap_file = tmp_path / "snap.json"
        snap_file.write_text(json.dumps(snap_data), encoding="utf-8")

        with patch("fix_references.get_deluge_root", return_value=deluge_root):
            with pytest.raises(SystemExit) as exc_info:
                main(["--snapshot", str(snap_file)])
            assert exc_info.value.code == 1

    def test_fix_apply_skips_prompt(self, tmp_path: Path) -> None:
        """--apply skips the confirmation prompt and applies changes."""
        from fix_references import main

        content = b"kick_audio"
        deluge_root = _make_deluge_tree(tmp_path, {"NewKick.wav": content})
        digest = hashlib.sha256(content).hexdigest()
        # Kit references old path
        _write_minimal_kit_xml(
            deluge_root / "KITS" / "KIT001.XML",
            ["SAMPLES/OldKick.wav"],
        )
        snap_data = {
            "date": "2026-04-01",
            "deluge_root": str(deluge_root),
            "hashes": {digest: ["SAMPLES/OldKick.wav"]},
        }
        snap_file = tmp_path / "snap.json"
        snap_file.write_text(json.dumps(snap_data), encoding="utf-8")

        with patch("fix_references.get_deluge_root", return_value=deluge_root), patch(
            "fix_references.confirm_apply"
        ) as mock_confirm:
            main(["--snapshot", str(snap_file), "--apply"])

        mock_confirm.assert_not_called()
