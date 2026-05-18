# Deluge CLI v0.2
"""Centralized path constants for script-generated data."""

from __future__ import annotations

from pathlib import Path

# Root of the scripts/ directory.
SCRIPTS_DIR = Path(__file__).resolve().parent.parent

# Data directory and subdirectories.
DATA_DIR = SCRIPTS_DIR / "data"
LOGS_DIR = DATA_DIR / "logs"

# Individual file paths.
SYNC_MANIFEST_PATH = DATA_DIR / "sync_manifest.json"
SYNC_LOG_PATH = LOGS_DIR / "sync.log"
