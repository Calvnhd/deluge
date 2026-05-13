# Deluge CLI v0.1
"""Tests for deluge_lib.syncing — shared sync primitives."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import _touch
from deluge_lib.scanning import FileEntry, ScanResult, normalise_mtime
from deluge_lib.syncing import (
    SyncError,
    SyncPlan,
    SyncResult,
    _mtime_matches,
    append_sync_log,
    compute_sync,
    execute_plan,
    print_plan,
)


# =============================================================================
# _mtime_matches
# =============================================================================


class TestMtimeMatches:
    def test_identical_times(self) -> None:
        # TODO-v0.1-REVIEW
        assert _mtime_matches(1000.0, 1000.0) is True

    def test_within_fat32_tolerance(self) -> None:
        # TODO-v0.1-REVIEW
        assert _mtime_matches(1000.0, 1001.5) is True

    def test_exactly_at_tolerance(self) -> None:
        # TODO-v0.1-REVIEW
        assert _mtime_matches(1000.0, 1002.0) is True

    def test_beyond_tolerance(self) -> None:
        # TODO-v0.1-REVIEW
        assert _mtime_matches(1000.0, 1005.0) is False

    def test_dst_offset_not_matched(self) -> None:
        # DST shift (3600s) should NOT be treated as matching
        # TODO-v0.1-REVIEW
        assert _mtime_matches(1000.0, 4600.0) is False


# =============================================================================
# compute_sync — comparison logic
# =============================================================================


class TestComputeSyncNewFile:
    """New file on source not in dest → files_to_copy."""

    def test_new_file_added_to_copy(self, tmp_path: Path) -> None:
        # TODO-v0.1-REVIEW
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        _touch(src / "KITS" / "NewKit.XML", b"<kit/>")
        dst.mkdir()

        plan, _ = compute_sync(src, dst)

        assert len(plan.files_to_copy) == 1
        assert plan.files_to_copy[0][1] == dst / "KITS" / "NewKit.XML"


class TestComputeSyncDeletedFile:
    """File in dest not on source → files_to_delete."""

    def test_extra_dest_file_marked_for_delete(self, tmp_path: Path) -> None:
        # TODO-v0.1-REVIEW
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        _touch(dst / "KITS" / "OldKit.XML", b"<kit/>")

        plan, _ = compute_sync(src, dst)

        assert len(plan.files_to_delete) == 1
        assert plan.files_to_delete[0] == dst / "KITS" / "OldKit.XML"


class TestComputeSyncUnchanged:
    """Same file (same size, same mtime) → unchanged."""

    def test_identical_files_unchanged(self, tmp_path: Path) -> None:
        # TODO-v0.1-REVIEW
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        mtime = 1_700_000_000.0
        _touch(src / "KITS" / "Kit.XML", b"<kit/>", mtime=mtime)
        _touch(dst / "KITS" / "Kit.XML", b"<kit/>", mtime=mtime)

        plan, _ = compute_sync(src, dst)

        assert plan.files_to_copy == []
        assert plan.files_to_delete == []
        assert plan.files_unchanged == 1

    def test_mtime_within_fat32_tolerance_unchanged(self, tmp_path: Path) -> None:
        # TODO-v0.1-REVIEW
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        _touch(src / "KITS" / "Kit.XML", b"<kit/>", mtime=1_700_000_000.0)
        _touch(dst / "KITS" / "Kit.XML", b"<kit/>", mtime=1_700_000_001.5)

        plan, _ = compute_sync(src, dst)

        assert plan.files_to_copy == []
        assert plan.files_unchanged == 1


class TestComputeSyncOverwrite:
    """Different size or mtime beyond tolerance → files_to_copy."""

    def test_different_size_triggers_copy(self, tmp_path: Path) -> None:
        # TODO-v0.1-REVIEW
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        mtime = 1_700_000_000.0
        _touch(src / "KITS" / "Kit.XML", b"<kit>new</kit>", mtime=mtime)
        _touch(dst / "KITS" / "Kit.XML", b"<kit/>", mtime=mtime)

        plan, _ = compute_sync(src, dst)

        assert len(plan.files_to_copy) == 1

    def test_same_size_different_mtime_triggers_copy(self, tmp_path: Path) -> None:
        # TODO-v0.1-REVIEW
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        content = b"<kit/>"
        _touch(src / "KITS" / "Kit.XML", content, mtime=1_700_000_000.0)
        _touch(dst / "KITS" / "Kit.XML", content, mtime=1_700_000_010.0)

        plan, _ = compute_sync(src, dst)

        assert len(plan.files_to_copy) == 1


class TestComputeSyncCaseVariant:
    """Case-only difference with same size → unchanged."""

    def test_case_variant_treated_as_unchanged(self, tmp_path: Path) -> None:
        # TODO-v0.1-REVIEW
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        mtime = 1_700_000_000.0
        _touch(src / "KITS" / "Kit001.XML", b"<kit/>", mtime=mtime)
        _touch(dst / "KITS" / "KIT001.XML", b"<kit/>", mtime=mtime)

        plan, _ = compute_sync(src, dst)

        assert plan.files_to_copy == []
        assert plan.files_unchanged == 1


class TestComputeSyncManifest:
    """Manifest-aware comparison."""

    def test_manifest_entry_used_when_available(self, tmp_path: Path) -> None:
        # TODO-v0.1-REVIEW
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        content = b"<kit/>"
        src_mtime = 1_700_000_000.0
        _touch(src / "KITS" / "Kit.XML", content, mtime=src_mtime)
        # Dest has wrong mtime (simulates git clone destroying mtime)
        dst_mtime = 1_600_000_000.0
        _touch(dst / "KITS" / "Kit.XML", content, mtime=dst_mtime)

        # Manifest records both SD and local stats from last sync
        manifest = {"kits/kit.xml": {
            "sd_size": len(content), "sd_mtime": src_mtime,
            "local_size": len(content), "local_mtime": dst_mtime,
        }}

        plan, _ = compute_sync(src, dst, manifest=manifest)

        # SD stats match manifest sd_* AND local stats match manifest local_* → unchanged
        assert plan.files_to_copy == []
        assert plan.files_unchanged == 1

    def test_fallback_to_dest_stat_when_no_manifest_entry(self, tmp_path: Path) -> None:
        # TODO-v0.1-REVIEW
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        content = b"<kit/>"
        mtime = 1_700_000_000.0
        _touch(src / "KITS" / "Kit.XML", content, mtime=mtime)
        _touch(dst / "KITS" / "Kit.XML", content, mtime=mtime)

        # Manifest exists but has no entry for this file
        manifest = {"other/file.xml": {
            "sd_size": 10, "sd_mtime": 1.0,
            "local_size": 10, "local_mtime": 1.0,
        }}

        plan, _ = compute_sync(src, dst, manifest=manifest)

        assert plan.files_to_copy == []
        assert plan.files_unchanged == 1

    def test_local_size_change_detected(self, tmp_path: Path) -> None:
        """SD unchanged but local file has different size → copy."""
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        content = b"x" * 100
        sd_mtime = normalise_mtime(1_700_000_000.0)
        local_mtime = normalise_mtime(1_690_000_000.0)
        _touch(src / "KITS" / "Kit.XML", content, mtime=sd_mtime)
        # Dest file has 120 bytes — differs from manifest local_size of 100
        _touch(dst / "KITS" / "Kit.XML", b"x" * 120, mtime=local_mtime)

        manifest = {"kits/kit.xml": {
            "sd_size": len(content), "sd_mtime": sd_mtime,
            "local_size": len(content), "local_mtime": local_mtime,
        }}

        plan, _ = compute_sync(src, dst, manifest=manifest)

        assert len(plan.files_to_copy) == 1

    def test_local_mtime_change_detected(self, tmp_path: Path) -> None:
        """SD unchanged but local file has different mtime (same size) → copy."""
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        content = b"x" * 100
        sd_mtime = normalise_mtime(1_700_000_000.0)
        local_mtime = normalise_mtime(1_690_000_000.0)
        changed_mtime = normalise_mtime(1_680_000_000.0)
        _touch(src / "KITS" / "Kit.XML", content, mtime=sd_mtime)
        # Dest file has same size but different mtime from manifest local_mtime
        _touch(dst / "KITS" / "Kit.XML", content, mtime=changed_mtime)

        manifest = {"kits/kit.xml": {
            "sd_size": len(content), "sd_mtime": sd_mtime,
            "local_size": len(content), "local_mtime": local_mtime,
        }}

        plan, _ = compute_sync(src, dst, manifest=manifest)

        assert len(plan.files_to_copy) == 1

    def test_sd_change_detected_even_if_local_matches(self, tmp_path: Path) -> None:
        """SD stats differ from manifest sd_* → copy, even if local matches local_*."""
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        old_content = b"x" * 100
        new_content = b"x" * 150  # SD file has changed size
        sd_mtime = normalise_mtime(1_700_000_000.0)
        local_mtime = normalise_mtime(1_690_000_000.0)
        _touch(src / "KITS" / "Kit.XML", new_content, mtime=sd_mtime)
        # Dest matches manifest local_* exactly
        _touch(dst / "KITS" / "Kit.XML", old_content, mtime=local_mtime)

        manifest = {"kits/kit.xml": {
            "sd_size": len(old_content), "sd_mtime": sd_mtime,
            "local_size": len(old_content), "local_mtime": local_mtime,
        }}

        plan, _ = compute_sync(src, dst, manifest=manifest)

        assert len(plan.files_to_copy) == 1

    def test_both_changed_triggers_copy(self, tmp_path: Path) -> None:
        """SD changed AND local changed → copy."""
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        sd_mtime = normalise_mtime(1_700_000_000.0)
        local_mtime = normalise_mtime(1_690_000_000.0)
        changed_mtime = normalise_mtime(1_680_000_000.0)
        # SD file differs from manifest sd_size
        _touch(src / "KITS" / "Kit.XML", b"x" * 200, mtime=sd_mtime)
        # Dest file differs from manifest local_mtime
        _touch(dst / "KITS" / "Kit.XML", b"x" * 100, mtime=changed_mtime)

        manifest = {"kits/kit.xml": {
            "sd_size": 100, "sd_mtime": sd_mtime,
            "local_size": 100, "local_mtime": local_mtime,
        }}

        plan, _ = compute_sync(src, dst, manifest=manifest)

        assert len(plan.files_to_copy) == 1

    def test_null_timestamp_idempotent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Null FAT32 timestamp (-11644473600.0) does not cause false positive."""
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        content = b"<preset/>"
        null_mtime = normalise_mtime(-11644473600.0)  # null FAT32 timestamp
        ntfs_copy_mtime = normalise_mtime(1_777_722_966.0)  # NTFS copy time

        # Create placeholder files (actual mtimes don't matter — we mock
        # scan_tree because negative mtimes can't be set on Windows NTFS).
        _touch(src / "SYNTHS" / "Preset.XML", content)
        _touch(dst / "SYNTHS" / "Preset.XML", content)

        src_scan = ScanResult(files={"synths/preset.xml": FileEntry(
            rel_path=Path("SYNTHS/Preset.XML"), size=len(content), mtime=null_mtime,
        )})
        dst_scan = ScanResult(files={"synths/preset.xml": FileEntry(
            rel_path=Path("SYNTHS/Preset.XML"), size=len(content), mtime=ntfs_copy_mtime,
        )})
        calls = iter([src_scan, dst_scan])
        monkeypatch.setattr(
            "deluge_lib.syncing.scan_tree", lambda *a, **kw: next(calls),
        )

        # Manifest records the null SD mtime and the NTFS copy mtime
        manifest = {"synths/preset.xml": {
            "sd_size": len(content), "sd_mtime": null_mtime,
            "local_size": len(content), "local_mtime": ntfs_copy_mtime,
        }}

        plan, _ = compute_sync(src, dst, manifest=manifest)

        assert plan.files_to_copy == []
        assert plan.files_unchanged == 1

    def test_source_is_sd_false_swaps_manifest_keys(self, tmp_path: Path) -> None:
        """When source_is_sd=False, source is compared against local_* fields."""
        src = tmp_path / "src"  # local side
        dst = tmp_path / "dst"  # SD side
        content = b"<kit/>"
        local_mtime = 1_700_000_000.0
        sd_mtime = 1_600_000_000.0
        _touch(src / "KITS" / "Kit.XML", content, mtime=local_mtime)
        _touch(dst / "KITS" / "Kit.XML", content, mtime=sd_mtime)

        # Manifest records the correct stats from last sync
        manifest = {"kits/kit.xml": {
            "sd_size": len(content), "sd_mtime": sd_mtime,
            "local_size": len(content), "local_mtime": local_mtime,
        }}

        # source_is_sd=False: source is local, dest is SD
        plan, _ = compute_sync(src, dst, manifest=manifest, source_is_sd=False)

        # local stats match manifest local_* AND SD stats match manifest sd_* → unchanged
        assert plan.files_to_copy == []
        assert plan.files_unchanged == 1


