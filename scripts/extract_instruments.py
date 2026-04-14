"""Extract standalone synth and kit presets from Deluge song XMLs.

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
    ExtractionResult,
    InstrumentClipGroup,
    NormalisationConfig,
    SECTION_COLOURS,
    build_manifest_entry,
    compare_versions,
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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Extract standalone presets from Deluge song XMLs.",
    )
    parser.add_argument(
        "--extended",
        action="store_true",
        help="Extract multiple versions per instrument when parameters differ significantly",
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

    # --- Phase 1: Discovery --------------------------------------------------

    try:
        deluge_root = get_deluge_root()
    except SystemExit as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    # Validate init presets exist (required for normalisation reference values).
    init_synth_path = deluge_root / "SYNTHS" / "Init-Synth.XML"
    init_kit_path = deluge_root / "KITS" / "Init-Kit.XML"
    if not init_synth_path.is_file():
        print(f"Error: Init synth preset not found: {init_synth_path}", file=sys.stderr)
        sys.exit(1)
    if not init_kit_path.is_file():
        print(f"Error: Init kit preset not found: {init_kit_path}", file=sys.stderr)
        sys.exit(1)

    # Discover and parse all valid song XMLs.
    try:
        songs = discover_songs(deluge_root)
    except NotImplementedError:
        print("Error: discover_songs() is not yet implemented.", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning {len(songs)} songs...\n")

    # --- Phase 2: Extraction -------------------------------------------------

    all_results: list[ExtractionResult] = []
    all_warnings: list[str] = []
    norm_config = NormalisationConfig()

    # Track filenames per output directory for collision detection.
    used_synth_filenames: set[str] = set()
    used_kit_filenames: set[str] = set()

    for song_path, song_tree in songs:
        song_name = song_path.stem

        # Discover instruments and clips in this song.
        try:
            instruments = discover_instruments(song_tree)
            clips = discover_clips(song_tree)
            groups, match_warnings = match_instruments_to_clips(instruments, clips)
        except NotImplementedError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)

        # Print match warnings (orphaned instruments, duplicate clips).
        for warning in match_warnings:
            print(f"WARNING: {song_name}.XML — {warning}")
            all_warnings.append(f"{song_name}.XML — {warning}")

        # Skip songs with no extractable instruments.
        if not groups:
            continue

        song_results: list[ExtractionResult] = []

        for group in groups:
            # Select clips for extraction based on mode.
            try:
                if args.extended:
                    clips_to_extract = select_extended_clips(group)
                else:
                    clips_to_extract = [select_default_clip(group)]
            except NotImplementedError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                sys.exit(1)

            for clip_info in clips_to_extract:
                inst = group.instrument
                section_id = clip_info.section
                colour_name, colour_abbr = SECTION_COLOURS.get(
                    section_id, ("Unknown", "Unk")
                )

                # Transform embedded instrument → standalone preset.
                try:
                    if inst.instrument_type == "synth":
                        element = extract_synth(inst.element, clip_info.element)
                    else:
                        element = extract_kit(inst.element, clip_info.element)

                    # Normalise master volume and pan.
                    normalise_params(element, inst.instrument_type, norm_config)
                except NotImplementedError as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    sys.exit(1)

                # Generate output filename.
                used = (
                    used_synth_filenames
                    if inst.instrument_type == "synth"
                    else used_kit_filenames
                )
                try:
                    filename = generate_filename(
                        song_name=song_name,
                        preset_name=inst.preset_name,
                        instrument_type=inst.instrument_type,
                        section_id=section_id,
                        extended=args.extended,
                        used_filenames=used,
                    )
                except NotImplementedError as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    sys.exit(1)

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
                song_results.append(result)

        # Print per-song extraction listing.
        if song_results:
            print(f"{song_name}.XML")
            for r in song_results:
                type_label = r.instrument_type.upper()
                subdir = (
                    "SONG-SYNTHS" if r.instrument_type == "synth" else "SONG-KITS"
                )
                print(
                    f"  {type_label:<6} {r.preset_name:<20}"
                    f"→ {subdir}/{r.output_filename}"
                )
            all_results.extend(song_results)

    # --- Phase 3: Summary and Output -----------------------------------------

    synth_count = sum(1 for r in all_results if r.instrument_type == "synth")
    kit_count = sum(1 for r in all_results if r.instrument_type == "kit")
    print(
        f"\nSummary: Extracted {synth_count} synths and {kit_count} kits "
        f"from {len(songs)} songs"
    )

    synth_output_dir = deluge_root / "SYNTHS" / "SONG-SYNTHS"
    kit_output_dir = deluge_root / "KITS" / "SONG-KITS"

    if synth_count > 0:
        print(f"  Output: {synth_output_dir.relative_to(deluge_root)}/ ({synth_count} files)")
    if kit_count > 0:
        print(f"  Output: {kit_output_dir.relative_to(deluge_root)}/ ({kit_count} files)")

    if not all_results:
        print("\nNo instruments to extract.")
        return

    # In dry-run mode, stop here.
    if explicit_dry_run:
        print("\n(dry run)")
        return

    # Prompt for confirmation before writing.
    print()
    if not confirm_apply("Apply these changes?"):
        print("Aborted.")
        return

    # Trash previous extraction directories (D8).
    _trash_output_dir(deluge_root / "SYNTHS", "SONG-SYNTHS")
    _trash_output_dir(deluge_root / "KITS", "SONG-KITS")

    # Create fresh output directories.
    synth_output_dir.mkdir(parents=True, exist_ok=True)
    kit_output_dir.mkdir(parents=True, exist_ok=True)

    # Write extraction files.
    for result in all_results:
        output_dir = synth_output_dir if result.instrument_type == "synth" else kit_output_dir
        output_path = output_dir / result.output_filename
        try:
            serialise_xml(result.element, output_path)
        except NotImplementedError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)

    # Write manifests.
    _write_manifest(synth_output_dir, all_results, "synth", len(songs))
    _write_manifest(kit_output_dir, all_results, "kit", len(songs))

    print(f"\nDone. Wrote {len(all_results)} preset files.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _trash_output_dir(parent_dir: Path, subdir_name: str) -> None:
    """Move an existing output subdirectory to .trash within the parent.

    If SONG-SYNTHS/ exists, moves it to SYNTHS/.trash/SONG-SYNTHS/.
    Overwrites any previous trash contents.
    """
    source = parent_dir / subdir_name
    if not source.is_dir():
        return

    trash_dir = parent_dir / ".trash"
    trash_dest = trash_dir / subdir_name

    # Remove old trash if it exists.
    if trash_dest.is_dir():
        shutil.rmtree(trash_dest)

    trash_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(trash_dest))


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
    main()
