# Deduplication configuration comparison

Instrument extraction includes a deduplication process that checks whether two instruments are the same, such that the final output is a set of unique instruments when using the default settings. This doc includes information about the deduplication process and configuration, plus various benchmarks representing the results of configuration testing.

## Deduplication process

Extraction runs per-song, building a flat list of `ExtractionResult` objects. After all songs are processed, deduplication filters this list before any files are written to disk. With `--extended` mode, an intra-song comparison also runs during extraction to decide which clip versions of the same instrument are worth extracting separately.

The dedup function (`deduplicate_results()`) runs two passes:

1. **Name pass** — Groups results by `(preset_name, instrument_type)` and sorts alphabetically by song name. The first result in each group becomes the baseline (automatically accepted). Each subsequent result is compared against all accepted results in the group — if it's distinct from every one, it's accepted; if it's similar to any, it's rejected. This catches same-name duplicates across songs (e.g. kit "000" appearing in 12 songs).

2. **Global pass** — Takes the accepted results from pass 1 and groups them by `(instrument_type,)` only, sorted by `(preset_name, song_name)`. This catches cross-name duplicates where the user renamed a preset (e.g. "000" and "000 TR-808" that are structurally identical).

Dedup is enabled by default. Use `--no-dedup` to disable it.

### Hard vs soft markers, thresholds, sidechain detection

The comparison engine (`compare_instruments()`) uses a three-tier model:

**Hard markers** — Structural attributes where any single difference means two instruments are immediately distinct, regardless of other parameters. These include: synthesis mode, oscillator types, sample files, filter modes/routing, mod FX type, arpeggiator mode, patchCable routing (added/removed cables), unison voice count, and `<modKnobs>` knob assignments. For kits: sound count, sound names, and per-sound structural attributes. Hard markers are not configurable via thresholds — they always trigger.

**Soft markers** — Numerical hex parameters on `<defaultParams>` and its children (`envelope1`, `envelope2`, `patchCable` amounts, `equalizer`) plus instrument-level `<delay>`, `<sidechain>`, and `<audioCompressor>` attributes. Two thresholds control soft marker sensitivity:

- **% threshold** (`param_percent_threshold`) — The minimum proportional change for a single parameter to count as "different". Expressed as a fraction of the full unsigned 32-bit range (`0xFFFFFFFF`). At 10% (0.10), a parameter must change by ~5 display units on a 0–50 scale (or ~10 units on a ±50 scale) to count. This is consistent across all parameter types.
- **Count threshold** (`param_count_threshold`) — The minimum number of soft parameters that must individually exceed the % threshold for two instruments to be considered distinct. At count=3, at least 3 parameters must each differ by more than the % threshold.

An instrument pair is "distinct" (kept) if it triggers any hard marker OR meets both soft thresholds. It's "similar" (dedup candidate) if it triggers no hard markers and fewer than `count_threshold` parameters exceed the `%_threshold`.

**Ignored attributes** — Excluded from all comparison: `volume`, `pan` (normalised during extraction), `firmwareVersion`, `earliestCompatibleFirmware`, `modFXCurrentParam`, `currentFilterType`.

**Sidechain detection** — Before dedup, sidechain-only kits are detected and excluded by default (re-include with `--include-sidechain`). Detection uses two heuristics: (A) only 1 row has sequence data, that row's sound has `sideChainSend` near max, and volume is low; (B) the kit has a single sound with `sideChainSend` near max. These kits exist purely as sidechain triggers and aren't useful as standalone presets.

### Config representation and editing

Configuration lives in `scripts/deluge_lib/extraction.py`:

**Module-level constants** (top of file, ~line 81):
```python
DIFF_PARAM_COUNT_THRESHOLD = 3      # soft marker count threshold
DIFF_PARAM_PERCENT_THRESHOLD = 0.10  # soft marker % threshold (0.0–1.0)
```

These constants are consumed by `ComparisonConfig.default()`, which creates the config used by both intra-song extended mode comparison (`comp_config`) and cross-song dedup (`dedup_config`). Changing these constants affects both.

To tune thresholds: edit the two constants above, save, and re-run `uv run extract_instruments.py --dry-run` to preview the effect. No rebuild is needed — the constants are read at import time.

