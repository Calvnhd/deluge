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
import re
from collections.abc import Callable
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

# Regex matching Deluge hex parameter values (0x followed by hex digits).
_HEX_VALUE_RE = re.compile(r"^0x[0-9A-Fa-f]+$")

# Full range for proportional soft-marker difference calculation.
# Deluge hex params span 0x80000000 (-2,147,483,648) to 0x7FFFFFFF (+2,147,483,647).
# User-facing values map to either 0–50 or -50 to +50, using the full signed range.
# Using 0x7FFFFFFF (positive half) as the denominator means the 10% threshold
# corresponds to ~2.5 display units on a 0–50 scale.  Using 0xFFFFFFFF (full span)
# would correspond to ~5 display units.  Adjust during testing if needed.
_HEX_FULL_RANGE = 0x7FFFFFFF


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
class ComparisonConfig:
    """Configurable ruleset for the generalised comparison engine.

    Maps element paths to sets of attribute names that constitute hard markers
    (structural identity).  Sentinel values prefixed with ``_`` signal special
    comparison logic in the engine:

    * ``_structure`` — compare child-element structure (e.g. patchCable routing)
    * ``_count``     — compare child-element count
    * ``_names``     — compare child-element ``name`` attributes as a set
    """

    # Hard markers — structural attributes that make instruments immediately distinct.
    # Maps element path → set of attribute names (or sentinel keys).
    synth_hard_attrs: dict[str, set[str]]
    kit_hard_attrs: dict[str, set[str]]

    # Soft marker thresholds
    param_count_threshold: int  # min number of params that must differ
    param_percent_threshold: float  # min proportional change per param (0.0–1.0)

    # Ignored attributes — excluded from all comparison tiers
    ignored_attrs: set[str]

    # Child elements whose attributes are walked for soft-marker diffs
    # (beyond defaultParams, delay, sidechain, audioCompressor which are
    # already handled).  Maps element tag → set of attributes to SKIP
    # (because they are hard markers or ignored).
    synth_soft_elements: dict[str, set[str]]
    kit_sound_soft_elements: dict[str, set[str]]

    @classmethod
    def default(cls) -> ComparisonConfig:
        """Return the standard comparison config.

        Hard markers sourced from research Section 16.2.  Thresholds and
        ignored attrs consume the existing module-level constants.
        """
        return cls(
            synth_hard_attrs={
                "sound": {
                    "mode",
                    "polyphonic",
                    "voicePriority",
                    "maxVoices",
                    "clippingAmount",
                    "modFXType",
                    "lpfMode",
                    "hpfMode",
                    "filterRoute",
                },
                "osc1": {"type", "fileName", "transpose"},
                "osc2": {"type", "fileName", "transpose"},
                "lfo1": {"type"},
                "lfo2": {"type"},
                "unison": {"num"},
                "arpeggiator": {"mode", "noteMode", "octaveMode"},
                "patchCables": {"_structure"},
            },
            kit_hard_attrs={
                "kit": {"modFXType", "lpfMode", "hpfMode", "filterRoute"},
                "soundSources": {"_count", "_names"},
                "soundSources/sound": {
                    "polyphonic",
                    "voicePriority",
                    "mode",
                    "maxVoices",
                    "modFXType",
                    "lpfMode",
                    "hpfMode",
                    "filterRoute",
                },
                "soundSources/sound/osc1": {
                    "type",
                    "fileName",
                    "transpose",
                    "loopMode",
                    "reversed",
                },
                "soundSources/sound/osc2": {
                    "type",
                    "fileName",
                    "transpose",
                    "loopMode",
                    "reversed",
                },
                "soundSources/sound/lfo1": {"type"},
                "soundSources/sound/lfo2": {"type"},
                "soundSources/sound/unison": {"num"},
                "soundSources/sound/arpeggiator": {"mode"},
            },
            param_count_threshold=DIFF_PARAM_COUNT_THRESHOLD,
            param_percent_threshold=DIFF_PARAM_PERCENT_THRESHOLD,
            ignored_attrs={
                "volume",
                "pan",
                "firmwareVersion",
                "earliestCompatibleFirmware",
                "modFXCurrentParam",
                "currentFilterType",
            },
            synth_soft_elements={
                "osc1": {"type", "fileName", "transpose"},
                "osc2": {"type", "fileName", "transpose"},
                "lfo1": {"type"},
                "lfo2": {"type"},
                "unison": {"num"},
                "arpeggiator": {"mode", "noteMode", "octaveMode"},
            },
            kit_sound_soft_elements={
                "osc1": {
                    "type",
                    "fileName",
                    "transpose",
                    "loopMode",
                    "reversed",
                },
                "osc2": {
                    "type",
                    "fileName",
                    "transpose",
                    "loopMode",
                    "reversed",
                },
                "lfo1": {"type"},
                "lfo2": {"type"},
                "unison": {"num"},
                "arpeggiator": {"mode"},
            },
        )


