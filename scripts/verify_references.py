"""Verify that sample references in Deluge XML files point to existing files."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from lxml import etree

from deluge_lib.cli_utils import get_deluge_root
from deluge_lib.deluge_sdk import SampleRef, extract_sample_refs, find_all_xml_files

# Regex to find sample paths in raw XML text. Case-insensitive.
# Matches paths like SAMPLES/any/path.wav (possibly inside quotes or element text).
_SAMPLE_PATH_RE = re.compile(r"SAMPLES/[^\s\"'<>]+\.wav", re.IGNORECASE)

# Directories under SAMPLES/ that should exist
_SPECIAL_DIRS = ("CLIPS", "RECORD", "RESAMPLE")


@dataclass
class BrokenRef:
    """A sample reference that does not resolve to an existing file."""

    xml_file: Path
    preset_name: str
    sample_path: str


class CheckResult(NamedTuple):
    """Result of checking all sample references for existence."""

    total_refs: int
    broken: list[BrokenRef]
    unextracted: list[tuple[Path, str]]


def find_unextracted_refs(
    xml_path: Path, extracted_refs: list[SampleRef]
) -> list[str]:
    """Regex-scan raw XML text for sample paths not found by extract_sample_refs().

    Args:
        xml_path: Absolute path to the XML file.
        extracted_refs: The refs already extracted by extract_sample_refs() for this file.

    Returns:
        List of sample paths found in raw text but not in extracted refs.
    """
    raw_text = xml_path.read_text(encoding="utf-8")
    raw_paths = set(_SAMPLE_PATH_RE.findall(raw_text))

    extracted_paths = {ref.path for ref in extracted_refs}

    return sorted(raw_paths - extracted_paths)


def check_references(deluge_root: Path) -> CheckResult:
    """Check that every sample reference in all XMLs resolves to an existing file.

    Args:
        deluge_root: Absolute path to the DELUGE directory.

    Returns:
        CheckResult with total count, broken references, and unextracted paths.
    """
    xml_files = find_all_xml_files(deluge_root)

    all_refs: list[SampleRef] = []
    refs_by_file: dict[Path, list[SampleRef]] = {}
    for xml_file in xml_files:
        try:
            file_refs = extract_sample_refs(xml_file, deluge_root)
        except etree.XMLSyntaxError as e:
            relative_path = xml_file.resolve().relative_to(deluge_root.resolve())
            print(f"Warning: skipping {relative_path} (malformed XML: {e})")
            continue
        all_refs.extend(file_refs)
        refs_by_file[xml_file] = file_refs

    broken: list[BrokenRef] = []
    for ref in all_refs:
        sample_full_path = deluge_root / ref.path
        if not sample_full_path.is_file():
            broken.append(
                BrokenRef(
                    xml_file=ref.xml_file,
                    preset_name=ref.preset_name,
                    sample_path=ref.path,
                )
            )

    unextracted: list[tuple[Path, str]] = []
    for xml_file, file_refs in refs_by_file.items():
        relative_path = xml_file.resolve().relative_to(deluge_root.resolve())
        for sample_path in find_unextracted_refs(xml_file, file_refs):
            unextracted.append((relative_path, sample_path))

    return CheckResult(
        total_refs=len(all_refs), broken=broken, unextracted=unextracted
    )


def check_special_dirs(deluge_root: Path) -> list[str]:
    """Check that SAMPLES/CLIPS, SAMPLES/RECORD, SAMPLES/RESAMPLE exist.

    Missing directories are reported as warnings (they may not exist on a fresh
    setup). Subdirectories within these dirs are allowed — the firmware creates
    them legitimately.

    Args:
        deluge_root: Absolute path to the DELUGE directory.

    Returns:
        List of missing directory names (e.g. ["SAMPLES/CLIPS"]). Empty if all exist.
    """
    samples_dir = deluge_root / "SAMPLES"
    return [
        f"SAMPLES/{name}"
        for name in _SPECIAL_DIRS
        if not (samples_dir / name).is_dir()
    ]


def main(argv: list[str] | None = None) -> None:  # noqa: ARG001
    """CLI entry point for the reference verifier.

    Exit code 0 = all references valid. Exit code 1 = broken references found.
    Missing special directories are warnings only and do not affect the exit code.
    """
    deluge_root = get_deluge_root()

    result = check_references(deluge_root)

    # Reference check results
    if result.broken:
        print(f"Broken references ({len(result.broken)}):")
        for ref in result.broken:
            print(f"  {ref.xml_file} ({ref.preset_name}): {ref.sample_path}")
    else:
        print("All references valid.")

    # Unextracted warnings
    if result.unextracted:
        print()
        print(f"Unextracted sample paths ({len(result.unextracted)}):")
        for xml_file, sample_path in result.unextracted:
            print(f"  {xml_file}: {sample_path}")

    # Directory check results
    missing_dirs = check_special_dirs(deluge_root)
    if missing_dirs:
        print()
        print("Missing special directories (warning):")
        for d in missing_dirs:
            print(f"  {d}")

    # Summary
    print()
    print(
        f"Summary: {result.total_refs} references checked, "
        f"{len(result.broken)} broken, "
        f"{len(result.unextracted)} unextracted warnings, "
        f"{len(missing_dirs)} directory warnings"
    )

    sys.exit(1 if result.broken else 0)


if __name__ == "__main__":
    main()
