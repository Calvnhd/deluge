"""Create a timestamped .zip backup of the Deluge SD card or repo DELUGE/ directory.

Archives all XML and WAV files (excluding .trash) into a compressed zip file.
Pass --dry-run to preview file count and estimated size without creating an archive.
"""

from __future__ import annotations

import argparse
import zipfile
from datetime import datetime
from pathlib import PurePosixPath

from deluge_lib.cli_utils import get_zip_dest_path, get_zip_source_path
from deluge_lib.scanning import scan_tree


def _format_size(size_bytes: int) -> str:
    """Format a byte count as a human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Create a timestamped .zip backup of the Deluge SD card or repo DELUGE/ directory."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show file count and estimated size without creating an archive.",
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
        print("No files found to archive.")
        return

    total_size = sum(entry.size for entry in files.values())

    if args.dry_run:
        print(f"Files:           {len(files)}")
        print(f"Uncompressed:    {_format_size(total_size)}")
        print()
        print("Dry run complete.")
        return

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    archive_name = f"DELUGE-backup-{timestamp}.zip"
    archive_path = dest / archive_name

    file_count = len(files)
    archived = 0

    try:
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for entry in files.values():
                abs_path = source / entry.rel_path
                arcname = str(PurePosixPath(entry.rel_path))
                zf.write(abs_path, arcname)
                archived += 1
                print(f"\rArchiving... {archived}/{file_count}", end="", flush=True)
        print()
    except OSError as exc:
        print()
        print(f"ERROR: Failed to create archive: {exc}")
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
    print(f"Size:        {_format_size(archive_size)}")


if __name__ == "__main__":
    main()
