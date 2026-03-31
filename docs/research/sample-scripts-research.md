# Research: Sample Management Scripts

> **Document Type:** Research
> **Date:** 31 March 2026
> **Request:** Design and build a suite of modular sample management scripts for the Deluge SD card backup repository — including a sample manifest generator, hash-based reference fixer, and reference verifier — with a shared XML parsing library.
> **Pipeline:** Research → Plan → Implement

## Executive Summary

This research analyses the Deluge XML format landscape, audio metadata extraction options, and architectural patterns for a suite of sample management scripts. The XML analysis reveals two distinct format eras (element-style and attribute-style) plus a critical third reference type (`filePath` on audio clips) that parsing must cover. SHA256 hashing is confirmed as the correct approach for migration mapping at the expected scale (~1000 files). The recommended architecture is a Python-based modular system with a shared `deluge_sdk` library, individual scripts per function, and bash/Makefile orchestration.

## Objectives

- Document all XML formats and sample reference patterns across firmware versions
- Determine the complete set of attributes/elements that reference sample files
- Evaluate audio metadata extraction libraries for `.wav` duration/properties
- Validate the SHA256 hashing approach for file migration mapping
- Design a keyword/category inference strategy from paths and filenames
- Define the dry-run + confirm CLI workflow pattern
- Recommend a module structure for `scripts/`

## Feature Overview

### Purpose and Value

The user maintains a Deluge SD card backup in `DELUGE/` and wants to reorganise their `DELUGE/SAMPLES/` directory — moving, renaming, creating new folder structures, and deleting unused samples. This reorganisation breaks all hardcoded sample references in XML preset files. The scripts provide:

1. **Decision support** — a manifest to understand what samples exist, where they're used, and what can be safely deleted
2. **Automated reference fixing** — hash-based detection of moved/renamed files with automatic XML path updates
3. **Verification** — confidence that all references are valid before deploying back to the physical SD card

### Primary Use Cases

1. **Pre-reorganisation**: Generate manifest → review what's in use → decide what to move/rename/delete
2. **Post-reorganisation**: Snapshot before → rearrange manually → diff → fix references → verify
3. **Ad-hoc verification**: Quick check that all XML references point to existing files

### Inputs and Outputs

| Script | Inputs | Outputs |
|--------|--------|---------|
| Sample Manifest | `DELUGE/SAMPLES/**/*.wav`, all XMLs | `docs/manifests/sample-manifest-<date>.json` + `.csv` |
| Reference Fixer | Before/after hash snapshots, all XMLs | Modified XML files (with dry-run preview) |
| Reference Verifier | `DELUGE/SAMPLES/`, all XMLs | Report of broken references |
| Sample Usage Utility | Sample name/path, all XMLs | Detailed usage information for a single sample |

### Scope

**In scope:**
- Scripts operate on the local `DELUGE/` directory in this repository only
- XML parsing for KITS/, SYNTHS/, SONGS/ (including all subdirectories, recursively)
- `.wav` and `.WAV` files only
- All firmware versions present in the repo
- Shared XML parsing library (`deluge_sdk`) for reuse

**Out of scope:**
- Physical SD card operations (read/write)
- Cloud backup sync (handled by separate scripts)
- Creating or modifying audio files
- Song/kit/synth creation or editing beyond path reference updates

## Existing Assets Analysis

| Capability | Status | Location | Notes |
|------------|--------|----------|-------|
| Scripts directory | ⚠️ Partial | `scripts/` | Empty except for `.env.example` |
| Environment config | ✅ Ready | `scripts/.env.example` | Has `SAMPLES_SOURCE`, `SD_CARD_PATH`, etc. |
| Scripts plan | ⚠️ Partial | `docs/scripts-plan.md` | Old, unimplemented plan — useful as reference for naming and workflow |
| Hashing explanation | ✅ Ready | `docs/hashing-eli5.md` | Thorough explanation of the hashing approach — good for user docs |
| User requirements | ✅ Ready | `temp/samples-notes.md` | Detailed requirements and answers to clarifying questions |
| Deluge SDK library | ❌ Missing | — | No shared XML parsing code exists yet |
| Sample manifest script | ❌ Missing | — | No implementation exists |
| Reference fixer script | ❌ Missing | — | No implementation exists |
| Reference verifier script | ❌ Missing | — | No implementation exists |
| Firmware wiki | ❌ Missing | — | `DelugeFirmware.wiki/` not present in workspace |
| Firmware contrib tools | ❌ Missing | — | `DelugeFirmware/contrib/` not present in workspace |

## Findings

### 1. XML Format Analysis

#### 1.1 Firmware Versions Present in Repository

Ten distinct firmware versions were found across **75 kit XMLs**, **~280+ synth XMLs** (509 total including community), and **48 song XMLs**:

| Version | Format Style | Found In | Example File |
|---------|-------------|----------|-------------|
| *(none)* | Element | KIT000.XML | Oldest — pre-2.0, no version tag at all |
| `2.0.0-beta` | Element | Synths (SYNT060, SYNT079, etc.) | `DELUGE/SYNTHS/SYNT060.XML` |
| `2.0.0` | Element | Kits (KIT039) | `DELUGE/KITS/KIT039.XML` |
| `2.1.0-beta` | Element | Kits (KIT029) | `DELUGE/KITS/KIT029.XML` |
| `2.1.0` | Element | Kits, Synths (KIT027, SYNT168, SYNT169) | `DELUGE/KITS/KIT027.XML` |
| `3.1.5` | Attribute | Synths (65-FUNK, TB series) | `DELUGE/SYNTHS/65-FUNK.XML` |
| `4.0.0` | Attribute | Synths (SYNT085A, SYNT053A) | `DELUGE/SYNTHS/SYNT085A.XML` |
| `4.0.1` | Attribute | Kits, Synths (Deeper, Nr Drums, named presets) | `DELUGE/KITS/Deeper.XML` |
| `c1.2.0` | Attribute | Community presets | `DELUGE/KITS/COMMUNITY/1.2 Presets/VSCO Perc Kit.XML` |
| `c1.2.1` | Attribute | All songs | `DELUGE/SONGS/K01Sink.XML` |

**Source:** Direct examination of XML files in `DELUGE/KITS/`, `DELUGE/SYNTHS/`, `DELUGE/SONGS/`.

#### 1.2 Format Category A: Element-Style (firmware < 3.x)

Used by files with firmware versions: *(none)*, `2.0.0-beta`, `2.0.0`, `2.1.0-beta`, `2.1.0`.

**Firmware version** is either absent (oldest files) or a top-level sibling element:

```xml
<!-- KIT000.XML — no firmware version at all -->
<?xml version="1.0" encoding="UTF-8"?>
<kit>
    ...

<!-- KIT039.XML — firmware 2.0.0 -->
<?xml version="1.0" encoding="UTF-8"?>
<firmwareVersion>2.0.0</firmwareVersion>
<earliestCompatibleFirmware>2.0.0</earliestCompatibleFirmware>
<kit>
    ...
```

**Sample references** use `<fileName>` as an **element with text content**:

```xml
<!-- Inside <osc1> or <osc2> within a <sound> element -->
<osc1>
    <type>sample</type>
    <fileName>SAMPLES/DRUMS/Kick/808 Kick.wav</fileName>
    <zone>
        <startMilliseconds>0</startMilliseconds>
        <endMilliseconds>501</endMilliseconds>
    </zone>
</osc1>

<!-- Empty osc2 (no sample assigned) -->
<osc2>
    <type>sample</type>
    <fileName></fileName>
</osc2>
```

**Multisampled synths** use `<sampleRanges>` with element-style `<fileName>`:

```xml
<!-- SYNT168.XML — firmware 2.1.0 -->
<osc1>
    <type>sample</type>
    <sampleRanges>
        <sampleRange>
            <rangeTopNote>72</rangeTopNote>
            <fileName>SAMPLES/Artists/Leonard Ludvigsen/Hangdrum/1.wav</fileName>
            <zone>
                <startSamplePos>0</startSamplePos>
                <endSamplePos>146506</endSamplePos>
            </zone>
        </sampleRange>
        <sampleRange>
            <fileName>SAMPLES/Artists/Leonard Ludvigsen/Hangdrum/2.wav</fileName>
            ...
        </sampleRange>
    </sampleRanges>
</osc1>
```

**Source:** `DELUGE/KITS/KIT000.XML`, `DELUGE/KITS/KIT039.XML`, `DELUGE/KITS/KIT027.XML`, `DELUGE/SYNTHS/SYNT168.XML`, `DELUGE/SYNTHS/SYNT169.XML`.

#### 1.3 Format Category B: Attribute-Style (firmware >= 3.x)

Used by files with firmware versions: `3.1.5`, `4.0.0`, `4.0.1`, `c1.2.0`, `c1.2.1`.

**Firmware version** is an attribute on the root element:

```xml
<!-- Deeper.XML — kit, firmware 4.0.1 -->
<kit firmwareVersion="4.0.1" earliestCompatibleFirmware="4.0.0" ...>

<!-- Islp.XML — synth, firmware 4.0.1 -->
<sound firmwareVersion="4.0.1" ...>

<!-- K01Sink.XML — song, firmware c1.2.1 -->
<song firmwareVersion="c1.2.1" ...>
```

**Sample references** use `fileName` as an **XML attribute**:

```xml
<!-- Inside <osc1> or <osc2> -->
<osc1
    type="sample"
    loopMode="1"
    fileName="SAMPLES/DRUMS/Kick/Deep Sky Kick HQ9094.wav">
    <zone startSamplePos="0" endSamplePos="17471" />
</osc1>

<!-- Empty osc2 (no sample assigned) -->
<osc2
    type="sample"
    loopMode="0">
</osc2>
```

Note: in the attribute-style format, an osc element with no sample may have `fileName=""` or may simply **omit the fileName attribute entirely** (as shown above for osc2 in `Deeper.XML`). Both cases must be handled.

**Multisampled synths** use `<sampleRanges>` with attribute-style `fileName`:

