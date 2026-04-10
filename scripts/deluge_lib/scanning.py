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

FileFilter = Literal["wav", "xml", "both"]


def normalise_key(path: str | Path) -> str:
    """Convert *path* to a normalised lookup key: lowercase with forward slashes.

    Used for case-insensitive dict matching and cross-platform manifest
    portability.  Works on both ``str`` and ``Path`` inputs.
    """
    return str(PurePosixPath(path)).lower()


def normalise_mtime(raw_mtime: float) -> float:
    """Truncate a timestamp to FAT32's 2-second resolution.

    FAT32 stores modification times with 2-second granularity (the seconds
    field is divided by 2 and truncated).  This function maps any timestamp
    onto that same grid so that values from FAT32 sources, NTFS sources,
    and manifest files are directly comparable.
    """
    return 2.0 * (raw_mtime // 2.0)


# Mapping from FileFilter literals to extension frozensets.
_FILTER_MAP: dict[str, frozenset[str]] = {
    "wav": frozenset({".wav"}),
    "xml": frozenset({".xml"}),
    "both": frozenset({".xml", ".wav"}),
}

# Directory names to skip entirely (case-insensitive).
_SKIP_DIRS: frozenset[str] = frozenset({".trash"})


@dataclass(frozen=True)
class FileEntry:
    """Stat data for a single scanned file."""

    rel_path: Path
    size: int
    mtime: float


@dataclass
class ScanResult:
    """Result of scanning a directory tree.

    Attributes:
        files: Mapping of normalised key (lowercase, forward-slash) to
            ``FileEntry`` containing the actual relative path, size, and mtime.
    """

    files: dict[str, FileEntry] = field(default_factory=dict)


def scan_tree(
    root: Path,
    *,
    label: str = "source",
    file_filter: FileFilter = "both",
) -> ScanResult:
    """Walk *root* and collect filtered file entries.

    Parameters
    ----------
    root:
        Any directory to scan.  Does not need to be an SD card.
    label:
        Human-readable name shown in progress messages (e.g. ``"source"``,
        ``"destination"``).
    file_filter:
        Which file types to include: ``"wav"``, ``"xml"``, or ``"both"``
        (the default).

    Returns
    -------
    ScanResult
        A dataclass containing:
        - ``files``: dict mapping normalised keys to ``FileEntry`` objects.
    """
    allowed = _FILTER_MAP[file_filter]
    result = ScanResult()
    file_count = 0

    print(f"Scanning {label}...", end="", flush=True)

    for dirpath, dirnames, filenames in os.walk(root):
        current_dir = Path(dirpath)

        # Prune skipped directories in-place so os.walk does not descend.
        dirnames[:] = [d for d in dirnames if d.lower() not in _SKIP_DIRS]

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

    print(f"\rScanning {label}... {file_count} files found.")

    return result