@dataclass
class ComparisonResult:
    """Result of comparing two assembled standalone presets."""

    is_distinct: bool
    hard_diffs: list[str]
    soft_diff_count: int
    soft_diffs: list[str]
    reason: str


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


@dataclass
class RejectedResult:
    """An extraction result rejected during cross-song deduplication."""

    result: ExtractionResult
    matched_result: ExtractionResult  # which accepted result it was similar to
    comparison: ComparisonResult


@dataclass
class DedupResult:
    """Output of cross-song deduplication."""

    accepted: list[ExtractionResult]
    rejected: list[RejectedResult]
    # Per-stage breakdown for reporting
    name_pass_rejected: list[RejectedResult] = field(default_factory=list)
    global_pass_rejected: list[RejectedResult] = field(default_factory=list)


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
                colour_entry = SECTION_COLOURS.get(clip.section)
                section_label = (
                    f"{clip.section}/{colour_entry[0]}"
                    if colour_entry
                    else str(clip.section)
                )
                msg = (
                    f"Duplicate clip for {instrument.preset_name!r}"
                    f" in section {section_label}, taking first"
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
        A tuple of (standalone <kit> element, list of warning strings).
        The warnings describe any sounds that received default params.

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

    # 7. Safety pass: ensure every <sound> has a <defaultParams> child
    default_param_warnings: list[str] = []
    if sound_sources is not None:
        default_param_warnings = _ensure_all_sounds_have_default_params(sounds)

    # 8. Reorder kit top-level children
    _reorder_kit_children(kit)

    # 9. Reorder each kit row sound's children
    if sound_sources is not None:
        for sound in sound_sources:
            if sound.tag == "sound":
                _reorder_kit_sound_children(sound)

    return kit, default_param_warnings


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
# Automation Stripping
# ---------------------------------------------------------------------------

_AUTOMATION_RE = re.compile(r"^0x[0-9A-Fa-f]{9,}$")


def _strip_automation(element: etree._Element) -> list[str]:
    """Truncate extended hex automation strings to base values on element and all descendants.

    Standalone Deluge presets never contain automation data — the Deluge strips
    it on save.  For every attribute value matching ``0x`` followed by more than
    8 hex characters, this function truncates to the first 8 hex chars (the base
    parameter value).

    Returns:
        List of warning strings for attributes that were truncated.
    """
    warnings: list[str] = []
    for el in element.iter():
        for attr_name, attr_value in el.attrib.items():
            if _AUTOMATION_RE.match(attr_value):
                el.set(attr_name, attr_value[:10])
                warnings.append(f"Stripped automation from {el.tag}.{attr_name}")
    return warnings


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
# Generalised Comparison Engine (Task 4.2)
# ---------------------------------------------------------------------------


def compare_instruments(
    preset_a: etree._Element,
    preset_b: etree._Element,
    instrument_type: str,
    config: ComparisonConfig,
) -> ComparisonResult:
    """Compare two assembled standalone presets for equivalence.

    Three-tier comparison operating on post-extraction, post-normalisation
    preset elements (``<sound>`` for synths, ``<kit>`` for kits).

    Tier 1 — Hard markers: structural attributes where any single difference
    means the instruments are immediately distinct.

    Tier 2 — Soft markers: numerical hex params compared with a per-param
    proportional threshold and a group count threshold.

    Tier 3 — Ignored: attributes in ``config.ignored_attrs`` are skipped
    throughout all tiers.

    Args:
        preset_a: First assembled standalone element (``<sound>`` or ``<kit>``).
        preset_b: Second assembled standalone element.
        instrument_type: ``"synth"`` or ``"kit"``.
        config: Comparison ruleset (hard markers, thresholds, ignore list).

    Returns:
        A :class:`ComparisonResult` carrying the verdict, diffs, and a
        human-readable reason string.
    """
    hard_attrs = (
        config.synth_hard_attrs
        if instrument_type == "synth"
        else config.kit_hard_attrs
    )
    hard_diffs: list[str] = []

    # --- TIER 1: HARD MARKERS ---

    # Root element attributes
    root_key = "sound" if instrument_type == "synth" else "kit"
    if root_key in hard_attrs:
        for attr in sorted(hard_attrs[root_key]):
            if attr in config.ignored_attrs:
                continue
            val_a = preset_a.get(attr, "")
            val_b = preset_b.get(attr, "")
            if val_a != val_b:
                hard_diffs.append(f"{root_key}.{attr}: {val_a!r} vs {val_b!r}")

    # Direct child element attributes (synth: osc1, osc2, arpeggiator; etc.)
    for path, attrs in sorted(hard_attrs.items()):
        if path in (root_key, "patchCables", "soundSources") or "/" in path:
            continue
        el_a = preset_a.find(path)
        el_b = preset_b.find(path)
        for attr in sorted(attrs):
            if attr.startswith("_") or attr in config.ignored_attrs:
                continue
            val_a = el_a.get(attr, "") if el_a is not None else ""
            val_b = el_b.get(attr, "") if el_b is not None else ""
            if val_a != val_b:
                hard_diffs.append(f"{path}.{attr}: {val_a!r} vs {val_b!r}")

    # PatchCables structure on top-level defaultParams (D19)
    dp_a = preset_a.find("defaultParams")
    dp_b = preset_b.find("defaultParams")
    hard_diffs.extend(_check_patchcable_structure(dp_a, dp_b))

    # Kit-specific structural hard markers
    if instrument_type == "kit":
        hard_diffs.extend(
            _check_kit_structure_hard(preset_a, preset_b, hard_attrs, config)
        )

    if hard_diffs:
        reason = f"hard: {hard_diffs[0]}"
        if len(hard_diffs) > 1:
            reason += f" (+{len(hard_diffs) - 1} more)"
        return ComparisonResult(
            is_distinct=True,
            hard_diffs=hard_diffs,
            soft_diff_count=0,
            soft_diffs=[],
            reason=reason,
        )

    # --- TIER 2: SOFT MARKERS ---

    if instrument_type == "kit":
        return _compare_kit_soft(preset_a, preset_b, config)

    # Synth soft markers
    soft_diffs = _collect_soft_diffs(
        dp_a, dp_b, preset_a, preset_b, config,
        soft_elements=config.synth_soft_elements,
    )
    is_distinct = len(soft_diffs) >= config.param_count_threshold
    count = len(soft_diffs)
    if is_distinct:
        reason = (
            f"soft: {count} params differ"
            f" >{config.param_percent_threshold:.0%}"
        )
    else:
        reason = (
            f"similar: {count} soft diffs"
            f" (threshold: {config.param_count_threshold})"
        )
    return ComparisonResult(
        is_distinct=is_distinct,
        hard_diffs=[],
        soft_diff_count=count,
        soft_diffs=soft_diffs,
        reason=reason,
    )


# ---------------------------------------------------------------------------
# Extended Mode Selection (Task 4.3)
# ---------------------------------------------------------------------------


def select_extended_clips(
    group: InstrumentClipGroup,
    comparison_config: ComparisonConfig,
    normalisation_config: NormalisationConfig,
) -> list[tuple[ClipInfo, list[ComparisonResult]]]:
    """Select clips for extended mode extraction based on version comparison.

    The baseline clip (lowest section ID) is always included.  Each subsequent
    section version is extracted, normalised, and compared against ALL
    previously accepted assembled presets.  If distinct from every accepted
    preset it is included; if similar to any it is rejected.

    Args:
        group: An InstrumentClipGroup with all clips for one instrument.
        comparison_config: Ruleset for the generalised comparison engine.
        normalisation_config: Targets for volume/pan normalisation.

    Returns:
        List of ``(ClipInfo, comparisons)`` tuples for accepted clips.
        The baseline's ``comparisons`` list is empty.  Each subsequent
        accepted clip carries the :class:`ComparisonResult` for every
        previously-accepted preset it was compared against.
    """
    inst = group.instrument
    instrument_type = inst.instrument_type

    # 1. Sort clips by section ID ascending.
    sorted_clips = [
        clip for _sid, clip in sorted(group.clips_by_section.items())
    ]

    if not sorted_clips:
        return []

    def _assemble(clip: ClipInfo) -> etree._Element:
        """Extract, strip automation, and normalise a clip for comparison."""
        if instrument_type == "synth":
            element = extract_synth(inst.element, clip.element)
        else:
            element, _warnings = extract_kit(inst.element, clip.element)
        _strip_automation(element)
        normalise_params(element, instrument_type, normalisation_config)
        return element

    # 2. Baseline clip (lowest section ID) is always accepted.
    baseline_clip = sorted_clips[0]
    baseline_preset = _assemble(baseline_clip)

    accepted: list[tuple[ClipInfo, list[ComparisonResult]]] = [
        (baseline_clip, [])
    ]
    accepted_presets: list[etree._Element] = [baseline_preset]

    # 3. Compare each subsequent clip against ALL accepted presets.
    for candidate_clip in sorted_clips[1:]:
        candidate_preset = _assemble(candidate_clip)

        comparisons: list[ComparisonResult] = []
        is_distinct_from_all = True

        for accepted_preset in accepted_presets:
            result = compare_instruments(
                candidate_preset,
                accepted_preset,
                instrument_type,
                comparison_config,
            )
            comparisons.append(result)
            if not result.is_distinct:
                is_distinct_from_all = False
                break  # similar to at least one — reject

        if is_distinct_from_all:
            accepted.append((candidate_clip, comparisons))
            accepted_presets.append(candidate_preset)

    return accepted


# ---------------------------------------------------------------------------
# Cross-Song Deduplication (Task 5.1)
# ---------------------------------------------------------------------------


def _dedup_pass(
    results: list[ExtractionResult],
    config: ComparisonConfig,
    group_key: Callable[[ExtractionResult], tuple],
    sort_key: Callable[[ExtractionResult], tuple],
    *,
    verbose: bool = False,
    label: str = "dedup",
) -> DedupResult:
    """Run a single deduplication pass with configurable grouping and sorting.

    Groups extraction results by *group_key*, sorts within each group by
    *sort_key*, then applies incremental acceptance: the first result in each
    group is the baseline; subsequent results are compared against all accepted
    results in the group.  If distinct from all → accept; if similar to any →
    reject.

    Returns:
        A :class:`DedupResult` with accepted and rejected lists.
    """
    _LABEL_MAP = {
        "dedup-name": "Deduplication (by name)",
        "dedup-global": "Deduplication (global)",
    }
    friendly_label = _LABEL_MAP.get(label, label)

    groups: dict[tuple, list[ExtractionResult]] = {}
    for r in results:
        groups.setdefault(group_key(r), []).append(r)

    accepted: list[ExtractionResult] = []
    rejected: list[RejectedResult] = []

    total = len(results)
    compared = 0

    for _key, group in sorted(groups.items()):
        group.sort(key=sort_key)

        if len(group) == 1:
            accepted.append(group[0])
            compared += 1
            if not verbose:
                print(f"\r{friendly_label}... compared {compared}/{total}", end="", flush=True)
            continue

        if verbose:
            print(f"[{label}] Group: {_key} — {len(group)} versions")

        baseline = group[0]
        accepted.append(baseline)
        accepted_in_group: list[ExtractionResult] = [baseline]
        compared += 1
        if not verbose:
            print(f"\r{friendly_label}... compared {compared}/{total}", end="", flush=True)

        if verbose:
            print(f"[{label}]   baseline: {baseline.song_name}")

        for candidate in group[1:]:
            is_distinct_from_all = True
            matched: ExtractionResult | None = None
            matched_comparison: ComparisonResult | None = None

            for accepted_result in accepted_in_group:
                comparison = compare_instruments(
                    candidate.element,
                    accepted_result.element,
                    candidate.instrument_type,
                    config,
                )
                if verbose:
                    verdict = "distinct" if comparison.is_distinct else "similar"
                    print(
                        f"[{label}]   {candidate.song_name} vs"
                        f" {accepted_result.song_name}"
                        f" → {verdict} ({comparison.reason})"
                    )
                if not comparison.is_distinct:
                    is_distinct_from_all = False
                    matched = accepted_result
                    matched_comparison = comparison
                    break

            if is_distinct_from_all:
                accepted.append(candidate)
                accepted_in_group.append(candidate)
                compared += 1
                if not verbose:
                    print(f"\r{friendly_label}... compared {compared}/{total}", end="", flush=True)
                if verbose:
                    print(f"[{label}]   → accepted {candidate.song_name}")
            else:
                assert matched is not None
                assert matched_comparison is not None
                rejected.append(
                    RejectedResult(
                        result=candidate,
                        matched_result=matched,
                        comparison=matched_comparison,
                    )
                )
                compared += 1
                if not verbose:
                    print(f"\r{friendly_label}... compared {compared}/{total}", end="", flush=True)
                if verbose:
                    print(
                        f"[{label}]   → rejected {candidate.song_name}"
                        f" (matches {matched.song_name})"
                    )

    if not verbose and total > 0:
        print(f"\r{friendly_label}... compared {total}/{total} — COMPLETE")

    return DedupResult(accepted=accepted, rejected=rejected)


def deduplicate_results(
    results: list[ExtractionResult],
    config: ComparisonConfig,
    *,
    verbose: bool = False,
) -> DedupResult:
    """Filter redundant instruments across songs using two dedup passes.

    **Pass 1 (by name):** Groups by ``(preset_name, instrument_type)`` and
    sorts by ``song_name``.  This catches duplicates of the same named preset
    across multiple songs.

    **Pass 2 (global):** Groups accepted results from pass 1 by
    ``(instrument_type,)`` only and sorts by ``(preset_name, song_name)``.
    This catches cross-name duplicates (e.g. "000" vs "000 TR-808").

    Args:
        results: Full list of :class:`ExtractionResult` objects (post-extraction,
            post-normalisation).
        config: Comparison ruleset for the generalised comparison engine.
        verbose: Print detailed comparison logging.

    Returns:
        A :class:`DedupResult` with accepted, rejected, and per-stage lists.
    """

    # Pass 1: group by (preset_name, instrument_type)
    name_result = _dedup_pass(
        results,
        config,
        group_key=lambda r: (r.preset_name, r.instrument_type),
        sort_key=lambda r: (r.song_name,),
        verbose=verbose,
        label="dedup-name",
    )

    # Pass 2: group accepted results by (instrument_type,) only
    global_result = _dedup_pass(
        name_result.accepted,
        config,
        group_key=lambda r: (r.instrument_type,),
        sort_key=lambda r: (r.preset_name, r.song_name),
        verbose=verbose,
        label="dedup-global",
    )

    # Combine rejected from both passes
    all_rejected = name_result.rejected + global_result.rejected

    return DedupResult(
        accepted=global_result.accepted,
        rejected=all_rejected,
        name_pass_rejected=name_result.rejected,
        global_pass_rejected=global_result.rejected,
    )


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
        drum_index = noterow.get("drumIndex", "?")
        msg = f"WARNING: noteRow (drumIndex={drum_index}) has no <soundParams> — skipping"
        print(msg)
        return [msg]

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


def _ensure_all_sounds_have_default_params(
    sounds: list[etree._Element],
) -> list[str]:
    """Ensure every <sound> in a kit has a <defaultParams> child.

    After the noteRow merge pass, some sounds may still lack <defaultParams>
    (e.g. drums the user never programmed notes for). A standalone kit preset
    requires every sound to have <defaultParams> — without it the Deluge
    cannot load the kit.

    Strategy:
        1. Find the first sound that already has <defaultParams> → use as template
        2. For any sound missing <defaultParams>, deep-clone the template and insert it
        3. If NO sound has <defaultParams> (extremely unlikely), fall back to
           a minimal hardcoded init structure

    Returns:
        A list of warning strings for each sound that received default params.
    """
    # Find a template <defaultParams> from an existing sound
    template: etree._Element | None = None
    for sound in sounds:
        dp = sound.find("defaultParams")
        if dp is not None:
            template = dp
            break

    warnings: list[str] = []
    for idx, sound in enumerate(sounds):
        if sound.find("defaultParams") is not None:
            continue

        # Clone from template or create from init values
        if template is not None:
            new_dp = copy.deepcopy(template)
        else:
            new_dp = _create_init_default_params()

        name = sound.get("name", f"index {idx}")
        warnings.append(
            f"Kit sound {name!r} (index {idx})"
            " has no clip parameters — using defaults"
        )

        # Insert after <unison> to match expected element order
        unison = sound.find("unison")
        if unison is not None:
            unison_idx = list(sound).index(unison)
            sound.insert(unison_idx + 1, new_dp)
        else:
            sound.append(new_dp)

    return warnings


def _create_init_default_params() -> etree._Element:
    """Create a minimal <defaultParams> element with init kit sound values.

    Hardcoded from Init-Kit.XML's per-sound <defaultParams>. Used only as a
    last-resort fallback when no other sound in the kit has <defaultParams>
    to clone from.
    """
    dp = etree.Element(
        "defaultParams",
        arpeggiatorGate="0x00000000",
        portamento="0x80000000",
        compressorShape="0xDC28F5B2",
        oscAVolume="0x7FFFFFFF",
        oscAPulseWidth="0x00000000",
        oscAWavetablePosition="0x00000000",
        oscBVolume="0x80000000",
        oscBPulseWidth="0x00000000",
        oscBWavetablePosition="0x00000000",
        noiseVolume="0x80000000",
        volume="0x4CCCCCA8",
        pan="0x00000000",
        lpfFrequency="0x7FFFFFFF",
        lpfResonance="0x80000000",
        hpfFrequency="0x80000000",
        hpfResonance="0x80000000",
        lfo1Rate="0x1999997E",
        lfo2Rate="0x00000000",
        modulator1Amount="0x80000000",
        modulator1Feedback="0x80000000",
        modulator2Amount="0x80000000",
        modulator2Feedback="0x80000000",
        carrier1Feedback="0x80000000",
        carrier2Feedback="0x80000000",
        modFXRate="0x00000000",
        modFXDepth="0x00000000",
        delayRate="0x00000000",
        delayFeedback="0x80000000",
        reverbAmount="0x80000000",
        arpeggiatorRate="0x00000000",
        stutterRate="0x00000000",
        sampleRateReduction="0x80000000",
        bitCrush="0x80000000",
        modFXOffset="0x00000000",
        modFXFeedback="0x00000000",
        compressorThreshold="0x00000000",
        lpfMorph="0x80000000",
        hpfMorph="0x80000000",
        waveFold="0x80000000",
        ratchetProbability="0x80000000",
        ratchetAmount="0x80000000",
        sequenceLength="0x80000000",
        rhythm="0x80000000",
    )
    etree.SubElement(
        dp, "envelope1",
        attack="0x80000000", decay="0xE6666654",
        sustain="0x7FFFFFD2", release="0x80000000",
    )
    etree.SubElement(
        dp, "envelope2",
        attack="0xE6666654", decay="0xE6666654",
        sustain="0xFFFFFFE9", release="0xE6666654",
    )
    patch_cables = etree.SubElement(dp, "patchCables")
    etree.SubElement(
        patch_cables, "patchCable",
        source="velocity", destination="volume", amount="0x3FFFFFE8",
    )
    etree.SubElement(
        dp, "equalizer",
        bass="0x00000000", treble="0x00000000",
        bassFrequency="0x00000000", trebleFrequency="0x00000000",
    )
    return dp


def _parse_hex_value(hex_str: str) -> int:
    """Parse a Deluge hex string (e.g. '0x4CCCCCA8') as a 32-bit signed integer.

    For extended hex strings containing automation data (longer than 10 chars),
    uses only the first 10 characters (the static value) per D15.
    """
    if len(hex_str) > 10:
        hex_str = hex_str[:10]
    raw = int(hex_str, 16)
    if raw >= 0x80000000:
        raw -= 0x100000000
    return raw


def _hex_diff_exceeds(val_a: str, val_b: str, threshold: float) -> bool:
    """Return True if two hex param values differ by more than *threshold* proportion."""
    a = _parse_hex_value(val_a)
    b = _parse_hex_value(val_b)
    return abs(a - b) / _HEX_FULL_RANGE > threshold


def _build_patchcable_dict(
    default_params: etree._Element | None,
) -> dict[tuple[str, str], str]:
    """Build a ``(source, destination) -> amount`` dict from ``<patchCables>``."""
    result: dict[tuple[str, str], str] = {}
    if default_params is None:
        return result
    patch_cables = default_params.find("patchCables")
    if patch_cables is None:
        return result
    for cable in patch_cables:
        if cable.tag != "patchCable":
            continue
        src = cable.get("source", "")
        dst = cable.get("destination", "")
        amount = cable.get("amount", "")
        result[(src, dst)] = amount
    return result


def _check_patchcable_structure(
    dp_a: etree._Element | None,
    dp_b: etree._Element | None,
) -> list[str]:
    """Return hard diffs if patchCable ``(source, destination)`` sets differ."""
    cables_a = _build_patchcable_dict(dp_a)
    cables_b = _build_patchcable_dict(dp_b)
    keys_a = set(cables_a)
    keys_b = set(cables_b)
    if keys_a == keys_b:
        return []
    added = keys_b - keys_a
    removed = keys_a - keys_b
    parts: list[str] = []
    if added:
        parts.append(f"added {sorted(added)}")
    if removed:
        parts.append(f"removed {sorted(removed)}")
    return [f"patchCables structure: {'; '.join(parts)}"]


def _collect_soft_diffs(
    dp_a: etree._Element | None,
    dp_b: etree._Element | None,
    root_a: etree._Element,
    root_b: etree._Element,
    config: ComparisonConfig,
    prefix: str = "",
    soft_elements: dict[str, set[str]] | None = None,
) -> list[str]:
    """Collect soft-marker differences for one comparison scope.

    Walks ``<defaultParams>`` attributes and children (``envelope1``,
    ``envelope2``, ``equalizer``), matching patchCable amounts,
    instrument-level ``<delay>``, ``<sidechain>``, ``<audioCompressor>``,
    and configurable child elements (osc1/osc2 cents, lfo syncLevel, etc.).
    """
    diffs: list[str] = []
    threshold = config.param_percent_threshold
    ignored = config.ignored_attrs
    pfx = f"{prefix}." if prefix else ""

    # 1. defaultParams attributes
    if dp_a is not None and dp_b is not None:
        all_attrs = set(dp_a.attrib) | set(dp_b.attrib)
        for attr in sorted(all_attrs):
            if attr in ignored:
                continue
            val_a = dp_a.get(attr, "")
            val_b = dp_b.get(attr, "")
            if val_a == val_b:
                continue
            if _HEX_VALUE_RE.match(val_a) and _HEX_VALUE_RE.match(val_b):
                if _hex_diff_exceeds(val_a, val_b, threshold):
                    diffs.append(f"{pfx}defaultParams.{attr}")
            else:
                diffs.append(f"{pfx}defaultParams.{attr}")

    # 2. defaultParams children: envelope1, envelope2, equalizer
    if dp_a is not None and dp_b is not None:
        for child_tag in ("envelope1", "envelope2", "equalizer"):
            el_a = dp_a.find(child_tag)
            el_b = dp_b.find(child_tag)
            if el_a is None and el_b is None:
                continue
            attrs_a = dict(el_a.attrib) if el_a is not None else {}
            attrs_b = dict(el_b.attrib) if el_b is not None else {}
            all_attrs = set(attrs_a) | set(attrs_b)
            for attr in sorted(all_attrs):
                if attr in ignored:
                    continue
                va = attrs_a.get(attr, "")
                vb = attrs_b.get(attr, "")
                if va == vb:
                    continue
                if _HEX_VALUE_RE.match(va) and _HEX_VALUE_RE.match(vb):
                    if _hex_diff_exceeds(va, vb, threshold):
                        diffs.append(f"{pfx}{child_tag}.{attr}")
                else:
                    diffs.append(f"{pfx}{child_tag}.{attr}")

    # 3. PatchCable amounts (matching cables only — structure is a hard marker)
    cables_a = _build_patchcable_dict(dp_a)
    cables_b = _build_patchcable_dict(dp_b)
    for key in sorted(set(cables_a) & set(cables_b)):
        va = cables_a[key]
        vb = cables_b[key]
        if va == vb:
            continue
        if _HEX_VALUE_RE.match(va) and _HEX_VALUE_RE.match(vb):
            if _hex_diff_exceeds(va, vb, threshold):
                src, dst = key
                diffs.append(f"{pfx}patchCable({src}->{dst}).amount")
        else:
            src, dst = key
            diffs.append(f"{pfx}patchCable({src}->{dst}).amount")

    # 4. Instrument-level: delay, sidechain, audioCompressor (D24)
    for elem_tag in ("delay", "sidechain", "audioCompressor"):
        el_a = root_a.find(elem_tag)
        el_b = root_b.find(elem_tag)
        if el_a is None and el_b is None:
            continue
        attrs_a = dict(el_a.attrib) if el_a is not None else {}
        attrs_b = dict(el_b.attrib) if el_b is not None else {}
        all_attrs = set(attrs_a) | set(attrs_b)
        for attr in sorted(all_attrs):
            if attr in ignored:
                continue
            va = attrs_a.get(attr, "")
            vb = attrs_b.get(attr, "")
            if va == vb:
                continue
            if _HEX_VALUE_RE.match(va) and _HEX_VALUE_RE.match(vb):
                if _hex_diff_exceeds(va, vb, threshold):
                    diffs.append(f"{pfx}{elem_tag}.{attr}")
            else:
                diffs.append(f"{pfx}{elem_tag}.{attr}")

    # 5. Configurable child elements (osc1/osc2 cents, lfo syncLevel, etc.)
    if soft_elements:
        for elem_tag, skip_attrs in sorted(soft_elements.items()):
            el_a = root_a.find(elem_tag)
            el_b = root_b.find(elem_tag)
            if el_a is None and el_b is None:
                continue
            attrs_a = dict(el_a.attrib) if el_a is not None else {}
            attrs_b = dict(el_b.attrib) if el_b is not None else {}
            all_attrs = set(attrs_a) | set(attrs_b)
            for attr in sorted(all_attrs):
                if attr in ignored or attr in skip_attrs:
                    continue
                va = attrs_a.get(attr, "")
                vb = attrs_b.get(attr, "")
                if va == vb:
                    continue
                if _HEX_VALUE_RE.match(va) and _HEX_VALUE_RE.match(vb):
                    if _hex_diff_exceeds(va, vb, threshold):
                        diffs.append(f"{pfx}{elem_tag}.{attr}")
                else:
                    diffs.append(f"{pfx}{elem_tag}.{attr}")

    return diffs


def _check_kit_structure_hard(
    preset_a: etree._Element,
    preset_b: etree._Element,
    hard_attrs: dict[str, set[str]],
    config: ComparisonConfig,
) -> list[str]:
    """Check kit structural hard markers: soundSources count/names, per-sound attrs."""
    diffs: list[str] = []

    ss_a = preset_a.find("soundSources")
    ss_b = preset_b.find("soundSources")
    sounds_a = list(ss_a) if ss_a is not None else []
    sounds_b = list(ss_b) if ss_b is not None else []

    if "soundSources" in hard_attrs:
        sentinels = hard_attrs["soundSources"]
        if "_count" in sentinels and len(sounds_a) != len(sounds_b):
            diffs.append(
                f"soundSources count: {len(sounds_a)} vs {len(sounds_b)}"
            )
            return diffs  # can't compare per-sound if counts differ

        if "_names" in sentinels:
            names_a = [s.get("name", "") for s in sounds_a]
            names_b = [s.get("name", "") for s in sounds_b]
            if names_a != names_b:
                diffs.append(f"soundSources names: {names_a} vs {names_b}")
                return diffs  # can't compare per-sound if names differ

    # Per-sound root attrs (soundSources/sound — attrs on the <sound> element itself)
    if "soundSources/sound" in hard_attrs:
        sound_root_attrs = hard_attrs["soundSources/sound"]
        for i, (sa, sb) in enumerate(zip(sounds_a, sounds_b, strict=True)):
            for attr in sorted(sound_root_attrs):
                if attr.startswith("_") or attr in config.ignored_attrs:
                    continue
                va = sa.get(attr, "")
                vb = sb.get(attr, "")
                if va != vb:
                    name = sa.get("name", f"index {i}")
                    diffs.append(
                        f"sound[{name}].{attr}: {va!r} vs {vb!r}"
                    )

    # Per-sound child hard attrs (e.g. soundSources/sound/osc1)
    for path_key, attrs in sorted(hard_attrs.items()):
        if not path_key.startswith("soundSources/sound/"):
            continue
        child_tag = path_key.rsplit("/", 1)[-1]
        for i, (sa, sb) in enumerate(zip(sounds_a, sounds_b, strict=True)):
            el_a = sa.find(child_tag)
            el_b = sb.find(child_tag)
            for attr in sorted(attrs):
                if attr.startswith("_") or attr in config.ignored_attrs:
                    continue
                va = el_a.get(attr, "") if el_a is not None else ""
                vb = el_b.get(attr, "") if el_b is not None else ""
                if va != vb:
                    name = sa.get("name", f"index {i}")
                    diffs.append(
                        f"sound[{name}].{child_tag}.{attr}: {va!r} vs {vb!r}"
                    )

    # Per-sound patchCable structure
    for i, (sa, sb) in enumerate(zip(sounds_a, sounds_b, strict=True)):
        sdp_a = sa.find("defaultParams")
        sdp_b = sb.find("defaultParams")
        pc_diffs = _check_patchcable_structure(sdp_a, sdp_b)
        if pc_diffs:
            name = sa.get("name", f"index {i}")
            diffs.extend(f"sound[{name}].{d}" for d in pc_diffs)

    return diffs


def _compare_kit_soft(
    preset_a: etree._Element,
    preset_b: etree._Element,
    config: ComparisonConfig,
) -> ComparisonResult:
    """Evaluate soft markers for kits with per-sound threshold checking."""
    all_soft_diffs: list[str] = []

    # Kit-level soft markers
    dp_a = preset_a.find("defaultParams")
    dp_b = preset_b.find("defaultParams")
    kit_diffs = _collect_soft_diffs(dp_a, dp_b, preset_a, preset_b, config)

    if len(kit_diffs) >= config.param_count_threshold:
        return ComparisonResult(
            is_distinct=True,
            hard_diffs=[],
            soft_diff_count=len(kit_diffs),
            soft_diffs=kit_diffs,
            reason=(
                f"soft: {len(kit_diffs)} kit-level params differ"
                f" >{config.param_percent_threshold:.0%}"
            ),
        )
    all_soft_diffs.extend(kit_diffs)

    # Per-sound soft markers
    ss_a = preset_a.find("soundSources")
    ss_b = preset_b.find("soundSources")
    sounds_a = list(ss_a) if ss_a is not None else []
    sounds_b = list(ss_b) if ss_b is not None else []

    for sa, sb in zip(sounds_a, sounds_b, strict=True):
        sdp_a = sa.find("defaultParams")
        sdp_b = sb.find("defaultParams")
        name = sa.get("name", "")
        sound_diffs = _collect_soft_diffs(
            sdp_a, sdp_b, sa, sb, config, prefix=f"sound[{name}]",
            soft_elements=config.kit_sound_soft_elements,
        )

        if len(sound_diffs) >= config.param_count_threshold:
            all_soft_diffs.extend(sound_diffs)
            return ComparisonResult(
                is_distinct=True,
                hard_diffs=[],
                soft_diff_count=len(all_soft_diffs),
                soft_diffs=all_soft_diffs,
                reason=(
                    f"soft: sound[{name}] has {len(sound_diffs)} params differ"
                    f" >{config.param_percent_threshold:.0%}"
                ),
            )
        all_soft_diffs.extend(sound_diffs)

    count = len(all_soft_diffs)
    return ComparisonResult(
        is_distinct=False,
        hard_diffs=[],
        soft_diff_count=count,
        soft_diffs=all_soft_diffs,
        reason=(
            f"similar: {count} soft diffs"
            f" (threshold: {config.param_count_threshold})"
        ),
    )



