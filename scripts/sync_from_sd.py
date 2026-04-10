"""Sync the contents of a mounted Deluge SD card into the local DELUGE/ directory.

By default, shows a preview of changes then prompts to apply.
Pass --dry-run to preview only (no prompt).
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict

from deluge_lib.cli_utils import confirm_apply, get_deluge_root, get_sd_card_path
from deluge_lib.scanning import ScanResult, normalise_key, normalise_mtime, scan_tree

# -- Manifest types and helpers -----------------------------------------------


class FileRecord(TypedDict):
    """Per-file manifest entry with size and modification time."""

    size: int
    mtime: float


FilesDict = dict[str, FileRecord]


def _default_manifest_path() -> Path:
    """Return the default manifest path (``scripts/data/manifest.json``)."""
    return Path(__file__).resolve().parent / "data" / "manifest.json"


def _read_manifest(path: Path) -> tuple[str, dict[str, FileRecord]]:
    """Read a manifest JSON file, returning (timestamp, files).

    Returns ``("", {})`` when the file is missing or contains invalid JSON.
    Tolerates old manifest formats that include extra metadata fields
    (version, direction, file_count) — they are simply ignored.
    """
    if not path.is_file():
        return ("", {})

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Warning: corrupt manifest at {path} ({exc}) — treating as empty")
        return ("", {})

    # Support old format (metadata.last_sync_timestamp) and new (top-level).
    if "metadata" in data:
        timestamp = str(data["metadata"].get("last_sync_timestamp", ""))
    else:
        timestamp = str(data.get("last_sync_timestamp", ""))

    files: dict[str, FileRecord] = {}
    for key, val in data.get("files", {}).items():
        if isinstance(val, dict) and "size" in val and "mtime" in val:
            files[key] = {"size": int(val["size"]), "mtime": normalise_mtime(float(val["mtime"]))}

    return (timestamp, files)


def _write_manifest(
    path: Path,
    *,
    timestamp: str,
    files: dict[str, FileRecord],
) -> None:
    """Atomically write a manifest JSON file.

    Uses a temporary file in the same directory followed by a rename
    to prevent corruption from interrupted writes.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "last_sync_timestamp": timestamp,
        "files": files,
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
    """Outcome of executing a sync plan — counts only."""

    copied: int = 0
    trashed: int = 0
    unchanged: int = 0


_MTIME_TOLERANCE_S = 2.0
_TRASH_DIR_NAME = ".trash"


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
) -> tuple[SyncPlan, ScanResult]:
    """Walk both trees and build a plan of copy/delete/rename actions.

    Parameters
    ----------
    source:
        Root of the SD card (or any source directory).
    dest:
        Root of the local ``DELUGE/`` directory.
    manifest:
        Optional manifest dict mapping normalised keys to
        ``{"size": int, "mtime": float, ...}`` entries.  When an entry
        exists, the SD card stat is compared against the manifest instead
        of the destination file stat.

    Returns
    -------
    tuple[SyncPlan, ScanResult]
        The sync plan and the source scan result (needed for manifest
        updates after execution).
    """
    plan = SyncPlan()

    # --- scan source (SD card) ---
    src_scan = scan_tree(source, label="source")

    # --- scan destination (DELUGE/) ---
    dst_scan = scan_tree(dest, label="destination")

    # --- compare source → dest (file-level) ---
    for key, src_entry in src_scan.files.items():
        src_path = source / src_entry.rel_path
        dst_path = dest / src_entry.rel_path

        if key not in dst_scan.files:
            # On SD, not in repo → copy
            plan.files_to_copy.append((src_path, dst_path))
            continue

        dst_entry = dst_scan.files[key]

        # Choose comparison target: manifest entry if it exists, otherwise use destination stat
        if manifest is not None and key in manifest:
            cmp_size: int = manifest[key]["size"]
            cmp_mtime: float = manifest[key]["mtime"]
        else:
            cmp_size = dst_entry.size
            cmp_mtime = dst_entry.mtime

        if src_entry.size != cmp_size:
            # Size differs → copy (overwrite)
            plan.files_to_copy.append((src_path, dst_path))
        elif not _mtime_matches(src_entry.mtime, cmp_mtime):
            # Same size, mtime differs → copy (overwrite)
            plan.files_to_copy.append((src_path, dst_path))
        else:
            # Identical (or case-only difference) → skip
            plan.files_unchanged += 1

    # --- files in dest not on source → trash ---
    for key, dst_entry in dst_scan.files.items():
        if key not in src_scan.files:
            plan.files_to_delete.append(dest / dst_entry.rel_path)

    return plan, src_scan


def print_plan(plan: SyncPlan, *, dest: Path) -> None:
    """Print a human-readable summary of what the sync would do."""
    for _src, dst in plan.files_to_copy:
        rel = dst.relative_to(dest)
        if dst.exists():
            print(f"  update  {rel}")
        else:
            print(f"  copy    {rel}")

    for path in plan.files_to_delete:
        print(f"  trash   {path.relative_to(dest)}")

    print()
    print(
        f"  {len(plan.files_to_copy)} to copy, "
        f"{len(plan.files_to_delete)} to trash, "
        f"{plan.files_unchanged} unchanged"
    )


