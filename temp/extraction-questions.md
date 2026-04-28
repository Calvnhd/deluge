# Extract Instruments — Clarifying Questions

40 questions organised by topic, covering ambiguities, edge cases, design decisions, and implementation choices.

---

## Scope & Purpose (1–5)

1. **Should instruments be extracted from _all_ songs, or should there be a way to include/exclude specific songs?** For example, some songs might be experiments or junk — would a `--songs` filter or exclude list be useful?

All songs

2. **Should the script also extract instruments that exist in the `<instruments>` section but have no corresponding clips (orphaned instruments)?** These may be stale presets from deleted clips, or arrangement-only instruments.

The orphaned instrument in Arpo is in arrangement only, therefore it can be ignored.  Assume this is the case for any other orphaned instruments.  However, when skipping these, we should print a warning for uiser awareness.

3. **Is the intent to run this script once and curate the results, or to re-run it periodically as new songs are added?** This affects whether idempotency and incremental updates matter.

Run it periodically. 

For simplicity, v1 can remove xmls from previous runs and create a fresh set each time.  Incremental updates do not matter.  The idea is that running this script will create a set of synth and kits that exist in the current set of songs as a snapshot in time. 

In the future we might refine this e.g. by adding a flag to specify songs, or to add new only (checking by name).

4. **Should arrangement-only clips (those in `<arrangementOnlyClips>` but not `<sessionClips>`) be included as extraction sources?** Some instruments may only have clips in the arrangement view.

No, ignore arrangement only information.

5. **Is there interest in extracting audio clip metadata (e.g. sample paths, FX settings) in the future, or is this strictly for synths and kits?**

synths and kits only

---

## Colour System & Version Selection (6–12)

6. **The clip version system uses the `section` attribute (0–11 on `<instrumentClip>`), which maps to the 12 colour-coded launch rows. `colourOffset` is a separate cosmetic hue for pad display. Is there any reason to track `colourOffset` in extraction output, or can it be ignored entirely?**

ignore colourOffset

7. **When you say "favour versions early in the colour order" — this maps to lowest `section` id (section 0 = light blue, section 1 = pink, etc.). Should the default extraction pick the clip with the lowest section id?**

default should be lowest id, yes

8. **For the default mode (take one version per instrument), should it be the _first clip encountered_ in the XML, or the one with the _lowest section id_ (earliest in the colour order)?** These may differ since XML element order doesn't necessarily match creation order.

lowest id

9. **If two clips of the same instrument are in the same `section` (duplicate clips in the same launch row), should both be examined or just the first?**

take the first and print a warning about the second

10. **For the extended mode (extracting multiple versions), what level of difference justifies saving a separate version?** For context: differences could range from a single volume tweak to completely different oscillator settings.

TBD. I need you to research variation in sections to inform this decision

> **Clarification:** Examined K01Drone across sections 2, 3, and 4 in K01Sink.XML. Most parameters (volume, pan, lfo1Rate) are **identical across sections**. The main differences found were in `lpfFrequency` and `lpfResonance` — and notably, some section clips contain **embedded automation data** (extended hex strings encoding parameter changes over time) while others have static single values. This suggests that cross-section variation is typically limited to a few parameters being tweaked or automated for different song parts, rather than wholesale instrument redesigns. For a simple threshold: if more than ~3 non-volume/pan parameters differ, the versions are likely meaningfully different.

Ignore automation data - that is something specific to the way that clip is played in that song.

We should investigate two things: how many params have changed, and by how much.  Make these two thresholds easily editable (a constant value somewhere?) -- it's likely I'll be tweaking them over time. 

To start, let's say if three or more numerical params (ignoring master volume and pan) alter by more than 10%, treat it as distinct. Note that most values range from 0-50 or -50 to +50 from the user's perspective. Extra research may be required for the upper and lower limits of each param.

11. **Which parameters should be considered "structurally significant" for difference detection (e.g. oscillator type, filter mode, patch cables) vs. "trivially different" (e.g. slight volume change, LFO rate tweak)?**

Give me a list of all parameters 

