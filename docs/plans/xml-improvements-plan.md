# Plan: XML Extraction & Dedup Improvements

> **Document Type:** Plan
> **Date:** 24 April 2026
> **Research:** [xml-code-analysis.md](../research/xml-code-analysis.md)
> **Pipeline:** Research → **Plan** → Implement
> **Status:** Draft

## Executive Summary

This plan addresses findings from the [code analysis](../research/xml-code-analysis.md) of the extraction and dedup code. It organises improvements into four independently shippable phases: sidechain kit detection (skip musically useless trigger kits), warning text improvements (clearer context for orphaned instruments and kit default-params notes), comparison engine refinements (nested patchCable structure and synth osc hard markers), and test song filtering (exclude `SONGS/testing/` subdirectory). Each phase builds on the existing codebase without new dependencies.

## Research Summary

The [xml-code-analysis.md](../research/xml-code-analysis.md) audited the extraction code (`extraction.py`, `extract_instruments.py`) against the [xml-structure-research.md](../research/xml-structure-research.md) ground truth. Key findings:

- **Sidechain-only kits** (analysis Section 5.5) are extracted as standalone presets despite being musically useless — they function purely as sidechain triggers. The XML structure research (Section 12) documents recognisable heuristics for detecting these kits.
- **Warning text** is misleading in two places: orphan warnings do not distinguish arrangement-only instruments (Section 1.5), and the kit default-params warning implies an error when it is normal behaviour (Section 1.8).
- **Comparison engine gaps**: nested `<depthControlledBy>` patchCable sub-structure is not compared (Section 2.2), and synth oscillator `loopMode`/`reversed` attributes are missing from hard markers despite being present for kits (Section 2.6).
- **`_merge_noterow_params()` warnings** are printed but not propagated into the structured warning pipeline (Section 1.10).
- **Test songs** in `SONGS/testing/` are extracted alongside real songs with no way to exclude them (Section 1.11).

The existing [extract-instruments-plan.md](extract-instruments-plan.md) is fully implemented (all 6 phases complete). This plan covers post-implementation improvements only.

## Decisions Log

| ID | Decision | Rationale | Alternatives Considered |
|----|----------|-----------|------------------------|
| D1 | Sidechain detection is on by default with `--include-sidechain` opt-out flag | Sidechain kits produce musically useless presets; most users want them excluded. Opt-out follows the same pattern as `--no-dedup` (default behaviour serves the common case). | Off by default with `--exclude-sidechain` (rejected — cluttered output is the common complaint); always skip without flag (rejected — user should have control) |
| D2 | Sidechain detection uses a multi-criteria heuristic, not a single check | Single criteria (e.g. only `sideChainSend` value) would produce false positives on normal kits that happen to use sidechain routing. The XML research Section 12 identifies a combination of indicators. | Single-criterion check (rejected — false positives); user-maintained exclusion list (rejected — manual overhead) |
| D3 | Detected sidechain kits print a NOTE-level message, not a WARNING | The kit is valid XML — it is simply not useful as a standalone preset. A NOTE communicates "we saw this and handled it" without implying an error. | WARNING (rejected — misleading); silent skip (rejected — user should know) |
| D4 | Orphan warning checks `<arrangementOnlyClips>` for matching clips to provide context | The current warning is misleading. Checking arrangement clips clarifies whether an instrument is arrangement-only (expected) vs truly orphaned (unusual). This matches the analysis Section 1.5 recommendation. | Leave warning as-is (rejected — misleading); extract arrangement-only instruments (rejected — out of scope, deferred per D13 in extraction plan) |
| D5 | Kit default-params message downgraded from WARNING to NOTE | Per analysis Section 1.8, sounds missing from a clip's noteRows is normal Deluge behaviour (user deleted that row in that clip). The current WARNING tone implies an error. | Keep as WARNING (rejected — causes unnecessary concern); suppress entirely (rejected — still useful information) |
| D6 | Add `depthControlledBy` sub-patchCable comparison to the comparison engine | Per analysis Section 2.2, nested modulation structure differences are currently missed. Two instruments with identical top-level routing but different modulation depth sources would not be flagged. | Ignore nested structure (rejected — misses legitimate structural differences); treat all depth differences as hard markers (rejected — amount differences within the same structure are soft) |
| D7 | Add `loopMode` and `reversed` to `synth_hard_attrs` for `osc1` and `osc2` | These attributes are already in `kit_hard_attrs` per-sound but missing for synths. Synth oscillators using samples have these attributes and changing them is a structural difference. Analysis Section 2.6. | Leave as-is (rejected — inconsistent treatment between synth and kit oscillators) |
| D8 | Propagate `_merge_noterow_params()` warnings into `default_param_warnings` | Analysis Section 1.10 identified that the return value from `_merge_noterow_params()` is discarded at line 873 of `extraction.py`. The warnings are printed but not collected. | Leave as-is (rejected — warnings pipeline is incomplete) |
| D9 | Test song filtering uses `--exclude-dir` flag with convention default for `testing/` | A general-purpose `--exclude-dir` flag is more flexible than hardcoding `testing/`. The flag accepts subdirectory names relative to `SONGS/`. Can be specified multiple times. No exclusions by default — the user opts in. | Hardcoded `testing/` exclusion (rejected — inflexible); automatic exclusion with `--include-testing` (rejected — surprising default behaviour for a new feature) |
| D10 | Dedup grouping by name without folder is NOT changed | Per orchestrator correction citing extraction plan D21: preset folder indicates load location, not identity. The global comparison pass catches cross-name structural duplicates. This is deliberate design, not a bug. | Add `preset_folder` to group key (rejected — contradicts D21) |

