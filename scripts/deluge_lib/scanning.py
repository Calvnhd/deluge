# Deluge CLI v0.1
"""Generic filtered file scanner with stat capture.

Accepts any root directory and returns a case-normalised path dict.
Only .xml and .wav files are yielded; .trash directories are silently
skipped.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Literal

def normalise_key(path: str | Path) -> str:
    """Convert *path* to a normalised lookup key: lowercase with forward slashes.

    Used for case-insensitive dict matching and cross-platform portability. 
    """
    return str(PurePosixPath(path)).lower()


def print_path(path: str | Path) -> str:
    """Cosmetic consistency. Use forward slashes and preserve case."""
    return str(PurePosixPath(path))


def normalise_mtime(raw_mtime: float) -> float:
    """Truncate a timestamp to FAT32's 2-second resolution."""
    return 2.0 * (raw_mtime // 2.0)

# File extensions to find while scanning
FileFilter = Literal["wav", "xml", "both"]

# Mapping extensions from FileFilter literals to frozensets
FILTER_MAP: dict[str, frozenset[str]] = {
    "wav": frozenset({".wav"}),
    "xml": frozenset({".xml"}),
    "both": frozenset({".xml", ".wav"}),
}

# Directory names to skip (case-insensitive)
SKIP_DIRS: frozenset[str] = frozenset({".trash"})


def format_size(size_bytes: int) -> str:
    """Format a byte count as a human-readable string"""
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


@dataclass(frozen=True)
class FileEntry:
    """Status data for a single scanned file"""

    rel_path: Path
    size: int
    mtime: float


@dataclass
class ScanResult:
    """Result of scanning a directory tree"""

    files: dict[str, FileEntry] = field(default_factory=dict)


def scan_tree(
    root: Path,
    *,
    label: str = "source",
    file_filter: FileFilter = "both",
) -> ScanResult:
    """Walk *root* and collect filtered file entries

    Args:
        root: Directory to scan
        label: Human-readable name shown in progress messages
        file_filter: File types to include: `"wav"`, `"xml"`, or `"both"` (default)

    Returns:
        The computed ScanResult
    """
    allowed = FILTER_MAP[file_filter]
    result = ScanResult()
    file_count = 0

    print(f"Scanning {label}...", end="", flush=True)

    for dirpath, dirnames, filenames in os.walk(root):
        current_dir = Path(dirpath)

        # Prune skipped directories in-place so os.walk does not descend.
        dirnames[:] = [d for d in dirnames if d.lower() not in SKIP_DIRS]

        for fname in filenames:
            file_path = current_dir / fname

            ext = file_path.suffix.lower()
            if ext not in allowed:
                continue

            try:
                st = file_path.stat()
            except OSError as exc:
                rel = file_path.relative_to(root)
                print(f"\nWarning: cannot stat {rel}: {exc}")
                continue

            rel = file_path.relative_to(root)
            key = normalise_key(rel)
            entry = FileEntry(rel_path=rel, size=st.st_size, mtime=normalise_mtime(st.st_mtime))
            result.files[key] = entry

            file_count += 1
            print(f"\rScanning {label}... {file_count} files", end="", flush=True)

    print(f"\rScanning {label}... {file_count} files found")

    return result
