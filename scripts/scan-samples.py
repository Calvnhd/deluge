#!/usr/bin/env python3
"""
Scan SAMPLES folder and create a hash manifest for detecting moved files.

This script generates a JSON manifest containing SHA256 hashes of all sample files,
enabling detection of files that have been moved or renamed during reorganization.

Usage:
    # BEFORE reorganizing - create baseline manifest
    python scripts/scan-samples.py --before
    
    # AFTER reorganizing - detect moves and generate migration map
    python scripts/scan-samples.py --after
    
    # Custom paths
    python scripts/scan-samples.py --before --samples-dir /path/to/SAMPLES --output manifest.json

Output files (in docs/):
    - sample-manifest-before.json: Baseline manifest (hash -> path mapping)
    - sample-manifest-after.json: Post-reorganization manifest
    - sample-migration-map.json: Mapping of old paths -> new paths for moved files

IMPORTANT: This script is READ-ONLY with respect to the DELUGE/ folder.
It only reads files to compute hashes and writes output to docs/.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Iterator


# =============================================================================
# Configuration
# =============================================================================

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
DELUGE_DIR = PROJECT_ROOT / "DELUGE"
SAMPLES_DIR = DELUGE_DIR / "SAMPLES"
DOCS_DIR = PROJECT_ROOT / "docs"

# Sample file extensions to scan (case-insensitive)
SAMPLE_EXTENSIONS = {'.wav', '.aif', '.aiff'}

# Manifest filenames
MANIFEST_BEFORE = "sample-manifest-before.json"
MANIFEST_AFTER = "sample-manifest-after.json"
MIGRATION_MAP = "sample-migration-map.json"


# =============================================================================
# Hashing Functions
# =============================================================================

def compute_file_hash(file_path: Path, algorithm: str = 'sha256') -> str:
    """
    Compute hash of a file using streaming to handle large files.
    
    Args:
        file_path: Path to the file
        algorithm: Hash algorithm ('sha256', 'md5', etc.)
        
    Returns:
        Hex digest of the file hash
        
    Raises:
        IOError: If file cannot be read
    """
    hasher = hashlib.new(algorithm)
    buffer_size = 65536  # 64KB chunks
    
    with open(file_path, 'rb') as f:
        while True:
            data = f.read(buffer_size)
            if not data:
                break
            hasher.update(data)
    
    return hasher.hexdigest()


def find_sample_files(samples_dir: Path) -> Iterator[Path]:
    """
    Recursively find all sample files in a directory.
    
    Args:
        samples_dir: Root directory to search
        
    Yields:
        Path objects for each sample file found
    """
    if not samples_dir.exists():
        raise FileNotFoundError(f"Samples directory not found: {samples_dir}")
    
    for file_path in samples_dir.rglob('*'):
        if file_path.is_file() and file_path.suffix.lower() in SAMPLE_EXTENSIONS:
            yield file_path


# =============================================================================
# Manifest Operations
# =============================================================================

def create_manifest(samples_dir: Path, show_progress: bool = True) -> dict:
    """
    Create a manifest of all samples with their hashes.
    
    The manifest structure:
    {
        "created": "2026-01-29T10:30:00",
        "samples_dir": "/path/to/SAMPLES",
        "total_files": 1234,
        "total_bytes": 5678901234,
        "by_hash": {
            "<sha256>": {
                "path": "SAMPLES/relative/path.wav",
                "size": 12345,
                "modified": "2026-01-15T08:20:00"
            },
            ...
        },
        "by_path": {
            "SAMPLES/relative/path.wav": "<sha256>",
            ...
        },
        "duplicates": {
            "<sha256>": ["path1.wav", "path2.wav"],
            ...
        }
    }
    
    Args:
        samples_dir: Root samples directory
        show_progress: Whether to print progress updates
        
    Returns:
        Manifest dictionary
    """
    manifest = {
        "created": datetime.now().isoformat(),
        "samples_dir": str(samples_dir.resolve()),
        "total_files": 0,
        "total_bytes": 0,
        "by_hash": {},
        "by_path": {},
        "duplicates": {},
    }
    
    # Get base path for relative paths (parent of SAMPLES, i.e., DELUGE/)
    base_path = samples_dir.parent
    
    # First pass: count files for progress
    files = list(find_sample_files(samples_dir))
    total_files = len(files)
    
    if show_progress:
        print(f"Found {total_files} sample files to hash...")
    
    # Second pass: compute hashes
    for i, file_path in enumerate(files, 1):
        if show_progress and i % 100 == 0:
            print(f"  Processing {i}/{total_files}...")
        
        try:
            file_hash = compute_file_hash(file_path)
            file_stat = file_path.stat()
            rel_path = str(file_path.relative_to(base_path))
            
            # Normalize path separators for cross-platform consistency
            rel_path = rel_path.replace('\\', '/')
            
            file_info = {
                "path": rel_path,
                "size": file_stat.st_size,
                "modified": datetime.fromtimestamp(file_stat.st_mtime).isoformat(),
            }
            
            # Track by path
            manifest["by_path"][rel_path] = file_hash
            
            # Track by hash (detect duplicates)
            if file_hash in manifest["by_hash"]:
                # Duplicate found
                existing_path = manifest["by_hash"][file_hash]["path"]
                if file_hash not in manifest["duplicates"]:
                    manifest["duplicates"][file_hash] = [existing_path]
                manifest["duplicates"][file_hash].append(rel_path)
            else:
                manifest["by_hash"][file_hash] = file_info
            
            manifest["total_files"] += 1
            manifest["total_bytes"] += file_stat.st_size
            
        except (IOError, OSError) as e:
            print(f"  WARNING: Could not process {file_path}: {e}", file=sys.stderr)
    
    if show_progress:
        print(f"Processed {manifest['total_files']} files ({manifest['total_bytes']:,} bytes)")
        if manifest["duplicates"]:
            print(f"Found {len(manifest['duplicates'])} sets of duplicate files")
    
    return manifest


def generate_migration_map(before_manifest: dict, after_manifest: dict) -> dict:
    """
    Compare before/after manifests and generate a migration map.
    
    The migration map structure:
    {
        "created": "2026-01-29T10:30:00",
        "moves": {
            "SAMPLES/old/path.wav": "SAMPLES/new/path.wav",
            ...
        },
        "added": ["SAMPLES/new/file.wav", ...],
        "deleted": ["SAMPLES/removed/file.wav", ...],
        "unchanged": 1234,
        "ambiguous": {
            "<sha256>": {
                "old_paths": ["path1.wav", "path2.wav"],
                "new_paths": ["path3.wav", "path4.wav"]
            }
        }
    }
    
    Args:
        before_manifest: Manifest from before reorganization
        after_manifest: Manifest from after reorganization
        
    Returns:
        Migration map dictionary
    """
    migration = {
        "created": datetime.now().isoformat(),
        "moves": {},
        "added": [],
        "deleted": [],
        "unchanged": 0,
        "ambiguous": {},
    }
    
    before_by_hash = before_manifest["by_hash"]
    after_by_hash = after_manifest["by_hash"]
    before_by_path = before_manifest["by_path"]
    after_by_path = after_manifest["by_path"]
    before_duplicates = before_manifest.get("duplicates", {})
    after_duplicates = after_manifest.get("duplicates", {})
    
    # Track which paths we've matched
    matched_old_paths = set()
    matched_new_paths = set()
    
    # Find moves: same hash, different path
    for file_hash, after_info in after_by_hash.items():
        after_path = after_info["path"]
        
        if file_hash in before_by_hash:
            before_path = before_by_hash[file_hash]["path"]
            
            # Check for duplicates - these need special handling
            has_before_dupes = file_hash in before_duplicates
            has_after_dupes = file_hash in after_duplicates
            
            if has_before_dupes or has_after_dupes:
                # Ambiguous case: multiple files with same hash
                old_paths = before_duplicates.get(file_hash, [before_path])
                if before_path not in old_paths:
                    old_paths = [before_path] + list(old_paths)
                new_paths = after_duplicates.get(file_hash, [after_path])
                if after_path not in new_paths:
                    new_paths = [after_path] + list(new_paths)
                
                migration["ambiguous"][file_hash] = {
                    "old_paths": old_paths,
                    "new_paths": new_paths,
                }
                matched_old_paths.update(old_paths)
                matched_new_paths.update(new_paths)
            elif before_path != after_path:
                # Clear move: single file changed location
                migration["moves"][before_path] = after_path
                matched_old_paths.add(before_path)
                matched_new_paths.add(after_path)
            else:
                # Unchanged
                migration["unchanged"] += 1
                matched_old_paths.add(before_path)
                matched_new_paths.add(after_path)
        else:
            # New file (hash not seen before)
            if after_path not in matched_new_paths:
                migration["added"].append(after_path)
                matched_new_paths.add(after_path)
    
    # Find deleted files (in before but not in after)
    for old_path in before_by_path:
        if old_path not in matched_old_paths:
            migration["deleted"].append(old_path)
    
    # Sort lists for consistent output
    migration["added"].sort()
    migration["deleted"].sort()
    
    return migration


def save_manifest(manifest: dict, output_path: Path) -> None:
    """Save manifest to JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)
    print(f"Saved: {output_path}")


