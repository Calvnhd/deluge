"""Sync the contents of a mounted Deluge SD card into the local DELUGE/ directory.

By default, shows a dry-run preview then prompts to apply.
Pass --dry-run to preview only, or --confirm to skip the preview.
"""

from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from deluge_lib.cli_utils import confirm_apply, get_deluge_root, get_sd_card_path

# FAT32 has 2-second mtime resolution — allow tolerance when comparing timestamps.
_MTIME_TOLERANCE_S = 2.0


@dataclass
class SyncPlan:
    """Holds the list of planned sync actions."""

    files_to_copy: list[tuple[Path, Path]] = field(default_factory=list)
    files_to_delete: list[Path] = field(default_factory=list)
    dirs_to_delete: list[Path] = field(default_factory=list)
    files_unchanged: int = 0


def _needs_copy(src: Path, dst: Path) -> bool:
    """Return True if src is newer than dst (or dst doesn't exist)."""
    if not dst.exists():
        return True
    return src.stat().st_mtime - dst.stat().st_mtime > _MTIME_TOLERANCE_S


def compute_sync(source: Path, dest: Path) -> SyncPlan:
    """Walk both trees and build a plan of copy/delete actions.

    """
    plan = SyncPlan()

    # --- files/dirs to copy (source → dest) ---
    for src_path in sorted(source.rglob("*")):
        if not src_path.is_file():
            continue
        rel = src_path.relative_to(source)
        dst_path = dest / rel
        if _needs_copy(src_path, dst_path):
            plan.files_to_copy.append((src_path, dst_path))
        else:
            plan.files_unchanged += 1

    # --- extra files/dirs in dest not present in source (--delete equivalent) ---
    if dest.is_dir():
        for dst_path in sorted(dest.rglob("*"), reverse=True):  # deepest first so files delete before parent dirs
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
        print(f"  delete  {path.relative_to(dest)}")
    for path in plan.dirs_to_delete:
        print(f"  rmdir   {path.relative_to(dest)}/")

    print()
    print(
        f"  {len(plan.files_to_copy)} to copy, "
        f"{len(plan.files_to_delete)} to delete, "
        f"{plan.files_unchanged} unchanged"
    )


def execute_plan(plan: SyncPlan) -> None:
    """Execute the sync plan: copy files, remove extras."""
    for src, dst in plan.files_to_copy:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    for path in plan.files_to_delete:
        path.unlink()

    for path in plan.dirs_to_delete:
        if path.is_dir():
            shutil.rmtree(path)


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

    execute_plan(plan)
    print()
    print(f"Sync complete: {len(plan.files_to_copy)} copied, {len(plan.files_to_delete)} deleted.")


if __name__ == "__main__":
    main()
