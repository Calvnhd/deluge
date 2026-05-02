# Deluge CLI v0.1
"""WORK IN PROGRESS

Sync the local DELUGE/ directory back to a mounted Deluge SD card.

By default, shows a preview of changes then prompts to apply.
Pass --dry-run to preview only.

All copies (repo → SD) execute before any deletions 
Files deleted from SD are first backed up to DELUGE/.trash/SD-<timestamp>/
"""

from __future__ import annotations

import argparse
import shutil
import time
from datetime import datetime
from pathlib import Path

from deluge_lib.cli_utils import confirm_apply, get_deluge_root, get_sd_card_path
from deluge_lib.paths import TO_SD_SYNC_LOG_PATH
from deluge_lib.syncing import (
    SyncError,
    SyncPlan,
    SyncResult,
    append_sync_log,
    compute_sync,
    print_plan,
)


def _execute_to_sd(
    plan: SyncPlan,
    *,
    source: Path,
    dest: Path,
) -> SyncResult:
    # TODO-v0.1-REVIEW
    """Execute the sync plan: copy repo files to SD, then trash-and-delete SD extras.

    The execution has two phases, always in this order:
    1. **Copy phase** — copy new/modified files from repo to SD card
    2. **Trash-and-delete phase** — for each file on SD not in repo:
       a. Copy the SD file to ``source/.trash/SD-<timestamp>/<rel_path>``
       b. Verify the trash copy exists
       c. Delete the SD original
       d. Clean up empty parent directories on SD

    Parameters
    ----------
    plan:
        The computed sync plan.
    source:
        Repo ``DELUGE/`` root (used for the ``.trash/`` backup location).
    dest:
        SD card mount point.

    Returns
    -------
    SyncResult
        Counts of copied, trashed, and unchanged files.

    Raises
    ------
    SyncError
        On any file operation failure, with context about progress.
    """
    copied = 0
    total_copy = len(plan.files_to_copy)

    # --- Phase 1: copies (repo → SD) ---
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

    # --- Phase 2: trash-and-delete (SD → repo .trash/, then delete from SD) ---
    trashed = 0
    trash_count = len(plan.files_to_delete)
    if trash_count:
        trash_base = source / ".trash" / datetime.now().strftime("SD-%Y%m%d_%H%M%S")
        try:
            for path in plan.files_to_delete:
                rel = path.relative_to(dest)
                # Back up SD file to repo .trash/
                trash_dest = trash_base / rel
                trash_dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(path), str(trash_dest))
                # Verify backup exists before deleting original
                if not trash_dest.is_file():
                    raise OSError(f"Trash backup verification failed: {trash_dest}")
                # Delete from SD
                path.unlink()
                trashed += 1
                # Clean up empty ancestor directories on SD up to dest root
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


def main(argv: list[str] | None = None) -> None:
    # TODO-v0.1-REVIEW
    parser = argparse.ArgumentParser(
        description="Sync the local DELUGE/ directory back to a mounted Deluge SD card."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change and exit without prompting.",
    )
    parser.add_argument(
        "--xml",
        action="store_true",
        help="Sync only XML files. Combine with --wav to sync both.",
    )
    parser.add_argument(
        "--wav",
        action="store_true",
        help="Sync only WAV files. Combine with --xml to sync both.",
    )
    args = parser.parse_args(argv)

    if args.xml and not args.wav:
        file_filter = "xml"
    elif args.wav and not args.xml:
        file_filter = "wav"
    else:
        file_filter = "both"

    deluge_root = get_deluge_root()
    sd_path = get_sd_card_path()

    print(f"Source:      {deluge_root}")
    print(f"Destination: {sd_path}")
    print()

    plan, _src_scan = compute_sync(deluge_root, sd_path, file_filter=file_filter)

    if not plan.files_to_copy and not plan.files_to_delete:
        print("Already up to date")
        return

    print_plan(plan, dest=sd_path, delete_label="delete")
    print()

    if args.dry_run:
        print("Dry run complete.")
        return

    if not confirm_apply(
        f"This will modify the SD card at {sd_path}. Continue?"
    ):
        print("\n*** Aborted ***\n")
        return

    start_time = time.monotonic()
    try:
        result = _execute_to_sd(plan, source=deluge_root, dest=sd_path)
    except SyncError as exc:
        elapsed = time.monotonic() - start_time
        error_result = SyncResult(
            copied=exc.copied,
            trashed=exc.trashed,
            unchanged=exc.unchanged,
        )
        append_sync_log(
            error_result,
            elapsed_seconds=elapsed,
            error=str(exc),
            log_path=TO_SD_SYNC_LOG_PATH,
        )
        print()
        print(f"ERROR: Operation failed on: {exc.file}")
        print(f"  {exc}")
        print(f"  {exc.copied} copied, {exc.remaining} remaining")
        raise SystemExit(1) from None
    elapsed = time.monotonic() - start_time

    append_sync_log(result, elapsed_seconds=elapsed, log_path=TO_SD_SYNC_LOG_PATH)

    print()
    print(
        f"Sync complete: {result.copied} copied, "
        f"{result.trashed} deleted from SD "
        f"(backed up to .trash/)."
    )


if __name__ == "__main__":
    main()
