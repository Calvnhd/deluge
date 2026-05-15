# Research: Missing Reference Recovery

> **Document Type:** Research
> **Date:** 16 May 2026
> **Request:** Add hash-based and basename-based recovery for sample references classified as "missing" in `fix_references.py`, so that files moved before the manifest existed can be located and fixed automatically.
> **Pipeline:** Research → Plan → Implement

## Executive Summary

The `fix_references.py` script currently classifies XML sample references as "missing" when they don't match any entry in the migration map and the file doesn't exist at the referenced path. Analysis of the 14 real missing references shows that 13 are recoverable — the files exist on disk at different paths. The root cause is that files were moved *before* the manifest was created, so the manifest only knows the current path. Recovery requires building a basename→path index from data already computed during the migration map phase (`after_hashes`), then matching missing refs by filename. This is a low-risk, low-complexity enhancement that reuses existing data structures with no additional filesystem scanning or hashing.

## Objectives

- Understand exactly how `compute_migration_map` and `classify_ref_changes` work and what data is available at each stage
- Identify what data computed during migration map construction is currently discarded but useful for recovery
- Evaluate matching strategies: basename-only, hash-verified, fuzzy path matching
- Analyse the 14 real missing references to validate chosen strategy
- Determine where recovery fits in the existing classify/preview/apply flow
- Identify edge cases: duplicate basenames, renamed files, truly missing files

## Feature Overview

### Purpose and Value

When samples are reorganised *before* the manifest captures their original location, the migration map has no record of the old path. XML references to the old path fall through all classification checks and are reported as "missing" — a dead end requiring manual resolution. This enhancement adds a recovery step that searches the current filesystem by filename to locate the actual file and suggest a fix.

### Key Benefits

- **Eliminates manual investigation** for the most common "missing" scenario (files moved before manifest)
- **Handles historical path errors** — XML references that were always wrong (typos, wrong subfolder)
- **Reuses existing data** — no additional filesystem scanning or hashing required
- **Preserves safety model** — recovered refs are presented for review before applying

### Primary Use Case

User runs `fix_references.py` after reorganising samples. Some references show up as "missing" because the files were moved in a previous session before the manifest existed. The recovery step finds the files at their current paths and presents them as suggested fixes alongside regular migration map changes.

### Inputs and Outputs

| Item | Description |
|------|-------------|
| **Input** | `MigrationResult` from `compute_migration_map` (specifically `after_hashes`) |
| **Input** | Missing `SampleRef` entries from XML scanning |
| **Output** | `RecoveredRefChange` entries: missing path → candidate filesystem path |
| **Output** | `UnrecoverableMissingRef` entries: missing path with no match anywhere |

### Scope

**In scope:**
- Basename matching against current filesystem files
- Hash-based disambiguation when multiple candidates share a basename
- Path similarity ranking when hash alone doesn't disambiguate
- Integration with the existing preview/apply flow

**Out of scope:**
- Fuzzy/approximate filename matching (e.g. `uwahwah.wav` → `uwahwah2.wav`)
- Re-hashing the entire filesystem (performance constraint)
- Automatic application without user review
- Handling references to non-WAV files (e.g. the `MIDIFollow.XML` entry in the manifest)

## Existing Assets Analysis

| Capability | Status | Location | Notes |
|------------|--------|----------|-------|
| Migration map computation | ✅ Ready | [fix_references.py](../scripts/fix_references.py) `compute_migration_map()` | Builds `after_hashes` (hash→paths) but discards it; only returns `MigrationResult` |
| Hash→path index (after state) | ⚠️ Partial | [fix_references.py](../scripts/fix_references.py) L88–115 | Computed as local `after_hashes` dict inside `compute_migration_map()` but not exposed on `MigrationResult` |
| Ref classification | ✅ Ready | [fix_references.py](../scripts/fix_references.py) `classify_ref_changes()` | Handles moved/deleted/ambiguous/missing; missing is the dead end this feature addresses |
| Filesystem existence check | ✅ Ready | [deluge_sdk.py](../scripts/deluge_lib/deluge_sdk.py) `get_existing_samples()` | Returns normalised path set; used for "missing" check |
| Normalised key generation | ✅ Ready | [scanning.py](../scripts/deluge_lib/scanning.py) `normalise_key()` | Lowercase, forward-slash normalisation |
| Preview and apply flow | ✅ Ready | [fix_references.py](../scripts/fix_references.py) `preview_and_apply()` | Displays changes/errors/warnings/missing; already has section-based output |
| Manifest read/write | ✅ Ready | [syncing.py](../scripts/deluge_lib/syncing.py) | `read_manifest()`, `write_manifest()` |
| Test infrastructure | ✅ Ready | [test_fix_references.py](../scripts/tests/test_fix_references.py) | Comprehensive test suite with helpers for creating test trees, manifests, and XML files |

