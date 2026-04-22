"""WORK IN PROGRESS

Core extraction logic for extracting standalone presets from Deluge song XMLs.

This module contains all reusable functions for:
- Song parsing and instrument/clip discovery
- Synth and kit XML transformation (merging instrument structure with clip params)
- Volume/pan normalisation
- Version comparison (extended mode)
- Filename generation and XML serialisation

No CLI concerns, no user interaction. Receives parsed XML trees and returns data structures.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from deluge_lib.deluge_sdk import parse_deluge_xml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FIRMWARE_VERSION = "c1.2.1"
EARLIEST_COMPATIBLE = "4.1.0-alpha"

# Init preset reference values for normalisation (from Init-Synth.XML and Init-Kit.XML)
SYNTH_INIT_VOLUME = "0x4CCCCCA8"
KIT_INIT_VOLUME = "0x3504F334"
CENTRE_PAN = "0x00000000"

# Attributes present on song-embedded instruments but absent from standalone presets.
# These must be stripped during extraction.
SONG_SPECIFIC_ATTRS = (
    "presetName",
    "presetFolder",
    "defaultVelocity",
    "isArmedForRecording",
    "activeModFunction",
    "clipInstances",
    "colour",
)

# Extra numeric attributes on clip-level <arpeggiator> that must be stripped.
# These duplicate values from <soundParams> and are not present on standalone presets.
ARPEGGIATOR_EXTRA_ATTRS = (
    "gate",
    "rate",
    "ratchetProbability",
    "ratchetAmount",
    "sequenceLength",
    "rhythm",
)

# Section ID → (colour name, 3-letter abbreviation) mapping.
# The Deluge has 12 colour-coded launch sections (rows).
SECTION_COLOURS: dict[int, tuple[str, str]] = {
    0: ("LightBlue", "Lbl"),
    1: ("Pink", "Pnk"),
    2: ("Gold", "Gld"),
    3: ("Cyan", "Cyn"),
    4: ("Red", "Red"),
    5: ("Yellow", "Ylw"),
    6: ("DarkBlue", "Dbl"),
    7: ("Orange", "Orn"),
    8: ("Purple", "Pur"),
    9: ("Lime", "Lme"),
    10: ("Green", "Grn"),
    11: ("Magenta", "Mag"),
}

# Extended mode thresholds for version comparison (D4).
# A version is "distinct" if >= DIFF_PARAM_COUNT_THRESHOLD numerical params
# differ by > DIFF_PARAM_PERCENT_THRESHOLD (as a fraction of the full range).
DIFF_PARAM_COUNT_THRESHOLD = 3
DIFF_PARAM_PERCENT_THRESHOLD = 0.10

# The standalone synth child element order for c1.2.1 firmware.
# Elements are reordered to match this sequence during extraction.
SYNTH_CHILD_ORDER = (
    "osc1",
    "osc2",
    "lfo1",
    "lfo2",
    "modulator1",
    "modulator2",
    "unison",
    "defaultParams",
    "arpeggiator",
    "modKnobs",
    "delay",
    "sidechain",
    "audioCompressor",
)

# The standalone kit top-level child element order for c1.2.1 firmware.
KIT_CHILD_ORDER = (
    "defaultParams",
    "delay",
    "sidechain",
    "audioCompressor",
    "soundSources",
    "selectedDrumIndex",
)

# The standalone kit per-row sound child element order for c1.2.1 firmware.
KIT_SOUND_CHILD_ORDER = (
    "osc1",
    "osc2",
    "lfo1",
    "lfo2",
    "unison",
    "defaultParams",
    "arpeggiator",
    "modKnobs",
    "delay",
    "sidechain",
    "audioCompressor",
)

# Attributes to exclude from numerical comparison (always normalised, so not meaningful).
COMPARISON_EXCLUDED_ATTRS = ("volume", "pan")


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class InstrumentInfo:
    """An instrument definition found in a song's <instruments> section."""

    element: etree._Element
    instrument_type: str  # "synth" or "kit"
    preset_name: str
    preset_folder: str


@dataclass
class ClipInfo:
    """An <instrumentClip> found in a song's <sessionClips> section."""

    element: etree._Element
    section: int
    preset_name: str
    preset_folder: str


@dataclass
class InstrumentClipGroup:
    """Groups an instrument with all its clips, keyed by section ID."""

    instrument: InstrumentInfo
    clips_by_section: dict[int, ClipInfo]  # section_id → ClipInfo
    warnings: list[str] = field(default_factory=list)


