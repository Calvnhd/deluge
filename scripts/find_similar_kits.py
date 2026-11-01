# Work in progress: review comparison results before acting on them.
"""Find equivalent and near-duplicate kit presets without modifying them."""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

from lxml import etree

from deluge_lib.cli_utils import get_deluge_root
from deluge_lib.scanning import scan_tree

_NUMERIC_VALUE = re.compile(r"(?:-?[0-9]+|0x[0-9a-fA-F]{1,8})\Z")
_SAMPLE_FIELDS = frozenset({"fileName", "filePath"})


@dataclass(frozen=True)
class KitProfile:
    path: Path
    fields: dict[str, str]
    numeric_fields: frozenset[str]
    candidate_key: tuple[tuple[str, str | None], ...]


@dataclass(frozen=True)
class ParameterDifference:
    field: str
    left: str
    right: str


@dataclass(frozen=True)
class KitMatch:
    left: Path
    right: Path
    differences: tuple[ParameterDifference, ...]


def load_kit(path: Path) -> KitProfile:
    """Keep every XML field except kit/sound labels and selectedDrumIndex."""
    parser = etree.XMLParser(
        resolve_entities=False, no_network=True, remove_comments=True, remove_pis=True
    )
    try:
        tree = etree.parse(path, parser)
    except etree.XMLSyntaxError as exc:
        raise ValueError(f"Invalid kit XML: {path}: {exc}") from exc
    if tree.docinfo.internalDTD is not None:
        raise ValueError(f"Kit XML with a DTD is not supported: {path}")
    root = tree.getroot()
    if root.tag != "kit":
        raise ValueError(f"Expected a <kit> root in {path}, found <{root.tag}>")

    fields: dict[str, str] = {}
    numeric_fields: set[str] = set()

    def record(key: str, value: str, *, numeric: bool) -> None:
        fields[key] = value
        if numeric and _NUMERIC_VALUE.fullmatch(value):
            numeric_fields.add(key)

    def walk(element: etree._Element, location: str, *, sound_label: bool = False) -> None:
        fields[f"{location}/#element"] = str(element.tag)
        for attr, value in element.attrib.items():
            if not isinstance(attr, str) or not isinstance(value, str):
                raise ValueError(f"Expected text XML attributes in {path}")
            if attr == "name" and (element is root or sound_label):
                continue
            record(f"{location}/@{attr}", value, numeric=attr not in _SAMPLE_FIELDS)
        if element.text and element.text.strip():
            record(
                f"{location}/#text",
                element.text.strip(),
                numeric=element.tag not in _SAMPLE_FIELDS,
            )
        if element.tail and element.tail.strip():
            record(f"{location}/#tail", element.tail.strip(), numeric=False)
        children = [
            child for child in element if not (element is root and child.tag == "selectedDrumIndex")
        ]
        for index, child in enumerate(children, 1):
            walk(
                child,
                f"{location}/{child.tag}[{index}]",
                sound_label=element.tag == "soundSources" and child.tag == "sound",
            )

    walk(root, "kit")
    candidate_key = tuple(
        (key, None if key in numeric_fields else value) for key, value in sorted(fields.items())
    )
    return KitProfile(path.resolve(), fields, frozenset(numeric_fields), candidate_key)


def find_matches(
    kits: list[KitProfile],
    *,
    max_differences: int = 3,
    reference: Path | None = None,
) -> list[KitMatch]:
    """Compare only pairs with identical structure and non-numerical values."""
    if max_differences < 0:
        raise ValueError("max_differences must be zero or greater")
    reference = reference.resolve() if reference is not None else None
    groups: dict[tuple[tuple[str, str | None], ...], list[KitProfile]] = defaultdict(list)
    for kit in sorted(kits, key=lambda kit: str(kit.path)):
        groups[kit.candidate_key].append(kit)

    matches: list[KitMatch] = []
    for group in groups.values():
        for left, right in combinations(group, 2):
            if reference is not None and reference not in (left.path, right.path):
                continue
            differences: list[ParameterDifference] = []
            for key in sorted(left.numeric_fields):
                if left.fields[key] != right.fields[key]:
                    differences.append(
                        ParameterDifference(key, left.fields[key], right.fields[key])
                    )
                    if len(differences) > max_differences:
                        break
            if len(differences) <= max_differences:
                matches.append(KitMatch(left.path, right.path, tuple(differences)))
    return sorted(
        matches,
        key=lambda match: (len(match.differences), str(match.left), str(match.right)),
    )


def main(argv: list[str] | None = None) -> None:
    print("WORK IN PROGRESS: review comparison results before acting on them.")
    parser = argparse.ArgumentParser(
        description="Report equivalent and near-duplicate kits. Never changes kit files."
    )
    parser.add_argument(
        "kit", nargs="?", type=Path, help="Compare only this kit against the library"
    )
    parser.add_argument(
        "--kits-dir", type=Path, help="Kit library directory (default: DELUGE_ROOT/KITS)"
    )
    parser.add_argument(
        "--max-differences",
        type=int,
        default=3,
        help="Maximum changed numerical fields across a whole kit (default: 3; 0: equivalent only)",
    )
    args = parser.parse_args(argv)
    if args.max_differences < 0:
        parser.error("--max-differences must be zero or greater")
    kits_dir = args.kits_dir.resolve() if args.kits_dir is not None else get_deluge_root() / "KITS"
    reference = args.kit.resolve() if args.kit is not None else None
    try:
        scan = scan_tree(kits_dir, label="kits", file_filter="xml", strict=True)
        kits = [load_kit(kits_dir / entry.rel_path) for entry in scan.files.values()]
        if reference is not None and all(kit.path != reference for kit in kits):
            kits.append(load_kit(reference))
        matches = find_matches(kits, max_differences=args.max_differences, reference=reference)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Kit comparison failed: {exc}") from exc

    equivalent = sum(not match.differences for match in matches)
    print(
        f"\nScanned {len(scan.files)} kits: {equivalent} equivalent pairs, "
        f"{len(matches) - equivalent} near-duplicate pairs"
        + (" (reference kit only)." if reference is not None else ".")
    )
    print(
        "Ignores kit/sound names and selectedDrumIndex. "
        "Sample paths, sound order, structure and non-numerical values must match."
    )
    print("Near-duplicates are review candidates, not a guarantee of similar audio.")

    def label(path: Path) -> str:
        return str(path.relative_to(kits_dir)) if path.is_relative_to(kits_dir) else str(path)

    for match in matches:
        category = (
            f"NEAR ({len(match.differences)} changed fields)" if match.differences else "EQUIVALENT"
        )
        print(f"\n{category}: {label(match.left)} <-> {label(match.right)}")
        for difference in match.differences:
            print(f"  {difference.field}: {difference.left} -> {difference.right}")
    if not matches:
        print("\nNo matches within the selected threshold.")


if __name__ == "__main__":
    main()
