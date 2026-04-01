"""Tests for lib/cli_utils.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from lib.cli_utils import confirm_apply, get_deluge_root


class TestGetDelugeRoot:
    """Tests for get_deluge_root()."""

    def test_loads_from_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """DELUGE_ROOT set in environment is used directly."""
        deluge_dir = tmp_path / "DELUGE"
        deluge_dir.mkdir()
        monkeypatch.setenv("DELUGE_ROOT", str(deluge_dir))
        with patch("lib.cli_utils.load_dotenv"):
            result = get_deluge_root()
        assert result == deluge_dir

    def test_fallback_when_unset(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Falls back to <repo_root>/DELUGE when DELUGE_ROOT is not set."""
        deluge_dir = tmp_path / "DELUGE"
        deluge_dir.mkdir()
        monkeypatch.delenv("DELUGE_ROOT", raising=False)
        monkeypatch.setattr("lib.cli_utils._REPO_ROOT", tmp_path)
        with patch("lib.cli_utils.load_dotenv"):
            result = get_deluge_root()
        assert result == deluge_dir

    def test_system_exit_on_missing_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Raises SystemExit when resolved directory doesn't exist."""
        monkeypatch.setenv("DELUGE_ROOT", str(tmp_path / "nonexistent"))
        with patch("lib.cli_utils.load_dotenv"), pytest.raises(SystemExit, match="does not exist"):
            get_deluge_root()

    def test_relative_path_resolved_against_repo_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Relative DELUGE_ROOT is resolved against repo root."""
        deluge_dir = tmp_path / "DELUGE"
        deluge_dir.mkdir()
        monkeypatch.setenv("DELUGE_ROOT", "./DELUGE")
        monkeypatch.setattr("lib.cli_utils._REPO_ROOT", tmp_path)
        with patch("lib.cli_utils.load_dotenv"):
            result = get_deluge_root()
        assert result == deluge_dir.resolve()

    def test_loads_env_from_scripts_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verifies load_dotenv is called with scripts/.env path."""
        deluge_dir = tmp_path / "DELUGE"
        deluge_dir.mkdir()
        monkeypatch.setenv("DELUGE_ROOT", str(deluge_dir))
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        monkeypatch.setattr("lib.cli_utils._SCRIPTS_DIR", scripts_dir)
        with patch("lib.cli_utils.load_dotenv") as mock_load:
            get_deluge_root()
        mock_load.assert_called_once_with(scripts_dir / ".env")


class TestConfirmApply:
    """Tests for confirm_apply()."""

    def test_returns_true_on_y(self) -> None:
        """Returns True when user types 'y'."""
        with patch("builtins.input", return_value="y"):
            assert confirm_apply("Apply changes?") is True

    def test_returns_true_on_uppercase_y(self) -> None:
        """Returns True when user types 'Y'."""
        with patch("builtins.input", return_value="Y"):
            assert confirm_apply("Apply changes?") is True

    def test_returns_false_on_n(self) -> None:
        """Returns False when user types 'n'."""
        with patch("builtins.input", return_value="n"):
            assert confirm_apply("Apply changes?") is False

    def test_returns_false_on_empty(self) -> None:
        """Returns False on empty input (default is No)."""
        with patch("builtins.input", return_value=""):
            assert confirm_apply("Apply changes?") is False

    def test_returns_false_on_other_input(self) -> None:
        """Returns False on any non-y input."""
        with patch("builtins.input", return_value="maybe"):
            assert confirm_apply("Apply changes?") is False

    def test_prints_message(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Prints the provided message before prompting."""
        with patch("builtins.input", return_value="n"):
            confirm_apply("Apply 5 changes to 3 files?")
        captured = capsys.readouterr()
        assert "Apply 5 changes to 3 files?" in captured.out