@dataclass
class VersionComparison:
    """Result of comparing two clip versions of the same instrument."""

    is_distinct: bool
    differing_params: list[str]  # names of parameters that differ


@dataclass
class NormalisationConfig:
    """Which attributes to normalise on <defaultParams> and their target values.

    Designed to be extendable — add new entries to the dict to normalise
    additional attributes in the future.
    """

    synth_targets: dict[str, str] = field(
        default_factory=lambda: {
            "volume": SYNTH_INIT_VOLUME,
            "pan": CENTRE_PAN,
        }
    )
    kit_targets: dict[str, str] = field(
        default_factory=lambda: {
            "volume": KIT_INIT_VOLUME,
            "pan": CENTRE_PAN,
        }
    )


@dataclass
class ExtractionResult:
    """Carries all information about a single extracted instrument preset."""

    song_name: str
    preset_name: str
    instrument_type: str  # "synth" or "kit"
    section_id: int
    colour_abbr: str
    element: etree._Element  # the assembled standalone XML element
    output_filename: str
    # Metadata for the manifest
    preset_folder: str
    colour_name: str
    differing_params: list[str] = field(default_factory=list)  # for extended mode


# ---------------------------------------------------------------------------
# Song Discovery (Task 1.2)
# ---------------------------------------------------------------------------


def discover_songs(deluge_root: Path) -> list[tuple[Path, etree._Element]]:
    """Find and parse all valid song XMLs in DELUGE_ROOT/SONGS/.

    Discovers all *.XML files directly in the SONGS/ directory (non-recursive).
    Parses each file and validates the firmwareVersion attribute on the <song>
    root element. Songs with firmware != c1.2.1 are skipped with a warning.

    Returns:
        List of (path, parsed_root_element) tuples for valid songs.

    Steps:
        1. Glob DELUGE_ROOT/SONGS/*.XML (case-insensitive on content, uppercase ext)
        2. For each file, parse with parse_deluge_xml()
        3. Read firmwareVersion attribute from <song> root element
        4. If firmwareVersion != "c1.2.1", print warning and skip
        5. Collect and return valid (path, root) tuples
    """
    songs_dir = deluge_root / "SONGS"
    if not songs_dir.is_dir():
        return []

    results: list[tuple[Path, etree._Element]] = []

    for xml_path in sorted(songs_dir.glob("*.XML")):
        if not xml_path.is_file():
            continue

        try:
            _tree, root, _recovered = parse_deluge_xml(xml_path)
        except Exception as exc:
            print(f"WARNING: Skipping {xml_path.name} — failed to parse XML: {exc}")
            continue

        # If the parser wrapped content in a <root> element, find the <song> child.
        song_el = root if root.tag == "song" else root.find("song")
        if song_el is None:
            print(f"WARNING: Skipping {xml_path.name} — no <song> root element found")
            continue

        firmware = song_el.get("firmwareVersion", "")
        if firmware != FIRMWARE_VERSION:
            print(
                f"WARNING: Skipping {xml_path.name}"
                f" — firmware {firmware!r} (expected {FIRMWARE_VERSION!r})"
            )
            continue

        results.append((xml_path, song_el))

    return results


# ---------------------------------------------------------------------------
# Instrument & Clip Discovery (Task 1.3)
# ---------------------------------------------------------------------------


def discover_instruments(song_tree: etree._Element) -> list[InstrumentInfo]:
    """Extract all synth and kit instruments from a song's <instruments> section.

    Discovers all <sound> (synth) and <kit> children of <instruments>.
    Ignores <midi> and <audioTrack> elements.

    Steps:
        1. Find the <instruments> child of the song root
        2. Iterate children: for <sound> tags → type="synth", for <kit> tags → type="kit"
        3. Read presetName and presetFolder attributes from each instrument
        4. Return list of InstrumentInfo dataclasses
    """
    instruments_el = song_tree.find("instruments")
    if instruments_el is None:
        return []

    tag_to_type = {"sound": "synth", "kit": "kit"}
    results: list[InstrumentInfo] = []

    for child in instruments_el:
        instrument_type = tag_to_type.get(child.tag)
        if instrument_type is None:
            continue

        preset_name = child.get("presetName", "")
        preset_folder = child.get("presetFolder", "")

        results.append(
            InstrumentInfo(
                element=child,
                instrument_type=instrument_type,
                preset_name=preset_name,
                preset_folder=preset_folder,
            )
        )

    return results


