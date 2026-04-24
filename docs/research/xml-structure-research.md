# Deluge XML Structure Reference

> **Document Type:** Living Reference
> **Created:** 24 April 2026
> **Firmware:** `c1.2.1` (Community Firmware)
> **Sources:** Init-Synth.XML, Init-Kit.XML, Duppy test series, Triggy test series, real song data

## 1. Executive Summary

This document is an ongoing reference for understanding how the Deluge hardware represents musical data in XML. It documents the structure of song, synth, and kit XMLs; how edits made on the hardware are reflected in the data; and the encoding schemes used for parameter values.

The primary use case is supporting scripts that read, analyse, or transform Deluge XML data — particularly the `extract_instruments.py` script and any future tools that need to understand the relationship between instruments, clips, and parameters.

All findings are based on firmware `c1.2.1` XML output. Earlier firmware versions use different XML structures and are out of scope.

---

## 2. Song XML Structure Overview

A song XML has the root element `<song>` with the following high-level structure:

```xml
<song firmwareVersion="c1.2.1" ...>
    <modeNotes>...</modeNotes>
    <reverb>...</reverb>
    <delay>...</delay>
    <sidechain>...</sidechain>
    <audioCompressor>...</audioCompressor>
    <songParams>...</songParams>
    <instruments>
        <!-- All instrument definitions (synths, kits, MIDI, audio) -->
    </instruments>
    <sections>
        <section id="0" numRepeats="0" />
        ...
        <section id="11" numRepeats="0" />
    </sections>
    <sessionClips>
        <!-- All session-view clips -->
    </sessionClips>
    <arrangementOnlyClips>
        <!-- Arranger-specific "white" clips (if any) -->
    </arrangementOnlyClips>
    <scales>...</scales>
</song>
```

**Key relationships:**

| Element | Contains | Role |
|---|---|---|
| `<instruments>` | `<sound>` (synths), `<kit>` (kits) | Structural instrument definitions — oscillators, samples, effects routing |
| `<sessionClips>` | `<instrumentClip>` | Per-clip parameters, note data, automation |
| `<arrangementOnlyClips>` | `<instrumentClip>` | Arranger-specific clips not visible in session view |
| `<sections>` | `<section id="0">`–`<section id="11">` | 12 sections, each with a repeat count |

Clips reference instruments by name/folder pair. The instrument definition is shared across all clips that use it. [Verified]

---

## 3. Instrument Definitions (`<instruments>`)

### Synths (`<sound>`)

Synths appear as `<sound>` elements directly inside `<instruments>`:

```xml
<instruments>
    <sound
        presetName="Init-Synth"
        presetFolder="SYNTHS"
        defaultVelocity="64"
        isArmedForRecording="0"
        activeModFunction="1"
        colour="0"
        polyphonic="poly"
        voicePriority="1"
        mode="subtractive"
        modFXType="none"
        lpfMode="24dB"
        hpfMode="HPLadder"
        filterRoute="H2L"
        maxVoices="8">
        <osc1 type="saw" transpose="0" cents="0" retrigPhase="-1" />
        <osc2 type="square" transpose="0" cents="0" retrigPhase="-1" />
        <lfo1 type="triangle" syncLevel="0" syncType="0" />
        <lfo2 type="triangle" syncLevel="0" syncType="0" />
        <unison num="1" detune="8" spread="0" />
        <modKnobs>...</modKnobs>
        <delay ... />
        <sidechain ... />
        <audioCompressor ... />
    </sound>
</instruments>
```

**Key attributes:**

| Attribute | Values | Notes |
|---|---|---|
| `presetName` | String | Name shown on the Deluge display |
| `presetFolder` | `"SYNTHS"`, `"SYNTHS/subfolder"` | Path relative to `DELUGE/` |
| `mode` | `"subtractive"`, `"fm"`, `"ringmod"` | Synthesis mode |
| `polyphonic` | `"poly"`, `"mono"`, `"legato"` | Voice mode |
| `osc1.type` / `osc2.type` | `"saw"`, `"square"`, `"sine"`, `"triangle"`, `"sample"`, `"wavetable"` | Oscillator type |

**Note:** The instrument definition in a song does NOT contain `<defaultParams>`. Tunable parameters live in the clip's `<soundParams>`. Standalone preset XMLs (in `SYNTHS/`) use `<defaultParams>` instead. [Verified]

### Kits (`<kit>`)

Kits appear as `<kit>` elements inside `<instruments>`:

