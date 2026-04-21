"""Sample library overview — cross-referenced reports for the Deluge sample library."""

from __future__ import annotations

import argparse
from collections import defaultdict

from deluge_lib.analysis import (
    SampleUsage,
    build_usage_index,
    compute_folder_breakdown,
    compute_summary,
    filter_by_pattern,
    top_by_refs,
)
from deluge_lib.cli_utils import get_deluge_root
from deluge_lib.deluge_sdk import SampleRef, extract_sample_refs, find_all_xml_files
from deluge_lib.scanning import format_size, print_path, scan_tree

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _top_folder(path: str) -> str:
    """Extract the first path component (top-level folder under SAMPLES/)."""
    slash = path.find("/")
    if slash == -1:
        return ""
    return path[:slash]


def _group_by_folder(
    samples: list[SampleUsage],
) -> dict[str, list[SampleUsage]]:
    """Group samples by top-level folder, sorted alphabetically by folder."""
    groups: dict[str, list[SampleUsage]] = defaultdict(list)
    for s in samples:
        groups[_top_folder(s.path)].append(s)
    return dict(sorted(groups.items()))


def _format_ref(ref: SampleRef) -> str:
    """Format a single SampleRef for display.

    Songs show ``→ presetName`` after the XML filename.
    """
    xml_name = print_path(ref.xml_file)
    if ref.xml_type == "song":
        return f"{xml_name} \u2192 {ref.preset_name} ({ref.xml_type})"
    return f"{xml_name} ({ref.xml_type})"


# ---------------------------------------------------------------------------
# Subcommand: summary
# ---------------------------------------------------------------------------


def cmd_summary(index, args):
    """Print the library overview with totals, folder breakdown, and top refs."""
    summary = compute_summary(index)
    folders = compute_folder_breakdown(index)
    top_n = args.top

    print()
    print("=======================")
    print("Sample Library Overview")
    print("=======================")
    print()
    print(f"On disk:       {summary.on_disk_count:,} samples ({format_size(summary.on_disk_size)})")
    print(f"Referenced:    {summary.referenced_count:,} samples ({format_size(summary.referenced_size)})")
    print(f"Unreferenced:  {summary.unreferenced_count:,} samples ({format_size(summary.unreferenced_size)})")
    print(f"Missing:       {summary.missing_count:,} samples")
    print()

    if folders:
        print("By folder:")
        max_name = max(len(f.folder) + 1 for f in folders)  # +1 for trailing /
        for f in folders:
            name = f"{f.folder}/" if f.folder else "(root)"
            print(f"  {name:<{max_name}}  {f.file_count:>6,} files   {format_size(f.total_size):>8}")
        print()

    top = top_by_refs(index, top_n)
    if top:
        print(f"Top {top_n} most-referenced:")
        for s in top:
            print(f"  {print_path(s.path):<45} {s.ref_count:>4} refs")
        print()


# ---------------------------------------------------------------------------
# Subcommand: unused
# ---------------------------------------------------------------------------


def cmd_unused(index, args):
    """Print unreferenced samples, grouped by folder or as a flat top-N list."""
    unreferenced = list(index.unreferenced.values())
    total_count = len(unreferenced)
    total_size = sum(s.size or 0 for s in unreferenced)

    if args.top is not None:
        top = sorted(unreferenced, key=lambda u: u.size or 0, reverse=True)[: args.top]
        header = f"Top {args.top} largest unreferenced samples ({total_count:,} total, {format_size(total_size)})"
        print(header)
        print("=" * len(header))
        for s in top:
            print(f"  {print_path(s.path):<45} {format_size(s.size or 0):>8}")
        return

    header = f"Unreferenced samples ({total_count:,} files, {format_size(total_size)})"
    print(header)
    print("=" * len(header))

    groups = _group_by_folder(unreferenced)
    for folder, samples in groups.items():
        samples.sort(key=lambda s: s.size or 0, reverse=True)
        folder_size = sum(s.size or 0 for s in samples)
        label = f"{folder}/" if folder else "(root)"
        print()
        print(f"{label} \u2014 {len(samples):,} files, {format_size(folder_size)}")
        for s in samples:
            print(f"  {print_path(s.path):<45} {format_size(s.size or 0):>8}")