## Findings

### Finding 1: `after_hashes` Is the Key Missing Data

**Source:** [fix_references.py](../scripts/fix_references.py) lines 87–115

`compute_migration_map()` builds an `after_hashes: dict[str, list[str]]` mapping every SHA-256 hash to its original-case filesystem path(s). This dict represents the **complete current state** of the filesystem. It is used to build the `MigrationResult` (moved/deleted/added/ambiguous) and then discarded.

This dict contains everything needed for recovery:
- All current filesystem paths (original case preserved)
- All hashes (for disambiguation)
- Already computed — no additional I/O required

To make it available for recovery, it needs to be added to `MigrationResult`.

### Finding 2: Analysis of All 14 Real Missing References

**Source:** [fix-refs-output.log](../scripts/fix-refs-output.log) lines 12312–12329, [sync_manifest.json](../scripts/data/sync_manifest.json)

| # | XML Reference Path | Manifest Path (current location) | Same Hash? | Basename Match? | Recovery |
|---|---|---|---|---|---|
| 1 | `SAMPLES/FOUND/Tui/TuiWeo.wav` | `samples/found/tuiweo.wav` | ✅ | ✅ unique | ✅ Auto |
| 2 | `SAMPLES/LANDR/Sci-Fi Ambiences/CS-SCI-FI Sustain Breath 2.wav` | `samples/landr/_fx/sci-fi ambiences/...` + `samples/landr/premium sfx/one_shot/...` | ✅ (same hash at both) | ⚠️ 2 candidates | ⚠️ Ambiguous (same hash = duplicates, pick by path similarity) |
| 3 | `SAMPLES/LANDR/Computer SFX/FS_COM_Computer_Glitch_SFX 26.wav` | `samples/landr/_fx/computer sfx/...` + `samples/landr/premium sfx/one_shot/...` | ✅ (same hash at both) | ⚠️ 2 candidates | ⚠️ Ambiguous (same hash = duplicates, pick by path similarity) |
| 4 | `SAMPLES/LANDR/Birds/BritishHarborBirdsChirping_Y3Mls_07.wav` | `samples/landr/_fx/birds/...` | ✅ | ✅ unique | ✅ Auto |
| 5 | `SAMPLES/LANDR/Birds/MorningBirds_OTtBf_05.wav` | `samples/landr/_fx/birds/...` | ✅ | ✅ unique | ✅ Auto |
| 6 | `SAMPLES/LANDR/Dholak Session Vol 2/Dholak 72 - 8 Ptn.wav` | `samples/landr/_perc/dholak session vol 2/...` | ✅ | ✅ unique | ✅ Auto |
| 7 | `SAMPLES/COMMUNITY/1.2 Presets B-Sides/Low Drone Bass/uwahwah.wav` | Only `uwahwah2.wav` exists | ❌ | ❌ no match | ❌ Truly missing |

References 1–6 each appear in 1–3 XML files (kits, song-kits, songs), totalling 14 missing entries from 7 unique sample paths. 13 of 14 entries (6 of 7 unique paths) are recoverable via basename matching. The single unrecoverable case (`uwahwah.wav` vs `uwahwah2.wav`) is a genuine filename mismatch.

### Finding 3: Duplicate Files Create Multi-Candidate Scenarios

**Source:** Manifest entries for `FS_COM_Computer_Glitch_SFX 26.wav` and `CS-SCI-FI Sustain Breath 2.wav`