def discover_clips(song_tree: etree._Element) -> list[ClipInfo]:
    """Extract all instrumentClips from a song's <sessionClips> section.

    Discovers all <instrumentClip> children of <sessionClips>.
    Ignores <arrangementOnlyClips> entirely (D13).

    Steps:
        1. Find the <sessionClips> child of the song root
        2. Iterate children: collect <instrumentClip> elements only
        3. Read instrumentPresetName, instrumentPresetFolder, and section attributes
        4. If section attribute is missing, treat as section 0 and log a warning
        5. Return list of ClipInfo dataclasses
    """
    session_clips_el = song_tree.find("sessionClips")
    if session_clips_el is None:
        return []

    results: list[ClipInfo] = []

    for child in session_clips_el:
        if child.tag != "instrumentClip":
            continue

        preset_name = child.get("instrumentPresetName", "")
        preset_folder = child.get("instrumentPresetFolder", "")

        section_str = child.get("section")
        if section_str is None:
            print(
                f"WARNING: <instrumentClip> for {preset_name!r} has no section attribute"
                " — treating as section 0"
            )
            section = 0
        else:
            section = int(section_str)

        results.append(
            ClipInfo(
                element=child,
                section=section,
                preset_name=preset_name,
                preset_folder=preset_folder,
            )
        )

    return results


def match_instruments_to_clips(
    instruments: list[InstrumentInfo],
    clips: list[ClipInfo],
) -> tuple[list[InstrumentClipGroup], list[str]]:
    """Match clips to instruments and group by section, identifying orphans.

    Matching key: (presetName, presetFolder) on instrument == (preset_name, preset_folder)
    on clip (from instrumentPresetName / instrumentPresetFolder attributes).

    Steps:
        1. Build a lookup dict of clips keyed by (preset_name, preset_folder)
        2. For each instrument, find all matching clips
        3. Group matching clips by section ID
        4. If two clips share the same section for one instrument, keep the first
           and record a warning (D14)
        5. If an instrument has no matching clips, it is orphaned — record a warning (D7)
        6. Return (groups, warnings) where warnings is a flat list of all warning strings
    """
    # Build lookup: (preset_name, preset_folder) → list of ClipInfo
    clips_by_key: dict[tuple[str, str], list[ClipInfo]] = {}
    for clip in clips:
        key = (clip.preset_name, clip.preset_folder)
        clips_by_key.setdefault(key, []).append(clip)

    groups: list[InstrumentClipGroup] = []
    warnings: list[str] = []

    for instrument in instruments:
        key = (instrument.preset_name, instrument.preset_folder)
        matching_clips = clips_by_key.get(key, [])

        if not matching_clips:
            msg = (
                f"Orphaned instrument {instrument.preset_name!r}"
                f" (folder={instrument.preset_folder!r}, type={instrument.instrument_type})"
                " — no matching session clips"
            )
            warnings.append(msg)
            continue

        clips_by_section: dict[int, ClipInfo] = {}
        group_warnings: list[str] = []

        for clip in matching_clips:
            if clip.section in clips_by_section:
                msg = (
                    f"Duplicate clip for {instrument.preset_name!r}"
                    f" in section {clip.section}, taking first"
                )
                group_warnings.append(msg)
                continue
            clips_by_section[clip.section] = clip

        group = InstrumentClipGroup(
            instrument=instrument,
            clips_by_section=clips_by_section,
            warnings=group_warnings,
        )
        groups.append(group)
        warnings.extend(group_warnings)

    return groups, warnings


# ---------------------------------------------------------------------------
# Version Selection — Default Mode (Task 1.4)
# ---------------------------------------------------------------------------


def select_default_clip(group: InstrumentClipGroup) -> ClipInfo:
    """Select the clip with the lowest section ID as the extraction source.

    This is the default mode selection strategy (D3). Simple, deterministic,
    and favours section 0 (light blue).

    Steps:
        1. Get all section IDs from group.clips_by_section
        2. Find the minimum section ID
        3. Return the corresponding ClipInfo
    """
    lowest_section = min(group.clips_by_section)
    return group.clips_by_section[lowest_section]


# ---------------------------------------------------------------------------
# Synth Extraction Transformation (Task 2.1)
# ---------------------------------------------------------------------------