## Technical Specification

### 5a. Language and Tooling

No changes from the existing extraction plan. Same Python 3.12+, lxml, pytest, ruff stack. No new dependencies.

### 5b. Architecture

All changes are modifications to existing modules:

- `scripts/deluge_lib/extraction.py` — New sidechain detection function, updated warning text in `match_instruments_to_clips()` and `_ensure_all_sounds_have_default_params()`, extended comparison engine functions, `_merge_noterow_params()` warning propagation fix, updated `discover_songs()` for directory exclusion
- `scripts/extract_instruments.py` — New CLI flags (`--include-sidechain`, `--exclude-dir`), sidechain filtering step in the extraction pipeline, updated output formatting for sidechain notes
- `scripts/tests/test_extraction.py` — New test classes and cases for sidechain detection, updated warning tests, comparison engine extension tests, directory exclusion tests

### 5c. Interface Design

**New CLI flags:**

```
extract_instruments.py --include-sidechain    # Include sidechain-only kits (excluded by default)
extract_instruments.py --exclude-dir testing   # Exclude SONGS/testing/ from extraction
extract_instruments.py --exclude-dir testing --exclude-dir drafts  # Multiple exclusions
```

**New console output for sidechain detection:**

```
Bloop.XML
  SYNTH  133                → SONG-SYNTHS/Bloop-133.XML
  NOTE:  Kit "SC Kick" detected as sidechain-only — skipped (use --include-sidechain to extract)
```

**Updated orphan warning:**

```
# Before:
Orphaned instrument "049" (folder="SYNTHS/KERERU", type=synth) — no matching session clips

# After (arrangement-only case):
Instrument "049" has arrangement-only clips — session clips required for extraction (skipped)

# After (truly orphaned case):
Orphaned instrument "049" — no clips in session or arrangement view
```

**Updated kit default-params message:**

```
# Before:
WARNING: (Bloop, section 0/Light Blue) — Kit sound "KICK" (index 0) has no clip parameters — using defaults

# After:
NOTE: (Bloop, section 0/Light Blue) — Kit sound "KICK" not used in this clip — applying init defaults
```

### 5d. Integration Points

- **Sidechain detection** operates on assembled standalone kit elements (post-extraction, pre-output). It does not change the extraction pipeline — it filters results before writing.
- **Warning improvements** modify existing functions in `extraction.py`. No new integration points.
- **Comparison engine changes** extend existing private functions. The public `compare_instruments()` API is unchanged.
- **Directory exclusion** modifies `discover_songs()` to accept an exclusion list parameter. The CLI passes the flag values through.

## Cross-Cutting Concerns

| Concern | Mitigation |
|---|---|
| **Existing tests** | All existing tests must continue to pass. Warning text changes require updating test assertions that match on specific warning strings. |
| **Sidechain detection false positives** | Multi-criteria heuristic reduces risk. `--include-sidechain` provides escape hatch. |
| **Comparison engine backward compatibility** | `compare_instruments()` public signature is unchanged. New behaviour only affects results for instruments with nested patchCable structures or synth sample oscillators — these are additive improvements, not breaking changes. |
| **Cross-platform** | No platform-specific changes. All modifications use existing Python/lxml patterns. |

