"""Environment and output utilities for Deluge scripts."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent

def get_deluge_root() -> Path:
    """Load DELUGE_ROOT from scripts/.env.

    Raises SystemExit if DELUGE_ROOT is not set or the directory does not exist.
    """
    load_dotenv(_SCRIPTS_DIR / ".env")

    env_value = os.environ.get("DELUGE_ROOT")
    if not env_value:
        raise SystemExit(
            "DELUGE_ROOT is not set. Set it in scripts/.env"
        )

    root = Path(env_value).resolve()
    if not root.is_dir():
        raise SystemExit(f"DELUGE_ROOT directory does not exist: {root}")

    return root


def get_sd_card_path() -> Path:
    """Load SD_CARD_PATH from scripts/.env.

    Raises SystemExit if SD_CARD_PATH is not set or the path does not exist
    """
    load_dotenv(_SCRIPTS_DIR / ".env")

    env_value = os.environ.get("SD_CARD_PATH")
    if not env_value:
        raise SystemExit(
            "SD_CARD_PATH is not set. Set it in scripts/.env"
        )

    path = Path(env_value).resolve()
    if not path.is_dir():
        raise SystemExit(
            f"SD card not found at {path}\n"
            "Make sure the SD card is mounted and SD_CARD_PATH is correct."
        )

    return path


def confirm_apply(message: str) -> bool:
    """Print message and prompt user for confirmation.

    Returns True if user enters 'y' or 'Y', False otherwise.
    Default is No (empty input returns False).
    """
    print(message)
    response = input("[y/N] ").strip().lower()
    return response == "y"
