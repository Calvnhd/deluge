# Deluge CLI v0.1
"""Tests for sync_to_sd.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from sync_to_sd import (
    main,
)

from tests.conftest import _touch
from deluge_lib.scanning import FileEntry, ScanResult, normalise_mtime
from deluge_lib.syncing import build_post_sync_manifest, FileRecord, SyncPlan, read_manifest, write_manifest


def _setup_env(
    monkeypatch: pytest.MonkeyPatch,
    deluge_root: Path,
    sd_path: Path,
) -> None:
    
    """Set environment variables and stub load_dotenv."""
    monkeypatch.setenv("DELUGE_ROOT", str(deluge_root))
    monkeypatch.setenv("SD_CARD_PATH", str(sd_path))


# ============================================================================
# Dry run
# ============================================================================


class TestDryRun:
    def test_dry_run_shows_preview_without_modifying(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # Repo has a file, SD does not
        
        deluge = tmp_path / "DELUGE"
        _touch(deluge / "KITS" / "MyKit.XML", b"<kit/>", mtime=1_700_000_000.0)

        sd = tmp_path / "SD"
        sd.mkdir()

        _setup_env(monkeypatch, deluge, sd)

        with patch("deluge_lib.cli_utils.load_dotenv"):
            main(["--dry-run"])

        out = capsys.readouterr().out
        assert "MyKit.XML" in out
        assert "Dry run complete." in out
        # Nothing copied to SD
        assert not (sd / "KITS" / "MyKit.XML").exists()

    def test_dry_run_no_confirmation_prompt(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        
        deluge = tmp_path / "DELUGE"
        _touch(deluge / "KITS" / "Kit.XML", b"<kit/>", mtime=1_700_000_000.0)

        sd = tmp_path / "SD"
        sd.mkdir()

        _setup_env(monkeypatch, deluge, sd)

        with (
            patch("deluge_lib.cli_utils.load_dotenv"),
            patch("sync_to_sd.confirm_apply") as mock_confirm,
        ):
            main(["--dry-run"])

        mock_confirm.assert_not_called()


# ============================================================================
# Up to date
# ============================================================================


class TestUpToDate:
    def test_already_up_to_date(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        
        deluge = tmp_path / "DELUGE"
        _touch(deluge / "KITS" / "Kit.XML", b"<kit/>", mtime=1_700_000_000.0)

        sd = tmp_path / "SD"
        _touch(sd / "KITS" / "Kit.XML", b"<kit/>", mtime=1_700_000_000.0)

        _setup_env(monkeypatch, deluge, sd)

        with patch("deluge_lib.cli_utils.load_dotenv"):
            main(["--dry-run"])

        out = capsys.readouterr().out
        assert "Already up to date" in out


# ============================================================================
# Full sync
# ============================================================================


class TestFullSync:
    def test_new_files_copied_to_sd(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        
        deluge = tmp_path / "DELUGE"
        _touch(deluge / "KITS" / "NewKit.XML", b"<new/>", mtime=1_700_000_000.0)
        _touch(deluge / "SYNTHS" / "Synth.XML", b"<synth/>", mtime=1_700_000_000.0)

        sd = tmp_path / "SD"
        sd.mkdir()

        _setup_env(monkeypatch, deluge, sd)

        with (
            patch("deluge_lib.cli_utils.load_dotenv"),
            patch("sync_to_sd.confirm_apply", return_value=True),
        ):
            main([])

        assert (sd / "KITS" / "NewKit.XML").read_bytes() == b"<new/>"
        assert (sd / "SYNTHS" / "Synth.XML").read_bytes() == b"<synth/>"
        out = capsys.readouterr().out
        assert "Sync complete" in out

    def test_modified_files_overwritten_on_sd(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        
        deluge = tmp_path / "DELUGE"
        _touch(deluge / "KITS" / "Kit.XML", b"<updated/>", mtime=1_700_001_000.0)

        sd = tmp_path / "SD"
        _touch(sd / "KITS" / "Kit.XML", b"<old/>", mtime=1_700_000_000.0)

        _setup_env(monkeypatch, deluge, sd)

        with (
            patch("deluge_lib.cli_utils.load_dotenv"),
            patch("sync_to_sd.confirm_apply", return_value=True),
        ):
            main([])

        assert (sd / "KITS" / "Kit.XML").read_bytes() == b"<updated/>"

    def test_sd_only_files_deleted(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        
        deluge = tmp_path / "DELUGE"
        _touch(deluge / "KITS" / "Kept.XML", b"<kept/>", mtime=1_700_000_000.0)

        sd = tmp_path / "SD"
        _touch(sd / "KITS" / "Kept.XML", b"<kept/>", mtime=1_700_000_000.0)
        _touch(sd / "KITS" / "OldKit.XML", b"<old/>", mtime=1_600_000_000.0)

        _setup_env(monkeypatch, deluge, sd)

        with (
            patch("deluge_lib.cli_utils.load_dotenv"),
            patch("sync_to_sd.confirm_apply", return_value=True),
        ):
            main([])

        # Old file removed from SD
        assert not (sd / "KITS" / "OldKit.XML").exists()
        # Kept file untouched
        assert (sd / "KITS" / "Kept.XML").exists()
        # No .trash/ directory created
        assert not (deluge / ".trash").exists()

    def test_unchanged_files_left_alone(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        
        deluge = tmp_path / "DELUGE"
        _touch(deluge / "KITS" / "Same.XML", b"<same/>", mtime=1_700_000_000.0)
        _touch(deluge / "KITS" / "New.XML", b"<new/>", mtime=1_700_000_000.0)

        sd = tmp_path / "SD"
        _touch(sd / "KITS" / "Same.XML", b"<same/>", mtime=1_700_000_000.0)

        _setup_env(monkeypatch, deluge, sd)

        with (
            patch("deluge_lib.cli_utils.load_dotenv"),
            patch("sync_to_sd.confirm_apply", return_value=True),
        ):
            main([])

        out = capsys.readouterr().out
        assert "1 copied" in out
        # Unchanged file still has original content
        assert (sd / "KITS" / "Same.XML").read_bytes() == b"<same/>"

    def test_result_summary_correct_counts(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        
        deluge = tmp_path / "DELUGE"
        _touch(deluge / "KITS" / "A.XML", b"<a/>", mtime=1_700_000_000.0)
        _touch(deluge / "KITS" / "B.XML", b"<b/>", mtime=1_700_000_000.0)

        sd = tmp_path / "SD"
        _touch(sd / "KITS" / "B.XML", b"<b/>", mtime=1_700_000_000.0)
        _touch(sd / "KITS" / "C.XML", b"<c/>", mtime=1_600_000_000.0)

        _setup_env(monkeypatch, deluge, sd)

        with (
            patch("deluge_lib.cli_utils.load_dotenv"),
            patch("sync_to_sd.confirm_apply", return_value=True),
        ):
            main([])

        out = capsys.readouterr().out
        # A copied, B unchanged, C deleted
        assert "1 copied" in out
        assert "1 deleted" in out

    def test_log_entry_written(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        
        deluge = tmp_path / "DELUGE"
        _touch(deluge / "KITS" / "Kit.XML", b"<kit/>", mtime=1_700_000_000.0)

        sd = tmp_path / "SD"
        sd.mkdir()

        log_path = tmp_path / "to_sd_sync.log"

        _setup_env(monkeypatch, deluge, sd)

        with (
            patch("deluge_lib.cli_utils.load_dotenv"),
            patch("sync_to_sd.confirm_apply", return_value=True),
            patch("deluge_lib.syncing.SYNC_LOG_PATH", log_path),
        ):
            main([])

        assert log_path.exists()
        log_content = log_path.read_text()
        assert "SUCCESS" in log_content
        assert "copied=1" in log_content

    def test_empty_parent_dirs_cleaned_on_sd(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        
        """When a file is deleted from SD and its parent becomes empty, clean up."""
        deluge = tmp_path / "DELUGE"
        deluge.mkdir()

        sd = tmp_path / "SD"
        _touch(sd / "KITS" / "SUB" / "Old.XML", b"<old/>", mtime=1_600_000_000.0)

        _setup_env(monkeypatch, deluge, sd)

        with (
            patch("deluge_lib.cli_utils.load_dotenv"),
            patch("sync_to_sd.confirm_apply", return_value=True),
        ):
            main([])

        # File, SUB dir, and KITS dir should all be gone (empty)
        assert not (sd / "KITS" / "SUB").exists()
        assert not (sd / "KITS").exists()


# ============================================================================
# build_post_sync_manifest
# ============================================================================


class TestBuildPostSyncManifest:
    def test_creates_correct_entries_after_sync(self, tmp_path: Path) -> None:
        dest = tmp_path / "SD"
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
            files_to_copy=[(tmp_path / "DELUGE" / "KITS" / "Kit.XML", kit_file)],
        )
        old_files: dict[str, FileRecord] = {}

        files = build_post_sync_manifest(plan, src_scan, dest, old_files, source_is_sd=False)

        assert "kits/kit.xml" in files
        entry = files["kits/kit.xml"]
        assert entry["local_size"] == 6
        assert entry["local_mtime"] == 1_700_000_000.0
        assert entry["sd_size"] == kit_file.stat().st_size
        assert entry["sd_mtime"] == normalise_mtime(kit_file.stat().st_mtime)

    def test_deleted_files_excluded(self, tmp_path: Path) -> None:
        dest = tmp_path / "SD"

        src_scan = ScanResult(
            files={
                "kits/kept.xml": FileEntry(
                    rel_path=Path("KITS/Kept.XML"),
                    size=6,
                    mtime=1_700_000_000.0,
                ),
            },
        )
        plan = SyncPlan(
            files_to_delete=[dest / "KITS" / "Deleted.XML"],
        )
        old_files: dict[str, FileRecord] = {
            "kits/kept.xml": {
                "local_size": 6, "local_mtime": 1_700_000_000.0,
                "sd_size": 6, "sd_mtime": 1_700_000_100.0,
            },
            "kits/deleted.xml": {
                "local_size": 10, "local_mtime": 1_600_000_000.0,
                "sd_size": 10, "sd_mtime": 1_600_000_100.0,
            },
        }

        files = build_post_sync_manifest(plan, src_scan, dest, old_files, source_is_sd=False)

        assert "kits/kept.xml" in files
        assert "kits/deleted.xml" not in files

    def test_unchanged_preserves_old_entry(self, tmp_path: Path) -> None:
        dest = tmp_path / "SD"
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
            "local_size": 6, "local_mtime": 1_700_000_000.0,
            "sd_size": 6, "sd_mtime": 1_700_000_050.0,
        }
        old_files: dict[str, FileRecord] = {"kits/kit.xml": old_entry}

        files = build_post_sync_manifest(plan, src_scan, dest, old_files, source_is_sd=False)

        assert files["kits/kit.xml"] is old_entry


# ============================================================================
# build_post_sync_manifest — hash population
# ============================================================================


class TestBuildPostSyncManifestHashing:
    """Hash population in build_post_sync_manifest for sync_to_sd."""

    def test_copied_files_get_hash(self, tmp_path: Path) -> None:
        """Copied files have hash computed from destination file on SD."""
        dest = tmp_path / "SD"
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
            files_to_copy=[(tmp_path / "DELUGE" / "KITS" / "Kit.XML", kit_file)],
        )
        old_files: dict[str, FileRecord] = {}

        files = build_post_sync_manifest(plan, src_scan, dest, old_files, source_is_sd=False)

        assert files["kits/kit.xml"]["hash"] == expected_hash

    def test_unchanged_files_preserve_hash(self, tmp_path: Path) -> None:
        """Unchanged files preserve their existing hash from old manifest."""
        dest = tmp_path / "SD"
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
            "local_size": 6, "local_mtime": 1_700_000_000.0,
            "sd_size": 6, "sd_mtime": 1_700_000_050.0,
            "hash": "preserved_hash_value",
        }
        old_files: dict[str, FileRecord] = {"kits/kit.xml": old_entry}

        files = build_post_sync_manifest(plan, src_scan, dest, old_files, source_is_sd=False)

        assert files["kits/kit.xml"]["hash"] == "preserved_hash_value"

    def test_new_file_gets_hash(self, tmp_path: Path) -> None:
        """New file (no prior manifest entry) gets hash computed."""
        dest = tmp_path / "SD"
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
        plan = SyncPlan(
            files_to_copy=[(tmp_path / "DELUGE" / "KITS" / "New.XML", kit_file)],
        )
        old_files: dict[str, FileRecord] = {}

        files = build_post_sync_manifest(plan, src_scan, dest, old_files, source_is_sd=False)

        assert files["kits/new.xml"]["hash"] == expected_hash


# ============================================================================
# read_manifest / write_manifest
# ============================================================================


class TestReadWriteManifest:
    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        files = read_manifest(tmp_path / "nonexistent.json")
        assert files == {}

    def test_round_trip(self, tmp_path: Path) -> None:
        mf = tmp_path / "manifest.json"
        files: dict[str, FileRecord] = {
            "kits/mykit.xml": {
                "local_size": 1234, "local_mtime": 1712600000.0,
                "sd_size": 1234, "sd_mtime": 1712600050.0,
            },
        }
        ts = "2026-05-14T12:00:00+00:00"

        write_manifest(mf, files=files)
        read_files = read_manifest(mf)

        assert len(read_files) == 1
        assert read_files["kits/mykit.xml"]["local_size"] == 1234
        assert read_files["kits/mykit.xml"]["sd_mtime"] == 1712600050.0


# ============================================================================
# Manifest integration
# ============================================================================


class TestManifestIntegration:
    def test_manifest_prevents_unnecessary_recopies(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        deluge = tmp_path / "DELUGE"
        _touch(deluge / "KITS" / "Kit.XML", b"<kit/>", mtime=1_700_000_000.0)

        sd = tmp_path / "SD"
        sd.mkdir()

        manifest_path = tmp_path / "sync_manifest.json"
        _setup_env(monkeypatch, deluge, sd)

        with (
            patch("deluge_lib.cli_utils.load_dotenv"),
            patch("sync_to_sd.confirm_apply", return_value=True),
            patch("sync_to_sd.SYNC_MANIFEST_PATH", manifest_path),
            patch("deluge_lib.syncing.SYNC_LOG_PATH", tmp_path / "log.log"),
        ):
            main([])

        out1 = capsys.readouterr().out
        assert "Sync complete" in out1

        with (
            patch("deluge_lib.cli_utils.load_dotenv"),
            patch("sync_to_sd.SYNC_MANIFEST_PATH", manifest_path),
            patch("deluge_lib.syncing.SYNC_LOG_PATH", tmp_path / "log.log"),
        ):
            main(["--dry-run"])

        out2 = capsys.readouterr().out
        assert "Already up to date" in out2


# ============================================================================
# Abort
# ============================================================================


class TestAbort:
    def test_abort_no_changes(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        
        deluge = tmp_path / "DELUGE"
        _touch(deluge / "KITS" / "Kit.XML", b"<kit/>", mtime=1_700_000_000.0)

        sd = tmp_path / "SD"
        sd.mkdir()

        _setup_env(monkeypatch, deluge, sd)

        with (
            patch("deluge_lib.cli_utils.load_dotenv"),
            patch("sync_to_sd.confirm_apply", return_value=False),
        ):
            main([])

        out = capsys.readouterr().out
        assert "Aborted" in out
        assert not (sd / "KITS" / "Kit.XML").exists()


# ============================================================================
# Error handling
# ============================================================================


class TestErrorHandling:
    def test_copy_failure_exits_with_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        
        deluge = tmp_path / "DELUGE"
        _touch(deluge / "KITS" / "Kit.XML", b"<kit/>", mtime=1_700_000_000.0)

        sd = tmp_path / "SD"
        sd.mkdir()

        _setup_env(monkeypatch, deluge, sd)

        def failing_copy2(*args: object, **kwargs: object) -> None:
            
            raise OSError("Disk full")

        with (
            patch("deluge_lib.cli_utils.load_dotenv"),
            patch("sync_to_sd.confirm_apply", return_value=True),
            patch("sync_to_sd.shutil.copy2", side_effect=failing_copy2),
        ):
            with pytest.raises(SystemExit) as exc_info:
                main([])
            assert exc_info.value.code == 1

        out = capsys.readouterr().out
        assert "ERROR" in out

    def test_copy_failure_logs_partial_result(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        
        deluge = tmp_path / "DELUGE"
        _touch(deluge / "KITS" / "Kit.XML", b"<kit/>", mtime=1_700_000_000.0)

        sd = tmp_path / "SD"
        sd.mkdir()

        log_path = tmp_path / "to_sd_sync.log"
        _setup_env(monkeypatch, deluge, sd)

        def failing_copy2(*args: object, **kwargs: object) -> None:
            
            raise OSError("Disk full")

        with (
            patch("deluge_lib.cli_utils.load_dotenv"),
            patch("sync_to_sd.confirm_apply", return_value=True),
            patch("sync_to_sd.shutil.copy2", side_effect=failing_copy2),
            patch("deluge_lib.syncing.SYNC_LOG_PATH", log_path),
        ):
            with pytest.raises(SystemExit):
                main([])

        assert log_path.exists()
        assert "FAILED" in log_path.read_text()

    def test_missing_sd_card_exits(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        
        deluge = tmp_path / "DELUGE"
        deluge.mkdir()

        monkeypatch.setenv("DELUGE_ROOT", str(deluge))
        monkeypatch.setenv("SD_CARD_PATH", str(tmp_path / "nonexistent"))

        with patch("deluge_lib.cli_utils.load_dotenv"):
            with pytest.raises(SystemExit):
                main([])

    def test_missing_deluge_root_exits(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        
        sd = tmp_path / "SD"
        sd.mkdir()

        monkeypatch.setenv("DELUGE_ROOT", str(tmp_path / "nonexistent"))
        monkeypatch.setenv("SD_CARD_PATH", str(sd))

        with patch("deluge_lib.cli_utils.load_dotenv"):
            with pytest.raises(SystemExit):
                main([])

    def test_delete_failure_exits_with_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        
        deluge = tmp_path / "DELUGE"
        deluge.mkdir()

        sd = tmp_path / "SD"
        _touch(sd / "KITS" / "Old.XML", b"<old/>", mtime=1_600_000_000.0)

        _setup_env(monkeypatch, deluge, sd)

        # Patch unlink to fail during delete phase
        original_unlink = Path.unlink

        def failing_unlink(self: Path, *args: object, **kwargs: object) -> None:
            
            if self.name == "Old.XML" and "SD" in str(self):
                raise OSError("Permission denied")
            original_unlink(self, *args, **kwargs)

        with (
            patch("deluge_lib.cli_utils.load_dotenv"),
            patch("sync_to_sd.confirm_apply", return_value=True),
            patch.object(Path, "unlink", failing_unlink),
        ):
            with pytest.raises(SystemExit) as exc_info:
                main([])
            assert exc_info.value.code == 1

        out = capsys.readouterr().out
        assert "ERROR" in out