## Risk Mitigation

| Risk | Mitigation | Residual Risk |
|---|---|---|
| Sidechain heuristic misidentifies a real kit | Multi-criteria check requires several indicators to align. `--include-sidechain` provides escape hatch. Run against full library and verify no false positives. | Low — heuristic is conservative |
| Warning text changes break test assertions | Update test assertions alongside warning text changes. Run full test suite after each change. | Minimal |
| `depthControlledBy` comparison adds noise to dedup | Nested structure comparison only fires as a hard marker when sub-patchCable `source` attributes differ. Amount differences remain soft markers. This is consistent with the existing patchCable hybrid approach (D19 in extraction plan). | Low |
| `--exclude-dir` flag misused to exclude all songs | Flag requires explicit directory names. No wildcards. `SONGS/` root-level songs are never excluded. | Minimal |

## Implementation Roadmap

### Phase 1: Sidechain Kit Detection

> **Goal:** Detect sidechain-only kits during extraction and exclude them from output by default, with an opt-out flag to include them
> **Prerequisites:** Existing extraction pipeline fully working (all phases complete)

#### Task 1.1: Define sidechain detection function

- **Description:** Create a function in `extraction.py` that examines an assembled standalone kit element and determines whether it is a sidechain-only kit. The function uses heuristics from the XML structure research Section 12: (1) only 1 noteRow in the source clip has `noteDataWithLift`, (2) that row's sound has `sideChainSend` at or near max, (3) kit-level or row-level volume is low, OR (4) the kit has only 1 sound total (dedicated sidechain kit). The function needs access to both the assembled kit element and the source clip element (for noteRow data).
- **Inputs:** Assembled standalone `<kit>` element, source `<instrumentClip>` element
- **Outputs:** Boolean indicating whether the kit is a sidechain-only kit, plus a reason string for the console note
- **Acceptance Criteria:**
  - [x] Function accepts a kit element and clip element
  - [x] Returns `True` when the kit matches the sidechain heuristic (criteria 1+2+3 OR criteria 4+2)
  - [x] Returns `False` for normal kits (multiple sequenced rows, no extreme sideChainSend, normal volume)
  - [x] The reason string identifies which criteria triggered detection (e.g. "single sound with max sideChainSend" or "only 1 sequenced row with max sideChainSend and low volume")
  - [x] `sideChainSend` threshold is defined as a named constant (max value `2147483647`, allow near-max e.g. within 1% of max)
  - [x] Volume threshold for "low" is defined as a named constant (suggested: below init kit volume `0x3504F334`, but this needs verification during implementation against real sidechain kits in the library)
- **Implementation Notes:**
  > Function `is_sidechain_kit(group: InstrumentClipGroup) -> tuple[bool, str]` added to `extraction.py`. Takes the group (not raw elements) to access both instrument and clip data via `select_default_clip` logic (lowest section). Constants: `SIDECHAIN_SEND_MAX = 2147483647`, `SIDECHAIN_SEND_THRESHOLD = int(max * 0.99)`, `SIDECHAIN_LOW_VOLUME_THRESHOLD = 0xC0000000 - 0x100000000` (signed: -1073741824 ≈ display 12/50). Path B (single sound) does not require low volume check per research — dedicated sidechain kits may have any volume. Path A (multi-sound, 1 sequenced row) requires low volume at kit or row level.

#### Task 1.2: Add `--include-sidechain` CLI flag

- **Description:** Add an `--include-sidechain` argparse flag to `extract_instruments.py`. When present, sidechain-only kits are extracted normally. When absent (default), sidechain kits are detected and excluded.
- **Inputs:** Existing argparse setup in `extract_instruments.py`
- **Outputs:** New CLI flag available, passed through to the extraction pipeline
- **Acceptance Criteria:**
  - [x] `--include-sidechain` flag added to argparse
  - [x] Flag defaults to `False` (sidechain kits excluded by default)
  - [x] Flag value is accessible in the main extraction loop
  - [x] `--help` output describes the flag clearly
