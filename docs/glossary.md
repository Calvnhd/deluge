# Glossary

Terms used in this project's scripts, documentation, and the Deluge itself.

## Deluge Concepts

| Term | Definition |
|------|-----------|
| **Preset** | A saved kit or synth configuration. Stored as standalone XML files in `KITS/` or `SYNTHS/`, or embedded inline within song XMLs. Identified by `presetName` in the XML. |
| **Kit** | A preset containing multiple sounds (e.g. drums). Each sound has its own oscillators, samples, and effects. XML root element: `<kit>`. |
| **Synth** | A preset containing a single sound with oscillators, filters, and effects. XML root element: `<sound>`. |
| **Song** | A complete musical project containing embedded presets, clips, and arrangement data. XML root element: `<song>`. |
| **Clip** | A self-contained unit within a song — exactly one of: a kit clip, a synth clip, or an audio clip. Contains sequencing data, effects, and a reference to its preset/audio. Each clip has a colour used to group clips into sections. |
| **Audio clip** | A clip that plays back a recorded or imported audio file. References a sample via `filePath` on the `<audioClip>` element. Identified by `trackName` (e.g. `"AUDIO2"`). |
| **Instrument** | A kit or synth — the sound-producing entity within a clip. Does not include audio clips. |
| **Sound** | A single voice within a kit, represented by a `<sound>` element inside `<soundSources>`. Each sound has `osc1`/`osc2` which may reference samples. |
| **Oscillator** | A sound source within a sound (`<osc1>`, `<osc2>`). May be a synth waveform (sine, saw, square) or a sample/wavetable player. |
| **Sample range** | A key-range zone within a multisampled oscillator. Each `<sampleRange>` maps a `fileName` to a note range via `rangeTopNote`. |
| **Section** | A group of clips sharing the same colour. Sections provide a way to organise song parts (e.g. intro, verse, chorus). |
| **Arrangement** | An automated sequence of clips in a timeline (arranger view). May include arrangement-only clips (coloured white) not present in the regular clip set. |
| **Song view** | UI mode showing all clips as rows — one row per clip. |
| **Clip view** | UI mode showing a single clip's sequencing data. |
| **Arranger view** | UI mode showing an arrangement timeline — each row is an instrument or audio track, clips are placed along a timeline. |

## SD Card / File Structure

| Term | Definition |
|------|-----------|
| **DELUGE_ROOT** | The root directory of the Deluge SD card backup in this repository (`DELUGE/`). All paths in XMLs are relative to this directory. |
| **Standalone preset** | A kit or synth XML file in `KITS/` or `SYNTHS/`. Represents a preset that can be loaded independently. |
| **Embedded preset** | A kit or synth defined inline within a song XML under `<instruments>`. Songs embed complete copies of their presets so that song-specific edits don't affect standalone preset files. |
| **SAMPLES/** | Directory containing all audio sample files (`.wav`). Subdirectories include `CLIPS/`, `RECORD/`, `RESAMPLE/`, and user-created folders. |
| **CLIPS/** | Samples recorded via audio clip view. Must exist, must not contain subdirectories. |
| **RECORD/** | Samples recorded via kit clip view. Must exist, must not contain subdirectories. |
| **RESAMPLE/** | Samples created with the resample feature. Must exist, must not contain subdirectories. |

## XML Format

| Term | Definition |
|------|-----------|
| **Element-style** | Pre-3.x firmware XML format where values are stored as element text content (e.g. `<fileName>SAMPLES/kick.wav</fileName>`). |
| **Attribute-style** | 3.x+ firmware XML format where values are stored as XML attributes (e.g. `fileName="SAMPLES/kick.wav"`). |
| **`presetName`** | XML attribute on embedded presets within songs. Identifies the preset (e.g. `"K01Perc2"`). |
| **`trackName`** | XML attribute on `<audioClip>` elements. Identifies the audio track (e.g. `"AUDIO2"`). |
| **`fileName`** | XML element (element-style) or attribute (attribute-style) holding a sample path, found on `<osc1>`, `<osc2>`, and `<sampleRange>` elements. |
| **`filePath`** | XML attribute on `<audioClip>` elements holding the audio file path. Distinct from `fileName`. |

## Script Terminology

| Term | Definition |
|------|-----------|
| **Sample reference** | Any XML element or attribute that points to a sample file. Represented by the `SampleRef` dataclass. Five patterns exist (see research §1.5). |
| **Manifest** | A JSON/CSV inventory of all samples in `SAMPLES/` with metadata and usage information. |
| **Migration map** | A mapping of old sample paths to new sample paths, derived by comparing the sync manifest against the current filesystem state. |