# ---------------------------------------------------------------------------
# Subcommand: missing
# ---------------------------------------------------------------------------


def cmd_missing(index, _args):
    """Print samples referenced in XML but missing from disk."""
    missing = list(index.missing.values())

    if not missing:
        print("All referenced samples found on disk.")
        return

    header = f"Missing samples ({len(missing):,})"
    print(header)
    print("=" * len(header))

    groups = _group_by_folder(missing)
    for folder, samples in groups.items():
        samples.sort(key=lambda s: s.path.lower())
        label = f"{folder}/" if folder else "(root)"
        print()
        print(label)
        for s in samples:
            print(f"  {print_path(s.path)}")
            for ref in sorted(s.refs, key=lambda r: (str(r.xml_file), r.preset_name)):
                print(f"    {_format_ref(ref)}")


# ---------------------------------------------------------------------------
# Subcommand: usage
# ---------------------------------------------------------------------------


def cmd_usage(index, args):
    """Print usage detail for samples matching a pattern."""
    matches = filter_by_pattern(index, args.pattern)

    if not matches:
        print(f'No samples matching "{args.pattern}".')
        return

    header = f'Samples matching "{args.pattern}" ({len(matches):,} matches)'
    print(header)
    print("=" * len(header))

    groups = _group_by_folder(matches)
    for folder, samples in groups.items():
        samples.sort(key=lambda s: s.path.lower())
        label = f"{folder}/" if folder else "(root)"
        print()
        print(label)
        for s in samples:
            size_str = f" ({format_size(s.size)})" if s.size is not None else ""
            print(f"  {print_path(s.path)}{size_str}")
            for ref in sorted(s.refs, key=lambda r: (str(r.xml_file), r.preset_name)):
                print(f"    {_format_ref(ref)}")
            if s.ref_count > 0:
                label_text = "shared" if s.ref_count > 1 else "exclusive"
                print(f"    {s.ref_count} {'ref' if s.ref_count == 1 else 'refs'} ({label_text})")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="sample_overview",
        description="Sample library overview \u2014 cross-referenced reports for the Deluge sample library.",
    )
    subparsers = parser.add_subparsers(dest="command")

    # summary
    sp_summary = subparsers.add_parser(
        "summary", help="Library overview with totals and folder breakdown"
    )
    sp_summary.add_argument(
        "--top",
        type=int,
        default=5,
        help="Number of top-referenced samples to show (default: 5)",
    )

    # unused
    sp_unused = subparsers.add_parser("unused", help="List unreferenced samples")
    sp_unused.add_argument(
        "--top",
        type=int,
        default=None,
        help="Show only the N largest unreferenced samples",
    )

    # missing
    subparsers.add_parser(
        "missing",
        help="List samples referenced in XML but missing from disk",
        epilog="For thorough verification including regex fallback, use verify_references.py",
    )

    # usage
    sp_usage = subparsers.add_parser(
        "usage", help="Show usage detail for samples matching a pattern"
    )
    sp_usage.add_argument(
        "pattern",
        metavar="PATTERN",
        help="Case-insensitive substring to match against sample paths",
    )

    args = parser.parse_args(argv)

    # Default to summary when no subcommand is given
    if args.command is None:
        args.command = "summary"
        args.top = 5

    # Data collection — shared by all subcommands
    deluge_root = get_deluge_root()
    sample_scan = scan_tree(deluge_root / "SAMPLES", label="SAMPLES", file_filter="wav")
    xml_files = find_all_xml_files(deluge_root)
    refs = []
    for xml_file in xml_files:
        refs.extend(extract_sample_refs(xml_file, deluge_root))
    index = build_usage_index(refs, sample_scan)

    commands = {
        "summary": cmd_summary,
        "unused": cmd_unused,
        "missing": cmd_missing,
        "usage": cmd_usage,
    }
    commands[args.command](index, args)


if __name__ == "__main__":
    main()
