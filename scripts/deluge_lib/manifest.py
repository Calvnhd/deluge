"""Shared manifest read/write/update module.

The manifest is a JSON file that persists sync state (file size + mtime)
across runs, solving the fresh-clone problem where git destroys mtimes.
Designed as a shared "file inventory" — sync writes it, other scripts
can read it to inspect what files exist and their stats.

"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_MANIFEST_VERSION = "1.0"

# Default manifest location relative to the scripts directory.
_DEFAULT_MANIFEST_REL = Path("data") / "manifest.json"


# -- Types -------------------------------------------------------------------

# Per-file entry: at minimum {size: int, mtime: float}.  
# Extensible — unknown fields are preserved on read/update, never stripped.
FileRecord = dict[str, Any]

# Files dict: normalised key → FileRecord.
FilesDict = dict[str, FileRecord]


@dataclass
class ManifestData:
    """In-memory representation of a manifest file.

    Attributes:
        version: Schema version string.
        last_sync_timestamp: ISO 8601 timestamp of the last sync, or empty
            string if no sync has been recorded.
        last_sync_direction: ``"sd-to-local"`` or ``"local-to-sd"``, or empty
            string if no sync has been recorded.
        file_count: Number of tracked files (metadata convenience field).
        files: Mapping of normalised path keys to per-file record dicts.
    """

    version: str = _MANIFEST_VERSION
    last_sync_timestamp: str = ""
    last_sync_direction: str = ""
    file_count: int = 0
    files: FilesDict = field(default_factory=dict)


# -- Public API --------------------------------------------------------------


def default_manifest_path() -> Path:
    """Return the default manifest path (``scripts/data/manifest.json``).

    The path is resolved relative to the ``scripts/`` directory (i.e. the
    parent of the ``deluge_lib`` package).
    """
    scripts_dir = Path(__file__).resolve().parent.parent
    return scripts_dir / _DEFAULT_MANIFEST_REL


def read_manifest(path: Path | None = None) -> ManifestData:
    """Read and parse a manifest file, returning empty state on failure.

    Parameters
    ----------
    path:
        Path to the manifest JSON file.  Defaults to
        :func:`default_manifest_path` when *None*.

    Returns
    -------
    ManifestData
        Parsed manifest, or an empty ``ManifestData`` if the file is
        missing or contains invalid JSON
    """
    if path is None:
        path = default_manifest_path()

    if not path.is_file():
        return ManifestData()

    try:
        raw = path.read_text(encoding="utf-8")
        data: dict[str, Any] = json.loads(raw)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Warning: corrupt manifest at {path} ({exc}) — treating as empty")
        return ManifestData()

    return _parse_manifest(data)


def write_manifest(
    data: ManifestData,
    path: Path | None = None,
) -> None:
    """Atomically write *data* to the manifest file.

    The write uses a temporary file in the same directory followed by an
    atomic rename (D11).  The ``scripts/data/`` directory is created
    automatically if missing.

    Parameters
    ----------
    data:
        The manifest data to persist.
    path:
        Destination file path.  Defaults to :func:`default_manifest_path`
        when *None*.
    """
    if path is None:
        path = default_manifest_path()

    path.parent.mkdir(parents=True, exist_ok=True)

    # Keep file_count consistent with the actual files dict.
    data.file_count = len(data.files)

    payload = _serialise_manifest(data)
    blob = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"

    # Atomic write: temp file in the same directory → rename.
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(path.parent),
        suffix=".tmp",
        delete=False,
    ) as fd:
        tmp_path = Path(fd.name)
        try:
            fd.write(blob)
            fd.flush()
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise
    try:
        tmp_path.replace(path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


# -- Internals ---------------------------------------------------------------


def _parse_manifest(data: dict[str, Any]) -> ManifestData:
    """Parse a raw JSON dict into a ``ManifestData`` instance.

    Unknown per-file fields are preserved (D30).
    """
    meta: dict[str, Any] = data.get("metadata", {})
    files_raw: dict[str, Any] = data.get("files", {})

    # Coerce files values to dicts (defensive).
    files: FilesDict = {}
    for key, val in files_raw.items():
        if isinstance(val, dict):
            files[key] = val

    return ManifestData(
        version=str(meta.get("version", _MANIFEST_VERSION)),
        last_sync_timestamp=str(meta.get("last_sync_timestamp", "")),
        last_sync_direction=str(meta.get("last_sync_direction", "")),
        file_count=int(meta.get("file_count", len(files))),
        files=files,
    )


def _serialise_manifest(data: ManifestData) -> dict[str, Any]:
    """Convert a ``ManifestData`` into a JSON-serialisable dict."""
    return {
        "metadata": {
            "version": data.version,
            "last_sync_timestamp": data.last_sync_timestamp,
            "last_sync_direction": data.last_sync_direction,
            "file_count": data.file_count,
        },
        "files": data.files,
    }


def make_timestamp() -> str:
    """Return the current UTC time as an ISO 8601 string (no microseconds)."""
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()