Two of the missing files exist at two different paths with identical hashes (true duplicates created during sample library reorganisation). Both copies are in the manifest. In these cases:

- Basename matching finds 2 candidates
- Hash comparison confirms they are duplicates (identical content)
- Path similarity can select the better match: the XML ref `SAMPLES/LANDR/Computer SFX/...` is closer to `samples/landr/_fx/computer sfx/...` than to `samples/landr/premium sfx/one_shot/...`

When all candidates share the same hash, the choice doesn't affect audio output — any copy will work. Path similarity is a reasonable tiebreaker for cleanliness.

### Finding 4: The `existing` Set Is Redundant with `after_hashes`

**Source:** [fix_references.py](../scripts/fix_references.py) `classify_ref_changes()` line 234, [deluge_sdk.py](../scripts/deluge_lib/deluge_sdk.py) `get_existing_samples()`

`classify_ref_changes()` calls `get_existing_samples(deluge_root)` to build a set of normalised paths for existence checking. This performs a **second** `scan_tree()` of the SAMPLES directory. The `after_hashes` dict from `compute_migration_map()` already contains all the same paths (with original case and hash data). If `after_hashes` is exposed on `MigrationResult`, the `existing` set can be derived from it, eliminating the redundant scan.

### Finding 5: Data Flow Through the Pipeline

**Source:** [fix_references.py](../scripts/fix_references.py) `main()`

```
main()
  ├── read_manifest() → manifest: FilesDict
  ├── compute_migration_map(manifest, deluge_root) → MigrationResult
  │     └── builds after_hashes locally (currently discarded)
  ├── classify_ref_changes(migration, deluge_root) → BrokenRefResult
  │     ├── builds deleted_paths, ambiguous_paths sets from migration
  │     ├── calls get_existing_samples() (redundant scan)
  │     └── classifies each XML ref → changes/errors/warnings/missing
  ├── preview_and_apply(broken, deluge_root) → (has_issues, applied)
  │     └── displays CHANGES/ERRORS/WARNINGS/MISSING sections
  └── update_manifest_keys() (if applied and moved files exist)
```

Recovery plugs in at the classification stage: after a ref is identified as "missing" (not in moved/deleted/ambiguous AND not in existing), attempt basename-based recovery before adding to the `missing` list.

## Approaches Considered

### Approach A: Basename Index from `after_hashes` (Recommended)

**How it works:**
1. Add `after_hashes: dict[str, list[str]]` field to `MigrationResult`
2. In `classify_ref_changes`, build a `basename_index: dict[str, list[tuple[str, str]]]` mapping lowercase basenames to `(original_path, hash)` tuples
3. Derive `existing` set from `after_hashes` values instead of calling `get_existing_samples()`
4. For each ref classified as "missing", look up its basename in the index:
   - **1 candidate** → `RecoveredRefChange` (auto-fixable)
   - **N candidates, same hash** → duplicates; pick closest path or report with candidates
   - **N candidates, different hashes** → ambiguous; report with candidates
   - **0 candidates** → truly missing (no file with that basename exists)
5. Add a `RECOVERED` section to `preview_and_apply` output

| Pros | Cons |
|------|------|
| Zero additional I/O — reuses computed data | Requires adding a field to `MigrationResult` |
| Handles the TuiWeo case and all LANDR cases | Basename-only matching may produce false positives for very common filenames |
| Hash disambiguation for multi-candidate matches | Cannot recover renamed files (different basename) |
| Eliminates redundant `scan_tree` call | |
| Simple implementation (~30–50 lines of new logic) | |

**Complexity:** Low

### Approach B: Manifest-Only Basename Lookup

**How it works:**
1. Build a basename index from manifest entries (before state)
2. For missing refs, look up basename in manifest
3. If found in manifest, check if the manifest path exists on disk

| Pros | Cons |
|------|------|
| No changes to `MigrationResult` | Manifest may not have the file if it was never synced |
| Simple to implement | Requires existence check per candidate (minor I/O) |
| | Less reliable — manifest may be stale |

