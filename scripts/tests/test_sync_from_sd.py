"""Tests for sync_from_sd.py — sync-specific logic."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from sync_from_sd import (
    FileRecord,
    FilesDict,
    SyncError,
    SyncPlan,
    SyncResult,
    _build_post_sync_manifest,
    _mtime_matches,
    _read_manifest,
    _write_manifest,
    append_sync_log,
    compute_sync,
    execute_plan,
)

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
        manifest: FilesDict = {"kits/kit.xml": {"size": len(content), "mtime": src_mtime}}

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
        manifest: FilesDict = {"other/file.xml": {"size": 10, "mtime": 1.0}}

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
        old_files: dict[str, FileRecord] = {}

        ts, files = _build_post_sync_manifest(plan, src_scan, dest, old_files)

        assert "kits/kit.xml" in files
        entry = files["kits/kit.xml"]
        assert entry["size"] == kit_file.stat().st_size
        assert ts != ""

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
            "kits/kept.xml": {"size": 6, "mtime": 1_700_000_000.0},
            "kits/trashed.xml": {"size": 10, "mtime": 1_600_000_000.0},
        }

        _ts, files = _build_post_sync_manifest(plan, src_scan, dest, old_files)

        assert "kits/kept.xml" in files
        assert "kits/trashed.xml" not in files

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

        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        assert "copied=1" in lines[0]
        assert "copied=2" in lines[1]
        assert "---" not in log_path.read_text(encoding="utf-8")


# =============================================================================
# _read_manifest / _write_manifest (inlined manifest functions)
# =============================================================================


class TestReadManifest:
    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        ts, files = _read_manifest(tmp_path / "nonexistent.json")
        assert ts == ""
        assert files == {}

    def test_corrupt_json_returns_empty(self, tmp_path: Path) -> None:
        bad = tmp_path / "manifest.json"
        bad.write_text("{invalid json!!!", encoding="utf-8")

        ts, files = _read_manifest(bad)

        assert ts == ""
        assert files == {}

    def test_corrupt_json_prints_warning(self, tmp_path: Path, capsys: object) -> None:
        bad = tmp_path / "manifest.json"
        bad.write_text("{broken", encoding="utf-8")

        _read_manifest(bad)

        import _pytest.capture

        assert isinstance(capsys, _pytest.capture.CaptureFixture)
        captured = capsys.readouterr()
        assert "Warning" in captured.out
        assert "corrupt" in captured.out.lower()

    def test_valid_manifest_round_trip(self, tmp_path: Path) -> None:
        mf = tmp_path / "manifest.json"
        files: dict[str, FileRecord] = {
            "kits/mykit.xml": {"size": 1234, "mtime": 1712600000.0},
            "samples/kick.wav": {"size": 56789, "mtime": 1712600100.0},
        }
        ts = "2026-04-09T12:00:00+00:00"

        _write_manifest(mf, timestamp=ts, files=files)
        read_ts, read_files = _read_manifest(mf)

        assert read_ts == ts
        assert len(read_files) == 2
        assert read_files["kits/mykit.xml"]["size"] == 1234
        assert read_files["samples/kick.wav"]["mtime"] == 1712600100.0


class TestWriteManifest:
    def test_creates_file(self, tmp_path: Path) -> None:
        mf_path = tmp_path / "manifest.json"
        _write_manifest(mf_path, timestamp="2026-04-09T00:00:00+00:00", files={})

        assert mf_path.exists()
        raw = json.loads(mf_path.read_text(encoding="utf-8"))
        assert "last_sync_timestamp" in raw
        assert "files" in raw

    def test_atomic_write_no_temp_file_lingers(self, tmp_path: Path) -> None:
        mf_path = tmp_path / "manifest.json"
        _write_manifest(mf_path, timestamp="", files={})

        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == []

    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        mf_path = tmp_path / "scripts" / "data" / "manifest.json"
        _write_manifest(mf_path, timestamp="", files={})

        assert mf_path.parent.is_dir()
