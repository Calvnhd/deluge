#!/usr/bin/env python3
"""
Sync Deluge SD card contents to this repository.

Safety guarantees:
  - Read-only access to SD card (copies FROM, never writes TO)
  - Files removed from SD card are moved to DELUGE/.trash/ (not deleted)
  - Only syncs .xml and .wav files
  - Validates paths before any operations

Logs: Appends execution summary to docs/scripts.log
"""

import os
import sys
import shutil
import hashlib
import filecmp
from pathlib import Path
from datetime import datetime
from typing import NamedTuple


class SyncStats(NamedTuple):
    added: list[str]
    modified: list[str]
    trashed: list[str]
    unchanged: int


def load_env(env_path: Path) -> dict[str, str]:
    """Load environment variables from .env file."""
    env = {}
    if not env_path.exists():
        return env
    
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, _, value = line.partition('=')
                # Remove quotes and expand $HOME
                value = value.strip().strip('"').strip("'")
                value = os.path.expandvars(value)
                # Convert Git Bash paths to Windows paths (e.g., /c/Users -> C:\Users)
                value = convert_gitbash_path(value)
                env[key.strip()] = value
    return env


def convert_gitbash_path(path: str) -> str:
    """Convert Git Bash style paths to Windows paths if needed.
    
    Examples:
        /c/Users/name -> C:\\Users\\name
        /g/ -> G:\\
        C:\\Users\\name -> C:\\Users\\name (unchanged)
    """
    import re
    # Match Git Bash style: /c/ or /c/path/to/file
    match = re.match(r'^/([a-zA-Z])(/.*)?$', path)
    if match:
        drive = match.group(1).upper()
        rest = match.group(2) or ''
        # Convert forward slashes to backslashes
        rest = rest.replace('/', '\\')
        return f"{drive}:{rest}" if rest else f"{drive}:\\"
    return path


def get_file_type(rel_path: str) -> str:
    """Categorize file by its location/extension."""
    rel_lower = rel_path.lower()
    
    if rel_lower.startswith('kits/'):
        return 'kit'
    elif rel_lower.startswith('synths/'):
        return 'synth'
    elif rel_lower.startswith('songs/'):
        return 'song'
    elif rel_lower.startswith('samples/'):
        return 'sample'
    elif rel_lower.endswith('.xml'):
        return 'xml'
    elif rel_lower.endswith('.wav'):
        return 'wav'
    else:
        return 'other'


def files_are_identical(src: Path, dst: Path) -> bool:
    """Check if two files have identical content."""
    if not dst.exists():
        return False
    
    # Quick check: different sizes = different files
    if src.stat().st_size != dst.stat().st_size:
        return False
    
    # For small files, compare directly
    if src.stat().st_size < 1024 * 1024:  # < 1MB
        return filecmp.cmp(src, dst, shallow=False)
    
    # For large files, compare MD5 hashes
    def md5(path: Path) -> str:
        h = hashlib.md5()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                h.update(chunk)
        return h.hexdigest()
    
    return md5(src) == md5(dst)


