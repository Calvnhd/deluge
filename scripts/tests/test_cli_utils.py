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


class TestConfirmApply:
    """Tests for confirm_apply()."""

    def test_returns_true_on_y(self) -> None:
        """Returns True when user types 'y'."""
        with patch("builtins.input", return_value="y"):
            assert confirm_apply("Apply changes?") is True

    def test_returns_false_on_other_input(self) -> None:
        """Returns False on any non-y input."""
        with patch("builtins.input", return_value="n"):
            assert confirm_apply("Apply changes?") is False
