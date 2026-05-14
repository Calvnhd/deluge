# Deluge CLI v0.1
"""Shared sync primitives used by sync scripts.

Contains dataclasses, comparison logic, plan computation, plan display,
plan execution, and logging utilities extracted from ``sync_from_sd.py``
so that multiple sync scripts can share them.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TypedDict

from deluge_lib.scanning import FileEntry, FileFilter, ScanResult, print_path, normalise_mtime, scan_tree


class _FileRecordRequired(TypedDict):
    """Required fields for a manifest entry."""

    sd_size: int
    sd_mtime: float
    local_size: int
    local_mtime: float


class FileRecord(_FileRecordRequired, total=False):
    """Per-file dual-stat manifest entry with optional content hash.

    The ``hash`` field holds a SHA-256 hex digest or is absent/None when
    the hash has not yet been computed (v1 manifests, newly added entries).
    """

    hash: str | None


FilesDict = dict[str, FileRecord]


def read_manifest(path: Path) -> tuple[str, FilesDict]:
    """Read a JSON manifest file (v1 or v2).

    v2 manifests have a top-level ``"version": 2`` field and per-entry
    ``"hash"`` values.  v1 manifests (no version field) are migrated
    transparently: stat fields are preserved and ``hash`` is set to
    ``None``.
    """

    if not path.is_file():
        print(f"Warning: No manifest at {path}")
        return ("", {})

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Warning: corrupt manifest at {path} ({exc}) \u2014 treating as empty")
        return ("", {})

    timestamp = str(data.get("last_sync_timestamp", ""))
    version = data.get("version", 1)

    files: dict[str, FileRecord] = {}
    for key, val in data.get("files", {}).items():
        if isinstance(val, dict) and "sd_size" in val and "sd_mtime" in val and "local_size" in val and "local_mtime" in val:
            entry: FileRecord = {
                "sd_size": int(val["sd_size"]),
                "sd_mtime": float(val["sd_mtime"]),
                "local_size": int(val["local_size"]),
                "local_mtime": float(val["local_mtime"]),
                "hash": val.get("hash") if version >= 2 else None,
            }
            files[key] = entry

    return (timestamp, files)


def write_manifest(
    path: Path,
    *,
    timestamp: str,
    files: FilesDict,
) -> None:
    """Atomically write a v2 manifest JSON file.

    The output includes ``"version": 2`` at the top level and each file
    entry includes a ``"hash"`` key (value is a hex string or ``null``).
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    # Ensure every entry has an explicit "hash" key for v2 format
    v2_files: dict[str, dict] = {}
    for key, rec in files.items():
        v2_files[key] = {
            "sd_size": rec["sd_size"],
            "sd_mtime": rec["sd_mtime"],
            "local_size": rec["local_size"],
            "local_mtime": rec["local_mtime"],
            "hash": rec.get("hash"),
        }

    payload = {
        "version": 2,
        "last_sync_timestamp": timestamp,
        "files": v2_files,
    }
    blob = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"

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


_MTIME_TOLERANCE_S = 2.0
_TRASH_DIR_NAME = ".trash"


def _stat_cache_valid(
    entry: FileEntry,
    manifest_size: int,
    manifest_mtime: float,
) -> bool:
    """Return True when a file's current stat matches the manifest entry.

    When this returns True the cached hash in the manifest can be trusted
    without re-reading the file (the stat-cache fast path).

    Returns False (forcing a re-hash) when:
    - size differs
    - mtime differs
    - mtime is 0 or negative (unreliable FAT32 null timestamps)
    """
    if entry.mtime <= 0:
        return False
    return entry.size == manifest_size and entry.mtime == manifest_mtime


@dataclass
class SyncPlan:
    """Holds the list of planned sync actions."""

    files_to_copy: list[tuple[Path, Path]] = field(default_factory=list)
    files_to_delete: list[Path] = field(default_factory=list)
    files_unchanged: int = 0


class SyncError(Exception):
    """Raised when a sync operation fails mid-execution.

    Carries context about the failure: which file, what went wrong,
    how many operations completed, and how many were left.
    """

    def __init__(
        self,
        message: str,
        *,
        file: str,
        copied: int = 0,
        trashed: int = 0,
        unchanged: int = 0,
        remaining: int = 0,
    ) -> None:
        super().__init__(message)
        self.file = file
        self.copied = copied
        self.trashed = trashed
        self.unchanged = unchanged
        self.remaining = remaining


@dataclass
class SyncResult:
    """Number of files copied, trashed, and unchanged after sync"""

    copied: int = 0
    trashed: int = 0
    unchanged: int = 0


def _mtime_matches(mtime_a: float, mtime_b: float) -> bool:
    """Return True if two mtimes are equal within FAT32 tolerance.

    FAT32 has 2-second mtime resolution, so mtimes within ±2 seconds
    are treated as equal.
    """
    return abs(mtime_a - mtime_b) <= _MTIME_TOLERANCE_S


