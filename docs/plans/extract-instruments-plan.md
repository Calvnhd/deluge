# Plan: Extract Instruments from Songs

> **Document Type:** Plan
> **Date:** 14 April 2026
> **Research:** [extract-instruments-research.md](../research/extract-instruments-research.md)
> **Pipeline:** Research → **Plan** → Implement
> **Status:** Draft

## Executive Summary

Build a script that scans all song XMLs in `DELUGE/SONGS/`, extracts embedded synth and kit instruments as standalone preset XMLs, and writes them to `DELUGE/SYNTHS/SONG-SYNTHS/` and `DELUGE/KITS/SONG-KITS/`. The script merges the split instrument structure (from `<instruments>`) with clip-level parameters (from `<sessionClips>`) and arpeggiator data, normalises master volume and pan, and outputs firmware `c1.2.1` standalone presets. Two modes are supported: default mode extracts one version per instrument (lowest section ID), and extended mode extracts multiple versions when parameters differ significantly. Research Section 13.5 provides the definitive transformation recipes.

## Research Summary

Key findings from the [research document](../research/extract-instruments-research.md):

- **Split architecture (Section 3):** Instrument structure lives in `<instruments>`, tuneable parameters live in clip-level `<soundParams>`/`<kitParams>`, and synth arpeggiators live at clip level. Extraction requires merging these sources.
- **Transformation recipes (Section 13.5):** Precise, verified step-by-step procedures for both synth and kit extraction, including element reordering, attribute stripping, and tag renaming.
- **Kit arpeggiator asymmetry (Section 13.6):** Kit sounds keep their arpeggiator in the instrument definition; synth arpeggiators live at clip level. Different handling required.
- **Existing assets (Section 10):** `parse_deluge_xml()`, `get_deluge_root()`, `scan_tree()`, `confirm_apply()`, dataclass patterns, and `pyproject.toml` entry points are all reusable.
- **All 58 songs use `c1.2.1` firmware (Section 11):** Single format target simplifies extraction. Warn and skip songs with other firmware.
- **Recommended approach:** Merge instrument + clip params (Approach A) — the only viable approach since active instruments lack `<defaultParams>`.

Authoritative user decisions from [extraction-questions.md](../../temp/extraction-questions.md) supplement the research and take precedence where conflicts exist.

## Decisions Log

