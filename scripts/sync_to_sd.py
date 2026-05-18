# Deluge CLI v0.1
"""
Sync the local DELUGE/ directory back to a mounted Deluge SD card.

By default, shows a preview of changes then prompts to apply.
Pass --dry-run to preview only.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from deluge_lib.cli_utils import confirm_apply, get_deluge_root, get_sd_card_path
from deluge_lib.paths import SYNC_MANIFEST_PATH
from deluge_lib.syncing import (
    SyncError,
    SyncResult,
    append_sync_log,
    build_post_sync_manifest,
    compute_sync,
    execute_plan,
    print_plan,
    read_manifest,
    clean_empty_dirs,
    write_manifest,
)


def main(argv: list[str] | None = None) -> None:
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

    manifest_files = read_manifest(SYNC_MANIFEST_PATH)

    print(f"Source:      {deluge_root}")
    print(f"Destination: {sd_path}")
    print()

    plan, src_scan = compute_sync(deluge_root, sd_path, manifest=manifest_files, source_is_sd=False, file_filter=file_filter)

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
        result = execute_plan(plan, dest=sd_path, delete_mode="delete")
    except SyncError as exc:
        elapsed = time.monotonic() - start_time
        error_result = SyncResult(
            copied=exc.copied,
            trashed=exc.trashed,
            unchanged=exc.unchanged,
        )
        append_sync_log(
            error_result,
            direction="to-sd",
            elapsed_seconds=elapsed,
            error=str(exc),
        )
        print()
        print(f"ERROR: Operation failed on: {exc.file}")
        print(f"  {exc}")
        print(f"  {exc.copied} copied, {exc.remaining} remaining")
        print()
        print("Sync FAILED. Manifest was NOT updated.")
        raise SystemExit(1) from None
    elapsed = time.monotonic() - start_time

    append_sync_log(result, direction="to-sd", elapsed_seconds=elapsed)

    try:
        updated_manifest = build_post_sync_manifest(plan, src_scan, sd_path, manifest_files, source_is_sd=False, file_filter=file_filter)
        write_manifest(SYNC_MANIFEST_PATH, files=updated_manifest)
    except OSError as exc:
        print(f"\nWARNING: Sync succeeded but manifest update failed: {exc}")

    print()
    print(
        f"Sync complete: {result.copied} copied, "
        f"{result.trashed} deleted from SD."
    )
    clean_empty_dirs(sd_path)


if __name__ == "__main__":
    main()
