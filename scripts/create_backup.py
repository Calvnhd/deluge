# Deluge CLI v0.2
"""Create a timestamped .zip backup of the Deluge SD card or repo DELUGE/ directory.

Archives all XML and WAV files into a compressed zip file.
Pass --dry-run to preview file count and estimated size
"""

from __future__ import annotations

import argparse
import time
import zipfile
from datetime import datetime
from pathlib import PurePosixPath

from deluge_lib.cli_utils import get_zip_dest_path, get_zip_source_path
from deluge_lib.scanning import format_size, scan_tree


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Create a timestamped .zip backup of the Deluge SD card or repo DELUGE/ directory."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show file count and estimated size without creating an archive",
    )
    args = parser.parse_args(argv)

    source = get_zip_source_path()
    dest = get_zip_dest_path()

    print(f"Source:      {source}")
    print(f"Destination: {dest}")
    print()

    scan = scan_tree(source, label="source", file_filter="both")
    files = scan.files

    if not files:
        print("No files found to archive")
        return

    total_size = sum(entry.size for entry in files.values())

    if args.dry_run:
        print(f"Files:           {len(files)}")
        print(f"Uncompressed:    {format_size(total_size)}")
        print()
        print("Dry run complete")
        return

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    archive_name = f"DELUGE-backup-{timestamp}.zip"
    archive_path = dest / archive_name

    file_count = len(files)
    archived = 0

    # ZIP requires dates >= 1980-01-01 (unix timestamp 315532800).
    # FAT32 SD cards often have bogus timestamps (e.g. 1601-01-01 on Windows)
    # so we clamp to the ZIP minimum unconditionally.
    _ZIP_MIN_EPOCH = 315532800

    try:
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for entry in files.values():
                abs_path = source / entry.rel_path
                arcname = str(PurePosixPath(entry.rel_path))
                info = zipfile.ZipInfo(arcname)
                info.compress_type = zipfile.ZIP_DEFLATED
                mtime = max(abs_path.stat().st_mtime, _ZIP_MIN_EPOCH)
                info.date_time = time.localtime(mtime)[:6]
                with abs_path.open("rb") as f:
                    zf.writestr(info, f.read())
                archived += 1
                print(f"\rArchiving... {archived}/{file_count}", end="", flush=True)
        print()
    except OSError as exc:
        print()
        print(f"ERROR: Failed to create archive at {archived} files: {exc}")
        raise SystemExit(1) from None

    # Verify archive integrity
    print("Verifying archive...", end="", flush=True)
    with zipfile.ZipFile(archive_path, "r") as zf:
        bad_file = zf.testzip()
    if bad_file:
        print(f"\nWARNING: Corrupt file in archive: {bad_file}")
    else:
        print(" OK")

    archive_size = archive_path.stat().st_size
    print()
    print(f"Archive:     {archive_path}")
    print(f"Files:       {file_count}")
    print(f"Size:        {format_size(archive_size)}")


if __name__ == "__main__":
    main()
