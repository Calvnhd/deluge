"""Tests for sync_from_sd.py — manifest logic."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sync_from_sd import (
    FileRecord,
    _build_post_sync_manifest,
    _read_manifest,
    _write_manifest,
)

from tests.conftest import _touch
from deluge_lib.scanning import FileEntry, ScanResult
from deluge_lib.syncing import SyncError, SyncPlan, SyncResult, execute_plan


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