def extract_synth(
    instrument: etree._Element,
    clip: etree._Element,
) -> etree._Element:
    """Transform an embedded synth into a standalone preset XML element.

    Follows the synth extraction recipe from research Section 13.5.
    Does NOT mutate the original tree — operates on a deep clone.

    Args:
        instrument: The <sound> element from <instruments>.
        clip: The corresponding <instrumentClip> element.

    Returns:
        A standalone <sound> element ready for serialisation.

    Steps:
        1. Deep-clone the <sound> element from <instruments>
        2. Strip song-specific attributes: presetName, presetFolder,
           defaultVelocity, isArmedForRecording, activeModFunction,
           clipInstances, colour (using _strip_song_attrs)
        3. Add firmwareVersion="c1.2.1" and earliestCompatibleFirmware="4.1.0-alpha"
        4. Extract <soundParams> from clip → rename tag to <defaultParams>
           (tag rename only — no attribute or child element changes)
        5. Extract <arpeggiator> from clip → strip extra numeric attributes
           (gate, rate, ratchetProbability, ratchetAmount, sequenceLength, rhythm)
           using _extract_arpeggiator_from_clip()
        6. Reorder child elements using _reorder_synth_children():
           osc1, osc2, lfo1, lfo2, [modulator1, modulator2], unison,
           defaultParams (inserted), arpeggiator (inserted from clip),
           modKnobs (moved from after unison to after arpeggiator),
           delay, sidechain, audioCompressor
        7. Preserve all attribute values verbatim including extended hex
           automation strings (D10)
        8. Preserve all child elements within <defaultParams>:
           envelope1, envelope2, patchCables, equalizer
    """
    # 1. Deep-clone the <sound> element
    sound = copy.deepcopy(instrument)

    # 2. Strip song-specific attributes
    _strip_song_attrs(sound)

    # 3. Add firmware version attributes
    sound.set("firmwareVersion", FIRMWARE_VERSION)
    sound.set("earliestCompatibleFirmware", EARLIEST_COMPATIBLE)

    # 4. Extract <soundParams> from clip → rename tag to <defaultParams>
    sound_params = clip.find("soundParams")
    if sound_params is not None:
        default_params = copy.deepcopy(sound_params)
        default_params.tag = "defaultParams"
        sound.append(default_params)

    # 5. Extract <arpeggiator> from clip → strip extra numeric attributes
    arp = _extract_arpeggiator_from_clip(clip)
    if arp is not None:
        sound.append(arp)

    # 6. Reorder child elements to match standalone c1.2.1 ordering
    _reorder_synth_children(sound)

    return sound


# ---------------------------------------------------------------------------
# Kit Extraction Transformation (Task 2.2)
# ---------------------------------------------------------------------------


