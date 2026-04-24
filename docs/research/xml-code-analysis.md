# XML Code Analysis — Extraction Code vs XML Structure Research

> **Document Type:** Analysis
> **Created:** 24 April 2026
> **Scope:** `scripts/deluge_lib/extraction.py`, `scripts/extract_instruments.py`, `scripts/deluge_lib/deluge_sdk.py`, `scripts/deluge_lib/scanning.py`
> **Reference:** `docs/research/xml-structure-research.md` (ground truth)

---

## Summary of Findings

| Severity | Count | Description |
|----------|-------|-------------|
| **BUG** | 2 | Issues that produce incorrect output or data loss |
| **IMPROVEMENT** | 8 | Working code that could be more accurate, robust, or clear |
| **ENHANCEMENT** | 6 | New capabilities or features worth adding |
| **OK** | 16 | Verified correct behaviour |

---

## 1. Warnings Analysis

### 1.1 Current Warning: Firmware Version Mismatch

**Location:** `extraction.py` → `discover_songs()` (line ~523)
```
WARNING: Skipping {name} — firmware {firmware!r} (expected 'c1.2.1')
```

**Assessment:** [OK] Correct and useful. The XML structure changed significantly between firmware versions. Skipping non-c1.2.1 songs prevents misinterpretation. The warning text is clear.

---

### 1.2 Current Warning: Failed to Parse XML

**Location:** `extraction.py` → `discover_songs()` (line ~511)
```
WARNING: Skipping {name} — failed to parse XML: {exc}
```

**Assessment:** [OK] Correct safety net. The `parse_deluge_xml()` three-stage fallback in `deluge_sdk.py` is robust; this warning only fires if all three stages fail.

---

### 1.3 Current Warning: No `<song>` Root Element

**Location:** `extraction.py` → `discover_songs()` (line ~517)
```
WARNING: Skipping {name} — no <song> root element found
```

**Assessment:** [OK] Defensive. Could fire for non-song XMLs accidentally placed in the SONGS/ directory.

---

### 1.4 Current Warning: Missing Section Attribute on Clip

**Location:** `extraction.py` → `discover_clips()` (line ~606)
```
WARNING: <instrumentClip> for {name!r} has no section attribute — treating as section 0
```

**Assessment:** [IMPROVEMENT] The warning text is correct, but the scenario is unusual. Per the XML research, all `<instrumentClip>` elements in c1.2.1 firmware have a `section` attribute. This warning might indicate corrupt or manually edited XML. Consider adding "this may indicate a corrupt or pre-c1.2.1 file" to the message.

**Recommendation:** Append contextual hint: `"— treating as section 0 (may indicate corrupt XML)"`.

---

### 1.5 Current Warning: Orphaned Instrument

**Location:** `extraction.py` → `match_instruments_to_clips()` (line ~658)
```
Orphaned instrument {name!r} (folder={folder!r}, type={type}) — no matching session clips
```

**Assessment:** [IMPROVEMENT] Functionally correct, but the warning text is misleading. Per XML research Section 5, instruments can legitimately have clips only in `<arrangementOnlyClips>`. The current warning makes this sound like an error when it's expected Deluge behaviour.

An instrument is "orphaned" from the extraction perspective (no session clips to source parameters from), but not orphaned from the song's perspective. The warning should distinguish between:
- Instruments with arrangement-only clips (normal, expected)
- Instruments with no clips at all (unusual — typically happens after clip deletion, Section 11)
- MIDI and audio track instruments (always skipped, never warned about — this is correctly handled)

**Recommendation:** Check `<arrangementOnlyClips>` for matching clips. If found, change text to: `"Instrument {name!r} has arrangement-only clips — session clips required for extraction (skipped)"`. If no clips at all: `"Orphaned instrument {name!r} — no clips in session or arrangement view"`.

---

### 1.6 Current Warning: Duplicate Clip in Same Section

**Location:** `extraction.py` → `match_instruments_to_clips()` (line ~676)
```
Duplicate clip for {name!r} in section {section_label}, taking first
```

