# Deluge CLI v0.1
"""Shared sync primitives used by sync scripts.

Contains dataclasses, comparison logic, plan computation, plan display,
plan execution, and logging utilities extracted from ``sync_from_sd.py``
so that multiple sync scripts can share them.
"""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from deluge_lib.scanning import FileFilter, ScanResult, print_path, normalise_key, normalise_mtime, scan_tree

if TYPE_CHECKING:
    from typing import TypedDict

    class _FileRecord(TypedDict):
        sd_size: int
        sd_mtime: float
        local_size: int
        local_mtime: float

    FilesDict = dict[str, _FileRecord]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MTIME_TOLERANCE_S = 2.0
_TRASH_DIR_NAME = ".trash"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


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
        # TODO-v0.1-REVIEW
        super().__init__(message)
        self.file = file
        self.copied = copied
        self.trashed = trashed
        self.unchanged = unchanged
        self.remaining = remaining


@dataclass
class SyncResult:
    # TODO-v0.1-REVIEW
    """Outcome of executing a sync plan — counts only."""

    copied: int = 0
    trashed: int = 0
    unchanged: int = 0


# ---------------------------------------------------------------------------
# Comparison helpers
# ---------------------------------------------------------------------------


def _mtime_matches(mtime_a: float, mtime_b: float) -> bool:
    """Return True if two mtimes are equal within FAT32 tolerance.

    FAT32 has 2-second mtime resolution, so mtimes within ±2 seconds
    are treated as equal.
    """
    return abs(mtime_a - mtime_b) <= _MTIME_TOLERANCE_S


# ---------------------------------------------------------------------------
# Plan computation
# ---------------------------------------------------------------------------


def compute_sync(
    source: Path,
    dest: Path,
    *,
    manifest: FilesDict | None = None,
    file_filter: FileFilter = "both",
) -> tuple[SyncPlan, ScanResult]:
    """Walk both trees and build a plan of copy/delete/rename actions.

    Parameters
    ----------
    source:
        Root of the SD card (or any source directory).
    dest:
        Root of the local ``DELUGE/`` directory.
    manifest:
        Optional manifest dict mapping normalised keys to dual-stat
        entries with ``sd_size``, ``sd_mtime``, ``local_size``, and
        ``local_mtime``.  When present, detects both SD-side changes
        (SD stats vs manifest) and local-side changes (local stats vs
        manifest).
    file_filter:
        Which file types to include: ``"wav"``, ``"xml"``, or ``"both"``
        (the default).  Forwarded to ``scan_tree()``.

    Returns
    -------
    tuple[SyncPlan, ScanResult]
        The sync plan and the source scan result (needed for manifest
        updates after execution).
    """
    plan = SyncPlan()

    # --- scan source (SD card) ---
    src_scan = scan_tree(source, label="source", file_filter=file_filter)

    # --- scan destination (DELUGE/) ---
    dst_scan = scan_tree(dest, label="destination", file_filter=file_filter)

    # --- compare source → dest (file-level) ---
    for key, src_entry in src_scan.files.items():
        src_path = source / src_entry.rel_path
        dst_path = dest / src_entry.rel_path

        if key not in dst_scan.files:
            # On SD, not in repo → copy
            plan.files_to_copy.append((src_path, dst_path))
            continue

        dst_entry = dst_scan.files[key]

        # Deluge firware does not record file creation time, and FAT32 vs NTFS have a bunch of conflicts
        # Dual-stat manifest check deals with this
        if manifest is not None and key in manifest:
            manifest_entry = manifest[key]
            sd_changed = (
                src_entry.size != manifest_entry["sd_size"]
                or not _mtime_matches(src_entry.mtime, manifest_entry["sd_mtime"])
            )
            local_changed = (
                dst_entry.size != manifest_entry["local_size"]
                or normalise_mtime(dst_entry.mtime) != manifest_entry["local_mtime"]
            )
            if sd_changed or local_changed:
                plan.files_to_copy.append((src_path, dst_path))
            else:
                plan.files_unchanged += 1
        else:
            # No manifest entry — fall back to direct SD vs local comparison.
            if src_entry.size != dst_entry.size:
                plan.files_to_copy.append((src_path, dst_path))
            elif not _mtime_matches(src_entry.mtime, normalise_mtime(dst_entry.mtime)):
                plan.files_to_copy.append((src_path, dst_path))
            else:
                plan.files_unchanged += 1

    # --- files in dest not on source → trash ---
    for key, dst_entry in dst_scan.files.items():
        if key not in src_scan.files:
            plan.files_to_delete.append(dest / dst_entry.rel_path)

    return plan, src_scan


# ---------------------------------------------------------------------------
# Plan display
# ---------------------------------------------------------------------------


def print_plan(plan: SyncPlan, *, dest: Path, delete_label: str = "trash") -> None:
    """Print a human-readable summary of what the sync would do.

    Parameters
    ----------
    plan:
        The computed sync plan.
    dest:
        Destination root, used to display relative paths.
    delete_label:
        Verb printed for files to be removed (e.g. ``"trash"`` or
        ``"delete"``).
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


# ---------------------------------------------------------------------------
# Plan execution
# ---------------------------------------------------------------------------

def execute_plan(
    plan: SyncPlan,
    *,
    dest: Path,
    delete_mode: str = "trash",
) -> SyncResult:
    """Execute the sync plan: copy files and remove extras.

    Parameters
    ----------
    plan:
        The computed sync plan.
    dest:
        Destination root directory.
    delete_mode:
        How to handle files marked for deletion:

        - ``"trash"`` (default): move to a timestamped ``.trash/``
          subdirectory inside *dest*.
        - ``"delete"``: hard-delete via ``Path.unlink()`` and clean up
          empty ancestor directories up to *dest*.

    Returns
    -------
    SyncResult
        Counts of copied, trashed (i.e. removed regardless of mode),
        and unchanged files.

    Raises
    ------
    SyncError
        On any copy or delete failure, with context about completed and
        remaining operations.
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def append_sync_log(
    result: SyncResult,
    *,
    elapsed_seconds: float,
    error: str | None = None,
    log_path: Path | None = None,
) -> None:
    """Append a structured entry to the sync execution log."""
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