- **Implementation Notes:**
  > Added `--include-sidechain` with `action="store_true"` to argparse in `extract_instruments.py`. Accessible as `args.include_sidechain`.

#### Task 1.3: Integrate sidechain filtering into the extraction pipeline

- **Description:** In the extraction loop in `extract_instruments.py`, after a kit is extracted and before it is added to results, call the sidechain detection function. If detected and `--include-sidechain` is not set, skip the kit and print a NOTE. If `--include-sidechain` is set, extract normally.
- **Inputs:** Assembled kit element, source clip, `--include-sidechain` flag value
- **Outputs:** Sidechain kits excluded from results (or included if flag is set), NOTE printed for each detected sidechain kit
- **Acceptance Criteria:**
  - [x] Sidechain-only kits are excluded from `all_results` when `--include-sidechain` is not set
  - [x] A NOTE-level message is printed for each excluded sidechain kit: `NOTE: Kit "{name}" detected as sidechain-only — skipped (use --include-sidechain to extract)`
  - [x] When `--include-sidechain` is set, sidechain kits are extracted and included in results normally with no note
  - [x] Sidechain filtering happens per-song during extraction (not as a post-processing step), so the per-song console output correctly reflects what was extracted
  - [x] Summary count reflects the actual number of extractions (excluding sidechain kits)
- **Implementation Notes:**
  > Filtering placed at the top of the `for group in groups:` loop in `extract_instruments.py`, before clip selection. If group is a kit and `--include-sidechain` is not set, calls `is_sidechain_kit(group)` and `continue`s to skip the entire group if detected. This is before any extraction work, so no wasted computation. The NOTE message uses double-space indent to align with extraction lines.

#### Task 1.4: Tests for sidechain detection

- **Description:** Add tests for the sidechain detection function covering positive cases (sidechain kits), negative cases (normal kits), and edge cases.
- **Inputs:** Test fixture builders
- **Outputs:** New test class in `test_extraction.py`
- **Acceptance Criteria:**
  - [x] Test: single-sound kit with max `sideChainSend` and low volume → detected as sidechain
  - [x] Test: single-sound kit with max `sideChainSend` and normal volume → detected as sidechain (criteria 4+2 — dedicated sidechain kit)
  - [x] Test: multi-sound kit with one sequenced row, max `sideChainSend`, low volume → detected as sidechain
  - [x] Test: multi-sound kit with multiple sequenced rows → not detected as sidechain (normal kit)
  - [x] Test: kit with no `sideChainSend` attribute → not detected
  - [x] Test: kit with `sideChainSend` well below max → not detected
  - [x] All existing tests still pass
- **Implementation Notes:**
  > 9 tests in `TestIsSidechainKit` class: Path B (single sound, max SC), Path B (single sound, normal volume — still detected), Path A (multi-sound, low kit volume), Path A (multi-sound, low row volume), negative (multiple sequenced rows), negative (no SC attr), negative (SC below max), edge (near-max threshold), negative (multi-sound, normal volume). Also added a `_make_kit_group()` helper to build minimal `InstrumentClipGroup` fixtures for kit detection tests. Full suite: 329 passed, 9 skipped.

#### Task 1.5: Verify against real library

- **Description:** Run the script with sidechain detection against the full song library. Verify that sidechain kits are correctly detected and that no real kits are false-positived.
- **Inputs:** Full song library in `DELUGE/SONGS/`
- **Outputs:** Dry-run output with sidechain notes
- **Acceptance Criteria:**
  - [x] Script runs to completion without errors
  - [x] At least one sidechain kit is detected across the library (if any exist)
  - [x] No normal kits are falsely identified as sidechain-only (verify by inspecting detected kits)
  - [x] `--include-sidechain` correctly includes all kits when set
  - [x] Extraction count with sidechain detection ≤ count without (or equal if no sidechain kits exist)
- **Implementation Notes:**
  > 11 sidechain kits detected across the library: "001" (×2), "000" (×5), "KIT057", "000 TR-808", "Sidechain", plus appearances in Triggy 18/19 test songs matching research documentation. With filtering: 133 kits found → 80 after dedup. Without filtering: 144 kits → 84 after dedup. Difference of 11 pre-dedup and 4 post-dedup (some sidechain kits were duplicates of each other). Inspected detected names: all are typical sidechain trigger kit names or documented test cases. No false positives identified.

### Phase 2: Warning Improvements

