"""Benchmark dedup threshold configurations against the current song library."""

from __future__ import annotations

import argparse
import io
import os
import sys
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

from deluge_lib.cli_utils import get_deluge_root
from deluge_lib.extraction import (
    SECTION_COLOURS,
    ComparisonConfig,
    ExtractionResult,
    _strip_automation,
    deduplicate_results,
    discover_clips,
    discover_instruments,
    discover_songs,
    extract_kit,
    extract_synth,
    generate_filename,
    is_sidechain_kit,
    load_init_defaults,
    load_kit_init_template,
    match_instruments_to_clips,
    normalise_params,
    select_default_clip,
    select_extended_clips,
)


def _extract_default_results(
    songs: list[tuple[Path, object]],
    norm_config: object,
    kit_init_template: object,
) -> list[ExtractionResult]:
    """Run the default-mode extraction pipeline once (no dedup) and return all results."""
    all_results: list[ExtractionResult] = []
    used_synth_filenames: set[str] = set()
    used_kit_filenames: set[str] = set()

    for song_path, song_tree in songs:
        song_name = song_path.stem
        instruments = discover_instruments(song_tree)
        clips = discover_clips(song_tree)
        groups, _warnings = match_instruments_to_clips(instruments, clips, song_tree)

        for group in groups:
            if group.instrument.instrument_type == "kit":
                is_sc, _reason = is_sidechain_kit(group)
                if is_sc:
                    continue

            clip_info = select_default_clip(group)
            inst = group.instrument
            section_id = clip_info.section
            if section_id not in SECTION_COLOURS:
                section_id = 0
            colour_name, colour_abbr = SECTION_COLOURS[section_id]

            if inst.instrument_type == "synth":
                element = extract_synth(inst.element, clip_info.element)
            else:
                element, _dp_warnings = extract_kit(
                    inst.element, clip_info.element,
                    init_template=kit_init_template,
                )

            _strip_automation(element)
            normalise_params(element, inst.instrument_type, norm_config)

            used = (
                used_synth_filenames
                if inst.instrument_type == "synth"
                else used_kit_filenames
            )
            filename = generate_filename(
                song_name=song_name,
                preset_name=inst.preset_name,
                instrument_type=inst.instrument_type,
                section_id=section_id,
                extended=False,
                used_filenames=used,
            )

            result = ExtractionResult(
                song_name=song_name,
                preset_name=inst.preset_name,
                instrument_type=inst.instrument_type,
                section_id=section_id,
                colour_abbr=colour_abbr,
                element=element,
                output_filename=filename,
                preset_folder=inst.preset_folder,
                colour_name=colour_name,
            )
            all_results.append(result)

    return all_results


