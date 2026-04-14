# Research: Extract Instruments from Songs

> **Document Type:** Research
> **Date:** 14 April 2026
> **Request:** Build a script that analyses all saved songs on the Deluge SD card backup and extracts embedded kit and synth instruments as standalone preset XMLs in `DELUGE/SYNTHS/SONG-SYNTHS/` and `DELUGE/KITS/SONG-KITS/`.
> **Pipeline:** Research → Plan → Implement

## Executive Summary

Song XMLs on the Deluge store complete copies of every instrument used, but the instrument parameters are split between two locations: the structural definition lives in the `<instruments>` section and the tuneable parameters live in clip-level `<soundParams>` or `<kitParams>` blocks. For synths, the `<arpeggiator>` element also lives at the clip level rather than the instrument level. Extracting a standalone preset requires merging these sources, renaming the clip params tag to `<defaultParams>`, and inserting the clip-level arpeggiator into the correct position. The existing codebase provides strong patterns for XML parsing, `.env` configuration, and cross-platform file handling via `lxml`, `pathlib`, and `python-dotenv`. All 58 songs use firmware `c1.2.1`, which simplifies extraction to a single format target.

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
| Multi-version selection by colour | Cross-song deduplication |
| Firmware version safety check (`c1.2.1`) | Support for firmware versions other than `c1.2.1` |
| Trash-and-replace existing extractions | Song XML modification |

## Existing Assets Analysis

| Capability | Status | Location | Notes |
|------------|--------|----------|-------|
| XML parsing with lxml | ✅ Ready | [deluge_sdk.py](scripts/deluge_lib/deluge_sdk.py) | Three-stage fallback parser (`_parse_deluge_xml`), handles multi-root and malformed XML |
| XML file discovery | ✅ Ready | [deluge_sdk.py](scripts/deluge_lib/deluge_sdk.py) | `find_all_xml_files()` scans KITS/, SYNTHS/, SONGS/ |
| Sample reference extraction | ✅ Ready | [deluge_sdk.py](scripts/deluge_lib/deluge_sdk.py) | `extract_sample_refs()` with preset name lookup logic |
| .env configuration | ✅ Ready | [cli_utils.py](scripts/deluge_lib/cli_utils.py) | `get_deluge_root()` loads DELUGE_ROOT from `scripts/.env` |
| File scanning/filtering | ✅ Ready | [scanning.py](scripts/deluge_lib/scanning.py) | `scan_tree()` with `.trash` skipping, case normalisation |
| Interactive confirmation | ✅ Ready | [cli_utils.py](scripts/deluge_lib/cli_utils.py) | `confirm_apply()` for destructive operations |
| Instrument structure extraction | ❌ Missing | — | No existing code to extract instrument definitions from songs |
| Clip → instrument matching | ❌ Missing | — | No existing code linking clips to their instrument entries |
| Standalone XML generation | ❌ Missing | — | No existing code to produce standalone synth/kit XMLs |
| Parameter comparison/diffing | ❌ Missing | — | No existing code for comparing instrument parameter sets |
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
| lxml for XML parsing | `_parse_deluge_xml()` in [deluge_sdk.py](scripts/deluge_lib/deluge_sdk.py) | Three-stage fallback (strict → synthetic root → recover) |
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

The first 14 knobs are largely standard. Positions 3–4 and 15–16 get customized based on synth mode:

| Knob Positions | Default (subtractive) | FM synth example |
|---|---|---|
| 3–4 | `lpfResonance`, `lpfFrequency` | `modulator1Volume`, `modulator1Feedback` |
| 15–16 | `bitcrushAmount`, `sampleRateReduction` | `modulator2Volume`, `carrier1Feedback` |

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

### Shared resources

- **lxml dependency** — already in pyproject.toml
- **XML parsing fallback** — `_parse_deluge_xml()` handles edge cases; the extraction script should reuse this
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

## Recommendation

**Use Approach A: Merge instrument structure + clip params.** This is the only approach that produces valid presets.

Implement in two modes as proposed in the feature notes:

1. **Default mode** — extract one version per instrument per song: the first clip found (or the one with the lowest `section` id, favouring the default colour order where section 0 = light blue). Simple, produces a clean set of presets.

2. **Extended mode** (`--all-versions` or similar flag) — extract multiple versions if they differ sufficiently. This requires a parameter comparison engine, which adds complexity. Recommend deferring the differencing logic to a later iteration and starting with the simpler "first version only" default.

**Filename convention:** `<SongName>-<PresetName>.XML` for default mode; `<SongName>-<PresetName>-<SectionId>.XML` (or `<SongName>-<PresetName>-<ColourName>.XML`) for extended mode. Sanitise for filesystem safety.

**Key implementation decisions:**
- Reuse `_parse_deluge_xml()` from `deluge_sdk.py` for robust XML parsing
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

3. **Should extracted presets that are identical to existing standalone presets be skipped?**
   - **Impact:** Avoids duplicating presets already in `SYNTHS/` or `KITS/`
   - **Recommendation:** Defer to planning — cross-referencing requires parameter comparison
   - **Blocking:** No

4. **What threshold defines "sufficiently different" for multi-version extraction?**
   - **Impact:** Core to the extended mode's version selection logic
   - **Recommendation:** Defer to planning — needs experimentation with actual song data
   - **Blocking:** No — default mode extracts only one version

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
2. Review `temp/extraction-questions.md` for additional clarifying questions
3. Invoke the Plan agent to create a feature plan from this research