def sync_files(sd_path: Path, repo_path: Path, trash_path: Path, dry_run: bool = False) -> tuple[SyncStats, dict]:
    """
    Sync files from SD card to repository.
    
    - New files: copied to repo
    - Modified files: overwritten in repo  
    - Deleted files: moved to trash
    
    Returns (stats, pending_ops) where pending_ops contains the file operations
    to be applied later without re-scanning.
    """
    added = []
    modified = []
    trashed = []
    unchanged = 0
    
    # Pending operations to apply later (avoids re-scanning)
    pending_ops = {
        'copies': [],   # (src, dst) tuples for add/modify
        'trashes': [],  # (src, trash_dest) tuples
        'repo_path': repo_path,
    }
    
    # Collect all relevant files from SD card (single pass, case-insensitive)
    print("  Scanning SD card...", end="", flush=True)
    sd_files: dict[str, str] = {}  # lowercase -> actual path
    sd_count = 0
    for f in sd_path.rglob('*'):
        if f.is_file() and f.suffix.lower() in ('.xml', '.wav'):
            rel = str(f.relative_to(sd_path))
            rel_lower = rel.lower()
            if rel_lower not in sd_files:
                sd_files[rel_lower] = rel
                sd_count += 1
                if sd_count % 500 == 0:
                    print(f"\r  Scanning SD card... {sd_count} files", end="", flush=True)
    print(f"\r  Scanning SD card... {sd_count} files ✓")
    
    # Collect all relevant files from repo (single pass, case-insensitive)
    print("  Scanning repository...", end="", flush=True)
    repo_files: dict[str, str] = {}  # lowercase -> actual path
    repo_count = 0
    for f in repo_path.rglob('*'):
        # Skip trash folder
        if '.trash' in f.parts:
            continue
        if f.is_file() and f.suffix.lower() in ('.xml', '.wav'):
            rel = str(f.relative_to(repo_path))
            rel_lower = rel.lower()
            if rel_lower not in repo_files:
                repo_files[rel_lower] = rel
                repo_count += 1
    print(f"\r  Scanning repository... {repo_count} files ✓")
    
    # Compare files
    print("  Comparing files...", end="", flush=True)
    compared = 0
    total_to_compare = len(sd_files)
    
    # Process files from SD card (add/modify)
    for rel_lower, rel_path in sorted(sd_files.items()):
        src = sd_path / rel_path
        # Use the repo's actual path if it exists, otherwise use SD card path
        repo_rel = repo_files.get(rel_lower, rel_path)
        dst = repo_path / repo_rel
        
        compared += 1
        if compared % 200 == 0:
            print(f"\r  Comparing files... {compared}/{total_to_compare}", end="", flush=True)
        
        if not dst.exists():
            # New file
            pending_ops['copies'].append((src, dst))
            added.append(rel_path)
        elif not files_are_identical(src, dst):
            # Modified file
            pending_ops['copies'].append((src, dst))
            modified.append(rel_path)
        else:
            unchanged += 1
    
    print(f"\r  Comparing files... {total_to_compare}/{total_to_compare} ✓")
    
    # Process files only in repo (deleted from SD card -> trash)
    deleted_keys = set(repo_files.keys()) - set(sd_files.keys())
    if deleted_keys:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        for rel_lower in sorted(deleted_keys):
            rel_path = repo_files[rel_lower]
            src = repo_path / rel_path
            # Preserve folder structure in trash with timestamp prefix
            trash_dest = trash_path / timestamp / rel_path
            pending_ops['trashes'].append((src, trash_dest))
            trashed.append(rel_path)
    
    return SyncStats(added, modified, trashed, unchanged), pending_ops


def apply_changes(pending_ops: dict, repo_path: Path, trash_path: Path) -> SyncStats:
    """Apply the pending file operations (copies and trashes)."""
    copies = pending_ops['copies']
    trashes = pending_ops['trashes']
    
    added_count = 0
    modified_count = 0
    
    # Apply copies
    total_copies = len(copies)
    for i, (src, dst) in enumerate(copies):
        if i % 100 == 0:
            print(f"\r  Copying files... {i}/{total_copies}", end="", flush=True)
        
        is_new = not dst.exists()
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        
        if is_new:
            added_count += 1
        else:
            modified_count += 1
    
    if total_copies > 0:
        print(f"\r  Copying files... {total_copies}/{total_copies} ✓")
    
    # Apply trashes
    total_trashes = len(trashes)
    for i, (src, trash_dest) in enumerate(trashes):
        trash_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(trash_dest))
        
        # Clean up empty directories
        parent = src.parent
        while parent != repo_path:
            if not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent
            else:
                break
    
    if total_trashes > 0:
        print(f"  Moved {total_trashes} files to trash ✓")
    
    return SyncStats(
        added=[str(dst) for src, dst in copies if added_count],  # simplified
        modified=[],
        trashed=[str(src) for src, trash_dest in trashes],
        unchanged=0
    )


def print_summary(stats: SyncStats) -> None:
    """Print categorized summary of changes."""
    
    def print_files(files: list[str], action: str) -> None:
        if not files:
            return
        
        # Group by type
        by_type: dict[str, list[str]] = {}
        for f in files:
            ftype = get_file_type(f)
            by_type.setdefault(ftype, []).append(f)
        
        print(f"\n{action}:")
        for ftype in ['kit', 'synth', 'song', 'sample', 'xml', 'wav', 'other']:
            if ftype in by_type:
                type_files = by_type[ftype]
                print(f"  {ftype.upper()}S ({len(type_files)}):")
                for f in type_files[:10]:  # Show first 10
                    print(f"    {f}")
                if len(type_files) > 10:
                    print(f"    ... and {len(type_files) - 10} more")
    
    print_files(stats.added, "✚ ADDED")
    print_files(stats.modified, "✎ MODIFIED")
    print_files(stats.trashed, "🗑 MOVED TO TRASH")
    
    if not stats.added and not stats.modified and not stats.trashed:
        print("\n✓ No changes detected - repository is up to date")


