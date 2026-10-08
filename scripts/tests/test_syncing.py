# Deluge CLI v0.1
"""Tests for deluge_lib.syncing — shared sync primitives."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tests.conftest import _touch
from deluge_lib.scanning import FileEntry, ScanResult, normalise_mtime
from deluge_lib.syncing import (
    SyncError,
    SyncPlan,
    SyncResult,
    _mtime_matches,
    append_sync_log,
    clean_empty_dirs,
    compute_sync,
    execute_plan,
    print_plan,
)


# =============================================================================
# _mtime_matches
# =============================================================================


class TestMtimeMatches:
    def test_identical_times(self) -> None:
        
        assert _mtime_matches(1000.0, 1000.0) is True

    def test_within_fat32_tolerance(self) -> None:
        
        assert _mtime_matches(1000.0, 1001.5) is True

    def test_exactly_at_tolerance(self) -> None:
        
        assert _mtime_matches(1000.0, 1002.0) is True

    def test_beyond_tolerance(self) -> None:
        
        assert _mtime_matches(1000.0, 1005.0) is False

    def test_dst_offset_not_matched(self) -> None:
        # DST shift (3600s) should NOT be treated as matching
        
        assert _mtime_matches(1000.0, 4600.0) is False


# =============================================================================
# compute_sync — comparison logic
# =============================================================================


class TestComputeSyncNewFile:
    """New file on source not in dest → files_to_copy."""

    def test_new_file_added_to_copy(self, tmp_path: Path) -> None:
        
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
        
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        mtime = 1_700_000_000.0
        _touch(src / "KITS" / "Kit.XML", b"<kit>new</kit>", mtime=mtime)
        _touch(dst / "KITS" / "Kit.XML", b"<kit/>", mtime=mtime)

        plan, _ = compute_sync(src, dst)

        assert len(plan.files_to_copy) == 1

    def test_same_size_different_mtime_triggers_copy(self, tmp_path: Path) -> None:
        
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
        
        src_file = tmp_path / "src" / "KITS" / "Kit.XML"
        dst_file = tmp_path / "dst" / "KITS" / "Kit.XML"
        _touch(src_file, b"<kit>content</kit>")

        plan = SyncPlan(files_to_copy=[(src_file, dst_file)])

        result = execute_plan(plan, dest=tmp_path / "dst")

        assert result.copied == 1
        assert dst_file.read_bytes() == b"<kit>content</kit>"


class TestExecutePlanTrash:
    def test_trashes_files_to_trash_directory(self, tmp_path: Path) -> None:
        
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
        
        log_path = tmp_path / "data" / "sync.log"
        result = SyncResult(
            copied=5,
            trashed=3,
            unchanged=10,
        )

        with patch("deluge_lib.syncing.SYNC_LOG_PATH", log_path):
            append_sync_log(result, direction="from-sd", elapsed_seconds=65.0)

        content = log_path.read_text(encoding="utf-8")
        lines = content.strip().splitlines()
        assert len(lines) == 1
        line = lines[0]
        assert "SUCCESS" in line
        assert "direction=from-sd" in line
        assert "copied=5" in line
        assert "trashed=3" in line
        assert "unchanged=10" in line
        assert "elapsed=1m 5s" in line
        assert "error=" not in line

    def test_creates_entry_on_failure_with_error(self, tmp_path: Path) -> None:
        
        log_path = tmp_path / "data" / "sync.log"
        result = SyncResult(
            copied=2,
        )

        with patch("deluge_lib.syncing.SYNC_LOG_PATH", log_path):
            append_sync_log(
                result,
                direction="from-sd",
                elapsed_seconds=12.0,
                error="Permission denied: /mnt/sd/file.wav",
            )

        content = log_path.read_text(encoding="utf-8")
        lines = content.strip().splitlines()
        assert len(lines) == 1
        line = lines[0]
        assert "FAILED" in line
        assert "copied=2" in line
        assert 'error="Permission denied: /mnt/sd/file.wav"' in line

    def test_log_file_created_in_data_directory(self, tmp_path: Path) -> None:
        
        log_path = tmp_path / "data" / "sync.log"
        result = SyncResult()

        with patch("deluge_lib.syncing.SYNC_LOG_PATH", log_path):
            append_sync_log(result, direction="from-sd", elapsed_seconds=1.0)

        assert log_path.exists()
        assert log_path.parent.name == "data"

    def test_multiple_entries_appended(self, tmp_path: Path) -> None:
        
        log_path = tmp_path / "data" / "sync.log"
        r1 = SyncResult(copied=1)
        r2 = SyncResult(copied=2)

        with patch("deluge_lib.syncing.SYNC_LOG_PATH", log_path):
            append_sync_log(r1, direction="from-sd", elapsed_seconds=1.0)
            append_sync_log(r2, direction="to-sd", elapsed_seconds=2.0)

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
        
        dest = tmp_path / "dst"
        target = dest / "old.xml"
        _touch(target, b"x")

        plan = SyncPlan(files_to_delete=[target])

        print_plan(plan, dest=dest)

        output = capsys.readouterr().out
        assert "trash" in output

    def test_custom_label_delete(self, tmp_path: Path, capsys) -> None:
        
        dest = tmp_path / "dst"
        target = dest / "old.wav"
        _touch(target, b"x")

        plan = SyncPlan(files_to_delete=[target])

        print_plan(plan, dest=dest, delete_label="delete")

        output = capsys.readouterr().out
        assert "delete" in output
        assert "trash" not in output

    def test_summary_uses_custom_label(self, tmp_path: Path, capsys) -> None:
        
        dest = tmp_path / "dst"
        target = dest / "old.wav"
        _touch(target, b"x")

        plan = SyncPlan(files_to_delete=[target], files_unchanged=3)

        print_plan(plan, dest=dest, delete_label="remove")

        output = capsys.readouterr().out
        assert "1 to remove" in output


# =============================================================================
# clean_empty_dirs
# =============================================================================


class TestCleanEmptyDirs:
    def test_warns_and_continues_when_directory_cannot_be_removed(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        root = tmp_path / "root"
        blocked = root / "CLIPS" / "Blocked"
        removable = root / "EXPORTS" / "Removable"
        blocked.mkdir(parents=True)
        removable.mkdir(parents=True)

        original_rmdir = Path.rmdir

        def rmdir(path: Path) -> None:
            if path == blocked:
                raise PermissionError(13, "Access is denied", str(path))
            original_rmdir(path)

        monkeypatch.setattr(Path, "rmdir", rmdir)

        removed = clean_empty_dirs(root)

        output = capsys.readouterr().out
        assert removed == 1
        assert blocked.exists()
        assert not removable.exists()
        assert "Warning: could not remove empty directory" in output
        assert str(blocked) in output


# =============================================================================
# compute_sync — hash-aware comparison
# =============================================================================


class TestComputeSyncHashAware:
    """Hash-aware comparison branches in compute_sync with manifest."""

    def test_stat_cache_hit_skips_file(self, tmp_path: Path) -> None:
        """Both sides match manifest stats + manifest has hash → skip (no I/O)."""
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        content = b"<kit/>"
        sd_mtime = 1_700_000_000.0
        local_mtime = 1_690_000_000.0
        _touch(src / "KITS" / "Kit.XML", content, mtime=sd_mtime)
        _touch(dst / "KITS" / "Kit.XML", content, mtime=local_mtime)

        manifest = {"kits/kit.xml": {
            "sd_size": len(content), "sd_mtime": sd_mtime,
            "local_size": len(content), "local_mtime": local_mtime,
            "hash": "abc123",
        }}

        plan, _ = compute_sync(src, dst, manifest=manifest)

        assert plan.files_to_copy == []
        assert plan.files_unchanged == 1

    def test_local_stat_miss_hash_match_skips(self, tmp_path: Path) -> None:
        """Local mtime changed but content hash matches manifest → skip (mtime drift)."""
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        content = b"<kit/>"
        sd_mtime = 1_700_000_000.0
        original_local_mtime = 1_690_000_000.0
        changed_local_mtime = 1_680_000_000.0  # mtime drifted

        _touch(src / "KITS" / "Kit.XML", content, mtime=sd_mtime)
        _touch(dst / "KITS" / "Kit.XML", content, mtime=changed_local_mtime)

        # Compute the real hash of the content
        import hashlib
        real_hash = hashlib.sha256(content).hexdigest()

        manifest = {"kits/kit.xml": {
            "sd_size": len(content), "sd_mtime": sd_mtime,
            "local_size": len(content), "local_mtime": original_local_mtime,
            "hash": real_hash,
        }}

        plan, _ = compute_sync(src, dst, manifest=manifest)

        assert plan.files_to_copy == []
        assert plan.files_unchanged == 1
        # Manifest local stats should be updated to current values
        assert manifest["kits/kit.xml"]["local_mtime"] == changed_local_mtime

    def test_local_stat_miss_hash_mismatch_copies(self, tmp_path: Path) -> None:
        """Local mtime changed AND content hash differs → copy (genuine change)."""
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        sd_content = b"<kit>original</kit>"
        local_content = b"<kit>modified</kit>"
        sd_mtime = 1_700_000_000.0
        original_local_mtime = 1_690_000_000.0
        changed_local_mtime = 1_680_000_000.0

        _touch(src / "KITS" / "Kit.XML", sd_content, mtime=sd_mtime)
        _touch(dst / "KITS" / "Kit.XML", local_content, mtime=changed_local_mtime)

        import hashlib
        original_hash = hashlib.sha256(sd_content).hexdigest()

        manifest = {"kits/kit.xml": {
            "sd_size": len(sd_content), "sd_mtime": sd_mtime,
            "local_size": len(sd_content), "local_mtime": original_local_mtime,
            "hash": original_hash,
        }}

        plan, _ = compute_sync(src, dst, manifest=manifest)

        assert len(plan.files_to_copy) == 1

    def test_sd_stat_and_content_change_copies(self, tmp_path: Path) -> None:
        """SD stat+content genuinely changed (hash mismatch) → copy."""
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        new_sd_content = b"<kit>updated</kit>"
        local_content = b"<kit>original</kit>"
        sd_mtime = 1_700_000_000.0
        local_mtime = 1_690_000_000.0

        _touch(src / "KITS" / "Kit.XML", new_sd_content, mtime=sd_mtime)
        _touch(dst / "KITS" / "Kit.XML", local_content, mtime=local_mtime)

        manifest = {"kits/kit.xml": {
            "sd_size": 100,  # Different from actual SD size
            "sd_mtime": sd_mtime,
            "local_size": len(local_content), "local_mtime": local_mtime,
            "hash": "abc123",
        }}

        plan, _ = compute_sync(src, dst, manifest=manifest)

        assert len(plan.files_to_copy) == 1

    def test_null_hash_computes_and_stores(self, tmp_path: Path) -> None:
        """Manifest entry with null hash → hash computed and stored, copy triggered."""
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        content = b"<kit/>"
        sd_mtime = 1_700_000_000.0
        original_local_mtime = 1_690_000_000.0
        changed_local_mtime = 1_680_000_000.0

        _touch(src / "KITS" / "Kit.XML", content, mtime=sd_mtime)
        _touch(dst / "KITS" / "Kit.XML", content, mtime=changed_local_mtime)

        manifest = {"kits/kit.xml": {
            "sd_size": len(content), "sd_mtime": sd_mtime,
            "local_size": len(content), "local_mtime": original_local_mtime,
            "hash": None,
        }}

        plan, _ = compute_sync(src, dst, manifest=manifest)

        # Null hash falls back to mtime-based decision — local changed → copy
        assert len(plan.files_to_copy) == 1
        # But hash should now be populated in the manifest for next run
        assert manifest["kits/kit.xml"]["hash"] is not None
        assert len(manifest["kits/kit.xml"]["hash"]) == 64  # SHA-256 hex length

    def test_null_mtime_forces_rehash(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """File with null mtime (0 or negative) → stat cache always invalid, rehash required."""
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        content = b"<kit/>"

        _touch(src / "KITS" / "Kit.XML", content)
        _touch(dst / "KITS" / "Kit.XML", content)

        null_mtime = 0.0

        import hashlib
        real_hash = hashlib.sha256(content).hexdigest()

        # Mock scan_tree to return null mtime entries
        src_scan = ScanResult(files={"kits/kit.xml": FileEntry(
            rel_path=Path("KITS/Kit.XML"), size=len(content), mtime=null_mtime,
        )})
        dst_scan = ScanResult(files={"kits/kit.xml": FileEntry(
            rel_path=Path("KITS/Kit.XML"), size=len(content), mtime=null_mtime,
        )})
        calls = iter([src_scan, dst_scan])
        monkeypatch.setattr(
            "deluge_lib.syncing.scan_tree", lambda *a, **kw: next(calls),
        )

        manifest = {"kits/kit.xml": {
            "sd_size": len(content), "sd_mtime": null_mtime,
            "local_size": len(content), "local_mtime": null_mtime,
            "hash": real_hash,
        }}

        plan, _ = compute_sync(src, dst, manifest=manifest)

        # null mtime → sd_changed check: _mtime_matches(0.0, 0.0) is True (within tolerance)
        # but local stat cache invalid (mtime <= 0), so hash comparison is done.
        # Hash matches → file is unchanged
        assert plan.files_to_copy == []
        assert plan.files_unchanged == 1

    def test_no_manifest_entry_falls_through(self, tmp_path: Path) -> None:
        """File not in manifest → direct stat comparison (existing behaviour)."""
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        content = b"<kit/>"
        mtime = 1_700_000_000.0
        _touch(src / "KITS" / "Kit.XML", content, mtime=mtime)
        _touch(dst / "KITS" / "Kit.XML", content, mtime=mtime)

        # Manifest has entry for a different file
        manifest = {"other/file.xml": {
            "sd_size": 10, "sd_mtime": 1.0,
            "local_size": 10, "local_mtime": 1.0,
            "hash": "abc",
        }}

        plan, _ = compute_sync(src, dst, manifest=manifest)

        assert plan.files_to_copy == []
        assert plan.files_unchanged == 1

    def test_manifest_none_unchanged(self, tmp_path: Path) -> None:
        """manifest=None → existing stat-only comparison (cloud sync path)."""
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        content = b"<kit/>"
        mtime = 1_700_000_000.0
        _touch(src / "KITS" / "Kit.XML", content, mtime=mtime)
        _touch(dst / "KITS" / "Kit.XML", content, mtime=mtime)

        plan, _ = compute_sync(src, dst, manifest=None)

        assert plan.files_to_copy == []
        assert plan.files_unchanged == 1

    def test_sd_stat_drift_hash_match_skips(self, tmp_path: Path) -> None:
        """SD mtime drifted but content hash matches manifest → skip."""
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        content = b"<kit/>"
        sd_mtime_original = 1_700_000_000.0
        sd_mtime_drifted = 1_700_000_004.0  # beyond FAT32 tolerance
        local_mtime = 1_690_000_000.0

        import hashlib
        real_hash = hashlib.sha256(content).hexdigest()

        _touch(src / "KITS" / "Kit.XML", content, mtime=sd_mtime_drifted)
        _touch(dst / "KITS" / "Kit.XML", content, mtime=local_mtime)

        manifest = {"kits/kit.xml": {
            "sd_size": len(content), "sd_mtime": sd_mtime_original,
            "local_size": len(content), "local_mtime": local_mtime,
            "hash": real_hash,
        }}

        plan, _ = compute_sync(src, dst, manifest=manifest)

        assert plan.files_to_copy == []
        assert plan.files_unchanged == 1
        # Manifest sd stats updated to current values
        assert manifest["kits/kit.xml"]["sd_mtime"] == sd_mtime_drifted

    def test_sd_stat_change_null_hash_copies(self, tmp_path: Path) -> None:
        """SD stat changed with null hash → conservative copy (can't verify)."""
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        content = b"<kit/>"
        sd_mtime_original = 1_700_000_000.0
        sd_mtime_changed = 1_700_000_004.0
        local_mtime = 1_690_000_000.0

        _touch(src / "KITS" / "Kit.XML", content, mtime=sd_mtime_changed)
        _touch(dst / "KITS" / "Kit.XML", content, mtime=local_mtime)

        manifest = {"kits/kit.xml": {
            "sd_size": len(content), "sd_mtime": sd_mtime_original,
            "local_size": len(content), "local_mtime": local_mtime,
            "hash": None,
        }}

        plan, _ = compute_sync(src, dst, manifest=manifest)

        assert len(plan.files_to_copy) == 1

    def test_source_is_sd_false_sd_stat_drift_skips(self, tmp_path: Path) -> None:
        """source_is_sd=False: SD mtime drifted but hash matches → skip."""
        src = tmp_path / "src"  # local
        dst = tmp_path / "dst"  # SD
        content = b"<kit/>"
        local_mtime = 1_700_000_000.0
        sd_mtime = 1_600_000_000.0
        changed_sd_mtime = 1_590_000_000.0

        import hashlib
        real_hash = hashlib.sha256(content).hexdigest()

        _touch(src / "KITS" / "Kit.XML", content, mtime=local_mtime)
        _touch(dst / "KITS" / "Kit.XML", content, mtime=changed_sd_mtime)

        # source_is_sd=False: source=local, dest=SD
        # sd_entry = dst_entry, local_entry = src_entry
        manifest = {"kits/kit.xml": {
            "sd_size": len(content), "sd_mtime": sd_mtime,
            "local_size": len(content), "local_mtime": local_mtime,
            "hash": real_hash,
        }}

        # SD mtime changed but hash matches → stat drift only → skip
        plan, _ = compute_sync(src, dst, manifest=manifest, source_is_sd=False)

        assert plan.files_to_copy == []
        assert plan.files_unchanged == 1
        # Manifest sd stats updated to current values
        assert manifest["kits/kit.xml"]["sd_mtime"] == changed_sd_mtime