| ID | Decision | Rationale | Alternatives Considered |
|----|----------|-----------|------------------------|
| D1 | Python with lxml, pathlib, python-dotenv | Matches existing codebase (pyproject.toml, all other scripts). Cross-platform requirement satisfied by pathlib. Python standard: `standards/languages/python/` | None — codebase is Python-only |
| D2 | Standalone script `extract_instruments.py` + reusable functions in `deluge_lib/` | User decision (Q36, Q38). Thin CLI in `scripts/extract_instruments.py`, core logic in `scripts/deluge_lib/extraction.py`. Follows existing pattern where scripts import from `deluge_lib/`. | Self-contained script (rejected — user wants reusable functions) |
| D3 | Default mode = lowest section ID clip | User decision (Q7, Q8). Simple, deterministic, favours the default colour (section 0 = light blue). | First clip encountered in XML (rejected — non-deterministic) |
| D4 | Extended mode threshold: ≥3 numerical params differ by >10%, OR any structural/non-numerical change | User decision (Q10, Q11). Thresholds stored as module-level constants for easy tuning. Automation data ignored for comparison purposes. | Fixed parameter whitelist (rejected — too rigid); modKnob-weighted comparison (deferred as future refinement per research Section 15.5) |
| D5 | Filename: `<SongName>-<PresetName>.XML` (default), `<SongName>-<PresetName>-<Abbr>.XML` (extended) | User decisions (Q13-Q16). Flat directory. Spaces preserved. Collision resolved by appending number. Extended mode uses 3-letter colour abbreviation. | Numeric section ID suffix (rejected — user prefers readable abbreviation); nested folders by presetFolder (rejected Q14) |
| D6 | Normalise only `volume` and `pan` on `<defaultParams>` — synth master → init synth value, kit master → init kit value, pan → centre | User decisions (Q21-Q25). Kit row volume and pan preserved (Q22, Q23). PatchCable volume destinations untouched. Extendable ignore list for future additions (Q24). | Scale row volumes relative to master (rejected Q22); normalise additional params (rejected Q24) |
| D7 | Orphaned instruments: skip with warning | User decision (Q2). Orphaned instruments are assumed to be arrangement-only remnants. Print warning for user awareness. | Extract with `-orphaned` suffix (deferred); extract all (rejected) |
| D8 | Trash entire `SONG-SYNTHS/` and `SONG-KITS/` directories before each run | User decision (Q30). Fresh extraction each time. Existing `.trash` pattern from codebase. | Trash individual files (rejected — more complex for no benefit in v1) |
| D9 | No `presetName` attribute in output XML | User decision (Q17) confirmed by research. Standalone presets identify by filename, not XML attribute. | Include presetName (rejected — not present in any standalone preset) |
| D10 | Keep automation data in extracted params | User decision (Q33). Extended hex strings in `<soundParams>` attributes preserved verbatim. | Strip automation to initial value (rejected) |
| D11 | Firmware check = warn and skip, not abort | User decision (Q34). Future syncs may bring non-c1.2.1 songs. Script continues processing remaining songs. | Hard fail (rejected — too disruptive) |
| D12 | Clip arpeggiator is the source for synths; strip extra numeric attrs | Research Section 13.6. Synth instruments have no arpeggiator in `<instruments>` — it lives at clip level only. Extra attrs (`gate`, `rate`, `ratchetProbability`, `ratchetAmount`, `sequenceLength`, `rhythm`) are duplicates of `<soundParams>` values and must be stripped. User confirmed (Q35). | Use instrument-level arpeggiator (not viable — doesn't exist for synths) |
| D13 | Ignore arrangement-only clips and `<arrangementOnlyClips>` entirely | User decision (Q4). Session clips only. | Include arrangement clips (deferred) |
| D14 | Duplicate clips in same section: take first, warn about second | User decision (Q9). | Take both (rejected — would produce near-identical extractions) |
| D15 | Extended mode comparison ignores automation data | User decision (Q10 clarification). Automation is song-specific playback data, not a meaningful instrument difference. For comparison, use the raw attribute value; if it's an extended hex string (automation), treat the value as unchanged from other versions that also have automation or use the first hex value segment. | Include automation in comparison (rejected) |

## Technical Specification

### 5a. Language and Tooling

| Item | Choice | Notes |
|------|--------|-------|
| Language | Python 3.12+ | Standard: `agent-system/standards/languages/python/` |
| Package Manager | uv / pip | Existing pyproject.toml with hatchling build backend |
| Linter/Formatter | Ruff | Existing config in pyproject.toml (line-length 100, py312 target) |
| Type Checker | mypy | Existing dev dependency |
| Test Framework | pytest | Existing dev dependency |
| Key Dependencies | lxml ≥5.0.0, python-dotenv ≥1.0.0 | Already in pyproject.toml — no new dependencies |

### 5b. Architecture

The feature follows the existing codebase pattern: a thin CLI script imports reusable logic from `deluge_lib/`.

**Module responsibilities:**

- `scripts/deluge_lib/extraction.py` — Core extraction logic. Contains all reusable functions: song parsing, instrument-clip matching, synth/kit transformation, version comparison, normalisation, and XML serialisation. This module has no CLI concerns, no I/O side effects (except receiving parsed XML trees and returning data structures), and no user interaction.
- `scripts/extract_instruments.py` — CLI entry point. Handles argument parsing, file discovery, dry-run logic, trash management, file writing, manifest generation, and console output. Calls into `extraction.py` for all domain logic.

**Data flow:**

1. CLI loads config (`DELUGE_ROOT` from `.env`) and parses arguments
2. CLI discovers all song XMLs in `DELUGE_ROOT/SONGS/`
3. For each song, CLI passes the parsed XML tree to extraction functions
4. Extraction functions return structured results (dataclasses) describing what to extract
5. CLI handles output: trash previous runs, write XML files, generate manifest, print summary

**Key data structures (conceptual — the implementer defines the concrete representation):**

- An extraction result for each instrument: carries the song name, preset name, instrument type (synth/kit), section ID, colour abbreviation, the assembled standalone XML element tree, and metadata for the manifest
- A version comparison result: carries whether two clip versions are considered distinct, and the parameters that differ
- A normalisation config: which attributes to normalise and their target values, stored as a data structure that can be extended

**File layout after implementation:**

```
scripts/
├── extract_instruments.py          # CLI entry point
├── pyproject.toml                  # Updated with new entry point
├── deluge_lib/
│   ├── extraction.py               # Core extraction logic
│   └── ...                         # Existing modules unchanged
├── tests/
│   ├── test_extraction.py          # Unit tests for extraction logic
│   └── fixtures/                   # Test fixture XMLs
└── data/
    └── ...                         # Existing data files
```

**Output directory layout:**

```
DELUGE/
├── SYNTHS/
│   └── SONG-SYNTHS/                # Flat directory of extracted synths
│       ├── Bloop-133.XML
│       ├── K01Sink-K01Bass.XML
│       ├── K01Sink-K01Arp-Lbl.XML  # Extended mode with colour abbr
│       └── ...
├── KITS/
│   └── SONG-KITS/                  # Flat directory of extracted kits
│       ├── Bloop-000.XML
│       └── ...
└── SONGS/                          # Unchanged — never modified
```

### 5c. Interface Design

**Inputs:**

| Input | Source | Description |
|-------|--------|-------------|
| `DELUGE_ROOT` | `scripts/.env` | Path to `DELUGE/` directory. Loaded via `get_deluge_root()` |
| `--extended` | CLI flag | Enable extended mode (extract multiple versions per instrument) |
| `--dry-run` | CLI flag | List extractions without writing files. Default behaviour when no flag is given — matches existing script conventions |
| Song XMLs | `DELUGE_ROOT/SONGS/*.XML` | All song XMLs discovered recursively |
| Init presets | `DELUGE_ROOT/SYNTHS/Init-Synth.XML`, `DELUGE_ROOT/KITS/Init-Kit.XML` | Reference volume/pan values for normalisation |

**Outputs:**

| Output | Location | Description |
|--------|----------|-------------|
| Standalone synth XMLs | `DELUGE_ROOT/SYNTHS/SONG-SYNTHS/` | One or more per instrument per song |
| Standalone kit XMLs | `DELUGE_ROOT/KITS/SONG-KITS/` | One or more per instrument per song |
| Manifest JSON | `DELUGE_ROOT/SYNTHS/SONG-SYNTHS/manifest.json` and `DELUGE_ROOT/KITS/SONG-KITS/manifest.json` | Maps each extraction to source song, instrument, section, and key metadata |
| Console output | stdout | Per-extraction listing and final summary |

**Console output format:**

```
Scanning 58 songs...

WARNING: Skipping Arpo.XML — orphaned instrument "000" (no session clips)
WARNING: K01Sink.XML — duplicate clip for "K01Bass" in section 6, taking first

Bloop.XML
  SYNTH  133                → SONG-SYNTHS/Bloop-133.XML
  SYNTH  166                → SONG-SYNTHS/Bloop-166.XML
  KIT    000                → SONG-KITS/Bloop-000.XML
K01Sink.XML
  SYNTH  K01Bass            → SONG-SYNTHS/K01Sink-K01Bass.XML
  SYNTH  K01Arp             → SONG-SYNTHS/K01Sink-K01Arp.XML
  ...

Summary: Extracted 45 synths and 12 kits from 58 songs
  Output: DELUGE/SYNTHS/SONG-SYNTHS/ (45 files)
  Output: DELUGE/KITS/SONG-KITS/ (12 files)

Apply these changes? [y/N]
```

In dry-run mode, the final confirmation prompt is skipped and a `(dry run)` label is shown.

**Error handling strategy:**

- Firmware version mismatch → warn, skip song, continue (D11)
- Orphaned instrument → warn, skip, continue (D7)
- Duplicate clip in same section → warn, take first, continue (D14)
- Missing init preset files → abort with clear error (these are required for normalisation values)
- XML parse failure → warn, skip song, continue (reuse `parse_deluge_xml()` fallback logic)
- drumIndex mismatch in kit noteRows → warn, skip that noteRow, continue
- Filename collision → append incrementing number (D5)

**User interaction:**

- Dry-run is the default (matches existing script convention from `sync_from_sd.py`)
- After dry-run preview, prompt for confirmation before writing (using `confirm_apply()` pattern)
- `--dry-run` flag forces dry-run only (no prompt)
- No interactive prompts during extraction logic itself

### 5d. Integration Points

- **`deluge_lib/cli_utils.py`** — Reuse `get_deluge_root()` for environment loading
- **`deluge_lib/deluge_sdk.py`** — Reuse `parse_deluge_xml()` for XML parsing. Consider whether `find_all_xml_files()` is suitable or if a simpler song-specific discovery is better (it currently scans all three subdirectories)
- **`deluge_lib/scanning.py`** — Reuse `scan_tree()` if needed for file discovery, though a simpler `Path.glob()` for `SONGS/*.XML` may suffice
- **`pyproject.toml`** — Add `deluge-extract = "extract_instruments:main"` entry point
- **SD card safety compliance:** The script reads from `DELUGE/SONGS/` and writes to `DELUGE/SYNTHS/SONG-SYNTHS/` and `DELUGE/KITS/SONG-KITS/`. All operations are within the repository `DELUGE/` directory (permitted per project standard). No SD card writes. Song XMLs are never modified.

## Cross-Cutting Concerns

| Concern (from Research) | Planned Mitigation |
|---|---|
| **Sample references** | Extracted kits preserve sample paths verbatim from the song XML. Paths are relative to `DELUGE/` and remain valid since samples don't move. |
| **Sync-to-SD workflow** | `SONG-SYNTHS/` and `SONG-KITS/` are within the standard `SYNTHS/` and `KITS/` directories. `sync_to_sd.py` will include them automatically. No changes needed. |
| **verify_references.py** | Will automatically find and check sample references in extracted kit presets. No changes needed. |
| **fix_references.py** | Will automatically update sample references in extracted presets if samples are moved. No changes needed. |
| **Naming collisions** | Dedicated output subdirectories prevent overwriting user presets. Within the output directory, incrementing numbers resolve same-name instruments. |
| **.env configuration** | Uses existing `DELUGE_ROOT`. No new environment variables. |
| **Cross-platform** | Python + pathlib + lxml. No platform-specific tools. Spaces in filenames are kept (Deluge handles them; both platforms support them). |

## Risk Mitigation

| Risk (from Research) | Plan Mitigation | Residual Risk |
|---|---|---|
| Extracted presets produce unexpected audio | Transformation recipes from Section 13.5 are verified against real standalone presets. Volume/pan normalisation uses init preset reference values. | User should spot-check a few extractions on hardware |
| Kit row drumIndex mismatch | Validate drumIndex against soundSources count. Warn and skip mismatched rows. | Minimal — user confirms this scenario indicates broken XML |
| Special characters cause filesystem issues | Spaces preserved (Deluge handles them). FAT32 sanitisation deemed unnecessary — filenames originate from the FAT32 SD card, so unsafe characters cannot appear. | None |
| Orphaned instruments produce stale presets | Skip orphaned instruments with warning (D7). | None — user aware and can revisit |
| `.trash` replacement deletes user files | Only trash contents of `SONG-SYNTHS/` and `SONG-KITS/`. Never touch parent directories or user preset folders. | Minimal — output dirs are clearly script-managed |
| Synth arpeggiator missed | Extraction explicitly handles clip-level arpeggiator for synths (D12). Strip extra numeric attrs. | Low if tests verify arpeggiator presence |
| Clips without `section` attribute | Treat missing section as section 0 (default colour). Log a warning. | Low — uncommon edge case |
| Element ordering mismatch | Follow verified c1.2.1 standalone ordering from research Sections 6 and 7. | Low if tests compare output ordering with Init presets |
| Parameter automation in soundParams | Preserve all attribute values verbatim (D10). No parsing or truncation of hex strings. | None |
| Extended mode comparison noise | Configurable thresholds (D4). Automation ignored for comparison (D15). Structural/non-numerical changes always trigger extraction. | May need threshold tuning — constants are easily editable |

## Implementation Roadmap

### Phase 1: Foundation

> **Goal:** Set up the module structure, XML parsing infrastructure, and instrument-clip discovery logic
> **Prerequisites:** Existing codebase available, `DELUGE_ROOT` configured in `.env`

#### Task 1.1: Create module and script scaffolding ✅

- **Description:** Create `scripts/deluge_lib/extraction.py` and `scripts/extract_instruments.py` with basic structure. Add pyproject.toml entry point.
- **Inputs:** Existing pyproject.toml, existing deluge_lib module structure
- **Outputs:** Empty module with docstring, CLI script with argparse skeleton (`--extended`, `--dry-run`), pyproject.toml updated
- **Acceptance Criteria:**
  - [x] `scripts/deluge_lib/extraction.py` exists with module docstring
  - [x] `scripts/extract_instruments.py` exists with `main()` function and argparse for `--extended` and `--dry-run`
  - [x] `pyproject.toml` has `deluge-extract = "extract_instruments:main"` entry point
  - [x] `deluge-extract --help` runs successfully
- **Implementation Notes:**
  > Scaffolding completed 15 Apr 2026. Files created:
  > - `scripts/extract_instruments.py` — full CLI pipeline with argparse, discovery loop, extraction loop, trash logic (inline), manifest writing, summary output, dry-run/confirmation flow
  > - `scripts/deluge_lib/extraction.py` — all dataclasses (`InstrumentInfo`, `ClipInfo`, `InstrumentClipGroup`, `VersionComparison`, `NormalisationConfig`, `ExtractionResult`), all function stubs with full signatures and detailed docstrings, all constants defined (init volumes, section colours, element ordering, thresholds, stripped attributes)
  > - Key decisions: dataclasses for all data structures, `NotImplementedError` stubs with task references, constants as module-level tuples/dicts
  > - `pyproject.toml` entry point (`deluge-extract = "extract_instruments:main"`) was already present at line 25 — no addition needed

#### Task 1.2: Song discovery and firmware validation

- **Description:** Implement song XML discovery in `DELUGE_ROOT/SONGS/` and firmware version checking. Songs with firmware other than `c1.2.1` are skipped with a warning.
- **Inputs:** `DELUGE_ROOT` from `.env`, song XMLs
- **Outputs:** List of valid song file paths, warnings for skipped songs
- **Acceptance Criteria:**
  - [x] Discovers all `*.XML` files in `DELUGE_ROOT/SONGS/` (non-recursive — songs are at top level)
  - [x] Parses each song XML using `parse_deluge_xml()` or equivalent
  - [x] Reads `firmwareVersion` attribute from `<song>` root element
  - [x] Skips and warns for songs with firmware ≠ `c1.2.1`
  - [x] Returns list of `(path, parsed_tree)` tuples for valid songs
- **Implementation Notes:**
  > Implemented 15 Apr 2026. `discover_songs()` in `extraction.py`:
  > - Globs `SONGS/*.XML` (sorted for deterministic order), parses each with `parse_deluge_xml()`
  > - Handles wrapper `<root>` case (multi-root fallback) by finding the `<song>` child
  > - Gracefully skips files that fail to parse (catches all exceptions, warns, continues)
  > - Warns and skips songs with `firmwareVersion != "c1.2.1"`
  > - Verified via `--dry-run`: all 58 songs discovered and parsed (13 use recover-mode due to duplicate `isPlaying` attributes, all pass firmware validation). Hits `NotImplementedError` at Task 1.3 as expected.

#### Task 1.3: Instrument and clip discovery

- **Description:** For a parsed song, extract all synth (`<sound>`) and kit (`<kit>`) instruments from `<instruments>`, discover their corresponding clips from `<sessionClips>`, and group clips by instrument and section.
- **Inputs:** Parsed song XML tree
- **Outputs:** Data structure mapping each instrument to its clips, grouped by section ID
- **Acceptance Criteria:**
  - [ ] Discovers all `<sound>` and `<kit>` children of `<instruments>` (ignores `<midi>` and `<audioTrack>`)
  - [ ] Discovers all `<instrumentClip>` children of `<sessionClips>` (ignores `<arrangementOnlyClips>`)
  - [ ] Matches clips to instruments via `instrumentPresetName` + `instrumentPresetFolder` ↔ `presetName` + `presetFolder`
  - [ ] Groups clips by `(presetName, presetFolder)` then by `section` attribute
  - [ ] Identifies orphaned instruments (in `<instruments>` but no matching session clips) and returns them separately with a warning message
  - [ ] Handles missing `section` attribute by treating as section 0 with a warning
  - [ ] For duplicate clips in the same section, keeps the first and records a warning
- **Implementation Notes:**
  > {Space for the Implement agent to add notes during execution}

#### Task 1.4: Version selection (default mode)

- **Description:** For each instrument, select the clip with the lowest section ID as the extraction source.
- **Inputs:** `InstrumentClipGroup` from Task 1.3
- **Outputs:** `ClipInfo` — the selected clip for the instrument
- **Acceptance Criteria:**
  - [ ] Selects the clip with the lowest section ID for each instrument
  - [ ] Returns a `ClipInfo` dataclass (contains element, section, preset_name, preset_folder)
  - [ ] Handles instruments with only one clip (trivial selection)
- **Implementation Notes:**
  > API scaffolded as `select_default_clip(group: InstrumentClipGroup) -> ClipInfo`. Returns a single `ClipInfo` rather than a tuple — the calling code in `main()` accesses `clip_info.section` and `clip_info.element` directly.

### Phase 2: Core Transformation

> **Goal:** Implement the synth and kit XML transformation logic following the research's transformation recipes
> **Prerequisites:** Phase 1 complete — instrument/clip discovery working

#### Task 2.1: Synth extraction transformation

- **Description:** Implement the synth extraction recipe from research Section 13.5. Given a `<sound>` from `<instruments>` and its corresponding `<instrumentClip>`, produce a standalone synth XML element.
- **Inputs:** Instrument `<sound>` element, clip `<instrumentClip>` element
- **Outputs:** Standalone `<sound>` element ready for serialisation
- **Acceptance Criteria:**
  - [ ] Clones the `<sound>` element from `<instruments>` (does not mutate the original tree)
  - [ ] Strips song-specific attributes: `presetName`, `presetFolder`, `defaultVelocity`, `isArmedForRecording`, `activeModFunction`, `clipInstances`, `colour`
  - [ ] Adds `firmwareVersion="c1.2.1"` and `earliestCompatibleFirmware="4.1.0-alpha"`
  - [ ] Extracts `<soundParams>` from clip and renames tag to `<defaultParams>`
  - [ ] Extracts `<arpeggiator>` from clip and strips extra numeric attributes (`gate`, `rate`, `ratchetProbability`, `ratchetAmount`, `sequenceLength`, `rhythm`)
  - [ ] Reorders child elements to match standalone c1.2.1 ordering: `osc1, osc2, lfo1, lfo2, [modulator1, modulator2], unison, defaultParams, arpeggiator, modKnobs, delay, sidechain, audioCompressor`
  - [ ] Preserves all attribute values verbatim (including extended hex automation strings)
  - [ ] Preserves all child elements within `<defaultParams>` (envelopes, patchCables, equalizer)
- **Implementation Notes:**
  > {Space for the Implement agent to add notes during execution}

#### Task 2.2: Kit extraction transformation

- **Description:** Implement the kit extraction recipe from research Section 13.5. Given a `<kit>` from `<instruments>` and its corresponding `<instrumentClip>`, produce a standalone kit XML element.
- **Inputs:** Instrument `<kit>` element, clip `<instrumentClip>` element
- **Outputs:** Standalone `<kit>` element ready for serialisation
- **Acceptance Criteria:**
  - [ ] Clones the `<kit>` element from `<instruments>` (does not mutate the original tree)
  - [ ] Strips song-specific attributes: `presetName`, `presetFolder`, `defaultVelocity`, `isArmedForRecording`, `activeModFunction`, `colour`
  - [ ] Adds `firmwareVersion="c1.2.1"` and `earliestCompatibleFirmware="4.1.0-alpha"`
  - [ ] Extracts `<kitParams>` from clip and renames tag to `<defaultParams>`
  - [ ] Inserts kit-level `<defaultParams>` as the first child of `<kit>` (before `<delay>`)
  - [ ] For each `<noteRow>` in the clip with a `drumIndex`, extracts `<soundParams>`, renames to `<defaultParams>`, and inserts into the corresponding `<sound>` in `<soundSources>` (matched by drumIndex as 0-based index) between `<unison>` and `<arpeggiator>`
  - [ ] Leaves kit sound `<arpeggiator>` elements in place (they are already in the instrument definition)
  - [ ] Warns on drumIndex mismatch (out of range of soundSources) and skips that noteRow
  - [ ] Preserves all attribute values verbatim
  - [ ] Kit-level element ordering matches standalone: `defaultParams, delay, sidechain, audioCompressor, soundSources, selectedDrumIndex`
  - [ ] Per-row sound element ordering matches standalone: `osc1, osc2, lfo1, lfo2, unison, defaultParams, arpeggiator, modKnobs, delay, sidechain, audioCompressor`
- **Implementation Notes:**
  > {Space for the Implement agent to add notes during execution}

#### Task 2.3: Volume and pan normalisation

- **Description:** Normalise the master `volume` and `pan` attributes on the `<defaultParams>` element of extracted instruments. Kit row volume and pan are preserved.
- **Inputs:** Assembled standalone XML element (from Task 2.1 or 2.2), instrument type (synth or kit)
- **Outputs:** The same element with normalised volume and pan on the top-level `<defaultParams>`
- **Acceptance Criteria:**
  - [ ] For synths: sets `volume` on `<defaultParams>` to `0x4CCCCCA8` (init synth value)
  - [ ] For kits: sets `volume` on kit-level `<defaultParams>` to `0x3504F334` (init kit value)
  - [ ] Sets `pan` on top-level `<defaultParams>` to `0x00000000` (centre) for both types
  - [ ] Does NOT modify `volume` or `pan` on kit row `<defaultParams>` (within `<soundSources>/<sound>`)
  - [ ] Does NOT modify patchCable entries with `destination="volume"`
  - [ ] Normalisation targets are defined as named constants or a data structure that can be extended with additional attributes in the future
- **Implementation Notes:**
  > {Space for the Implement agent to add notes during execution}

### Phase 3: Output and CLI

> **Goal:** Implement file output, naming, trash mechanism, manifest generation, and CLI integration
> **Prerequisites:** Phase 2 complete — transformation logic producing valid XML elements

#### Task 3.1: Filename generation and collision handling

- **Description:** Generate output filenames following the naming convention. Handle collisions between instruments with the same name in the same song.
- **Inputs:** Song name (stem of XML filename), preset name, instrument type, section ID (for extended mode), list of already-used filenames
- **Outputs:** Unique filename string
- **Acceptance Criteria:**
  - [ ] Default mode: `<SongName>-<PresetName>.XML`
  - [ ] Extended mode: `<SongName>-<PresetName>-<Abbr>.XML` where `<Abbr>` is the 3-letter colour abbreviation for the section ID
  - [ ] Colour abbreviation map: 0=Lbl, 1=Pnk, 2=Gld, 3=Cyn, 4=Red, 5=Ylw, 6=Dbl, 7=Orn, 8=Pur, 9=Lme, 10=Grn, 11=Mag
  - [ ] Collision resolution: if filename already used, append `-2`, `-3`, etc.
  - [ ] Spaces, hyphens, and digits in names preserved as-is
  - [ ] ~~FAT32 sanitisation removed — filenames originate from FAT32 SD card, so unsafe characters cannot appear~~
- **Implementation Notes:**
  > Function stub exists in `extraction.py` with full signature: `generate_filename(song_name, preset_name, instrument_type, section_id, extended, used_filenames) -> str`. Needs implementation.

#### Task 3.2: XML serialisation

- **Description:** Serialise assembled lxml elements to standalone XML files with the correct declaration and formatting.
- **Inputs:** Assembled lxml element, output file path
- **Outputs:** Written XML file
- **Acceptance Criteria:**
  - [ ] XML declaration: `<?xml version="1.0" encoding="UTF-8"?>`
  - [ ] Output matches the formatting style of existing standalone presets (use `lxml.etree.tostring` with `xml_declaration=True`, `encoding="UTF-8"`)
  - [ ] Investigate and match the whitespace/indentation style of Init-Synth.XML and Init-Kit.XML — the Deluge may be sensitive to formatting
- **Implementation Notes:**
  > Function stub exists in `extraction.py` with full signature: `serialise_xml(element, output_path) -> None`. Docstring references hardware-tested lxml `pretty_print=True` approach. Needs implementation.

#### Task 3.3: Trash mechanism and file writing ✅

- **Description:** Implement the trash-and-replace mechanism for output directories. Before writing new extractions, move existing `SONG-SYNTHS/` and `SONG-KITS/` directories to `.trash`.
- **Inputs:** Output directory paths
- **Outputs:** Previous contents trashed, new directories created, extraction files written
- **Acceptance Criteria:**
  - [x] If `SONG-SYNTHS/` exists, moves it to `DELUGE/.trash/extract-<timestamp>/SYNTHS/SONG-SYNTHS/` (mirroring relative paths)
  - [x] If `SONG-KITS/` exists, moves it to `DELUGE/.trash/extract-<timestamp>/KITS/SONG-KITS/` (mirroring relative paths)
  - [x] Creates fresh `SONG-SYNTHS/` and `SONG-KITS/` directories
  - [x] Writes all extraction files to the appropriate directory
  - [x] Only performs trash + write after user confirmation (or when not in dry-run mode)
- **Implementation Notes:**
  > Completed during scaffolding (15 Apr 2026). Trash logic was inlined in `extract_instruments.py` `main()` rather than a separate function. Uses a single timestamp for both directories: `DELUGE/.trash/extract-<YYYYMMDD_HHMMSS>/`. Each trashed directory preserves its relative path from `DELUGE/` (e.g. `SYNTHS/SONG-SYNTHS/` and `KITS/SONG-KITS/`). This corrects the original plan which had trash going to `SYNTHS/.trash/` and `KITS/.trash/` separately.

#### Task 3.4: Manifest generation (partially complete)

- **Description:** Generate a JSON manifest file in each output directory listing all extractions with metadata.
- **Inputs:** List of extraction results
- **Outputs:** `manifest.json` in each output directory
- **Acceptance Criteria:**
  - [ ] Each entry includes: output filename, source song, preset name, preset folder, instrument type, section ID, colour name, and timestamp
  - [x] Manifest is written as formatted JSON (indented for readability)
  - [x] Summary stats at the top level: total count, songs processed, date generated
- **Implementation Notes:**
  > `_write_manifest()` in `extract_instruments.py` is fully implemented — filters results by instrument type, constructs the manifest dict with `generated`, `songs_processed`, `total_count`, and `extractions` keys, writes JSON with `indent=2`. However, `build_manifest_entry()` in `extraction.py` is still a `NotImplementedError` stub — this function maps `ExtractionResult` → dict for each manifest entry. Manifest writing is wired up but will fail at runtime until `build_manifest_entry` is implemented.

#### Task 3.5: CLI integration and output formatting (substantially complete)

- **Description:** Wire everything together in the CLI script. Implement discovery → extraction → output pipeline with dry-run support, confirmation prompts, and formatted console output.
- **Inputs:** All previous tasks
- **Outputs:** Complete working CLI script
- **Acceptance Criteria:**
  - [x] `deluge-extract` with no flags performs a dry-run preview
  - [x] `deluge-extract --dry-run` performs dry-run only (no confirmation prompt)
  - [x] After dry-run preview, prompts for confirmation before writing
  - [x] `deluge-extract --extended` enables extended mode
  - [x] Console output lists each extraction per song, plus warnings, plus summary (see Interface Design section for format)
  - [ ] Exit code 0 on success, non-zero on failure
  - [ ] Missing init preset files produce a clear error and abort
- **Implementation Notes:**
  > Full CLI pipeline scaffolded in `extract_instruments.py` `main()` (15 Apr 2026). Wired together: argparse, `discover_songs()` → per-song loop → `discover_instruments()`/`discover_clips()`/`match_instruments_to_clips()` → `select_default_clip()`/`select_extended_clips()` → `extract_synth()`/`extract_kit()` → `normalise_params()` → `generate_filename()` → `ExtractionResult` construction → per-song console output → summary → dry-run/confirmation flow → trash → file writing → manifest writing. The pipeline structure is complete but calls stubbed functions — will work end-to-end once stubs are implemented. Exit code handling and init preset validation still need to be added.

### Phase 4: Extended Mode

> **Goal:** Implement multi-version extraction with parameter comparison
> **Prerequisites:** Phase 3 complete — default mode fully working end-to-end

#### Task 4.1: Parameter comparison engine

- **Description:** Implement the version comparison logic that determines whether two clips of the same instrument are sufficiently different to warrant separate extraction. This compares structural elements, non-numerical settings, and numerical parameter values.
- **Inputs:** Two clip elements for the same instrument, the instrument element
- **Outputs:** Boolean (distinct or not) and a list of differing parameters
- **Acceptance Criteria:**
  - [ ] Compares structural elements on the instrument `<sound>` definition (oscillator types, filter modes, polyphonic mode, etc.) — any structural/non-numerical change = distinct
  - [ ] Compares envelope, patchCable, and arpeggiator settings — any non-numerical setting change = distinct
  - [ ] Compares numerical `<soundParams>` attributes (excluding `volume` and `pan`) — if ≥ threshold count differ by > threshold percentage, versions are distinct
  - [ ] Count threshold and percentage threshold are module-level constants (default: 3 params, 10%)
  - [ ] Percentage calculation: absolute difference as proportion of the full parameter range. For hex values, parse as 32-bit signed integers. For extended hex strings (automation), treat as unchanged or use first value segment
  - [ ] Returns the list of parameters that differ (for logging/manifest)
  - [ ] Ignores automation data for comparison purposes per D15
- **Implementation Notes:**
  > {Space for the Implement agent to add notes during execution}

#### Task 4.2: Multi-version selection and extraction

- **Description:** When `--extended` is active, compare all section versions of each instrument and extract distinct versions with colour-abbreviated filenames.
- **Inputs:** Instrument-to-clips mapping (all sections), comparison engine from Task 4.1
- **Outputs:** List of extraction results — one or more per instrument
- **Acceptance Criteria:**
  - [ ] Uses lowest section ID as the baseline version (always extracted)
  - [ ] Compares each subsequent section version against the baseline
  - [ ] Extracts additional versions only if they are distinct from the baseline
  - [ ] Each extracted version uses the `<SongName>-<PresetName>-<Abbr>.XML` filename format
  - [ ] Manifest includes which parameters differ for each additional version
  - [ ] Console output indicates when multiple versions are extracted and why
- **Implementation Notes:**
  > {Space for the Implement agent to add notes during execution}

### Phase 5: Testing and Verification

> **Goal:** Create test fixtures and automated tests to verify extraction correctness
> **Prerequisites:** Phase 4 complete (or Phase 3 if testing default mode only first)

#### Task 5.1: Create test fixtures

- **Description:** Create minimal XML fixture files for testing. These should be small, hand-crafted XMLs that exercise the key extraction scenarios without being full-size song files.
- **Inputs:** Research document XML examples, Init-Synth.XML, Init-Kit.XML structure
- **Outputs:** Fixture files in `scripts/tests/fixtures/`
- **Acceptance Criteria:**
  - [ ] Fixture: minimal song with one synth instrument and one session clip
  - [ ] Fixture: minimal song with one kit instrument and one session clip with noteRows
  - [ ] Fixture: song with multiple sections of the same instrument (for version comparison testing)
  - [ ] Fixture: song with an orphaned instrument (no clips)
  - [ ] Fixture: song with clip arpeggiator having extra numeric attributes
  - [ ] Fixture: song with non-c1.2.1 firmware version
  - [ ] Fixture: init synth and init kit reference files (can use actual Init-Synth.XML and Init-Kit.XML)
- **Implementation Notes:**
  > {Space for the Implement agent to add notes during execution}

#### Task 5.2: Unit tests for extraction logic

- **Description:** Write pytest tests for the core extraction functions in `extraction.py`.
- **Inputs:** Test fixtures, extraction module
- **Outputs:** Test file `scripts/tests/test_extraction.py`
- **Acceptance Criteria:**
  - [ ] Tests instrument-clip discovery and matching
  - [ ] Tests synth transformation produces correct element ordering and attributes
  - [ ] Tests kit transformation produces correct element ordering with noteRow params merged
  - [ ] Tests volume/pan normalisation (correct values, row preservation)
  - [ ] Tests arpeggiator extraction and extra attribute stripping for synths
  - [ ] Tests orphaned instrument detection and skipping
  - [ ] Tests firmware version validation (skip non-c1.2.1)
  - [ ] Tests filename generation and collision handling
  - [ ] Tests version comparison logic (extended mode)
  - [ ] All tests pass with `pytest`
- **Implementation Notes:**
  > {Space for the Implement agent to add notes during execution}

#### Task 5.3: Integration test with real songs

- **Description:** Run the script against the actual song library in dry-run mode. Verify output count and spot-check a few extractions against their standalone counterparts.
- **Inputs:** Full song library in `DELUGE/SONGS/`
- **Outputs:** Dry-run output, spot-check results
- **Acceptance Criteria:**
  - [ ] Script runs to completion without errors on all 58 songs
  - [ ] All warnings are expected and understood
  - [ ] Extraction count is reasonable (each song should produce at least one instrument)
  - [ ] Spot-check: compare at least one extracted synth (e.g. from K01Sink) against its standalone counterpart to verify structural correctness
  - [ ] Spot-check: compare at least one extracted kit (e.g. Deeper from Ell.XML) against its standalone counterpart
- **Implementation Notes:**
  > {Space for the Implement agent to add notes during execution}

## Progress Tracker

| Phase | Status | Tasks Complete | Notes |
|-------|--------|---------------|-------|
| Phase 1: Foundation | In Progress | 1/4 | Task 1.1 complete (scaffolding) |
| Phase 2: Core Transformation | Not Started | 0/3 | |
| Phase 3: Output and CLI | In Progress | 3/5 | Tasks 3.3, 3.4, 3.5 substantially complete via scaffolding |
| Phase 4: Extended Mode | Not Started | 0/2 | |
| Phase 5: Testing and Verification | Not Started | 0/3 | |

## Open Questions

1. **What is the correct indentation/whitespace style for output XML?** ✅ Resolved
   - **Impact:** The Deluge firmware may be sensitive to XML formatting. If Init-Synth.XML uses tabs or specific indentation, the output should match.
   - **Recommendation:** Inspect Init-Synth.XML formatting during implementation and replicate it. lxml's `pretty_print` option with appropriate indentation should suffice.
   - **Blocking:** No — can be resolved during Task 3.2
   - **Resolution:** Hardware-tested. lxml's `pretty_print=True` with `encoding="UTF-8"` produces output that the Deluge firmware (c1.2.1) loads without issue. The Deluge re-normalises formatting to its preferred tab-indented style when the user saves the preset. No custom serialiser needed — use lxml's default pretty-print output.

2. **Should the manifest be one file per output directory or one combined file?**
   - **Impact:** Minor organisational choice. Two manifests (one per output dir) is slightly cleaner; one combined file is simpler to parse.
   - **Recommendation:** One per output directory (as specified in Task 3.4). Each manifest covers only its directory's contents.
   - **Blocking:** No
   - **Resolution:** _{To be filled during implementation}_

3. **How should extended mode handle automation data in parameter comparisons?**
   - **Impact:** Automation strings are variable-length hex (e.g. `0x7FFFFFFF7FFFFFFF000000607FFFFFFF00000120`). Comparing these verbatim would flag any automated parameter as "different" even if the base value hasn't changed.
   - **Recommendation:** For comparison purposes, extract the first 10 characters (one 32-bit hex value) from each attribute value as the "static" value. If the value is longer than 10 chars, it contains automation — use only the first value for comparison. Per D15, automation is ignored for comparison.
   - **Blocking:** No — only affects extended mode
   - **Resolution:** _{To be filled during implementation}_

## References

### Research Document
- [extract-instruments-research.md](../research/extract-instruments-research.md) — Primary input. Transformation recipes (Section 13.5), structural comparisons (Sections 13.2–13.3), and edge cases (Section 12).

### User Decisions
- [extraction-questions.md](../../temp/extraction-questions.md) — 40 questions with authoritative user answers. Takes precedence over research where conflicts exist.
- [extract-instruments.md](../../temp/extract-instruments.md) — Original feature notes. Superseded by Q&A on kit row pan (Q23: preserve, not normalise).

### Standards Applied
- [project.md](../../agent-system/standards/project.md) — SD card safety rules (DELUGE/ editable, SD card read-only) and cross-platform requirements (Python + pathlib)
- [standards/languages/python/](../../agent-system/standards/languages/python/) — Python coding standards (to be loaded by implementer)

### Project Files
- [Init-Synth.XML](../../DELUGE/SYNTHS/Init-Synth.XML) — Reference synth volume (`0x4CCCCCA8`) and pan (`0x00000000`)
- [Init-Kit.XML](../../DELUGE/KITS/Init-Kit.XML) — Reference kit volume (`0x3504F334`) and pan (`0x00000000`)
- [deluge_sdk.py](../../scripts/deluge_lib/deluge_sdk.py) — XML parsing (`parse_deluge_xml()`), file discovery
- [cli_utils.py](../../scripts/deluge_lib/cli_utils.py) — `get_deluge_root()`, `confirm_apply()`
- [scanning.py](../../scripts/deluge_lib/scanning.py) — `scan_tree()`, `.trash` skipping
- [pyproject.toml](../../scripts/pyproject.toml) — Dependencies, entry points, tool config

## Change Log

| Date | Change | Reason |
| 15 Apr 2026 | Updated plan to reflect scaffolding state | Task 1.1 complete, Tasks 3.3/3.4/3.5 substantially complete, trash path corrected, Task 1.4 API updated to use dataclasses |
|------|--------|--------|
| 14 Apr 2026 | Initial plan created | — |