def load_manifest(input_path: Path) -> dict:
    """Load manifest from JSON file."""
    with open(input_path, 'r', encoding='utf-8') as f:
        return json.load(f)


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Scan samples and create hash manifest for detecting moved files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Before reorganizing samples
    python scripts/scan-samples.py --before
    
    # After reorganizing samples
    python scripts/scan-samples.py --after
    
    # Check what the migration map would contain (dry run)
    python scripts/scan-samples.py --after --dry-run
        """
    )
    
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        '--before',
        action='store_true',
        help='Create baseline manifest before reorganizing samples'
    )
    mode_group.add_argument(
        '--after',
        action='store_true',
        help='Create post-reorganization manifest and generate migration map'
    )
    
    parser.add_argument(
        '--samples-dir',
        type=Path,
        default=SAMPLES_DIR,
        help=f'Path to SAMPLES directory (default: {SAMPLES_DIR})'
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=DOCS_DIR,
        help=f'Directory for output files (default: {DOCS_DIR})'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without writing files'
    )
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress progress output'
    )
    
    args = parser.parse_args()
    
    # Validate samples directory
    if not args.samples_dir.exists():
        print(f"ERROR: Samples directory not found: {args.samples_dir}", file=sys.stderr)
        sys.exit(1)
    
    if args.before:
        # Create baseline manifest
        print(f"Scanning samples in: {args.samples_dir}")
        manifest = create_manifest(args.samples_dir, show_progress=not args.quiet)
        
        output_path = args.output_dir / MANIFEST_BEFORE
        if args.dry_run:
            print(f"\nDry run - would save to: {output_path}")
            print(f"  Total files: {manifest['total_files']}")
            print(f"  Total size: {manifest['total_bytes']:,} bytes")
        else:
            save_manifest(manifest, output_path)
            print(f"\nBaseline manifest created. Now reorganize your samples, then run:")
            print(f"  python scripts/scan-samples.py --after")
    
    elif args.after:
        # Load before manifest
        before_path = args.output_dir / MANIFEST_BEFORE
        if not before_path.exists():
            print(f"ERROR: Baseline manifest not found: {before_path}", file=sys.stderr)
            print("Run with --before first to create the baseline.", file=sys.stderr)
            sys.exit(1)
        
        print(f"Loading baseline manifest: {before_path}")
        before_manifest = load_manifest(before_path)
        
        # Create after manifest
        print(f"Scanning samples in: {args.samples_dir}")
        after_manifest = create_manifest(args.samples_dir, show_progress=not args.quiet)
        
        # Generate migration map
        print("\nComparing manifests...")
        migration = generate_migration_map(before_manifest, after_manifest)
        
        # Report summary
        print(f"\nMigration Summary:")
        print(f"  Unchanged: {migration['unchanged']} files")
        print(f"  Moved:     {len(migration['moves'])} files")
        print(f"  Added:     {len(migration['added'])} files")
        print(f"  Deleted:   {len(migration['deleted'])} files")
        print(f"  Ambiguous: {len(migration['ambiguous'])} sets (duplicates with same hash)")
        
        if migration['ambiguous']:
            print("\n  WARNING: Ambiguous moves detected (duplicate files).")
            print("  Review sample-migration-map.json and manually resolve 'ambiguous' entries.")
        
        if args.dry_run:
            print(f"\nDry run - would save to:")
            print(f"  {args.output_dir / MANIFEST_AFTER}")
            print(f"  {args.output_dir / MIGRATION_MAP}")
            
            if migration['moves']:
                print("\nSample moves detected:")
                for old_path, new_path in list(migration['moves'].items())[:10]:
                    print(f"  {old_path}")
                    print(f"    -> {new_path}")
                if len(migration['moves']) > 10:
                    print(f"  ... and {len(migration['moves']) - 10} more")
        else:
            save_manifest(after_manifest, args.output_dir / MANIFEST_AFTER)
            save_manifest(migration, args.output_dir / MIGRATION_MAP)
            
            if migration['moves']:
                print(f"\nMigration map created. To update XML references, run:")
                print(f"  python scripts/update-refs.py --dry-run")
                print(f"  python scripts/update-refs.py")
            else:
                print("\nNo file moves detected - no XML updates needed.")


if __name__ == '__main__':
    main()