> **Goal:** Improve warning and note messages for clarity and accuracy based on code analysis findings
> **Prerequisites:** None (independent of Phase 1)

#### Task 2.1: Improve orphan instrument warning

- **Description:** Update the orphan warning in `match_instruments_to_clips()` to check `<arrangementOnlyClips>` for matching clips. If found, use a different message indicating the instrument has arrangement-only clips. If no clips found anywhere, use a message indicating the instrument is truly orphaned.
- **Inputs:** Song XML tree (needed to access `<arrangementOnlyClips>`), instrument info
- **Outputs:** Updated warning text that distinguishes arrangement-only instruments from truly orphaned ones
- **Acceptance Criteria:**
  - [x] When an instrument has no session clips but has matching clips in `<arrangementOnlyClips>`: message reads `Instrument "{name}" has arrangement-only clips — session clips required for extraction (skipped)`
  - [x] When an instrument has no clips in session or arrangement: message reads `Orphaned instrument "{name}" — no clips in session or arrangement view`
  - [x] The function signature may need to accept the song root element (or `<arrangementOnlyClips>` element) as an additional parameter to perform the lookup
  - [x] Existing tests updated to match new warning text
- **Implementation Notes:**
  > Added optional `song_tree` parameter to `match_instruments_to_clips()`. When an instrument has no matching session clips, checks `<arrangementOnlyClips>` for matching `instrumentPresetName`/`instrumentPresetFolder`. Two new tests added: `test_orphan_with_arrangement_clip_shows_arrangement_only_message` and `test_orphan_without_arrangement_clip_shows_orphaned_message`. Updated existing orphan test assertions to match new message text. CLI passes `song_tree` through to the function.

#### Task 2.2: Downgrade kit default-params message to NOTE

- **Description:** Change the "has no clip parameters" warning in `_ensure_all_sounds_have_default_params()` from WARNING to NOTE level, and update the message text to be less alarming.
- **Inputs:** Existing `_ensure_all_sounds_have_default_params()` function
- **Outputs:** Updated message text and level
- **Acceptance Criteria:**
  - [x] Message prefix changed from `WARNING:` to `NOTE:`
  - [x] Message text changed from `Kit sound "{name}" (index {idx}) has no clip parameters — using defaults` to `Kit sound "{name}" not used in this clip — applying init defaults`
  - [x] The message still includes the preset name and section/colour context from the calling code
  - [x] Existing tests updated to match new message text
- **Implementation Notes:**
  > Changed message in `_ensure_all_sounds_have_default_params()` from `Kit sound {name!r} (index {idx}) has no clip parameters — using defaults` to `Kit sound {name!r} not used in this clip — applying init defaults`. CLI print prefix changed from `WARNING:` to `NOTE:` (with double-space alignment matching sidechain notes). Updated `test_warning_printed_for_defaulted_sound` assertions.

#### Task 2.3: Propagate `_merge_noterow_params()` warnings

- **Description:** In `extract_kit()`, collect the return value from `_merge_noterow_params()` (line ~873) and extend the `default_param_warnings` list with any warnings returned. Currently the return value is discarded.
- **Inputs:** Existing `extract_kit()` function
- **Outputs:** Warnings from `_merge_noterow_params()` included in the structured warning pipeline
- **Acceptance Criteria:**
  - [x] Return value from `_merge_noterow_params()` is collected (not discarded)
  - [x] Warnings are appended to a list that is included in the function's return value or the `default_param_warnings` list
  - [x] A test verifies that a noteRow without `<soundParams>` produces a warning that reaches the caller
- **Implementation Notes:**
  > Initialised `default_param_warnings: list[str] = []` before the noteRow merge loop. Each call to `_merge_noterow_params()` now has its return value collected via `default_param_warnings.extend(merge_warnings)`. The subsequent `_ensure_all_sounds_have_default_params()` call also extends (not replaces) the list. Updated existing `test_noterow_without_soundparams_warns` to additionally assert that the warning appears in the returned warnings list, not just stdout.

#### Task 2.4: Improve missing-section warning context

- **Description:** Append contextual hint to the missing-section warning in `discover_clips()`: `"— treating as section 0 (may indicate corrupt XML)"`.
- **Inputs:** Existing `discover_clips()` function
- **Outputs:** Updated warning text
- **Acceptance Criteria:**
  - [x] Warning text updated to include the hint about corrupt XML
  - [x] Existing tests updated if they assert on this warning text