**Hard markers** are defined in `ComparisonConfig.default()` (~line 244) as dictionaries mapping element paths to attribute sets. These are structural and rarely need tuning.

**Ignored attributes** are also in `ComparisonConfig.default()` (~line 316) as a set. Add attribute names here to exclude them from all comparison tiers.

For advanced tuning, you can create separate configs for extended mode and dedup by modifying `extract_instruments.py` directly — the two `ComparisonConfig.default()` calls at lines 123–124 can be replaced with custom instances.

### Current default settings

| Setting | Default | Meaning |
|---------|---------|---------|
| `DIFF_PARAM_PERCENT_THRESHOLD` | `0.10` (10%) | A parameter must change by ≥10% of its full range to count |
| `DIFF_PARAM_COUNT_THRESHOLD` | `3` | At least 3 parameters must each exceed the % threshold |
| Sidechain detection | Enabled (excluded by default) | Sidechain-only kits filtered unless `--include-sidechain` |
| Dedup | Enabled (two-pass) | Name-pass then global-pass; disable with `--no-dedup` |

## Soft markers configuration comparision

Testing against the 81 songs currently present in `DELUGE/SONGS/`

No deduplication, we have 373/493

|--------------|-----------------|-----------------|
| Thresholds   | Default         | Extended        |
|--------------|-----------------|-----------------|
|    % | count |  Kit, Syn (tot) |  Kit, Syn (tot) |
|------|-------|-----------------|-----------------|
| none |  none |  133, 240 (373) |  178, 315 (493) |
|------|-------|-----------------|-----------------|

Minimal brings us down a little

|------|-------|-----------------|-----------------|
|   1% |     1 |   85, 204 (289) |  143, 331 (474) |
|------|-------|-----------------|-----------------|

Results taper off where count > 5 with aggressive % thresholds

|------|-------|-----------------|-----------------|
|  95% |     1 |   81, 173 (254) |  106, 193 (299) |
|  95% |     2 |   79, 169 (248) |   96, 189 (285) |
|  95% |     3 |   79, 162 (241) |   96, 182 (278) |
|  95% |     4 |   78, 160 (238) |   95, 180 (275) |
|  95% |     5 |   77, 158 (235) |   94, 178 (272) |
|  95% |     6 |   77, 158 (235) |   94, 178 (272) |
|  95% |     7 |   77, 158 (235) |   94, 178 (272) |
|  95% |     8 |   77, 158 (235) |   94, 178 (272) |
|  95% |     9 |   77, 158 (235) |   94, 178 (272) |
|  95% |    10 |   77, 158 (235) |   94, 178 (272) |
|------|-------|-----------------|-----------------|

A similar tapering occurs when count > 18 at permissible % thresholds

|------|-------|-----------------|-----------------|
|   1% |    14 |   77, 160 (237) |   94, 181 (275) |
|   1% |    15 |   77, 159 (236) |   94, 180 (274) |
|   1% |    16 |   77, 158 (235) |   94, 179 (273) |
|   1% |    17 |   77, 158 (235) |   94, 179 (273) |
|   1% |    18 |   77, 158 (235) |   94, 178 (272) |
|   1% |    19 |   77, 158 (235) |   94, 178 (272) |
|   1% |    20 |   77, 158 (235) |   94, 178 (272) |
|------|-------|-----------------|-----------------|

Confirm this taper is the actual floor

|------|-------|-----------------|-----------------|
|  99% |    50 |   77, 158 (235) |   94, 178 (272) |
|------|-------|-----------------|-----------------|

So we have...

No duplication:         373/493  
Minimal dupe checks:    289/474 (-84/-19)
Aggressive dupe checks: 235/272 (-54/-202)

So a good sweet is probably somewhere between minimal and aggressive at around 262/373
There's a tradeoff between lower count and higher percentage vs higher count and lower percentage

Let's go with 10% / 3 as defaults for now

|------|-------|-----------------|-----------------|
|  10% |     3 |   80, 185 (265) |  106, 234 (340) |
|------|-------|-----------------|-----------------|
|   5% |     4 |   78, 186 (264) |  101, 233 (334) |
|------|-------|-----------------|-----------------|
|   5% |     5 |   78, 183 (261) |   99, 217 (316) |
|------|-------|-----------------|-----------------|