> **Clarification — Synth `<soundParams>` attributes (44 total):**
> 
> `arpeggiatorGate`, `portamento`, `compressorShape`, `oscAVolume`, `oscAPulseWidth`, `oscAWavetablePosition`, `oscBVolume`, `oscBPulseWidth`, `oscBWavetablePosition`, `oscBPitchAdjust`, `noiseVolume`, `volume`, `pan`, `lpfFrequency`, `lpfResonance`, `hpfFrequency`, `hpfResonance`, `lfo1Rate`, `lfo2Rate`, `modulator1Amount`, `modulator1Feedback`, `modulator2Amount`, `modulator2Feedback`, `carrier1Feedback`, `carrier2Feedback`, `modFXRate`, `modFXDepth`, `delayRate`, `delayFeedback`, `reverbAmount`, `arpeggiatorRate`, `stutterRate`, `sampleRateReduction`, `bitCrush`, `modFXOffset`, `modFXFeedback`, `compressorThreshold`, `lpfMorph`, `hpfMorph`, `waveFold`, `ratchetProbability`, `ratchetAmount`, `sequenceLength`, `rhythm`
> 
> **Child elements:** `<envelope1>` (attack, decay, sustain, release), `<envelope2>` (attack, decay, sustain, release), `<patchCables>` (each with source, destination, amount — can be nested with `<depthControlledBy>`), `<equalizer>` (bass, treble, bassFrequency, trebleFrequency)
> 
> **Kit `<kitParams>` attributes (15 total):**
> 
> `reverbAmount`, `volume`, `pan`, `sidechainCompressorShape`, `modFXDepth`, `modFXRate`, `stutterRate`, `sampleRateReduction`, `bitCrush`, `modFXOffset`, `modFXFeedback`, `compressorThreshold`, `lpfMorph`, `hpfMorph`, `tempo`
> 
> **Kit child elements:** `<delay>` (rate, feedback), `<lpf>` (frequency, resonance), `<hpf>` (frequency, resonance), `<equalizer>` (bass, treble, bassFrequency, trebleFrequency)
> 
> Note: Kit row `<soundParams>` use the same attribute set as synth `<soundParams>`.
> 
> **Instrument structural elements (on `<sound>` definition, NOT in soundParams):**
> 
> These define the fundamental character of the instrument and are equally important for comparison:
> 
> - `<sound>` root attributes: `polyphonic`, `voicePriority`, `mode`, `transpose`, `modFXType`, `lpfMode`, `hpfMode`, `filterRoute`, `maxVoices`, `clippingAmount`
> - `<osc1>`: `type` (square/saw/sine/triangle/analogSquare/analogSaw/sample/wavetable), `transpose`, `cents`, `retrigPhase`; for samples: `loopMode`, `reversed`, `timeStretchEnable`, `timeStretchAmount`, `fileName`, plus `<zone>` child
> - `<osc2>`: same attributes as osc1
> - `<lfo1>`: `type`, `syncLevel`, `syncType`
> - `<lfo2>`: `type`, `syncLevel`, `syncType`
> - `<unison>`: `num`, `detune`, `spread`
> - `<modulator1>` (FM only): `transpose`, `cents`, `retrigPhase`
> - `<modulator2>` (FM only): `transpose`, `cents`, `retrigPhase`, `toModulator1`
> - `<delay>`: `pingPong`, `analog`, `syncLevel`, `syncType`
> - `<sidechain>`: `attack`, `release`, `syncLevel`, `syncType`
> - `<audioCompressor>`: `attack`, `release`, `thresh`, `ratio`, `compHPF`, `compBlend`
> 
> Note: FM synths omit `type` on oscillators, use `<compressor>` instead of `<audioCompressor>`, and may omit some attributes on `<lfo>`, `<unison>`, and `<delay>` elements.

The Instrument structural elements represent major changes to an instrument.  If any of these are altered, the instrument should be extracted.

Similarly, envelope (ADSR), patch cable, arpeggiator settings can signify big changes.  Any setting that is non-numerical i.e. represents a mode or similar is grounds for treating a version as distinct.

For other numerical values, follow the guidance from q10.  


12. **Should the difference detection compare the clip `<soundParams>` attributes only, or also compare structural elements like oscillator settings (which are shared across all clips of the same instrument)?**

Treat all settings as changeable. Structural elements like oscillator settings may vary between clips of the same instrument.  This represents a significant change between instruments.

---

## Output Format & Naming (13–20)

13. **For default mode, the proposed filename is `<SongName>-<PresetName>.XML`. If a song has two _different_ instruments with the same `presetName` (loaded from different folders), how should the collision be handled?** For example, two instruments both named "000" but from different `presetFolder` paths.

Add a number to the end

14. **Should the `presetFolder` path be reflected in the output filename or directory structure?** For example, an instrument from `SYNTHS/KERERU` could be saved as `SONG-SYNTHS/KERERU/SongName-PresetName.XML` or flat as `SONG-SYNTHS/SongName-PresetName.XML`.

No.  Keep it flat.

15. **How should special characters in `presetName` or `SongName` be handled for filenames?** Observed names include spaces ("41-VIOLINE 3"), numeric-only ("133"), and hyphens. Should spaces be replaced, or kept as-is (the Deluge handles spaces in filenames)?

Deluge handles spaces.  Keep as is. 

16. **For extended mode filenames, is `<SongName>-<PresetName>-<SectionId>.XML` acceptable, or would you prefer a human-readable colour name (e.g. `<SongName>-<PresetName>-LightBlue.XML`)?**