```xml
<instruments>
    <kit
        presetName="Init-Kit"
        presetFolder="KITS"
        defaultVelocity="64"
        ...
        modFXType="none"
        lpfMode="24dB"
        hpfMode="HPLadder"
        filterRoute="H2L">
        <delay ... />
        <sidechain ... />
        <audioCompressor ... />
        <soundSources>
            <sound name="HR16B Block" ... >
                <osc1 type="sample" fileName="SAMPLES/DRUMS/Block/HR16B Block.wav">
                    <zone startSamplePos="0" endSamplePos="5088" />
                </osc1>
                ...
            </sound>
            <sound name="R-50 Agog" ... >
                ...
            </sound>
        </soundSources>
        <selectedDrumIndex>1</selectedDrumIndex>
    </kit>
</instruments>
```

**Kit `<soundSources>` structure:**
- Each `<sound>` within `<soundSources>` represents one row/sample in the kit
- Sounds are indexed by position (0-based) — this is the `drumIndex` used by clips
- Each sound has its own `<osc1>`, `<osc2>`, `<lfo1>`, `<lfo2>`, `<unison>`, `<modKnobs>`, `<arpeggiator>`, `<delay>`, `<sidechain>`, `<audioCompressor>`
- The `name` attribute is the display name for the row (e.g. `"HR16B Block"`, `"KICK"`)
- The `path` attribute on kit sounds is typically empty (`path=""`)

**Critical finding:** Instrument definitions are immutable once loaded into a song. Edits on the Deluge only change clip-level parameters — the `<instruments>` section is never modified after initial load. Deleting rows from a clip does NOT remove sounds from `<soundSources>`. [Verified — Duppy series]

---

## 4. Session Clips (`<sessionClips>`)

### `<instrumentClip>` structure

```xml
<instrumentClip
    clipName=""
    inKeyMode="1"
    yScroll="-2"
    yScrollKeyboard="50"
    affectEntire="0"
    instrumentPresetName="Init-Kit"
    instrumentPresetFolder="KITS"
    isPlaying="1"
    isSoloing="0"
    isArmedForRecording="1"
    length="384"
    colourOffset="-60"
    section="0"
    selected="1"
    keyboardLayout="0"
    ...>
```

**Instrument referencing:** Clips link to instruments via `instrumentPresetName` + `instrumentPresetFolder`. Multiple clips can reference the same instrument (different sections/colours). [Verified]

### Section IDs and Colours

Sections are numbered 0–11. The `colourOffset` attribute on clips controls the visual colour but is separate from the section ID. The default clip colour order when creating new clips for the same instrument:

| Order | Colour | Notes |
|---|---|---|
| 1 | Light blue | Default for first clip |
| 2 | Pink | |
| 3 | Gold | |
| 4 | Cyan | |
| 5 | Red | |
| 6 | Yellow | |
| 7 | Dark blue | |
| 8 | Orange | |
| 9 | Purple | |
| 10 | Yellowy-green | |
| 11 | Green | |
| 12 | Lighter-purple | |

Each new clip is placed in the next available section by default.

### Synth clip parameters (`<soundParams>`)

Synth clips contain `<soundParams>` — the per-clip tuneable parameter values:

```xml
<soundParams
    arpeggiatorGate="0x00000000"
    portamento="0x80000000"
    compressorShape="0xDC28F5B2"
    oscAVolume="0x7FFFFFFF"
    ...
    volume="0x4CCCCCA8"
    pan="0x00000000"
    lpfFrequency="0x7FFFFFFF"
    lpfResonance="0x80000000"
    ...>
    <envelope1 attack="0x80000000" decay="0xE6666654" sustain="0x7FFFFFFF" release="0x80000000" />
    <envelope2 ... />
    <patchCables>
        <patchCable source="velocity" destination="volume" amount="0x3FFFFFE8" />
        ...
    </patchCables>
    <equalizer ... />
</soundParams>
```

**Note:** `<soundParams>` in a song clip is structurally equivalent to `<defaultParams>` in a standalone preset. Extraction requires renaming the tag. [Verified]

### Kit clip parameters (`<kitParams>`)

Kit clips contain `<kitParams>` at the clip level (global kit parameters) and per-row `<soundParams>` inside each `<noteRow>`:

```xml
<kitParams
    reverbAmount="0x80000000"
    volume="0x3504F334"
    pan="0x00000000"
    ...>
    <delay rate="0x00000000" feedback="0x80000000" />
    <lpf frequency="0x7FFFFFFF" resonance="0x80000000" />
    <hpf frequency="0x80000000" resonance="0x80000000" />
    <equalizer ... />
</kitParams>
```