# =============================================================================
# execute_plan
# =============================================================================


class TestExecutePlanCopy:
    def test_copies_files_correctly(self, tmp_path: Path) -> None:
        # TODO-v0.1-REVIEW
        src_file = tmp_path / "src" / "KITS" / "Kit.XML"
        dst_file = tmp_path / "dst" / "KITS" / "Kit.XML"
        _touch(src_file, b"<kit>content</kit>")

        plan = SyncPlan(files_to_copy=[(src_file, dst_file)])

        result = execute_plan(plan, dest=tmp_path / "dst")

        assert result.copied == 1
        assert dst_file.read_bytes() == b"<kit>content</kit>"


class TestExecutePlanTrash:
    def test_trashes_files_to_trash_directory(self, tmp_path: Path) -> None:
        # TODO-v0.1-REVIEW
        dest = tmp_path / "dst"
        target = dest / "KITS" / "OldKit.XML"
        _touch(target, b"<kit/>")

        plan = SyncPlan(files_to_delete=[target])

        result = execute_plan(plan, dest=dest)

        assert result.trashed == 1
        assert not target.exists()
        # File should be in .trash subdirectory
        trash_files = list((dest / ".trash").rglob("OldKit.XML"))
        assert len(trash_files) == 1
        assert trash_files[0].read_bytes() == b"<kit/>"


