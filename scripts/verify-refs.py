#!/usr/bin/env python3
"""
Verify sample references in Deluge XML files.

This script scans all XML files and checks that every referenced sample
actually exists on disk. Useful for:
- Pre-flight check before reorganizing samples
- Post-migration verification
- Finding broken references after manual edits

Usage:
    # Check all XML files for broken references
    python scripts/verify-refs.py
    
    # Show all references (not just broken ones)
    python scripts/verify-refs.py --all
    
    # Export results to JSON
    python scripts/verify-refs.py --output results.json

IMPORTANT: This script is READ-ONLY. It only reads XML files and checks
if referenced samples exist on disk.

Known Limitations:
    - Firmware updates may introduce new XML formats not yet supported
    - Some sample references may use relative paths in unexpected ways
"""

import argparse
import json
import re
import sys
from pathlib import Path
from collections import defaultdict
from typing import Iterator


# =============================================================================
# Configuration
# =============================================================================

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
DELUGE_DIR = PROJECT_ROOT / "DELUGE"

# Directories containing XML files
XML_DIRS = [
    DELUGE_DIR / "KITS",
    DELUGE_DIR / "SYNTHS",
    DELUGE_DIR / "SONGS",
]

SAMPLES_DIR = DELUGE_DIR / "SAMPLES"


# =============================================================================
# File Discovery
# =============================================================================

def find_xml_files(directories: list[Path]) -> Iterator[Path]:
    """Find all XML files in directories (recursive)."""
    for directory in directories:
        if directory.exists():
            for xml_path in directory.rglob('*.XML'):
                yield xml_path
            for xml_path in directory.rglob('*.xml'):
                yield xml_path


def find_sample_references(xml_content: str) -> list[str]:
    """
    Find all sample path references in XML content.
    
    Returns:
        List of sample paths found
    """
    references = []
    
    # Pattern 1: <fileName>SAMPLES/...</fileName>
    pattern1 = re.compile(r'<fileName>(SAMPLES/[^<]+)</fileName>', re.IGNORECASE)
    for match in pattern1.finditer(xml_content):
        references.append(match.group(1))
    
    # Pattern 2: fileName="SAMPLES/..."
    pattern2 = re.compile(r'fileName="(SAMPLES/[^"]+)"', re.IGNORECASE)
    for match in pattern2.finditer(xml_content):
        references.append(match.group(1))
    
    # Pattern 3: filePath="SAMPLES/..."
    pattern3 = re.compile(r'filePath="(SAMPLES/[^"]+)"', re.IGNORECASE)
    for match in pattern3.finditer(xml_content):
        references.append(match.group(1))
    
    return references


# =============================================================================
# Verification
# =============================================================================

def verify_sample_exists(sample_path: str, base_dir: Path) -> bool:
    """
    Check if a sample file exists.
    
    Args:
        sample_path: Relative path like "SAMPLES/DRUMS/kick.wav"
        base_dir: Base directory (DELUGE/)
        
    Returns:
        True if file exists
    """
    # Normalize path separators
    normalized = sample_path.replace('\\', '/')
    full_path = base_dir / normalized
    return full_path.exists()