def compute_sync(
    source: Path,
    dest: Path,
    *,
    manifest: FilesDict | None = None,
    source_is_sd: bool = True,
    file_filter: FileFilter = "both",
) -> tuple[SyncPlan, ScanResult]:
    """Walk both trees to build a plan of copy/delete actions for altering
    the destination directory such that it becomes identical to source.

    When a manifest is provided and entries contain a non-null ``hash``,
    the comparison uses a stat-cache fast path: if size+mtime match the
    manifest on both sides the cached hash is trusted (no file I/O).
    On a stat-cache miss the file is hashed and compared to the manifest
    hash.  Entries with a null hash fall back to mtime-based comparison.

    The manifest dict may be mutated in place when stat-cache misses are
    resolved (updated stats + newly computed hashes).

    Args:
        source: Source directory to sync with
        dest: Destination to sync
        manifest: Optional manifest dict used during SD syncs. Maps normalised 
            keys to status data for both SD and local sides
        source_is_sd: When True (default), source is the SD card and dest is the
            local directory.  When False, source is local and dest is SD.
            Controls which manifest fields are compared against source vs dest.
        file_filter: File types to include: "wav", "xml", or
            "both" (default).  Forwarded to scan_tree().

    Returns:
        The sync plan and the source scan result.
    """
    from deluge_lib.deluge_sdk import hash_file

    plan = SyncPlan()

    # --- scan source and dest
    src_scan = scan_tree(source, label="source", file_filter=file_filter)
    dst_scan = scan_tree(dest, label="destination", file_filter=file_filter)

    # --- compare source → dest, file by file ---
    for key, src_entry in src_scan.files.items():
        src_path = source / src_entry.rel_path
        dst_path = dest / src_entry.rel_path

        # File is in source but not dest: copy
        if key not in dst_scan.files:
            plan.files_to_copy.append((src_path, dst_path))
            continue

        dst_entry = dst_scan.files[key]

        # Deluge firmware does not record file creation time, and FAT32/NTFS record mtime differently
        # The manifest lets us check changes on both source and destination for an accurate sync
        if manifest is not None and key in manifest:
            manifest_entry = manifest[key]
            # Compare each side against its own manifest baseline.
            # SD side always uses tolerance (FAT32 quirks, Deluge firmware
            # doesn't reliably write timestamps).
            # Local side uses exact equality (NTFS/APFS timestamps are reliable).
            if source_is_sd:
                sd_entry, local_entry = src_entry, dst_entry
                local_path = dst_path
            else:
                sd_entry, local_entry = dst_entry, src_entry
                local_path = src_path

            sd_changed = (
                sd_entry.size != manifest_entry["sd_size"]
                or not _mtime_matches(sd_entry.mtime, manifest_entry["sd_mtime"])
            )

            if sd_changed:
                # SD changed — always copy (SD is source of truth)
                plan.files_to_copy.append((src_path, dst_path))
                continue

            # SD unchanged — check local side
            local_stat_matches = _stat_cache_valid(
                local_entry,
                manifest_entry["local_size"],
                manifest_entry["local_mtime"],
            )

            if local_stat_matches:
                # Stat-cache hit: both sides match manifest → unchanged
                plan.files_unchanged += 1
            else:
                # Stat-cache miss on local side — use hash if available
                cached_hash = manifest_entry.get("hash")
                if cached_hash is not None:
                    local_hash = hash_file(local_path)
                    if local_hash == cached_hash:
                        # Content unchanged — mtime drift only. Update
                        # manifest local stats so next run hits the fast path.
                        manifest_entry["local_size"] = local_entry.size
                        manifest_entry["local_mtime"] = local_entry.mtime
                        plan.files_unchanged += 1
                    else:
                        # Content genuinely changed — copy from source
                        plan.files_to_copy.append((src_path, dst_path))
                else:
                    # No hash in manifest (v1 migration) — hash the local
                    # file and store for future runs, then fall back to
                    # mtime-based decision (copy, since local stat changed).
                    local_hash = hash_file(local_path)
                    manifest_entry["hash"] = local_hash
                    manifest_entry["local_size"] = local_entry.size
                    manifest_entry["local_mtime"] = local_entry.mtime
                    plan.files_to_copy.append((src_path, dst_path))
        else:
            # No manifest entry — fall back to direct source vs dest comparison.
            if src_entry.size != dst_entry.size:
                plan.files_to_copy.append((src_path, dst_path))
            elif not _mtime_matches(src_entry.mtime, normalise_mtime(dst_entry.mtime)):
                plan.files_to_copy.append((src_path, dst_path))
            else:
                plan.files_unchanged += 1

    # File in dest but not source: delete
    for key, dst_entry in dst_scan.files.items():
        if key not in src_scan.files:
            plan.files_to_delete.append(dest / dst_entry.rel_path)

    return plan, src_scan