class TestExecutePlanFailure:
    def test_stops_on_copy_failure_and_raises_sync_error(self, tmp_path: Path) -> None:
        # TODO-v0.1-REVIEW
        dest = tmp_path / "dst"
        # First file is valid
        good_src = tmp_path / "src" / "good.xml"
        good_dst = dest / "good.xml"
        _touch(good_src, b"<ok/>")
        # Second file: source doesn't exist → copy will fail
        bad_src = tmp_path / "src" / "missing.xml"
        bad_dst = dest / "missing.xml"

        plan = SyncPlan(
            files_to_copy=[(good_src, good_dst), (bad_src, bad_dst)],
        )

        with pytest.raises(SyncError) as exc_info:
            execute_plan(plan, dest=dest)

        assert exc_info.value.copied == 1
        assert exc_info.value.file is not None
        assert exc_info.value.remaining == 0  # 2 total, 1 copied, 1 failed = 0 remaining


# =============================================================================
# append_sync_log
# =============================================================================


class TestAppendSyncLog:
    def test_creates_entry_on_success(self, tmp_path: Path) -> None:
        # TODO-v0.1-REVIEW
        log_path = tmp_path / "data" / "sync.log"
        result = SyncResult(
            copied=5,
            trashed=3,
            unchanged=10,
        )

        append_sync_log(result, elapsed_seconds=65.0, log_path=log_path)

        content = log_path.read_text(encoding="utf-8")
        lines = content.strip().splitlines()
        assert len(lines) == 1
        line = lines[0]
        assert "SUCCESS" in line
        assert "copied=5" in line
        assert "trashed=3" in line
        assert "unchanged=10" in line
        assert "elapsed=1m 5s" in line
        assert "error=" not in line

    def test_creates_entry_on_failure_with_error(self, tmp_path: Path) -> None:
        # TODO-v0.1-REVIEW
        log_path = tmp_path / "data" / "sync.log"
        result = SyncResult(
            copied=2,
        )

        append_sync_log(
            result,
            elapsed_seconds=12.0,
            error="Permission denied: /mnt/sd/file.wav",
            log_path=log_path,
        )

        content = log_path.read_text(encoding="utf-8")
        lines = content.strip().splitlines()
        assert len(lines) == 1
        line = lines[0]
        assert "FAILED" in line
        assert "copied=2" in line
        assert 'error="Permission denied: /mnt/sd/file.wav"' in line

    def test_log_file_created_in_data_directory(self, tmp_path: Path) -> None:
        # TODO-v0.1-REVIEW
        log_path = tmp_path / "data" / "sync.log"
        result = SyncResult()

        append_sync_log(result, elapsed_seconds=1.0, log_path=log_path)

        assert log_path.exists()
        assert log_path.parent.name == "data"

    def test_multiple_entries_appended(self, tmp_path: Path) -> None:
        # TODO-v0.1-REVIEW
        log_path = tmp_path / "data" / "sync.log"
        r1 = SyncResult(copied=1)
        r2 = SyncResult(copied=2)

        append_sync_log(r1, elapsed_seconds=1.0, log_path=log_path)
        append_sync_log(r2, elapsed_seconds=2.0, log_path=log_path)

        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        assert "copied=1" in lines[0]
        assert "copied=2" in lines[1]
        assert "---" not in log_path.read_text(encoding="utf-8")