Human readable-ish.  Map the colours to a three letter abbreviation and use that.

17. **Should the extracted XML files include the `presetName` attribute (as they would if saved from the Deluge), or is the filename alone sufficient for identification?**

Is the presetName attribute typically in standalone xmls?  The format of extracted XMLs should match that of regular xmls.

> **Clarification:** No. Standalone preset XMLs do **not** have a `presetName` attribute. Checked Init-Synth.XML, K01Bass.XML, Init-Kit.XML, and Deeper.XML — none have `presetName` on the root element. The `presetName` only appears on `<sound>` and `<kit>` elements when they are embedded inside a song's `<instruments>` section. The Deluge identifies standalone presets by their filename, not an XML attribute. Extracted XMLs should therefore **not include** `presetName`.

Yeah do that then. 

18. **Should the output directories (`SONG-SYNTHS/`, `SONG-KITS/`) be created at the top level of the type folder (e.g. `DELUGE/SYNTHS/SONG-SYNTHS/`) or nested differently?**

top

19. **Would it be useful to generate a manifest/summary file alongside the extracted presets?** For example, a CSV or JSON mapping each extracted file to its source song, instrument name, colour, and key parameters.

yes

20. **For songs with version suffixes (e.g. `Oddish.XML`, `Oddish 2.XML`, `Oddish 3.XML`), should only the latest version be processed, or all versions?**

all

---

## Volume & Pan Normalisation (21–26)

21. **The init synth has `volume="0x4CCCCCA8"` and the init kit has `volume="0x3504F334"`. Should extracted synths use the init synth volume value and extracted kits use the init kit volume value?**

yes

22. **For kit rows, you want to preserve row-level volume. Should this be the raw value from the clip's `<soundParams>`, or should it be scaled relative to the kit master volume being normalised?** For example, if the original kit master was 50% and a row was at 80%, normalising the master to 100% might make the row disproportionately loud.

Take the value exactly as it is set in the embedded xml

23. **Pan normalisation: you want master pan set to centre (`0x00000000`) but kit row pan preserved. What about synth-level parameters like `oscBPitchAdjust` that might be considered "balance" settings — are those always preserved?**

synth level setting preserved.  Only volume and pan should be normalized.

24. **Are there any other parameters besides `volume` and `pan` that should be normalised/standardised across extractions?** For example, reverb send amounts, delay settings, or sidechain settings that are song-context-dependent.

no, not at this point.  But perhaps we could use an extendable list of attributes to ignore?

25. **Should the volume normalisation happen on the `<defaultParams>` level only, or also on parameters within `<patchCables>` that might route to volume?** Patch cables can include `destination="volume"` entries.

I need you to clarify this point. There should only be one volume setting to change, the one that represents master volume of the entire synth or kit. 

> **Clarification:** There are actually **two places** where volume appears:
> 
> 1. **`volume` attribute on `<defaultParams>`** — e.g. `<defaultParams volume="0x4CCCCCA8" ...>`. This is the master volume knob for the instrument. **This is the one to normalise.**
> 
> 2. **`<patchCable>` entries with `destination="volume"`** — e.g. `<patchCable source="velocity" destination="volume" amount="0x3FFFFFE8" />`. The init synth has two: velocity→volume and aftertouch→volume. These control how much velocity/aftertouch *modulates* the volume — they are not the volume level itself, but rather how responsive the volume is to playing dynamics.
> 
> **Recommendation:** Normalise only #1 (the `volume` attribute on `<defaultParams>`). Leave the patchCable volume destinations untouched — they represent the user's performance sensitivity settings, not the overall loudness level.

We only want to normalise the master volume

26. **The `<songParams>` section has its own `volume` value. Is this distinct from and irrelevant to the instrument-level volume we're normalising?** (Research indicates yes, but confirming.)

Probably, yes. There are song level params to affect all clips at once, including volume, EQ, reverb, filters, stutter, delay, and more.  Song level attributes can be ignored.  We are only concerned with clip level settings. 

---

## Extraction Logic & Edge Cases (27–35)

27. **If a kit clip has fewer `<noteRow>` entries than the instrument has `<sound>` entries in `<soundSources>`, should the missing rows get default parameters (from Init-Kit.XML) or should they be omitted?**

Clarify this.  What is noteRow?  Why is it relevnat?

