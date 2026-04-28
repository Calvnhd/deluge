# Deluge CLI v0.1
"""Shared test helpers."""

from __future__ import annotations

import os
from pathlib import Path


def _touch(path: Path, content: bytes = b"x", mtime: float | None = None) -> None:
    # TODO-v0.1-REVIEW
    """Create a tiny file with optional content and mtime."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