# =============================================================================
# execute_plan — delete mode
# =============================================================================


class TestExecutePlanDeleteMode:
    def test_hard_delete_removes_files(self, tmp_path: Path) -> None:
        # TODO-v0.1-REVIEW
        dest = tmp_path / "dst"
        target = dest / "KITS" / "OldKit.XML"
        _touch(target, b"<kit/>")

        plan = SyncPlan(files_to_delete=[target])

        result = execute_plan(plan, dest=dest, delete_mode="delete")

        assert result.trashed == 1
        assert not target.exists()
        # No .trash directory should be created
        assert not (dest / ".trash").exists()

    def test_hard_delete_cleans_empty_parents(self, tmp_path: Path) -> None:
        # TODO-v0.1-REVIEW
        dest = tmp_path / "dst"
        target = dest / "SAMPLES" / "DRUMS" / "Kick" / "kick.wav"
        _touch(target, b"\x00")

        plan = SyncPlan(files_to_delete=[target])

        execute_plan(plan, dest=dest, delete_mode="delete")

        # All ancestor dirs up to dest should be removed (they were empty)
        assert not (dest / "SAMPLES" / "DRUMS" / "Kick").exists()
        assert not (dest / "SAMPLES" / "DRUMS").exists()
        assert not (dest / "SAMPLES").exists()
        # dest itself must still exist
        assert dest.exists()

    def test_hard_delete_preserves_non_empty_parents(self, tmp_path: Path) -> None:
        # TODO-v0.1-REVIEW
        dest = tmp_path / "dst"
        target = dest / "SAMPLES" / "DRUMS" / "kick.wav"
        sibling = dest / "SAMPLES" / "DRUMS" / "snare.wav"
        _touch(target, b"\x00")
        _touch(sibling, b"\x00")

        plan = SyncPlan(files_to_delete=[target])

        execute_plan(plan, dest=dest, delete_mode="delete")

        assert not target.exists()
        assert sibling.exists()
        # Parent dir preserved because sibling still exists
        assert (dest / "SAMPLES" / "DRUMS").exists()

    def test_trash_mode_default_still_works(self, tmp_path: Path) -> None:
        # TODO-v0.1-REVIEW
        dest = tmp_path / "dst"
        target = dest / "KITS" / "OldKit.XML"
        _touch(target, b"<kit/>")

        plan = SyncPlan(files_to_delete=[target])

        result = execute_plan(plan, dest=dest)

        assert result.trashed == 1
        assert not target.exists()
        trash_files = list((dest / ".trash").rglob("OldKit.XML"))
        assert len(trash_files) == 1