### Kit `<noteRows>` — drumIndex mapping

For kit clips, `<noteRows>` contains one `<noteRow>` per kit row in the clip. Each row maps to a sound in `<soundSources>` via `drumIndex`:

```xml
<noteRows>
    <noteRow
        colourOffset="30"
        drumIndex="0">
        <soundParams
            arpeggiatorGate="0x00000000"
            ...
            volume="0x4CCCCCA8"
            pan="0x00000000"
            ...>
            <envelope1 ... />
            <envelope2 ... />
            <patchCables>...</patchCables>
            <equalizer ... />
        </soundParams>
    </noteRow>
    <noteRow
        colourOffset="48"
        drumIndex="1">
        <soundParams ...>...</soundParams>
    </noteRow>
</noteRows>
```

- `drumIndex="0"` → first `<sound>` in `<soundSources>`
- `drumIndex="1"` → second `<sound>` in `<soundSources>`
- A clip may reference only a subset of the kit's sounds
- Note data (sequencing) appears as `noteDataWithLift` attribute on the `<noteRow>` element

[Verified — Duppy series]

---

## 5. Arrangement Clips (`<arrangementOnlyClips>`)

Arranger-specific clips ("white clips") are stored in `<arrangementOnlyClips>`, not `<sessionClips>`. These clips are created when the user adds content directly in the arranger view without first creating a session clip.

**Key behaviours (from Triggy series):**

- Creating a white clip for an existing instrument adds a clip to `<arrangementOnlyClips>` referencing the same instrument in `<instruments>` [Verified — Triggy v4]
- Converting a white clip to coloured moves the clip from `<arrangementOnlyClips>` to `<sessionClips>` [Verified — Triggy v6/v7]
- Instruments unique to the arranger view (created only via white clips) appear in `<instruments>` but have no matching `<sessionClips>` entry — they appear orphaned from the session perspective [Verified — Triggy v5]
- Deleting white clips from the arranger does not remove the instrument from `<instruments>` [Verified — Triggy v13]

**Note:** The `<arrangementOnlyClips>` element may be absent entirely if the song has no arranger-specific clips. [Expected]

---

## 6. Hex Parameter Value Mapping

Most tuneable parameters use a signed 32-bit integer encoded as a hex string (e.g. `"0x80000000"`).

### Range

| Hex | Decimal | Meaning |
|---|---|---|
| `0x80000000` | −2,147,483,648 | Minimum (floor) |
| `0x00000000` | 0 | Centre / zero |
| `0x7FFFFFFF` | +2,147,483,647 | Maximum (ceiling) |

### Mapping schemes

**0–50 parameters** (e.g. volume, resonance, LPF frequency, HPF frequency, reverb amount):

| Display Value | Hex | Decimal |
|---|---|---|
| 0 | `0x80000000` | −2,147,483,648 |
| 25 | `0x00000000` | 0 |
| 50 | `0x7FFFFFFF` | +2,147,483,647 |

**−50 to +50 parameters** (e.g. pan, patchCable amounts, modulation depths):

| Display Value | Hex | Decimal |
|---|---|---|
| −50 | `0x80000000` | −2,147,483,648 |
| 0 | `0x00000000` | 0 |
| +50 | `0x7FFFFFFF` | +2,147,483,647 |

### Reference values from test data

Collected from Init-Synth defaults and Triggy v15/v16 where known display values were set:

| Parameter | Display | Hex | Context |
|---|---|---|---|
| volume (init synth) | ~35 | `0x4CCCCCA8` | Init-Synth default |
| volume (init kit) | ~27 | `0x3504F334` | Init-Kit default |
| pan (centre) | 0 | `0x00000000` | Init default |
| pan (max right) | +25 | `0x7FFFFFFF` | Triggy v15 |
| pan (max left) | −25 | `0x80000000` | Triggy v16 |
| lpfFrequency (max) | 50 | `0x7FFFFFFF` | Init default (fully open) |
| lpfResonance (min) | 0 | `0x80000000` | Init default |
| hpfFrequency (min) | 0 | `0x80000000` | Init default |
| hpfFrequency (25) | 25 | `0xFE000000` | Triggy v16 |
| oscAVolume (max) | 50 | `0x7FFFFFFF` | Init default |
| oscBVolume (min) | 0 | `0x80000000` | Init default |
| sidechain→level (+30) | +30 | `0x26000000` | Triggy v15 |
| sidechain→level (−49) | −49 | `0xC1800000` | Triggy v16 |
| LFO→LPF (+40) | +40 | `0x33333333` | Triggy v15 |
| LFO→LPF (−50) | −50 | `0xC0000000` | Triggy v16 |
| compressorShape | — | `0xDC28F5B2` | Init default (both synths and kits) |

