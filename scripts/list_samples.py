"""List all sample paths referenced across Deluge XML files."""

from __future__ import annotations

import sys
from pathlib import Path

from lxml import etree

from deluge_lib.cli_utils import get_deluge_root
from deluge_lib.deluge_sdk import extract_sample_refs, find_all_xml_files


def collect_sample_paths(deluge_root: Path) -> list[str]:
    """Return a deduplicated, sorted list of all sample paths across XMLs."""
    xml_files = find_all_xml_files(deluge_root)
    paths: set[str] = set()

    for xml_file in xml_files:
        try:
            refs = extract_sample_refs(xml_file, deluge_root)
        except etree.XMLSyntaxError as e:
            relative_path = xml_file.resolve().relative_to(deluge_root.resolve())
            print(f"Warning: skipping {relative_path} (malformed XML: {e})")
            continue
        for ref in refs:
            paths.add(ref.path)

    return sorted(paths)


def main(argv: list[str] | None = None) -> None:  # noqa: ARG001
    """Print all unique sample paths referenced in Deluge XMLs."""
    deluge_root = get_deluge_root()
    sample_paths = collect_sample_paths(deluge_root)

    for path in sample_paths:
        print(path)

    print(f"\n{len(sample_paths)} unique samples referenced.")


if __name__ == "__main__":
    main()