**Assessment:** [OK] Correct handling. Per XML research, the Deluge allows multiple clips for the same instrument in the same section. Taking the first is a reasonable deterministic choice. The warning text is clear.

---

### 1.7 Current Warning: Unexpected Section ID

**Location:** `extract_instruments.py` (line ~171)
```
WARNING: ({preset_name}) — unexpected section ID {section_id}, treating as section 0
```

**Assessment:** [OK] Defensive. The Deluge uses sections 0–11. Any value outside this range would indicate corrupt data. The fallback to section 0 is safe.

---

### 1.8 Current Warning: Kit Sound Missing Default Params

**Location:** `extraction.py` → `_ensure_all_sounds_have_default_params()` via `extract_instruments.py` (line ~188)
```
WARNING: ({preset_name}, section {section_id}/{colour_name}) — Kit sound {name!r} (index {idx}) has no clip parameters — using defaults
```

**Assessment:** [IMPROVEMENT] Functionally correct — this fires when a kit sound exists in `<soundSources>` but the selected clip's `<noteRows>` doesn't include a `<noteRow>` with that `drumIndex`. Per XML research Section 11, this is **normal and expected**: deleting a row from a clip removes the `<noteRow>` but the sound persists in `<soundSources>`. Different clips can reference different subsets of sounds.

The warning text "has no clip parameters — using defaults" is accurate but the tone suggests an error. This is routine for kits where the user deleted rows.

**Recommendation:** Downgrade this from WARNING to NOTE. Change text to: `"Kit sound {name!r} not used in this clip — applying init defaults"`. Consider suppressing entirely if the kit has multiple clips and the sound appears in at least one.

---

### 1.9 Current Warning: drumIndex Out of Range

**Location:** `extraction.py` → `extract_kit()` (line ~868)
```
WARNING: drumIndex {drum_index} out of range (soundSources has {len(sounds)} sounds) — skipping noteRow
```

**Assessment:** [OK] Correct safety check. This would indicate corrupt XML data. The skip behaviour is safe.

---

### 1.10 Missing Warning: noteRow Without soundParams

**Location:** `extraction.py` → `_merge_noterow_params()` (line ~1644)
```
WARNING: noteRow (drumIndex={drum_index}) has no <soundParams> — skipping
```

**Assessment:** [IMPROVEMENT] This warning prints to stdout but the message is never surfaced through the warning pipeline in `extract_kit()`. The function returns a list but the `_merge_noterow_params` return value is silently discarded in `extract_kit()`'s loop. The warning is printed directly but not included in `default_param_warnings`.

**Recommendation:** Collect the return value from `_merge_noterow_params()` and include any warnings in the result. Currently the print is the only signal.

---

### 1.11 Missing Warning Scenarios

**Assessment:** [ENHANCEMENT] The following XML scenarios should produce warnings but currently don't:

1. **Sidechain-only kits being extracted** — Per XML research Section 12, kits that function purely as sidechain triggers (single KICK sound with max `sideChainSend`, very low volume) are not useful standalone presets. The script extracts them without comment.

2. **Songs in `testing/` subdirectory** — Test songs (Duppy, Triggy series) in `DELUGE/SONGS/testing/` are extracted alongside real songs. Consider adding an option to exclude test directories, or at minimum note that test songs were found.

---

## 2. XML Field Coverage

### 2.1 `pitchAdjust` Attribute on Kit noteRow soundParams

**Assessment:** [BUG] The `pitchAdjust` attribute appears on `<soundParams>` elements within kit `<noteRow>` elements in real song data (verified in K01Sink.XML, No-More-Colour.XML, Japarps.XML). It is a hex-encoded parameter that adjusts the pitch of individual kit row sounds.

The extraction code correctly copies `<soundParams>` from noteRows to `<defaultParams>` via `_merge_noterow_params()`, so `pitchAdjust` IS preserved in extracted presets (it's copied as part of the deep clone). **However:**

1. The `_create_init_default_params()` fallback does NOT include `pitchAdjust`. When a sound receives fallback defaults (no matching noteRow), it gets no `pitchAdjust` attribute at all. This is **acceptable** because init kits don't have `pitchAdjust` (it's `0x00000000` / absent by default).

