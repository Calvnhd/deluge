# Plan: Extract Instruments from Songs

> **Document Type:** Plan
> **Date:** 14 April 2026
> **Research:** [extract-instruments-research.md](../research/extract-instruments-research.md)
> **Pipeline:** Research → **Plan** → Implement
> **Status:** Complete — in threshold tuning

## Executive Summary

Build a script that scans all song XMLs in `DELUGE/SONGS/`, extracts embedded synth and kit instruments as standalone preset XMLs, and writes them to `DELUGE/SYNTHS/SONG-SYNTHS/` and `DELUGE/KITS/SONG-KITS/`. The script merges the split instrument structure (from `<instruments>`) with clip-level parameters (from `<sessionClips>`) and arpeggiator data, normalises master volume and pan, and outputs firmware `c1.2.1` standalone presets. Two modes are supported: default mode extracts one version per instrument (lowest section ID), and extended mode extracts multiple versions when parameters differ significantly. A generalised comparison engine (research Section 16) classifies parameters into hard markers, soft markers, and ignorable params — used by both intra-song extended selection and cross-song deduplication. Cross-song dedup (research Section 17) filters redundant extractions where the same preset appears in multiple songs, using a baseline + incremental acceptance algorithm grouped by preset name. Dedup is enabled by default (`--no-dedup` to disable). Research Section 13.5 provides the definitive transformation recipes.

Post-plan enhancements include: sidechain-only kit detection and filtering (`--include-sidechain`), SD card direct mode (`--sd-direct`), configurable filename ordering (`--naming`), subdirectory exclusion (`--exclude-dir`), verbose dedup logging (`--verbose`), dynamic init file loading (reads normalisation values from Init-Synth/Init-Kit XMLs instead of hardcoded constants), init template for kit sounds without clip params, two-pass deduplication (name-pass + global cross-name pass), and `<modKnobs>` mapping as a hard marker in the comparison engine.

## Research Summary

Key findings from the [research document](../research/extract-instruments-research.md):

- **Split architecture (Section 3):** Instrument structure lives in `<instruments>`, tuneable parameters live in clip-level `<soundParams>`/`<kitParams>`, and synth arpeggiators live at clip level. Extraction requires merging these sources.
- **Transformation recipes (Section 13.5):** Precise, verified step-by-step procedures for both synth and kit extraction, including element reordering, attribute stripping, and tag renaming.
- **Kit arpeggiator asymmetry (Section 13.6):** Kit sounds keep their arpeggiator in the instrument definition; synth arpeggiators live at clip level. Different handling required.
- **Existing assets (Section 10):** `parse_deluge_xml()`, `get_deluge_root()`, `scan_tree()`, `confirm_apply()`, dataclass patterns, and `pyproject.toml` entry points are all reusable.
- **All 58 songs use `c1.2.1` firmware (Section 11):** Single format target simplifies extraction. Warn and skip songs with other firmware.
- **Recommended approach:** Merge instrument + clip params (Approach A) — the only viable approach since active instruments lack `<defaultParams>`.
- **Generalised comparison engine (Section 16):** A single `compare_instruments()` function with a three-tier model — hard markers (structural identity: osc type, sample file, patchCable structure, arp mode, etc.), soft markers (numerical params with per-param and group thresholds), and an ignore list (volume, pan). Configured via a `ComparisonConfig` dataclass with a `default()` classmethod. Operates on assembled standalone presets post-normalisation.
- **Cross-song deduplication (Section 17):** Post-extraction filter using baseline + incremental acceptance. Groups results by `(preset_name, instrument_type)`, ignoring preset folder. First alphabetically becomes baseline; subsequent results compared against all accepted. Dedup on by default, `--no-dedup` to disable.
- **Impact on extended mode (Section 18):** Existing `compare_versions()` replaced by `compare_instruments()`. `select_extended_clips()` updated to compare against all accepted (not just baseline). Both use cases share the generalised engine with independently configurable thresholds.
- **Duplication analysis (Section 19):** Kit "000" appears in 10+ songs, "Deeper" in 5, "K01Bass" in 4. Estimated 20-30% reduction in output files from dedup.

Authoritative user decisions from [extraction-questions.md](../../temp/extraction-questions.md) supplement the research and take precedence where conflicts exist.