```xml
<!-- Song Kg.XML — embedded synth with double bass multisample -->
<osc1
    type="sample"
    loopMode="0">
    <sampleRanges>
        <sampleRange
            rangeTopNote="37"
            fileName="SAMPLES/Artists/Leonard Ludvigsen/Double bass/Lo/36 b.WAV"
            transpose="24">
            <zone startSamplePos="0" endSamplePos="324506" />
        </sampleRange>
        <sampleRange
            rangeTopNote="41"
            fileName="SAMPLES/Artists/Leonard Ludvigsen/Double bass/Lo/39 b.WAV"
            transpose="21">
            <zone startSamplePos="0" endSamplePos="180147" />
        </sampleRange>
    </sampleRanges>
</osc1>
```

**Community preset format** (`c1.2.0`) uses compact single-line attribute style:

```xml
<!-- VSCO Perc Kit.XML — community firmware c1.2.0, all on one line -->
<osc1 type="sample" loopMode="1" reversed="0" timeStretchEnable="0"
      timeStretchAmount="0"
      fileName="SAMPLES/COMMUNITY/1.2 Presets/VSCO Perc Kit/wood_click_f.wav">
    <zone startSamplePos="0" endSamplePos="14741" />
</osc1>
```

**Source:** `DELUGE/KITS/Deeper.XML`, `DELUGE/SYNTHS/Islp.XML`, `DELUGE/SONGS/Kg.XML`, `DELUGE/KITS/COMMUNITY/1.2 Presets/VSCO Perc Kit.XML`.

**Note:** `type="wavetable"` oscillators also use `fileName` attributes to reference WAV files. For example:

```xml
<!-- Low Drone Bass.XML — community synth with wavetable oscillator -->
<osc1 type="wavetable" loopMode="0" reversed="0" timeStretchEnable="0" timeStretchAmount="0"
      fileName="SAMPLES/COMMUNITY/1.2 Presets B-Sides/Low Drone Bass/uwahwah.wav">
</osc1>
```

Several community synths use `type="wavetable"` (e.g., `Exprestrings.XML`, `Ample Vocal Pad.XML`, `Shinep.XML`, `Bubbley.XML`, `Meld Arp.XML`). Extraction must not filter by `type="sample"` — any `osc` element with a `fileName` should be captured regardless of its `type` value.

#### 1.4 Audio Clip References: `filePath` Attribute

**Critical finding:** Song XMLs reference samples via a **second distinct attribute name** — `filePath` — on `<audioClip>` elements. This is separate from the `fileName` attribute used on `<osc1>`/`<osc2>`/`<sampleRange>`.

```xml
<!-- K01Sink.XML — audioClip referencing a CLIPS recording -->
<audioClip
    trackName="AUDIO2"
    filePath="SAMPLES/CLIPS/REC00040.WAV"
    startSamplePos="2086"
    endSamplePos="707686"
    ...>
```

This pattern was found across many songs for CLIPS, RECORD, and RESAMPLE references, as well as regular sample references:

```xml
<!-- K02Slpspk.XML — audioClip referencing a regular sample -->
<audioClip
    ...
    filePath="SAMPLES/KERERU/SleepSpeak/Vocals/SS-Vox-5-CX-120bpm.wav"
    ...>
```

RESAMPLE samples can also appear as `fileName` on `<osc1>` within embedded kit sounds:

```xml
<!-- Yeti.XML — RESAMPLE used as a regular sample in a kit -->
<osc1
    ...
    fileName="SAMPLES/RESAMPLE/REC00005.WAV">
```

**Source:** `DELUGE/SONGS/K01Sink.XML` (line 2740), `DELUGE/SONGS/K02Slpspk.XML` (line 12052), `DELUGE/SONGS/Yeti.XML` (line 217), `DELUGE/SONGS/Noize.XML` (line 152).

#### 1.5 Complete Reference Location Map

All sample references found in the repository, with their XML context:

| # | Attribute/Element | Style | Parent Element | Context | Found In |
|---|------------------|-------|---------------|---------|----------|
| 1 | `<fileName>text</fileName>` | Element | `<osc1>`, `<osc2>` | Direct sample on oscillator | Old kits, synths |
| 2 | `<fileName>text</fileName>` | Element | `<sampleRange>` | Multisample zone | Old synths |
| 3 | `fileName="..."` | Attribute | `<osc1>`, `<osc2>` | Direct sample on oscillator | New kits, synths, songs |
| 4 | `fileName="..."` | Attribute | `<sampleRange>` | Multisample zone | New synths, songs |
| 5 | `filePath="..."` | Attribute | `<audioClip>` | Audio clip recording | Songs only |

**Empty references to skip:** `<fileName></fileName>`, `fileName=""`, and the absence of a `fileName` attribute entirely. All three mean "no sample assigned" and must be ignored by all scripts.

**Note:** Patterns 1–4 apply to oscillators with `type="sample"` AND `type="wavetable"` — any `osc` element with a `fileName` should be captured regardless of its `type` value. Do not add a `type="sample"` filter to extraction logic.

#### 1.6 Case Sensitivity

Both `.wav` and `.WAV` extensions are used in the repository. Notably, case differences exist in folder names too:

- `SAMPLES/ARTISTS/Campbell Kneale/...` (uppercase ARTISTS, firmware 2.0.0 — `KIT039.XML`)
- `SAMPLES/Artists/Leonard Ludvigsen/...` (mixed case Artists, firmware 2.1.0 — `SYNT168.XML`)

