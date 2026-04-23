"""WORK IN PROGRESS

Extract standalone synth and kit presets from Deluge song XMLs.

Scans all song XMLs in DELUGE/SONGS/, extracts embedded instruments as
standalone preset XMLs, and writes them to DELUGE/SYNTHS/SONG-SYNTHS/ and
DELUGE/KITS/SONG-KITS/.

By default, shows a preview of extractions then prompts to apply.
Pass --dry-run to preview only (no prompt).
Pass --extended to extract multiple versions per instrument when parameters
differ significantly.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

from deluge_lib.cli_utils import confirm_apply, get_deluge_root
from deluge_lib.extraction import (
    SECTION_COLOURS,
    ClipInfo,
    ComparisonConfig,
    DedupResult,
    ExtractionResult,
    NormalisationConfig,
    _strip_automation,
    build_manifest_entry,
    deduplicate_results,
    discover_clips,
    discover_instruments,
    discover_songs,
    extract_kit,
    extract_synth,
    generate_filename,
    match_instruments_to_clips,
    normalise_params,
    select_default_clip,
    select_extended_clips,
    serialise_xml,
)
from deluge_lib.scanning import print_path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Extract standalone presets from Deluge song XMLs.",
    )
    parser.add_argument(
        "--extended",
        action="store_true",
        help="Extract multiple versions per instrument when parameters differ",
    )
    parser.add_argument(
        "--no-dedup",
        action="store_true",
        help="Disable cross-song deduplication (extract all versions from all songs)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List extractions without writing files (default behaviour when no flag given)",
    )
    args = parser.parse_args(argv)

    # Dry-run is the default behaviour (matches existing script conventions).
    # With no flags: show dry-run preview, then prompt to apply.
    # With --dry-run: show dry-run preview only, no prompt.
    explicit_dry_run = args.dry_run

    # ----- Extraction -----

    # Discover and parse all valid song XMLs.
    deluge_root = get_deluge_root()

    # Validate init preset files exist (sanity check).
    init_synth = deluge_root / "SYNTHS" / "Init-Synth.XML"
    init_kit = deluge_root / "KITS" / "Init-Kit.XML"
    missing: list[str] = []
    if not init_synth.is_file():
        missing.append(str(init_synth))
    if not init_kit.is_file():
        missing.append(str(init_kit))
    if missing:
        print(f"ERROR: Missing init preset files: {', '.join(missing)}", file=sys.stderr)
        print("These files are expected on a valid Deluge SD card.", file=sys.stderr)
        sys.exit(1)

    songs = discover_songs(deluge_root)

    all_results: list[ExtractionResult] = []
    norm_config = NormalisationConfig()
    comp_config = ComparisonConfig.default()  # intra-song comparison (extended mode)
    dedup_config = ComparisonConfig.default()  # inter-song dedup (D22 — threshold independence)

    # Track filenames per output directory for collision detection.
    used_synth_filenames: set[str] = set()
    used_kit_filenames: set[str] = set()

    synth_output_dir = deluge_root / "SYNTHS" / "SONG-SYNTHS"
    kit_output_dir = deluge_root / "KITS" / "SONG-KITS"

    for song_path, song_tree in songs:
        song_name = song_path.stem

        # Discover instruments and clips in this song.
        instruments = discover_instruments(song_tree)
        clips = discover_clips(song_tree)
        groups, match_warnings = match_instruments_to_clips(instruments, clips)

        # Print match warnings (orphaned instruments, duplicate clips).
        for warning in match_warnings:
            print(f"WARNING: {song_name}.XML \u2014 {warning}")

        # Skip songs with no extractable instruments.
        if not groups:
            continue

        song_results: list[ExtractionResult] = []

        for group in groups:
            # Build the list of (ClipInfo, differing_params) for extraction.
            clips_with_diffs: list[tuple[ClipInfo, list[str]]] = []
            if args.extended:
                extended_results = select_extended_clips(
                    group, comp_config, norm_config,
                )
                for clip_info, comparisons in extended_results:
                    # Collect differing param descriptions from comparisons.
                    diffs: list[str] = []
                    for cr in comparisons:
                        diffs.extend(cr.hard_diffs)
                        diffs.extend(cr.soft_diffs)
                    # Deduplicate while preserving order.
                    seen: set[str] = set()
                    unique_diffs: list[str] = []
                    for d in diffs:
                        if d not in seen:
                            seen.add(d)
                            unique_diffs.append(d)
                    clips_with_diffs.append((clip_info, unique_diffs))
            else:
                clips_with_diffs.append((select_default_clip(group), []))

            for clip_info, differing_params in clips_with_diffs:
                inst = group.instrument
                section_id = clip_info.section
                if section_id not in SECTION_COLOURS:
                    print(
                        f"WARNING: {song_name}.XML ({inst.preset_name})"
                        f" — unexpected section ID {section_id}, treating as section 0"
                    )
                    section_id = 0
                colour_name, colour_abbr = SECTION_COLOURS[section_id]

                # Transform embedded instrument → standalone preset.
                if inst.instrument_type == "synth":
                    element = extract_synth(inst.element, clip_info.element)
                else:
                    element = extract_kit(inst.element, clip_info.element)

                # Strip automation data (extended hex strings → base values).
                auto_warnings = _strip_automation(element)
                if auto_warnings:
                    print(
                        f"WARNING: {song_name}.XML ({inst.preset_name})"
                        f" \u2014 Stripped automation from {len(auto_warnings)} attributes"
                    )

                # Normalise master volume and pan.
                normalise_params(element, inst.instrument_type, norm_config)

                # Generate output filename.
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
                    extended=args.extended,
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
                    differing_params=differing_params,
                )
                song_results.append(result)

        # Print per-song extraction listing.
        if song_results:
            print(f"{song_name}.XML")
            for r in song_results:
                type_label = r.instrument_type.upper()
                output_dir = (
                    synth_output_dir if r.instrument_type == "synth" else kit_output_dir
                )
                rel_dir = print_path(output_dir.relative_to(deluge_root))
                diff_info = ""
                if r.differing_params:
                    diff_info = f"  ({len(r.differing_params)} diffs)"
                print(
                    f"  {type_label:<6} {r.preset_name:<20}"
                    f"→ {rel_dir}/{r.output_filename}{diff_info}"
                )
            all_results.extend(song_results)

    # ----- Dedup -----

    dedup_result: DedupResult | None = None
    if not args.no_dedup and all_results:
        dedup_result = deduplicate_results(all_results, dedup_config)
        all_results = dedup_result.accepted

    if dedup_result is not None:
        _print_dedup_report(dedup_result)

    # ----- Summary and Output -----

    synth_count = sum(1 for r in all_results if r.instrument_type == "synth")
    kit_count = sum(1 for r in all_results if r.instrument_type == "kit")
    dedup_removed = len(dedup_result.rejected) if dedup_result else 0
    dedup_suffix = f" ({dedup_removed} duplicates removed)" if dedup_removed else ""
    print(
        f"\nSummary: Extracted {synth_count} synths and {kit_count} kits "
        f"from {len(songs)} songs{dedup_suffix}"
    )

    if synth_count > 0:
        print(f"  Output: {print_path(synth_output_dir.relative_to(deluge_root))}/ ({synth_count} files)")
    if kit_count > 0:
        print(f"  Output: {print_path(kit_output_dir.relative_to(deluge_root))}/ ({kit_count} files)")

    if not all_results:
        print("\nNo instruments to extract.")
        return

    # In dry-run mode, stop here.
    if explicit_dry_run:
        print("\nDry run complete")
        return

    # Prompt for confirmation before writing.
    print()
    if not confirm_apply("Apply these changes?"):
        print("Aborted.")
        return

    # Trash previous extraction directories.
    if synth_output_dir.is_dir() or kit_output_dir.is_dir():
        trash_base = deluge_root / ".trash" / datetime.now().strftime("extract-%Y%m%d_%H%M%S")
        for source in [synth_output_dir, kit_output_dir]:
            if source.is_dir():
                rel_path = source.relative_to(deluge_root)
                trash_dest = trash_base / rel_path
                trash_dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), str(trash_dest))

    # Create fresh output directories.
    synth_output_dir.mkdir(parents=True, exist_ok=True)
    kit_output_dir.mkdir(parents=True, exist_ok=True)

    # Write extraction files.
    for result in all_results:
        output_dir = synth_output_dir if result.instrument_type == "synth" else kit_output_dir
        output_path = output_dir / result.output_filename
        serialise_xml(result.element, output_path)

    # Write manifests.
    _write_manifest(synth_output_dir, all_results, "synth", len(songs))
    _write_manifest(kit_output_dir, all_results, "kit", len(songs))

    print(f"\nDone. Wrote {len(all_results)} preset files.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _print_dedup_report(dedup_result: DedupResult) -> None:
    """Print a summary of duplicates removed during cross-song dedup."""
    rejected = dedup_result.rejected
    if not rejected:
        return

    synth_removed = sum(1 for r in rejected if r.result.instrument_type == "synth")
    kit_removed = sum(1 for r in rejected if r.result.instrument_type == "kit")

    print(
        f"\nDedup: Removed {len(rejected)} duplicates"
        f" ({synth_removed} synths, {kit_removed} kits)"
    )

    # Group rejected results by (preset_name, instrument_type).
    groups: dict[tuple[str, str], list[ExtractionResult]] = {}
    for r in rejected:
        key = (r.result.preset_name, r.result.instrument_type)
        groups.setdefault(key, []).append(r.result)

    # Build set of accepted song names per group for the "kept" display.
    accepted_songs: dict[tuple[str, str], list[str]] = {}
    for a in dedup_result.accepted:
        key = (a.preset_name, a.instrument_type)
        accepted_songs.setdefault(key, []).append(a.song_name)

    for (preset_name, inst_type), removed in sorted(groups.items()):
        kept = sorted(accepted_songs.get((preset_name, inst_type), []))
        removed_names = sorted(r.song_name for r in removed)
        print(
            f"  {preset_name} ({inst_type}): kept {', '.join(kept)},"
            f" removed {', '.join(removed_names)}"
        )


def _write_manifest(
    output_dir: Path,
    all_results: list[ExtractionResult],
    instrument_type: str,
    songs_processed: int,
) -> None:
    """Write a manifest.json file in the output directory.

    Includes only results matching the given instrument_type.
    """
    entries = [
        build_manifest_entry(r) for r in all_results if r.instrument_type == instrument_type
    ]

    if not entries:
        return

    manifest = {
        "generated": datetime.now(tz=UTC).isoformat(),
        "songs_processed": songs_processed,
        "total_count": len(entries),
        "extractions": entries,
    }

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