> **Codebase audit (22 Apr 2026):** All extraction dependencies (`parse_deluge_xml()`, `get_deluge_root()`, `confirm_apply()`) confirmed stable and unchanged at their original locations. No new reusable code found in modules added since the feature was paused (`analysis.py`, `sample_overview.py` — different domain). Minor utility: `print_path()` from `scanning.py` could be adopted for consistent forward-slash path display in extraction output formatting.

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
| D10 | Strip automation data during extraction | Revised decision (was: keep verbatim). Standalone presets never contain automation — the Deluge strips it on save. Post-processing step truncates extended hex strings to base value (first 8 hex chars). | Keep automation verbatim (original D10, reversed) |
| D11 | Firmware check = warn and skip, not abort | User decision (Q34). Future syncs may bring non-c1.2.1 songs. Script continues processing remaining songs. | Hard fail (rejected — too disruptive) |
| D12 | Clip arpeggiator is the source for synths; strip extra numeric attrs | Research Section 13.6. Synth instruments have no arpeggiator in `<instruments>` — it lives at clip level only. Extra attrs (`gate`, `rate`, `ratchetProbability`, `ratchetAmount`, `sequenceLength`, `rhythm`) are duplicates of `<soundParams>` values and must be stripped. User confirmed (Q35). | Use instrument-level arpeggiator (not viable — doesn't exist for synths) |
| D13 | Ignore arrangement-only clips and `<arrangementOnlyClips>` entirely | User decision (Q4). Session clips only. | Include arrangement clips (deferred) |
| D14 | Duplicate clips in same section: take first, warn about second | User decision (Q9). | Take both (rejected — would produce near-identical extractions) |
| D15 | Extended mode comparison ignores automation data | User decision (Q10 clarification). Automation is song-specific playback data, not a meaningful instrument difference. For comparison, use the raw attribute value; if it's an extended hex string (automation), treat the value as unchanged from other versions that also have automation or use the first hex value segment. | Include automation in comparison (rejected) |
| D16 | Generalised comparison engine — single `compare_instruments()` function for both extended mode and dedup | Research Section 16.1. Both use cases need the same comparison logic. A single engine with configurable rulesets avoids divergence and duplication. Operates on assembled standalone presets post-normalisation, so the engine doesn't need to understand the split instrument/clip architecture. | Two separate comparison implementations (rejected — divergence risk) |
| D17 | Three-tier comparison model: hard markers, soft markers, ignore list | Research Section 16.2. Hard markers (structural identity) trigger immediate "distinct" — osc type, sample file, patchCable structure, arp mode, etc. Soft markers use per-param threshold + group count threshold. Ignore list covers normalised params (volume, pan). | Binary identical/different (rejected — too coarse); single threshold (rejected — doesn't capture structural vs numerical) |
| D18 | ComparisonConfig as a dataclass with `default()` classmethod | Research Section 16.3. Type-safe, IDE-completable, testable. `default()` returns the standard config matching existing constants. Easily overridden for testing. Not user-facing config — developer tuning only. | TOML/YAML config file (rejected — not user-facing, adds parsing complexity) |
| D19 | PatchCables hybrid comparison — structure is hard, amounts are soft | Research Section 16.6. Adding/removing a cable is structural (hard marker). Changing amount on an existing cable is numerical (soft marker). Compare set of `(source, destination)` pairs for structure, then `amount` values for soft comparison. | Treat all patchCable changes as hard (rejected — too aggressive); treat all as soft (rejected — misses structural routing changes) |
| D20 | Cross-song dedup enabled by default, `--no-dedup` to disable | Research Section 17.5. The primary user runs the script periodically and wants clean output. Most songs share common starting-point presets (e.g., kit "000" in 10+ songs). | Dedup off by default (rejected — cluttered output is the common complaint) |
| D21 | Dedup groups by `(preset_name, instrument_type)`, ignoring preset_folder | Research Section 17.3 (Option A) and 17.4. Preset folder indicates load location, not identity. Two instruments named "K01Bass" from different folders are the same base preset. Cross-name dedup deferred — hard markers would catch structurally identical instruments under different names if later needed. | Global cross-name comparison (rejected — O(n²), high false-positive risk); hybrid with `--global-dedup` flag (deferred) |
| D22 | Threshold independence — both use cases get separate `ComparisonConfig` instances with identical defaults | Research Section 17.7. Allows independent tuning during testing (e.g., more aggressive dedup thresholds vs. more permissive extended selection). | Single shared config (rejected — limits tuning flexibility) |
| D23 | Extended mode `select_extended_clips()` compares against ALL accepted clips, not just baseline | Research Section 18.2. Prevents accepting clips that are similar to each other but both differ from baseline. Same pattern as dedup algorithm. | Compare only against baseline (original plan — rejected for consistency and quality) |
| D24 | Envelope and delay/sidechain/compressor attributes treated as soft markers | Research Sections 16.7 and 16.8. These are numerical/tweakable settings, not structural identity. Included in soft param count. | Treat as hard markers (rejected — too aggressive for numerical tweaks) |
| D25 | Sidechain-only kits excluded by default, `--include-sidechain` to include | Sidechain trigger kits (e.g. single-sound kick with max sideChainSend) are not useful as standalone presets. Detection uses heuristics from research Section 12: Path A (1 sequenced row with high sideChainSend and low volume) and Path B (single sound with max sideChainSend). | Include all kits (rejected — clutters output with unusable presets) |
| D26 | `--sd-direct` reads/writes to SD card with double confirmation | Users may want to extract directly to the SD card without syncing. SD card safety rules require explicit confirmation before any SD card writes. Old SD output dirs are backed up to the LOCAL `.trash/` (not the SD card) before deletion. | Always use local backup (rejected — limits workflow flexibility) |
| D27 | `--naming` flag: `preset` (default) or `song` filename ordering | `preset` mode produces `<PresetName>-<SongName>.XML` for easier alphabetical browsing by preset. `song` mode produces `<SongName>-<PresetName>.XML` for grouping by source song. Default changed from song-first (original D5) to preset-first based on user preference. | Single fixed format (rejected — both orderings have valid use cases) |
| D28 | `--exclude-dir` for subdirectory exclusion | Songs in `SONGS/testing/` are test fixtures, not real songs. `--exclude-dir testing` skips them. Multiple dirs can be excluded. Case-insensitive matching on directory name. | Process all songs always (rejected — testing songs produce noise in output) |
| D29 | `--verbose` for detailed dedup logging | Shows per-result comparison details during dedup: which results were compared, which matched, and why. Useful for threshold tuning. | Always verbose (rejected — too noisy for normal use) |
| D30 | Dynamic init file loading with hardcoded fallback | `load_init_defaults()` reads volume/pan from Init-Synth.XML and Init-Kit.XML at runtime. Falls back to hardcoded constants if files are missing or unparseable. More robust than hardcoded-only — adapts if user changes their init presets. | Hardcoded constants only (original approach — replaced for flexibility) |
| D31 | Init kit template for sounds without clip params | `load_kit_init_template()` extracts `<defaultParams>` from Init-Kit.XML's first sound. Used as a fallback when `_ensure_all_sounds_have_default_params()` needs to create default params for kit sounds that have no corresponding noteRow in the selected clip. | Skip sounds without params (rejected — produces incomplete presets) |
| D32 | Two-pass deduplication: name-pass then global cross-name pass | Pass 1 groups by `(preset_name, instrument_type)` — catches same-name duplicates across songs. Pass 2 groups accepted results by `(instrument_type,)` only — catches cross-name duplicates (e.g. "000" vs "000 TR-808" which are structurally identical). Both passes use baseline + incremental acceptance. | Single-pass by name only (original D21 — upgraded to catch renamed presets) |
| D33 | `<modKnobs>` mapping as hard marker in comparison engine | Different knob assignments (positional comparison of `controlsParam` and `patchAmountFromSource` on all 16 slots) indicate different user intent for the instrument. Checked on synth `<sound>` top-level and per-sound in kit `<soundSources>`. Kits have no kit-level modKnobs. | Ignore modKnobs (rejected — loses meaningful structural information) |
| D34 | Standalone threshold benchmark script, no CLI flags on extract_instruments | Threshold tuning is a developer/testing concern, not a user workflow. A separate `dedup_threshold_test.py` imports extraction internals directly and uses `dataclasses.replace()` on `ComparisonConfig` to test different thresholds without modifying module-level constants. No changes to `extraction.py` or `extract_instruments.py` required. | Add --percent/--count flags to extract_instruments.py (rejected — pollutes the user-facing CLI with developer-only options) |

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

- `scripts/deluge_lib/extraction.py` — Core extraction logic. Contains all reusable functions: song parsing, instrument-clip matching, synth/kit transformation, version comparison via the generalised comparison engine, cross-song deduplication, normalisation, and XML serialisation. This module has no CLI concerns, no I/O side effects (except receiving parsed XML trees and returning data structures), and no user interaction.
- `scripts/extract_instruments.py` — CLI entry point. Handles argument parsing, file discovery, dry-run logic, trash management, file writing, manifest generation, dedup reporting, and console output. Calls into `extraction.py` for all domain logic.

**Data flow:**

1. CLI loads config (`DELUGE_ROOT` from `.env`) and parses arguments
2. CLI discovers all song XMLs in `DELUGE_ROOT/SONGS/`
3. For each song, CLI passes the parsed XML tree to extraction functions
4. Extraction functions return structured results (dataclasses) describing what to extract
5. CLI collects all results across all songs into a flat list
6. If dedup is enabled (default), the dedup function groups results by `(preset_name, instrument_type)` and applies baseline + incremental acceptance using the comparison engine, returning only accepted results
7. CLI handles output: trash previous runs, write XML files, generate manifest, print summary with dedup stats

**Key data structures (conceptual — the implementer defines the concrete representation):**

- An extraction result for each instrument: carries the song name, preset name, instrument type (synth/kit), section ID, colour abbreviation, the assembled standalone XML element tree, and metadata for the manifest
- A comparison config: carries hard marker attribute sets (per element path, per instrument type), soft marker thresholds (param count threshold, per-param percentage threshold), and the set of ignored attribute names. Provides a `default()` classmethod returning standard thresholds. Separate instances used for intra-song and inter-song comparison to support independent tuning.
- A comparison result: carries whether two instruments are distinct, any hard marker differences found, the count and names of soft params exceeding threshold, and a human-readable reason string
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
| `--no-dedup` | CLI flag | Disable cross-song deduplication (extract all versions from all songs) |
| `--dry-run` | CLI flag | List extractions without writing files. Default behaviour when no flag is given — matches existing script conventions |
| Song XMLs | `DELUGE_ROOT/SONGS/*.XML` | All song XMLs discovered recursively |
| Init presets | `DELUGE_ROOT/SYNTHS/Init-Synth.XML`, `DELUGE_ROOT/KITS/Init-Kit.XML` | Reference volume/pan values for normalisation |
| `--verbose` | CLI flag | Print detailed dedup comparison logging |
| `--sd-direct` | CLI flag | Read from and write to SD card directly (with double confirmation) |
| `--include-sidechain` | CLI flag | Include sidechain-only kits (excluded by default) |
| `--exclude-dir` | CLI flag (repeatable) | Exclude songs in subdirectories of SONGS/ |
| `--naming` | CLI flag (`preset`/`song`) | Filename ordering: preset-first (default) or song-first |

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

Dedup: Removed 12 duplicates (8 synths, 4 kits)
  000 (kit): kept Alr, removed Ape, Beginagain, Bingbong, Bloop, ...
  K01Bass (synth): kept Ambient-Fishes, removed K01Sink, Wf, Wf 7
  Deeper (kit): kept Ell, removed K05BeautifulStranger, No-More-Colour, Noize, One Eye Tea

Summary: Extracted 33 synths and 8 kits from 58 songs (12 duplicates removed)
  Output: DELUGE/SYNTHS/SONG-SYNTHS/ (33 files)
  Output: DELUGE/KITS/SONG-KITS/ (8 files)

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
- **`deluge_lib/scanning.py`** — Reuse `scan_tree()` if needed for file discovery, though a simpler `Path.glob()` for `SONGS/*.XML` may suffice. `print_path()` is available for consistent forward-slash path display in console output
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
| **Comparison engine** | The generalised `compare_instruments()` function is used by both extended mode (`select_extended_clips()`) and cross-song dedup (`deduplicate_results()`). Changes to comparison logic or thresholds affect both features. Both use cases get independent `ComparisonConfig` instances to allow separate tuning. |
| **SD card safety (`--sd-direct`)** | `--sd-direct` reads songs from and writes extractions to the SD card. SD card writes require double confirmation (standard prompt + explicit "yes" input). Old output dirs on SD card are backed up to the local repo's `.trash/` before deletion, not to the SD card itself. Compliant with project standard: scripts never write to SD card without explicit user confirmation. |

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
| Parameter automation in soundParams | Strip automation: truncate extended hex values to base (first 8 hex chars after `0x`). Standalone presets never contain automation data. | `_strip_automation()` called from CLI after `extract_synth()`/`extract_kit()`, before `normalise_params()` |
| Extended mode comparison noise | Configurable thresholds (D4). Automation ignored for comparison (D15). Structural/non-numerical changes always trigger extraction. | May need threshold tuning — constants are easily editable |
| Dedup removes legitimately different instruments | Hard marker comparison catches structural differences regardless of thresholds. Instruments with different osc types, sample files, or patchCable structure are always kept. Soft threshold defaults (3 params, 10%) are conservative. `--no-dedup` flag provides escape hatch. | Possible false negatives for instruments with identical structure but subtly different numerical settings below threshold — user can lower thresholds or disable dedup |
| Dedup ordering affects which version is kept | Deterministic alphabetical ordering by song name ensures reproducible results. The "first alphabetically" convention is consistent with default mode's "lowest section ID" strategy. | User may prefer a specific song's version — not controllable without manual intervention |
| SD card data loss via `--sd-direct` | Double confirmation: standard `confirm_apply()` then explicit "type yes" prompt. Old SD output dirs backed up to LOCAL `.trash/` before deletion. | Minimal — user must actively confirm twice |
| Comparison engine performance on large preset sets | Grouping by preset name keeps comparison groups small (typically 2-10 instruments per group). Each comparison is in-memory XML traversal — no I/O. Extended mode has at most ~6 pairwise comparisons per instrument per song. | Negligible unless preset counts grow significantly |

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

#### Task 1.2: Song discovery and firmware validation ✅

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
  - [x] Discovers all `<sound>` and `<kit>` children of `<instruments>` (ignores `<midi>` and `<audioTrack>`)
  - [x] Discovers all `<instrumentClip>` children of `<sessionClips>` (ignores `<arrangementOnlyClips>`)
  - [x] Matches clips to instruments via `instrumentPresetName` + `instrumentPresetFolder` ↔ `presetName` + `presetFolder`
  - [x] Groups clips by `(presetName, presetFolder)` then by `section` attribute
  - [x] Identifies orphaned instruments (in `<instruments>` but no matching session clips) and returns them separately with a warning message
  - [x] Handles missing `section` attribute by treating as section 0 with a warning
  - [x] For duplicate clips in the same section, keeps the first and records a warning
- **Implementation Notes:**
  > Implemented 22 Apr 2026. Three functions in `extraction.py`:
  > - `discover_instruments()` — iterates `<instruments>` children, maps `<sound>` → synth, `<kit>` → kit via tag-to-type dict, skips all other tags. Returns empty list if `<instruments>` is absent.
  > - `discover_clips()` — iterates `<sessionClips>` children, collects only `<instrumentClip>` tags. Reads `instrumentPresetName`, `instrumentPresetFolder`, `section` attrs. Missing `section` → 0 with printed warning. Returns empty list if `<sessionClips>` is absent.
  > - `match_instruments_to_clips()` — builds `(preset_name, preset_folder)` lookup from clips, iterates instruments to find matches. Orphaned instruments (no clips) → warning, excluded from groups. Duplicate clips in same section → first kept, warning recorded. Warnings stored both on the group and in the flat return list.
  > - 16 tests added/unskipped in `test_extraction.py` across `TestDiscoverInstruments` (5), `TestDiscoverClips` (5), `TestMatchInstrumentsToClips` (6). All pass.

#### Task 1.4: Version selection (default mode)

- **Description:** For each instrument, select the clip with the lowest section ID as the extraction source.
- **Inputs:** `InstrumentClipGroup` from Task 1.3
- **Outputs:** `ClipInfo` — the selected clip for the instrument
- **Acceptance Criteria:**
  - [x] Selects the clip with the lowest section ID for each instrument
  - [x] Returns a `ClipInfo` dataclass (contains element, section, preset_name, preset_folder)
  - [x] Handles instruments with only one clip (trivial selection)
- **Implementation Notes:**
  > API scaffolded as `select_default_clip(group: InstrumentClipGroup) -> ClipInfo`. Returns a single `ClipInfo` rather than a tuple — the calling code in `main()` accesses `clip_info.section` and `clip_info.element` directly.
  > Implemented: uses `min()` on `group.clips_by_section` keys to find the lowest section ID, returns the corresponding `ClipInfo`. 3 tests added/unskipped in `TestSelectDefaultClip`: lowest-section selection, single-clip trivial case, and ClipInfo return type verification. All pass.

### Phase 2: Core Transformation

> **Goal:** Implement the synth and kit XML transformation logic following the research's transformation recipes
> **Prerequisites:** Phase 1 complete — instrument/clip discovery working

#### Task 2.1: Synth extraction transformation

- **Description:** Implement the synth extraction recipe from research Section 13.5. Given a `<sound>` from `<instruments>` and its corresponding `<instrumentClip>`, produce a standalone synth XML element.
- **Inputs:** Instrument `<sound>` element, clip `<instrumentClip>` element
- **Outputs:** Standalone `<sound>` element ready for serialisation
- **Acceptance Criteria:**
  - [x] Clones the `<sound>` element from `<instruments>` (does not mutate the original tree)
  - [x] Strips song-specific attributes: `presetName`, `presetFolder`, `defaultVelocity`, `isArmedForRecording`, `activeModFunction`, `clipInstances`, `colour`
  - [x] Adds `firmwareVersion="c1.2.1"` and `earliestCompatibleFirmware="4.1.0-alpha"`
  - [x] Extracts `<soundParams>` from clip and renames tag to `<defaultParams>`
  - [x] Extracts `<arpeggiator>` from clip and strips extra numeric attributes (`gate`, `rate`, `ratchetProbability`, `ratchetAmount`, `sequenceLength`, `rhythm`)
  - [x] Reorders child elements to match standalone c1.2.1 ordering: `osc1, osc2, lfo1, lfo2, [modulator1, modulator2], unison, defaultParams, arpeggiator, modKnobs, delay, sidechain, audioCompressor`
  - [x] Preserves all attribute values verbatim (including extended hex automation strings)
  - [x] Preserves all child elements within `<defaultParams>` (envelopes, patchCables, equalizer)
- **Implementation Notes:**
  > Implemented 22 Apr 2026. Four functions in `extraction.py`:
  > - `extract_synth(instrument, clip)` — main transformation: deep-clones `<sound>`, strips song attrs, adds firmware version, extracts `<soundParams>` from clip and renames to `<defaultParams>`, extracts and cleans `<arpeggiator>` from clip, reorders children to standalone c1.2.1 order.
  > - `_strip_song_attrs(element)` — removes `SONG_SPECIFIC_ATTRS` from element in-place, silently ignores missing attrs.
  > - `_extract_arpeggiator_from_clip(clip)` — finds `<arpeggiator>` child, deep-clones, strips `ARPEGGIATOR_EXTRA_ATTRS`, returns clone (or None if not found).
  > - `_reorder_synth_children(sound)` — collects children by tag into dict, rebuilds in `SYNTH_CHILD_ORDER`, appends unknown tags at end. Handles optional modulators (FM mode).
  > - 10 tests in `TestExtractSynth` — all passing. Tests cover: immutability, attr stripping, firmware attrs, soundParams→defaultParams rename, arpeggiator extraction and cleaning, element ordering, automation hex preservation, defaultParams children preservation, FM mode with modulators.

#### Task 2.2: Kit extraction transformation

- **Description:** Implement the kit extraction recipe from research Section 13.5. Given a `<kit>` from `<instruments>` and its corresponding `<instrumentClip>`, produce a standalone kit XML element.
- **Inputs:** Instrument `<kit>` element, clip `<instrumentClip>` element
- **Outputs:** Standalone `<kit>` element ready for serialisation
- **Acceptance Criteria:**
  - [x] Clones the `<kit>` element from `<instruments>` (does not mutate the original tree)
  - [x] Strips song-specific attributes: `presetName`, `presetFolder`, `defaultVelocity`, `isArmedForRecording`, `activeModFunction`, `colour`
  - [x] Adds `firmwareVersion="c1.2.1"` and `earliestCompatibleFirmware="4.1.0-alpha"`
  - [x] Extracts `<kitParams>` from clip and renames tag to `<defaultParams>`
  - [x] Inserts kit-level `<defaultParams>` as the first child of `<kit>` (before `<delay>`)
  - [x] For each `<noteRow>` in the clip with a `drumIndex`, extracts `<soundParams>`, renames to `<defaultParams>`, and inserts into the corresponding `<sound>` in `<soundSources>` (matched by drumIndex as 0-based index) between `<unison>` and `<arpeggiator>`
  - [x] Leaves kit sound `<arpeggiator>` elements in place (they are already in the instrument definition)
  - [x] Warns on drumIndex mismatch (out of range of soundSources) and skips that noteRow
  - [x] Preserves all attribute values verbatim
  - [x] Kit-level element ordering matches standalone: `defaultParams, delay, sidechain, audioCompressor, soundSources, selectedDrumIndex`
  - [x] Per-row sound element ordering matches standalone: `osc1, osc2, lfo1, lfo2, unison, defaultParams, arpeggiator, modKnobs, delay, sidechain, audioCompressor`
- **Implementation Notes:**
  > Implemented 22 Apr 2026. Four functions in `extraction.py`:
  > - `extract_kit(instrument, clip)` — main transformation: deep-clones `<kit>`, strips song attrs, adds firmware version, extracts `<kitParams>` from clip and renames to `<defaultParams>`, inserts as first child. Iterates `<noteRows>` with `drumIndex`, merges `<soundParams>` into corresponding `<sound>` via `_merge_noterow_params()`. Warns on invalid drumIndex. Reorders kit-level and per-sound children.
  > - `_reorder_kit_children(kit)` — collects children by tag into dict, rebuilds in `KIT_CHILD_ORDER`, appends unknown tags at end. Same pattern as `_reorder_synth_children()`.
  > - `_reorder_kit_sound_children(sound)` — collects children by tag into dict, rebuilds in `KIT_SOUND_CHILD_ORDER`, appends unknown tags at end.
  > - `_merge_noterow_params(sound, noterow)` — finds `<soundParams>` in noteRow, deep-clones and renames to `<defaultParams>`, inserts after `<unison>` in the sound element.
  > - 11 tests in `TestExtractKit` — all passing.

#### Task 2.3: Volume and pan normalisation

- **Description:** Normalise the master `volume` and `pan` attributes on the `<defaultParams>` element of extracted instruments. Kit row volume and pan are preserved.
- **Inputs:** Assembled standalone XML element (from Task 2.1 or 2.2), instrument type (synth or kit)
- **Outputs:** The same element with normalised volume and pan on the top-level `<defaultParams>`
- **Acceptance Criteria:**
  - [x] For synths: sets `volume` on `<defaultParams>` to `0x4CCCCCA8` (init synth value)
  - [x] For kits: sets `volume` on kit-level `<defaultParams>` to `0x3504F334` (init kit value)
  - [x] Sets `pan` on top-level `<defaultParams>` to `0x00000000` (centre) for both types
  - [x] Does NOT modify `volume` or `pan` on kit row `<defaultParams>` (within `<soundSources>/<sound>`)
  - [x] Does NOT modify patchCable entries with `destination="volume"`
  - [x] Normalisation targets are defined as named constants or a data structure that can be extended with additional attributes in the future
- **Implementation Notes:**
  > Implemented 22 Apr 2026. Single function in `extraction.py`:
  > - `normalise_params(element, instrument_type, config)` — finds top-level `<defaultParams>` child, selects target dict from `NormalisationConfig` based on instrument_type, sets each (attr, value) pair. Does not descend into `<soundSources>` children. `NormalisationConfig` dataclass uses `synth_targets` and `kit_targets` dicts with defaults from module constants, extensible by adding new entries.
  > - 6 tests in `TestNormaliseParams` — all passing. Tests cover: synth volume, kit volume, pan centre for both types, kit row volume preserved, kit row pan preserved, patchCable volume untouched.

### Phase 3: Output and CLI

> **Goal:** Implement file output, naming, trash mechanism, manifest generation, and CLI integration
> **Prerequisites:** Phase 2 complete — transformation logic producing valid XML elements

#### Task 3.1: Filename generation and collision handling

- **Description:** Generate output filenames following the naming convention. Handle collisions between instruments with the same name in the same song.
- **Inputs:** Song name (stem of XML filename), preset name, instrument type, section ID (for extended mode), list of already-used filenames
- **Outputs:** Unique filename string
- **Acceptance Criteria:**
  - [x] Default mode: `<SongName>-<PresetName>.XML`
  - [x] Extended mode: `<SongName>-<PresetName>-<Abbr>.XML` where `<Abbr>` is the 3-letter colour abbreviation for the section ID
  - [x] Colour abbreviation map: 0=Lbl, 1=Pnk, 2=Gld, 3=Cyn, 4=Red, 5=Ylw, 6=Dbl, 7=Orn, 8=Pur, 9=Lme, 10=Grn, 11=Mag
  - [x] Collision resolution: if filename already used, append `-2`, `-3`, etc.
  - [x] Spaces, hyphens, and digits in names preserved as-is
  - [x] ~~FAT32 sanitisation removed — filenames originate from FAT32 SD card, so unsafe characters cannot appear~~
- **Implementation Notes:**
  > Implemented 22 Apr 2026. `generate_filename()` in `extraction.py`: constructs `<song>-<preset>.XML` (default) or `<song>-<preset>-<Abbr>.XML` (extended), appends `-2`, `-3`, etc. on collision, adds final filename to `used_filenames` set. 5 tests in `TestGenerateFilename` — all passing.

#### Task 3.2: XML serialisation

- **Description:** Serialise assembled lxml elements to standalone XML files with the correct declaration and formatting.
- **Inputs:** Assembled lxml element, output file path
- **Outputs:** Written XML file
- **Acceptance Criteria:**
  - [x] XML declaration: `<?xml version="1.0" encoding="UTF-8"?>`
  - [x] Output matches the formatting style of existing standalone presets (use `lxml.etree.tostring` with `xml_declaration=True`, `encoding="UTF-8"`)
  - [x] Investigate and match the whitespace/indentation style of Init-Synth.XML and Init-Kit.XML — the Deluge may be sensitive to formatting
- **Implementation Notes:**
  > Implemented 22 Apr 2026. `serialise_xml()` in `extraction.py`: uses `etree.tostring()` with `xml_declaration=True`, `encoding="UTF-8"`, `pretty_print=True`. Creates parent directories with `mkdir(parents=True)`. Writes bytes directly. 2 tests in `TestSerialiseXml` — all passing.

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
  - [x] Each entry includes: output filename, source song, preset name, preset folder, instrument type, section ID, colour name, and timestamp
  - [x] Manifest is written as formatted JSON (indented for readability)
  - [x] Summary stats at the top level: total count, songs processed, date generated
- **Implementation Notes:**
  > Completed 22 Apr 2026. `build_manifest_entry()` in `extraction.py` maps `ExtractionResult` fields to a dict with keys: `output_filename`, `source_song`, `preset_name`, `preset_folder`, `instrument_type`, `section_id`, `colour_name`, `colour_abbr`, `differing_params`. Combined with the existing `_write_manifest()` in `extract_instruments.py`, the manifest pipeline is now fully functional.

#### Task 3.5: CLI integration and output formatting (partially scaffolded)

- **Description:** Wire everything together in the CLI script. Implement discovery → extraction → output pipeline with dry-run support, confirmation prompts, and formatted console output.
- **Inputs:** All previous tasks
- **Outputs:** Complete working CLI script
- **Acceptance Criteria:**
  - [x] `deluge-extract` with no flags performs a dry-run preview
  - [x] `deluge-extract --dry-run` performs dry-run only (no confirmation prompt)
  - [x] After dry-run preview, prompts for confirmation before writing
  - [x] `deluge-extract --extended` enables extended mode
  - [x] Console output lists each extraction per song, plus warnings, plus summary (see Interface Design section for format)
  - [x] Exit code 0 on success, non-zero on failure
  - [x] Missing init preset files produce a clear error and abort
- **Implementation Notes:**
  > Full CLI pipeline scaffolded in `extract_instruments.py` `main()` (15 Apr 2026). Wired together: argparse, `discover_songs()` → per-song loop → `discover_instruments()`/`discover_clips()`/`match_instruments_to_clips()` → `select_default_clip()`/`select_extended_clips()` → `extract_synth()`/`extract_kit()` → `normalise_params()` → `generate_filename()` → `ExtractionResult` construction → per-song console output → summary → dry-run/confirmation flow → trash → file writing → manifest writing. All stubs now implemented. Exit codes added 22 Apr 2026: `__main__` block wraps `main()` in try/except, calling `sys.exit(1)` on unhandled exceptions. Init preset validation added at startup — checks `SYNTHS/Init-Synth.XML` and `KITS/Init-Kit.XML` exist before proceeding, exits with error message if missing.

### Phase 4: Generalised Comparison Engine and Extended Mode

> **Goal:** Build the three-tier comparison engine (hard/soft/ignore markers) and use it for both intra-song extended mode selection and (later, Phase 5) cross-song dedup
> **Prerequisites:** Phase 3 complete — default mode fully working end-to-end

#### Task 4.1: ComparisonConfig and ComparisonResult data structures

- **Description:** Define the `ComparisonConfig` dataclass (research Section 16.3) and `ComparisonResult` dataclass (research Section 16.4). `ComparisonConfig` carries hard marker attribute sets per element path and instrument type, soft marker thresholds, and ignored attributes. `ComparisonResult` carries the distinct/duplicate verdict, hard diffs, soft diffs, and a human-readable reason string. Provide a `ComparisonConfig.default()` classmethod that consumes the existing module-level constants (`DIFF_PARAM_COUNT_THRESHOLD`, `DIFF_PARAM_PERCENT_THRESHOLD`, `COMPARISON_EXCLUDED_ATTRS`). The existing `VersionComparison` dataclass can be removed or replaced by `ComparisonResult`.
- **Inputs:** Research Section 16.2 (hard marker tables), 16.3 (config structure), 16.4 (result structure)
- **Outputs:** Two dataclasses in `extraction.py` with sensible defaults
- **Acceptance Criteria:**
  - [x] `ComparisonConfig` dataclass exists with fields for synth hard attrs, kit hard attrs, soft thresholds (param count, param percent), and ignored attrs
  - [x] `ComparisonConfig.default()` returns a config populated with all hard markers from research Section 16.2 (synth: mode, polyphonic, osc types, sample files, filter route, lpfMode, hpfMode, modFXType, arp mode/noteMode/octaveMode, patchCable structure; kit: sound count, sound names, per-sound sample files, per-sound osc types, per-sound arp mode, kit-level modFXType, kit-level filter modes)
  - [x] `ComparisonConfig.default()` uses existing constants for thresholds: `param_count_threshold=3`, `param_percent_threshold=0.10`, `ignored_attrs={"volume", "pan"}`
  - [x] `ComparisonResult` dataclass exists with fields: `is_distinct` (bool), `hard_diffs` (list of strings), `soft_diff_count` (int), `soft_diffs` (list of strings), `reason` (string)
  - [x] Existing `VersionComparison` dataclass removed or replaced
- **Implementation Notes:**
  > Completed 23 Apr 2026. `VersionComparison` removed and replaced by `ComparisonResult` (richer fields: `is_distinct`, `hard_diffs`, `soft_diff_count`, `soft_diffs`, `reason`). `ComparisonConfig` added after `NormalisationConfig` following the same dataclass pattern. `default()` classmethod consumes `DIFF_PARAM_COUNT_THRESHOLD`, `DIFF_PARAM_PERCENT_THRESHOLD`, `COMPARISON_EXCLUDED_ATTRS`. Hard marker dicts use element-path keys with sentinel values (`_structure`, `_count`, `_names`) for special structural comparisons that the engine (Task 4.2) will interpret. Test import updated (`VersionComparison` → `ComparisonResult` + `ComparisonConfig`). All 280 tests pass.

#### Task 4.2: Generalised comparison engine — `compare_instruments()`

- **Description:** Implement the generalised comparison function (research Section 16.4) that compares two assembled standalone presets for equivalence. Operates post-extraction, post-normalisation. Replaces the existing `compare_versions()` stub. The function walks the XML trees applying the three-tier comparison model: first checks hard markers (any single hard diff = immediately distinct), then counts soft marker diffs (must meet both per-param threshold and group count threshold), skipping ignored attrs throughout.
- **Inputs:** Two assembled standalone preset elements (post-extraction, post-normalisation), instrument type, comparison config
- **Outputs:** `ComparisonResult` with verdict, diffs, and reason
- **Acceptance Criteria:**
  - [x] Accepts two assembled standalone preset elements (the root `<sound>` or `<kit>` element), instrument type string, and a `ComparisonConfig`
  - [x] **Hard markers — synths:** Checks all synth hard markers from research Section 16.2 table — root `<sound>` attributes (`mode`, `polyphonic`, `modFXType`, `lpfMode`, `hpfMode`, `filterRoute`), oscillator attributes (`type`, `fileName` on `<osc1>` and `<osc2>`), arpeggiator attributes (`mode`, `noteMode`, `octaveMode`). Any single difference = immediately distinct.
  - [x] **Hard markers — kits:** Checks kit hard markers from research Section 16.2 — sound count in `<soundSources>`, sound names/identity, per-sound sample files and osc types, per-sound arp mode, kit-level modFXType, kit-level filter modes. Any single difference = immediately distinct.
  - [x] **Hard markers — patchCables (D19):** Compares the set of `(source, destination)` tuples from `<patchCables>`. Added/removed cables = hard diff. Amount differences are soft markers.
  - [x] **Soft markers:** For `<defaultParams>` attributes (excluding ignored), parses hex values as 32-bit signed integers. For extended hex strings (automation), uses first 10 chars only (D15). Calculates absolute difference as proportion of full range (`0x00000000` to `0x7FFFFFFF`). A param "differs" if proportional difference exceeds `config.param_percent_threshold`. Instrument is distinct if count of differing soft params ≥ `config.param_count_threshold`.
  - [x] **Soft markers — child elements (D24):** Walks into `<defaultParams>` children (`<envelope1>`, `<envelope2>`, `<equalizer>`) and compares their hex attributes using the same threshold logic. PatchCable `amount` values on matching cables are included as soft markers.
  - [x] **Soft markers — instrument-level settings (D24):** Includes attributes on `<delay>`, `<sidechain>`, and `<audioCompressor>` elements in the soft param count.
  - [x] **Kit per-sound comparison (research Section 16.5):** If kit structure matches (same sounds), applies soft-marker comparison per-sound. If any sound has enough soft diffs to be distinct, the whole kit is distinct.
  - [x] **Ignored attrs:** Skips attributes in `config.ignored_attrs` (default: volume, pan) throughout all tiers.
  - [x] Returns a `ComparisonResult` with `is_distinct`, `hard_diffs`, `soft_diff_count`, `soft_diffs`, and a human-readable `reason`.
  - [x] Old `compare_versions()` stub removed
- **Implementation Notes:**
  > Completed 23 Apr 2026. Implemented `compare_instruments()` as a generalised three-tier comparison engine in `extraction.py` (lines ~1450–1570). Also implemented 7 private helpers: `_parse_hex_value()`, `_hex_diff_exceeds()`, `_build_patchcable_dict()`, `_check_patchcable_structure()`, `_collect_soft_diffs()`, `_check_kit_structure_hard()`, `_compare_kit_soft()`. Added module constants `_HEX_VALUE_RE` and `_HEX_FULL_RANGE`. Removed the old `compare_versions()` stub entirely. Updated test import (`compare_versions` → `compare_instruments`). PatchCable structure is checked as a hard marker for both synths and kits (including per-sound patchCables in kits) per D19. For kit soft comparison, each sound is evaluated independently against the threshold — if any single sound exceeds it, the whole kit is distinct. Non-hex attribute differences (e.g. delay/sidechain integer attrs) count as soft diffs unconditionally. All 280 tests pass, ruff clean (only pre-existing warnings).

#### Task 4.3: Updated extended mode selection — `select_extended_clips()`

- **Description:** Update the `select_extended_clips()` stub to use the generalised comparison engine. The existing stub compares candidates against the baseline only. The updated version (D23) compares each candidate against ALL previously accepted clips — same pattern as cross-song dedup (research Section 18.2). Each candidate is first extracted and normalised to produce an assembled standalone preset, then compared using `compare_instruments()`.
- **Inputs:** `InstrumentClipGroup` with all clips for one instrument, `ComparisonConfig` instance
- **Outputs:** List of `ClipInfo` objects to extract (always includes baseline) plus comparison metadata
- **Acceptance Criteria:**
  - [x] Accepts an `InstrumentClipGroup` and a `ComparisonConfig`
  - [x] Sorts clips by section ID ascending
  - [x] Baseline clip (lowest section ID) is always accepted
  - [x] For each subsequent clip: extracts and normalises the candidate, then calls `compare_instruments()` against ALL previously accepted assembled presets
  - [x] If distinct from all accepted → accept. If similar to any accepted → reject.
  - [x] Returns accepted `ClipInfo` list plus the `ComparisonResult` metadata for each comparison (for manifest/logging)
  - [x] CLI code updated to pass `ComparisonConfig` to `select_extended_clips()` and remove the `--extended` early-exit error
  - [x] Console output indicates when multiple versions are extracted and which parameters differ
- **Implementation Notes:**
  > Completed 23 Apr 2026. Updated `select_extended_clips()` signature to accept `ComparisonConfig` and `NormalisationConfig` in addition to `InstrumentClipGroup`. Return type changed to `list[tuple[ClipInfo, list[ComparisonResult]]]` — each accepted clip carries its comparison results (empty for baseline). Internally assembles each candidate via `extract_synth()`/`extract_kit()` + `_strip_automation()` + `normalise_params()` before comparison. Uses early-break optimisation: rejects a candidate as soon as it's found similar to any accepted preset. CLI updated: removed `--extended` early-exit error, added `ComparisonConfig.default()` instantiation, wired `select_extended_clips()` with both configs, collects `differing_params` from comparison results into `ExtractionResult`, and appends diff count to console output for extended-mode extractions. All 274 tests pass (19 skipped stubs), ruff clean (only pre-existing warnings).

### Phase 5: Cross-Song Deduplication

> **Goal:** Implement post-extraction dedup that filters redundant instruments appearing in multiple songs
> **Prerequisites:** Phase 4 complete — comparison engine working

#### Task 5.1: Dedup function — `deduplicate_results()`

- **Description:** Implement the baseline + incremental acceptance algorithm (research Section 17.2) as a function in `extraction.py`. Groups extraction results by `(preset_name, instrument_type)`, ignoring preset folder (D21). Within each group, sorts by song name for deterministic ordering, accepts the first as baseline, then compares each subsequent result against all accepted using `compare_instruments()`. Returns accepted results and rejected results (for reporting).
- **Inputs:** Full list of `ExtractionResult` objects (post-extraction), `ComparisonConfig` instance
- **Outputs:** Accepted results list, rejected results list with metadata (which accepted result they matched)
- **Acceptance Criteria:**
  - [x] Groups results by `(preset_name, instrument_type)`, ignoring `preset_folder`
  - [x] Within each group, sorts by song name alphabetically for deterministic ordering
  - [x] First result in each group becomes baseline — automatically accepted
  - [x] Each subsequent result is compared against ALL accepted results in the group (not just baseline)
  - [x] If distinct from all accepted → accept. If similar to any accepted → reject.
  - [x] Returns both accepted and rejected lists, with rejected entries carrying the reason and which accepted result they matched
  - [x] Groups with only one result are passed through without comparison
  - [x] Handles both synth and kit instrument types correctly
- **Implementation Notes:**
  > Completed 23 Apr 2026. Added three items to `extraction.py`:
  > - `RejectedResult` dataclass — carries the rejected `ExtractionResult`, the `ExtractionResult` it matched against, and the `ComparisonResult`
  > - `DedupResult` dataclass — carries `accepted: list[ExtractionResult]` and `rejected: list[RejectedResult]`
  > - `deduplicate_results(results, config) -> DedupResult` — groups by `(preset_name, instrument_type)`, sorts each group by `song_name`, baseline-accepts first, compares subsequent against all accepted with early-break on first similar match. Groups iterate in sorted key order for deterministic output. All 274 tests pass (19 skipped stubs).

#### Task 5.2: CLI integration — dedup in the pipeline

- **Description:** Wire `deduplicate_results()` into the CLI pipeline in `extract_instruments.py`. Dedup runs after all songs are processed and before file writing (research Section 17.1). Add `--no-dedup` flag to disable. Update the summary output to include dedup stats. Only write accepted results to disk.
- **Inputs:** All extraction results from the per-song loop, `ComparisonConfig` instance
- **Outputs:** Filtered results written to disk, updated console output
- **Acceptance Criteria:**
  - [x] `--no-dedup` argparse flag added (disables dedup; dedup is on by default per D20)
  - [x] Dedup runs after the per-song extraction loop and before the summary/write phase
  - [x] Only accepted results are written to disk and included in manifests
  - [x] Summary line shows dedup stats: "Extracted X synths and Y kits from Z songs (N duplicates removed)"
  - [x] `--no-dedup` skips the dedup step entirely and writes all results
  - [x] `--extended --no-dedup` extracts everything from every song without any filtering
  - [x] `--extended` (without `--no-dedup`) applies intra-song extended selection then inter-song dedup
  - [x] Separate `ComparisonConfig` instances for intra-song (extended) and inter-song (dedup) comparison, both using `ComparisonConfig.default()` initially
- **Implementation Notes:**
  > Completed 23 Apr 2026. Changes to `extract_instruments.py`:
  > - Added `--no-dedup` argparse flag between `--extended` and `--dry-run`
  > - Imported `deduplicate_results` and `DedupResult` from `deluge_lib.extraction`
  > - Created separate `dedup_config = ComparisonConfig.default()` (D22 — threshold independence from `comp_config` used for intra-song extended mode)
  > - New "Dedup" section between extraction loop and summary: calls `deduplicate_results(all_results, dedup_config)` when `--no-dedup` is not set and `all_results` is non-empty, replaces `all_results` with accepted results only, stores `DedupResult` for future reporting (Task 5.3)
  > - Summary line appended with ` (N duplicates removed)` when dedup removes results; omitted when N=0 or dedup is disabled
  > - Only accepted results flow to the write phase (file writing, manifest generation)
  > - Flag combinations work as specified: default=dedup ON, `--no-dedup`=dedup OFF, `--extended`=dedup ON after extended selection, `--extended --no-dedup`=no filtering
  > - All 280 existing tests pass (1 pre-existing failure in `test_create_backup.py` unrelated to this task)

#### Task 5.3: Dedup reporting

- **Description:** Implement dedup reporting in the console output (research Section 17.6). After dedup runs, print a summary of removed duplicates grouped by preset name. The per-song extraction listing remains unchanged — it shows all extractions before dedup. The dedup summary appears between the per-song listing and the final summary.
- **Inputs:** Rejected results from `deduplicate_results()`
- **Outputs:** Formatted console output
- **Acceptance Criteria:**
  - [x] Prints "Dedup: Removed N duplicates (X synths, Y kits)" header
  - [x] For each preset name with removals, prints which song was kept and which songs were removed
  - [x] Format matches research Section 17.6 example: `000 (kit): kept Alr, removed Ape, Beginagain, ...`
  - [x] When dedup removes nothing, no dedup section is printed
  - [x] When `--no-dedup` is used, no dedup section is printed
- **Implementation Notes:**
  > Completed 23 Apr 2026. Added `_print_dedup_report(dedup_result)` function in `extract_instruments.py` (Helpers section).
  > - Groups rejected results by `(preset_name, instrument_type)`, builds kept song names from accepted list with matching key
  > - Prints header with total count and per-type breakdown, then sorted per-group lines: `preset_name (type): kept X, removed Y, Z`
  > - Called between dedup section and summary; guarded by `if dedup_result is not None` (covers `--no-dedup` case) and early return on empty rejected list (covers no-removals case)
  > - All 274 existing tests pass (1 pre-existing failure in `test_create_backup.py` unrelated)

### Phase 6: Testing and Verification

> **Goal:** Create test fixtures and automated tests to verify extraction correctness, comparison engine, and dedup
> **Prerequisites:** Phase 5 complete (or Phase 3 if testing default mode only first)

#### Task 6.1: Create test fixtures

- **Description:** Create minimal XML fixture files for testing. These should be small, hand-crafted XMLs that exercise the key extraction scenarios without being full-size song files.
- **Inputs:** Research document XML examples, Init-Synth.XML, Init-Kit.XML structure
- **Outputs:** Fixture files in `scripts/tests/fixtures/`
- **Acceptance Criteria:**
  - [x] Fixture: minimal song with one synth instrument and one session clip *(covered by existing inline builders in TestExtractSynth, TestDiscoverInstruments, etc.)*
  - [x] Fixture: minimal song with one kit instrument and one session clip with noteRows *(covered by existing inline builders in TestExtractKit)*
  - [x] Fixture: song with multiple sections of the same instrument (for comparison engine testing) *(TestSelectExtendedClips._make_synth_group builds multi-section groups)*
  - [x] Fixture: song with an orphaned instrument (no clips) *(covered by existing TestMatchInstrumentsToClips)*
  - [x] Fixture: song with clip arpeggiator having extra numeric attributes *(covered by existing TestExtractSynth.test_strips_extra_arpeggiator_attrs)*
  - [ ] Fixture: song with non-c1.2.1 firmware version *(deferred — TestDiscoverSongs stubs still skipped)*
  - [ ] Fixture: init synth and init kit reference files *(deferred — TestDiscoverSongs stubs still skipped)*
  - [x] Fixture: two preset elements with hard marker differences (different osc types) for comparison engine testing *(`_make_synth_preset()` helper with `osc1_type`/`osc2_type` overrides)*
  - [x] Fixture: two preset elements with soft marker differences (3+ params changed >10%) for comparison engine testing *(`_make_synth_preset()` with `lpfFrequency`, `hpfFrequency`, `env1_*` overrides)*
  - [x] Fixture: two nearly-identical preset elements (1-2 params changed) for dedup testing *(`_make_extraction_result()` + identical `_make_synth_preset()` elements)*
  - [x] Fixture: preset elements with different patchCable structures (added/removed cables) for hybrid patchCable comparison testing *(`_make_synth_preset(patchCables=[...])` with added/removed cables)*
- **Implementation Notes:**
  > Implemented 23 Apr 2026. Used inline builder functions (`_make_synth_preset()`, `_make_kit_preset()`, `_make_extraction_result()`) following the existing test file pattern. No separate fixture files created — all test data is constructed inline with keyword overrides for the specific scenario. Two plan criteria deferred (firmware version, init reference files) as they relate to TestDiscoverSongs which is a Phase 1.2 stub.

#### Task 6.2: Unit tests for extraction logic

- **Description:** Write pytest tests for the core extraction functions in `extraction.py`.
- **Inputs:** Test fixtures, extraction module
- **Outputs:** Test file `scripts/tests/test_extraction.py`
- **Acceptance Criteria:**
  - [x] Tests instrument-clip discovery and matching *(pre-existing: TestDiscoverInstruments, TestDiscoverClips, TestMatchInstrumentsToClips)*
  - [x] Tests synth transformation produces correct element ordering and attributes *(pre-existing: TestExtractSynth)*
  - [x] Tests kit transformation produces correct element ordering with noteRow params merged *(pre-existing: TestExtractKit)*
  - [x] Tests volume/pan normalisation (correct values, row preservation) *(pre-existing: TestNormaliseParams)*
  - [x] Tests arpeggiator extraction and extra attribute stripping for synths *(pre-existing: TestExtractSynth.test_extracts_arpeggiator_from_clip, test_strips_extra_arpeggiator_attrs)*
  - [x] Tests orphaned instrument detection and skipping *(pre-existing: TestMatchInstrumentsToClips.test_identifies_orphaned_instruments)*
  - [ ] Tests firmware version validation (skip non-c1.2.1) *(deferred — TestDiscoverSongs/TestFirmwareValidation stubs still skipped)*
  - [x] Tests filename generation and collision handling *(pre-existing: TestGenerateFilename)*
  - [x] Tests version comparison logic (extended mode) *(TestSelectExtendedClips — 5 tests)*
  - [x] Tests comparison engine — hard marker detection (osc type change = distinct) *(TestCompareInstruments.test_osc1_type_change_is_hard_distinct, test_osc2_type_change_is_hard_distinct, test_synth_mode_change_is_hard_distinct)*
  - [x] Tests comparison engine — soft marker threshold (3+ params at 10%+ = distinct, fewer = not distinct) *(TestCompareInstruments.test_soft_three_params_above_threshold_is_distinct, test_soft_two_params_below_threshold_not_distinct, test_soft_small_change_not_counted)*
  - [x] Tests comparison engine — ignored params (volume/pan changes do not affect verdict) *(TestCompareInstruments.test_volume_change_does_not_affect_verdict, test_pan_change_does_not_affect_verdict, test_volume_and_pan_combined_with_soft_diffs)*
  - [x] Tests comparison engine — patchCable hybrid comparison (structure vs amount) *(TestCompareInstruments.test_added_patchcable_is_hard_distinct, test_removed_patchcable_is_hard_distinct, test_patchcable_amount_change_is_soft_marker)*
  - [x] Tests comparison engine — kit per-sound comparison (one tweaked row makes entire kit distinct) *(TestCompareInstruments.test_kit_one_tweaked_row_makes_kit_distinct, test_kit_minor_tweak_not_distinct)*
  - [x] Tests comparison engine — envelope attributes treated as soft markers *(TestCompareInstruments.test_envelope_changes_are_soft_markers, test_envelope2_changes_are_soft_markers)*
  - [x] Tests dedup — baseline + incremental acceptance algorithm *(TestDeduplicateResults.test_identical_presets_deduplicated, test_distinct_presets_both_accepted)*
  - [x] Tests dedup — preset-name grouping (different names never compared) *(TestDeduplicateResults.test_preset_name_grouping, test_instrument_type_grouping)*
  - [x] Tests dedup — single-result groups pass through *(TestDeduplicateResults.test_single_result_passes_through, test_single_result_group_passes_through)*
  - [x] Tests dedup — compare-against-all-accepted (not just baseline) *(TestDeduplicateResults.test_compare_against_all_accepted)*
  - [x] Tests select_extended_clips with compare-against-all-accepted *(TestSelectExtendedClips.test_compare_against_all_accepted)*
  - [x] All tests pass with `pytest` *(313 passed, 9 skipped — all 9 skips are pre-existing Phase 1.2/firmware stubs)*
- **Implementation Notes:**
  > Implemented 23 Apr 2026. Added 3 test classes (TestCompareInstruments: 22 tests, TestSelectExtendedClips: 5 tests, TestDeduplicateResults: 11 tests) and 3 module-level helper builders (`_make_synth_preset`, `_make_kit_preset`, `_make_extraction_result`) to the existing `test_extraction.py`. Total: 39 new tests, all passing. No separate fixture files needed — inline builders with keyword overrides are sufficient. No source code bugs discovered during testing.

#### Task 6.3: Integration test with real songs

- **Description:** Run the script against the actual song library in dry-run mode. Verify output count and spot-check a few extractions against their standalone counterparts.
- **Inputs:** Full song library in `DELUGE/SONGS/`
- **Outputs:** Dry-run output, spot-check results
- **Acceptance Criteria:**
  - [x] Script runs to completion without errors on all 52 songs (library has 52 songs, not 58 — library changed since research)
  - [x] All warnings are expected and understood
  - [x] Extraction count is reasonable (each song should produce at least one instrument)
  - [x] Dedup removes a plausible number of results (expected 20-30% reduction per research Section 19.2)
  - [x] Kit "000" appears only once in output (or a small number of distinct versions)
  - [x] `--no-dedup` produces more results than default mode
  - [x] Spot-check: compare at least one extracted synth (e.g. from K01Sink) against its standalone counterpart to verify structural correctness
  - [x] Spot-check: compare at least one extracted kit (e.g. Deeper from Ell.XML) against its standalone counterpart
- **Implementation Notes:**
  > Verified 23 Apr 2026. Full integration test results:
  >
  > **Dry-run (default, dedup on):** 184 synths + 77 kits = 261 from 52 songs. Dedup removed 55 duplicates (33 synths, 22 kits). Total before dedup: 316, reduction: 17.4% (slightly below 20-30% estimate — reasonable given library has fewer songs than research analysed).
  >
  > **Kit "000" dedup:** 14 total appearances → 5 distinct versions kept (Alr, Ambient-Fishes, K01Sink, K09Arparty-old, SlpspkArpsOld), 9 removed. Correctly identifies structural differences between versions.
  >
  > **--no-dedup mode:** 217 synths + 99 kits = 316 total. Confirms dedup removes exactly 55 results (316 - 261 = 55). ✅
  >
  > **--extended mode:** 241 synths + 105 kits = 346 total (before dedup: 422). Extended mode found 106 additional distinct clip variants across songs. Dedup removed 76 duplicates. ✅ No errors.
  >
  > **Warnings (all expected):** Stripped automation (D10), orphaned instruments (D7: Arpo/000, K02Slpspk/043+049, K09Arparty/KRAF-BASS, No-More-Colour/012, Paddy/000), duplicate clips in same section (D14: Dject, K09Arparty-old, SlpspkArpsOld, Spook), kit sounds with no clip params (using defaults).
  >
  > **Spot-check synth (K01Bass from K01Sink):** Correct structure — `<sound>` root with osc1, osc2, lfo1, lfo2, unison, defaultParams (envelope1, envelope2, patchCables, equalizer), arpeggiator, modKnobs, delay, sidechain, audioCompressor. firmwareVersion=c1.2.1. ✅
  >
  > **Spot-check kit (Deeper from Ell):** Correct structure — `<kit>` root with defaultParams, delay, sidechain, audioCompressor, soundSources (5 sounds: Deep Sky Kick HQ9094, Rhythmace Snare, 909 Clap, etc.), selectedDrumIndex. firmwareVersion=c1.2.1. ✅
  >
  > **Test suite:** 319 passed, 9 skipped, 1 failed. The failure is a pre-existing issue in `test_create_backup.py` (period mismatch in assertion) — unrelated to extract_instruments. All extraction tests (313+) pass.

## Progress Tracker

| Phase | Status | Tasks Complete | Notes |
|-------|--------|---------------|-------|
| Phase 1: Foundation | Complete | 4/4 | Tasks 1.1 (scaffolding) ✅, 1.2 (discover_songs) ✅, 1.3 (instrument/clip discovery) ✅, 1.4 (default version selection) ✅ |
| Phase 2: Core Transformation | Complete | 3/3 | Tasks 2.1 (synth extraction) ✅, 2.2 (kit extraction) ✅, 2.3 (normalisation) ✅ |
| Phase 3: Output and CLI | Complete | 5/5 | Tasks 3.1 (filename generation) ✅, 3.2 (XML serialisation) ✅, 3.3 (trash mechanism) ✅, 3.4 (manifest entry) ✅, 3.5 (exit codes, init validation) ✅ |
| Phase 4: Comparison Engine & Extended Mode | Complete | 3/3 | Task 4.1 (ComparisonConfig/Result) ✅, Task 4.2 (compare_instruments) ✅, Task 4.3 (updated select_extended_clips) ✅ |
| Phase 5: Cross-Song Deduplication | Complete | 3/3 | Task 5.1 (deduplicate_results) ✅, Task 5.2 (CLI integration + --no-dedup) ✅, Task 5.3 (dedup reporting) ✅ |
| Phase 6: Testing and Verification | Complete | 3/3 | Task 6.1 (test fixtures) ✅, Task 6.2 (unit tests) ✅, Task 6.3 (integration test) ✅ |
| Phase 7: Post-Plan Enhancements | Complete | 10/10 | Sidechain detection ✅, SD-direct mode ✅, --naming flag ✅, --exclude-dir flag ✅, --verbose flag ✅, dynamic init loading ✅, init template ✅, two-pass dedup ✅, modKnobs hard marker ✅, threshold benchmark script ✅ |

## Open Questions

1. **What is the correct indentation/whitespace style for output XML?** ✅ Resolved
   - **Impact:** The Deluge firmware may be sensitive to XML formatting. If Init-Synth.XML uses tabs or specific indentation, the output should match.
   - **Recommendation:** Inspect Init-Synth.XML formatting during implementation and replicate it. lxml's `pretty_print` option with appropriate indentation should suffice.
   - **Blocking:** No — can be resolved during Task 3.2
   - **Resolution:** Hardware-tested. lxml's `pretty_print=True` with `encoding="UTF-8"` produces output that the Deluge firmware (c1.2.1) loads without issue. The Deluge re-normalises formatting to its preferred tab-indented style when the user saves the preset. No custom serialiser needed — use lxml's default pretty-print output.

2. **Should the manifest be one file per output directory or one combined file?** ✅ Resolved
   - **Impact:** Minor organisational choice. Two manifests (one per output dir) is slightly cleaner; one combined file is simpler to parse.
   - **Recommendation:** One per output directory (as specified in Task 3.4). Each manifest covers only its directory's contents.
   - **Blocking:** No
   - **Resolution:** One manifest per output directory, as originally recommended. Implemented in `_write_manifest()` in `extract_instruments.py`.

3. **How should extended mode handle automation data in parameter comparisons?** ✅ Resolved
   - **Impact:** Automation strings are variable-length hex (e.g. `0x7FFFFFFF7FFFFFFF000000607FFFFFFF00000120`). Comparing these verbatim would flag any automated parameter as "different" even if the base value hasn't changed.
   - **Recommendation:** For comparison purposes, extract the first 10 characters (one 32-bit hex value) from each attribute value as the "static" value. If the value is longer than 10 chars, it contains automation — use only the first value for comparison. Per D15, automation is ignored for comparison.
   - **Blocking:** No — only affects extended mode
   - **Resolution:** Resolved by research Section 16.2 (soft marker tier) and D15. Automation is stripped during extraction (`_strip_automation()`), so post-normalisation comparison sees only base values. For any residual automation strings, the comparison engine uses the first 10 chars.

4. **Should dedup threshold tuning be exposed to the user via CLI flags?**
   - **Impact:** Currently thresholds are developer-tunable constants in the `ComparisonConfig.default()` classmethod. A `--dedup-threshold` flag would let users control aggressiveness.
   - **Recommendation:** Not for v1. Keep thresholds as code constants. If users need tuning, add CLI flags in a future iteration.
   - **Blocking:** No

5. **Should dedup reporting support a `--verbose` flag for per-result match details?** ✅ Resolved
   - **Impact:** Research Section 17.6 suggests optionally showing which specific song × preset combinations were rejected and which accepted result they matched.
   - **Recommendation:** Defer. The default summary (preset name → kept/removed list) is sufficient for v1. Verbose mode can be added later if needed.
   - **Blocking:** No
   - **Resolution:** Implemented. `--verbose` flag added to CLI, passed through to `deduplicate_results()`. Verbose mode prints per-result match details showing which results were compared, matched, and rejected with reasons.

## References

### Research Document
- [extract-instruments-research.md](../research/extract-instruments-research.md) — Primary input. Transformation recipes (Section 13.5), structural comparisons (Sections 13.2–13.3), edge cases (Section 12), generalised comparison engine (Section 16), cross-song deduplication (Section 17), extended mode impact (Section 18), and duplication analysis (Section 19).

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
|------|--------|--------|
| 27 Apr 2026 | Hex range denominator fixed, threshold set to 10% / count 3 | `_HEX_FULL_RANGE` changed from `0x7FFFFFFF` (positive half) to `0xFFFFFFFF` (full unsigned span) for consistent % semantics across all parameter types. Default threshold set to `0.10` (10%) with count 3. 10% now means 10% of the parameter's total range regardless of display mapping (0–50, ±50, or ±25). |
| 27 Apr 2026 | Default percent threshold changed from 10% to 15% | Based on threshold benchmarking with 81 songs. 15% sits at a natural step in the data — past this point, default mode flattens at 265 instruments through 25%. Translates to ~3.75 display units on a 0–50 knob scale. |
| 27 Apr 2026 | Threshold benchmark script created | `dedup_threshold_test.py` — standalone script to benchmark dedup threshold configurations. Accepts `--percent` and `--count` ranges, runs extraction once then loops dedup with custom `ComparisonConfig` instances via `dataclasses.replace()`. Produces aligned markdown table to stdout, progress to stderr. Entry point: `deluge-threshold-test`. |
| 27 Apr 2026 | Plan updated to reflect post-plan enhancements | Added Phase 7 (9 post-plan features), decisions D25–D33, resolved Open Questions 2 and 5, updated CLI interface documentation. Feature is complete pending threshold tuning. |
| 27 Apr 2026 | modKnobs mapping added as hard marker (D33) | `_check_modknobs_structure()` added to comparison engine. Positional comparison of 16 `<modKnob>` entries by `controlsParam` and `patchAmountFromSource`. Checked for synths (top-level) and kits (per-sound). 7 new tests added. |
| 25 Apr 2026 | Two-pass dedup implemented (D32) | `deduplicate_results()` refactored into `_dedup_pass()` helper called twice: name-pass groups by `(preset_name, instrument_type)`, global-pass groups by `(instrument_type,)` only. `DedupResult` expanded with `name_pass_rejected` and `global_pass_rejected` fields. Dedup reporting updated with per-stage sections. |
| 24 Apr 2026 | Post-plan enhancements implemented | Sidechain detection (`is_sidechain_kit()`, `--include-sidechain`), SD-direct mode (`--sd-direct`, `get_sd_card_path()`), naming flag (`--naming preset/song`), exclude-dir (`--exclude-dir`), verbose dedup (`--verbose`), dynamic init loading (`load_init_defaults()`, `load_kit_init_template()`), init template for sounds without clip params (`_ensure_all_sounds_have_default_params()`). |
| 22 Apr 2026 | Task 1.4 implemented — Phase 1 complete | `select_default_clip()` implemented with `min()` on `clips_by_section` keys. 3 tests added in `TestSelectDefaultClip`. Phase 1 marked complete (4/4). |
| 22 Apr 2026 | Plan revised to reflect true implementation state after code audit | Phase 1 progress corrected (2/4 — Task 1.2 confirmed complete). Phase 3 status clarified (1/5 — only Task 3.3 truly complete; Tasks 3.4/3.5 partially scaffolded but depend on unimplemented stubs). Codebase audit note added to Research Summary. `print_path()` noted in Integration Points. |
| 22 Apr 2026 | Tasks 3.1, 3.2, 3.4, 3.5 implemented — Phase 3 complete | `generate_filename()` implemented with collision handling. `serialise_xml()` implemented with lxml pretty_print. `build_manifest_entry()` implemented mapping ExtractionResult to dict. CLI exit codes added (try/except + sys.exit(1)). Init preset validation added at startup (checks Init-Synth.XML and Init-Kit.XML). 7 new tests (5 filename + 2 serialisation), all passing. Phase 3 marked complete (5/5). |
| 23 Apr 2026 | Plan re-review: generalised comparison engine and cross-song dedup | Added research Sections 16–19 findings to Research Summary. Added decisions D16–D24 (comparison engine, dedup, config design, patchCables hybrid, threshold independence, etc.). Rewrote Phase 4 (was 2 tasks, now 3: ComparisonConfig/Result, compare_instruments(), updated select_extended_clips()). Added new Phase 5: Cross-Song Deduplication (3 tasks: deduplicate_results(), CLI integration with --no-dedup, dedup reporting). Renumbered Testing to Phase 6 and added comparison engine + dedup test criteria. Updated architecture data flow, key data structures, CLI interface (--no-dedup flag), console output format, cross-cutting concerns, and risk mitigation. Resolved Open Question 3 (automation handling). Progress Tracker updated (now 6 phases, 21 total tasks). |
| 23 Apr 2026 | Automation stripping post-processing added | `_strip_automation()` helper in `extraction.py` truncates extended hex automation strings to base values. Called from CLI script after extraction, before normalisation. 5 tests added. D10 reversed — standalone presets never contain automation. |
| 23 Apr 2026 | Task 4.2 implemented — `compare_instruments()` | Generalised three-tier comparison engine replacing `compare_versions()`. Implemented `compare_instruments()` + 7 helpers (`_parse_hex_value`, `_hex_diff_exceeds`, `_build_patchcable_dict`, `_check_patchcable_structure`, `_collect_soft_diffs`, `_check_kit_structure_hard`, `_compare_kit_soft`). Added `_HEX_VALUE_RE` and `_HEX_FULL_RANGE` constants. Removed old `compare_versions()` stub. Test import updated. PatchCable structure checked as hard marker for both synths and kits (per D19). All 280 tests pass. |
| 22 Apr 2026 | Tasks 2.2 and 2.3 implemented — Phase 2 complete | `extract_kit()` with helpers `_reorder_kit_children()`, `_reorder_kit_sound_children()`, `_merge_noterow_params()` implemented. `normalise_params()` implemented. 17 new tests (11 kit + 6 normalisation), all passing. Phase 2 marked complete (3/3). |
| 15 Apr 2026 | Updated plan to reflect scaffolding state | Task 1.1 complete, Tasks 3.3/3.4/3.5 substantially complete, trash path corrected, Task 1.4 API updated to use dataclasses |
| 14 Apr 2026 | Initial plan created | — |
