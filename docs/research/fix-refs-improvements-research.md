# Research: Fix References Improvements

> **Document Type:** Research
> **Date:** 16 May 2026
> **Request:** Investigate two issues discovered during real-world testing of `fix_references.py` — manifest lifecycle data loss and overly aggressive ambiguity classification — and evaluate approaches to resolve them.
> **Pipeline:** Research → Plan → Implement

## Executive Summary

Two issues prevent `fix_references.py` from resolving many broken XML sample references after file reorganisation. Issue 1: `build_post_sync_manifest()` in `syncing.py` rebuilds the manifest solely from the SD card's current state, silently dropping entries for files that were moved before the sync — by the time `fix_references` runs, the old path→hash data needed for move detection is gone. Issue 2: `compute_migration_map()` classifies all N:M hash mappings (where N≠1 or M≠1) as "ambiguous", even fully resolvable N:1 cases where one path survived and the rest were deleted. Of the five approaches proposed, two are recommended for immediate implementation: **Approach E (resolve N:1 mappings)** for Issue 2, and **Approach D (path-similarity recovery)** as a strengthened fallback. A manifest-level fix (Approach A) is recommended as a follow-up to prevent Issue 1 at its source.

## Objectives

- Trace the complete data flow through `sync_from_sd` → manifest → `fix_references` to identify exactly where old path→hash data is lost
- Analyse how `compute_migration_map()` handles N:M hash mappings and identify which cases are resolvable
- Evaluate all five proposed approaches (A through E) for correctness, complexity, and implementation priority
- Identify edge cases around truly ambiguous moves (N files with the same hash shuffled to N new locations)
- Determine whether path-similarity recovery (Approach D) can serve as a universal fallback
- Assess whether N:1 resolution (Approach E) can extend to N:M cases

## Feature Overview

### Purpose and Value

After samples are reorganised on the Deluge SD card, XML presets (kits, synths, songs) contain stale file paths. `fix_references.py` detects these moves by comparing a "before" state (the sync manifest) to an "after" state (the current filesystem) and rewrites XML references. Two bugs prevent it from resolving the majority of real-world broken references, producing either "missing" or "ambiguous warning" classifications for fixable cases.

### Key Benefits

- **Fixes 151+ broken references** that currently produce warnings instead of automatic fixes (Issue 2)
- **Recovers ~48 references** that currently fall through as missing due to lost manifest data (Issue 1)
- **Reduces manual intervention** — the user currently must hand-fix or re-run with workarounds

### Primary Use Cases

1. User reorganises samples on SD card → syncs to repo → runs `fix_references` → expects automatic XML updates
2. User deletes duplicate samples after consolidation → runs `fix_references` → expects references to point to surviving copy

### Inputs and Outputs

| Item | Description |
|------|-------------|
| **Input** | `sync_manifest.json` — before-state hash→path mapping |
| **Input** | Current filesystem under `DELUGE/SAMPLES/` — after-state |
| **Input** | XML files in `DELUGE/KITS/`, `DELUGE/SYNTHS/`, `DELUGE/SONGS/` |
| **Output** | Updated XML files with corrected `fileName` attributes |
| **Output** | Updated manifest keys for moved files |

### Scope

**In scope:**
- Fixing the N:1 ambiguity classification in `compute_migration_map()`
- Improving the basename/path-similarity recovery fallback
- Preventing manifest data loss during `sync_from_sd` (research/recommendation — implementation may be separate)

**Out of scope:**
- Fuzzy filename matching (e.g. `uwahwah.wav` → `uwahwah2.wav`)
- Changes to the Deluge firmware or XML schema
- `sync_to_sd.py` direction (writing to SD card)

## Existing Assets Analysis