def print_plan(plan: SyncPlan, *, dest: Path, delete_label: str = "trash") -> None:
    """Print a human-readable summary of what the sync would do.

    Args:
        plan: The computed sync plan.
        dest: Destination root, used to display relative paths.
        delete_label: Verb printed for files to be removed (e.g. "trash" or
            "delete").
    """
    for _src, dst in plan.files_to_copy:
        rel = dst.relative_to(dest)
        if dst.exists():
            print(f"  update  {print_path(rel)}")
        else:
            print(f"  copy    {print_path(rel)}")

    for path in plan.files_to_delete:
        print(f"  {delete_label:<8}{print_path(path.relative_to(dest))}")

    print()
    print(
        f"  {len(plan.files_to_copy)} to copy, "
        f"{len(plan.files_to_delete)} to {delete_label}, "
        f"{plan.files_unchanged} unchanged"
    )


def execute_plan(
    plan: SyncPlan,
    *,
    dest: Path,
    delete_mode: str = "trash",
) -> SyncResult:
    """Execute the sync plan: copy and remove files.

    Args:
        plan: The computed sync plan.
        dest: Destination root directory.
        delete_mode: How to handle files marked for deletion:

            - "trash" (default): move to a timestamped .trash/
              subdirectory inside `dest`.
            - "delete": hard-delete and clean up empty ancestor directories
              up to `dest`.

    Returns:
        Counts of copied, trashed/deleted, and unchanged files.

    Raises:
        SyncError: On any copy or delete failure, with context about completed
            and remaining operations.
    """
    copied = 0
    total_copy = len(plan.files_to_copy)

    # --- copies ---
    try:
        for i, (src, dst) in enumerate(plan.files_to_copy, 1):
            print(f"\rCopying... {i}/{total_copy}", end="", flush=True)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied += 1
    except OSError as exc:
        if total_copy:
            print()
        remaining = total_copy - copied - 1
        raise SyncError(
            str(exc),
            file=str(src),
            copied=copied,
            unchanged=plan.files_unchanged,
            remaining=remaining,
        ) from exc
    if total_copy:
        print()

    # --- remove extras ---
    trashed = 0
    trash_count = len(plan.files_to_delete)
    if trash_count and delete_mode == "trash":
        print(f"Trashing {trash_count} files...")
        trash_base = dest / _TRASH_DIR_NAME / datetime.now().strftime("%Y%m%d_%H%M%S")
        try:
            for path in plan.files_to_delete:
                rel = path.relative_to(dest)
                trash_dest = trash_base / rel
                trash_dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), str(trash_dest))
                trashed += 1
        except OSError as exc:
            raise SyncError(
                str(exc),
                file=str(path),
                copied=copied,
                trashed=trashed,
                unchanged=plan.files_unchanged,
                remaining=trash_count - trashed - 1,
            ) from exc
    elif trash_count and delete_mode == "delete":
        print(f"Deleting {trash_count} files...")
        try:
            for path in plan.files_to_delete:
                path.unlink()
                trashed += 1
                # Clean up empty ancestor directories up to dest
                parent = path.parent
                while parent != dest:
                    try:
                        parent.rmdir()  # only succeeds if empty
                    except OSError:
                        break
                    parent = parent.parent
        except OSError as exc:
            raise SyncError(
                str(exc),
                file=str(path),
                copied=copied,
                trashed=trashed,
                unchanged=plan.files_unchanged,
                remaining=trash_count - trashed - 1,
            ) from exc

    return SyncResult(
        copied=copied,
        trashed=trashed,
        unchanged=plan.files_unchanged,
    )


def append_sync_log(
    result: SyncResult,
    *,
    elapsed_seconds: float,
    error: str | None = None,
    log_path: Path | None = None,
) -> None:
    """Append a structured entry to the sync execution log."""

    # default to "From SD" log if none is specified
    if log_path is None:
        from deluge_lib.paths import FROM_SD_SYNC_LOG_PATH
        log_path = FROM_SD_SYNC_LOG_PATH

    log_path.parent.mkdir(parents=True, exist_ok=True)
    status = "FAILED" if error else "SUCCESS"
    elapsed_m = int(elapsed_seconds) // 60
    elapsed_s = int(elapsed_seconds) % 60
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    line = (
        f"{timestamp} {status}"
        f" copied={result.copied}"
        f" trashed={result.trashed}"
        f" unchanged={result.unchanged}"
        f" elapsed={elapsed_m}m {elapsed_s}s"
    )
    if error:
        line += f' error="{error}"'

    with log_path.open("a") as f:
        f.write(line + "\n")


def report_empty_dirs(dest: Path) -> None:
    """Print any empty subdirectories of *dest*.

    Bottom-up walk, skips .trash/.
    """
    from deluge_lib.scanning import _SKIP_DIRS, print_path

    empties: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(dest, topdown=False):
        dirnames[:] = [d for d in dirnames if d.lower() not in _SKIP_DIRS]
        current = Path(dirpath)
        if current == dest:
            continue
        # Empty if no files and all subdirs were already flagged as empty.
        if not filenames and all((current / d) in empties for d in dirnames):
            empties.append(current)

    if empties:
        print(f"\nFound {len(empties)} empty director{'y' if len(empties) == 1 else 'ies'} in {dest}:")
        for p in empties:
            print(f"  {print_path(p.relative_to(dest))}")