### Automation encoding

When a parameter is automated, the base value is followed by keyframe pairs. The exact binary encoding of keyframes within the hex blob is not yet fully documented. [Expected]

---

## 7. Non-Hex Parameter Values

Some attributes use plain integers rather than hex encoding:

| Parameter | Element | Range | Notes |
|---|---|---|---|
| `transpose` | `<osc1>`, `<osc2>` | −96 to +96 | Display value = XML value directly |
| `cents` | `<osc1>`, `<osc2>` | −50 to +50 | Display value = XML value directly |
| `num` | `<unison>` | 1–8 | Number of unison voices |
| `detune` | `<unison>` | 0–50 | Unison detune amount |
| `spread` | `<unison>` | 0–50 | Unison stereo spread |
| `syncLevel` | `<lfo1>`, `<delay>`, `<sidechain>` | Integer | Sync division level |
| `syncType` | `<lfo1>`, `<delay>`, `<sidechain>` | Integer | Sync type selector |
| `attack` | `<sidechain>` | Integer | e.g. `327244` |
| `release` | `<sidechain>` | Integer | e.g. `936` |
| `attack` | `<audioCompressor>` | Integer | e.g. `83886080` |
| `release` | `<audioCompressor>` | Integer | e.g. `83886080` |
| `thresh` | `<audioCompressor>` | Integer | e.g. `0` |
| `ratio` | `<audioCompressor>` | Integer | e.g. `1073741824` |
| `loopMode` | `<osc1>`, `<osc2>` | `0`, `1` | 0 = cut, 1 = loop |
| `retrigPhase` | `<osc1>`, `<osc2>` | Integer | −1 = off |

**Verified examples:**
- Triggy v15: `osc1 transpose="96"`, `osc2 transpose="40"` (display 96, 40) [Verified]
- Triggy v16: `osc1 transpose="-96"`, `osc2 transpose="-40"` (display −96, −40) [Verified]

---

## 8. PatchCables

PatchCables define modulation routing between sources and destinations. They appear inside `<patchCables>` within `<soundParams>` (clips) or `<defaultParams>` (presets):

```xml
<patchCables>
    <patchCable
        source="velocity"
        destination="volume"
        amount="0x3FFFFFE8" />
    <patchCable
        source="aftertouch"
        destination="volume"
        amount="0x2A3D7094" />
    <patchCable
        source="y"
        destination="lpfFrequency"
        amount="0x19999990" />
    <patchCable
        source="compressor"
        destination="volumePostReverbSend"
        amount="0x26000000" />
</patchCables>
```

### Amount encoding

The `amount` attribute uses the full signed 32-bit hex range:

- `0x00000000` = no modulation (zero)
- Positive values = positive modulation
- Negative values (e.g. `0xC0000000`, `0xC1800000`) = inverted modulation

### Nested `<depthControlledBy>`

PatchCable amounts can themselves be modulated by another source via `<depthControlledBy>`:

```xml
<patchCable
    source="lfo2"
    destination="lpfFrequency"
    amount="0x051EB851">
    <depthControlledBy>
        <patchCable
            source="envelope2"
            amount="0x11EB851E" />
    </depthControlledBy>
</patchCable>
```

This means "LFO2 modulates LPF frequency, but the depth of that modulation is itself controlled by Envelope 2." [Verified — Triggy 13]

### Key routing: sidechain ducking

A patchCable with `source="compressor"` and `destination="volumePostReverbSend"` represents sidechain ducking — the compressor signal reduces the output volume. This is how synths/kits "duck" when the sidechain kick triggers:

```xml
<patchCable
    source="compressor"
    destination="volumePostReverbSend"
    amount="0x01000000" />
```

[Verified — Triggy 7, 15, 16, 18]

---

## 9. "No Sound" Rows

"No sound" rows appear when the user adds a new row to a kit clip but does not load a sample into it. In the XML, they appear as a minimal `<noteRow>` with only a `colourOffset` attribute and no `drumIndex`:

```xml
<noteRow
    colourOffset="27" />
```