# =============================================================================
# print_plan — delete_label
# =============================================================================


class TestPrintPlanDeleteLabel:
    def test_default_label_is_trash(self, tmp_path: Path, capsys) -> None:
        # TODO-v0.1-REVIEW
        dest = tmp_path / "dst"
        target = dest / "old.xml"
        _touch(target, b"x")

        plan = SyncPlan(files_to_delete=[target])

        print_plan(plan, dest=dest)

        output = capsys.readouterr().out
        assert "trash" in output

    def test_custom_label_delete(self, tmp_path: Path, capsys) -> None:
        # TODO-v0.1-REVIEW
        dest = tmp_path / "dst"
        target = dest / "old.wav"
        _touch(target, b"x")

        plan = SyncPlan(files_to_delete=[target])

        print_plan(plan, dest=dest, delete_label="delete")

        output = capsys.readouterr().out
        assert "delete" in output
        assert "trash" not in output

    def test_summary_uses_custom_label(self, tmp_path: Path, capsys) -> None:
        # TODO-v0.1-REVIEW
        dest = tmp_path / "dst"
        target = dest / "old.wav"
        _touch(target, b"x")

        plan = SyncPlan(files_to_delete=[target], files_unchanged=3)

        print_plan(plan, dest=dest, delete_label="remove")

        output = capsys.readouterr().out
        assert "1 to remove" in output