def extract_kit(
    instrument: etree._Element,
    clip: etree._Element,
) -> etree._Element:
    """Transform an embedded kit into a standalone preset XML element.

    Follows the kit extraction recipe from research Section 13.5.
    Does NOT mutate the original tree — operates on a deep clone.

    Args:
        instrument: The <kit> element from <instruments>.
        clip: The corresponding <instrumentClip> element.

    Returns:
        A standalone <kit> element ready for serialisation.

    Steps:
        1. Deep-clone the <kit> element from <instruments>
        2. Strip song-specific attributes: presetName, presetFolder,
           defaultVelocity, isArmedForRecording, activeModFunction,
           colour (using _strip_song_attrs)
           Note: kits do NOT have clipInstances in the observed data
        3. Add firmwareVersion="c1.2.1" and earliestCompatibleFirmware="4.1.0-alpha"
        4. Extract <kitParams> from clip → rename tag to <defaultParams>
        5. Insert kit-level <defaultParams> as the FIRST child of <kit>
           (before <delay>) — this is the "affect entire" params block
        6. For each <noteRow> in the clip's <noteRows> that has a drumIndex:
           a. Read drumIndex attribute (0-based index into <soundSources>)
           b. Extract <soundParams> from the <noteRow> → rename tag to <defaultParams>
           c. Find the corresponding <sound> in <soundSources> by index
              (drumIndex=0 → first <sound>, etc.)
           d. Insert <defaultParams> into that <sound> between <unison> and
              <arpeggiator> (using _merge_noterow_params)
           e. If drumIndex is out of range, warn and skip that noteRow
        7. Leave kit sound <arpeggiator> elements in place — they are already
           in the instrument definition (kit arpeggiator asymmetry, Section 13.6)
        8. Reorder kit top-level children using _reorder_kit_children():
           defaultParams, delay, sidechain, audioCompressor, soundSources,
           selectedDrumIndex
        9. Reorder each kit row sound's children to match standalone order:
           osc1, osc2, lfo1, lfo2, unison, defaultParams, arpeggiator,
           modKnobs, delay, sidechain, audioCompressor
        10. Preserve all attribute values verbatim (D10)
    """
    # 1. Deep-clone the <kit> element
    kit = copy.deepcopy(instrument)

    # 2. Strip song-specific attributes
    _strip_song_attrs(kit)

    # 3. Add firmware version attributes
    kit.set("firmwareVersion", FIRMWARE_VERSION)
    kit.set("earliestCompatibleFirmware", EARLIEST_COMPATIBLE)

    # 4. Extract <kitParams> from clip → rename tag to <defaultParams>
    kit_params = clip.find("kitParams")
    if kit_params is not None:
        default_params = copy.deepcopy(kit_params)
        default_params.tag = "defaultParams"
        # 5. Insert kit-level <defaultParams> as the FIRST child of <kit>
        kit.insert(0, default_params)

    # 6. Merge noteRow soundParams into corresponding kit row sounds
    sound_sources = kit.find("soundSources")
    sounds = list(sound_sources) if sound_sources is not None else []

    note_rows_el = clip.find("noteRows")
    if note_rows_el is not None:
        for noterow in note_rows_el:
            if noterow.tag != "noteRow":
                continue
            drum_index_str = noterow.get("drumIndex")
            if drum_index_str is None:
                continue
            drum_index = int(drum_index_str)
            if drum_index < 0 or drum_index >= len(sounds):
                print(
                    f"WARNING: drumIndex {drum_index} out of range"
                    f" (soundSources has {len(sounds)} sounds) — skipping noteRow"
                )
                continue
            _merge_noterow_params(sounds[drum_index], noterow)

    # 8. Reorder kit top-level children
    _reorder_kit_children(kit)

    # 9. Reorder each kit row sound's children
    if sound_sources is not None:
        for sound in sound_sources:
            if sound.tag == "sound":
                _reorder_kit_sound_children(sound)

    return kit


# ---------------------------------------------------------------------------
# Volume/Pan Normalisation (Task 2.3)
# ---------------------------------------------------------------------------


def normalise_params(
    element: etree._Element,
    instrument_type: str,
    config: NormalisationConfig,
) -> None:
    """Normalise master volume and pan on the top-level <defaultParams>.

    Modifies the element in-place. Only touches the top-level <defaultParams>
    element — does NOT modify kit row <defaultParams> within <soundSources>.
    Does NOT modify patchCable entries with destination="volume".

    Args:
        element: The assembled standalone <sound> or <kit> element.
        instrument_type: "synth" or "kit".
        config: NormalisationConfig with target values per instrument type.

    Steps:
        1. Find the top-level <defaultParams> child of element
           - For synths: direct child of <sound>
           - For kits: direct child of <kit> (first <defaultParams>, not row-level)
        2. Select target values based on instrument_type:
           - synth → config.synth_targets
           - kit → config.kit_targets
        3. For each (attr_name, target_value) in targets:
           set the attribute on <defaultParams> to the target value
        4. Do NOT descend into <soundSources>/<sound>/<defaultParams>
        5. Do NOT touch <patchCables> children with destination="volume"
    """
    default_params = element.find("defaultParams")
    if default_params is None:
        return

    targets = (
        config.synth_targets if instrument_type == "synth" else config.kit_targets
    )
    for attr_name, target_value in targets.items():
        default_params.set(attr_name, target_value)


# ---------------------------------------------------------------------------
# Filename Generation (Task 3.1)
# ---------------------------------------------------------------------------


def generate_filename(
    song_name: str,
    preset_name: str,
    instrument_type: str,
    section_id: int,
    extended: bool,
    used_filenames: set[str],
) -> str:
    """Generate a unique output filename following the naming convention.

    Default mode:   <SongName>-<PresetName>.XML
    Extended mode:  <SongName>-<PresetName>-<Abbr>.XML

    Args:
        song_name: Stem of the song XML filename (e.g. "Bloop").
        preset_name: The instrument's presetName attribute (e.g. "133").
        instrument_type: "synth" or "kit" (not used in filename, but determines output dir).
        section_id: Section ID for colour abbreviation lookup (extended mode only).
        extended: Whether extended mode is active.
        used_filenames: Set of filenames already used — for collision detection.

    Returns:
        A unique filename string (e.g. "Bloop-133.XML").

    Steps:
        1. Construct base name: "<song_name>-<preset_name>"
        2. If extended, append "-<Abbr>" using SECTION_COLOURS[section_id]
        3. Append ".XML" extension
        4. If filename is already in used_filenames, append "-2", "-3", etc.
           until unique
        5. Add the final filename to used_filenames
        6. Return the filename
    """
    base = f"{song_name}-{preset_name}"
    if extended:
        _colour_name, abbr = SECTION_COLOURS[section_id]
        base = f"{base}-{abbr}"

    filename = f"{base}.XML"

    if filename in used_filenames:
        counter = 2
        while f"{base}-{counter}.XML" in used_filenames:
            counter += 1
        filename = f"{base}-{counter}.XML"

    used_filenames.add(filename)
    return filename