Paths are case-sensitive on the Deluge hardware. The parsing library must preserve original case exactly and never normalise it.

### 2. Song XML Structure — Embedded Instruments

Song XMLs embed complete instrument definitions inline. The `<instruments>` element contains:

| Element | Identifies As | Has Samples? |
|---------|--------------|-------------|
| `<sound presetName="..." presetFolder="SYNTHS/...">` | Embedded synth | If osc1/osc2 uses `type="sample"` |
| `<kit presetName="..." presetFolder="KITS/...">` | Embedded kit | Yes — has `<soundSources>` with `<sound>` children |
| `<audioTrack name="...">` | Audio track | No direct samples (clips reference via `<audioClip>`) |
| `<midi channel="...">` | MIDI track | No samples |

**Kit structure within songs:**

```
<kit presetName="K01Perc2" presetFolder="KITS/KERERU">
    <soundSources>
        <sound name="Rhythmace Kick" ...>
            <osc1 fileName="SAMPLES/DRUMS/Kick/Rhythmace Kick.wav" ...>
            <osc2 ...>  <!-- may or may not have fileName -->
        </sound>
        <sound name="XV5080 Ride edge" ...>
            ...
        </sound>
    </soundSources>
</kit>
```

**Synth structure within songs:**

```
<sound presetName="41-VIOLINE 3" presetFolder="SYNTHS">
    <osc1 type="sine" ...>  <!-- no sample, pure synth -->
    <osc2 type="square" ...>
</sound>
```

For the manifest, the **instrument name** referencing a given sample within a song is:
- For kits: `presetName` on the `<kit>` element (e.g., "K01Perc2")
- For synths: `presetName` on the `<sound>` element (e.g., "41-VIOLINE 3")

The `presetFolder` attribute provides the source folder (e.g., `KITS/KERERU`, `SYNTHS`).

**Duplicate handling:** A song may contain multiple instruments that use the same sample. Per user requirements, a song should count as **1 reference** regardless of how many embedded instruments use the sample. However, the manifest should list which embedded instrument(s) within the song use it.

**Source:** `DELUGE/SONGS/K01Sink.XML` (lines 147–1891), `DELUGE/SONGS/Ape.XML` (lines 130–230).

### 3. Audio Metadata Extraction

#### 3.1 Library Comparison

| Library | Type | WAV Support | Duration | Sample Rate | Bit Depth | Install Size | Notes |
|---------|------|------------|----------|-------------|-----------|-------------|-------|
| `wave` | stdlib | ✅ | ✅ (calculate from frames/rate) | ✅ | ✅ | 0 (built-in) | Read-only, no dependencies, WAV-only |
| `soundfile` | PyPI | ✅ | ✅ | ✅ | ✅ | ~2MB + libsndfile | Fast, C-based, needs system lib |
| `mutagen` | PyPI | ✅ | ✅ | ✅ | ✅ | ~1MB | Pure Python, designed for tag metadata |
| `pydub` | PyPI | ✅ | ✅ | ✅ | ✅ | ~50KB + ffmpeg | Overkill — designed for audio processing |

#### 3.2 Recommendation: `wave` (stdlib)

The `wave` module is the best fit for this use case:

- **Zero dependencies** — no external libraries to install or maintain
- **Sufficient for the task** — provides frames, sample rate, bit depth, channels
- **Duration** is calculated as `frames / sample_rate`
- **WAV-only** — which is exactly what we need (the Deluge only uses `.wav`)

```python
import wave
from pathlib import Path

def get_wav_metadata(path: Path) -> dict:
    with wave.open(str(path), "rb") as w:
        frames = w.getnframes()
        rate = w.getframerate()
        return {
            "duration_seconds": round(frames / rate, 2),
            "sample_rate": rate,
            "channels": w.getnchannels(),
            "bit_depth": w.getsampwidth() * 8,
        }
```