| Capability | Status | Location | Notes |
|------------|--------|----------|-------|
| Migration map computation | ✅ Ready | [fix_references.py](../../scripts/fix_references.py) `compute_migration_map()` | Builds before/after hash maps, classifies moves |
| N:M ambiguity classification | ⚠️ Overly strict | [fix_references.py](../../scripts/fix_references.py) L144–148 | All non-1:1 cases go to `ambiguous` — N:1 is resolvable |
| Basename recovery | ✅ Ready | [fix_references.py](../../scripts/fix_references.py) `classify_ref_changes()` | Works for missing refs; blocked by ambiguity pre-emption |
| Path similarity scoring | ✅ Ready | [fix_references.py](../../scripts/fix_references.py) `path_similarity()` | Counts matching trailing path components; already tested |
| Manifest rebuild | ⚠️ Lossy | [syncing.py](../../scripts/deluge_lib/syncing.py) `build_post_sync_manifest()` | Iterates only `src_scan.files`; drops entries not in current scan |
| Manifest I/O | ✅ Ready | [syncing.py](../../scripts/deluge_lib/syncing.py) `read_manifest()`, `write_manifest()` | v2 format with hash field |
| `after_hashes` on MigrationResult | ✅ Ready | [fix_references.py](../../scripts/fix_references.py) `MigrationResult.after_hashes` | Added during recovery feature; exposes current filesystem hash→paths |
| Existing test suite | ✅ Comprehensive | [test_fix_references.py](../../scripts/tests/test_fix_references.py) | ~50 tests covering migration map, classification, recovery, preview |

## Findings

### Finding 1: Exact Mechanism of Manifest Data Loss (Issue 1)

**Source:** [syncing.py](../../scripts/deluge_lib/syncing.py) `build_post_sync_manifest()` lines 126–187, [sync_from_sd.py](../../scripts/sync_from_sd.py) lines 87–92

The data loss occurs in `build_post_sync_manifest()` at line 148:

```python
for key, src_entry in src_scan.files.items():
    if key in old_files and key not in copied_keys:
        updated_manifest[key] = old_files[key]
    else:
        # ... create new entry and queue for hashing
```

The function iterates **only over `src_scan.files`** — the SD card's current state. It preserves old manifest entries only when their key matches a key in the current scan. The final manifest contains:
- Entries for every file currently on the SD card (the source)
- Old manifest entries preserved for unchanged files (key match + not copied)
- **Nothing** for files that existed in the old manifest but are absent from the current scan

There is one exception: the `file_filter` block at lines 180–186 preserves old entries for file types not included in a filtered sync (e.g. WAV entries preserved during an XML-only sync). But for a full sync (`file_filter="both"`), this doesn't help — all old entries for files no longer on the SD card are silently dropped.

**Data flow timeline:**
1. Manifest has `samples/artists/kody nielson/1.wav` → hash X
2. User moves files on SD card: `Artists/` → `FACTORY/Artists/`
3. `sync_from_sd` runs, scanning the SD card (source) → `src_scan` has `samples/factory/artists/kody nielson/1.wav`
4. `build_post_sync_manifest` iterates `src_scan.files` — old key `samples/artists/kody nielson/1.wav` is not present
5. New manifest only has `samples/factory/artists/kody nielson/1.wav` → hash X
6. `fix_references` runs: before-state = manifest (new paths only), after-state = filesystem (same new paths) → no moves detected
7. XML refs pointing to old paths fall through to recovery; generic basenames like `1.wav` exceed `MAX_RECOVERY_CANDIDATES` (5) → "missing"

### Finding 2: The N:1 Ambiguity Bug (Issue 2)

**Source:** [fix_references.py](../../scripts/fix_references.py) `compute_migration_map()` lines 133–148

The comparison logic:

```python
for h in set(before_dict) | set(after_dict):
    bpaths = before_dict.get(h, [])
    apaths = after_dict.get(h, [])
    apaths_norm = [normalise_key(p) for p in apaths]

    if bpaths and not apaths:
        deleted[h] = list(bpaths)
    elif apaths and not bpaths:
        added[h] = list(apaths)
    elif len(bpaths) == 1 and len(apaths) == 1:
        if bpaths[0] != apaths_norm[0]:
            moved[bpaths[0]] = apaths[0]
    else:
        ambiguous[h] = (list(bpaths), list(apaths))
```

The `else` branch catches **every** case where `len(bpaths) != 1` or `len(apaths) != 1`. This includes fully resolvable scenarios:

| Before | After | Current Classification | Correct Classification |
|--------|-------|----------------------|----------------------|
| 2 paths | 1 path | Ambiguous | Resolvable: match surviving path, classify rest as deleted |
| N paths | 1 path | Ambiguous | Resolvable: same logic |
| 1 path | 2 paths | Ambiguous | Resolvable: match surviving path, classify new path as added duplicate |
| N paths | M paths (N≠M, some overlap) | Ambiguous | Partially resolvable |
| N paths | N paths (no overlap) | Ambiguous | Truly ambiguous |

The real-world scenario from Issue 2: after manually recovering files and syncing, the manifest has BOTH old (`samples/artists/kody nielson/1.wav`) and new (`samples/factory/artists/kody nielson/1.wav`) paths with the same hash. After deleting the duplicate at the old path, the filesystem has only the new path. This creates a 2:1 mapping that is fully resolvable but classified as ambiguous.

### Finding 3: Ambiguous Refs Pre-empt Recovery

**Source:** [fix_references.py](../../scripts/fix_references.py) `classify_ref_changes()` lines 265–275

The classification priority order in `classify_ref_changes`:
1. Check `migration.moved` → PlannedChange
2. Check `deleted_paths` → BrokenRefError
3. Check `ambiguous_paths` → AmbiguousRefWarning ← **blocks recovery**
4. Check `existing` set → valid (skip)
5. Attempt basename recovery → RecoveredRefChange or MissingRefError

When a ref's normalised path appears in `ambiguous_paths` (all before-paths from ambiguous entries), it becomes a warning at step 3 and **never reaches** the recovery logic at step 5. This is why Issue 2 produces 151 warnings — the refs are trapped in the ambiguity check.

### Finding 4: N:1 Resolution Is Safe and Deterministic

**Source:** Analysis of `compute_migration_map()` hash comparison logic

For an N:1 hash mapping (N before-paths, 1 after-path):
- The after-path either matches one of the before-paths (normalised) or it doesn't
- **If it matches one:** that before-path is "unchanged", all other before-paths are "deleted" (their content survives at the matching path)
- **If it matches none:** this is a move + delete scenario — one before-path moved to the after-path, all others were deleted. Since all before-paths had the same content (same hash), it doesn't matter *which* before-path we attribute the move to. XML refs to any of the deleted before-paths should point to the after-path.

In both sub-cases, the resolution is deterministic and safe: all XML refs to deleted before-paths should be rewritten to the surviving after-path.

### Finding 5: N:M Resolution Is Partially Possible

**Source:** Analysis of migration map edge cases

For N before-paths → M after-paths (N>1, M>1):
1. **Find overlaps:** before-paths whose normalised form matches an after-path normalised form → "unchanged"
2. **Remove overlaps** from both sets
3. **Remaining 1:1:** if exactly 1 before-path and 1 after-path remain → "moved"
4. **Remaining N:1 or 1:M:** apply N:1 / 1:M resolution
5. **Remaining N:M (N>1, M>1, no overlaps):** truly ambiguous — cannot determine which before-path maps to which after-path

This decomposition approach reduces the number of truly ambiguous cases. However, step 5 cases (true N:M with no overlaps) are genuinely unresolvable without additional heuristics (e.g. path similarity).

### Finding 6: Path Similarity as Universal Fallback (Approach D)

**Source:** [fix_references.py](../../scripts/fix_references.py) `path_similarity()` lines 181–205, existing recovery logic lines 307–340

`path_similarity()` already exists and is tested. It counts matching trailing path components (case-insensitive). The current recovery logic already uses it as a tiebreaker for multi-candidate same-hash basename matches.

**Could it replace manifest-level fixes?** Partially:
- For Issue 1 (manifest data loss): basename recovery with path similarity *already works* for unique basenames. The problem is generic basenames like `1.wav` that exceed `MAX_RECOVERY_CANDIDATES`. Raising the threshold wouldn't help — `1.wav` could match dozens of files across the library, and path similarity cannot reliably pick the right one without hash verification.
- For Issue 2 (N:1 ambiguity): path similarity could help, but it's unnecessary — the N:1 case has a deterministic solution (Finding 4) that doesn't require heuristics.

**Conclusion:** Path similarity is a useful enhancement for the recovery fallback but is not a substitute for fixing the root causes.