- **Implementation Notes:**
  > Appended `(may indicate corrupt XML)` to the existing missing-section warning in `discover_clips()`. The existing test `test_missing_section_defaults_to_zero` asserts on `"no section attribute"` substring which still matches. No test update needed.

### Phase 3: Comparison Engine Refinements

> **Goal:** Extend the comparison engine to catch nested patchCable structure differences and add missing synth oscillator hard markers
> **Prerequisites:** None (independent of Phases 1–2)

#### Task 3.1: Add `depthControlledBy` sub-patchCable comparison

- **Description:** Extend `_check_patchcable_structure()` to also compare `<depthControlledBy>` children on matching patchCables. When two patchCables have the same `(source, destination)` but different nested `<depthControlledBy>` sub-patchCable `source` attributes, this is a hard marker difference. When they have the same nested structure but different `amount` values, those count as soft markers.
- **Inputs:** Existing `_check_patchcable_structure()` and `_collect_soft_diffs()` functions
- **Outputs:** Extended comparison that covers nested patchCable modulation structure
- **Acceptance Criteria:**
  - [x] For matching top-level patchCables, the function examines `<depthControlledBy>` children
  - [x] If one cable has a `<depthControlledBy>` child and the other does not → hard diff
  - [x] If both have `<depthControlledBy>` but with different sub-patchCable `source` attributes → hard diff
  - [x] If both have identical `<depthControlledBy>` structure but different `amount` values → soft marker (handled in `_collect_soft_diffs()`)
  - [x] PatchCables without `<depthControlledBy>` children are unaffected (existing behaviour preserved)
- **Implementation Notes:**
  > Added `_build_patchcable_element_dict()` helper that returns `(source, destination) -> element` mapping (vs the existing `_build_patchcable_dict` which returns `-> amount`). Extended `_check_patchcable_structure()`: after checking cable key sets, iterates matching cables and compares `<depthControlledBy>` children — presence/absence and sub-patchCable source differences are hard markers. Extended `_collect_soft_diffs()` step 3b: for matching cables with matching depthControlledBy structure, compares nested amount values through the same hex threshold logic as top-level cable amounts.

#### Task 3.2: Add synth osc `loopMode` and `reversed` to hard markers

- **Description:** Add `loopMode` and `reversed` to `synth_hard_attrs` for `osc1` and `osc2` in `ComparisonConfig.default()`. These are already present in `kit_hard_attrs` per-sound but missing for synths.
- **Inputs:** Existing `ComparisonConfig.default()` method
- **Outputs:** Updated default config with consistent osc hard markers for synths
- **Acceptance Criteria:**
  - [x] `synth_hard_attrs["osc1"]` includes `"loopMode"` and `"reversed"`
  - [x] `synth_hard_attrs["osc2"]` includes `"loopMode"` and `"reversed"`
  - [x] A test verifies that two synths with different `loopMode` on `osc1` are flagged as hard-distinct
  - [x] A test verifies that two synths with different `reversed` on `osc1` are flagged as hard-distinct
  - [x] Existing comparison tests still pass (no false positives introduced)
- **Implementation Notes:**
  > Added `"loopMode"` and `"reversed"` to `synth_hard_attrs` for both `osc1` and `osc2` in `ComparisonConfig.default()`. The `synth_soft_elements` skip sets already contained these attributes from the earlier attribute completeness update, so no double-counting risk.

#### Task 3.3: Tests for comparison engine extensions

- **Description:** Add tests for the new comparison engine behaviour.
- **Inputs:** Test fixture builders
- **Outputs:** New tests in `test_extraction.py`
- **Acceptance Criteria:**
  - [x] Test: patchCable with `<depthControlledBy>` present on one side only → hard distinct
  - [x] Test: patchCable with different `<depthControlledBy>` sub-patchCable sources → hard distinct
  - [x] Test: patchCable with same `<depthControlledBy>` structure but different amounts → soft marker (not hard)
  - [x] Test: patchCable without `<depthControlledBy>` → existing behaviour unchanged
  - [x] Test: synth with `loopMode` difference on osc1 → hard distinct
  - [x] Test: synth with `reversed` difference on osc1 → hard distinct
  - [x] All existing tests still pass