**Complexity:** Low

### Approach C: Full Filesystem Re-Hash

**How it works:**
1. Call `hash_all_samples()` from `deluge_sdk.py` to hash every WAV file
2. Build comprehensive hash→path and basename→path indexes
3. Use hash matching as the primary recovery mechanism

| Pros | Cons |
|------|------|
| Most thorough — handles every possible case | Re-hashes entire filesystem (~6500 files) |
| Hash-based matching is definitive | Expensive: minutes of I/O for large sample libraries |
| | Duplicates work already done in `compute_migration_map` |

**Complexity:** Medium (but wasteful)

## Cross-Cutting Concerns

### Interaction with Migration Map Classification

Recovery runs *after* the existing migration map checks (moved/deleted/ambiguous). A ref only reaches recovery if it failed all prior checks. This means:
- Recovery cannot conflict with migration map results
- Recovery handles the gap that the migration map structurally cannot cover (paths that were never in the manifest)

### Interaction with `preview_and_apply`

The preview function currently has four sections: CHANGES, ERRORS, WARNINGS, MISSING. Recovery adds a fifth section (RECOVERED) or replaces some MISSING entries with recoverable changes. Design decision: should recovered refs be:
1. **Added to CHANGES** alongside migration map changes — simplest, but obscures provenance
2. **Shown in a separate RECOVERED section** — clearest for user review, recommended
3. **Mixed into MISSING with annotations** — confusing

Recommendation: separate RECOVERED section, displayed between CHANGES and ERRORS.

### Interaction with `update_manifest_keys`

Currently, `update_manifest_keys` only processes `migration.moved`. Recovered refs represent a similar old→new path mapping. If recovered refs are applied to XMLs, the manifest doesn't need updating — the manifest already knows the file at its current path.

### Redundant Filesystem Scan

`classify_ref_changes` currently calls `get_existing_samples()`, which runs `scan_tree()` a second time. If `after_hashes` is exposed on `MigrationResult`, the `existing` set can be derived as:
```python
existing = {normalise_key(p) for paths in migration.after_hashes.values() for p in paths}
```
This is a minor cleanup opportunity within scope of this feature.

## Risk Analysis

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| False positive: basename matches wrong file (same name, different content) | Low | Medium — would point XML to wrong audio | Hash comparison between candidates; report as ambiguous if hashes differ |
| Common basenames (e.g. `kick.wav`) matching dozens of files | Low | Low — reported as ambiguous, not auto-applied | Threshold: if >N candidates, skip recovery for that ref |
| Adding `after_hashes` to `MigrationResult` increases memory use | Very Low | Very Low — dict already exists, just retained longer | Negligible for ~6500 entries |
| Breaking existing test expectations | Low | Low — tests are well-structured | New tests for recovery; existing tests unchanged since recovery only applies to previously-missing refs |

## Recommendation

**Approach A (Basename Index from `after_hashes`)** is the clear choice. It:

1. **Solves 93% of real cases** — 13 of 14 missing entries (6 of 7 unique paths) are recoverable
2. **Requires zero additional I/O** — all data is already computed
3. **Is low-complexity** — ~30–50 lines of classification logic plus display updates
4. **Integrates cleanly** — plugs into the existing classification flow as a fallback after "missing" detection
5. **Eliminates a redundant scan** — `get_existing_samples()` call can be replaced

### Implementation Sketch

```python
# New field on MigrationResult
@dataclass
class MigrationResult:
    ...
    after_hashes: dict[str, list[str]] = field(default_factory=dict)

# New dataclass for recovered refs
@dataclass
class RecoveredRefChange:
    ref: SampleRef
    old_path: str
    new_path: str
    candidates: list[str]  # all candidates found (length 1 for unambiguous)

# In classify_ref_changes:
# 1. Build basename index from after_hashes
basename_index: dict[str, list[tuple[str, str]]] = defaultdict(list)
for h, paths in migration.after_hashes.items():
    for p in paths:
        basename_index[PurePosixPath(p).name.lower()].append((p, h))

# 2. Derive existing set (replaces get_existing_samples call)
existing = {normalise_key(p) for paths in migration.after_hashes.values() for p in paths}

# 3. For missing refs, attempt recovery:
bn = PurePosixPath(ref.path).name.lower()
candidates = basename_index.get(bn, [])
if len(candidates) == 1:
    result.recovered.append(RecoveredRefChange(...))
elif len(candidates) > 1:
    # Check if all candidates share the same hash (duplicates)
    # Pick best by path similarity, or report as ambiguous
    ...
else:
    result.missing.append(MissingRefError(...))
```

