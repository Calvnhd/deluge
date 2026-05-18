# Deluge CLI v0.2
"""Sync the contents of a mounted Deluge SD card into the local DELUGE/ directory.

By default, shows a preview of changes then prompts to apply.
Pass --dry-run to preview only (no prompt).
"""

from __future__ import annotations

import argparse
import time

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
        description="Sync Deluge SD card contents into the local DELUGE/ directory."
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

    sd_path = get_sd_card_path()
    deluge_root = get_deluge_root()

    manifest_files = read_manifest(SYNC_MANIFEST_PATH)

    print(f"Source:      {sd_path}")
    print(f"Destination: {deluge_root}")
    print()

    plan, src_scan = compute_sync(sd_path, deluge_root, manifest=manifest_files, source_is_sd=True, file_filter=file_filter)

    if not plan.files_to_copy and not plan.files_to_delete:
        print("Already up to date")
        return

    print_plan(plan, dest=deluge_root)
    print()

    if args.dry_run:
        print("Dry run complete.")
        return

    if not confirm_apply(
        f"This will overwrite {deluge_root} to match {sd_path} \nContinue?"
    ):
        print("\n*** Aborted ***\n")
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
        append_sync_log(error_result, direction="from-sd", elapsed_seconds=elapsed, error=str(exc))
        print()
        print(f"ERROR: Operation failed on: {exc.file}")
        print(f"  {exc}")
        print(f"  {exc.copied} copied, {exc.trashed} trashed, {exc.remaining} remaining")
        print()
        print("Sync FAILED. Manifest was NOT updated.")
        raise SystemExit(1) from None
    elapsed = time.monotonic() - start_time

    # Always log on success.
    append_sync_log(result, direction="from-sd", elapsed_seconds=elapsed)

    # Build and write updated manifest after successful sync.
    try:
        updated_manifest = build_post_sync_manifest(plan, src_scan, deluge_root, manifest_files, source_is_sd=True, file_filter=file_filter)
        write_manifest(SYNC_MANIFEST_PATH, files=updated_manifest)
    except OSError as exc:
        print(f"\nWARNING: Sync succeeded but manifest update failed: {exc}")

    print()
    print(
        f"Sync complete: {result.copied} copied, "
        f"{result.trashed} trashed"
    )
    print()
    clean_empty_dirs(deluge_root)

if __name__ == "__main__":
    main()