### Finding 7: `MAX_RECOVERY_CANDIDATES` Threshold Behaviour

**Source:** [fix_references.py](../../scripts/fix_references.py) line 190, [test_fix_references.py](../../scripts/tests/test_fix_references.py) `TestCandidateThresholdExceeded`

The current threshold is 5. For Issue 1's real data, the `Artists/` files have basenames like `1.wav`, `2.wav`, etc. — extremely common in sample libraries. A scan of the filesystem would likely find dozens of files named `1.wav`, making basename-only matching unreliable regardless of the threshold.

However, if the hash is known (from the manifest), path similarity combined with hash verification could resolve these cases even with many candidates. The problem is that Issue 1's scenario is precisely the one where the hash is *not* in the manifest (it was dropped).

### Finding 8: Manifest Move Log (Approach A) Is the Root Fix for Issue 1

**Source:** [syncing.py](../../scripts/deluge_lib/syncing.py) `build_post_sync_manifest()` lines 126–187

`build_post_sync_manifest()` has access to both:
- `old_files` — the previous manifest (before-state)
- `src_scan.files` — the SD card's current state (after-state)

It already iterates `src_scan.files` and checks `old_files`. Detecting moves requires:
1. Build hash→key index from `old_files`
2. For each new entry in `src_scan.files` that is NOT in `old_files` by key, look up its hash in the old index
3. If found, record `old_key → new_key` as a move

This move log could be:
- Stored in the manifest as a `"moves"` section (schema change)
- Written to a sidecar file (e.g. `sync_manifest_moves.json`)
- Returned from the function and consumed immediately by `fix_references` if invoked as part of the sync pipeline

The simplest option is adding a `"moves"` dict to the manifest JSON. `fix_references` already reads the manifest; it would check for a `"moves"` key and merge those into its migration map.

### Finding 9: Test Infrastructure Supports All Changes

**Source:** [test_fix_references.py](../../scripts/tests/test_fix_references.py)

The test suite has:
- `_make_deluge_tree()` — creates filesystem trees with specific WAV content
- `_make_manifest()` — creates manifest dicts with specific hashes
- `_write_minimal_kit_xml()` — creates XML files with specific sample refs
- Comprehensive tests for every classification path including recovery

All proposed changes (N:1 resolution, improved recovery, manifest moves) can be tested using the existing infrastructure with minimal additions.

## Approaches Considered

### Approach A: Move Log During Sync

Record detected moves in the manifest when `build_post_sync_manifest()` sees an old hash appear at a new path.

| Pros | Cons | Complexity |
|------|------|------------|
| Fixes Issue 1 at its root cause | Requires manifest schema change (new `"moves"` key) | Medium |
| Move data captured at the only point where both states are available | Touches `syncing.py` (shared by multiple sync scripts) | |
| Zero false positives — hash-verified moves | `fix_references` must be updated to consume moves data | |
| Enables automatic resolution of even generic basenames | Only helps for *future* syncs — cannot retroactively fix | |

### Approach B: Run fix_refs as Part of Sync

Invoke migration map logic during `sync_from_sd` before the manifest is rewritten.

| Pros | Cons | Complexity |
|------|------|------------|
| Old manifest data is available at the right time | Tightly couples sync and ref-fixing — currently separate concerns | High |
| Could fix XML refs immediately after sync | Changes the user workflow (currently sync and fix are separate steps) | |
| | Harder to test in isolation | |

### Approach C: Never Delete Manifest Entries

Mark old entries as "relocated" instead of dropping them.

| Pros | Cons | Complexity |
|------|------|------------|
| Preserves all historical path→hash data | Manifest grows unboundedly over time | Medium |
| Simple to implement | Introduces "ghost" entries that complicate manifest consumers | |
| | Other tools reading the manifest must filter relocated entries | |

### Approach D: Path-Similarity Recovery Enhancement

Improve the recovery fallback to use path similarity more aggressively, potentially raising `MAX_RECOVERY_CANDIDATES` or adding hash-verified path matching.

