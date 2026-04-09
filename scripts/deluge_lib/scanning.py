"""Generic filtered file scanner with stat capture.

Accepts any root directory and returns a case-normalised path dict.
Only .xml and .wav files are yielded; .trash directories and symlinks
are silently skipped.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath


def normalise_key(path: str | Path) -> str:
    """Convert *path* to a normalised lookup key: lowercase with forward slashes.

    Used for case-insensitive dict matching and cross-platform manifest
    portability.  Works on both ``str`` and ``Path`` inputs.
    """
    return str(PurePosixPath(path)).lower()


# Extensions to include (lowercased, with leading dot).
_ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".xml", ".wav"})

# Directory names to skip entirely (case-insensitive).
_SKIP_DIRS: frozenset[str] = frozenset({".trash"})

# Print a progress message every N files.
_PROGRESS_INTERVAL: int = 500


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


def scan_tree(root: Path, *, progress: bool = True, label: str = "source") -> ScanResult:
    """Walk *root* and collect filtered file entries.

    Parameters
    ----------
    root:
        Any directory to scan.  Does not need to be an SD card.
    progress:
        If ``True``, print scanning progress every 500 files.
    label:
        Human-readable name shown in progress messages (e.g. ``"source"``,
        ``"destination"``).

    Returns
    -------
    ScanResult
        A dataclass containing:
        - ``files``: dict mapping normalised keys to ``FileEntry`` objects.
    """
    result = ScanResult()
    file_count = 0

    if progress:
        print(f"Scanning {label}...", end="", flush=True)

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dir_path = Path(dirpath)

        # Prune skipped directories in-place so os.walk does not descend.
        dirnames[:] = [
            d
            for d in dirnames
            if d.lower() not in _SKIP_DIRS and not Path(dir_path / d).is_symlink()
        ]

        for fname in filenames:
            file_path = dir_path / fname

            # Skip symlinks silently.
            if file_path.is_symlink():
                continue

            ext = file_path.suffix.lower()
            if ext not in _ALLOWED_EXTENSIONS:
                continue

            try:
                st = file_path.stat()
            except OSError as exc:
                rel = file_path.relative_to(root)
                print(f"\nWarning: cannot stat {rel}: {exc}")
                continue

            rel = file_path.relative_to(root)
            key = normalise_key(rel)
            entry = FileEntry(rel_path=rel, size=st.st_size, mtime=st.st_mtime)
            result.files[key] = entry

            file_count += 1
            if progress and file_count % _PROGRESS_INTERVAL == 0:
                print(f"\rScanning {label}... {file_count} files", end="", flush=True)

    if progress:
        print(f"\rScanning {label}... {file_count} files found.")

    return result