> **Clarification:** In kit clips, `<noteRow>` elements are how the song stores per-drum-row data. Each kit has multiple sounds (drums/samples) defined in `<soundSources>`. In the clip, each `<noteRow>` contains:
> - `drumIndex` — which sound in the kit this row corresponds to (0 = first sound, 1 = second, etc.)
> - `<soundParams>` — the per-row parameter values (volume, pan, filter, envelopes, etc.)  
> - `noteDataWithLift` — the actual note/sequencing data (not relevant for extraction)
> 
> During extraction, each `<noteRow>`'s `<soundParams>` must be renamed to `<defaultParams>` and inserted into the corresponding `<sound>` in `<soundSources>` (matched by `drumIndex`). If a kit has 5 sounds but the clip only has 3 noteRows, 2 sounds would be missing their parameter values. Options: use Init-Kit defaults, or skip those sounds. This is mostly theoretical — in practice, clips usually have a noteRow for every sound in the kit.

I don't understand how there would ever not be the correct amount of noterow entries.  That sounds like a broken xml.

28. **If a `noteRow` references a `drumIndex` that doesn't exist in the kit's `<soundSources>`, should it be dropped with a warning, or should the extraction fail?**

Clarify this.  What is noteRow?  Why is it relevnat?

> **Clarification:** This is the inverse edge case — a noteRow references a drumIndex that's out of range of the `<soundSources>` list (e.g. drumIndex="5" but only 4 sounds exist). This would be a data inconsistency in the song XML. Recommendation: drop the noteRow with a warning and continue extraction.

I don't understand how there would ever not be the correct amount of noterow entries.  That sounds like a broken xml.

29. **Should the script verify that extracted kits still reference valid sample paths (using the existing `verify_references.py` logic)?** This could catch broken references before users load the presets.

No, I can verify. 

30. **How should the `.trash` mechanism work for replacing previous extractions?** Options: (a) trash the entire `SONG-SYNTHS/` directory, (b) trash individual files that would be overwritten, (c) delete and recreate. What's your preference?

trash the entire `SONG-SYNTHS/` or `SONG-KITS/` dir and replace.  We may refine this in a later version of the script.

31. **Should the script emit warnings for instruments with `presetName` matching numeric factory presets (e.g. "000", "133")?** These are likely modified versions of factory presets, which may or may not be interesting to extract.

extract all synths and kits regardless of their original source

32. **The `affectEntire` attribute on `<instrumentClip>` controls whether the user is editing kit-level or row-level params. Does this affect which parameters to extract, or is it purely a UI state indicator?**

Likely just a UI indicator

33. **If `<soundParams>` contains automation data (parameter changes over time), should the extracted preset use the initial value, or should automation be stripped entirely?** Research did not find inline automation in the examined clips, but it may exist.

Keep automation data

34. **Should the firmware version check be a hard fail (abort the script) or a warning (skip the song and continue)?** The feature notes say all songs are `c1.2.1`, but future syncs might bring different versions.

warn, skip and continue

35. **The `<arpeggiator>` element appears in both the instrument definition and inside clips. Should the clip's arpeggiator settings override the instrument's, or should the instrument's be kept?**

Provide an example for me to make this decision

> **Clarification:** Here's a concrete example from K01Sink.XML. The synth "K01Arp" has its arpeggiator configured at the **clip level**, not in the instrument definition:
> 
> **Clip-level arpeggiator (section 4):**
> ```xml
> <arpeggiator
>     mode="arp"
>     syncLevel="6"
>     numOctaves="2"
>     syncType="0"
>     arpMode="arp"
>     noteMode="up"
>     octaveMode="up"
>     mpeVelocity="off" />
> ```
> 
> The instrument definition in `<instruments>` has **no** `<arpeggiator>` child — for synths, the arpeggiator lives entirely at the clip level.
> 
> Another example: K01Twinlke1 in K09Arparty.XML has `mode="arp"`, `noteMode="down"`, `octaveMode="down"` — clearly customised per clip.
> 
> **Key point for kits:** Kit sounds (`<sound>` elements inside `<soundSources>`) DO keep their `<arpeggiator>` in the instrument definition. Only synth-level arpeggiators are stored at clip level.
> 
> **The decision:** For synth extraction, the clip's arpeggiator is the only source — use it. There is no instrument-level arpeggiator to conflict with.

---

## Implementation & Integration (36–40)

36. **Should this be a standalone script (e.g. `extract_instruments.py`) or a subcommand of an existing script?** Existing scripts are standalone with their own entry points.

standalone

37. **Should the script add its own entry point in `pyproject.toml` (e.g. `deluge-extract = "extract_instruments:main"`)?** This follows the pattern of other scripts.

yes

38. **Should any of the extraction logic (e.g. instrument discovery, parameter merging) be added to `deluge_sdk.py` as reusable functions, or should it be self-contained in the new script?**

reuseable

39. **How verbose should the output be?** Should it list every extracted instrument, or just a summary (e.g. "Extracted 45 synths and 12 kits from 58 songs")?

list each one, plus a summary

40. **Should the script support a `--dry-run` flag consistent with other scripts?** This would list what would be extracted without writing any files.

yes
