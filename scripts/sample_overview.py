# Deluge CLI v0.1
"""Sample library overview — cross-referenced reports for the Deluge sample library."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from deluge_lib.analysis import (
    SampleUsage,
    top_folder,
    build_usage_index,
    compute_folder_breakdown,
    compute_summary,
    filter_by_pattern,
    top_by_refs,
)
from deluge_lib.cli_utils import get_deluge_root
from deluge_lib.deluge_sdk import SampleRef, extract_sample_refs, find_all_xml_files, find_unextracted_refs, hash_all_samples
from deluge_lib.paths import SNAPSHOTS_DIR
from deluge_lib.scanning import format_size, print_path, scan_tree

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _folder_label(folder: str) -> str:
    """Format a folder name for display or '(root)' for empty."""
    return f"{folder}/" if folder else "(root)"


def _print_header(text: str) -> None:
    """Print a section header with === above and below the text"""
    print()
    print("=" * len(text))
    print(text)
    print("=" * len(text))


def _group_by_folder(
    samples: list[SampleUsage],
) -> dict[str, list[SampleUsage]]:
    """Group samples by top-level folder, sorted alphabetically by folder."""

    groups: dict[str, list[SampleUsage]] = defaultdict(list)
    for s in samples:
        groups[top_folder(s.path)].append(s)
    return dict(sorted(groups.items()))


def _strip_folder(path: str, folder: str) -> str:
    """Remove the top-level folder prefix from a sample path for grouped display."""
    if folder:
        return path[len(folder) + 1:]
    return path


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_summary(index, args):
    """Print the library overview with totals, folder breakdown, and top refs."""

    summary = compute_summary(index)
    folders = compute_folder_breakdown(index)
    top_n = args.top

    # Build structured rows for global alignment
    summary_rows = [
        ("On disk:", summary.on_disk_count, "samples", format_size(summary.on_disk_size)),
        ("Referenced:", summary.referenced_count, "samples", format_size(summary.referenced_size)),
        ("Unreferenced:", summary.unreferenced_count, "samples", format_size(summary.unreferenced_size)),
        ("Missing:", summary.missing_count, "samples", None),
    ]

    folder_rows = []
    if folders:
        for f in folders:
            name = _folder_label(f.folder)
            folder_rows.append((name, f.file_count, "files", format_size(f.total_size)))

    # Global alignment widths across both blocks
    all_counts = [r[1] for r in summary_rows] + [r[1] for r in folder_rows]
    max_count_len = max(len(f"{c:,}") for c in all_counts)

    all_sizes = [r[3] for r in summary_rows if r[3]] + [r[3] for r in folder_rows if r[3]]
    max_size_len = max(len(s) for s in all_sizes) if all_sizes else 0

    max_label_len = max(len(r[0]) for r in summary_rows)
    max_folder_len = max(len(r[0]) for r in folder_rows) if folder_rows else 0
    max_unit_len = 7  # "samples"

    # Shared left-column width so counts align across both blocks
    left_col = max(max_label_len, 2 + max_folder_len)

    _print_header(" Sample Library Overview ")
    print()

    # Summary rows
    for label, count, unit, size in summary_rows:
        count_str = f"{count:>{max_count_len},}"
        if size:
            print(f"{label:<{left_col}}  {count_str} {unit:<{max_unit_len}}  {size:>{max_size_len}}")
        else:
            print(f"{label:<{left_col}}  {count_str} {unit}")
    print()

    # Folder rows
    if folder_rows:
        print("By folder:")
        for name, count, unit, size in folder_rows:
            padded_name = "  " + name
            count_str = f"{count:>{max_count_len},}"
            print(f"{padded_name:<{left_col}}  {count_str} {unit:<{max_unit_len}}  {size:>{max_size_len}}")
        print()

    # Separator line — width of widest content line
    line_width = left_col + 2 + max_count_len + 1 + max_unit_len + 2 + max_size_len
    print("-" * line_width)
    print()

    top = top_by_refs(index, top_n)
    if top:
        print(f"Top {len(top)} most-referenced (on disk):")
        print()
        max_path_length = max(len(print_path(s.path)) for s in top)
        for s in top:
            print(f"  {print_path(s.path):<{max_path_length}}  {s.ref_count:>4} refs")
        print()


def _print_unused_full(unreferenced: list[SampleUsage]) -> None:
    """Print the full listing of unreferenced samples grouped by folder."""
    groups = _group_by_folder(unreferenced)

    # First pass: compute global alignment values
    folder_meta: dict[str, tuple[str, int, str, list[SampleUsage]]] = {}
    all_size_strings: dict[str, list[str]] = {}
    global_max_path = 0
    global_max_size = 0
    max_count = 0

    for folder, samples in groups.items():
        samples.sort(key=lambda s: s.path.lower())
        label = _folder_label(folder)
        count = len(samples)
        folder_size = sum(s.size or 0 for s in samples)
        folder_size_str = format_size(folder_size)
        size_strs = [format_size(s.size or 0) for s in samples]

        path_len = max(len(print_path(_strip_folder(s.path, folder))) for s in samples)
        global_max_path = max(global_max_path, path_len)
        global_max_size = max(global_max_size, len(folder_size_str), max(len(ss) for ss in size_strs))
        max_count = max(max_count, count)

        all_size_strings[folder] = size_strs
        folder_meta[folder] = (label, count, folder_size_str, samples)

    max_count_len = len(f"{max_count:,}")

    # Ensure minimum 5 dashes for all groups
    file_line_end = 2 + global_max_path + 2 + global_max_size
    min_dash = min(
        file_line_end - 1 - len(meta[0]) - len(
            f"{meta[1]:>{max_count_len},} {'file' if meta[1] == 1 else 'files'}  [{meta[2]:>{global_max_size}}]"
        )
        for meta in folder_meta.values()
    )
    if min_dash < 5:
        global_max_path += 5 - min_dash
        file_line_end = 2 + global_max_path + 2 + global_max_size

    # Second pass: print with global alignment
    for folder in groups:
        label, count, folder_size_str, samples = folder_meta[folder]
        file_word = "file" if count == 1 else "files"
        right = f"{count:>{max_count_len},} {file_word}  [{folder_size_str:>{global_max_size}}]"
        dash_count = file_line_end - 1 - len(label) - len(right)

        print()
        print(f"{label} {'-' * dash_count} {right}")
        for s, ss in zip(samples, all_size_strings[folder]):
            print(f"  {print_path(_strip_folder(s.path, folder)):<{global_max_path}}  {ss:>{global_max_size}}")
    print()


def _print_unused_condensed(unreferenced: list[SampleUsage]) -> None:
    """Print a per-folder summary table of unreferenced samples."""
    groups = _group_by_folder(unreferenced)

    rows: list[tuple[str, int, str]] = []
    for folder, samples in groups.items():
        label = _folder_label(folder)
        count = len(samples)
        folder_size = sum(s.size or 0 for s in samples)
        rows.append((label, count, format_size(folder_size)))

    max_count = max(c for _, c, _ in rows)
    max_count_len = len(f"{max_count:,}")
    max_size_len = max(len(s) for _, _, s in rows)
    max_label_len = max(len(r[0]) for r in rows)

    # Line width: ensure minimum 10 dashes for the longest label
    min_dashes = 10
    right_sample = f"{max_count:>{max_count_len},} files  {'X' * max_size_len}"
    line_width = max_label_len + 1 + min_dashes + 1 + len(right_sample)

    print()
    for label, count, size_str in rows:
        file_word = "file" if count == 1 else "files"
        right = f"{count:>{max_count_len},} {file_word:<5}  {size_str:>{max_size_len}}"
        dash_count = line_width - len(label) - 1 - 1 - len(right)
        print(f"{label} {'-' * dash_count} {right}")
    print()


def cmd_unused(index, args):
    """Print unreferenced samples with multiple output modes."""

    unreferenced = list(index.unreferenced.values())
    if not unreferenced:
        print()
        print("No unreferenced samples")
        print()
        return

    # --top: flat list of N largest
    if args.top is not None:
        top = sorted(unreferenced, key=lambda u: u.size or 0, reverse=True)[: args.top]
        if not top:
            print()
            print("Top 0? That's not how this works!")
            print()
            return
        max_path_length = max(len(print_path(s.path)) for s in top)
        if len(top) == 1:
            _print_header(" Largest unreferenced sample ")
        else:
            _print_header(f" Top {len(top)} largest unreferenced samples ")
        print()
        size_strs = [format_size(s.size or 0) for s in top]
        top_total = sum(s.size or 0 for s in top)
        total_str = format_size(top_total)
        max_size_len = max(max(len(ss) for ss in size_strs), len(total_str))
        for s, ss in zip(top, size_strs):
            print(f"  {print_path(s.path):<{max_path_length}}  {ss:>{max_size_len}}")
        print()
        print(f"  {'Total:':>{max_path_length}}  {total_str:>{max_size_len}}")
        print()
        return

    # --folder: filter to specific top-level folder(s)
    if args.folder:
        requested = [f.upper() for f in args.folder]
        filtered = [s for s in unreferenced if top_folder(s.path).upper() in requested]

        # Report folders with no unreferenced samples
        found_folders = {top_folder(s.path).upper() for s in filtered}
        for req in requested:
            if req not in found_folders:
                print()
                print(f"No unreferenced samples in {req}/")

        if not filtered:
            return

        total_size = sum(s.size or 0 for s in filtered)
        noun = "file" if len(filtered) == 1 else "files"
        header = f" Unreferenced samples ({len(filtered):,} {noun}, {format_size(total_size)}) "
        _print_header(header)
        _print_unused_full(filtered)
        return

    # --all: full listing of all unreferenced samples
    if args.all:
        total_size = sum(s.size or 0 for s in unreferenced)
        noun = "file" if len(unreferenced) == 1 else "files"
        header = f" Unreferenced samples ({len(unreferenced):,} {noun}, {format_size(total_size)}) "
        _print_header(header)
        _print_unused_full(unreferenced)
        return

    # Default: condensed per-folder summary
    total_size = sum(s.size or 0 for s in unreferenced)
    noun = "file" if len(unreferenced) == 1 else "files"
    header = f" Unreferenced samples ({len(unreferenced):,} {noun}, {format_size(total_size)}) "
    _print_header(header)
    _print_unused_condensed(unreferenced)

def cmd_missing(index, _args, *, refs_by_file: dict[Path, list[SampleRef]], deluge_root: Path):
    """Print samples referenced in XML but missing from disk, grouped by XML file."""

    unextracted: list[tuple[Path, str]] = []
    for xml_file, file_refs in refs_by_file.items():
        for path in find_unextracted_refs(xml_file, file_refs):
            rel = xml_file.resolve().relative_to(deluge_root.resolve())
            unextracted.append((rel, path))

    missing = list(index.missing.values())
    total_refs = sum(u.ref_count for u in index.entries.values())
    missing_count = len(missing)

    if not missing:
        print()
        print("All referenced samples found on disk")
    else:
        # Group by (xml_file, preset_name, xml_type) so songs show per-preset
        by_source: dict[tuple[str, str, str], Counter[str]] = defaultdict(Counter)
        for sample in missing:
            for ref in sample.refs:
                source_key = (str(ref.xml_file), ref.preset_name, ref.xml_type)
                by_source[source_key][ref.path] += 1

        _print_header(" Missing samples ")

        for (xml_file_str, preset_name, xml_type), sample_paths in sorted(by_source.items()):
            label = print_path(xml_file_str)
            if xml_type == "song":
                label += f" ({preset_name})"
            if len(sample_paths) > 1:
                label += f" — {len(sample_paths)} missing"
            print(f"\n{label}")
            for path in sorted(sample_paths, key=str.lower):
                ref_count = sample_paths[path]
                suffix = f"  [{ref_count} refs]" if ref_count > 1 else ""
                print(f"  {path}{suffix}")

    # Build footer lines
    footer_lines: list[str] = []
    if unextracted:
        count = len(unextracted)
        noun = "path" if count == 1 else "paths"
        footer_lines.append(f"Warning: {count} sample {noun} detected outside known XML elements")
        max_xml_len = max(len(print_path(xml_rel)) for xml_rel, _ in unextracted)
        for xml_rel, sample_path in sorted(unextracted):
            footer_lines.append(f"  {print_path(xml_rel):<{max_xml_len}}  \u2192 {sample_path}")
        footer_lines.append("")  # blank line after warnings
    footer_lines.append(f"{total_refs} references checked")
    footer_lines.append(f"{missing_count} .WAV files are missing")

    # Separator spans the widest footer line
    sep_width = max(len(line) for line in footer_lines)
    print()
    print("-" * sep_width)
    print()
    for line in footer_lines:
        print(line)
    print()

def cmd_duplicates(deluge_root: Path, hashes: dict[str, list[str]]) -> None:
    """Find and report duplicate sample files by content hash."""

    # Filter to only groups with duplicates
    dupes = {digest: paths for digest, paths in hashes.items() if len(paths) > 1}

    if not dupes:
        print()
        print("No duplicate samples found")
        print()
        return

    # Compute wasted space (all but one file in each group)
    total_wasted = 0
    group_data: list[tuple[str, list[str], int, int]] = []
    for digest, paths in sorted(dupes.items(), key=lambda kv: len(kv[1]), reverse=True):
        rep_path = deluge_root / paths[0]
        try:
            file_size = rep_path.stat().st_size
        except OSError:
            file_size = 0
        wasted = file_size * (len(paths) - 1)
        total_wasted += wasted
        group_data.append((digest, paths, file_size, wasted))

    noun = "group" if len(dupes) == 1 else "groups"
    header = f" Duplicate samples ({len(dupes)} {noun}, {format_size(total_wasted)} wasted) "
    _print_header(header)

    for digest, paths, file_size, wasted in group_data:
        short_hash = digest[:12]
        print()
        print(f"{short_hash}\u2026  ({len(paths)} copies, {format_size(file_size)} each)")
        for p in sorted(paths, key=str.lower):
            print(f"  {print_path(p)}")

    print()
    print("-" * len(header))
    print()
    print(f"{len(dupes)} duplicate {noun}")
    print(f"{format_size(total_wasted)} wasted by duplicates")
    print()


def cmd_usage(index, args):
    """Print usage detail for samples matching a pattern."""

    matches = filter_by_pattern(index, args.term)
    if not matches:
        print()
        print(f'No samples matching "{args.term}"')
        print()
        return

    _print_header(f' Samples matching "{args.term}" ({len(matches):,} matches) ')
    groups = _group_by_folder(matches)
    for folder, samples in groups.items():
        samples.sort(key=lambda s: s.path.lower())
        label = _folder_label(folder)
        max_path_length = max(len(print_path(_strip_folder(s.path, folder))) for s in samples)
        print()
        print(label)
        # Pre-compute all sample data for the folder group
        sample_data: list[tuple[SampleUsage, str, list[tuple[str, str, str]], int, int]] = []
        #                       sample, size_str, child_lines, max_xml_len, max_preset_len
        for s in samples:
            size_str = format_size(s.size) if s.size is not None else "missing!"
            child_lines: list[tuple[str, str, str]] = []
            sample_max_xml_len = 0
            if s.refs:
                refs_by_xml: dict[str, list[SampleRef]] = defaultdict(list)
                for ref in s.refs:
                    refs_by_xml[str(ref.xml_file)].append(ref)
                sample_max_xml_len = max(len(print_path(xml)) for xml in refs_by_xml)
                for xml_file_str in sorted(refs_by_xml):
                    xml_name = print_path(xml_file_str)
                    file_ref_count = len(refs_by_xml[xml_file_str])
                    presets = sorted({r.preset_name for r in refs_by_xml[xml_file_str] if r.xml_type == "song"})
                    preset_str = f"({', '.join(presets)})" if presets else ""
                    ref_str = f" {file_ref_count} refs" if file_ref_count > 1 else ""
                    child_lines.append((xml_name, preset_str, ref_str))
            sample_max_preset_len = max((len(ps) for _, ps, _ in child_lines), default=0)
            sample_data.append((s, size_str, child_lines, sample_max_xml_len, sample_max_preset_len))

        max_size_len = max(len(sz) for _, sz, _, _, _ in sample_data)

        # Compute group-wide alignment values
        group_max_xml_len = max((mxl for _, _, cl, mxl, _ in sample_data if cl), default=0)
        group_max_preset_len = max((mpl for _, _, cl, _, mpl in sample_data if cl), default=0)

        # Ensure parent dash line extends past child XML+preset columns
        min_path_length = group_max_xml_len + group_max_preset_len + 3
        max_path_length = max(max_path_length, min_path_length)
        max_path_length += 5  # minimum dash filler for all paths

        # Check if any sample in the group has ref counts to show
        group_has_refs = any(
            s.ref_count > 1 or any(rs for _, _, rs in cl)
            for s, _, cl, _, _ in sample_data
        )

        if group_has_refs:
            # Compute global ref column across all samples
            parent_content_width = 2 + max_path_length + 2 + max_size_len
            child_content_width = 4 + group_max_xml_len + 2 + group_max_preset_len
            ref_col = max(parent_content_width, child_content_width) + 2

            for s, size_str, child_lines, _, _ in sample_data:
                sample_path = print_path(_strip_folder(s.path, folder))
                gap = max_path_length - len(sample_path)
                filler = " " + "-" * gap + " "
                parent_base = f"  {sample_path}{filler}{size_str:>{max_size_len}}"
                if s.ref_count > 1:
                    padding = ref_col - len(parent_base)
                    print(f"{parent_base}{' ' * padding}[{s.ref_count} refs]")
                else:
                    print(parent_base)
                for xml_name, preset_str, ref_str in child_lines:
                    if preset_str or ref_str:
                        child_base = f"    {xml_name:<{group_max_xml_len}}  {preset_str:<{group_max_preset_len}}"
                        if ref_str:
                            padding = ref_col - len(child_base)
                            print(f"{child_base}{' ' * padding}{ref_str}")
                        else:
                            print(f"    {xml_name:<{group_max_xml_len}}  {preset_str}")
                    else:
                        print(f"    {xml_name}")
        else:
            # Simple case: no ref counts anywhere in this group
            for s, size_str, child_lines, _, _ in sample_data:
                sample_path = print_path(_strip_folder(s.path, folder))
                gap = max_path_length - len(sample_path)
                filler = " " + "-" * gap + " "
                print(f"  {sample_path}{filler}{size_str:>{max_size_len}}")
                for xml_name, preset_str, _ in child_lines:
                    if preset_str:
                        print(f"    {xml_name:<{group_max_xml_len}}  {preset_str}")
                    else:
                        print(f"    {xml_name}")
    print()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="sample_overview",
        description="Sample library overview \u2014 cross-referenced reports for the Deluge sample library.",
    )
    subparsers = parser.add_subparsers(dest="command")

    # uv run sample_overview summary --top 5
    sp_summary = subparsers.add_parser(
        "summary", help="Library overview with totals and folder breakdown"
    )
    sp_summary.add_argument(
        "--top",
        type=int,
        default=5,
        help="Number of top-referenced samples to show (default: 5)",
    )

    # uv run sample_overview unused
    sp_unused = subparsers.add_parser("unused", help="List unreferenced samples")
    unused_mode = sp_unused.add_mutually_exclusive_group()
    unused_mode.add_argument(
        "--all", "-a",
        action="store_true",
        help="Show full listing of all unreferenced samples grouped by folder",
    )
    unused_mode.add_argument(
        "--folder", "-f",
        nargs="+",
        metavar="FOLDER",
        help="Show full listing filtered to specific top-level folder(s)",
    )
    unused_mode.add_argument(
        "--top", "-t",
        type=int,
        default=None,
        help="Show only the N largest unreferenced samples",
    )

    subparsers.add_parser(
        "missing",
        help="List samples referenced in XML but missing from disk",
    )

    sp_usage = subparsers.add_parser(
        "usage", help="Show usage detail for samples matching a search term"
    )
    sp_usage.add_argument(
        "term",
        metavar="TERM",
        help="Case-insensitive substring to match against sample paths",
    )

    # duplicates
    sp_duplicates = subparsers.add_parser(
        "duplicates",
        help="Find duplicate sample files by content hash",
    )
    sp_duplicates.add_argument(
        "-s",
        "--snapshot",
        metavar="PATH_OR_LATEST",
        default=None,
        help="Use a snapshot JSON instead of hashing live. Pass a file path or 'latest'.",
    )

    args = parser.parse_args(argv)

    # Default to summary when no subcommand is given
    if args.command is None:
        args.command = "summary"
        args.top = 5

    deluge_root = get_deluge_root()

    # Duplicates only needs hashing — skip XML scanning
    if args.command == "duplicates":
        if args.snapshot is not None:
            if args.snapshot == "latest":
                manifests_dir = SNAPSHOTS_DIR
                snapshots = sorted(manifests_dir.glob("snapshot-*.json"))
                if not snapshots:
                    raise SystemExit(f"No snapshots found in {manifests_dir}")
                snapshot_path = snapshots[-1]
            else:
                snapshot_path = Path(args.snapshot)
                if not snapshot_path.exists():
                    raise SystemExit(f"Snapshot not found: {snapshot_path}")
            print(f"Using snapshot: {snapshot_path.name}")
            with open(snapshot_path, encoding="utf-8") as f:
                hashes = json.load(f)["hashes"]
        else:
            hashes = hash_all_samples(deluge_root)
        cmd_duplicates(deluge_root, hashes)
        return

    # Data collection for XML-based subcommands
    sample_scan = scan_tree(deluge_root / "SAMPLES", label="SAMPLES", file_filter="wav")
    xml_files = find_all_xml_files(deluge_root)
    refs: list[SampleRef] = []
    refs_by_file: dict[Path, list[SampleRef]] = {}
    total = len(xml_files)
    for i, xml_file in enumerate(xml_files, 1):
        print(f"\rParsing XML references... {i}/{total}", end="", flush=True)
        file_refs = extract_sample_refs(xml_file, deluge_root)
        refs.extend(file_refs)
        refs_by_file[xml_file] = file_refs
    print(f"\rParsing XML references... {total}/{total} done")
    index = build_usage_index(refs, sample_scan)

    # Branch to subcommand
    if args.command == "missing":
        cmd_missing(index, args, refs_by_file=refs_by_file, deluge_root=deluge_root)
    else:
        commands = {
            "summary": cmd_summary,
            "unused": cmd_unused,
            "usage": cmd_usage,
        }
        commands[args.command](index, args)


if __name__ == "__main__":
    main()
