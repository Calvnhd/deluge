# Deluge CLI v0.1
"""Sync WAV samples from DELUGE/SAMPLES/ to a local cloud-backup folder.

Mirrors all .wav files to CLOUD_BACKUP_PATH, preserving directory structure.
Files removed from source are hard-deleted from the destination.
Pass --dry-run to preview only.
"""

from __future__ import annotations

import argparse
import time

from deluge_lib.cli_utils import confirm_apply, get_cloud_backup_path, get_deluge_root
from deluge_lib.paths import CLOUD_SYNC_LOG_PATH
from deluge_lib.syncing import (
    SyncError,
    SyncResult,
    append_sync_log,
    compute_sync,
    execute_plan,
    print_plan,
    report_empty_dirs,
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Sync WAV samples from DELUGE/SAMPLES/ to a cloud-backup folder."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned changes and exit",
    )
    args = parser.parse_args(argv)

    deluge_root = get_deluge_root()
    source = deluge_root / "SAMPLES"
    if not source.is_dir():
        raise SystemExit(f"Source directory does not exist: {source}")
    dest = get_cloud_backup_path()

    print(f"Source:      {source}")
    print(f"Destination: {dest}")
    print()

    plan, _src_scan = compute_sync(
        source, dest, manifest=None, file_filter="wav"
    )

    if not plan.files_to_copy and not plan.files_to_delete:
        print("Already up to date")
        return

    print_plan(plan, dest=dest, delete_label="delete")
    print()

    if args.dry_run:
        print("Dry run complete.")
        return

    if not confirm_apply(
        f"This will sync WAV files from {source} to {dest}. Continue?"
    ):
        print("\n*** Aborted ***\n")
        return

    start_time = time.monotonic()
    try:
        result = execute_plan(plan, dest=dest, delete_mode="delete")
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
            log_path=CLOUD_SYNC_LOG_PATH,
        )
        print()
        print(f"ERROR: Operation failed on: {exc.file}")
        print(f"  {exc}")
        print(f"  {exc.copied} copied, {exc.remaining} remaining")
        raise SystemExit(1) from None
    elapsed = time.monotonic() - start_time
    append_sync_log(result, elapsed_seconds=elapsed, log_path=CLOUD_SYNC_LOG_PATH)

    print()
    print(
        f"Sync complete: {result.copied} copied, "
        f"{result.trashed} deleted, "
        f"{result.unchanged} unchanged."
    )
    report_empty_dirs(dest)


if __name__ == "__main__":
    main()