def verify_xml_file(xml_path: Path, base_dir: Path) -> dict:
    """
    Verify all sample references in an XML file.
    
    Returns:
        Dict with verification results
    """
    result = {
        "path": str(xml_path),
        "total_refs": 0,
        "valid_refs": [],
        "broken_refs": [],
        "error": None,
    }
    
    try:
        with open(xml_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        try:
            with open(xml_path, 'r', encoding='latin-1') as f:
                content = f.read()
        except Exception as e:
            result["error"] = str(e)
            return result
    except Exception as e:
        result["error"] = str(e)
        return result
    
    references = find_sample_references(content)
    result["total_refs"] = len(references)
    
    # Deduplicate while preserving order
    seen = set()
    unique_refs = []
    for ref in references:
        normalized = ref.replace('\\', '/')
        if normalized not in seen:
            seen.add(normalized)
            unique_refs.append(ref)
    
    for ref in unique_refs:
        if verify_sample_exists(ref, base_dir):
            result["valid_refs"].append(ref)
        else:
            result["broken_refs"].append(ref)
    
    return result


# =============================================================================
# Reporting
# =============================================================================

def print_summary(results: list[dict]) -> None:
    """Print verification summary."""
    total_files = len(results)
    files_with_refs = len([r for r in results if r["total_refs"] > 0])
    files_with_broken = len([r for r in results if r["broken_refs"]])
    files_with_errors = len([r for r in results if r["error"]])
    
    total_refs = sum(r["total_refs"] for r in results)
    total_broken = sum(len(r["broken_refs"]) for r in results)
    
    # Collect unique broken paths
    all_broken = set()
    for r in results:
        all_broken.update(r["broken_refs"])
    
    print(f"\nVerification Summary:")
    print(f"  XML files scanned:     {total_files}")
    print(f"  Files with samples:    {files_with_refs}")
    print(f"  Files with broken refs: {files_with_broken}")
    print(f"  Total sample refs:     {total_refs}")
    print(f"  Broken references:     {total_broken} ({len(all_broken)} unique)")
    
    if files_with_errors:
        print(f"\n  Errors: {files_with_errors} files could not be read")


def print_broken_refs(results: list[dict], show_files: bool = True) -> None:
    """Print details of broken references."""
    files_with_broken = [r for r in results if r["broken_refs"]]
    
    if not files_with_broken:
        print("\n✓ All sample references are valid!")
        return
    
    print(f"\nBroken References Found:")
    
    if show_files:
        for r in files_with_broken:
            rel_path = Path(r["path"])
            try:
                rel_path = rel_path.relative_to(PROJECT_ROOT)
            except ValueError:
                pass
            print(f"\n  {rel_path}:")
            for ref in r["broken_refs"]:
                print(f"    ✗ {ref}")
    else:
        # Group by sample path
        broken_by_sample = defaultdict(list)
        for r in files_with_broken:
            for ref in r["broken_refs"]:
                broken_by_sample[ref].append(r["path"])
        
        for sample_path in sorted(broken_by_sample.keys()):
            files = broken_by_sample[sample_path]
            print(f"\n  ✗ {sample_path}")
            print(f"    Referenced by {len(files)} file(s)")


def print_all_refs(results: list[dict]) -> None:
    """Print all sample references (valid and broken)."""
    files_with_refs = [r for r in results if r["total_refs"] > 0]
    
    for r in files_with_refs:
        rel_path = Path(r["path"])
        try:
            rel_path = rel_path.relative_to(PROJECT_ROOT)
        except ValueError:
            pass
        
        print(f"\n{rel_path}:")
        
        for ref in r["valid_refs"]:
            print(f"  ✓ {ref}")
        
        for ref in r["broken_refs"]:
            print(f"  ✗ {ref}")


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Verify sample references in Deluge XML files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Check for broken references
    python scripts/verify-refs.py
    
    # Group broken refs by sample (instead of by file)
    python scripts/verify-refs.py --by-sample
    
    # Show all references (valid and broken)
    python scripts/verify-refs.py --all
    
    # Export results to JSON
    python scripts/verify-refs.py --output verify-results.json
        """
    )
    
    parser.add_argument(
        '--xml-dirs',
        type=Path,
        nargs='+',
        default=XML_DIRS,
        help='Directories containing XML files to check'
    )
    parser.add_argument(
        '--deluge-dir',
        type=Path,
        default=DELUGE_DIR,
        help=f'Base DELUGE directory (default: {DELUGE_DIR})'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Show all references, not just broken ones'
    )
    parser.add_argument(
        '--by-sample',
        action='store_true',
        help='Group broken references by sample path instead of by file'
    )
    parser.add_argument(
        '--output',
        type=Path,
        help='Export results to JSON file'
    )
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress progress output'
    )
    
    args = parser.parse_args()
    
    # Validate directories
    if not args.deluge_dir.exists():
        print(f"ERROR: DELUGE directory not found: {args.deluge_dir}", file=sys.stderr)
        sys.exit(1)
    
    # Find XML files
    if not args.quiet:
        print(f"Scanning for XML files...")
    
    xml_files = list(find_xml_files(args.xml_dirs))
    
    if not xml_files:
        print("No XML files found.")
        sys.exit(0)
    
    if not args.quiet:
        print(f"Found {len(xml_files)} XML files to verify...")
    
    # Verify each file
    results = []
    for i, xml_path in enumerate(xml_files, 1):
        if not args.quiet and i % 20 == 0:
            print(f"  Verifying {i}/{len(xml_files)}...")
        
        result = verify_xml_file(xml_path, args.deluge_dir)
        results.append(result)
    
    # Output results
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        print(f"\nResults exported to: {args.output}")
    
    if args.all:
        print_all_refs(results)
    else:
        print_broken_refs(results, show_files=not args.by_sample)
    
    print_summary(results)
    
    # Exit with error code if broken refs found
    broken_count = sum(len(r["broken_refs"]) for r in results)
    if broken_count > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