def execute_plan(plan: SyncPlan, *, dest: Path) -> SyncResult:
    """Execute the sync plan: copy files and trash extras.

    Raises ``SyncError`` on any failure. On success, returns a
    ``SyncResult`` with counts.
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

    # --- trash ---
    trashed = 0
    trash_count = len(plan.files_to_delete)
    if trash_count:
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

    return SyncResult(
        copied=copied,
        trashed=trashed,
        unchanged=plan.files_unchanged,
    )


def _plan_is_empty(plan: SyncPlan) -> bool:
    return not plan.files_to_copy and not plan.files_to_delete


def _build_post_sync_manifest(
    plan: SyncPlan,
    src_scan: ScanResult,
    dest: Path,
    old_files: dict[str, FileRecord],
) -> tuple[str, dict[str, FileRecord]]:
    """Build updated manifest data after a successful sync.

    Returns ``(timestamp, files)`` where *timestamp* is the current UTC
    time as an ISO 8601 string and *files* maps normalised keys to
    ``FileRecord`` dicts.

    - Unchanged files: preserve existing manifest entries.
    - Copied files: read dest stat for fresh size/mtime.
    - Trashed files: omitted (not in source scan).
    """
    # Sets of normalised keys for files that were actively changed.
    copied_keys: set[str] = set()
    for _src, dst in plan.files_to_copy:
        copied_keys.add(normalise_key(dst.relative_to(dest)))

    new_files: dict[str, FileRecord] = {}
    for key, src_entry in src_scan.files.items():
        if key in copied_keys:
            # Copied: use the normalised source mtime (already on FAT32 grid).
            new_files[key] = {"size": src_entry.size, "mtime": src_entry.mtime}
        elif key in old_files:
            # Unchanged with existing manifest entry: preserve.
            old = old_files[key]
            new_files[key] = {"size": old["size"], "mtime": old["mtime"]}
        else:
            # Unchanged but no prior manifest entry (first run): use source stat.
            new_files[key] = {"size": src_entry.size, "mtime": src_entry.mtime}

    timestamp = datetime.now(tz=UTC).replace(microsecond=0).isoformat()
    return (timestamp, new_files)


def _default_log_path() -> Path:
    """Return the default path for the sync execution log."""
    return Path(__file__).resolve().parent / "data" / "sync.log"


def append_sync_log(
    result: SyncResult,
    *,
    elapsed_seconds: float,
    error: str | None = None,
    log_path: Path | None = None,
) -> None:
    """Append a structured entry to the sync execution log."""
    if log_path is None:
        log_path = _default_log_path()
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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Sync Deluge SD card contents into the local DELUGE/ directory."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change and exit without prompting.",
    )
    args = parser.parse_args(argv)

    sd_path = get_sd_card_path()
    deluge_root = get_deluge_root()

    # Load manifest (empty state on first run or if corrupt).
    manifest_path = _default_manifest_path()
    manifest_ts, manifest_files = _read_manifest(manifest_path)

    print(f"Source:      {sd_path}")
    print(f"Destination: {deluge_root}")
    print()

    plan, src_scan = compute_sync(sd_path, deluge_root, manifest=manifest_files)

    if _plan_is_empty(plan):
        print("Already up to date.")
        return

    print_plan(plan, dest=deluge_root)
    print()

    if args.dry_run:
        print("Dry run complete.")
        return

    if not confirm_apply(
        f"This will overwrite {deluge_root} to match {sd_path}. Continue?"
    ):
        print("Aborted.")
        return

    start_time = time.monotonic()
    try:
        result = execute_plan(plan, dest=deluge_root)
    except SyncError as exc:
        elapsed = time.monotonic() - start_time
        error_result = SyncResult(
            copied=exc.copied,
            trashed=exc.trashed,
            unchanged=exc.unchanged,
        )
        append_sync_log(error_result, elapsed_seconds=elapsed, error=str(exc))
        print()
        print(f"ERROR: Operation failed on: {exc.file}")
        print(f"  {exc}")
        print(f"  {exc.copied} copied, {exc.remaining} remaining")
        print()
        print("Sync FAILED. Manifest was NOT updated.")
        raise SystemExit(1) from None
    elapsed = time.monotonic() - start_time

    # Always log on success.
    append_sync_log(result, elapsed_seconds=elapsed)

    # Build and write updated manifest after successful sync.
    new_ts, new_files = _build_post_sync_manifest(plan, src_scan, deluge_root, manifest_files)
    _write_manifest(manifest_path, timestamp=new_ts, files=new_files)

    print()
    print(
        f"Sync complete: {result.copied} copied, "
        f"{result.trashed} trashed."
    )

if __name__ == "__main__":
    main()