**Key characteristics:**
- No `drumIndex` attribute — the row is not linked to any sound in `<soundSources>`
- No `<soundParams>` child element
- Clip-level only — no corresponding entry exists in the instrument's `<soundSources>`
- Can appear at any position in the `<noteRow>` list (beginning, middle, or end)
- Created by adding a row without assigning a sample [Verified — Duppy v2]
- Deleting a "no sound" row simply removes the `<noteRow>` element [Verified — Duppy v3]

---

## 10. Muted Rows and Notes

The `muted="1"` attribute can appear on `<noteRow>` elements to indicate a row is muted in that clip:

```xml
<noteRow
    muted="1"
    colourOffset="67"
    drumIndex="0">
    <soundParams
        arpeggiatorGate="0x00000000"
        ...>
        ...
    </soundParams>
</noteRow>
```

**Key characteristics:**
- `muted="1"` is a clip-specific state — the same sound may be muted in one clip and active in another
- Muted rows retain their full `<soundParams>` and `drumIndex` — no data is lost
- Muting does not affect preset extraction — parameters are preserved regardless of mute state
- Rows without `muted` attribute (or `muted="0"`) are active

[Verified — Duppy v8/v9 for kit rows, Triggy v17 for synth note rows]

---

## 11. Kit Sound Lifecycle

Based on the Duppy test series, the following lifecycle events have been confirmed:

| Action on Deluge | Effect on `<instruments>` | Effect on `<sessionClips>` |
|---|---|---|
| Load a kit preset | Full `<soundSources>` created with all sounds | `<noteRows>` created for all sounds with `drumIndex` references |
| Add a "no sound" row | No change | New `<noteRow>` with `colourOffset` only (no `drumIndex`) added |
| Delete a "no sound" row | No change | `<noteRow>` removed |
| Delete a sound row from clip | No change — sound remains in `<soundSources>` | `<noteRow>` for that `drumIndex` removed |
| Delete ALL rows from clip | No change — all sounds remain in `<soundSources>` | All `<noteRow>` elements removed |
| Delete all clips for an instrument | No change — instrument persists in `<instruments>` (orphaned) | All `<instrumentClip>` elements for that instrument removed |
| Create new clip for same instrument | No change | New `<instrumentClip>` with fresh `<noteRows>` for all sounds |
| Different clips reference same kit | Single shared instrument definition | Each clip has its own subset of `<noteRow>` elements |

**The core principle:** `<soundSources>` in the instrument definition is immutable after initial load. All user edits to rows are reflected only at the clip level via `<noteRow>` additions and removals. [Verified — Duppy v1 through v10]

---

## 12. Sidechain Kit Patterns

Based on Triggy v18/v19 analysis, sidechain-only kits follow a recognisable pattern.

### Sidechain sender identification

A kit is functioning as a sidechain trigger (not a full drum kit) when:

1. **Only 1 row has note data** — the `noteDataWithLift` attribute is present on only one `<noteRow>` (the kick trigger)
2. **That row's sound has `sideChainSend` at or near maximum** — `sideChainSend="2147483647"` (= `0x7FFFFFFF`) on the `<sound>` element in `<soundSources>`
3. **Kit or row volume is very low** — the kick sound is not intended to be audible
4. **Dedicated sidechain kits may have only 1 sound** — e.g. Triggy v19 creates a purpose-built sidechain kit with a single KICK sound

```xml
<!-- Sidechain kit sound with max sideChainSend -->
<sound
    name="KICK"
    polyphonic="auto"
    sideChainSend="2147483647"
    mode="subtractive"
    ...>
    <osc1
        type="sample"
        fileName="SAMPLES/DRUMS/Kick/808 Kick.wav">
        <zone startSamplePos="0" endSamplePos="22051" />
    </osc1>
    ...
</sound>
```

Note: `sideChainSend` is a plain integer (decimal), not hex-encoded. The value `2147483647` is the maximum (`0x7FFFFFFF` interpreted as unsigned). [Verified — Triggy 18, 19]

### Sidechain receiver identification

A synth or kit receives sidechain ducking when it has a patchCable with:

```xml
<patchCable
    source="compressor"
    destination="volumePostReverbSend"
    amount="0x..." />
```

The `amount` controls how much ducking is applied. This patchCable appears at the clip level in `<soundParams>`, not on the instrument definition. [Verified — Triggy 7, 15, 16]

---

## 13. Preset Changes and Identity

Based on Triggy v8/v9 analysis:

- **Changing a preset** on the Deluge creates a **new instrument definition** in `<instruments>`. The old definition is not updated — it may become orphaned if no other clips reference it. [Verified — Triggy v8]
- The clip's `instrumentPresetName` is updated to the new preset name. [Verified — Triggy v9]
- **Renaming a preset** (e.g. `"000"` → `"000 TR-808"`) means songs saved before and after the rename have different `instrumentPresetName` values for what is logically the same base preset. This is important for cross-song deduplication. [Verified]
- When a preset change is made in one clip, it affects the single instrument definition shared by all clips referencing that preset. All clips then reference the new instrument. [Verified — Triggy v8/v9]

---

## 14. Test XML Reference

Two test series exist in `DELUGE/SONGS/testing/` designed to systematically exercise XML edge cases.

### Duppy series

Tests kit-specific behaviours: row addition, deletion, "no sound" rows, muting, orphaned instruments.

| Version | Description | Key XML Feature Tested |
|---|---|---|
| Duppy | New song, Init-Kit loaded, 2 samples assigned (HR16B Block, R-50 Agog) | Baseline kit with 2 sounds |
| Duppy 2 | Added "no sound" row (no sample assigned) | `<noteRow>` without `drumIndex` |
| Duppy 3 | Deleted the "no sound" row | "No sound" row removal |
| Duppy 4 | No changes to Init-Kit; loaded additional kit "000 TR-808" | Second instrument in `<instruments>` |
| Duppy 5 | Duplicated clips to new sections; loaded kits with slices and samples; loaded Deeper | Multi-section clips, multiple kits |
| Duppy 6 | Added "no sound" rows to various kits (different positions) | "No sound" rows across multiple kits |
| Duppy 7 | Created section 3 clips for all instruments | Additional sections |
| Duppy 8 | Deleted rows from section 3 clips (various patterns) | Row deletion — `<noteRow>` removed, `<soundSources>` unchanged |
| Duppy 9 | Loaded Analog Machine kit; added sequencing; muted rows | Muted rows (`muted="1"`), sequencing data |
| Duppy 10 | Deleted all clips except Analog Machine | Orphaned instruments in `<instruments>` |

### Triggy series

Tests synth behaviours, arranger clips, preset changes, parameter values, sidechain patterns.

| Version | Description | Key XML Feature Tested |
|---|---|---|
| Triggy | New song, Init-Synth loaded, waveform changed, basic sequencing | Baseline synth |
| Triggy 2 | Multiple sections/variations for synth; added kit clip | Multi-section synth clips |
| Triggy 3 | Added arranger info using existing clips | Arranger references |
| Triggy 4 | Added white clips in arranger (synth + kit) | `<arrangementOnlyClips>` |
| Triggy 5 | New instrument unique to arranger view | Arranger-only instrument (orphaned from session) |
| Triggy 6 | Converted white clips to coloured (original synth + kit) | Clip migration to `<sessionClips>` |
| Triggy 7 | Converted white clips for arranger-only instrument | Arranger→session migration |
| Triggy 8 | Changed preset in arranger view | Preset change creates new instrument definition |
| Triggy 9 | Changed preset in song view (bassdirtyswell) | Preset change updates `instrumentPresetName` |
| Triggy 10 | Multiple clips for one instrument in same section | Duplicate clips per section |
| Triggy 11 | Deleted most clips; heavily edited one section | Divergent clip parameters |
| Triggy 12 | Separated bassdirtyswell into own section | Section reorganisation |
| Triggy 13 | Deleted arranger-only clips for removed instruments | `<depthControlledBy>` example present |
| Triggy 14 | Deleted arranger instruments; converted remaining white clips | Cleanup of arranger data |
| Triggy 15 | Loaded Init-Synth with known parameter values: sidechain→level=30, pan=25, osc1 transpose=96, osc2 transpose=40, LFO→LPF=40 | Hex↔display value reference (positive) |
| Triggy 16 | Section 1 with inverted values: sidechain→level=−49, pan=−25, osc1 transpose=−96, osc2 transpose=−40, LFO→LPF=−50, HPF cutoff=25 | Hex↔display value reference (negative) |
| Triggy 17 | Muted notes in synth clips; added kit with sequencing | `muted="1"` on synth `<noteRow>` elements |
| Triggy 18 | Muted kit rows; loaded TR-808 and configured as sidechain-only | `muted="1"` on kit rows, `sideChainSend` pattern |
| Triggy 19 | Created dedicated sidechain kit (single KICK sound) | Minimal sidechain kit — 1 sound in `<soundSources>` |