| Pros | Cons | Complexity |
|------|------|------------|
| No manifest changes needed | Cannot resolve Issue 1 for generic basenames (hash unknown) | Low |
| Improves recovery for all missing refs, not just manifest-related ones | Heuristic — path similarity can pick the wrong match | |
| Incremental improvement, low risk | Doesn't address Issue 2 at all (refs trapped in ambiguity check) | |

### Approach E: Resolve N:1 Hash Mappings

In `compute_migration_map()`, decompose N:1 (and partially N:M) cases instead of classifying all non-1:1 cases as ambiguous.

| Pros | Cons | Complexity |
|------|------|------------|
| Directly fixes Issue 2 (151 warnings → automatic fixes) | Slightly more complex classification logic | Low–Medium |
| Deterministic — no heuristics needed for N:1 | N:M cases (N>1, M>1, no overlap) remain truly ambiguous | |
| Refs to deleted before-paths become moves to the survivor | Must carefully handle the overlap-detection logic | |
| Compatible with existing test infrastructure | | |

## Cross-Cutting Concerns

### Interaction Between Approach E and Recovery

Approach E fixes Issue 2 by resolving N:1 mappings in `compute_migration_map()`, moving refs from "ambiguous" to "moved" or "deleted". This means fewer refs hit the `ambiguous_paths` check in `classify_ref_changes()`, allowing more refs to reach the recovery fallback. The two approaches are complementary: E handles manifest-aware cases, recovery handles cases where the manifest lacks data.

### Manifest Schema Stability

Approach A adds a `"moves"` key to the manifest JSON. Consumers must handle its absence gracefully (older manifests won't have it). Since `read_manifest()` already ignores unknown keys, this is backwards-compatible. `fix_references` would check `data.get("moves", {})`.

### Impact on `sync_to_sd.py`

`sync_to_sd.py` calls the same `build_post_sync_manifest()` with `source_is_sd=False`. Approach A's move detection logic would apply equally to both sync directions. Since the move log is informational (read by `fix_references`, not by sync itself), this is harmless.

### Impact on `sync_samples_to_cloud.py`

This script does not use the sync manifest — it has its own cloud manifest. No impact.

### Manifest Key Update After Apply

Currently, `update_manifest_keys()` in `fix_references.py` only processes `migration.moved`. If Approach E promotes refs from "ambiguous" to "moved", those new moved entries will automatically be included in the manifest key update. No additional changes needed.

## Risk Analysis

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| N:1 resolution incorrectly resolves a genuinely ambiguous case | Very Low | Medium — would rewrite XML refs to wrong path | N:1 with one surviving path is deterministic; all before-paths had identical content (same hash), so any surviving path is correct |
| Manifest `"moves"` key conflicts with future manifest changes | Low | Low — additive schema change | Use a descriptive key name; document in manifest version notes |
| Raised `MAX_RECOVERY_CANDIDATES` produces false positive recovery | Medium | Medium — would point XML to wrong file | Only raise threshold when hash verification is available; keep strict for hash-unknown cases |
| N:M decomposition logic has edge cases | Low | Medium — could misclassify some refs | Start with N:1 only; extend to N:M in a follow-up after real-world validation |
| Approach A only helps future syncs, not past data | Certain | Low — one-time issue | Combine with Approach E to handle the current state; Approach A prevents recurrence |

## Recommendation

### Immediate (This Feature)

**Implement Approach E first, then optionally enhance Approach D.**

1. **Approach E — Resolve N:1 mappings** (Priority 1, fixes Issue 2):
   - In `compute_migration_map()`, replace the blanket `else: ambiguous` with decomposition logic
   - For N before-paths → 1 after-path: match the after-path against before-paths by normalised key. The matching before-path is "unchanged"; all others generate `moved[before_path] = after_path`
   - For 1 before-path → M after-paths: the before-path that matches an after-path is "unchanged"; the after-path that doesn't match is "added". If no match, treat as 1:1 move to the first after-path (arbitrary but safe since all have the same content)
   - For N:M with overlaps: remove overlapping pairs (unchanged), then apply N:1/1:M/1:1 logic to residuals
   - For true N:M with no overlaps and N>1, M>1: keep as ambiguous
   - Expected impact: resolves 151 warnings from Issue 2's test run

2. **Approach D enhancement** (Priority 2, improves Issue 1 fallback):
   - For refs that reach the recovery fallback with >MAX_RECOVERY_CANDIDATES, add a "hash-verified path similarity" sub-strategy: if the ref's old path has a hash in the manifest, filter candidates by hash first, then apply path similarity to the hash-matched subset
   - This won't help when the manifest hash is missing (Issue 1's core problem) but improves recovery for cases where the hash exists but basename matching is too broad
   - Keep `MAX_RECOVERY_CANDIDATES` at 5 for hash-unknown cases

