# Research: Extract Instruments from Songs

> **Document Type:** Research
> **Date:** 14 April 2026
> **Request:** Build a script that analyses all saved songs on the Deluge SD card backup and extracts embedded kit and synth instruments as standalone preset XMLs in `DELUGE/SYNTHS/SONG-SYNTHS/` and `DELUGE/KITS/SONG-KITS/`.
> **Pipeline:** Research → Plan → Implement

## Executive Summary

Song XMLs on the Deluge store complete copies of every instrument used, but the instrument parameters are split between two locations: the structural definition lives in the `<instruments>` section and the tuneable parameters live in clip-level `<soundParams>` or `<kitParams>` blocks. For synths, the `<arpeggiator>` element also lives at the clip level rather than the instrument level. Extracting a standalone preset requires merging these sources, renaming the clip params tag to `<defaultParams>`, and inserting the clip-level arpeggiator into the correct position. The existing codebase provides strong patterns for XML parsing, `.env` configuration, and cross-platform file handling via `lxml`, `pathlib`, and `python-dotenv`. All 58 songs use firmware `c1.2.1`, which simplifies extraction to a single format target.

**Update (April 2026):** The scope has been expanded to include a generalised comparison engine and cross-song deduplication. Analysis of the repository shows significant cross-song duplication — e.g., kit "000" (TR-808) appears in 10+ songs, "Deeper" kit in 5 songs, "K01Bass" synth in 4 songs. A three-tier comparison model (hard markers for structural identity, soft markers with configurable thresholds for numerical parameters, and an ignore list for normalised params) supports both intra-song extended mode and inter-song dedup through a single `compare_instruments()` engine. Cross-song dedup uses a baseline + incremental acceptance algorithm, grouping by preset name, with dedup enabled by default and a `--no-dedup` flag to disable.

## Objectives

- Understand how song XMLs represent instruments, clips, and the relationship between them
- Determine the exact XML structure of embedded synths and kits vs. standalone presets
- Identify how clip colours/versions are encoded and how to select representative versions
- Establish what parameters need normalisation (volume, pan) and what values to use
- Audit existing scripts and libraries for reusable code and patterns
- Determine the correct standalone preset XML format for `c1.2.1` firmware

## Feature Overview

### Purpose and Value

Users create and tweak instruments within songs on the Deluge hardware. These customised presets exist only within the song XML — they are not automatically saved as standalone presets. This script extracts those embedded instruments so the user can:

- Browse and reuse custom presets created during songwriting without having to manually save each one
- Load extracted presets into new songs without manually recreating customizations 
- Maintain a library of song-specific instrument variations

### Primary Use Case

The user runs the script periodically after syncing their SD card. The script scans all songs, extracts each unique instrument, and writes standalone preset files to dedicated output directories. The user can then copy these to the SD card and load them from the Deluge's preset browser.

### Inputs and Outputs

| Direction | Item |
|-----------|------|
| Input | All song XMLs in `DELUGE/SONGS/` |
| Input | Init presets (`Init-Synth.XML`, `Init-Kit.XML`) for reference volume/pan values and minimum / default XML structure |
| Output | Standalone synth XMLs in `DELUGE/SYNTHS/SONG-SYNTHS/` |
| Output | Standalone kit XMLs in `DELUGE/KITS/SONG-KITS/` |

### Scope

| In Scope | Out of Scope |
|----------|-------------|
| Synth extraction from song clips | MIDI instrument extraction |
| Kit extraction (including row-level params) | Audio clip extraction |
| Volume/pan normalisation | Arrangement-only clip handling (deferred) |
| Multi-version selection by colour | Support for firmware versions other than `c1.2.1` |
| Firmware version safety check (`c1.2.1`) | Song XML modification |
| Trash-and-replace existing extractions | |
| Generalised comparison engine (hard/soft/ignore markers) | |
| Cross-song deduplication (post-extraction filter) | |

## Existing Assets Analysis

| Capability | Status | Location | Notes |
|------------|--------|----------|-------|
| XML parsing with lxml | ✅ Ready | [deluge_sdk.py](scripts/deluge_lib/deluge_sdk.py) | Three-stage fallback parser (`parse_deluge_xml`), handles multi-root and malformed XML |
| XML file discovery | ✅ Ready | [deluge_sdk.py](scripts/deluge_lib/deluge_sdk.py) | `find_all_xml_files()` scans KITS/, SYNTHS/, SONGS/ |
| Sample reference extraction | ✅ Ready | [deluge_sdk.py](scripts/deluge_lib/deluge_sdk.py) | `extract_sample_refs()` with preset name lookup logic |
| .env configuration | ✅ Ready | [cli_utils.py](scripts/deluge_lib/cli_utils.py) | `get_deluge_root()` loads DELUGE_ROOT from `scripts/.env` |
| File scanning/filtering | ✅ Ready | [scanning.py](scripts/deluge_lib/scanning.py) | `scan_tree()` with `.trash` skipping, case normalisation |
| Interactive confirmation | ✅ Ready | [cli_utils.py](scripts/deluge_lib/cli_utils.py) | `confirm_apply()` for destructive operations |
| Instrument structure extraction | ❌ Missing | — | No existing code to extract instrument definitions from songs |
| Clip → instrument matching | ❌ Missing | — | No existing code linking clips to their instrument entries |
| Standalone XML generation | ❌ Missing | — | No existing code to produce standalone synth/kit XMLs |
| Parameter comparison/diffing | ⚠️ Partial | [extraction.py](scripts/deluge_lib/extraction.py) | `compare_versions()` stub exists with detailed docstring (3-tier comparison described); `DIFF_PARAM_COUNT_THRESHOLD`, `DIFF_PARAM_PERCENT_THRESHOLD`, and `COMPARISON_EXCLUDED_ATTRS` constants defined |
| Cross-song deduplication | ❌ Missing | — | No existing code for inter-song redundancy filtering |
| Test fixtures for songs | ⚠️ Partial | [scripts/tests/fixtures/](scripts/tests/fixtures/) | Fixtures exist for other tests; song-specific fixtures would be needed |

## Findings

### 1. Song XML Top-Level Structure

**Source:** Analysis of [Bloop.XML](DELUGE/SONGS/Bloop.XML), [K01Sink.XML](DELUGE/SONGS/K01Sink.XML), [Ell.XML](DELUGE/SONGS/Ell.XML), [Arpo.XML](DELUGE/SONGS/Arpo.XML)

The `<song>` root element (firmware `c1.2.1`) contains these top-level children in order:

| Element | Purpose |
|---------|---------|
| `<modeNotes>` | Scale/mode configuration |
| `<reverb>` | Global reverb settings |
| `<delay>` | Global delay settings |
| `<sidechain>` | Global sidechain settings |
| `<audioCompressor>` | Global compressor settings |
| `<songParams>` | Song-level parameter values |
| `<instruments>` | **All instrument definitions (synths, kits, MIDI, audio tracks)** |
| `<sections>` | Section definitions (12 sections, ids 0–11) |
| `<sessionClips>` | **All session clips referencing instruments** |

Songs may also contain `<arrangementOnlyClips>` for clips exclusive to the arrangement view.

The `<song>` element carries attributes including:

```xml
<song
    firmwareVersion="c1.2.1"
    earliestCompatibleFirmware="4.1.0-alpha"
    inArrangementView="0|1"
    ...>
```

### 2. Instrument Types in `<instruments>`

**Source:** Multiple song XMLs

The `<instruments>` element may contain four types of children:

| Tag | Type | Relevant? | Key Attributes |
|-----|------|-----------|----------------|
| `<sound>` | Synth | ✅ Yes | `presetName`, `presetFolder`, `colour`, `polyphonic`, `mode`, etc. |
| `<kit>` | Kit | ✅ Yes | `presetName`, `presetFolder`, `colour`, `modFXType`, etc. |
| `<midi>` | MIDI instrument | ❌ No | `channel`, `suffix` |
| `<audioTrack>` | Audio track | ❌ No | `name`, `inputChannel` |

Song-specific attributes exist only on embedded instruments (not standalone presets):

```
presetName, presetFolder, defaultVelocity, isArmedForRecording,
activeModFunction, colour, clipInstances
```

These must be **stripped** when producing standalone presets.

### 3. The Instrument-Clip Relationship (Critical Architecture)

**Source:** Structural analysis of all examined song XMLs

This is the most important finding for the extraction logic. Instruments and their parameters are **split across two locations**:

#### For synths (`<sound>` instruments):

**In `<instruments>`** — the instrument _structure_:
- Oscillator settings (`<osc1>`, `<osc2>`)
- LFO settings (`<lfo1>`, `<lfo2>`)
- Modulator settings (`<modulator1>`, `<modulator2>`) — present only in FM mode instruments
- Unison settings (`<unison>`)
- Mod knob assignments (`<modKnobs>`)
- Delay, sidechain, audio compressor settings
- Synth-level attributes (`polyphonic`, `mode`, `modFXType`, `lpfMode`, etc.)
- **Does NOT contain `<defaultParams>`** (when the instrument has active clips)
- **Does NOT contain `<arpeggiator>`** — arpeggiator settings are stored at the clip level

**In `<sessionClips>/<instrumentClip>`** — the per-clip _parameter values_:
- `<arpeggiator>` element — arpeggiator configuration (mode, numOctaves, syncLevel, etc.). This is a direct child of `<instrumentClip>`, appearing before `<soundParams>`.
- `<soundParams>` block containing all tuneable parameter values
- This block is structurally identical to `<defaultParams>` in standalone presets
- Contains: volume, pan, filter settings, envelope settings, patch cables, equaliser, etc.

**Extraction formula for synths:**
```
Standalone <sound> = 
    instrument structure from <instruments>/<sound>
    + clip params from <instrumentClip>/<soundParams> → renamed to <defaultParams>
    + arpeggiator from <instrumentClip>/<arpeggiator> → inserted into <sound>
      (placed between <defaultParams> and <modKnobs> per standalone ordering)
    + <modKnobs> repositioned from after <unison> to after <arpeggiator>
    - song-specific attributes stripped (presetName, presetFolder, defaultVelocity,
      isArmedForRecording, activeModFunction, clipInstances, colour)
    - clip arpeggiator extra attrs stripped (gate, rate, ratchetProbability,
      ratchetAmount, sequenceLength, rhythm) if present
    + firmwareVersion/earliestCompatibleFirmware added
```

#### For kits (`<kit>` instruments):

