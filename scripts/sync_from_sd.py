"""Sync the contents of a mounted Deluge SD card into the local DELUGE/ directory.

By default, shows a dry-run preview then prompts to apply.
Pass --dry-run to preview only, or --confirm to skip the preview.
"""

from __future__ import annotations

import argparse
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from deluge_lib.cli_utils import confirm_apply, get_deluge_root, get_sd_card_path
from deluge_lib.manifest import (
    FilesDict,
    ManifestData,
    default_manifest_path,
    make_timestamp,
    read_manifest,
    write_manifest,
)
from deluge_lib.scanning import ScanResult, normalise_key, scan_tree


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
_DELUGE_EXPECTED_DIRS = {"KITS", "SYNTHS", "SONGS", "SAMPLES"}


def _mtime_matches(mtime_a: float, mtime_b: float) -> bool:
    """Return True if two mtimes are equal within FAT32 tolerance.

    FAT32 has 2-second mtime resolution, so mtimes within ±2 seconds
    are treated as equal.
    """
    return abs(mtime_a - mtime_b) <= _MTIME_TOLERANCE_S


def _validate_sd_card(sd_path: Path) -> None:
    """Check that the SD card path contains expected Deluge folders."""
    found = {d.name for d in sd_path.iterdir() if d.is_dir()} & _DELUGE_EXPECTED_DIRS
    if not found:
        raise SystemExit(
            f"SD card at {sd_path} does not look like a Deluge card.\n"
            f"Expected at least one of: {', '.join(sorted(_DELUGE_EXPECTED_DIRS))}"
        )


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
    src_scan = scan_tree(source, progress=True, label="source")

    # --- scan destination (DELUGE/) ---
    dst_scan = scan_tree(dest, progress=True, label="destination")

    # --- compare source → dest (file-level) ---
    for key, src_entry in src_scan.files.items():
        dst_path = dest / src_entry.rel_path

        if key not in dst_scan.files:
            # On SD, not in repo → copy
            plan.files_to_copy.append((source / src_entry.rel_path, dst_path))
            continue

        dst_entry = dst_scan.files[key]

        # Choose comparison target: manifest entry or destination stat.
        if manifest is not None and key in manifest:
            cmp_size: int = manifest[key]["size"]
            cmp_mtime: float = manifest[key]["mtime"]
        else:
            cmp_size = dst_entry.size
            cmp_mtime = dst_entry.mtime

        if src_entry.size != cmp_size:
            # Size differs → copy (overwrite)
            plan.files_to_copy.append((source / src_entry.rel_path, dst_path))
        elif not _mtime_matches(src_entry.mtime, cmp_mtime):
            # Same size, mtime differs → copy (overwrite)
            plan.files_to_copy.append((source / src_entry.rel_path, dst_path))
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
            if i % 100 == 0 or i == total_copy:
                print(f"\rCopying... {i}/{total_copy}", end="", flush=True)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied += 1
    except OSError as exc:
        if total_copy:
            print()
        remaining = total_copy - copied - 1
        print()
        print(f"ERROR: Copy failed on: {src}")
        print(f"  {exc}")
        print(f"  {copied}/{total_copy} files copied before failure")
        print(f"  {remaining} files remaining (unattempted)")
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
            print()
            print(f"ERROR: Trash operation failed on: {path}")
            print(f"  {exc}")
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
    old_manifest: ManifestData,
) -> ManifestData:
    """Build updated manifest data after a successful sync.

    - Unchanged files: preserve existing manifest entries (keeps unknown fields).
    - Copied files: read dest stat for fresh size/mtime.
    - Trashed files: omitted (not in source scan).
    """
    # Sets of normalised keys for files that were actively changed.
    copied_keys: set[str] = set()
    for _src, dst in plan.files_to_copy:
        copied_keys.add(normalise_key(dst.relative_to(dest)))

    new_files: FilesDict = {}
    for key, src_entry in src_scan.files.items():
        if key in copied_keys:
            # Copied: read the new destination stat.
            dst_path = dest / src_entry.rel_path
            try:
                st = dst_path.stat()
                new_files[key] = {"size": st.st_size, "mtime": st.st_mtime}
            except OSError:
                # Fallback to source stat if dest stat fails unexpectedly.
                new_files[key] = {"size": src_entry.size, "mtime": src_entry.mtime}
        elif key in old_manifest.files:
            # Unchanged with existing manifest entry: preserve (keeps D30 fields).
            new_files[key] = dict(old_manifest.files[key])
        else:
            # Unchanged but no prior manifest entry (first run): use source stat.
            new_files[key] = {"size": src_entry.size, "mtime": src_entry.mtime}

    return ManifestData(
        last_sync_timestamp=make_timestamp(),
        last_sync_direction="sd-to-local",
        files=new_files,
    )


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

    with log_path.open("a") as f:
        f.write("---\n")
        f.write("script: sync_from_sd.py\n")
        f.write(f"timestamp: {timestamp}\n")
        f.write(f"status: {status}\n")
        f.write(f"files_copied: {result.copied}\n")
        f.write(f"files_trashed: {result.trashed}\n")
        f.write(f"files_unchanged: {result.unchanged}\n")
        f.write(f"elapsed: {elapsed_m}m {elapsed_s}s\n")
        if error:
            f.write(f"error: {error}\n")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Sync Deluge SD card contents into the local DELUGE/ directory."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--confirm",
        action="store_true",
        help="Skip the dry-run preview and go straight to the confirmation prompt.",
    )
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change and exit without prompting.",
    )
    args = parser.parse_args(argv)

    sd_path = get_sd_card_path()
    deluge_root = get_deluge_root()
    _validate_sd_card(sd_path)

    # Load manifest (empty state on first run or if corrupt).
    manifest_path = default_manifest_path()
    manifest_data = read_manifest(manifest_path)

    print(f"Source:      {sd_path}")
    print(f"Destination: {deluge_root}")
    print()

    plan, src_scan = compute_sync(sd_path, deluge_root, manifest=manifest_data.files)

    if args.dry_run:
        print("=== DRY RUN ===")
        print()
        if _plan_is_empty(plan):
            print("  Already up to date.")
        else:
            print_plan(plan, dest=deluge_root)
        print()
        print("Dry run complete.")
        return

    if not args.confirm:
        print("=== DRY RUN PREVIEW ===")
        print()
        if _plan_is_empty(plan):
            print("  Already up to date.")
            return
        print_plan(plan, dest=deluge_root)
        print()

    if _plan_is_empty(plan):
        print("Already up to date.")
        return

    if not confirm_apply("This will overwrite DELUGE/ to match the SD card. Continue?"):
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
        print("Sync FAILED. Manifest was NOT updated.")
        raise SystemExit(1) from None
    elapsed = time.monotonic() - start_time

    # Always log on success.
    append_sync_log(result, elapsed_seconds=elapsed)

    # Build and write updated manifest after successful sync.
    new_manifest = _build_post_sync_manifest(plan, src_scan, deluge_root, manifest_data)
    write_manifest(new_manifest, manifest_path)

    print()
    print(
        f"Sync complete: {result.copied} copied, "
        f"{result.trashed} trashed."
    )
    if result.trashed:
        print(f"Trashed files are in: {deluge_root / _TRASH_DIR_NAME}")


if __name__ == "__main__":
    main()
