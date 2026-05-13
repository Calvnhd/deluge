# Deluge CLI v0.1
"""Sync the contents of a mounted Deluge SD card into the local DELUGE/ directory.

By default, shows a preview of changes then prompts to apply.
Pass --dry-run to preview only (no prompt).
"""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict

from deluge_lib.cli_utils import confirm_apply, get_deluge_root, get_sd_card_path
from deluge_lib.paths import MANIFEST_PATH
from deluge_lib.scanning import ScanResult, normalise_key, normalise_mtime
from deluge_lib.syncing import (
    SyncError,
    SyncPlan,
    SyncResult,
    append_sync_log,
    compute_sync,
    execute_plan,
    print_plan,
)

class FileRecord(TypedDict):
    """Per-file dual-stat manifest entry — SD-side and local-side stats."""

    sd_size: int
    sd_mtime: float
    local_size: int
    local_mtime: float


def _read_manifest(path: Path) -> tuple[str, dict[str, FileRecord]]:
    """Read a JSON manifest file"""

    if not path.is_file():
        print(f"Warning: No manifest at {path}")
        return ("", {})

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Warning: corrupt manifest at {path} ({exc}) \u2014 treating as empty")
        return ("", {})

    timestamp = str(data.get("last_sync_timestamp", ""))

    files: dict[str, FileRecord] = {}
    for key, val in data.get("files", {}).items():
        if isinstance(val, dict) and "sd_size" in val and "sd_mtime" in val and "local_size" in val and "local_mtime" in val:
            files[key] = {
                "sd_size": int(val["sd_size"]),
                "sd_mtime": float(val["sd_mtime"]),
                "local_size": int(val["local_size"]),
                "local_mtime": float(val["local_mtime"]),
            }

    return (timestamp, files)


def _write_manifest(
    path: Path,
    *,
    timestamp: str,
    files: dict[str, FileRecord],
) -> None:
    """Atomically write a manifest JSON file"""
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


def _build_post_sync_manifest(
    plan: SyncPlan,
    src_scan: ScanResult,
    dest: Path,
    old_files: dict[str, FileRecord],
    file_filter: str = "both",
) -> tuple[str, dict[str, FileRecord]]:
    """Build updated manifest after a successful sync"""

    from deluge_lib.scanning import _FILTER_MAP

    copied_keys: set[str] = set()
    for _src, dst in plan.files_to_copy:
        copied_keys.add(normalise_key(dst.relative_to(dest)))

    updated_manifest: dict[str, FileRecord] = {}
    for key, src_entry in src_scan.files.items():
        if key in old_files and key not in copied_keys:
            # Unchanged with existing manifest entry: preserve as-is.
            updated_manifest[key] = old_files[key]
        else:
            # Copied or no prior entry: SD stats from scan, local stats from dest file.
            dst_path = dest / src_entry.rel_path
            dst_stat = dst_path.stat()
            updated_manifest[key] = {
                "sd_size": src_entry.size,
                "sd_mtime": src_entry.mtime, # SD time is normalized upstream via scan_tree()
                "local_size": dst_stat.st_size,
                "local_mtime": normalise_mtime(dst_stat.st_mtime),
            }

    # Preserve manifest entries for file types not included in this filtered sync.
    if file_filter != "both":
        scanned_exts = _FILTER_MAP[file_filter]
        for key, old_entry in old_files.items():
            if key not in updated_manifest:
                ext = Path(key).suffix.lower()
                if ext not in scanned_exts:
                    updated_manifest[key] = old_entry

    timestamp = datetime.now(tz=UTC).replace(microsecond=0).isoformat()
    return (timestamp, updated_manifest)


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

    # Load manifest (empty state on first run or if corrupt).
    manifest_path = MANIFEST_PATH
    _, manifest_files = _read_manifest(manifest_path)

    print(f"Source:      {sd_path}")
    print(f"Destination: {deluge_root}")
    print()

    plan, src_scan = compute_sync(sd_path, deluge_root, manifest=manifest_files, file_filter=file_filter)

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
    try:
        new_ts, updated_manifest = _build_post_sync_manifest(plan, src_scan, deluge_root, manifest_files, file_filter)
        _write_manifest(manifest_path, timestamp=new_ts, files=updated_manifest)
    except OSError as exc:
        print(f"\nWARNING: Sync succeeded but manifest update failed: {exc}")

    print()
    print(
        f"Sync complete: {result.copied} copied, "
        f"{result.trashed} trashed"
    )
    print()

if __name__ == "__main__":
    main()