### Disambiguation Strategy for Multi-Candidate Matches

When multiple filesystem paths share the same basename:

1. **All same hash** → true duplicates. Pick the candidate whose path is most similar to the XML reference path (e.g. longest common path suffix). Auto-recover with the best match.
2. **Different hashes** → different files with same name. Report as ambiguous with all candidates listed. Do not auto-recover.

Path similarity metric: count matching path components from the end (basename already matches, so compare parent directories). In the `CS-SCI-FI Sustain Breath 2.wav` example:
- XML ref: `SAMPLES/LANDR/Sci-Fi Ambiences/CS-SCI-FI Sustain Breath 2.wav`
- Candidate A: `SAMPLES/LANDR/_FX/Sci-Fi Ambiences/CS-SCI-FI Sustain Breath 2.wav` — shares `Sci-Fi Ambiences` parent → 2 matching components
- Candidate B: `SAMPLES/LANDR/Premium SFX/One_Shot/CS-SCI-FI Sustain Breath 2.wav` — no matching parent → 1 matching component

Candidate A wins.

## Open Questions

1. **Should recovered refs be auto-applied alongside migration map changes, or require separate confirmation?**
   - **Impact:** UX design — separate confirmation adds friction but increases safety for a new, less-tested code path
   - **Recommendation:** Include recovered refs in the same apply step as migration map changes. They appear in a distinct RECOVERED section for visibility, but a single confirmation covers everything. The user can inspect and decline if any look wrong.
   - **Blocking:** No — defer to planning

2. **What is the maximum number of candidates before recovery gives up?**
   - **Impact:** Prevents noisy output for very common basenames like `kick.wav`
   - **Recommendation:** Cap at 5 candidates. If more than 5 files share a basename, skip recovery for that ref and leave it as "missing". This is a tunable constant.
   - **Blocking:** No — defer to planning

3. **Should the redundant `get_existing_samples()` scan be removed in this feature or as a separate cleanup?**
   - **Impact:** Minor performance improvement, code simplification
   - **Recommendation:** Remove in this feature since `after_hashes` provides the same data. It's a natural consequence of exposing `after_hashes`.
   - **Blocking:** No

4. **How should truly unrecoverable refs (0 candidates) be displayed?**
   - **Impact:** UX — currently all missing refs show the same message
   - **Recommendation:** Keep the existing MISSING section for truly unrecoverable refs. The section will naturally shrink as recovered refs move to the RECOVERED section.
   - **Blocking:** No

## References

### Project Files

- [fix_references.py](../../scripts/fix_references.py) — Main script with `compute_migration_map()`, `classify_ref_changes()`, `preview_and_apply()`
- [deluge_sdk.py](../../scripts/deluge_lib/deluge_sdk.py) — `get_existing_samples()`, `hash_file()`, `hash_all_samples()`
- [scanning.py](../../scripts/deluge_lib/scanning.py) — `normalise_key()`, `scan_tree()`
- [syncing.py](../../scripts/deluge_lib/syncing.py) — `read_manifest()`, `write_manifest()`, `FilesDict`
- [test_fix_references.py](../../scripts/tests/test_fix_references.py) — Existing test suite with helpers
- [fix-refs-output.log](../../scripts/fix-refs-output.log) — Real output showing 14 missing references
- [sync_manifest.json](../../scripts/data/sync_manifest.json) — Manifest with ~6538 entries, all with hashes
- [sample-scripts-research.md](sample-scripts-research.md) — Original research for the sample management scripts suite

## Next Steps

1. Review this document and resolve any blocking open questions
2. Invoke the Plan agent to create a feature plan from this research