- **Implementation Notes:**
  > Added `_add_depth_controlled_by()` test helper to inject nested elements into preset fixtures. Two new test classes: `TestDepthControlledByComparison` (7 tests: added, removed, different source, different amount, identical, no-depth unchanged) and `TestSynthOscHardMarkers` (5 tests: osc1 loopMode, osc1 reversed, osc2 loopMode, same loopMode, absent vs present). Total: 126 passed, 9 skipped (11 new tests).

### Phase 4: Test Song Filtering

> **Goal:** Allow users to exclude songs in specific subdirectories from extraction
> **Prerequisites:** None (independent of Phases 1–3)

#### Task 4.1: Add `--exclude-dir` CLI flag

- **Description:** Add an `--exclude-dir` argparse flag to `extract_instruments.py` that accepts subdirectory names relative to `SONGS/`. Can be specified multiple times (using `action="append"`). When specified, songs in matching subdirectories are excluded from discovery.
- **Inputs:** Existing argparse setup
- **Outputs:** New CLI flag, values passed to `discover_songs()`
- **Acceptance Criteria:**
  - [x] `--exclude-dir` flag added with `action="append"` and `default=None`
  - [x] `--help` output describes the flag: exclude songs in subdirectories of `SONGS/` (e.g. `--exclude-dir testing`)
  - [x] Multiple `--exclude-dir` flags can be specified
  - [x] Flag values are passed through to `discover_songs()`
- **Implementation Notes:**
  > Added `--exclude-dir` with `action="append"` and `default=None` to argparse in `extract_instruments.py`. Values passed as `exclude_dirs=args.exclude_dir` to `discover_songs()`. Help text: "Exclude songs in a subdirectory of SONGS/ (e.g. --exclude-dir testing). Can be specified multiple times."

#### Task 4.2: Update `discover_songs()` to support directory exclusion

- **Description:** Modify `discover_songs()` to accept an optional list of directory names to exclude. Songs whose path is within any excluded subdirectory are skipped. Exclusion is based on whether any path component matches an excluded directory name.
- **Inputs:** Existing `discover_songs()` function, exclusion list from CLI
- **Outputs:** Updated function that filters out songs in excluded directories
- **Acceptance Criteria:**
  - [x] `discover_songs()` accepts an optional `exclude_dirs` parameter (list of strings or `None`)
  - [x] When `exclude_dirs` is `None` or empty, all songs are discovered (existing behaviour)
  - [x] When `exclude_dirs` contains `"testing"`, songs in `SONGS/testing/` are excluded
  - [x] Exclusion uses the subdirectory path relative to `SONGS/` — matching against `xml_path.parent.relative_to(songs_dir)`
  - [x] A message is printed when songs are excluded: `Excluding N songs from {dir_name}/`
  - [x] Songs at the top level of `SONGS/` are never excluded by this mechanism
- **Implementation Notes:**
  > Added optional `exclude_dirs: list[str] | None = None` parameter to `discover_songs()`. After collecting paths from `scan_tree()`, filters using case-insensitive matching of parent directory components against the exclusion set. Prints count per excluded directory. Top-level songs have `rel.parts == ()` so never match. Nested subdirs (e.g. `testing/sub/`) are also excluded since `"testing"` appears in `rel.parts`.

#### Task 4.3: Tests for directory exclusion

- **Description:** Add tests for the directory exclusion behaviour.
- **Inputs:** Test fixture builders, mock filesystem or monkeypatch
- **Outputs:** New tests in `test_extraction.py`
- **Acceptance Criteria:**
  - [x] Test: `exclude_dirs=None` discovers all songs (existing behaviour)
  - [x] Test: `exclude_dirs=["testing"]` excludes songs in `testing/` subdirectory
  - [x] Test: multiple `exclude_dirs` values exclude multiple subdirectories
  - [x] Test: songs at top level of `SONGS/` are never excluded
  - [x] All existing tests still pass
- **Implementation Notes:**
  > Added `TestDiscoverSongsExcludeDir` class with 7 tests: `None` discovers all, single dir exclusion, multiple dirs, top-level never excluded, nested subdir exclusion, exclusion message printed, case-insensitive matching. Uses `_write_song()` helper that writes minimal valid song XML to `tmp_path`. Full suite: 349 passed, 9 skipped (7 new tests, 1 pre-existing unrelated failure in `test_create_backup.py`).

