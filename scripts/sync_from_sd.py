"""Sync the contents of a mounted Deluge SD card into the local DELUGE/ directory.

By default, shows a dry-run preview then prompts to apply.
Pass --dry-run to preview only, or --confirm to skip the preview.
"""

from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from deluge_lib.cli_utils import confirm_apply, get_deluge_root, get_sd_card_path


@dataclass
class SyncPlan:
    """Holds the list of planned sync actions."""

    files_to_copy: list[tuple[Path, Path]] = field(default_factory=list)
    files_to_delete: list[Path] = field(default_factory=list)
    dirs_to_delete: list[Path] = field(default_factory=list)
    files_unchanged: int = 0


_MTIME_TOLERANCE_S = 2.0
_DST_OFFSET_S = 3600
_TRASH_DIR_NAME = ".trash"
_DELUGE_EXPECTED_DIRS = {"KITS", "SYNTHS", "SONGS", "SAMPLES"}


def _needs_copy(src: Path, dst: Path) -> bool:
    """Return True if src should be copied to dst.

    Compares by existence, then file size, then mtime with DST-aware
    tolerance.  FAT32 (SD card) stores local time while NTFS stores UTC,
    so DST changes shift all FAT32 timestamps by ±1 hour on Windows.
    We treat an mtime difference within 2 s of 0 or 3600 as unchanged.
    """
    if not dst.exists():
        return True
    src_stat = src.stat()
    dst_stat = dst.stat()
    if src_stat.st_size != dst_stat.st_size:
        return True
    diff = abs(src_stat.st_mtime - dst_stat.st_mtime)
    if diff <= _MTIME_TOLERANCE_S:
        return False
    if abs(diff - _DST_OFFSET_S) <= _MTIME_TOLERANCE_S:
        return False
    return True


def _validate_sd_card(sd_path: Path) -> None:
    """Check that the SD card path contains expected Deluge folders."""
    found = {d.name for d in sd_path.iterdir() if d.is_dir()} & _DELUGE_EXPECTED_DIRS
    if not found:
        raise SystemExit(
            f"SD card at {sd_path} does not look like a Deluge card.\n"
            f"Expected at least one of: {', '.join(sorted(_DELUGE_EXPECTED_DIRS))}"
        )


def compute_sync(source: Path, dest: Path) -> SyncPlan:
    """Walk both trees and build a plan of copy/delete actions.

    """
    plan = SyncPlan()

    # --- scan source ---
    print("Scanning source...", end="", flush=True)
    src_files = []
    for p in source.rglob("*"):
        if p.is_file():
            src_files.append(p)
            if len(src_files) % 500 == 0:
                print(f"\rScanning source... {len(src_files)} files", end="", flush=True)
    print(f"\rScanning source... {len(src_files)} files found.")

    # --- compare source → dest ---
    for src_path in sorted(src_files):
        rel = src_path.relative_to(source)
        dst_path = dest / rel
        if _needs_copy(src_path, dst_path):
            plan.files_to_copy.append((src_path, dst_path))
        else:
            plan.files_unchanged += 1

    # --- scan dest for extras ---
    if dest.is_dir():
        print("Scanning destination...", end="", flush=True)
        dest_entries = []
        for p in dest.rglob("*"):
            rel = p.relative_to(dest)
            if rel.parts[0] == _TRASH_DIR_NAME:
                continue
            dest_entries.append(p)
            if len(dest_entries) % 500 == 0:
                print(f"\rScanning destination... {len(dest_entries)} items", end="", flush=True)
        print(f"\rScanning destination... {len(dest_entries)} items found.")

        for dst_path in sorted(dest_entries, reverse=True):  # deepest first
            rel = dst_path.relative_to(dest)
            src_path = source / rel
            if dst_path.is_file() and not src_path.is_file():
                plan.files_to_delete.append(dst_path)
            elif dst_path.is_dir() and not src_path.is_dir():
                plan.dirs_to_delete.append(dst_path)

    return plan


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
    for path in plan.dirs_to_delete:
        print(f"  trash   {path.relative_to(dest)}/")

    print()
    print(
        f"  {len(plan.files_to_copy)} to copy, "
        f"{len(plan.files_to_delete) + len(plan.dirs_to_delete)} to trash, "
        f"{plan.files_unchanged} unchanged"
    )


def execute_plan(plan: SyncPlan, *, dest: Path) -> None:
    """Execute the sync plan: copy files, trash extras."""
    total_copy = len(plan.files_to_copy)
    for i, (src, dst) in enumerate(plan.files_to_copy, 1):
        if i % 100 == 0 or i == total_copy:
            print(f"\rCopying... {i}/{total_copy}", end="", flush=True)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    if total_copy:
        print()

    trash_count = len(plan.files_to_delete) + len(plan.dirs_to_delete)
    if trash_count:
        trash_base = dest / _TRASH_DIR_NAME / datetime.now().strftime("%Y%m%d_%H%M%S")
        for path in plan.files_to_delete:
            rel = path.relative_to(dest)
            trash_dest = trash_base / rel
            trash_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(trash_dest))

        for path in plan.dirs_to_delete:
            if not path.is_dir():
                continue
            if any(path.iterdir()):
                rel = path.relative_to(dest)
                trash_dest = trash_base / rel
                trash_dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), str(trash_dest))
            else:
                path.rmdir()


def _plan_is_empty(plan: SyncPlan) -> bool:
    return not plan.files_to_copy and not plan.files_to_delete and not plan.dirs_to_delete


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

    print(f"Source:      {sd_path}")
    print(f"Destination: {deluge_root}")
    print()

    plan = compute_sync(sd_path, deluge_root)

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

    execute_plan(plan, dest=deluge_root)
    trash_count = len(plan.files_to_delete) + len(plan.dirs_to_delete)
    print()
    print(f"Sync complete: {len(plan.files_to_copy)} copied, {trash_count} trashed.")
    if trash_count:
        print(f"Trashed files are in: {deluge_root / _TRASH_DIR_NAME}")


if __name__ == "__main__":
    main()