def _extract_extended_results(
    songs: list[tuple[Path, object]],
    norm_config: object,
    kit_init_template: object,
    comp_config: ComparisonConfig,
) -> list[ExtractionResult]:
    """Run the extended-mode extraction pipeline with a given config (no cross-song dedup)."""
    all_results: list[ExtractionResult] = []
    used_synth_filenames: set[str] = set()
    used_kit_filenames: set[str] = set()

    for song_path, song_tree in songs:
        song_name = song_path.stem
        instruments = discover_instruments(song_tree)
        clips = discover_clips(song_tree)
        groups, _warnings = match_instruments_to_clips(instruments, clips, song_tree)

        for group in groups:
            if group.instrument.instrument_type == "kit":
                is_sc, _reason = is_sidechain_kit(group)
                if is_sc:
                    continue

            extended_results = select_extended_clips(
                group, comp_config, norm_config,
                kit_init_template=kit_init_template,
            )

            for clip_info, comparisons in extended_results:
                inst = group.instrument
                section_id = clip_info.section
                if section_id not in SECTION_COLOURS:
                    section_id = 0
                colour_name, colour_abbr = SECTION_COLOURS[section_id]

                if inst.instrument_type == "synth":
                    element = extract_synth(inst.element, clip_info.element)
                else:
                    element, _dp_warnings = extract_kit(
                        inst.element, clip_info.element,
                        init_template=kit_init_template,
                    )

                _strip_automation(element)
                normalise_params(element, inst.instrument_type, norm_config)

                diffs: list[str] = []
                for cr in comparisons:
                    diffs.extend(cr.hard_diffs)
                    diffs.extend(cr.soft_diffs)
                seen: set[str] = set()
                unique_diffs: list[str] = []
                for d in diffs:
                    if d not in seen:
                        seen.add(d)
                        unique_diffs.append(d)

                used = (
                    used_synth_filenames
                    if inst.instrument_type == "synth"
                    else used_kit_filenames
                )
                filename = generate_filename(
                    song_name=song_name,
                    preset_name=inst.preset_name,
                    instrument_type=inst.instrument_type,
                    section_id=section_id,
                    extended=True,
                    used_filenames=used,
                )

                result = ExtractionResult(
                    song_name=song_name,
                    preset_name=inst.preset_name,
                    instrument_type=inst.instrument_type,
                    section_id=section_id,
                    colour_abbr=colour_abbr,
                    element=element,
                    output_filename=filename,
                    preset_folder=inst.preset_folder,
                    colour_name=colour_name,
                    differing_params=unique_diffs,
                )
                all_results.append(result)

    return all_results


def _count_by_type(results: list[ExtractionResult]) -> tuple[int, int]:
    """Return (kit_count, synth_count) from a list of results."""
    kits = sum(1 for r in results if r.instrument_type == "kit")
    synths = sum(1 for r in results if r.instrument_type == "synth")
    return kits, synths


def _fmt_cell(kits: int, synths: int, total: int) -> str:
    """Format a cell as '  K,   S ( T)' with 3-digit aligned numbers."""
    return f"{kits:3d}, {synths:3d} ({total:3d})"


