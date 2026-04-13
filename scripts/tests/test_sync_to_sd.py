"""Tests for sync_to_sd.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from sync_to_sd import main

from tests.conftest import _touch


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
        assert "Already up to date." in out


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

    def test_sd_only_files_trashed_and_deleted(
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
        # Old file backed up to repo .trash/
        trash_dir = deluge / ".trash"
        assert trash_dir.is_dir()
        # Find the SD-timestamp folder
        sd_trash_dirs = [d for d in trash_dir.iterdir() if d.name.startswith("SD-")]
        assert len(sd_trash_dirs) == 1
        trash_copy = sd_trash_dirs[0] / "KITS" / "OldKit.XML"
        assert trash_copy.read_bytes() == b"<old/>"

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
            patch("sync_to_sd._TO_SD_LOG_PATH", log_path),
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
        assert "Aborted." in out
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
            patch("sync_to_sd._TO_SD_LOG_PATH", log_path),
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

    def test_trash_delete_failure_exits_with_error(
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

        # Patch unlink to fail after trash copy succeeds
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
