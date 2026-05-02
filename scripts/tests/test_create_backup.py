# Deluge CLI v0.1
"""Tests for create_backup.py."""

from __future__ import annotations

import zipfile
from pathlib import Path, PurePosixPath
from unittest.mock import patch

import pytest
from create_backup import main

from tests.conftest import _touch


def _setup_env(
    monkeypatch: pytest.MonkeyPatch,
    source: Path,
    dest: Path,
) -> None:
    # TODO-v0.1-REVIEW
    """Set environment variables and stub load_dotenv."""
    monkeypatch.setenv("ZIP_SOURCE_PATH", str(source))
    monkeypatch.setenv("ZIP_DEST_PATH", str(dest))


def _find_zip(dest: Path) -> Path:
    # TODO-v0.1-REVIEW
    """Return the single .zip file in dest."""
    zips = list(dest.glob("*.zip"))
    assert len(zips) == 1, f"Expected 1 zip, found {len(zips)}: {zips}"
    return zips[0]


# ============================================================================
# Dry run
# ============================================================================


class TestDryRun:
    def test_dry_run_prints_summary_without_creating_zip(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # TODO-v0.1-REVIEW
        source = tmp_path / "DELUGE"
        _touch(source / "KITS" / "kit.xml", b"<kit/>", mtime=1_700_000_000.0)
        _touch(source / "SAMPLES" / "kick.wav", b"audio", mtime=1_700_000_000.0)

        dest = tmp_path / "backups"
        dest.mkdir()

        _setup_env(monkeypatch, source, dest)

        with patch("deluge_lib.cli_utils.load_dotenv"):
            main(["--dry-run"])

        out = capsys.readouterr().out
        assert "Files:" in out
        assert "Dry run complete" in out
        assert list(dest.glob("*.zip")) == []


# ============================================================================
# Full backup
# ============================================================================


class TestFullBackup:
    def test_creates_zip_with_correct_contents(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # TODO-v0.1-REVIEW
        source = tmp_path / "DELUGE"
        _touch(source / "KITS" / "kit.xml", b"<kit/>", mtime=1_700_000_000.0)
        _touch(source / "SYNTHS" / "pad.xml", b"<synth/>", mtime=1_700_000_000.0)
        _touch(source / "SAMPLES" / "kick.wav", b"audio", mtime=1_700_000_000.0)

        dest = tmp_path / "backups"
        dest.mkdir()

        _setup_env(monkeypatch, source, dest)

        with patch("deluge_lib.cli_utils.load_dotenv"):
            main([])

        zip_path = _find_zip(dest)
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = set(zf.namelist())

        assert "KITS/kit.xml" in names
        assert "SYNTHS/pad.xml" in names
        assert "SAMPLES/kick.wav" in names
        assert len(names) == 3

        out = capsys.readouterr().out
        assert "Archive:" in out
        assert "OK" in out

    def test_zip_preserves_directory_structure(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # TODO-v0.1-REVIEW
        source = tmp_path / "DELUGE"
        _touch(source / "SAMPLES" / "DRUMS" / "kick.wav", b"kick", mtime=1_700_000_000.0)
        _touch(source / "SAMPLES" / "DRUMS" / "snare.wav", b"snare", mtime=1_700_000_000.0)
        _touch(source / "KITS" / "FACTORY" / "kit.xml", b"<k/>", mtime=1_700_000_000.0)

        dest = tmp_path / "backups"
        dest.mkdir()

        _setup_env(monkeypatch, source, dest)

        with patch("deluge_lib.cli_utils.load_dotenv"):
            main([])

        zip_path = _find_zip(dest)
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = set(zf.namelist())

        assert "SAMPLES/DRUMS/kick.wav" in names
        assert "SAMPLES/DRUMS/snare.wav" in names
        assert "KITS/FACTORY/kit.xml" in names

    def test_zip_uses_forward_slash_paths(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # TODO-v0.1-REVIEW
        source = tmp_path / "DELUGE"
        _touch(source / "SAMPLES" / "DRUMS" / "kick.wav", b"kick", mtime=1_700_000_000.0)

        dest = tmp_path / "backups"
        dest.mkdir()

        _setup_env(monkeypatch, source, dest)

        with patch("deluge_lib.cli_utils.load_dotenv"):
            main([])

        zip_path = _find_zip(dest)
        with zipfile.ZipFile(zip_path, "r") as zf:
            for name in zf.namelist():
                assert "\\" not in name
                assert name == str(PurePosixPath(name))


# ============================================================================
# .trash exclusion
# ============================================================================


class TestTrashExclusion:
    def test_trash_contents_excluded_from_zip(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # TODO-v0.1-REVIEW
        source = tmp_path / "DELUGE"
        _touch(source / "KITS" / "kit.xml", b"<kit/>", mtime=1_700_000_000.0)
        _touch(source / ".trash" / "old.xml", b"<old/>", mtime=1_600_000_000.0)
        _touch(source / "SAMPLES" / ".trash" / "stale.wav", b"gone", mtime=1_600_000_000.0)

        dest = tmp_path / "backups"
        dest.mkdir()

        _setup_env(monkeypatch, source, dest)

        with patch("deluge_lib.cli_utils.load_dotenv"):
            main([])

        zip_path = _find_zip(dest)
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = set(zf.namelist())

        assert "KITS/kit.xml" in names
        assert not any(".trash" in n.lower() for n in names)


# ============================================================================
# Missing env vars
# ============================================================================


class TestMissingEnvVars:
    def test_missing_zip_source_path_raises_system_exit(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # TODO-v0.1-REVIEW
        dest = tmp_path / "backups"
        dest.mkdir()
        monkeypatch.setenv("ZIP_DEST_PATH", str(dest))
        monkeypatch.delenv("ZIP_SOURCE_PATH", raising=False)

        with patch("deluge_lib.cli_utils.load_dotenv"), pytest.raises(SystemExit):
            main([])

    def test_missing_zip_dest_path_raises_system_exit(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # TODO-v0.1-REVIEW
        source = tmp_path / "DELUGE"
        source.mkdir()
        monkeypatch.setenv("ZIP_SOURCE_PATH", str(source))
        monkeypatch.delenv("ZIP_DEST_PATH", raising=False)

        with patch("deluge_lib.cli_utils.load_dotenv"), pytest.raises(SystemExit):
            main([])