### Follow-Up (Separate Feature)

3. **Approach A — Move log during sync** (Priority 3, prevents Issue 1 recurrence):
   - Recommended as a separate plan/implement cycle because it touches the manifest schema and sync pipeline
   - Will prevent future data loss by recording moves at the point where both old and new states are available
   - Should include: schema version bump to v3, graceful handling of v2 manifests, documentation of the `"moves"` key

### Rationale for Ordering

- Approach E is **low-complexity, high-impact** — directly fixes the 151 warnings from the real-world test and requires changes only in `compute_migration_map()`
- Approach D is a **minor enhancement** to existing recovery logic that improves resilience
- Approach A is the **correct long-term fix** but has higher complexity (manifest schema, sync pipeline changes) and only benefits future syncs
- Approaches B and C are not recommended: B over-couples sync and ref-fixing, C introduces manifest bloat

## Open Questions

1. **Should N:M decomposition go beyond N:1 in the first implementation?**
   - **Impact:** Determines scope and complexity of the `compute_migration_map()` changes
   - **Recommendation:** Implement the full overlap-removal decomposition (N:M with overlap reduction) in one pass. The logic is straightforward: find overlaps, remove them, classify residuals. Restricting to N:1 only would leave some resolvable cases unhandled.
   - **Blocking:** No — the planner can decide scope

2. **Should Approach A be part of this feature or a separate pipeline cycle?**
   - **Impact:** Determines the scope boundary of this implementation
   - **Recommendation:** Separate pipeline cycle. Approach A touches `syncing.py` (shared infrastructure), the manifest schema, and the sync workflow. Approach E alone resolves the immediate issue.
   - **Blocking:** No

3. **Should `update_manifest_keys` also process recovered refs (from Approach D)?**
   - **Impact:** After recovery, the manifest still has the old key pointing to the old path. If recovery rewrites XML refs, the manifest should reflect the new path.
   - **Recommendation:** Yes — extend `update_manifest_keys` to accept both `migration.moved` and recovered ref mappings. This keeps the manifest consistent with the XML state.
   - **Blocking:** No — defer to planning

4. **Should the decomposition logic produce a new `resolved_ambiguous` field on `MigrationResult` for traceability?**
   - **Impact:** Debugging and logging — would allow the preview output to show "resolved N:1" vs "simple move"
   - **Recommendation:** Not necessary for correctness. Resolved N:1 cases can go directly into `moved` and `deleted`. If traceability is desired, add a counter or log message rather than a new dataclass field.
   - **Blocking:** No

## References

### Project Files

- [fix_references.py](../../scripts/fix_references.py) — Migration map computation, classification, recovery, preview/apply
- [syncing.py](../../scripts/deluge_lib/syncing.py) — `build_post_sync_manifest()` where manifest data loss occurs
- [sync_from_sd.py](../../scripts/sync_from_sd.py) — Calls `build_post_sync_manifest` then `write_manifest`
- [test_fix_references.py](../../scripts/tests/test_fix_references.py) — Comprehensive test suite (~50 tests)
- [scanning.py](../../scripts/deluge_lib/scanning.py) — `normalise_key()`, `scan_tree()`
- [missing-ref-recovery-research.md](missing-ref-recovery-research.md) — Prior research on basename-based recovery
- [temp/fix-refs-improvements.md](../../temp/fix-refs-improvements.md) — Issue documentation with test run results

### Related Plans

- [docs/scripts-plan.md](../scripts-plan.md) — Original scripts plan (pre-implementation reference)

## Next Steps

1. Review this document and resolve any blocking open questions
2. Invoke the Plan agent to create a feature plan from this research
