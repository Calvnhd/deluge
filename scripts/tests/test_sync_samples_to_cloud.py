# Deluge CLI v0.1
"""Tests for sync_samples_to_cloud.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from sync_samples_to_cloud import main

from tests.conftest import _touch


def _setup_env(
    monkeypatch: pytest.MonkeyPatch,
    deluge_root: Path,
    cloud_path: Path,
) -> None:
    # TODO-v0.1-REVIEW
    """Set environment variables and stub load_dotenv."""
    monkeypatch.setenv("DELUGE_ROOT", str(deluge_root))
    monkeypatch.setenv("CLOUD_BACKUP_PATH", str(cloud_path))


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
        # TODO-v0.1-REVIEW
        deluge = tmp_path / "DELUGE"
        samples = deluge / "SAMPLES"
        _touch(samples / "kick.wav", b"audio", mtime=1_700_000_000.0)

        dest = tmp_path / "cloud"
        dest.mkdir()

        _setup_env(monkeypatch, deluge, dest)

        with patch("deluge_lib.cli_utils.load_dotenv"):
            main(["--dry-run"])

        out = capsys.readouterr().out
        assert "kick.wav" in out
        assert "Dry run complete." in out
        # Nothing copied
        assert not (dest / "kick.wav").exists()


# ============================================================================
# Full sync
# ============================================================================


class TestFullSync:
    def test_copies_wav_files_preserving_structure(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # TODO-v0.1-REVIEW
        deluge = tmp_path / "DELUGE"
        samples = deluge / "SAMPLES"
        _touch(samples / "DRUMS" / "kick.wav", b"kick", mtime=1_700_000_000.0)
        _touch(samples / "DRUMS" / "snare.wav", b"snare", mtime=1_700_000_000.0)

        dest = tmp_path / "cloud"
        dest.mkdir()

        _setup_env(monkeypatch, deluge, dest)

        with (
            patch("deluge_lib.cli_utils.load_dotenv"),
            patch("sync_samples_to_cloud.confirm_apply", return_value=True),
        ):
            main([])

        assert (dest / "DRUMS" / "kick.wav").read_bytes() == b"kick"
        assert (dest / "DRUMS" / "snare.wav").read_bytes() == b"snare"
        out = capsys.readouterr().out
        assert "Sync complete" in out

    def test_stale_wav_files_deleted(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # TODO-v0.1-REVIEW
        deluge = tmp_path / "DELUGE"
        samples = deluge / "SAMPLES"
        _touch(samples / "kick.wav", b"kick", mtime=1_700_000_000.0)

        dest = tmp_path / "cloud"
        _touch(dest / "kick.wav", b"kick", mtime=1_700_000_000.0)
        _touch(dest / "old.wav", b"gone", mtime=1_600_000_000.0)

        _setup_env(monkeypatch, deluge, dest)

        with (
            patch("deluge_lib.cli_utils.load_dotenv"),
            patch("sync_samples_to_cloud.confirm_apply", return_value=True),
        ):
            main([])

        assert (dest / "kick.wav").exists()
        assert not (dest / "old.wav").exists()


# ============================================================================
# Non-WAV handling
# ============================================================================


class TestNonWavHandling:
    def test_non_wav_in_source_ignored(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # TODO-v0.1-REVIEW
        deluge = tmp_path / "DELUGE"
        samples = deluge / "SAMPLES"
        _touch(samples / "kick.wav", b"kick", mtime=1_700_000_000.0)
        _touch(samples / "preset.xml", b"<xml/>", mtime=1_700_000_000.0)

        dest = tmp_path / "cloud"
        dest.mkdir()

        _setup_env(monkeypatch, deluge, dest)

        with (
            patch("deluge_lib.cli_utils.load_dotenv"),
            patch("sync_samples_to_cloud.confirm_apply", return_value=True),
        ):
            main([])

        assert (dest / "kick.wav").exists()
        assert not (dest / "preset.xml").exists()

    def test_non_wav_at_destination_untouched(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # TODO-v0.1-REVIEW
        deluge = tmp_path / "DELUGE"
        samples = deluge / "SAMPLES"
        _touch(samples / "kick.wav", b"kick", mtime=1_700_000_000.0)

        dest = tmp_path / "cloud"
        _touch(dest / "kick.wav", b"kick", mtime=1_700_000_000.0)
        _touch(dest / "notes.txt", b"my notes")

        _setup_env(monkeypatch, deluge, dest)

        with (
            patch("deluge_lib.cli_utils.load_dotenv"),
            patch("sync_samples_to_cloud.confirm_apply", return_value=True),
        ):
            main([])

        assert (dest / "notes.txt").read_bytes() == b"my notes"


# ============================================================================
# Empty directory cleanup
# ============================================================================


class TestEmptyDirCleanup:
    def test_empty_parent_removed_after_delete(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # TODO-v0.1-REVIEW
        deluge = tmp_path / "DELUGE"
        samples = deluge / "SAMPLES"
        samples.mkdir(parents=True)

        dest = tmp_path / "cloud"
        _touch(dest / "OLD" / "stale.wav", b"stale", mtime=1_600_000_000.0)

        _setup_env(monkeypatch, deluge, dest)

        with (
            patch("deluge_lib.cli_utils.load_dotenv"),
            patch("sync_samples_to_cloud.confirm_apply", return_value=True),
        ):
            main([])

        assert not (dest / "OLD" / "stale.wav").exists()
        assert not (dest / "OLD").exists()


# ============================================================================
# Already up to date
# ============================================================================


class TestAlreadyUpToDate:
    def test_no_changes_prints_up_to_date(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # TODO-v0.1-REVIEW
        deluge = tmp_path / "DELUGE"
        samples = deluge / "SAMPLES"
        _touch(samples / "kick.wav", b"kick", mtime=1_700_000_000.0)

        dest = tmp_path / "cloud"
        _touch(dest / "kick.wav", b"kick", mtime=1_700_000_000.0)

        _setup_env(monkeypatch, deluge, dest)

        with patch("deluge_lib.cli_utils.load_dotenv"):
            main(["--dry-run"])

        out = capsys.readouterr().out
        assert "Already up to date" in out


# ============================================================================
# Error handling
# ============================================================================


class TestErrorHandling:
    def test_missing_source_dir_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # TODO-v0.1-REVIEW
        deluge = tmp_path / "DELUGE"
        deluge.mkdir()
        # SAMPLES/ does not exist

        dest = tmp_path / "cloud"
        dest.mkdir()

        _setup_env(monkeypatch, deluge, dest)

        with (
            patch("deluge_lib.cli_utils.load_dotenv"),
            pytest.raises(SystemExit, match="Source directory does not exist"),
        ):
            main([])