def append_to_log(log_path: Path, stats: SyncStats, elapsed_secs: int, 
                  status: str, error_msg: str = "") -> None:
    """Append execution summary to scripts.log."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    elapsed_fmt = f"{elapsed_secs // 60}m {elapsed_secs % 60}s"
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    with open(log_path, 'a') as f:
        f.write("---\n")
        f.write("script: sd-to-repo.py\n")
        f.write(f"timestamp: {timestamp}\n")
        f.write(f"status: {status}\n")
        f.write(f"files_added: {len(stats.added)}\n")
        f.write(f"files_modified: {len(stats.modified)}\n")
        f.write(f"files_trashed: {len(stats.trashed)}\n")
        f.write(f"files_unchanged: {stats.unchanged}\n")
        f.write(f"elapsed: {elapsed_fmt}\n")
        if error_msg:
            f.write(f"error: {error_msg}\n")


def main() -> int:
    start_time = datetime.now()
    
    # Paths
    script_dir = Path(__file__).parent.resolve()
    repo_dir = script_dir.parent
    env_file = script_dir / '.env'
    log_file = repo_dir / 'docs' / 'scripts.log'
    
    # Load config
    env = load_env(env_file)
    if not env:
        print(f"Error: .env file not found at {env_file}")
        print("Copy .env.example to .env and configure your paths.")
        return 1
    
    sd_card_path = env.get('SD_CARD_PATH', '')
    if not sd_card_path:
        print("Error: SD_CARD_PATH must be set in .env")
        print('Example: SD_CARD_PATH="/media/$USER/DELUGE"')
        return 1
    
    sd_path = Path(sd_card_path)
    repo_deluge_path = repo_dir / 'DELUGE'
    trash_path = repo_deluge_path / '.trash'
    
    # Validate SD card
    if not sd_path.exists():
        print(f"Error: SD card not found at: {sd_path}")
        print("Please insert the Deluge SD card and verify the mount path.")
        return 1
    
    # Check for Deluge folder structure
    expected_folders = ['SAMPLES', 'KITS', 'SONGS', 'SYNTHS']
    found_folders = [f for f in expected_folders if (sd_path / f).is_dir()]
    if not found_folders:
        print(f"Error: SD card at {sd_path} doesn't look like a Deluge card.")
        print(f"Expected folders: {', '.join(expected_folders)}")
        return 1
    
    # Check for unexpected file types
    print("Scanning SD card...")
    unexpected_files = []
    for f in sd_path.rglob('*'):
        if f.is_file():
            ext = f.suffix.lower()
            if ext not in ('.xml', '.wav'):
                unexpected_files.append(str(f.relative_to(sd_path)))
    
    if unexpected_files:
        print(f"\n⚠ WARNING: Found {len(unexpected_files)} file(s) with unexpected extensions (will NOT be synced):")
        for f in unexpected_files[:20]:
            print(f"  {f}")
        if len(unexpected_files) > 20:
            print(f"  ... and {len(unexpected_files) - 20} more")
        print()
    
    # Print header
    print("=" * 50)
    print("Deluge SD Card → Repository Sync")
    print("=" * 50)
    print(f"Source:      {sd_path}")
    print(f"Destination: {repo_deluge_path}")
    print(f"Trash:       {trash_path}")
    print()
    
    # Dry-run first to show what will happen
    print("Analyzing changes...")
    try:
        stats, pending_ops = sync_files(sd_path, repo_deluge_path, trash_path, dry_run=True)
    except Exception as e:
        print(f"\n✗ Error during analysis: {e}")
        return 1
    
    # If there are changes, ask for confirmation
    if stats.added or stats.modified or stats.trashed:
        print_summary(stats)
        print()
        print("=" * 50)
        print("Review the changes above before proceeding.")
        print("=" * 50)
        
        try:
            response = input("\nApply these changes? (y/N): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            return 0
            
        if response != 'y':
            print("Aborted. No changes made.")
            return 0
        
        print()
        print("Applying changes...")
        try:
            stats = apply_changes(pending_ops, repo_deluge_path, trash_path)
        except Exception as e:
            elapsed = int((datetime.now() - start_time).total_seconds())
            print(f"\n✗ Error during sync: {e}")
            append_to_log(log_file, SyncStats([], [], [], 0), elapsed, "FAILED", str(e))
            return 1
    else:
        print("\n✓ No changes detected - repository is up to date")
    
    # Print final summary
    elapsed = int((datetime.now() - start_time).total_seconds())
    elapsed_fmt = f"{elapsed // 60}m {elapsed % 60}s"
    
    print()
    print("=" * 50)
    print("Sync complete!")
    print("=" * 50)
    print(f"Added:     {len(stats.added)}")
    print(f"Modified:  {len(stats.modified)}")
    print(f"Trashed:   {len(stats.trashed)}")
    print(f"Unchanged: {stats.unchanged}")
    print(f"Elapsed:   {elapsed_fmt}")
    
    if stats.trashed:
        print()
        print(f"💡 Trashed files are in: {trash_path}")
        print("   Review and delete manually when ready.")
    
    if stats.added or stats.modified or stats.trashed:
        print()
        print("💡 Run 'git status' to review changes before committing.")
    
    append_to_log(log_file, stats, elapsed, "SUCCESS")
    return 0


if __name__ == '__main__':
    sys.exit(main())