## Progress Tracker

| Phase | Status | Tasks Complete | Notes |
|-------|--------|---------------|-------|
| Phase 1: Sidechain Kit Detection | Complete | 5/5 | 11 sidechain kits detected in library, 329 tests pass |
| Phase 2: Warning Improvements | Complete | 4/4 | 332 tests pass (1 pre-existing failure unrelated), 2 new tests added |
| Phase 3: Comparison Engine Refinements | Complete | 3/3 | 11 new tests, 126 passed (342 full suite) |
| Phase 4: Test Song Filtering | Complete | 3/3 | 7 new tests, 349 pass (full suite). 29 test songs excluded in real library. |

## Open Questions

1. **What volume threshold constitutes "low" for sidechain kit detection?**
   - **Impact:** Affects false positive/negative rate of sidechain detection
   - **Recommendation:** Start with "below init kit volume" (`0x3504F334` ≈ display 27/50) and verify against real sidechain kits in the library. Adjust during implementation based on observed values.
   - **Blocking:** No — can be tuned during Task 1.5 verification
   - **Resolution:** Used `0xC0000000` (signed: -1,073,741,824 ≈ display 12/50) as the threshold. This is more generous than init kit volume, reducing false positives. All 11 detected sidechain kits in the library passed this threshold (most had volume at 0x80000000 = silent). No false positives at this level. Note: Path B (single-sound dedicated sidechain kits) bypasses the volume check entirely since those kits exist solely as sidechain triggers regardless of volume.

2. **Should `--exclude-dir` have a convention default (e.g. always exclude `testing/`)?**
   - **Impact:** Determines whether users need to remember to pass the flag
   - **Recommendation:** No convention default. The flag is opt-in only per D9. Users who want to exclude `testing/` pass `--exclude-dir testing` explicitly. This avoids surprising behaviour for new users and keeps the default behaviour unchanged from the current codebase.
   - **Blocking:** No
   - **Resolution:** No convention default. `--exclude-dir` is opt-in only. Users pass `--exclude-dir testing` explicitly. Verified against library: 29 songs in `SONGS/testing/` correctly excluded.

## References

### Research Documents
- [xml-code-analysis.md](../research/xml-code-analysis.md) — Primary input (code analysis findings)
- [xml-structure-research.md](../research/xml-structure-research.md) — XML structure ground truth (Section 12: sidechain patterns)

### Related Plans
- [extract-instruments-plan.md](extract-instruments-plan.md) — Original extraction plan (fully implemented, context for decisions D13, D19, D21)

### Standards Applied
- [project.md](../../agent-system/standards/project.md) — SD Card safety and platform requirements (no SD card writes, cross-platform compatibility)

### Project Files
- [extraction.py](../../scripts/deluge_lib/extraction.py) — Primary module being modified
- [extract_instruments.py](../../scripts/extract_instruments.py) — CLI entry point being modified
- [test_extraction.py](../../scripts/tests/test_extraction.py) — Test file being extended

## Change Log

| Date | Change | Reason |
|------|--------|--------|
| 24 Apr 2026 | Initial plan created | Post-implementation improvements based on code analysis |
| 24 Apr 2026 | Phase 1 complete | Sidechain kit detection implemented (Tasks 1.1–1.5). 11 sidechain kits detected across library, 329 tests pass. Volume threshold set at `0xC0000000` (display ~12/50). |
| 24 Apr 2026 | Phase 2 complete | Warning improvements implemented (Tasks 2.1–2.4). Orphan warnings now distinguish arrangement-only vs truly orphaned. Kit default-params downgraded to NOTE. `_merge_noterow_params()` warnings propagated. Missing-section warning improved. 332 tests pass. |
| 24 Apr 2026 | Phase 3 complete | Comparison engine refinements implemented (Tasks 3.1–3.3). `depthControlledBy` nested patchCable comparison (hard: presence/source; soft: amount). Synth osc `loopMode`/`reversed` added to hard markers. 11 new tests, 342 pass (full suite). |
| 24 Apr 2026 | Phase 4 complete | Test song filtering implemented (Tasks 4.1–4.3). `--exclude-dir` CLI flag with `action="append"`. `discover_songs()` filters by parent directory components (case-insensitive). 7 new tests, 349 pass. 29 test songs excluded in real library run. |