# ---------------------------------------------------------------------------
# XML Serialisation (Task 3.2)
# ---------------------------------------------------------------------------


def serialise_xml(element: etree._Element, output_path: Path) -> None:
    """Serialise an assembled lxml element to a standalone XML file.

    Writes with XML declaration and UTF-8 encoding to match the formatting
    style of existing standalone presets (Init-Synth.XML, Init-Kit.XML).

    Args:
        element: The root element to serialise (<sound> or <kit>).
        output_path: Absolute path for the output file.

    Steps:
        1. Use lxml.etree.tostring() with xml_declaration=True, encoding="UTF-8",
           pretty_print=True — hardware-tested and confirmed compatible with
           Deluge firmware c1.2.1 (the Deluge re-normalises formatting on save)
        2. Write the resulting bytes to output_path
        3. Ensure parent directories exist (create if needed)
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    xml_bytes = etree.tostring(
        element, xml_declaration=True, encoding="UTF-8", pretty_print=True
    )
    output_path.write_bytes(xml_bytes)


# ---------------------------------------------------------------------------
# Version Comparison — Extended Mode (Task 4.1)
# ---------------------------------------------------------------------------


def compare_versions(
    clip_a: etree._Element,
    clip_b: etree._Element,
    instrument: etree._Element,
) -> VersionComparison:
    """Compare two clip versions to determine if they are sufficiently different.

    Used in extended mode to decide whether to extract multiple versions of
    the same instrument. clip_a is the baseline (lowest section ID).

    The comparison has three tiers:
    1. Structural/non-numerical changes on the instrument element → always distinct
    2. Non-numerical changes in params (envelope, patchCable, arpeggiator settings) → always distinct
    3. Numerical param changes → distinct if >= DIFF_PARAM_COUNT_THRESHOLD params
       differ by > DIFF_PARAM_PERCENT_THRESHOLD

    Args:
        clip_a: The baseline <instrumentClip> element.
        clip_b: The candidate <instrumentClip> element.
        instrument: The <sound> or <kit> element from <instruments> (shared).

    Returns:
        VersionComparison with is_distinct flag and list of differing param names.

    Steps:
        1. Compare structural elements on the instrument <sound> definition:
           - Root attributes: polyphonic, voicePriority, mode, transpose, modFXType,
             lpfMode, hpfMode, filterRoute, maxVoices, clippingAmount
           - <osc1>, <osc2> attributes: type, transpose, cents, retrigPhase,
             loopMode, reversed, fileName
           - <lfo1>, <lfo2> attributes: type, syncLevel, syncType
           - <unison> attributes: num, detune, spread
           - <modulator1>, <modulator2> if present
           - <delay>, <sidechain>, <audioCompressor> attributes
           → Any change here = distinct (structural change)
        2. Compare non-numerical settings in clip params:
           - <envelope1>, <envelope2> attributes
           - <patchCables> structure (source, destination values)
           - <arpeggiator> attributes (mode, noteMode, octaveMode, etc.)
           → Any non-numerical change = distinct
        3. Compare numerical <soundParams>/<kitParams> attributes:
           - Exclude volume and pan (normalised, not meaningful)
           - For each attribute present on either clip's params:
             a. Parse hex values as 32-bit signed integers
             b. For extended hex strings (automation), use first 10 chars only (D15)
             c. Calculate absolute difference as proportion of full range (0x00000000–0x7FFFFFFF)
             d. If difference > DIFF_PARAM_PERCENT_THRESHOLD, count it
           - If count >= DIFF_PARAM_COUNT_THRESHOLD → distinct
        4. Return VersionComparison with combined results
    """
    raise NotImplementedError("Task 4.1: Parameter comparison engine")


# ---------------------------------------------------------------------------
# Extended Mode Selection (Task 4.2)
# ---------------------------------------------------------------------------


def select_extended_clips(group: InstrumentClipGroup) -> list[ClipInfo]:
    """Select clips for extended mode extraction based on version comparison.

    The baseline clip (lowest section ID) is always included. Each subsequent
    section version is compared against the baseline. If distinct, it is
    included for extraction.

    Args:
        group: An InstrumentClipGroup with all clips for one instrument.

    Returns:
        List of ClipInfo objects to extract (always includes baseline).

    Steps:
        1. Sort clips_by_section by section ID (ascending)
        2. Take the first clip as the baseline — always include it
        3. For each subsequent clip:
           a. Call compare_versions(baseline_clip, candidate_clip, instrument)
           b. If is_distinct, add to extraction list
        4. Return the full list of clips to extract
    """
    raise NotImplementedError("Task 4.2: Extended mode multi-version selection")


# ---------------------------------------------------------------------------
# Manifest Generation (Task 3.4)
# ---------------------------------------------------------------------------


def build_manifest_entry(result: ExtractionResult) -> dict[str, str | int | list[str]]:
    """Build a single manifest entry dict from an ExtractionResult.

    Steps:
        1. Construct dict with: output_filename, source_song, preset_name,
           preset_folder, instrument_type, section_id, colour_name,
           colour_abbr, differing_params (for extended mode)
        2. Return the dict
    """
    return {
        "output_filename": result.output_filename,
        "source_song": result.song_name,
        "preset_name": result.preset_name,
        "preset_folder": result.preset_folder,
        "instrument_type": result.instrument_type,
        "section_id": result.section_id,
        "colour_name": result.colour_name,
        "colour_abbr": result.colour_abbr,
        "differing_params": result.differing_params,
    }


# ---------------------------------------------------------------------------
# Private Helpers
# ---------------------------------------------------------------------------


def _strip_song_attrs(element: etree._Element) -> None:
    """Remove song-specific attributes from an instrument element.

    Strips: presetName, presetFolder, defaultVelocity, isArmedForRecording,
    activeModFunction, clipInstances, colour.

    Modifies the element in-place. Silently ignores attributes that are not present.
    """
    for attr in SONG_SPECIFIC_ATTRS:
        if attr in element.attrib:
            del element.attrib[attr]


def _extract_arpeggiator_from_clip(clip: etree._Element) -> etree._Element | None:
    """Extract and clean the <arpeggiator> element from an <instrumentClip>.

    For synth clips, the <arpeggiator> is a direct child of <instrumentClip>,
    appearing before <soundParams>. Kit clips do NOT have a clip-level arpeggiator.

    Steps:
        1. Find <arpeggiator> child of the clip element
        2. If not found, return None (expected for kit clips)
        3. Deep-clone the <arpeggiator> element
        4. Strip extra numeric attributes: gate, rate, ratchetProbability,
           ratchetAmount, sequenceLength, rhythm (ARPEGGIATOR_EXTRA_ATTRS)
        5. Return the cleaned <arpeggiator> element
    """
    arp_el = clip.find("arpeggiator")
    if arp_el is None:
        return None

    arp_clone = copy.deepcopy(arp_el)
    for attr in ARPEGGIATOR_EXTRA_ATTRS:
        if attr in arp_clone.attrib:
            del arp_clone.attrib[attr]

    return arp_clone


def _reorder_synth_children(sound: etree._Element) -> None:
    """Reorder child elements of a <sound> to match standalone c1.2.1 format.

    Target order: osc1, osc2, lfo1, lfo2, [modulator1, modulator2], unison,
    defaultParams, arpeggiator, modKnobs, delay, sidechain, audioCompressor.

    Handles optional elements (modulators for FM mode) gracefully — they are
    included only if present.

    Steps:
        1. Collect all child elements into a dict keyed by tag name
        2. Build ordered list following SYNTH_CHILD_ORDER, skipping missing tags
        3. Clear all children from the <sound> element
        4. Re-append children in the correct order
        5. Append any unexpected children at the end (future-proofing)

    Modifies the element in-place.
    """
    children_by_tag: dict[str, etree._Element] = {}
    for child in list(sound):
        children_by_tag[child.tag] = child

    ordered: list[etree._Element] = []
    seen_tags: set[str] = set()
    for tag in SYNTH_CHILD_ORDER:
        if tag in children_by_tag:
            ordered.append(children_by_tag[tag])
            seen_tags.add(tag)

    # Append any unexpected children at the end (future-proofing)
    for tag, child in children_by_tag.items():
        if tag not in seen_tags:
            ordered.append(child)

    # Clear and re-append in order
    for child in list(sound):
        sound.remove(child)
    for child in ordered:
        sound.append(child)


def _reorder_kit_children(kit: etree._Element) -> None:
    """Reorder top-level child elements of a <kit> to match standalone format.

    Target order: defaultParams, delay, sidechain, audioCompressor,
    soundSources, selectedDrumIndex.

    Steps:
        1. Collect all child elements into a dict keyed by tag name
        2. Build ordered list following KIT_CHILD_ORDER, skipping missing tags
        3. Clear all children from the <kit> element
        4. Re-append children in the correct order
        5. Append any unexpected children at the end (future-proofing)

    Modifies the element in-place.
    """
    children_by_tag: dict[str, etree._Element] = {}
    for child in list(kit):
        children_by_tag[child.tag] = child

    ordered: list[etree._Element] = []
    seen_tags: set[str] = set()
    for tag in KIT_CHILD_ORDER:
        if tag in children_by_tag:
            ordered.append(children_by_tag[tag])
            seen_tags.add(tag)

    # Append any unexpected children at the end (future-proofing)
    for tag, child in children_by_tag.items():
        if tag not in seen_tags:
            ordered.append(child)

    # Clear and re-append in order
    for child in list(kit):
        kit.remove(child)
    for child in ordered:
        kit.append(child)


def _reorder_kit_sound_children(sound: etree._Element) -> None:
    """Reorder child elements of a kit row <sound> to match standalone format.

    Target order: osc1, osc2, lfo1, lfo2, unison, defaultParams, arpeggiator,
    modKnobs, delay, sidechain, audioCompressor.

    Steps:
        1. Collect all child elements into a dict keyed by tag name
        2. Build ordered list following KIT_SOUND_CHILD_ORDER, skipping missing tags
        3. Clear all children from the <sound> element
        4. Re-append children in the correct order
        5. Append any unexpected children at the end (future-proofing)

    Modifies the element in-place.
    """
    children_by_tag: dict[str, etree._Element] = {}
    for child in list(sound):
        children_by_tag[child.tag] = child

    ordered: list[etree._Element] = []
    seen_tags: set[str] = set()
    for tag in KIT_SOUND_CHILD_ORDER:
        if tag in children_by_tag:
            ordered.append(children_by_tag[tag])
            seen_tags.add(tag)

    # Append any unexpected children at the end (future-proofing)
    for tag, child in children_by_tag.items():
        if tag not in seen_tags:
            ordered.append(child)

    # Clear and re-append in order
    for child in list(sound):
        sound.remove(child)
    for child in ordered:
        sound.append(child)


def _merge_noterow_params(
    sound: etree._Element,
    noterow: etree._Element,
) -> list[str]:
    """Merge a noteRow's <soundParams> into a kit row <sound> as <defaultParams>.

    Steps:
        1. Find <soundParams> in the noteRow
        2. If not found, return a warning message
        3. Deep-clone and rename tag to <defaultParams>
        4. Find the <unison> child in the sound element
        5. Insert <defaultParams> immediately after <unison>
           (before <arpeggiator> in the final order)
        6. Return an empty list (no warnings) on success

    Returns:
        List of warning strings (empty on success).
    """
    sound_params = noterow.find("soundParams")
    if sound_params is None:
        return [f"WARNING: noteRow has no <soundParams> — skipping"]

    default_params = copy.deepcopy(sound_params)
    default_params.tag = "defaultParams"

    # Insert after <unison> (before <arpeggiator> in final order)
    unison = sound.find("unison")
    if unison is not None:
        unison_idx = list(sound).index(unison)
        sound.insert(unison_idx + 1, default_params)
    else:
        # Fallback: append (will be reordered later)
        sound.append(default_params)

    return []


def _parse_hex_value(hex_str: str) -> int:
    """Parse a Deluge hex string (e.g. '0x4CCCCCA8') as a 32-bit signed integer.

    For extended hex strings containing automation data (longer than 10 chars),
    uses only the first 10 characters (the static value) per D15.

    Steps:
        1. If len > 10, truncate to first 10 chars (automation prefix)
        2. Parse as unsigned 32-bit int with int(hex_str, 16)
        3. Convert to signed 32-bit: if value >= 0x80000000, subtract 0x100000000
        4. Return the signed integer
    """
    raise NotImplementedError("Helper: Parse Deluge hex value")