@contextmanager
def _suppress_stdout():
    """Temporarily redirect stdout to devnull to suppress library output."""
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        yield
    finally:
        sys.stdout = old_stdout


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark dedup threshold configurations against the current song library.",
    )
    parser.add_argument(
        "--percent",
        nargs=3,
        type=int,
        default=[1, 99, 10],
        metavar=("LOWER", "UPPER", "STEP"),
        help="Percent threshold range: lower upper step (default: 1 99 10)",
    )
    parser.add_argument(
        "--count",
        nargs=3,
        type=int,
        default=[1, 5, 2],
        metavar=("LOWER", "UPPER", "STEP"),
        help="Count threshold range: lower upper step (default: 1 5 2)",
    )
    args = parser.parse_args(argv)

    pct_lower, pct_upper, pct_step = args.percent
    cnt_lower, cnt_upper, cnt_step = args.count

    percent_values = sorted(set(range(pct_lower, pct_upper + 1, pct_step)) | {pct_upper})
    count_values = sorted(set(range(cnt_lower, cnt_upper + 1, cnt_step)) | {cnt_upper})

    # Build all (count, percent) combos sorted by (count, percent).
    combos = [(c, p) for c in count_values for p in percent_values]

    # --- Setup ---
    deluge_root = get_deluge_root()
    norm_config = load_init_defaults(deluge_root)
    kit_init_template = load_kit_init_template(deluge_root)
    base_config = ComparisonConfig.default()

    print("Parsing songs...", end=" ", file=sys.stderr, flush=True)
    with _suppress_stdout():
        songs = discover_songs(deluge_root)
    print(f"done ({len(songs)} songs)", file=sys.stderr)

    # --- Default mode: extract once, dedup per combo ---
    print("Extracting instruments (default mode)...", end=" ", file=sys.stderr, flush=True)
    with _suppress_stdout():
        default_all = _extract_default_results(songs, norm_config, kit_init_template)
    default_kits_no_dedup, default_synths_no_dedup = _count_by_type(default_all)
    default_total_no_dedup = default_kits_no_dedup + default_synths_no_dedup
    print(f"done ({default_total_no_dedup} instruments)", file=sys.stderr)

    # --- Extended mode baseline: extract once with default config, no dedup ---
    print(
        "Extracting instruments (extended mode, baseline)...",
        end=" ",
        file=sys.stderr,
        flush=True,
    )
    with _suppress_stdout():
        extended_baseline = _extract_extended_results(
            songs, norm_config, kit_init_template, base_config,
        )
    ext_kits_no_dedup, ext_synths_no_dedup = _count_by_type(extended_baseline)
    ext_total_no_dedup = ext_kits_no_dedup + ext_synths_no_dedup
    print(f"done ({ext_total_no_dedup} instruments)", file=sys.stderr)

    # --- Test each configuration ---
    total_combos = len(combos)
    print(f"Testing {total_combos} configurations...", file=sys.stderr)

    # rows: list of (pct_label, cnt_label, def_kits, def_synths, def_total, ext_kits, ext_synths, ext_total)
    rows: list[tuple[str, str, int, int, int, int, int, int]] = []

    # No-dedup baseline row.
    rows.append((
        "none",
        "none",
        default_kits_no_dedup, default_synths_no_dedup, default_total_no_dedup,
        ext_kits_no_dedup, ext_synths_no_dedup, ext_total_no_dedup,
    ))

    idx_width = len(str(total_combos))

    for i, (count_val, pct_val) in enumerate(combos, 1):
        pct_fraction = pct_val / 100.0
        custom_config = replace(
            base_config,
            param_count_threshold=count_val,
            param_percent_threshold=pct_fraction,
        )

        # Default mode: dedup the cached results with the custom config.
        with _suppress_stdout():
            default_dedup = deduplicate_results(default_all, custom_config)
        def_kits, def_synths = _count_by_type(default_dedup.accepted)
        def_total = def_kits + def_synths

        # Extended mode: re-run extraction + dedup with the custom config.
        with _suppress_stdout():
            ext_results = _extract_extended_results(
                songs, norm_config, kit_init_template, custom_config,
            )
            ext_dedup = deduplicate_results(ext_results, custom_config)
        ext_kits, ext_synths = _count_by_type(ext_dedup.accepted)
        ext_total = ext_kits + ext_synths

        print(
            f"  [{i:>{idx_width}}/{total_combos}] {pct_val:>2}% / count {count_val}..."
            f" done (default: {def_total:3d}, extended: {ext_total:3d})",
            file=sys.stderr,
        )

        rows.append((
            f"{pct_val}%",
            str(count_val),
            def_kits, def_synths, def_total,
            ext_kits, ext_synths, ext_total,
        ))

    # --- Print markdown table to stdout ---
    print()
    print(f"Testing {len(songs)} songs...\n")
    print(
        "| Thresholds   |"
        " Default         |"
        " Extended        |"
    )
    print(
        "|--------------|"
        "-----------------|"
        "-----------------|"
    )
    print(
        f"|{' % ':>6}|{' count ':>7}"
        f"|{' Kit, Syn (tot) ':>17}"
        f"|{' Kit, Syn (tot) ':>17}|"
    )
    separator = (
        "|------|-------|"
        "-----------------|"
        "-----------------|"
    )
    print(separator)
    prev_cnt = None
    for pct_label, cnt_label, dk, ds, dt, ek, es, et in rows:
        if prev_cnt is not None and cnt_label != prev_cnt:
            print(separator)
        prev_cnt = cnt_label
        print(
            f"|{pct_label:>5} |{cnt_label:>6} "
            f"|{_fmt_cell(dk, ds, dt):>16} "
            f"|{_fmt_cell(ek, es, et):>16} |"
        )
    print()


if __name__ == "__main__":
    main()