**In `<instruments>`** — the kit _structure_:
- Kit-level settings (`modFXType`, `lpfMode`, `hpfMode`, etc.)
- Delay, sidechain, audio compressor
- `<soundSources>` containing `<sound>` elements (one per drum/row)
  - Each sound has oscillator, LFO, unison, **arpeggiator** (stays in place), mod knobs, delay, sidechain, compressor
  - Each sound has **no `<defaultParams>`** (those are in the clip's noteRows)
- `<selectedDrumIndex>` — present in both song-embedded and standalone kits

**In `<sessionClips>/<instrumentClip>`** — per-clip parameter values:
- `<kitParams>` block — kit-level ("affect entire") parameters → becomes kit's `<defaultParams>`
- Within `<noteRows>`, each `<noteRow>` has:
  - `drumIndex` — index into the kit's `<soundSources>` list
  - `<soundParams>` — per-row parameter values → becomes that sound's `<defaultParams>`

**Extraction formula for kits:**
```
Standalone <kit> =
    kit structure from <instruments>/<kit>
    + kit-level params from <instrumentClip>/<kitParams> → renamed to <defaultParams>
      and inserted as first child of <kit> (before <delay>)
    + per-row params from <noteRow>/<soundParams> → each renamed to <defaultParams>
      and inserted into the corresponding <sound> in <soundSources> (matched by drumIndex)
      placed between <unison> and <arpeggiator> within each sound
    - song-specific attributes stripped (presetName, presetFolder, defaultVelocity,
      isArmedForRecording, activeModFunction, colour)
    + firmwareVersion/earliestCompatibleFirmware added
    NOTE: Kit sounds already have <arpeggiator> in the instrument — no clip-level
    arpeggiator extraction needed (kit clips don't have one)
```

#### Orphaned instruments (no clips):

**Source:** [Arpo.XML](DELUGE/SONGS/Arpo.XML) — synth `presetName="000"` has `<defaultParams>` but no clip in `<sessionClips>`

Some instruments in `<instruments>` have no corresponding clips (deleted clips, arrangement-only remnants). These instruments **do** have `<defaultParams>` directly on the instrument definition. They can be extracted directly but may represent stale/unused instruments.

Note: Orphaned synths also lack an `<arpeggiator>` element (same as non-orphaned synths in songs — arpeggiator is normally stored at the clip level). Extraction must synthesize a default `<arpeggiator>` (e.g. `mode="off"`) for orphaned instrument presets.

### 4. Clip-to-Instrument Matching

**Source:** All examined song XMLs

Clips link to instruments via two attributes:

```xml
<instrumentClip
    instrumentPresetName="K01Bass"
    instrumentPresetFolder="SYNTHS/KERERU"
    ...>
```

These match the instrument's `presetName` and `presetFolder` attributes in `<instruments>`.

Multiple clips can reference the same instrument with different `section` values, each with their own independent `<soundParams>` or `<kitParams>` — these are the "colour versions" (section variants) of that instrument. The `section` attribute (0–11) corresponds to the 12 colour-coded launch rows on the Deluge, and is the true version discriminator.

**Example from K01Sink.XML:**
- "K01Bass" with `section="6"` (line 2803) — one version
- "K01Bass" with `section="3"` (line 4608) — another version, potentially different params

Note: `colourOffset` also appears on clips but is a cosmetic hue offset for pad grid display — it does not determine clip versioning. In K01Sink.XML, the instrument "K01Drone" has 10 clips ALL with `colourOffset="7"` but with different `section` values (2, 3, 4, etc.), confirming that `colourOffset` is unrelated to versioning.

### 5. The Colour System

**Source:** All examined song XMLs; user's feature notes; verified via K01Sink.XML analysis

#### `section` attribute — the clip version system

The `section` attribute on `<instrumentClip>` (values 0–11) is the true version discriminator for clip variants. The `<sections>` element at the song level defines 12 sections (ids 0–11), which correspond to the 12 colour-coded launch rows on the Deluge:

| Section ID | Colour |
|---|---|
| 0 | LightBlue |
| 1 | Pink |
| 2 | Gold |
| 3 | Cyan |
| 4 | Red |
| 5 | Yellow |
| 6 | DarkBlue |
| 7 | Orange |
| 8 | Purple |
| 9 | Lime |
| 10 | Green |
| 11 | Magenta |

Multiple clips of the same instrument in different sections represent the different colour versions described in the feature notes, each with potentially different parameter tweaks.

#### `colourOffset` attribute — cosmetic pad hue

The `colourOffset` attribute on `<instrumentClip>` and `<noteRow>` elements is purely cosmetic — it controls the display hue of pad buttons and note rows, not clip versioning. Evidence: in K01Sink.XML, "K01Drone" has 10 clips ALL with `colourOffset="7"` but with different `section` values.

#### `colour` attribute on instruments

The `colour` attribute on instruments in `<instruments>` was observed to be `"0"` across all examined songs. This is a cosmetic display property — it does not determine clip colours or versioning.

#### Key insight for version detection

Clips of the same instrument are identified by matching `instrumentPresetName` + `instrumentPresetFolder`. Different `section` values on those clips represent different colour versions (section variants) of the same instrument, each with potentially different parameter tweaks.

**Version grouping strategy:**
1. Group clips by `(instrumentPresetName, instrumentPresetFolder)`
2. Within each group, sub-group by `section`
3. Each unique `section` value represents one version candidate

### 6. Standalone Synth Preset Format

**Source:** [Init-Synth.XML](DELUGE/SYNTHS/Init-Synth.XML), [K01Bass.XML](DELUGE/SYNTHS/KERERU/K01Bass.XML)

Root element: `<sound>` (not `<song>`, not wrapped in `<instruments>`)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<sound
    firmwareVersion="c1.2.1"
    earliestCompatibleFirmware="4.1.0-alpha"
    polyphonic="poly"
    voicePriority="1"
    mode="subtractive"
    modFXType="none"
    lpfMode="24dB"
    hpfMode="HPLadder"
    filterRoute="H2L"
    maxVoices="8">
    <osc1 ... />
    <osc2 ... />
    <lfo1 ... />
    <lfo2 ... />
    <modulator1 ... />            ← FM mode only
    <modulator2 ... />            ← FM mode only
    <unison ... />
    <defaultParams ...>           ← params live here (renamed from soundParams)
        <envelope1 ... />
        <envelope2 ... />
        <patchCables>
            <patchCable ... />
        </patchCables>
        <equalizer ... />
    </defaultParams>
    <arpeggiator ... />           ← from clip level, not instrument
    <modKnobs>
        <modKnob ... />
    </modKnobs>
    <delay ... />
    <sidechain ... />
    <audioCompressor ... />
</sound>
```

**Attributes on `<sound>` in standalone vs song-embedded:**

| Attribute | Standalone | Song-embedded | Action |
|-----------|-----------|---------------|--------|
| `firmwareVersion` | ✅ Required | ❌ Absent | Add `"c1.2.1"` |
| `earliestCompatibleFirmware` | ✅ Required | ❌ Absent | Add `"4.1.0-alpha"` |
| `presetName` | ❌ Absent | ✅ Present | Strip |
| `presetFolder` | ❌ Absent | ✅ Present | Strip |
| `defaultVelocity` | ❌ Absent | ✅ Present | Strip |
| `isArmedForRecording` | ❌ Absent | ✅ Present | Strip |
| `activeModFunction` | ❌ Absent | ✅ Present | Strip |
| `colour` | ❌ Absent | ✅ Present | Strip |
| `clipInstances` | ❌ Absent | Sometimes present | Strip |
| `polyphonic`, `mode`, etc. | ✅ Present | ✅ Present | Keep |

### 7. Standalone Kit Preset Format

**Source:** [Init-Kit.XML](DELUGE/KITS/Init-Kit.XML), [Deeper.XML](DELUGE/KITS/KERERU/Deeper.XML)

Root element: `<kit>`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<kit
    firmwareVersion="c1.2.1"
    earliestCompatibleFirmware="4.1.0-alpha"
    modFXCurrentParam="feedback"
    currentFilterType="lpf"
    modFXType="flanger"
    lpfMode="24dB"
    hpfMode="HPLadder"
    filterRoute="H2L">
    <defaultParams ...>           ← kit-level params (from kitParams in clip)
        <delay ... />
        <lpf ... />
        <hpf ... />
        <equalizer ... />
    </defaultParams>
    <delay ... />
    <sidechain ... />
    <audioCompressor ... />
    <soundSources>
        <sound name="KICK" ...>
            <osc1 ... />
            <osc2 ... />
            <lfo1 ... />
            <lfo2 ... />
            <unison ... />
            <defaultParams ...>   ← per-row params (from noteRow/soundParams)
                <envelope1 ... />
                <envelope2 ... />
                <patchCables> ... </patchCables>
                <equalizer ... />
            </defaultParams>
            <arpeggiator ... />
            <modKnobs> ... </modKnobs>
            <delay ... />
            <sidechain ... />
            <audioCompressor ... />
        </sound>
    </soundSources>
    <selectedDrumIndex>0</selectedDrumIndex>
</kit>
```

The same attribute stripping rules apply as for synths.

### 8. Volume and Pan Normalisation

**Source:** [Init-Synth.XML](DELUGE/SYNTHS/Init-Synth.XML), [Init-Kit.XML](DELUGE/KITS/Init-Kit.XML)

The Deluge stores parameter values as 32-bit signed integers in hex format (e.g. `0x4CCCCCA8`). The value `0x80000000` typically represents the minimum or zero position, while `0x7FFFFFFF` represents maximum.

#### Reference values from init presets:

| Context | Parameter | Init Synth Value | Init Kit Value |
|---------|-----------|-----------------|----------------|
| Master | `volume` | `0x4CCCCCA8` | `0x3504F334` |
| Master | `pan` | `0x00000000` | `0x00000000` |
| Kit row | `volume` | — | `0x4CCCCCA8` |
| Kit row | `pan` | — | `0x00000000` |

Per the feature notes:
- **Master volume** should be normalised to the init preset value for the respective type (synth or kit)
- **Master pan** should be normalised to `0x00000000` (centre)
- **Kit row volume** should be **preserved** (user intentionally balanced row levels)
- **Kit row pan** should be normalised to `0x00000000` (centre)

Note: The `volume` in `<defaultParams>` / `<soundParams>` is distinct from `<songParams volume="...">` which is the song master volume. Only the instrument/clip volume needs normalisation; song-level volume is irrelevant.

### 9. Preset Naming

**Source:** All examined song XMLs

Instruments in `<instruments>` have a `presetName` attribute which is the name the Deluge gave (or the user assigned) to the preset. Examples:

| Song | presetName | presetFolder |
|------|------------|-------------|
| Bloop | `"133"` | `"SYNTHS"` |
| Bloop | `"166"` | `"SYNTHS"` |
| Bloop | `"000"` | `"KITS"` |
| K01Sink | `"41-VIOLINE 3"` | `"SYNTHS"` |
| K01Sink | `"K01Bass"` | `"SYNTHS/KERERU"` |
| Ell | `"Deeper"` | `"KITS"` |

These names are a mix of:
- Numeric factory preset identifiers (`"133"`, `"000"`, `"005"`)
- Custom user-given names (`"K01Bass"`, `"Deeper"`)
- Names with special characters and spaces (`"41-VIOLINE 3"`)

The user's proposed filename format is: `<SongName>-<PresetName>-<ClipIdentifier>.XML`

### 10. Existing Codebase Patterns

**Source:** All files in [scripts/](scripts/) and [scripts/deluge_lib/](scripts/deluge_lib/)

#### Architecture patterns:

| Pattern | Example | Description |
|---------|---------|-------------|
| `.env` configuration | `get_deluge_root()` in [cli_utils.py](scripts/deluge_lib/cli_utils.py) | All paths loaded from `scripts/.env` via `python-dotenv` |
| lxml for XML parsing | `parse_deluge_xml()` in [deluge_sdk.py](scripts/deluge_lib/deluge_sdk.py) | Three-stage fallback (strict → synthetic root → recover) |
| `pathlib.Path` everywhere | All scripts | Cross-platform path handling |
| Dry-run as default | [sync_from_sd.py](scripts/sync_from_sd.py) | Preview changes, prompt before applying |
| Dataclass result types | `SyncPlan`, `MigrationResult`, `SampleRef` | Typed, structured return values |
| Test fixtures | [scripts/tests/fixtures/](scripts/tests/fixtures/) | XML fixtures for unit tests |

#### Dependencies (from [pyproject.toml](scripts/pyproject.toml)):

```
lxml>=5.0.0
python-dotenv>=1.0.0
```

Dev: `ruff`, `mypy`, `pytest`, `lxml-stubs`

Python target: 3.12+

#### CLI entry points (from `[project.scripts]`):

Scripts are registered as console entry points via `pyproject.toml`. A new script would follow this pattern and add its own entry point.

### 11. Firmware Compatibility

**Source:** `grep` across all 58 songs

All 58 song XMLs in `DELUGE/SONGS/` use `firmwareVersion="c1.2.1"`. No other firmware versions are present. The associated `earliestCompatibleFirmware` is `"4.1.0-alpha"`.

Some standalone presets in `DELUGE/SYNTHS/KERERU/` and `DELUGE/KITS/KERERU/` use older firmware versions (e.g. `firmwareVersion="4.0.1"`), but these are existing presets and not the extraction target.

Extracted presets should be tagged with `firmwareVersion="c1.2.1"` and `earliestCompatibleFirmware="4.1.0-alpha"` to match the source songs.

### 12. Edge Cases Discovered

| Edge Case | Example | Impact |
|-----------|---------|--------|
| Orphaned instruments | Arpo.XML synth "000" — in `<instruments>` with `<defaultParams>` but no clips | Can extract directly; decide whether to include |
| Same presetName different songs | "Deeper" kit appears in Ell.XML | Output filenames must include song name to prevent collisions |
| Special chars in presetName | "41-VIOLINE 3" contains spaces and hyphens | Filename sanitisation needed |
| Numeric presetName | "133", "000", "005" | Still valid for filenames |
| Multiple clips, same section | Could have two clips with identical instrument + section | Need deduplication within a song |
| Arrangement-only clips | Clips in `<arrangementOnlyClips>` have no `section` attribute | Need alternative version identification for arrangement-only extraction |
| Kit noteRow drumIndex | drumIndex links noteRow params to soundSources order | Must match correctly, handle sparse indices |
| `.trash` directories | Existing codebase pattern for "soft delete" | Output directories should use `.trash` pattern for replacing existing extractions |
| Session clips without `section` | K01Sink.XML has K01Drone clips under `<sessionClips>` with no `section` attribute | Likely defaults to section 0 or represents arrangement-associated clips; need fallback handling |
| Clip-level arpeggiator for synths | `<arpeggiator>` is a child of `<instrumentClip>`, not `<sound>` in `<instruments>` | Must extract arpeggiator from clip and insert into standalone preset between `<defaultParams>` and `<modKnobs>` |
| Clip-level arpeggiator extra attributes | Some clips have `gate`, `rate`, `ratchetProbability`, `ratchetAmount`, `sequenceLength`, `rhythm` on `<arpeggiator>` (e.g. One Eye Tea.XML YAZO-LEAD2) | These duplicate values in `<soundParams>` and do not appear in standalone presets — must be stripped |
| Parameter automation in clip values | K01Sink.XML K01Perc2 noteRow drumIndex=1 has `lpfFrequency="0x7FFFFFFF7FFFFFFF000000607FFFFFFF00000120"` | Some `<soundParams>` attribute values encode automation curves as extended hex strings, not single values. Extraction must preserve these verbatim. |
| `presetFolder` mismatch | K09Arparty has `presetName="KRumchybass"` with `presetFolder="SYNTHS"` but the standalone file is `SYNTHS/KERERU/KRumchybass.XML` | Instruments may have been moved between folders after being loaded into a song — presetFolder in the song may not match the current standalone location |

### 13. Standalone vs Embedded Instrument Comparison

**Source:** Systematic comparison of instruments that exist both as standalone preset files and embedded in song XMLs. All songs are firmware `c1.2.1`. Standalone presets are a mix of `c1.2.1`, `c1.2.0`, and `4.0.1` firmware versions.

#### 13.1 Instrument Pairs Compared

| Song | Instrument | Type | Standalone File | Standalone FW |
|------|-----------|------|----------------|---------------|
| K01Sink.XML | K01Bass | Synth | SYNTHS/KERERU/K01Bass.XML | 4.0.1 |
| K01Sink.XML | K01Perc2 | Kit | KITS/KERERU/K01Perc2.XML | 4.0.1 |
| K09Arparty.XML | Padfoot | Synth | SYNTHS/KERERU/Padfoot.XML | **c1.2.1** |
| K09Arparty.XML | K01Fuzzbass | Synth | SYNTHS/KERERU/K01Fuzzbass.XML | 4.0.1 |
| K09Arparty.XML | Fuzzogatto | Kit | KITS/KERERU/Fuzzogatto.XML | 4.0.1 |
| Wf 7.XML | Fuzz | Synth | SYNTHS/KERERU/Fuzz.XML | 4.0.1 |
| Wf 7.XML | Arp1, Arp2, K01Arp, K01Drone, K01Bass, K01Violin | Synths | SYNTHS/KERERU/*.XML | 4.0.1 |
| Oddish 3.XML | Vibes WT | Synth | SYNTHS/COMMUNITY/1.2 Presets/Vibes WT.XML | c1.2.0 |
| Oddish 3.XML | Wall Of Static | Synth | SYNTHS/COMMUNITY/1.2 Presets/Wall Of Static.XML | c1.2.0 |
| No-More-Colour.XML | Apex Stab | Synth | SYNTHS/COMMUNITY/1.2 Presets/Apex Stab.XML | c1.2.0 |
| No-More-Colour.XML | Dystopia Keys | Synth | SYNTHS/COMMUNITY/1.2 Presets/Dystopia Keys.XML | c1.2.0 |
| One Eye Tea.XML | Deeper | Kit | KITS/KERERU/Deeper.XML | **c1.2.1** |
| K05BeautifulStranger.XML | Deeper | Kit | KITS/KERERU/Deeper.XML | **c1.2.1** |

The most authoritative comparisons are **Padfoot** (synth, both c1.2.1) and **Deeper** (kit, both c1.2.1) because both standalone and embedded are the same firmware version, eliminating firmware-upgrade noise.

#### 13.2 Synth: Structural Comparison

##### Root `<sound>` Attributes

**Compared:** Standalone Padfoot.XML (c1.2.1) vs embedded Padfoot in K09Arparty.XML (c1.2.1 song)

| Attribute | Standalone | Embedded | Action |
|-----------|-----------|----------|--------|
| `firmwareVersion` | `"c1.2.1"` | ❌ Absent | Add |
| `earliestCompatibleFirmware` | `"4.1.0-alpha"` | ❌ Absent | Add |
| `presetName` | ❌ Absent | `"Padfoot"` | Strip |
| `presetFolder` | ❌ Absent | `"SYNTHS/KERERU"` | Strip |
| `defaultVelocity` | ❌ Absent | `"64"` | Strip |
| `isArmedForRecording` | ❌ Absent | `"0"` | Strip |
| `activeModFunction` | ❌ Absent | `"0"` | Strip |
| `clipInstances` | ❌ Absent | binary hex string | Strip |
| `colour` | ❌ Absent | `"0"` | Strip |
| `polyphonic` | `"poly"` | `"poly"` | Keep (may differ — Vibes WT changed to `"legato"` in its song) |
| `voicePriority` | `"1"` | `"1"` | Keep |
| `mode` | `"subtractive"` | `"subtractive"` | Keep |
| `modFXType` | `"none"` | `"none"` | Keep |
| `lpfMode` | `"12dB"` | `"12dB"` | Keep |
| `hpfMode` | `"HPLadder"` | `"HPLadder"` | Keep |
| `filterRoute` | `"H2L"` | `"H2L"` | Keep |
| `maxVoices` | `"8"` | `"8"` | Keep |
| `transpose` | (not on Padfoot) | (not on Padfoot) | Keep if present (Fuzz has `transpose="-12"` on both) |
| `clippingAmount` | (not on Padfoot) | (not on Padfoot) | Keep if present (Fuzz has `clippingAmount="2"` on both) |

**Song-specific attributes to strip:** `presetName`, `presetFolder`, `defaultVelocity`, `isArmedForRecording`, `activeModFunction`, `clipInstances`, `colour`

##### Child Element Ordering

**Standalone synth (c1.2.1)** — verified from Init-Synth.XML, Padfoot.XML, Vibes WT.XML:

```
<sound ...>
    <osc1 />
    <osc2 />
    <lfo1 />
    <lfo2 />
    (<modulator1 /> <modulator2 />)     ← FM mode only
    <unison />
    <defaultParams>                      ← tuneable params
        <envelope1 /><envelope2 />
        <patchCables>...</patchCables>
        <equalizer />
    </defaultParams>
    <arpeggiator />                      ← synth arpeggiator
    <modKnobs>...</modKnobs>
    <delay />
    <sidechain />
    <audioCompressor />
</sound>
```

**Embedded synth in song `<instruments>` (c1.2.1)** — verified from K01Sink, K09Arparty, Wf 7, Oddish 3:

```
<sound ...>
    <osc1 />
    <osc2 />
    <lfo1 />
    <lfo2 />
    (<modulator1 /> <modulator2 />)     ← FM mode only
    <unison />
    <modKnobs>...</modKnobs>             ← MOVED UP from after arpeggiator
    <delay />
    <sidechain />
    <audioCompressor />
                                         ← NO <defaultParams>
                                         ← NO <arpeggiator>
</sound>
```

**Key difference:** In the embedded instrument, `<modKnobs>` moves to directly after `<unison>`, and `<defaultParams>` + `<arpeggiator>` are absent (they live at the clip level).

##### `<soundParams>` vs `<defaultParams>` — Structural Equivalence

**Verified by comparing** Padfoot standalone `<defaultParams>` with K09Arparty clip `<soundParams>`:

- **Tag name:** `<soundParams>` in clip → rename to `<defaultParams>` for standalone
- **Attributes:** Identical set. Both have the full c1.2.1 param set including `compressorThreshold`, `lpfMorph`, `hpfMorph`, `waveFold`, `ratchetProbability`, `ratchetAmount`, `sequenceLength`, `rhythm`
- **Child elements:** Same structure: `<envelope1>`, `<envelope2>`, `<patchCables>` (with arbitrarily nested `<depthControlledBy>` children), `<equalizer>`
- **Values:** May differ — the user adjusts params per-clip (e.g. Padfoot standalone `volume="0x74000000"` vs clip `volume="0x5A000000"`)

XML snippet — standalone `<defaultParams>` (partial):
```xml
<defaultParams
    arpeggiatorGate="0x00000000"
    portamento="0x80000000"
    ...
    volume="0x74000000"
    pan="0x10000000"
    ...>
    <envelope1 attack="0x4CCCCCA8" decay="0x1999997E" sustain="0x2E147AC2" release="0x1999997E" />
    <envelope2 ... />
    <patchCables>
        <patchCable source="velocity" destination="volume" amount="0x3FFFFFE8" />
        ...
    </patchCables>
    <equalizer bass="0x00000000" treble="0x00000000" ... />
</defaultParams>
```

Clip `<soundParams>` (same structure, different tag name, potentially different values):
```xml
<soundParams
    arpeggiatorGate="0x00000000"
    portamento="0x80000000"
    ...
    volume="0x5A000000"
    pan="0x36000000"
    ...>
    <envelope1 attack="0x4CCCCCA8" decay="0x1999997E" sustain="0x2E147AC2" release="0x1999997E" />
    <envelope2 ... />
    <patchCables>
        <patchCable source="velocity" destination="volume" amount="0x3FFFFFE8" />
        ...
    </patchCables>
    <equalizer bass="0x00000000" treble="0x00000000" ... />
</soundParams>
```

##### Clip-Level `<arpeggiator>` vs Standalone `<arpeggiator>`

**Standard form** (present on ALL examined clips and standalones):
```xml
<arpeggiator mode="off" numOctaves="2" syncLevel="7" syncType="0"
    arpMode="off" noteMode="up" octaveMode="up" mpeVelocity="off" />
```

Attributes: `mode`, `numOctaves`, `syncLevel`, `syncType`, `arpMode`, `noteMode`, `octaveMode`, `mpeVelocity` — present on both standalone and clip variants. Values may differ per-clip (e.g. Padfoot standalone `syncLevel="7"` vs clip `syncLevel="6"`).

**Extra attributes found on SOME clips only** (e.g. One Eye Tea.XML YAZO-LEAD2):
```xml
<arpeggiator mode="off" syncLevel="6" numOctaves="2"
    gate="0" rate="0" ratchetProbability="0" ratchetAmount="0"
    sequenceLength="0" rhythm="0"
    syncType="0" arpMode="off" noteMode="up" octaveMode="up" mpeVelocity="off" />
```

Extra attributes: `gate`, `rate`, `ratchetProbability`, `ratchetAmount`, `sequenceLength`, `rhythm`. These are integer representations of values already stored as hex in `<soundParams>` (`arpeggiatorGate`, `arpeggiatorRate`, etc.). Standalone presets (Init-Synth, Padfoot, Vibes WT) do NOT have these. **The extraction script must strip these extra attributes** when copying the clip arpeggiator to the standalone preset.

**Attribute ordering:** Standalone uses `mode, numOctaves, syncLevel` while clips use `mode, syncLevel, numOctaves`. This is semantically irrelevant but worth noting if byte-exact reproduction is desired.

##### Instrument-Level Elements Shared Between Standalone and Embedded

All non-params, non-arpeggiator elements on the embedded instrument match the standalone version exactly:

| Element | Standalone | Embedded | Notes |
|---------|-----------|----------|-------|
| `<osc1>`, `<osc2>` | ✅ | ✅ | Identical attributes and children. Includes `fileName` for sample-based oscillators, `<zone>` children. |
| `<lfo1>`, `<lfo2>` | ✅ | ✅ | Identical (c1.2.1 includes `syncType`; may differ from older standalone) |
| `<unison>` | ✅ | ✅ | Identical (c1.2.1 includes `spread`) |
| `<modKnobs>` | ✅ | ✅ | Identical content — same 16 `<modKnob>` entries with same `controlsParam` values |
| `<delay>` | ✅ | ✅ | Identical for Padfoot; Vibes WT/Fuzz had different values (user tweaked in song) |
| `<sidechain>` | ✅ | ✅ | Identical across all examined pairs |
| `<audioCompressor>` | ✅ | ✅ | Identical across all examined pairs |

**Critical finding:** The `<delay>`, `<sidechain>`, and `<audioCompressor>` on the instrument definition can differ from the standalone preset. In the Vibes WT comparison, the standalone has `<delay analog="0" syncLevel="7">` but the song-embedded instrument has `<delay analog="1" syncLevel="6" syncType="19">`. This means the user edited these instrument-level settings within the song. The extraction script should use the embedded instrument's values, not the standalone's.

#### 13.3 Kit: Structural Comparison

##### Root `<kit>` Attributes

**Compared:** Standalone Deeper.XML (c1.2.1) vs embedded Deeper in One Eye Tea.XML (c1.2.1 song)

| Attribute | Standalone | Embedded | Action |
|-----------|-----------|----------|--------|
| `firmwareVersion` | `"c1.2.1"` | ❌ Absent | Add |
| `earliestCompatibleFirmware` | `"4.1.0-alpha"` | ❌ Absent | Add |
| `presetName` | ❌ Absent | `"Deeper"` | Strip |
| `presetFolder` | ❌ Absent | `"KITS"` | Strip |
| `defaultVelocity` | ❌ Absent | `"59"` | Strip |
| `isArmedForRecording` | ❌ Absent | `"0"` | Strip |
| `activeModFunction` | ❌ Absent | `"1"` | Strip |
| `colour` | ❌ Absent | `"0"` | Strip |
| `modFXCurrentParam` | `"feedback"` | `"feedback"` | Keep |
| `currentFilterType` | `"lpf"` | `"lpf"` | Keep |
| `modFXType` | `"flanger"` | `"flanger"` | Keep |
| `lpfMode` | `"24dB"` | `"24dB"` | Keep |
| `hpfMode` | `"HPLadder"` | `"HPLadder"` | Keep |
| `filterRoute` | `"H2L"` | `"H2L"` | Keep |

Note: Kits do NOT have `clipInstances` on the `<kit>` element (unlike synths). They also lack `polyphonic`, `voicePriority`, `mode`, `maxVoices` at the kit level (these are per-sound attributes within `<soundSources>`).

##### Kit-Level Child Element Ordering

**Standalone kit (c1.2.1)** — verified from Deeper.XML, Init-Kit.XML:

```
<kit ...>
    <defaultParams>                      ← kit-level params ("affect entire")
        <delay /><lpf /><hpf /><equalizer />
    </defaultParams>
    <delay />
    <sidechain />
    <audioCompressor />
    <soundSources>
        <sound name="..." ...>...</sound>
        ...
    </soundSources>
    <selectedDrumIndex>N</selectedDrumIndex>
</kit>
```

**Embedded kit in song `<instruments>` (c1.2.1)** — verified from One Eye Tea, K01Sink:

```
<kit ...>
    <delay />                            ← NO <defaultParams> before this
    <sidechain />
    <audioCompressor />
    <soundSources>
        <sound name="..." ...>...</sound>
        ...
    </soundSources>
    <selectedDrumIndex>N</selectedDrumIndex>
                                         ← NO <defaultParams>
</kit>
```

**Key difference:** `<defaultParams>` is absent from the embedded kit; lives at the clip level as `<kitParams>`. Other elements (`<delay>`, `<sidechain>`, `<audioCompressor>`, `<soundSources>`, `<selectedDrumIndex>`) are present and identical.

##### Kit Sound Row Element Ordering

**Standalone kit sound (within `<soundSources>`)** — from Deeper.XML:

```
<sound name="Deep Sky Kick HQ9094" ...>
    <osc1 />
    <osc2 />
    <lfo1 />
    <lfo2 />
    <unison />
    <defaultParams>                      ← per-row tuneable params
        <envelope1 /><envelope2 />
        <patchCables>...</patchCables>
        <equalizer />
    </defaultParams>
    <arpeggiator />                      ← per-row arpeggiator
    <modKnobs>...</modKnobs>
    <delay />
    <sidechain />
    <audioCompressor />
</sound>
```

**Embedded kit sound (within `<soundSources>`)** — from One Eye Tea, K01Sink:

```
<sound name="Deep Sky Kick HQ9094" ...>
    <osc1 />
    <osc2 />
    <lfo1 />
    <lfo2 />
    <unison />
    <arpeggiator />                      ← PRESENT (kit sounds keep their arpeggiator!)
    <modKnobs>...</modKnobs>
    <delay />
    <sidechain />
    <audioCompressor />
                                         ← NO <defaultParams>
</sound>
```

**Critical finding: Kit sounds keep `<arpeggiator>` in the instrument definition.** Unlike synth instruments (where the arpeggiator moves to the clip level), kit row sounds always have their `<arpeggiator>` element. The `<defaultParams>` is the only element absent from embedded kit sounds — it lives in the clip's `<noteRow>/<soundParams>`.

##### Kit Clip Structure

```xml
<instrumentClip instrumentPresetName="Deeper" instrumentPresetFolder="KITS" ...>
    <kitParams                            ← kit-level params → becomes <defaultParams> on <kit>
        reverbAmount="..." volume="..." pan="..." ...>
        <delay rate="..." feedback="..." />
        <lpf frequency="..." resonance="..." />
        <hpf frequency="..." resonance="..." />
        <equalizer ... />
    </kitParams>
    <columnControls>...</columnControls>  ← clip-level UI state (not extracted)
    <noteRows>
        <noteRow drumIndex="0" ...>
            <soundParams ...>             ← per-row params → becomes <defaultParams> on sound[0]
                <envelope1 /><envelope2 />
                <patchCables>...</patchCables>
                <equalizer />
            </soundParams>
        </noteRow>
        <noteRow drumIndex="1" ...>
            <soundParams ...>             ← per-row params → becomes <defaultParams> on sound[1]
                ...
            </soundParams>
        </noteRow>
        ...
    </noteRows>
</instrumentClip>
```

**Kit clips do NOT have a clip-level `<arpeggiator>` element.** Verified across One Eye Tea.XML (Deeper) and K01Sink.XML (K01Perc2) — no `<arpeggiator>` child on kit `<instrumentClip>`. This is because each kit row sound already has its own `<arpeggiator>` in the instrument definition.

##### `<kitParams>` vs Kit `<defaultParams>` — Structural Equivalence

Structurally identical — same attributes, same child elements. Verified from Deeper standalone vs One Eye Tea clip:

Standalone `<defaultParams>`:
```xml
<defaultParams
    reverbAmount="0x80000000" volume="0x3504F334" pan="0x00000000"
    sidechainCompressorShape="0xDC28F5B2" modFXDepth="0x00000000"
    modFXRate="0xE0000000" stutterRate="0x00000000"
    sampleRateReduction="0x80000000" bitCrush="0x80000000"
    modFXOffset="0x00000000" modFXFeedback="0x80000000"
    compressorThreshold="0x00000000" lpfMorph="0x80000000"
    hpfMorph="0x80000000" tempo="0x00000000">
    <delay rate="0x00000000" feedback="0x80000000" />
    <lpf frequency="0x7FFFFFFF" resonance="0x80000000" />
    <hpf frequency="0x80000000" resonance="0x80000000" />
    <equalizer bass="0x00000000" treble="0x00000000" ... />
</defaultParams>
```

Clip `<kitParams>` (same structure, different values where user tweaked):
```xml
<kitParams
    reverbAmount="0x80000000" volume="0x3504F334" pan="0x00000000"
    sidechainCompressorShape="0xDC28F5B2" modFXDepth="0x00000000"
    modFXRate="0xE0000000" stutterRate="0x00000000"
    sampleRateReduction="0xD4000000" bitCrush="0x80000000"
    modFXOffset="0x00000000" modFXFeedback="0x80000000"
    compressorThreshold="0x00000000" lpfMorph="0x80000000"
    hpfMorph="0x80000000" tempo="0x00000000">
    <delay rate="0x00000000" feedback="0x80000000" />
    <lpf frequency="0x30000000" resonance="0x80000000" />
    <hpf frequency="0x80000000" resonance="0x80000000" />
    <equalizer bass="0x00000000" treble="0x00000000" ... />
</kitParams>
```

Note: `sampleRateReduction` changed from `0x80000000` to `0xD4000000`, `lpf frequency` changed from `0x7FFFFFFF` to `0x30000000` — user tweaks.

##### Kit Row `<soundParams>` vs Sound `<defaultParams>` — Structural Equivalence

Also structurally identical. Verified from Deeper standalone sound 0 `<defaultParams>` vs One Eye Tea clip noteRow drumIndex=0 `<soundParams>`:

Both have the same attributes (`arpeggiatorGate`, `portamento`, ..., `volume`, `pan`, ..., `waveFold`, `ratchetProbability`, etc.) and same child elements (`<envelope1>`, `<envelope2>`, `<patchCables>`, `<equalizer>`). Values may differ per-clip — in the Deeper comparison, the kick's `hpfFrequency` was `0x80000000` in standalone but `0x96000000` in the One Eye Tea clip.

#### 13.4 Firmware Version Differences (4.0.1/c1.2.0 vs c1.2.1)

Since many standalone presets are older firmware versions while all songs are c1.2.1, the embedded instrument in the song is the "upgraded" c1.2.1 version. The extraction script produces c1.2.1 format, so it should use the embedded instrument's structure (already c1.2.1) rather than the standalone's.

Key structural differences between 4.0.1 and c1.2.1:

| Feature | 4.0.1 Standalone | c1.2.1 (Song & Extraction Target) |
|---------|-----------------|-----------------------------------|
| `<compressor>` | Present | Renamed to `<sidechain>` with same attrs (`attack`, `release`, `syncLevel`) plus `syncType` |
| `<audioCompressor>` | ❌ Absent | New element (`attack`, `release`, `thresh`, `ratio`, `compHPF`, `compBlend`) |
| `hpfMode` attr on `<sound>` | ❌ Absent | Present (e.g. `"HPLadder"`) |
| `filterRoute` attr on `<sound>` | ❌ Absent | Present (e.g. `"H2L"`) |
| `maxVoices` attr on `<sound>` | ❌ Absent | Present (e.g. `"8"`) |
| `syncType` on `<lfo1>` `<lfo2>` | ❌ Absent | Present (e.g. `"0"`) |
| `syncLevel` on `<lfo2>` | Sometimes absent | Always present |
| `spread` on `<unison>` | ❌ Absent | Present (e.g. `"0"`) |
| `syncType` on `<delay>` | ❌ Absent | Present |
| `<defaultParams>` extra attrs | Missing: `compressorThreshold`, `lpfMorph`, `hpfMorph`, `waveFold`, `ratchetProbability`, `ratchetAmount`, `sequenceLength`, `rhythm` | All present |
| `<arpeggiator>` extra attrs | Missing: `syncType`, `arpMode`, `noteMode`, `octaveMode`, `mpeVelocity` | All present |
| Synth element order | `osc, lfo, unison, delay, compressor, defaultParams, arpeggiator, modKnobs` | `osc, lfo, unison, defaultParams, arpeggiator, modKnobs, delay, sidechain, audioCompressor` |
| Kit element order | `delay, compressor, defaultParams, soundSources, selectedDrumIndex` | `defaultParams, delay, sidechain, audioCompressor, soundSources, selectedDrumIndex` |

**Impact on extraction:** The embedded instruments in c1.2.1 songs already have the c1.2.1 structure for all shared elements (oscillators, LFOs, unison, modKnobs, delay, sidechain, audioCompressor). The extraction script does NOT need to upgrade firmware formats — it just needs to:
1. Reorder elements to match standalone c1.2.1 ordering
2. Insert `<defaultParams>` (from clip `<soundParams>` / `<kitParams>`) at the correct position
3. Insert `<arpeggiator>` (from clip, for synths only) at the correct position
4. Add firmware version attributes
5. Strip song-specific attributes

#### 13.5 Transformation Recipe

##### Synth Extraction (precise steps)

Given a synth `<sound>` from `<instruments>` and its corresponding `<instrumentClip>`:

1. **Clone** the `<sound>` element from `<instruments>`
2. **Strip** song-specific attributes: `presetName`, `presetFolder`, `defaultVelocity`, `isArmedForRecording`, `activeModFunction`, `clipInstances`, `colour`
3. **Add** `firmwareVersion="c1.2.1"` and `earliestCompatibleFirmware="4.1.0-alpha"`
4. **Extract** `<soundParams>` from `<instrumentClip>` → **rename** tag to `<defaultParams>`
5. **Extract** `<arpeggiator>` from `<instrumentClip>` → **strip** extra numeric attributes (`gate`, `rate`, `ratchetProbability`, `ratchetAmount`, `sequenceLength`, `rhythm`) if present
6. **Reorder** child elements of `<sound>` to match standalone format:
   - Keep: `<osc1>`, `<osc2>`, `<lfo1>`, `<lfo2>`, (`<modulator1>`, `<modulator2>` if present), `<unison>` (positions 1–7, already correct)
   - **Insert** `<defaultParams>` after `<unison>` (or after modulators if FM mode)
   - **Insert** `<arpeggiator>` after `<defaultParams>`
   - Keep `<modKnobs>` after `<arpeggiator>` (it's already in the embedded instrument but will need repositioning)
   - Keep `<delay>`, `<sidechain>`, `<audioCompressor>` at the end (already correct relative order)

The net effect on element ordering:
```
Embedded:  osc1, osc2, lfo1, lfo2, [mod], unison, modKnobs, delay, sidechain, audioCompressor
                                                   ^^^^^^^^ move down
Standalone: osc1, osc2, lfo1, lfo2, [mod], unison, +defaultParams, +arpeggiator, modKnobs, delay, sidechain, audioCompressor
                                                    ^^^^^^^^^^^^^^  ^^^^^^^^^^^^^ inserted from clip
```

##### Kit Extraction (precise steps)

Given a `<kit>` from `<instruments>` and its corresponding `<instrumentClip>`:

1. **Clone** the `<kit>` element from `<instruments>`
2. **Strip** song-specific attributes: `presetName`, `presetFolder`, `defaultVelocity`, `isArmedForRecording`, `activeModFunction`, `colour`
3. **Add** `firmwareVersion="c1.2.1"` and `earliestCompatibleFirmware="4.1.0-alpha"`
4. **Extract** `<kitParams>` from `<instrumentClip>` → **rename** tag to `<defaultParams>`
5. **Insert** `<defaultParams>` as the **first** child of `<kit>` (before `<delay>`)
6. **For each `<noteRow>`** in the clip with a `drumIndex` attribute:
   - Extract `<soundParams>` from the `<noteRow>` → **rename** tag to `<defaultParams>`
   - Find the corresponding `<sound>` in `<soundSources>` by list position (`drumIndex` is a 0-based index)
   - **Insert** `<defaultParams>` into that `<sound>` between `<unison>` and `<arpeggiator>`
7. `<arpeggiator>` on each kit sound — **leave in place** (already present in embedded kit sounds)
8. No need to insert an arpeggiator from the clip level (kit clips don't have one)

The net effect on element ordering:

Kit level:
```
Embedded:   delay, sidechain, audioCompressor, soundSources, selectedDrumIndex
Standalone: +defaultParams, delay, sidechain, audioCompressor, soundSources, selectedDrumIndex
            ^^^^^^^^^^^^^^ inserted from clip's <kitParams>
```

Per kit row sound:
```
Embedded:   osc1, osc2, lfo1, lfo2, unison, arpeggiator, modKnobs, delay, sidechain, audioCompressor
Standalone: osc1, osc2, lfo1, lfo2, unison, +defaultParams, arpeggiator, modKnobs, delay, sidechain, audioCompressor
                                              ^^^^^^^^^^^^^^ inserted from noteRow's <soundParams>
```

#### 13.6 Key Findings Affecting Extraction Logic

1. **Kit arpeggiator asymmetry (CRITICAL):** Kit sounds keep `<arpeggiator>` in the instrument definition; synth instruments move it to the clip. The extraction script must handle these differently — inject arpeggiator from clip for synths, leave it in place for kit sounds.

2. **Kit clips have no clip-level arpeggiator (CRITICAL):** Unlike synth clips which always have `<arpeggiator>`, kit clips do NOT have one. The arpeggiator-from-clip extraction step must be skipped for kits.

3. **Clip arpeggiator has extra attributes (IMPORTANT):** Some synth clip arpeggiators have `gate`, `rate`, `ratchetProbability`, `ratchetAmount`, `sequenceLength`, `rhythm` attributes that are not present on standalone presets. These must be stripped.

4. **`<modKnobs>` position differs (IMPORTANT):** In standalones, `<modKnobs>` comes after `<arpeggiator>`. In embedded instruments, it comes after `<unison>` (before `<delay>`). The extraction script must reorder this element.

5. **Instrument-level settings may differ from standalone (IMPORTANT):** The `<delay>`, `<sidechain>`, and other instrument-level elements in the song may have different attribute values than the original standalone preset (user tweaked them in the song). The extraction should use the embedded values.

6. **Parameter automation in soundParams values (IMPORTANT):** Some `<soundParams>` attribute values encode automation curves as extended hex strings (e.g. `lpfFrequency="0x7FFFFFFF7FFFFFFF000000607FFFFFFF00000120"` in K01Sink.XML K01Perc2), not just single hex values. These must be preserved verbatim as attribute text.

7. **Tag rename is the only param transformation:** `<soundParams>` → `<defaultParams>` and `<kitParams>` → `<defaultParams>` are pure tag renames with no attribute or child element changes needed.

8. **`presetFolder` may not match standalone location:** Instruments may have been moved between folders after being loaded into a song (e.g. K09Arparty references `KRumchybass` in `SYNTHS` but the standalone file is in `SYNTHS/KERERU`). This affects deduplication logic but not extraction.

### 14. Unmodified Preset Analysis

**Source:** Manual parameter comparison of 5 instrument pairs across standalone presets and song-embedded versions.

#### 14.1 Comparison Results

| Instrument | Type | Song | Standalone File | Result |
|---|---|---|---|---|
| K01Bass | Synth | K01Sink.XML | `SYNTHS/KERERU/K01Bass.XML` | **Unmodified** — all 37 params identical |
| K01Arp | Synth | K01Sink.XML | `SYNTHS/KERERU/K01Arp.XML` | **Modified** — 8 params differ (pan, LFO rate, modulator, delay, reverb, envelopes) |
| K01Drone | Synth | K01Sink.XML, K09Arparty.XML | `SYNTHS/KERERU/K01Drone.XML` | **Modified** — filter cutoff changed in both songs; delay feedback differs in K09 |
| K01Fuzzbass | Synth | K09Arparty.XML | `SYNTHS/KERERU/K01Fuzzbass.XML` | **Modified** — pan, filter cutoff, envelope attack tweaked |
| Deeper | Kit | Ell.XML, K05BeautifulStranger.XML | `KITS/KERERU/Deeper.XML` | **Unmodified** — kit-level and row-level params identical |

Result: ~40% unmodified, ~60% modified.

#### 14.2 Analysis

Modified instruments typically have 3–8 parameter tweaks targeting song-specific context: filter frequencies, pan positioning, envelope timing, effects sends. These are exactly the customisations that make extraction valuable.

#### 14.3 Recommendation: Do Not Optimise for Unmodified Presets

Reasons:

1. **Unmodified instruments are the least interesting** — they already exist as standalone presets. The extraction script's value is in capturing modified versions.
2. **Detection adds complexity without reducing work** — a full parameter comparison engine would be needed just to decide whether to copy or extract, and the extraction path is still required for the majority.
3. **Firmware version mismatch risk** — standalone presets may be on older firmware (e.g. 4.0.1) while songs are c1.2.1. A straight copy could produce version-inconsistent output.
4. **The extraction pipeline handles both cases identically** — an unmodified instrument produces a correct output either way.

### 15. modKnobs Structure and Version Comparison Strategy

**Source:** Analysis of `<modKnobs>` elements across standalone presets and song-embedded instruments; cross-section parameter comparison of K01Drone in K01Sink.XML

#### 15.1 modKnobs Overview

- Each instrument has exactly 16 `<modKnob>` elements representing the 16 physical knobs on the Deluge
- Each has a required `controlsParam` attribute and an optional `patchAmountFromSource` attribute
- modKnobs live at the **instrument level** (on `<sound>` in instruments, or per-`<sound>` in kit `<soundSources>`), NOT at the clip level
- They are shared across all section/colour versions of the same instrument — they don't vary per clip
- They represent the params the user actively mapped to physical knobs, i.e. the params they were performing with

#### 15.2 Default vs Customized Knob Mappings

The first 12 knobs (slots 0–11) form a stable framework that is rarely customised. The main exceptions:

- **Slots 2–3** automatically switch from `lpfResonance`/`lpfFrequency` to `modulator2Volume`/`modulator1Volume` (or similar FM params) for FM synth mode
- **Slot 12** is type-dependent: `portamento` for synths, `pitch` for kit sounds

**Slots 13–15 are the primary customisation zone** — users remap these to sound-specific params.

Examples of FM mode substitution at slots 2–4 and 14–16:

| Knob Positions | Default (subtractive) | FM synth example |
|---|---|---|
| 3–4 | `lpfResonance`, `lpfFrequency` | `modulator1Volume`, `modulator1Feedback` |
| 15–16 | `bitcrushAmount`, `sampleRateReduction` | `modulator2Volume`, `carrier1Feedback` |

Custom slots can also use `patchAmountFromSource` to control modulation depths rather than direct parameter values. Observed `patchAmountFromSource` values across all songs: `compressor`, `lfo1`, `lfo2`, `envelope1`, `envelope2`, `velocity`. [Verified — Init-Kit.XML, song XMLs]

#### 15.3 Proposed Version Comparison Strategy (for Extended Mode)

For instruments with multiple section versions, use modKnobs as a guide for evaluating whether versions are "sufficiently different" to extract separately:

1. Read the instrument's `<modKnobs>` to get the 16 param names the user actively mapped
2. For each section version, read the corresponding values from `<soundParams>`
3. Compare those specific values across versions
4. If ≥ X params differ by ≥ Y amount, treat the versions as distinct

**Why modKnobs are a good proxy:** They're the params the user chose to have at their fingertips — changes there are almost certainly intentional sound design, not incidental.

#### 15.4 controlsParam to XML Path Mapping

Most `controlsParam` names map directly to `<soundParams>` attributes, but some require special handling:

| Complexity | Examples | Mapping |
|---|---|---|
| Direct attribute (~10 knobs) | `lpfFrequency`, `delayFeedback`, `reverbAmount`, `pan`, `oscBVolume`, `lfo1Rate` | `soundParams/@{controlsParam}` |
| Child element (~2 knobs) | `env1Attack` → `envelope1/@attack`, `env1Release` → `envelope1/@release` | Path into child element |
| PatchCable lookup (~2 knobs) | `volumePostReverbSend` + `patchAmountFromSource="compressor"` | Search `<patchCable source="..." destination="...">` and compare `@amount` |
| Ambiguous (~1–2 knobs) | `volumePostFX` → likely `@volume` | Needs name normalization |

The mapping table is ~20 entries, most trivial. ~50–80 lines of implementation.

#### 15.5 Recommendation

Defer the comparison logic from v1 (which extracts one version per instrument using lowest section ID). For extended mode, two approaches in order of simplicity:

1. **Simple: Compare all soundParams** — trivially compare all 41 attributes. Catches everything but may flag trivial differences.
2. **Smart: Compare all, weight modKnob params higher** — compare all params but weight modKnob-mapped params higher in the significance calculation. Reduces noise from incidental changes.

The modKnob-weighted approach can be added later if the simple all-params comparison produces too many near-duplicate extractions.

#### 15.6 Cross-Section Variation Observed

Examined K01Drone across sections 2, 3, and 4 in K01Sink.XML:
- Most parameters (volume, pan, lfo1Rate) are **identical across sections**
- Main differences were in `lpfFrequency` and `lpfResonance`
- Some section clips contain **embedded automation data** (extended hex strings) while others have static values
- This suggests cross-section variation is typically limited to a few parameters being tweaked for different song parts, not wholesale redesigns

#### 15.7 modKnobs as Hard Marker in Comparison Engine

The comparison engine treats `<modKnobs>` mapping as a structural hard marker: [Verified — Init-Kit.XML, song XMLs]

- A positional comparison of all 16 `<modKnob>` entries is performed
- Any difference in `controlsParam` or `patchAmountFromSource` at any position = hard distinct
- For synths: checked on the top-level `<sound>` element
- For kits: checked per-sound inside `<soundSources>` (no kit-level `<modKnobs>` exist)
- This was implemented based on the insight that changing which parameter a knob controls reflects deliberate sound design intent, even if the parameter values haven't changed
- The actual *values* of modKnob-controlled parameters follow standard soft-marker rules (threshold-based) — see Section 16.2

#### 15.8 Kit-Level Knob Behaviour (Affect Entire)

When "affect entire" is enabled on a kit clip, the gold knobs control kit-level parameters instead of per-sound parameters. However, this mapping is not persisted to XML: [Verified — Init-Kit.XML, song XMLs]

- Kits have NO `<modKnobs>` at the `<kit>` level — only per-sound `<modKnobs>` inside `<soundSources>/<sound>`
- The "affect entire" gold knob mapping is firmware-hardcoded, not persisted to XML
- Kit-level `<defaultParams>` has a different parameter set from per-sound params. Unique kit-level params observed: `sidechainCompressorShape`, `modFXDepth`, `modFXRate`, `modFXOffset`, `modFXFeedback`, `compressorThreshold`, `lpfMorph`, `hpfMorph`, `tempo`
- Only the resulting parameter values in kit-level `<defaultParams>` are saved, not the knob assignments used to set them

### 16. Generalised Comparison Engine Design

**Source:** Analysis of existing `compare_versions()` stub in [extraction.py](scripts/deluge_lib/extraction.py), user requirements, and XML structure analysis across all examined presets and songs.

#### 16.1 Motivation

The existing `compare_versions()` function (Task 4.1, currently a stub) implements intra-song comparison for extended mode. A new cross-song deduplication system also needs comparison logic. Rather than building two independent comparison engines, both should share a single generalised comparison engine with configurable rulesets.

The user observed that many extracted instruments are essentially identical — e.g., Kit 000 / TR-808 appears in at least 10 songs as a starting point. K01Bass appears in 4 songs (K01Sink, Wf, Ambient-Fishes, Wf 7). Deeper kit appears in 5 songs (Ell, K05BeautifulStranger, One Eye Tea, Noize, No-More-Colour). Without dedup, the output is cluttered with near-duplicates.

#### 16.2 Three-Tier Comparison Model

The comparison engine classifies XML parameters into three tiers:

##### Tier 1: Hard Markers (Structural Identity)

Parameters/elements that, if changed, immediately indicate a fundamentally different instrument regardless of any other changes. A single hard marker difference = "distinct instrument".

**Synth hard markers (on the assembled standalone `<sound>`):**

| Element/Attribute | Path | Rationale |
|---|---|---|
| Synthesis mode | `<sound mode="...">` | `subtractive` vs `FM` vs `ringmod` = completely different synth engine |
| Polyphony mode | `<sound polyphonic="...">` | `poly` vs `mono` vs `legato` vs `choke` = different playing behaviour |
| Oscillator 1 type | `<osc1 type="...">` | `square` vs `saw` vs `sample` vs `wavetable` etc. = different sound source |
| Oscillator 2 type | `<osc2 type="...">` | Same as osc1 |
| Oscillator 1 sample | `<osc1 fileName="...">` | Different sample file = fundamentally different sound |
| Oscillator 2 sample | `<osc2 fileName="...">` | Same as osc1 |
| Filter route | `<sound filterRoute="...">` | `H2L` vs `L2H` vs `parallel` = different signal flow |
| LPF mode | `<sound lpfMode="...">` | `12dB` vs `24dB` vs different filter types |
| HPF mode | `<sound hpfMode="...">` | Same as LPF mode |
| Mod FX type | `<sound modFXType="...">` | `none` vs `flanger` vs `chorus` vs `phaser` etc. = different effect |
| PatchCables structure | `<patchCables>` children | Added/removed cables = different modulation routing (compare by `source`+`destination` pairs, not `amount` values) |
| Arpeggiator mode | `<arpeggiator mode="...">` | `off` vs `arp` = structurally different instrument behaviour |
| Arpeggiator note mode | `<arpeggiator noteMode="...">` | `up` vs `down` vs `upDown` vs `random` etc. |
| Arpeggiator octave mode | `<arpeggiator octaveMode="...">` | `up` vs `down` vs `upDown` vs `random` etc. |

Additionally, `<modKnobs>` mapping is compared as a structural hard marker — any positional change in `controlsParam` or `patchAmountFromSource` = distinct instrument. See Section 15.7.

**Kit hard markers (on the assembled standalone `<kit>`):**

| Element/Attribute | Path | Rationale |
|---|---|---|
| Sound count | `len(<soundSources>)` | Different number of drum rows = different kit composition |
| Sound order/identity | `<sound name="...">` in `<soundSources>` | Different drum names or ordering = different kit |
| Per-sound sample files | `<sound>/<osc1 fileName="...">` | Different samples on any row = different kit |
| Per-sound oscillator types | `<sound>/<osc1 type="...">` | Different oscillator types on any row |
| Per-sound arpeggiator mode | `<sound>/<arpeggiator mode="...">` | Per-row arpeggiator changes |
| Kit-level mod FX type | `<kit modFXType="...">` | Different master effect |
| Kit-level filter modes | `<kit lpfMode="...">`, `<kit hpfMode="...">` | Different filter configuration |

Additionally, per-sound `<modKnobs>` mapping is compared as a structural hard marker — any positional change in `controlsParam` or `patchAmountFromSource` on any kit row sound = distinct kit. See Section 15.7.

**Note on `<patchCables>` comparison:** Compare the _set_ of `(source, destination)` tuples, not the `amount` values. Adding or removing a patch cable is structural (hard marker); changing the amount of an existing cable is numerical (soft marker).

##### Tier 2: Soft Markers (Numerical Threshold-Based)

Parameters that are significant only if they've changed by more than a per-parameter threshold AND the total number of changed soft params exceeds a group threshold. These are the hex-encoded numerical values on `<defaultParams>` and its child elements.

**Synth soft marker attributes (on `<defaultParams>`, excluding ignored):**

All 41 numerical hex attributes on `<defaultParams>` minus the ignored params. The full set observed on c1.2.1 presets:

```
arpeggiatorGate, portamento, compressorShape,
oscAVolume, oscAPulseWidth, oscAWavetablePosition,
oscBVolume, oscBPulseWidth, oscBWavetablePosition,
noiseVolume, lpfFrequency, lpfResonance,
hpfFrequency, hpfResonance, lfo1Rate, lfo2Rate,
modulator1Amount, modulator1Feedback,
modulator2Amount, modulator2Feedback,
carrier1Feedback, carrier2Feedback,
modFXRate, modFXDepth, delayRate, delayFeedback,
reverbAmount, arpeggiatorRate, stutterRate,
sampleRateReduction, bitCrush, modFXOffset, modFXFeedback,
compressorThreshold, lpfMorph, hpfMorph, waveFold,
ratchetProbability, ratchetAmount, sequenceLength, rhythm
```

**Additionally, child element attributes:**

| Element | Attributes | Count |
|---|---|---|
| `<envelope1>` | `attack`, `decay`, `sustain`, `release` | 4 |
| `<envelope2>` | `attack`, `decay`, `sustain`, `release` | 4 |
| `<patchCable>` | `amount` (per existing cable) | variable |
| `<equalizer>` | `bass`, `treble`, `bassFrequency`, `trebleFrequency` | 4 |

**Kit soft marker attributes:**

Kit-level `<defaultParams>` has ~15 hex attributes (different set from synth — includes `sidechainCompressorShape`, `tempo`, but lacks oscillator-specific params). Each kit row sound's `<defaultParams>` has the same ~41 attributes as synth `<defaultParams>`.

**Threshold mechanism:**

1. **Per-param threshold:** Parse hex value as 32-bit signed integer. Calculate absolute difference as proportion of the full range (`0x00000000` to `0x7FFFFFFF` = 2,147,483,647). A param "differs" if the proportional difference exceeds the per-param threshold.
2. **Group threshold:** The instrument is "distinct" if the total count of differing soft params ≥ the count threshold.

**Existing constants:**
- `DIFF_PARAM_COUNT_THRESHOLD = 3` — minimum number of soft params that must differ
- `DIFF_PARAM_PERCENT_THRESHOLD = 0.10` (10%) — minimum proportional change per param

These thresholds mean: if ≥3 params have each changed by ≥10% of the full range, the versions are distinct. This filters out incidental 1-2 param nudges while catching deliberate sound design changes.

##### Tier 3: Ignorable Params

Parameters excluded from comparison entirely. Currently:
- `volume` — normalised during extraction (reset to init value), so any pre-normalisation difference is meaningless
- `pan` — normalised to centre during extraction

These are defined in `COMPARISON_EXCLUDED_ATTRS = ("volume", "pan")` in [extraction.py](scripts/deluge_lib/extraction.py).

**Note:** Volume is both ignored in comparison AND normalised during extraction. Pan is similarly both ignored and normalised. This dual treatment is intentional — even if comparison ran before normalisation, these params should not influence the distinct/duplicate decision.

#### 16.3 Comparison Config Data Structure

The config should be a Python dataclass (consistent with `NormalisationConfig` pattern already in the codebase):

```python
@dataclass
class ComparisonConfig:
    """Configurable ruleset for the generalised comparison engine."""

    # Hard markers — structural attributes that make instruments immediately distinct
    synth_hard_attrs: dict[str, set[str]]
    # Maps element path → set of attribute names
    # e.g. {"sound": {"mode", "polyphonic", "modFXType", ...},
    #        "osc1": {"type", "fileName"}, ...}

    kit_hard_attrs: dict[str, set[str]]
    # Same structure for kit-specific hard markers

    # Soft marker thresholds
    param_count_threshold: int      # min number of params that must differ
    param_percent_threshold: float  # min proportional change per param (0.0–1.0)

    # Ignored attributes — excluded from all comparison
    ignored_attrs: set[str]         # e.g. {"volume", "pan"}
```

**Default factory pattern:** Provide a `default()` classmethod that returns the standard config (matching the existing constants), so it can be easily overridden for testing:

```python
@classmethod
def default(cls) -> ComparisonConfig:
    return cls(
        synth_hard_attrs={...},
        kit_hard_attrs={...},
        param_count_threshold=3,
        param_percent_threshold=0.10,
        ignored_attrs={"volume", "pan"},
    )
```

**Why a dataclass over a TOML/YAML config file:** The config is primarily for developer tuning during testing, not user-facing configuration. A Python dataclass is type-safe, IDE-completable, and testable without parsing. If user-facing config is later needed, a thin loader can hydrate the dataclass from a config file.

#### 16.4 Comparison Function Signature

The generalised comparison function operates on **assembled standalone presets** (post-extraction, post-normalisation), not on raw clip/instrument pairs. This simplifies the comparison — the engine doesn't need to know about the split instrument/clip architecture.

```python
def compare_instruments(
    preset_a: etree._Element,
    preset_b: etree._Element,
    instrument_type: str,  # "synth" or "kit"
    config: ComparisonConfig,
) -> ComparisonResult:
    """Compare two assembled standalone presets for equivalence."""
```

**ComparisonResult** should include:
- `is_distinct: bool` — True if instruments are sufficiently different
- `hard_diffs: list[str]` — hard marker differences found (if any, immediately distinct)
- `soft_diff_count: int` — number of soft params that exceeded threshold
- `soft_diffs: list[str]` — names of soft params that differed
- `reason: str` — human-readable summary ("hard: osc1 type changed" or "soft: 5/41 params differ >10%")

#### 16.5 Kit Comparison: Sound-Level vs Kit-Level

Kit comparison requires two levels:

1. **Kit-level structural comparison:** Compare `<soundSources>` structure (count, names, oscillator types, sample files). Any difference here is a hard marker.
2. **Kit-level params:** Compare kit-level `<defaultParams>` (the "affect entire" params).
3. **Per-sound comparison:** For each matching sound (by index and name), compare the sound's `<defaultParams>` independently.

**Recommendation:** If the kit structure matches (same sounds in same order), apply soft-marker comparison per-sound. If _any_ sound has enough soft diffs to be distinct, the whole kit is distinct. This prevents false negatives where a kit has one heavily-tweaked row but the rest are identical.

#### 16.6 PatchCables Comparison Strategy

`<patchCables>` is a special case spanning both hard and soft tiers:

- **Hard:** The _set_ of `(source, destination)` pairs. Adding/removing a cable means a different modulation routing = structural change.
- **Soft:** The `amount` value on each cable. Changing how much velocity affects volume is a numerical tweak.

Implementation: Build a dict of `(source, dest) → amount` for each preset. If the key sets differ → hard diff. If key sets match but amounts differ → treat each amount as a soft param.

#### 16.7 Instrument-Level Settings in Comparison

The `<delay>`, `<sidechain>`, and `<audioCompressor>` elements on the instrument (not inside `<defaultParams>`) carry their own attributes. These are structural settings (not numerical hex params) that may differ between versions:

| Element | Attributes |
|---|---|
| `<delay>` | `pingPong`, `analog`, `syncLevel`, `syncType` |
| `<sidechain>` | `attack`, `release`, `syncLevel`, `syncType` |
| `<audioCompressor>` | `attack`, `release`, `thresh`, `ratio`, `compHPF`, `compBlend` |

**Recommendation:** Treat these as soft markers. They are integer/numeric values, not hex-encoded, but they represent tweakable settings rather than structural identity. Include them in the soft param count.

#### 16.8 Envelope Comparison

`<envelope1>` and `<envelope2>` each have 4 hex attributes: `attack`, `decay`, `sustain`, `release`. These are structurally children of `<defaultParams>` but represent important sound-shaping parameters.

**Recommendation:** Treat envelope attributes as soft markers. The existing `compare_versions()` stub already describes envelope attributes as part of the "non-numerical changes in params" tier (step 2), but they are actually hex-encoded numerical values and belong in the soft-marker tier. The engine should walk into `<defaultParams>` child elements and compare their attributes using the same threshold logic.

### 17. Cross-Song Deduplication Algorithm

**Source:** User requirements, analysis of preset name frequency across 58 songs, codebase flow analysis.

#### 17.1 Scope and Placement

Cross-song dedup is a **post-extraction filter** — it runs after all songs have been processed and `all_results` is fully populated, but before writing files to disk.

**Current flow in [extract_instruments.py](scripts/extract_instruments.py):**

```
1. discover_songs()
2. For each song:
   a. discover_instruments() + discover_clips()
   b. match_instruments_to_clips()
   c. select_default_clip() or select_extended_clips()  ← intra-song selection
   d. extract_synth() / extract_kit()
   e. _strip_automation()
   f. normalise_params()
   g. Append to all_results
3. Print summary                                         ← dedup goes HERE
4. Write files
```

**Updated flow with dedup:**

```
1–2. (unchanged — build all_results)
3. deduplicate_results(all_results, config)              ← NEW
4. Print summary (with dedup stats)
5. Write files (only accepted results)
```

#### 17.2 Algorithm: Baseline + Incremental Acceptance

```
For each group of results sharing the same (preset_name, instrument_type):
  1. Sort by song name (deterministic ordering)
  2. First result becomes the baseline → automatically ACCEPTED
  3. For each subsequent result:
     a. Compare against ALL accepted results (not just baseline)
     b. If sufficiently different from ALL accepted → ACCEPT
     c. If sufficiently similar to ANY accepted → REJECT (duplicate)
  4. Collect rejected results for reporting
```

**Why compare against all accepted, not just baseline:** A user might have three versions: A (original), B (slight tweak of A), C (slight tweak of B). Comparing only against A might accept both B and C. Comparing against all accepted means C is compared against both A and B — if C is too similar to B, it's rejected even if it differs slightly from A.

**Why sort by song name:** Provides deterministic, reproducible results. The first song alphabetically "wins" the baseline. This is consistent with the default-mode strategy of preferring deterministic selection.

#### 17.3 Grouping Strategy: Preset-Name Groups vs Global

**Option A: Group by `(preset_name, instrument_type)`**

Compare within groups of results that share the same preset name. "Deeper" kits are only compared against other "Deeper" kits, not against "K01Perc2" kits.

- **Pro:** Fast — small comparison groups. Semantically correct — instruments with different names are almost certainly different instruments.
- **Pro:** Handles the primary use case directly: the same kit loaded as a starting point in multiple songs.
- **Con:** Misses cases where the user saved the same instrument under different names in different songs (unlikely but possible).

**Option B: Global comparison across all results of the same type**

Compare every synth against every other synth, every kit against every other kit, regardless of name.

- **Pro:** Catches cross-name duplicates.
- **Con:** O(n²) comparisons — with 200+ extracted instruments, this is ~20,000 comparisons. Kit comparison involves walking multiple `<soundSources>`, so each comparison is non-trivial.
- **Con:** High false-positive risk — two unrelated instruments might have similar param values by coincidence.

**Option C: Hybrid — group by name, then optional global pass**

Default to preset-name grouping. Optionally add a `--global-dedup` flag for full cross-name comparison.

**Recommendation: Option A (group by preset name).** The motivation for dedup is handling the "TR-808 in every song" pattern, where the same-named starting-point preset appears repeatedly. Cross-name duplication is an edge case that adds complexity without clear value. The hard marker comparison (oscillator types, sample files) would catch structurally identical instruments under different names if global mode is later needed.

#### 17.4 Preset Name Matching Considerations

Preset names in songs come from the `presetName` attribute. Some considerations:

| Scenario | Example | Handling |
|---|---|---|
| Exact name match | "Deeper" in Ell.XML and One Eye Tea.XML | Same group — direct comparison |
| Numeric factory names | "000" in 10+ songs | Same group — these are the primary dedup targets |
| Name with folder mismatch | "KRumchybass" in `SYNTHS` vs `SYNTHS/KERERU` | Group by name only, ignore folder — the instrument is the same preset regardless of where it was loaded from |
| Case sensitivity | Unlikely to vary | Case-sensitive matching (consistent with FAT32/Deluge behaviour) |

**Key decision: Group by `preset_name` only, ignoring `preset_folder`.** The `presetFolder` indicates where the preset was loaded from, which can change if presets are moved. Two instruments named "K01Bass" loaded from different folders are almost certainly the same base preset.

#### 17.5 Flag Behaviour

- **Default:** Dedup is **always on**. The primary user runs the script periodically and wants clean output without duplicates.
- **Disable:** `--no-dedup` flag to skip deduplication and extract all versions from all songs.
- **Interaction with `--extended`:**
  - `--extended` enables intra-song breadth (multiple section variants per song)
  - Dedup then reduces inter-song redundancy across those expanded results
  - `--extended --no-dedup` extracts everything from every song without filtering

#### 17.6 Dedup Reporting

When dedup removes results, the summary should report:
- How many results were removed as duplicates
- Which preset names had duplicates removed
- Optionally (with a verbose flag): which specific song × preset combinations were rejected and which accepted result they matched

Example output:
```
Dedup: Removed 12 duplicates (8 synths, 4 kits)
  000 (kit): kept Alr, removed Ape, Beginagain, Bingbong, Bloop, ...
  K01Bass (synth): kept Ambient-Fishes, removed K01Sink, Wf, Wf 7
  Deeper (kit): kept Ell, removed K05BeautifulStranger, No-More-Colour, Noize, One Eye Tea
```

#### 17.7 Threshold Independence

Intra-song comparison (extended mode) and inter-song comparison (dedup) will probably use very similar thresholds, but the system should support different `ComparisonConfig` instances per use case:

```python
# In extract_instruments.py main():
intra_song_config = ComparisonConfig.default()
dedup_config = ComparisonConfig.default()  # same defaults, independently tweakable
```

This allows the user to tune thresholds during testing — e.g., making dedup more aggressive (lower thresholds) while keeping intra-song comparison more permissive.

### 18. Impact on Existing Extended Mode Design

**Source:** Analysis of existing `compare_versions()` and `select_extended_clips()` stubs in [extraction.py](scripts/deluge_lib/extraction.py).

#### 18.1 Current Stubs

The existing code has two `NotImplementedError` stubs:

1. **`compare_versions(clip_a, clip_b, instrument)`** — compares two clips of the same instrument within a song. Takes raw clip elements and the shared instrument element.
2. **`select_extended_clips(group)`** — selects which clips to extract in extended mode. Currently compares each candidate against the baseline only.

#### 18.2 Generalisation Changes

With the generalised comparison engine, these stubs change as follows:

**`compare_versions()` → replaced by `compare_instruments()`**

The existing `compare_versions()` operates on raw clips + instrument (pre-extraction). The generalised engine operates on assembled standalone presets (post-extraction). This is a better design because:
- The comparison sees the complete instrument (merged structure + params), not the split representation
- The same function works for both intra-song and inter-song comparison
- Post-normalisation comparison means volume/pan are already at init values

**Impact:** `compare_versions()` can be removed or refactored into a thin wrapper that:
1. Calls `extract_synth()`/`extract_kit()` to assemble each candidate
2. Calls `normalise_params()` on each
3. Calls `compare_instruments()` on the assembled pair

**`select_extended_clips()` → updated to use generalised engine**

The current stub compares each candidate against the baseline only. With the generalised engine, it should compare against ALL accepted clips (same pattern as cross-song dedup). This ensures that if clips B and C are both similar to A but different from each other, both are kept — but if D is similar to C, it's rejected.

Updated algorithm:
```
1. Sort clips by section ID (ascending)
2. Extract + normalise the baseline clip → add to accepted list
3. For each subsequent clip:
   a. Extract + normalise the candidate
   b. Compare against ALL accepted using compare_instruments()
   c. If distinct from all → accept
   d. If similar to any → reject
4. Return accepted clips
```

#### 18.3 Performance Consideration

The generalised approach means each candidate clip is extracted and normalised before comparison (rather than comparing raw clips). This adds some overhead but:
- The extraction is a pure in-memory XML transformation — no I/O
- Most instruments have ≤4 section variants, so at most ~6 pairwise comparisons per instrument per song
- For cross-song dedup, the presets are already extracted — no additional extraction cost

#### 18.4 Existing Constants Migration

The existing constants in [extraction.py](scripts/deluge_lib/extraction.py) should be consumed by the `ComparisonConfig`:

| Existing Constant | Maps to |
|---|---|
| `DIFF_PARAM_COUNT_THRESHOLD = 3` | `ComparisonConfig.param_count_threshold` |
| `DIFF_PARAM_PERCENT_THRESHOLD = 0.10` | `ComparisonConfig.param_percent_threshold` |
| `COMPARISON_EXCLUDED_ATTRS = ("volume", "pan")` | `ComparisonConfig.ignored_attrs` |

The constants can remain as module-level defaults that the `ComparisonConfig.default()` factory uses, maintaining backward compatibility.

### 19. Cross-Song Duplication Analysis

**Source:** Grep analysis across all 58 song XMLs to quantify actual duplication patterns.

#### 19.1 High-Frequency Preset Names

| Preset Name | Type | Songs Containing It | Notes |
|---|---|---|---|
| `000` | Kit | 10+ songs | TR-808 factory kit — the most duplicated instrument |
| `Deeper` | Kit | 5 songs (Ell, K05BeautifulStranger, One Eye Tea, Noize, No-More-Colour) | User-created kit reused across projects |
| `K01Bass` | Synth | 4 songs (K01Sink, Wf, Ambient-Fishes, Wf 7) | User bass preset |
| `K01Drone` | Synth | Multiple songs | User drone preset |

#### 19.2 Expected Dedup Impact

Based on Section 14's unmodified preset analysis (~40% unmodified), dedup should remove a significant portion of extracted results. Conservative estimate: 20-30% reduction in total output files, with the highest impact on factory presets like kit `000`.

#### 19.3 Edge Cases for Dedup

| Edge Case | Scenario | Handling |
|---|---|---|
| Same name, genuinely different | User creates "Bass" in two songs independently with totally different oscillator settings | Hard markers will detect structural differences → both kept |
| Same name, slightly tweaked | "Deeper" with minor filter cutoff changes across songs | Soft marker thresholds determine whether these are "different enough" |
| Different name, same instrument | User saves "K01Bass" as "MyBass" in another song | Not detected by preset-name grouping (acceptable — see 17.3) |
| Kit with added/removed rows | "000" with an extra drum row added in one song | Hard marker (soundSources count differs) → both kept |
| Automation-stripped differences | Two versions differ only in automation data (stripped during extraction) | After automation stripping, they compare as identical → correctly deduplicated |
| Extended mode + dedup | Song A has 3 versions of "Bass", Song B has 2 versions of "Bass" | Extended selection runs first (intra-song), then dedup filters across songs. Each accepted version from Song A is compared against each from Song B. |

## Approaches Considered

| Approach | Pros | Cons | Complexity |
|----------|------|------|------------|
| **A: Merge instrument + clip params** (recommended) | Produces accurate, complete presets; handles the split-params architecture correctly | Requires careful merging logic; must handle kit row mapping | Medium |
| **B: Extract `<defaultParams>` only from instruments** | Simpler code — just copy the instrument element | Only works for orphaned instruments; active instruments have no `<defaultParams>` — **would produce incomplete, invalid presets** | Low (but broken) |
| **C: Re-save via Deluge firmware API** | Would produce perfectly valid presets | No such API exists; requires loading songs on the hardware | N/A |

Approach B is not viable for active instruments — it would produce synths without any parameter values. Approach A is the only viable path.

## Cross-Cutting Concerns

### Interactions with existing functionality

| Area | Impact |
|------|--------|
| **Sample references** | Extracted kits refer to sample paths hardcoded from the SD card layout (`SAMPLES/DRUMS/Kick/808 Kick.wav`). These paths are preserved as-is — the samples remain in the same location. |
| **Sync-to-SD workflow** | Extracted presets in `DELUGE/SYNTHS/SONG-SYNTHS/` and `DELUGE/KITS/SONG-KITS/` will be synced to the SD card by `sync_to_sd.py`. No changes needed to that script. |
| **verify_references.py** | Will find and check sample refs in extracted kit presets. No changes needed. |
| **fix_references.py** | Will update sample refs in extracted presets if samples are moved. No changes needed. |
| **Naming collisions** | Output goes to dedicated subdirectories (`SONG-SYNTHS/`, `SONG-KITS/`) so no risk of overwriting user presets. |
| **.env configuration** | Uses existing `DELUGE_ROOT` from `.env`. No new environment variables needed. |
| **deluge_sdk.py** | May benefit from new helper functions, or the extraction code may be self-contained. |
| **Comparison engine** | New `compare_instruments()` function is used by both extended mode (`select_extended_clips()`) and cross-song dedup (`deduplicate_results()`). Changes to comparison logic affect both features. |
| **Existing `compare_versions()` stub** | Will be replaced or refactored to use the generalised engine. The existing stub's 3-tier comparison design (Section 16.2) is preserved but applied to assembled presets rather than raw clips. |
| **`NormalisationConfig` pattern** | `ComparisonConfig` follows the same dataclass pattern. Both configs are instantiated in `extract_instruments.py` and passed to library functions. |

### Shared resources

- **lxml dependency** — already in pyproject.toml
- **XML parsing fallback** — `parse_deluge_xml()` handles edge cases; the extraction script should reuse this
- **scan_tree** — can be used to discover song XMLs; or `find_all_xml_files()` which already scans SONGS/

## Risk Analysis

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Extracted presets produce unexpected audio when loaded | Medium | Medium | Test by loading extracted presets on the Deluge hardware; compare with original song audio |
| Kit row drumIndex mismatch | Low | High | Validate drumIndex matches soundSources count; log warnings for mismatches |
| Special characters in names cause filesystem issues on Windows | Medium | Low | Sanitise filenames; replace/strip unsafe characters |
| Large song XMLs cause memory issues | Low | Low | lxml is efficient; songs are typically <1MB |
| Orphaned instruments produce incomplete/stale presets | Medium | Low | Optionally exclude orphaned instruments or flag them in output |
| Section-based version detection may not cover all edge cases | Medium | Medium | Start with simple first-clip-only mode; add comparison mode as extension |
| `.trash` replacement deletes user-modified files | Low | Medium | Only trash contents of `SONG-SYNTHS/` and `SONG-KITS/`; never touch user preset directories |
| Synth arpeggiator missed during extraction | Medium | High | Arpeggiator lives at clip level (`<instrumentClip>/<arpeggiator>`), not instrument level; extraction code must explicitly merge it from the clip. For orphans, synthesize a default. |
| Clips without `section` attribute | Low | Low | Some session clips may lack `section`; treat as section 0 or skip, with a logged warning |
| Clip arpeggiator extra attributes produce invalid standalone | Medium | Medium | Some clips have extra numeric attrs (`gate`, `rate`, etc.) on `<arpeggiator>` that standalone presets don't have. Strip these during extraction. |
| Element ordering mismatch in produced XML | Medium | Medium | Standalone and embedded instruments have different child element ordering (especially `<modKnobs>` position). Reorder according to the verified c1.2.1 standalone ordering documented in section 13 |
| Parameter automation curves in soundParams | Low | High | Extended hex strings encoding automation curves must be preserved verbatim — do not parse or truncate hex attribute values |
| Dedup false positives — genuinely different instruments rejected | Medium | Medium | Hard markers catch structural differences (oscillator type, sample file, patchCable routing). Soft marker thresholds are independently configurable. `--no-dedup` flag provides escape hatch. |
| Dedup false negatives — near-duplicates not caught | Low | Low | Impact is cosmetic (extra files in output). User can tune thresholds lower if needed. |
| Comparison performance on large kit presets | Low | Low | Kit comparison walks all `<soundSources>` children. With ~10 sounds per kit and ~20 presets to compare, this is ~200 sound-level comparisons — trivial for lxml. |
| Threshold tuning difficulty | Medium | Medium | Provide clear dedup reporting so the user can see which presets were kept/rejected and why. Start with documented defaults (3 params, 10% change) and iterate. |
| Non-deterministic dedup results | Low | High | Sort by song name before grouping ensures deterministic baseline selection. Document the ordering guarantee. |
| Extended mode + dedup interaction | Medium | Medium | Run extended selection first (intra-song), then dedup (inter-song). Test with `--extended --no-dedup` to verify each stage independently. |

## Recommendation

**Use Approach A: Merge instrument structure + clip params.** This is the only approach that produces valid presets.

Implement in three modes as proposed in the feature notes:

1. **Default mode** — extract one version per instrument per song: the first clip found (or the one with the lowest `section` id, favouring the default colour order where section 0 = light blue). Cross-song dedup is enabled by default, filtering near-duplicate instruments across songs.

2. **Extended mode** (`--extended` flag) — extract multiple versions if they differ sufficiently. Uses the generalised comparison engine with configurable thresholds. Cross-song dedup still applies after extended selection.

3. **No-dedup mode** (`--no-dedup` flag) — disables cross-song deduplication. Can be combined with `--extended` for maximum output (all versions from all songs).

**Comparison engine:** Build a single generalised comparison engine (`compare_instruments()`) that operates on assembled standalone presets. Configure via `ComparisonConfig` dataclass with hard markers, soft marker thresholds, and ignore list. Use for both intra-song (extended mode) and inter-song (dedup) comparison.

**Dedup strategy:** Group by `(preset_name, instrument_type)`, ignoring `preset_folder`. Use baseline + incremental acceptance algorithm (Section 17.2). Sort by song name for deterministic baseline selection.

**Filename convention:** `<SongName>-<PresetName>.XML` for default mode; `<SongName>-<PresetName>-<SectionId>.XML` (or `<SongName>-<PresetName>-<ColourName>.XML`) for extended mode. Sanitise for filesystem safety.

**Key implementation decisions:**
- Reuse `parse_deluge_xml()` from `deluge_sdk.py` for robust XML parsing
- Reuse `get_deluge_root()` from `cli_utils.py` for configuration
- Add a `pyproject.toml` entry point for the new script
- Follow existing patterns: dry-run preview, confirmation before writing, `.trash` for replaced files
- Produce c1.2.1 firmware-tagged XMLs using the attribute-style format

## Open Questions

1. **Should orphaned instruments (no clips, have `<defaultParams>`) be extracted?**
   - **Impact:** Determines whether the script extracts stale/unused instruments
   - **Recommendation:** Extract them with a flag or annotation in the filename (e.g. suffix `-orphaned`)
   - **Blocking:** No — can default to skipping and add later

2. **~~What `colourOffset` values correspond to the 12 named colours?~~ RESOLVED**
   - **Resolution:** `colourOffset` is a cosmetic pad hue, not a version identifier. The 12 colour versions are determined by `section` (0–11), which maps directly to the 12 launch row colours (section 0 = light blue, section 1 = pink, etc.). No empirical mapping of `colourOffset` is needed.
   - **Blocking:** No

3. **~~Should extracted presets that are identical to existing standalone presets be skipped?~~ PARTIALLY RESOLVED**
   - **Resolution:** Cross-song dedup (Section 17) handles this for instruments with the same `presetName` across songs. The comparison engine will detect if a song-embedded version is identical to the first-encountered version and filter duplicates. However, dedup does NOT compare against standalone presets in `SYNTHS/` or `KITS/` — it only compares extracted results against each other.
   - **Remaining question:** Should we also compare against existing standalone presets on disk? This would require loading and assembling standalone presets for comparison. Recommend deferring — the value is low since extracted presets go to separate `SONG-SYNTHS/` and `SONG-KITS/` directories.
   - **Blocking:** No

4. **~~What threshold defines "sufficiently different" for multi-version extraction?~~ RESOLVED**
   - **Resolution:** The generalised comparison engine (Section 16) uses a configurable `ComparisonConfig` with:
     - Hard markers (structural) → any difference = distinct (Section 16.2)
     - Soft markers → `DIFF_PARAM_COUNT_THRESHOLD = 3` params must differ by ≥ `DIFF_PARAM_PERCENT_THRESHOLD = 10%` each
     - Thresholds are independently configurable for intra-song and inter-song comparison
   - **Blocking:** No

5. **Should arrangement-only clips be included as extraction sources?**
   - **Impact:** Some instruments may only exist in the arrangement timeline
   - **Recommendation:** Start with session clips only; add arrangement support if needed
   - **Blocking:** No

6. **~~What is the correct element ordering within `<sound>` and `<kit>` elements?~~ RESOLVED**
   - **Resolution:** Verified from Init-Synth.XML and Init-Kit.XML (firmware c1.2.1):
     - **Standalone synth (`<sound>`):** `osc1`, `osc2`, `lfo1`, `lfo2`, (`modulator1`, `modulator2` for FM), `unison`, `defaultParams`, `arpeggiator`, `modKnobs`, `delay`, `sidechain`, `audioCompressor`
     - **Standalone kit (`<kit>`):** `defaultParams`, `delay`, `sidechain`, `audioCompressor`, `soundSources`, `selectedDrumIndex`
     - **Kit row sound:** `osc1`, `osc2`, `lfo1`, `lfo2`, `unison`, `defaultParams`, `arpeggiator`, `modKnobs`, `delay`, `sidechain`, `audioCompressor`
   - **Blocking:** No

7. **~~Should `<selectedDrumIndex>` be included in extracted kit presets?~~ RESOLVED**
   - **Resolution:** Yes. `<selectedDrumIndex>` is present in both standalone kit XMLs (e.g. Init-Kit.XML) AND song-embedded kit definitions (e.g. Ell.XML). Preserve the value from the song-embedded kit definition during extraction.
   - **Blocking:** No

8. **How should the `clipInstances` binary format be decoded if arrangement support is added?**
   - **Impact:** Needed for arrangement-only instrument extraction
   - **Recommendation:** Defer — not needed for session clips
   - **Blocking:** No

9. **Should instrument-level `<delay>`, `<sidechain>`, `<audioCompressor>` attributes be hard or soft markers?**
   - **Impact:** Determines whether changing delay sync level or compressor settings counts as a structural change or a numerical tweak
   - **Recommendation:** Treat as soft markers (Section 16.7) — these are tweakable numeric settings, not structural identity changes. However, some attributes (e.g. `<delay analog="0">` vs `analog="1"`) could be considered hard markers. Defer to implementation testing.
   - **Blocking:** No

10. **Should the `<osc1>/<osc2>` `transpose` and `cents` attributes be hard or soft markers?**
    - **Impact:** Changing oscillator transpose fundamentally changes the pitch/note of the instrument. A synth transposed down an octave sounds very different.
    - **Recommendation:** Treat `transpose` as a hard marker (integer semitone offset — changing it radically alters the instrument). Treat `cents` as a soft marker (fine tuning — small detuning adjustments).
    - **Blocking:** No

11. **Should dedup compare against existing standalone presets on disk (not just other extracted results)?**
    - **Impact:** Could avoid extracting instruments that already exist as standalone presets in `SYNTHS/` or `KITS/`
    - **Recommendation:** Defer — extracted presets go to separate directories (`SONG-SYNTHS/`, `SONG-KITS/`), so there is no naming collision. Adding disk comparison significantly increases scope and complexity (must handle firmware version differences between standalone and embedded).
    - **Blocking:** No

12. **What is the correct comparison granularity for kit `<soundSources>` ordering?**
    - **Impact:** If a user reorders rows in a kit (e.g. moves kick from position 0 to position 3), should this be treated as a hard marker?
    - **Recommendation:** Compare by sound `name` attribute rather than position index. If the same set of named sounds exists in different order, treat as equivalent for dedup purposes. If sounds are added or removed, that's a hard marker.
    - **Blocking:** No — can start with strict positional comparison and relax later

## References

### Project Files
- [Init-Synth.XML](DELUGE/SYNTHS/Init-Synth.XML) — Reference standalone synth format with default parameter values
- [Init-Kit.XML](DELUGE/KITS/Init-Kit.XML) — Reference standalone kit format with default parameter values
- [Deeper.XML](DELUGE/KITS/KERERU/Deeper.XML) — Example standalone kit with samples, for comparison with Ell.XML embedded version
- [K01Bass.XML](DELUGE/SYNTHS/KERERU/K01Bass.XML) — Example standalone synth (older firmware version 4.0.1)
- [Bloop.XML](DELUGE/SONGS/Bloop.XML) — Example song with synths and a kit
- [K01Sink.XML](DELUGE/SONGS/K01Sink.XML) — Example song with multiple instruments, multiple clip colours, MIDI, and audio tracks
- [Ell.XML](DELUGE/SONGS/Ell.XML) — Example song with a kit clip showing noteRow/drumIndex/soundParams structure
- [Arpo.XML](DELUGE/SONGS/Arpo.XML) — Example song with an orphaned instrument containing `<defaultParams>`
- [extraction.py](scripts/deluge_lib/extraction.py) — Core extraction logic including `compare_versions()` stub, `ComparisonConfig` constants, `NormalisationConfig`, and all transformation functions
- [extract_instruments.py](scripts/extract_instruments.py) — Main CLI script showing the extraction flow where dedup would be inserted
- [deluge_sdk.py](scripts/deluge_lib/deluge_sdk.py) — XML parsing, file discovery, sample reference extraction
- [cli_utils.py](scripts/deluge_lib/cli_utils.py) — Environment loading, interactive confirmation
- [scanning.py](scripts/deluge_lib/scanning.py) — Directory scanning, path normalisation
- [pyproject.toml](scripts/pyproject.toml) — Project dependencies, entry points, tool configuration
- [.env.example](scripts/.env.example) — Environment variable template
- [glossary.md](docs/glossary.md) — Deluge terminology definitions
- [scripts-plan.md](docs/scripts-plan.md) — Planned scripts overview and safety matrix

### External Resources
- No external resources were consulted. All findings are from direct analysis of the repository contents.

## Next Steps

1. Review this document and resolve any remaining open questions
2. Invoke the Plan agent to create/update the feature plan incorporating the comparison engine and dedup
3. Implement `ComparisonConfig` dataclass and `compare_instruments()` function
4. Implement `deduplicate_results()` function and integrate into `extract_instruments.py`
5. Refactor `compare_versions()` and `select_extended_clips()` stubs to use the generalised engine
6. Add `--no-dedup` CLI flag
7. Test with actual song data to tune thresholds
