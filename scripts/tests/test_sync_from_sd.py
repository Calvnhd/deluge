"""Tests for sync_from_sd.py — sync-specific logic."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sync_from_sd import (
    SyncError,
    SyncPlan,
    SyncResult,
    _build_post_sync_manifest,
    _mtime_matches,
    append_sync_log,
    compute_sync,
    execute_plan,
)

from deluge_lib.manifest import ManifestData
from deluge_lib.scanning import FileEntry, ScanResult


def _touch(path: Path, content: bytes = b"x", mtime: float | None = None) -> None:
    """Create a tiny file with optional content and mtime."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    if mtime is not None:
        os.utime(path, (mtime, mtime))


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
        _touch(dst / "KITS" / "Kit.XML", content, mtime=1_600_000_000.0)

        # Manifest records the correct mtime from last sync
        manifest = {"kits/kit.xml": {"size": len(content), "mtime": src_mtime}}

        plan, _ = compute_sync(src, dst, manifest=manifest)

        # Manifest mtime matches source → unchanged (not a copy)
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
        manifest = {"other/file.xml": {"size": 10, "mtime": 1.0}}

        plan, _ = compute_sync(src, dst, manifest=manifest)

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
# _build_post_sync_manifest
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
        old_manifest = ManifestData()

        result = _build_post_sync_manifest(plan, src_scan, dest, old_manifest)

        assert "kits/kit.xml" in result.files
        entry = result.files["kits/kit.xml"]
        assert entry["size"] == kit_file.stat().st_size
        assert result.last_sync_direction == "sd-to-local"

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
        old_manifest = ManifestData(
            files={
                "kits/kept.xml": {"size": 6, "mtime": 1_700_000_000.0},
                "kits/trashed.xml": {"size": 10, "mtime": 1_600_000_000.0},
            },
        )

        result = _build_post_sync_manifest(plan, src_scan, dest, old_manifest)

        assert "kits/kept.xml" in result.files
        assert "kits/trashed.xml" not in result.files

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

        append_sync_log(result, elapsed_seconds=65.0, log_path=log_path)

        content = log_path.read_text(encoding="utf-8")
        assert "SUCCESS" in content
        assert "files_copied: 5" in content
        assert "files_trashed: 3" in content
        assert "files_unchanged: 10" in content
        assert "1m 5s" in content

    def test_creates_entry_on_failure_with_error(self, tmp_path: Path) -> None:
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
        assert "FAILED" in content
        assert "files_copied: 2" in content
        assert "error: Permission denied: /mnt/sd/file.wav" in content

    def test_log_file_created_in_data_directory(self, tmp_path: Path) -> None:
        log_path = tmp_path / "data" / "sync.log"
        result = SyncResult()

        append_sync_log(result, elapsed_seconds=1.0, log_path=log_path)

        assert log_path.exists()
        assert log_path.parent.name == "data"

    def test_multiple_entries_appended(self, tmp_path: Path) -> None:
        log_path = tmp_path / "data" / "sync.log"
        r1 = SyncResult(copied=1)
        r2 = SyncResult(copied=2)

        append_sync_log(r1, elapsed_seconds=1.0, log_path=log_path)
        append_sync_log(r2, elapsed_seconds=2.0, log_path=log_path)

        content = log_path.read_text(encoding="utf-8")
        assert content.count("---") == 2
        assert content.count("SUCCESS") == 2