2. The `oscBPitchAdjust` attribute on synth `<soundParams>` (seen in Paddy.XML, Bloop.XML) is similarly preserved through the deep clone path and absent from the init fallback. Same acceptable behaviour.

3. Neither `pitchAdjust` nor `oscBPitchAdjust` are in the comparison engine's ignored list or hard markers. They will be caught as soft markers during comparison — this is **correct** behaviour since pitch changes are musically meaningful.

**Revised assessment:** [OK] — The deep clone approach handles these attributes correctly. The init fallback omission is acceptable (default is absent/zero). No code changes needed.

---

### 2.2 `depthControlledBy` Nested PatchCables

**Assessment:** [IMPROVEMENT] Per XML research Section 8, patchCables can contain nested `<depthControlledBy>` elements with sub-patchCables. The extraction code's deep clone of `<soundParams>` correctly preserves these nested structures. However, the comparison engine's `_build_patchcable_dict()` and `_check_patchcable_structure()` functions only examine top-level patchCables — they do NOT compare nested `<depthControlledBy>` children.

This means two instruments with identical top-level routing but different modulation depths on those routings would NOT be flagged as structurally different (hard marker miss). The depth *amounts* would be caught by the soft marker pass, but the nested *structure* (e.g. one has envelope2 controlling LFO depth, the other doesn't) would be missed.

**Recommendation:** Extend `_check_patchcable_structure()` to also compare `<depthControlledBy>` children. For hard markers, check whether sub-patchCable `source` attributes differ. For soft markers, compare sub-patchCable `amount` values.

---

### 2.3 `sideChainSend` Attribute on Kit Sounds

**Assessment:** [OK] The `sideChainSend` attribute on `<sound>` elements within `<soundSources>` is a plain integer (not hex). It is preserved through the deep clone in `extract_kit()`. It is not referenced in the comparison config's hard or soft markers, meaning two kits with different `sideChainSend` values on their sounds would not be flagged as different unless other attributes also differ. This is acceptable for now — `sideChainSend` is a send routing parameter, not a structural or timbral attribute.

---

### 2.4 `noteDataWithLift` and Sequencing Data

**Assessment:** [OK] Note data (`noteDataWithLift` attribute on `<noteRow>`) is clip-specific and is correctly NOT copied to standalone presets. The extraction only takes `<soundParams>` from noteRows, not the note data. This matches the standalone preset format.

---

### 2.5 `clippingAmount` Attribute

**Assessment:** [OK] Listed as a hard marker for synths in `ComparisonConfig.default()`. This is correct — `clippingAmount` is a structural sound-shaping attribute present on `<sound>` elements. It's not present on init presets but appears on modified presets. Correctly treated as a hard differentiator.

---

### 2.6 Comparison Coverage Completeness

**Assessment:** [IMPROVEMENT] The comparison engine covers the main attributes but there are some gaps:

**Attributes compared that should be (OK):**
- Root element structural attrs: `mode`, `polyphonic`, `voicePriority`, `maxVoices`, `clippingAmount`, `modFXType`, `lpfMode`, `hpfMode`, `filterRoute` — all correct
- Oscillator: `type`, `fileName`, `transpose` — correct
- LFO: `type` — correct
- Unison: `num` — correct
- Arpeggiator: `mode`, `noteMode`, `octaveMode` — correct
- PatchCable structure — correct

**Attributes not compared that could be:**
- `osc1.loopMode` and `osc1.reversed` — included for kits but NOT for synths in `synth_hard_attrs`. These are present on synth oscillators too when using samples. **[IMPROVEMENT]**
- `osc1.retrigPhase` — not compared anywhere. Changes to oscillator retrigger phase could be musically significant. Minor.
- `unison.detune` and `unison.spread` — compared as soft markers via `synth_soft_elements` (skip set only excludes `num`). Correct.

**Recommendation:** Add `loopMode` and `reversed` to `synth_hard_attrs["osc1"]` and `synth_hard_attrs["osc2"]` to match the kit treatment.

---

## 3. Song vs Preset Understanding

### 3.1 `<soundParams>` (Song) vs `<defaultParams>` (Preset)

**Assessment:** [OK] The code correctly understands and implements this mapping:
- `extract_synth()` renames `<soundParams>` from the clip to `<defaultParams>` (line ~765)
- `extract_kit()` renames `<kitParams>` to `<defaultParams>` at kit level (line ~847)
- `_merge_noterow_params()` renames per-row `<soundParams>` to `<defaultParams>` (line ~1639)

This matches XML research Section 4: "`<soundParams>` in a song clip is structurally equivalent to `<defaultParams>` in a standalone preset. Extraction requires renaming the tag."

---

### 3.2 Split Architecture (Instrument Definition + Clip Parameters)

**Assessment:** [OK] The code correctly handles the split architecture:
- Instrument structure (oscillators, effects routing, samples) comes from `<instruments>` → deep cloned
- Tuneable parameters come from `<instrumentClip>` → extracted and merged
- Song-specific attributes are stripped (presetName, presetFolder, etc.)
- Firmware version attributes are added

This matches XML research Section 3: "The instrument definition in a song does NOT contain `<defaultParams>`. Tuneable parameters live in the clip's `<soundParams>`."

---

### 3.3 Kit `<kitParams>` → Kit-Level `<defaultParams>`

**Assessment:** [OK] `extract_kit()` correctly:
1. Extracts `<kitParams>` from the clip
2. Renames to `<defaultParams>`
3. Inserts as the FIRST child of `<kit>` (matching standalone format)

This "affect entire" params block contains kit-level reverb, volume, pan, filters, etc. The ordering is verified by `_reorder_kit_children()` which places `defaultParams` first in the child order.

---

### 3.4 Kit Arpeggiator Asymmetry

**Assessment:** [OK] The code correctly handles the kit arpeggiator asymmetry documented in the extraction plan. For synths, the arpeggiator is extracted from the clip and cleaned. For kits, the arpeggiator is already in the instrument definition's `<soundSources>` sounds and is left in place. The `_extract_arpeggiator_from_clip()` function returns `None` for kit clips (no clip-level arpeggiator).

---

## 4. Duplication Check Analysis

### 4.1 Hard/Soft/Ignore Marker Classifications

**Assessment:** [OK] The three-tier system is well-designed:

**Hard markers (structural identity):**
- Synth: `mode`, `polyphonic`, `voicePriority`, `maxVoices`, `clippingAmount`, `modFXType`, `lpfMode`, `hpfMode`, `filterRoute`, osc types/samples/transpose, LFO types, unison count, arpeggiator mode, patchCable routing structure — all correct
- Kit: same per-sound structural attrs plus `soundSources` count and names — correct

**Soft markers (numerical differences):**
- All hex params on `<defaultParams>`, envelopes, equalizer, patchCable amounts, delay/sidechain/audioCompressor, osc cents, LFO sync — comprehensive

**Ignored:**
- `volume`, `pan` — correct (normalised, so always identical post-extraction)
- `firmwareVersion`, `earliestCompatibleFirmware` — correct (always set to constants)
- `modFXCurrentParam`, `currentFilterType` — correct (UI state, not musical content)

---

### 4.2 `_HEX_FULL_RANGE` Value

**Assessment:** [IMPROVEMENT] Currently set to `0x7FFFFFFF` (2,147,483,647 — the positive half of the signed range). The comment explains this means the 10% threshold corresponds to ~2.5 display units on a 0–50 scale.

Per XML research Section 6, the full signed range spans `0x80000000` (−2,147,483,648) to `0x7FFFFFFF` (+2,147,483,647) — a total span of `0xFFFFFFFF` (4,294,967,295). Using `0x7FFFFFFF` as the denominator means the threshold is calculated against the positive half only, not the full range.

For a 10% threshold:
- With `0x7FFFFFFF`: 10% = ~214M raw units ≈ 2.5 display units (0–50 scale)
- With `0xFFFFFFFF`: 10% = ~429M raw units ≈ 5 display units (0–50 scale)

The current value is more conservative (flags smaller differences). This seems intentional per the comment "Adjust during testing if needed." The choice is defensible — keeping two versions that differ by 2.5+ display units across 3+ parameters is reasonable.

**Recommendation:** Document the actual display-unit equivalence more explicitly in the comment. Consider whether the threshold should differ for 0–50 params vs −50 to +50 params (currently it doesn't — the proportional calculation is the same regardless).

---

### 4.3 Dedup Grouping Strategy

**Assessment:** [IMPROVEMENT] The two-pass dedup strategy is:

1. **Pass 1 (by name):** Groups by `(preset_name, instrument_type)`, sorts by `song_name`
2. **Pass 2 (global):** Groups by `(instrument_type,)` only, sorts by `(preset_name, song_name)`

**Issue:** Pass 1 groups by `preset_name` but NOT `preset_folder`. This means instruments with the same name but different folders (e.g. `"Init-Synth"` in `"SYNTHS"` vs `"SYNTHS/KERERU"`) would be grouped together and potentially deduped as identical. Per XML research Section 13, preset identity is determined by `(presetName, presetFolder)` — not name alone.

In practice, instruments with the same name in different folders are likely different presets (e.g. a user's custom "Bass" vs a factory "Bass"). The comparison engine would catch structural differences and keep them. But if two folders contain genuinely identical presets with the same name, the name-pass sort by `song_name` determines which is kept — this is arbitrary rather than folder-aware.

**Recommendation:** Add `preset_folder` to the name-pass group key: `group_key=lambda r: (r.preset_name, r.preset_folder, r.instrument_type)`. This ensures presets from different folders are never grouped together in pass 1. Pass 2 (global) would still catch cross-folder duplicates via structural comparison.

---

### 4.4 Dedup Sort Stability

**Assessment:** [OK] Within each dedup group, results are sorted by `song_name` (pass 1) or `(preset_name, song_name)` (pass 2). The first result becomes the baseline and is always kept. This is deterministic and predictable. Songs are processed in alphabetical order by name.

---

### 4.5 Dedup Performance

**Assessment:** [ENHANCEMENT] The global pass groups ALL accepted results by instrument type and compares each against all previously accepted in the group. For N accepted synths, this is O(N²) comparisons. With the current song count (~50 songs), this is fast. At scale (hundreds of songs with hundreds of synths), it could slow down.

**Recommendation:** No immediate action needed. If performance becomes an issue, consider a hashing-based pre-filter (e.g. hash the set of hard marker values and only run full comparison within hash-collision groups).

---

## 5. Edge Cases and Blind Spots

### 5.1 Arrangement-Only Instruments

**Assessment:** [OK — by design, with improvement opportunity] Per the extraction plan (D13), arrangement-only clips are deliberately excluded. `discover_clips()` only reads `<sessionClips>`. This means instruments that exist solely in `<arrangementOnlyClips>` are reported as orphaned and skipped.

This is a documented design decision but the orphan warning is misleading (see Section 1.5 above). The instrument's parameters exist in the arrangement clips but are inaccessible to the current extraction pipeline.

**Recommendation:** See Section 1.5 for warning text improvement. Consider a future `--include-arrangement` flag as an enhancement.

---

### 5.2 "No Sound" Rows

**Assessment:** [OK] Per XML research Section 9, "no sound" rows have no `drumIndex` attribute. The extraction code in `extract_kit()` correctly skips noteRows without `drumIndex`:
```python
drum_index_str = noterow.get("drumIndex")
if drum_index_str is None:
    continue
```
These rows contribute no parameters and are correctly ignored.

---

### 5.3 Muted Rows

**Assessment:** [OK] Per XML research Section 10, muted rows retain their full `<soundParams>` and `drumIndex`. The extraction code does not check `muted` status — it extracts parameters from all noteRows regardless. This is correct: mute state is clip-specific and should not affect the standalone preset.

---

### 5.4 Kit Sounds with Deleted Rows Across Clips

**Assessment:** [OK] The safety pass `_ensure_all_sounds_have_default_params()` correctly handles this scenario. When a sound exists in `<soundSources>` but the selected clip has no matching `<noteRow>` (because the user deleted that row in that clip), the safety pass provides fallback defaults.

The template selection strategy is sound:
1. First, try to clone `<defaultParams>` from a sibling sound in the same kit
2. If no sibling has one, use `init_template` from Init-Kit.XML
3. Last resort: use `_create_init_default_params()` hardcoded values

**However:** [IMPROVEMENT] If the instrument has multiple clips and one of the OTHER clips does have a noteRow for the missing sound, the code doesn't look there. It only uses the selected clip. This means a sound that's deleted in section 0 (the default extraction source) but present in section 1 gets fallback defaults instead of the actual parameters from section 1.

**Recommendation:** Before applying fallback defaults, scan all clips in the group for a noteRow matching the missing drumIndex. Use those actual parameters if found. This would produce more accurate presets.

---

### 5.5 Sidechain-Only Kits

**Assessment:** [ENHANCEMENT] Per XML research Section 12, sidechain-only kits follow a recognisable pattern: single KICK sound with max `sideChainSend`, very low volume, only one row sequenced. These kits function as sidechain triggers and are not useful as standalone presets.

The current code extracts them without any special handling. The extracted preset is technically valid but musically useless.

**Recommendation:** Add sidechain-kit detection as a heuristic. Criteria from the XML research:
1. Kit has only 1 sound with `sideChainSend="2147483647"` (or near max)
2. Kit-level or row-level volume is very low
3. Optionally: only 1 noteRow has `noteDataWithLift`

If detected, either skip with a note or add a `[sidechain]` tag to the warning output. Do NOT suppress silently — the user should know.

---

### 5.6 Songs in Subdirectories

**Assessment:** [OK] The `discover_songs()` function uses `scan_tree()` which calls `os.walk()` recursively. Songs in subdirectories (e.g. `DELUGE/SONGS/testing/`) are correctly discovered and processed. The `scan_tree()` function also correctly skips `.trash` directories.

No issues found with recursive scanning.

---

### 5.7 Same presetName, Different presetFolder — Dedup Handling

**Assessment:** [BUG] The name-pass dedup groups by `(preset_name, instrument_type)` without considering `preset_folder`. This means:

- `"Bass"` from `"SYNTHS"` and `"Bass"` from `"SYNTHS/KERERU"` are grouped together
- The comparison engine runs and may flag them as identical if they happen to share the same structure
- If they ARE structurally identical, one gets rejected — but the kept one may be from the "wrong" folder

More importantly, the `preset_folder` is metadata that indicates the preset's origin/category. Two presets with the same name from different folders are conceptually distinct even if structurally identical (the user chose to organise them differently).

**Recommendation:** Include `preset_folder` in the name-pass group key (see Section 4.3). The global pass would still catch genuine structural duplicates across folders.

---

## 6. Value Accuracy

### 6.1 Hardcoded Init Values

**Assessment:** [OK] All three hardcoded constants match the XML research Section 6 reference values:

| Constant | Value | XML Research Match |
|----------|-------|--------------------|
| `SYNTH_INIT_VOLUME` | `0x4CCCCCA8` | ✓ Init-Synth default (~35 display) |
| `KIT_INIT_VOLUME` | `0x3504F334` | ✓ Init-Kit default (~27 display) |
| `CENTRE_PAN` | `0x00000000` | ✓ Centre pan (0 display) |

The `load_init_defaults()` function also reads from actual Init-Synth.XML and Init-Kit.XML files when available, falling back to these constants only if the files are missing. This is the correct approach.

---

### 6.2 `_create_init_default_params()` Accuracy

**Assessment:** [OK with minor note] The hardcoded fallback creates a comprehensive `<defaultParams>` element. Comparing against the XML research:

**Verified correct values:**
- `volume="0x4CCCCCA8"` — matches Init-Synth default for per-sound volume
- `pan="0x00000000"` — centre
- `lpfFrequency="0x7FFFFFFF"` — fully open (max)
- `lpfResonance="0x80000000"` — minimum
- `hpfFrequency="0x80000000"` — minimum (off)
- `oscAVolume="0x7FFFFFFF"` — max
- `oscBVolume="0x80000000"` — min (off)
- `compressorShape="0xDC28F5B2"` — matches init default for both synths and kits
- envelope1: `attack="0x80000000"`, `decay="0xE6666654"`, `sustain="0x7FFFFFD2"`, `release="0x80000000"` — matches init values (sustain near-max, fast attack, moderate decay)
- `patchCable source="velocity" destination="volume" amount="0x3FFFFFE8"` — matches init default
- equalizer: all zeros — correct

**Note:** The function does NOT include `pitchAdjust` or `oscBPitchAdjust`. This is correct — these attributes are absent on init presets and only appear when the user has adjusted pitch on a kit row sound. Their absence is equivalent to `0x00000000` (no adjustment).

---

### 6.3 Hex Value Comparison Threshold

**Assessment:** [OK] The 10% proportional threshold with `_HEX_FULL_RANGE = 0x7FFFFFFF` means:
- Two values must differ by >214M raw units (>2.5 display units on a 0–50 scale) to count as a soft diff
- At least 3 parameters must exceed this threshold for an instrument to be flagged as distinct

Per XML research Section 6, the display→hex mapping is linear across the full signed range. The threshold is proportional, so it works equivalently for both 0–50 and −50 to +50 parameter ranges.

The `_parse_hex_value()` function correctly handles signed interpretation (values ≥ 0x80000000 are treated as negative by subtracting 0x100000000). It also correctly truncates automation strings to the base value.

---

### 6.4 Automation Stripping

**Assessment:** [OK] The `_strip_automation()` function uses a regex matching `0x` followed by 9+ hex characters. Normal Deluge hex values are 8 hex chars after `0x` (10 chars total, e.g. `0x4CCCCCA8`). Automation data extends this with additional keyframe data. The function truncates to the first 10 characters (the base value).

Per XML research Section 6: "When a parameter is automated, the base value is followed by keyframe pairs." The truncation approach is correct.

The `_parse_hex_value()` function in the comparison engine also handles extended strings by truncating to 10 chars, providing double protection.

---

## 7. Priority Summary

### Critical (BUG)

1. **Dedup groups by name without folder** (Section 5.7 / 4.3) — Presets with the same `presetName` but different `presetFolder` are incorrectly grouped in the name-pass dedup. Could reject a unique preset or keep the wrong one. **Fix:** Add `preset_folder` to the name-pass group key.

2. **`_merge_noterow_params()` warning not propagated** (Section 1.10) — Warnings from `_merge_noterow_params()` are printed but not included in the structured warning pipeline. The return value is discarded in `extract_kit()`. **Fix:** Collect return values and extend `default_param_warnings`.

### Important (IMPROVEMENT)

3. **Orphan warning doesn't distinguish arrangement-only instruments** (Section 1.5) — Check `<arrangementOnlyClips>` to provide better context in the warning message.

4. **Kit default-params warning should be NOTE, not WARNING** (Section 1.8) — Sounds not used in a clip getting defaults is normal behaviour, not an error.

5. **`depthControlledBy` not compared** (Section 2.2) — Nested patchCable modulation structure is not checked in hard marker comparison.

6. **Synth osc `loopMode`/`reversed` not in hard markers** (Section 2.6) — These are included for kits but missing for synths.

7. **Fallback defaults don't check other clips** (Section 5.4) — When a sound is missing from the selected clip, other clips in the group could provide actual parameters.

8. **`_HEX_FULL_RANGE` comment could be clearer** (Section 4.2) — Document the display-unit equivalence more explicitly.

### Nice-to-Have (ENHANCEMENT)

9. **Sidechain-only kit detection** (Section 5.5) — Flag or skip kits that function purely as sidechain triggers.

10. **Test song filtering** (Section 1.11) — Option to exclude songs from `testing/` subdirectory.

11. **Arrangement clip extraction** (Section 5.1) — Future `--include-arrangement` flag.

12. **Dedup performance optimisation** (Section 4.5) — Hash-based pre-filter for large song collections.

13. **Missing section warning context** (Section 1.4) — Append "may indicate corrupt XML" to the warning.

14. **Per-sound parameter sourcing from alternative clips** (Section 5.4) — Scan all group clips for missing sound parameters before falling back to defaults.
