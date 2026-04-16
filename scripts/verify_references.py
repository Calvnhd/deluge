"""Verify that sample references in Deluge XML files point to existing files."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from deluge_lib.cli_utils import get_deluge_root
from deluge_lib.deluge_sdk import SampleRef, extract_sample_refs, find_all_xml_files
from deluge_lib.scanning import print_path, normalise_key, scan_tree

# Regex to find sample paths in raw XML text. Case-insensitive.
# Matches paths like SAMPLES/any/path.wav (possibly inside quotes or element text).
# Allows spaces in paths but stops at quotes, angle brackets, and newlines.
_SAMPLE_PATH_RE = re.compile(r"SAMPLES/[^\"'<>\t\n\r]+\.wav", re.IGNORECASE)


@dataclass
class BrokenRef:
    """A sample reference that does not resolve to an existing file."""

    xml_file: Path
    xml_type: str
    preset_name: str
    sample_path: str


class CheckResult(NamedTuple):
    """Result of checking all sample references for existence."""

    total_refs: int
    broken: list[BrokenRef]
    unextracted: list[tuple[Path, str]]


def check_references(deluge_root: Path) -> CheckResult:
    """Check that every sample reference in all XMLs resolves to an existing file.

    Args:
        deluge_root: Absolute path to the DELUGE directory.

    Returns:
        CheckResult with total count, broken references, and unextracted paths.
    """

    print("Finding all xml files...")
    xml_files = find_all_xml_files(deluge_root)
    print()

    print("Extracting sample references...")
    # Maps all xml files to a list containing all the samples that xml references (or empty if none)
    refs_by_file: dict[Path, list[SampleRef]] = {} 
    for xml_file in xml_files:
        refs_by_file[xml_file] = extract_sample_refs(xml_file, deluge_root)
    print()

    print("Finding all samples...")
    samples_dir = deluge_root / "SAMPLES"
    # case insensitive for accurate comparison. Do not write out to file
    existing_samples_normalised: set[str] = set()
    if samples_dir.is_dir():
        scan = scan_tree(samples_dir, label="SAMPLES", file_filter="wav")
        existing_samples_normalised = {normalise_key(Path("SAMPLES") / e.rel_path) for e in scan.files.values()}
    print()

    total_refs = 0
    broken: list[BrokenRef] = []
    unextracted: list[tuple[Path, str]] = []

    for xml_file, file_refs in refs_by_file.items():
        total_refs += len(file_refs)
        # Check for broken references (sample file missing on disk)
        for ref in file_refs:
            if normalise_key(ref.path) not in existing_samples_normalised:
                broken.append(
                    BrokenRef(
                        xml_file=ref.xml_file,
                        xml_type=ref.xml_type,
                        preset_name=ref.preset_name,
                        sample_path=ref.path,
                    )
                )
        # Check for refs the structured extractor might have missed
        # No normalisation because both sets of paths for comparison are from the same file
        relative_path = xml_file.resolve().relative_to(deluge_root.resolve())
        raw_paths = set(_SAMPLE_PATH_RE.findall(xml_file.read_text(encoding="utf-8")))
        extracted_paths = {ref.path for ref in file_refs}
        for sample_path in (raw_paths - extracted_paths):
            unextracted.append((relative_path, sample_path))

    return CheckResult(
        total_refs=total_refs, broken=broken, unextracted=unextracted
    )

def main(argv: list[str] | None = None) -> None:  # noqa: ARG001
    """CLI entry point for the reference verifier.
    """
    deluge_root = get_deluge_root()
    result = check_references(deluge_root)

    print("===== RESULTS =====")
    print()

    # Reference check results
    if result.broken:
        print(f"Broken references ({len(result.broken)}):")
        for ref in result.broken:
            if ref.xml_type == "song":
                print(f"  {print_path(ref.xml_file)} ({ref.preset_name}) — {ref.sample_path}")
            else:
                print(f"  {print_path(ref.xml_file)} — {ref.sample_path}")
    else:
        print("All references valid.")

    # Unextracted warnings
    if result.unextracted:
        print()
        print(f"Unextracted sample paths ({len(result.unextracted)}):")
        for xml_file, sample_path in result.unextracted:
            print(f"  {print_path(xml_file)} — {sample_path}")

    # Summary
    print()
    print(
        f"Summary: {result.total_refs} references checked, "
        f"{len(result.broken)} broken "
    )
    print()

if __name__ == "__main__":
    main()
