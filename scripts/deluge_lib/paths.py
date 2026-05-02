# Deluge CLI v0.1
"""Centralized path constants for script-generated data."""

from __future__ import annotations

from pathlib import Path

# Root of the scripts/ directory.
SCRIPTS_DIR = Path(__file__).resolve().parent.parent

# Data directory and subdirectories.
DATA_DIR = SCRIPTS_DIR / "data"
SNAPSHOTS_DIR = DATA_DIR / "snapshots"
LOGS_DIR = DATA_DIR / "logs"

# Individual file paths.
MANIFEST_PATH = DATA_DIR / "manifest.json"
SYNC_LOG_PATH = LOGS_DIR / "sync.log"
CLOUD_SYNC_LOG_PATH = LOGS_DIR / "cloud_sync.log"
TO_SD_SYNC_LOG_PATH = LOGS_DIR / "to_sd_sync.log"
