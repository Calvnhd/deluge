#!/usr/bin/env python3
"""
Bulk rename Deluge song files by removing trailing version numbers.

The Deluge saves song iterations with incrementing numbers:
  MySong.XML → MySong 2.XML → MySong 3.XML

After deleting old versions, run this script to clean up the names:
  MySong 3.XML → MySong.XML

Usage:
    python rename_songs.py           # Dry run (preview changes)
    python rename_songs.py --execute # Actually rename files

Safety:
    - Dry-run by default (no changes without --execute)
    - Skips files where target name already exists
    - Skips when multiple numbered versions exist (manual choice required)
"""

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

# Pattern: "SongName 123.XML" → captures ("SongName", "123")
# - Group 1: everything before the space+number (base name)
# - Group 2: the version number (digits only)
# - Match literal ".XML" at end (uppercase only)
PATTERN = re.compile(r'^(.+) (\d+)\.XML$')


def get_songs_dir() -> Path:
    """Get the absolute path to DELUGE/SONGS/ relative to this script."""
    script_dir = Path(__file__).parent.resolve()
    return script_dir.parent / "DELUGE" / "SONGS"


def find_numbered_files(songs_dir: Path) -> dict[str, list[Path]]:
    """
    Find files matching '<Name> <Number>.XML' pattern.
    
    Returns a dict mapping base name to list of matching files.
    Example: {"MySong": [Path("MySong 2.XML"), Path("MySong 5.XML")]}
    """
    groups: dict[str, list[Path]] = defaultdict(list)
    
    for file in songs_dir.glob("*.XML"):
        match = PATTERN.match(file.name)
        if match:
            base_name = match.group(1)
            groups[base_name].append(file)
    
    return dict(groups)


def plan_renames(
    songs_dir: Path, 
    groups: dict[str, list[Path]]
) -> tuple[list[tuple[Path, Path]], list[str]]:
    """
    Determine which files can be safely renamed.
    
    Returns:
        renames: List of (old_path, new_path) tuples for files to rename
        warnings: List of warning messages for skipped files
    """
    renames: list[tuple[Path, Path]] = []
    warnings: list[str] = []
    
    for base_name, files in sorted(groups.items()):
        new_path = songs_dir / f"{base_name}.XML"
        
        # Case 1: Multiple numbered versions exist
        if len(files) > 1:
            file_list = ", ".join(f.name for f in sorted(files))
            warnings.append(
                f"Multiple versions of '{base_name}': {file_list}\n"
                f"  → Skipping. Please manually choose which to keep."
            )
            continue
        
        # Case 2: Base name already exists (conflict)
        if new_path.exists():
            warnings.append(
                f"Cannot rename '{files[0].name}' → '{new_path.name}'\n"
                f"  → Target already exists. Skipping."
            )
            continue
        
        # Case 3: Safe to rename
        renames.append((files[0], new_path))
    
    return renames, warnings


def execute_renames(renames: list[tuple[Path, Path]]) -> int:
    """Rename files and return count of successful renames."""
    count = 0
    for old_path, new_path in renames:
        try:
            old_path.rename(new_path)
            print(f"  ✓ {old_path.name} → {new_path.name}")
            count += 1
        except OSError as e:
            print(f"  ✗ {old_path.name}: {e}")
    return count


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Remove version numbers from Deluge song filenames.",
        epilog="Example: python rename_songs.py --execute"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually rename files (default is dry-run)"
    )
    args = parser.parse_args()
    
    # Resolve songs directory
    songs_dir = get_songs_dir()
    if not songs_dir.exists():
        print(f"Error: Songs directory not found: {songs_dir}")
        return 1
    
    print(f"Scanning: {songs_dir}\n")
    
    # Find and plan renames
    groups = find_numbered_files(songs_dir)
    renames, warnings = plan_renames(songs_dir, groups)
    
    # Display warnings
    if warnings:
        print("⚠️  WARNINGS (files skipped):\n")
        for warning in warnings:
            print(f"  {warning}\n")
    
    # Handle no files case
    if not renames:
        print("No files to rename.")
        return 0
    
    # Execute or dry-run
    if args.execute:
        print(f"Renaming {len(renames)} file(s):\n")
        count = execute_renames(renames)
        print(f"\n✅ Done. Renamed {count} file(s).")
    else:
        print("DRY RUN - No files will be changed. Use --execute to rename.\n")
        print(f"Would rename {len(renames)} file(s):\n")
        for old_path, new_path in renames:
            print(f"  {old_path.name} → {new_path.name}")
        print(f"\nRun with --execute to apply these changes.")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