If `wave` fails on any files (some WAV variants aren't supported), `soundfile` would be the fallback — but this should be a future enhancement only if needed.

#### 3.3 File Dates

On Linux, `os.stat()` provides:
- `st_mtime` — last modification time (reliable)
- `st_ctime` — metadata change time on Linux (NOT creation time)
- `st_birthtime` — not available on Linux (only macOS/Windows)

**Recommendation:** Use `st_mtime` as the primary date field. Label it clearly as "last modified" rather than "created". True creation dates are not reliably available on Linux ext4 filesystems.

### 4. Hashing Strategy

#### 4.1 SHA256 Validation

SHA256 is the correct choice for this use case:

| Property | Assessment |
|----------|-----------|
| **Collision resistance** | Virtually impossible — SHA256 produces 2^256 unique values |
| **Speed at scale** | ~200-400 MB/s on modern hardware. A 1000-file collection of WAVs (assume ~5GB total) processes in ~15-25 seconds |
| **Determinism** | Same content always produces same hash, regardless of filename/path/metadata |
| **Built-in** | Python's `hashlib.sha256()` — no external dependencies |

#### 4.2 Implementation Pattern

```python
import hashlib
from pathlib import Path

def hash_file(path: Path, chunk_size: int = 8192) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()
```

#### 4.3 Edge Cases

| Edge Case | Handling |
|-----------|---------|
| **Duplicate content** (identical files at different paths) | Hash maps to a list of paths. If only one source existed before, and duplicates appear after, flag as ambiguous |
| **Very large files** (>100MB) | Chunked reading handles this. No memory issues |
| **Zero-byte files** | Will hash to the SHA256 of empty input. Likely an error — flag to user |
| **File moved AND content changed** | Cannot be detected by hashing alone. Treat as delete + new file. Flag the deleted reference as an error |

#### 4.4 Migration Map Format

```json
{
    "before": {
        "a1b2c3d4...": ["SAMPLES/DRUMS/Kick/808 Kick.wav"],
        "9f8e7d6c...": ["SAMPLES/DRUMS/Snare/808 Snare.wav"]
    },
    "after": {
        "a1b2c3d4...": ["SAMPLES/808/Kicks/808-Kick.wav"],
        "9f8e7d6c...": ["SAMPLES/808/Snares/808-Snare.wav"]
    },
    "mapping": {
        "SAMPLES/DRUMS/Kick/808 Kick.wav": "SAMPLES/808/Kicks/808-Kick.wav",
        "SAMPLES/DRUMS/Snare/808 Snare.wav": "SAMPLES/808/Snares/808-Snare.wav"
    },
    "deleted": [],
    "added": [],
    "ambiguous": []
}
```

### 5. Keyword/Category Inference

#### 5.1 Strategy: Path + Filename Parsing

Given the inconsistency of sample naming (per user: ranges from `kick-oneshot-120bpm-techno` to `rec-0001.WAV`), the approach should be **best-effort extraction** focused on speed of decision-making, not perfect classification.

#### 5.2 Extractable Information

| Category | Source | Method | Example |
|----------|--------|--------|---------|
| **Instrument type** | Path segments, filename | Keyword matching against known terms | `DRUMS/Kick/` → "kick", "drums" |
| **Sample pack/origin** | Parent directory name | Extract 2nd path segment after SAMPLES/ | `SAMPLES/ARTISTS/Campbell Kneale/` → "Campbell Kneale" |
| **One-shot vs Loop** | Filename keywords, path | Match keywords: "loop", "oneshot", "one-shot", "shot" | `kick-oneshot-120bpm.wav` → "one-shot" |
| **BPM** | Filename | Regex: `(\d{2,3})\s*bpm` | `NatRad-DrumsHook-8Bars-108bpm.wav` → 108 |
| **Musical key** | Filename | Regex for note names near end | Limited reliability |
| **Recording type** | Path | Match against CLIPS/, RECORD/, RESAMPLE/ | `SAMPLES/CLIPS/REC00040.WAV` → "clip-recording" |

#### 5.3 Keyword Dictionary

Build a modest lookup dictionary of common sample terms:

```python
INSTRUMENT_KEYWORDS = {
    "kick": ["kick", "bd", "bass drum", "bassdrum"],
    "snare": ["snare", "sd", "snr"],
    "hihat": ["hihat", "hat", "hh", "hi-hat"],
    "clap": ["clap", "cp"],
    "cymbal": ["cymbal", "crash", "ride"],
    "tom": ["tom"],
    "percussion": ["perc", "conga", "bongo", "shaker", "tambourine", "cowbell", "rim", "claves"],
    "bass": ["bass", "sub"],
    "piano": ["piano", "keys", "rhodes"],
    "guitar": ["guitar", "gtr"],
    "vocals": ["vocal", "vox", "voice"],
    "fx": ["fx", "effect", "riser", "sweep", "impact"],
    "pad": ["pad", "ambient", "drone"],
}
```

#### 5.4 Recommendation

Implement a `categorise_sample(path: str) -> dict` function that returns:

```python
{
    "categories": ["drums", "kick"],       # matched keywords
    "origin": "808",                        # inferred from path
    "bpm": 120,                             # if detected, else None
    "type": "one-shot",                     # one-shot, loop, recording, or None
    "raw_keywords": ["808", "kick"],        # all extracted terms
}
```

Keep it simple, fast, and deterministic. Users can refine categorisation after reviewing the manifest. The goal is to provide *any* useful signal, not perfect classification.

### 6. Dry-Run + Confirm Workflow

#### 6.1 Pattern: Compute → Preview → Confirm → Apply

The user explicitly wants to avoid re-scanning when moving from preview to apply. The recommended pattern:

```
1. Script runs full analysis (scan files, compute diffs, build change set)
2. Display preview of all changes
3. Prompt: "Apply these changes? [y/N]"
4. If confirmed, apply the already-computed change set
```

This means the change set must be held in memory (or serialised) between the preview and apply steps — not recomputed.

#### 6.2 Implementation

```python
def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="Apply changes (skips interactive confirmation)")
    args = parser.parse_args(argv)

    # Phase 1: Compute changes
    changes = compute_changes()

    # Phase 2: Preview
    print_preview(changes)

    if not changes:
        print("No changes needed.")
        return

    # Phase 3: Confirm + Apply
    if args.apply:
        apply_changes(changes)
    else:
        response = input("\nApply these changes? [y/N]: ")
        if response.lower() == "y":
            apply_changes(changes)
        else:
            print("No changes applied.")
```

The `--apply` flag skips the interactive prompt (useful for CI/automation). Default behaviour always previews first.

### 7. Module Structure

#### 7.1 Recommended Layout

Following the Python Core Standard's scripts layout recommendation:

```
scripts/
├── .env.example              # Existing — environment config template
├── .env                      # Gitignored — user's local config
├── .python-version           # Pin Python version
├── pyproject.toml            # Dependencies and tool config
├── Makefile                  # Workflow orchestration
├── generate_manifest.py      # Script 1: Sample manifest generator
├── fix_references.py         # Script 2: Reference fixer (snapshot + diff + fix)
├── verify_references.py      # Script 3: Reference verifier
├── sample_usage.py           # Utility: Detailed usage info for a single sample
├── lib/
│   ├── __init__.py
│   ├── deluge_sdk.py         # Shared XML parsing and reference extraction
│   ├── sample_utils.py       # Hashing, WAV metadata, categorisation
│   └── cli_utils.py          # Dry-run/confirm workflow, output formatting
└── tests/
    ├── conftest.py
    ├── test_deluge_sdk.py
    └── test_sample_utils.py
```

#### 7.2 Shared Library: `deluge_sdk.py`

Core functions for all scripts:

```python
# Key API surface:

def find_all_xml_files(deluge_dir: Path) -> list[Path]:
    """Recursively find all .XML files in KITS/, SYNTHS/, SONGS/."""

def extract_sample_refs(xml_path: Path) -> list[SampleRef]:
    """Extract ALL sample references from an XML file.
    Handles both element-style and attribute-style fileName,
    plus filePath on audioClip elements.
    Returns empty list for XMLs with no sample references."""

@dataclass
class SampleRef:
    path: str              # e.g. "SAMPLES/DRUMS/Kick/808 Kick.wav"
    xml_file: Path         # which XML file contains this reference
    xml_type: str          # "kit", "synth", "song"
    instrument_name: str   # presetName for songs, sound name for kits
    instrument_folder: str # presetFolder for songs
    ref_type: str          # "fileName-element" | "fileName-attribute" | "filePath-attribute"
    element_tag: str       # "osc1", "osc2", "sampleRange", "audioClip"

def update_sample_ref(xml_path: Path, old_path: str, new_path: str,
                      dry_run: bool = True) -> bool:
    """Update a single sample reference in an XML file.
    Handles both format styles. Preserves XML formatting."""
```

#### 7.3 `sample_utils.py` — Supporting Utilities

```python
def hash_file(path: Path) -> str:
    """SHA256 hash of file contents."""

def get_wav_metadata(path: Path) -> WavMetadata:
    """Extract duration, sample rate, channels, bit depth."""

def categorise_sample(sample_path: str) -> SampleCategory:
    """Infer categories/keywords from path and filename."""

def scan_samples_dir(samples_dir: Path) -> list[SampleInfo]:
    """Walk SAMPLES/ and gather metadata for all .wav/.WAV files."""
```

#### 7.4 Makefile / Workflow Orchestration

```makefile
.PHONY: manifest verify snapshot fix

manifest:
	python scripts/generate_manifest.py

verify:
	python scripts/verify_references.py

snapshot:
	python scripts/fix_references.py snapshot

fix:
	python scripts/fix_references.py fix
```

### 8. Special Rules: CLIPS/, RECORD/, RESAMPLE/

Per user requirements, these directories have special constraints:

| Rule | Enforcement |
|------|------------|
| Include in manifest | Scan and catalogue like any other samples |
| Contents can be moved out or deleted | Allow in migration map |
| Directories must NEVER be deleted | Verifier should check these directories exist; fixer should never remove them |
| Must NEVER contain subdirectories | Verifier should warn if subdirectories are found |

These rules should be checked by the reference verifier as part of its validation pass.

### 9. XML Parsing Approach: `lxml` vs `xml.etree`

Per the Python Core Standard, `lxml` is the recommended XML library for this project.

| Consideration | `lxml` | `xml.etree` |
|---------------|--------|-------------|
| XPath support | Full XPath 1.0 | Limited subset |
| Speed | 5-10x faster for large files | Adequate for small files |
| Formatting preservation | Better control via `write()` options | Tends to reformat |
| External dependency | Yes (C library) | No (stdlib) |

**Recommendation: `lxml`**. Song XMLs can be large (thousands of lines), XPath is essential for cleanly querying both format styles, and the project standard mandates it.

**Parsing strategy for both formats:**

```python
from lxml import etree

def extract_sample_refs(xml_path: Path) -> list[SampleRef]:
    tree = etree.parse(str(xml_path))
    root = tree.getroot()
    refs = []

    # Attribute-style: fileName="..." on osc1, osc2
    # Note: //*[@fileName] intentionally matches ALL elements with a fileName
    # attribute regardless of type (including type="wavetable"), not just type="sample"
    for elem in root.xpath("//*[@fileName]"):
        value = elem.get("fileName")
        if value:  # skip empty strings
            refs.append(make_ref(value, elem, xml_path))

    # Element-style: <fileName>text</fileName>
    for elem in root.xpath("//fileName"):
        value = elem.text
        if value and value.strip():  # skip empty elements
            refs.append(make_ref(value.strip(), elem, xml_path))

    # Audio clip filePath attribute
    for elem in root.xpath("//audioClip[@filePath]"):
        value = elem.get("filePath")
        if value:
            refs.append(make_ref(value, elem, xml_path))

    return refs
```

**Critical: updating references must preserve the original format.** If a file uses element-style `<fileName>`, the updated value must remain element-style. If it uses attribute-style `fileName="..."`, the update must use attribute-style. The `update_sample_ref` function must detect the format and write accordingly.

## Approaches Considered

### Architecture Approach

| Approach | Pros | Cons | Complexity |
|----------|------|------|------------|
| **A: Modular Python scripts with shared library** (recommended) | Clean separation, reusable parsing, testable, matches existing plan | More files to maintain | Medium |
| B: Single monolithic script with subcommands | Single file to run, simpler deployment | Hard to test, hard to extend, violates modularity goal | Medium |
| C: Pure bash scripts | No Python dependency | Cannot parse XML reliably, no hashing stdlib | Impractical |

### XML Parsing Approach

| Approach | Pros | Cons | Complexity |
|----------|------|------|------------|
| **A: `lxml` with XPath** (recommended) | Fast, powerful queries, handles both formats cleanly | External dependency | Low |
| B: `xml.etree.ElementTree` | No dependency | Limited XPath, slower, harder to query dual formats | Low |
| C: Regex-based parsing | Zero dependencies, very fast | Fragile, error-prone, hard to maintain | Medium |

### Dry-Run Approach

| Approach | Pros | Cons | Complexity |
|----------|------|------|------------|
| **A: Compute → Preview → Confirm in single run** (recommended) | No re-scanning, fast, user-friendly | Holds change set in memory | Low |
| B: Separate dry-run and apply commands | Simple logic per invocation | Requires re-scanning on apply, slower | Low |
| C: Write change plan to file, apply from file | Inspectable artefact, can resume | More complex, serialisation overhead | Medium |

## Cross-Cutting Concerns

### XML Parsing Library

The `deluge_sdk` module is the central dependency for all scripts. Changes to XML format handling affect every script. Design for:
- Clear version-agnostic API (callers should not need to know the firmware version)
- Both read and write operations
- Comprehensive test coverage (at least one test per firmware format era)

### Path Relativity

All sample paths in XMLs are relative to `DELUGE/`. Scripts must consistently resolve paths relative to the `DELUGE/` directory. The `.env` file should specify the `DELUGE/` path (defaulting to `./DELUGE/` when run from repo root).

### Git Integration

Scripts modify XML files in `DELUGE/`. All changes are captured by git, providing an automatic safety net. The user explicitly relies on git for backup and has stated the scripts do not need to create their own backups.

### SD Card Safety

Per `standards/project.md`: scripts operate on the local repo only. No script should accept an SD card path for writing. Read from SD card is handled by a separate `sd-to-repo` script (not in scope).

### Future Scripts

The `docs/scripts-plan.md` documents several other planned scripts (sync-samples, sd-to-repo, sd-to-zip, rename_songs). The `deluge_sdk` library should be designed with these in mind — particularly the XML parsing and file enumeration functions which will be reused.

## Risk Analysis

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **XML formatting corrupted on write** | Medium | High — broken presets | Use `lxml` write with format preservation. Test round-trip parsing on every firmware version. Verify with `verify_references.py` after every fix run |
| **Missed sample reference type** | Low | High — broken references after fix | Comprehensive testing with all 5 reference location types. Run verifier as post-fix validation |
| **Hash collision** (different files, same hash) | Negligible | Medium — wrong path assigned | SHA256 collision is practically impossible. No mitigation needed |
| **Duplicate file content** (same content, different paths) | Medium | Medium — ambiguous mapping | Detect and flag to user. Require manual resolution for ambiguous cases |
| **Large song XMLs cause slow parsing** | Low | Low — slower script | `lxml` handles large files efficiently. Expected max ~10K lines |
| **Deleted sample still referenced** | Medium (user error) | High — broken preset on hardware | Fixer MUST flag this as an error, not silently handle it. User must resolve manually |
| **CLIPS/RECORD/RESAMPLE directories deleted** | Low | High — Deluge recording breaks | Verifier checks these directories exist. Fixer never removes them |
| **Case sensitivity mismatch** | Low | Medium — broken reference on hardware | Preserve original case exactly. Never normalise paths. Verifier should check case-exact file existence |

## Recommendation

**Adopt Approach A: Modular Python scripts with a shared `deluge_sdk` library, using `lxml` for XML parsing, and compute-then-confirm dry-run workflow.**

This approach:
- Matches the existing `docs/scripts-plan.md` architecture vision
- Follows the Python Core Standard's scripts layout
- Provides reusable components for future scripts
- Keeps each script focused and testable
- Uses `lxml` as mandated by project standards
- Avoids re-scanning on apply (per user preference)
- Handles all 5 reference location types across all 10 firmware versions

The `wave` stdlib module is sufficient for audio metadata. SHA256 is the right choice for migration mapping at the expected scale. Keyword inference should be best-effort and simple.

## Open Questions

1. **What should the `.env` variable for the DELUGE directory be named?**
   - **Impact:** Affects all script configuration and is established early
   - **Recommendation:** `DELUGE_ROOT` pointing to `DELUGE/` relative to repo root, with a fallback to `./DELUGE/` if unset
   - **Blocking:** No — reasonable default exists

2. **Should the manifest include audio metadata (duration, sample rate) for all samples, or only for samples that are in use?**
   - **Impact:** Affects scan time and manifest size. Unused samples benefit from metadata too (helps decision-making about what to keep)
   - **Recommendation:** Include metadata for all samples. At ~1000 files, the overhead is trivial
   - **Blocking:** No

3. **Should the reference fixer support partial/incremental fixes (fix some references, skip others)?**
   - **Impact:** Increases complexity of the interactive confirm flow
   - **Recommendation:** Defer to planning. For v1, apply all or none. The user can re-run after resolving issues
   - **Blocking:** No

4. **How should the `sampleRange` `fileName` update interact with `rangeTopNote` and `transpose` attributes?**
   - **Impact:** These attributes are part of the same element. Updates must not disturb them
   - **Recommendation:** `lxml` attribute updates are per-attribute and don't affect siblings. Standard XML handling covers this
   - **Blocking:** No

5. **Should the CSV manifest output be a flat or nested structure?**
   - **Impact:** Affects usability in spreadsheet tools
   - **Recommendation:** Flat structure (one row per sample). Reference information can be comma-separated within cells or limited to counts. Defer detailed format to planning
   - **Blocking:** No

## References

### Project Files
- [AGENTS.md](AGENTS.md) — Project overview, SD card structure, agent system
- [docs/scripts-plan.md](docs/scripts-plan.md) — Old (unimplemented) scripts plan with relevant architecture ideas
- [docs/hashing-eli5.md](docs/hashing-eli5.md) — User-facing explanation of hashing approach
- [temp/samples-notes.md](temp/samples-notes.md) — Detailed user requirements and answers to clarifying questions
- [scripts/.env.example](scripts/.env.example) — Existing environment configuration template
- [agent-system/standards/languages/python/core.md](agent-system/standards/languages/python/core.md) — Python project structure and coding standards

### XML Files Examined
- [DELUGE/KITS/KIT000.XML](DELUGE/KITS/KIT000.XML) — Oldest format (no firmware version), element-style fileName
- [DELUGE/KITS/KIT039.XML](DELUGE/KITS/KIT039.XML) — Firmware 2.0.0, element-style
- [DELUGE/KITS/KIT027.XML](DELUGE/KITS/KIT027.XML) — Firmware 2.1.0, element-style
- [DELUGE/KITS/KIT029.XML](DELUGE/KITS/KIT029.XML) — Firmware 2.1.0-beta, element-style
- [DELUGE/KITS/Deeper.XML](DELUGE/KITS/Deeper.XML) — Firmware 4.0.1, attribute-style
- [DELUGE/KITS/Nr Drums.XML](DELUGE/KITS/Nr%20Drums.XML) — Firmware 4.0.1, attribute-style
- [DELUGE/KITS/KERERU/K01Perc.XML](DELUGE/KITS/KERERU/K01Perc.XML) — Firmware 4.0.1, attribute-style, subfolder kit
- [DELUGE/KITS/COMMUNITY/1.2 Presets/VSCO Perc Kit.XML](DELUGE/KITS/COMMUNITY/1.2%20Presets/VSCO%20Perc%20Kit.XML) — Community firmware c1.2.0, compact attribute-style
- [DELUGE/SYNTHS/SYNT168.XML](DELUGE/SYNTHS/SYNT168.XML) — Firmware 2.1.0, element-style with sampleRanges
- [DELUGE/SYNTHS/SYNT169.XML](DELUGE/SYNTHS/SYNT169.XML) — Firmware 2.1.0, element-style with many sampleRanges
- [DELUGE/SYNTHS/Islp.XML](DELUGE/SYNTHS/Islp.XML) — Firmware 4.0.1, attribute-style synth with sample
- [DELUGE/SYNTHS/SYNT000.XML](DELUGE/SYNTHS/SYNT000.XML) — No fileName (pure synth, no samples)
- [DELUGE/SONGS/K01Sink.XML](DELUGE/SONGS/K01Sink.XML) — Community firmware c1.2.1, embedded kits+synths, audioClip with filePath
- [DELUGE/SONGS/Ape.XML](DELUGE/SONGS/Ape.XML) — Community firmware c1.2.1, embedded kit with fileName attributes
- [DELUGE/SONGS/Bloop.XML](DELUGE/SONGS/Bloop.XML) — Community firmware c1.2.1, embedded kit
- [DELUGE/SONGS/Kg.XML](DELUGE/SONGS/Kg.XML) — Community firmware c1.2.1, embedded synth with sampleRanges (attribute-style)

### External Resources
- Python `wave` module documentation — stdlib WAV parsing (https://docs.python.org/3/library/wave.html)
- Python `hashlib` documentation — SHA256 hashing (https://docs.python.org/3/library/hashlib.html)
- `lxml` documentation — XML parsing and XPath (https://lxml.de/)

## Next Steps

1. Review this document and resolve any blocking open questions
2. Invoke the Plan agent to create a feature plan from this research
