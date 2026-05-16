# Plan: Fix References Improvements

> **Document Type:** Plan
> **Date:** 16 May 2026
> **Research:** [fix-refs-improvements-research.md](../research/fix-refs-improvements-research.md)
> **Pipeline:** Research → **Plan** → Implement
> **Status:** Draft

## Executive Summary

This plan addresses Issue 2 from the research — the overly aggressive ambiguity classification in `compute_migration_map()` that produces 151 false warnings for resolvable N:1 hash mappings. The chosen approach (Research Approach E) replaces the blanket `else: ambiguous` branch with an overlap-removal decomposition algorithm that resolves N:1, 1:M, and partial N:M cases deterministically. A minor integration improvement extends manifest key updates to include recovered refs. Approach A (manifest move log) is deferred to a separate pipeline cycle.

## Research Summary

The research identified two issues in `fix_references.py`:

1. **Issue 1 — Manifest data loss:** `build_post_sync_manifest()` in `syncing.py` drops old entries for files no longer on the SD card, losing the old path→hash data needed for move detection. This caused 61 missing refs in testing. The root fix (Approach A — move log during sync) requires manifest schema changes and is recommended as a separate follow-up.

2. **Issue 2 — False ambiguity:** `compute_migration_map()` classifies all non-1:1 hash mappings as ambiguous, including fully resolvable N:1 cases where duplicates were deleted and one copy survived. This caused 151 false warnings in testing.

**Recommended approach from research (Findings 4–5, Approach E):** Replace the blanket `else: ambiguous` with decomposition logic that finds overlapping paths (unchanged), then classifies residuals as moved, deleted, or added — falling back to truly ambiguous only when N>1 before-paths and M>1 after-paths remain with no overlap.

**Key existing assets:**
- `compute_migration_map()` in [fix_references.py](../../scripts/fix_references.py) — the function to modify (lines 133–148)
- `path_similarity()` in [fix_references.py](../../scripts/fix_references.py) — already exists and tested, needed for 1:M tiebreaking
- `classify_ref_changes()` — no changes needed; it reads from `migration.moved` and `migration.ambiguous`, which the decomposition populates correctly
- `update_manifest_keys()` — currently only processes `migration.moved`; will be extended for recovered refs
- Comprehensive test suite (~50 tests) in [test_fix_references.py](../../scripts/tests/test_fix_references.py) with helpers for creating filesystem trees, manifests, and XML files

## Decisions Log

| ID | Decision | Rationale | Alternatives Considered |
|----|----------|-----------|------------------------|
| D1 | Implement full overlap-removal decomposition (N:1, 1:M, partial N:M) in one pass, not just N:1 | The overlap-removal algorithm is the same regardless of N:M shape — restricting to N:1 only would add artificial branching without reducing complexity. Research Finding 5 confirms the decomposition is straightforward. | N:1 only (defers 1:M and partial N:M; simpler but leaves resolvable cases unhandled) |
| D2 | Resolved entries go directly into existing `moved` and `deleted` dicts — no new `MigrationResult` field | Adding a `resolved_ambiguous` field would be purely cosmetic; `classify_ref_changes()` already consumes `moved` and `deleted`. A log message provides sufficient traceability. Research Open Question 4 recommends this. | New `resolved_ambiguous` field on `MigrationResult` (adds API surface for no functional benefit) |
| D3 | Use `path_similarity()` as tiebreaker for 1:M residual cases | `path_similarity()` already exists and is tested. For 1:M residuals (1 before-path, M>1 after-paths, no overlap), all after-paths have the same hash so any is correct — path similarity picks the most intuitive match. | Arbitrary first-match (correct but less intuitive); no 1:M handling (leaves as ambiguous) |
| D4 | Extend `update_manifest_keys` to also process recovered ref mappings | After recovery rewrites XML refs, the manifest should reflect the new paths. Currently only `migration.moved` is passed. Research Open Question 3 recommends this. | Leave manifest inconsistent with XML state (causes issues on subsequent runs) |
| D5 | Defer Approach A (manifest move log) to a separate pipeline cycle | Approach A touches `syncing.py` (shared infrastructure), the manifest schema (v2→v3), and the sync workflow — higher complexity with different risk profile. Approach E alone resolves the immediate 151 warnings. Research recommends this ordering. | Include Approach A in this feature (larger scope, higher risk, mixed concerns) |
| D6 | For residual N before-paths with 0 residual after-paths (all after-paths consumed by overlaps), direct moved entries to the first overlap survivor | Content is identical (same hash) at all surviving paths. Picking any survivor is correct. The first overlap path is deterministic and reproducible. | Use path_similarity to pick among survivors (unnecessary since content is identical) |

## Technical Specification

### Language and Tooling

| Item | Choice | Notes |
|------|--------|-------|
| Language | Python | Existing codebase; reference `standards/languages/python/` |
| Test Framework | pytest | Existing test suite uses pytest |
| Key Dependencies | None new | All changes use existing stdlib and project utilities |

### Architecture

All changes are confined to [fix_references.py](../../scripts/fix_references.py). No new modules or files are created (beyond tests).

The decomposition logic replaces the current `else: ambiguous` branch in `compute_migration_map()` with a multi-step algorithm:

1. **Overlap detection** — For each hash with N before-paths and M after-paths (where N≠1 or M≠1), compare each before-path (already normalised) against each after-path (normalised). Matching pairs are "unchanged" and removed from both sets. Track which original-case after-paths were consumed as "survivors".

2. **Residual classification** — After removing overlaps, classify the remaining before-paths and after-paths:
   - Zero residual before, zero residual after → all unchanged, nothing to record
   - Zero residual before, K residual after → new duplicates added at those paths
   - K residual before, zero residual after → all K before-paths moved to the first survivor (content survives at overlap paths)
   - One residual before, one residual after → simple move
   - N residual before, one residual after → all N before-paths moved to the single residual after-path
   - One residual before, M residual after → moved to the best after-path by path similarity; remaining after-paths are added duplicates
   - N residual before, M residual after (N>1, M>1) → truly ambiguous, kept in the ambiguous dict

3. **Existing downstream unchanged** — `classify_ref_changes()` already reads `moved`, `deleted`, `added`, and `ambiguous` from `MigrationResult`. Promoting entries from ambiguous into moved/deleted/added means fewer refs hit the ambiguous check and more get automatic resolution. No changes to `classify_ref_changes()` are needed.

4. **Manifest key update extension** — In `main()`, after `preview_and_apply`, build a mapping from recovered refs (normalised old path → new path) and pass it alongside `migration.moved` to `update_manifest_keys`. This keeps the manifest consistent with the rewritten XML state.

### Interface Design

No CLI interface changes. The `--manifest` and `--apply` flags continue to work as before. The only user-visible difference is:
- **Before:** 151 ambiguous warnings for resolvable N:1 mappings
- **After:** Those 151 refs appear as automatic changes (in the CHANGES section of preview output)

Console output continues to show the CHANGES, RECOVERED, ERRORS, WARNINGS, and MISSING sections. The WARNINGS section will be shorter (or empty) for cases that are now resolved. No new output sections are needed. A log line noting how many N:M cases were decomposed provides traceability.

### Integration Points

- **`compute_migration_map()` → `classify_ref_changes()`** — No interface change. The `MigrationResult` dataclass keeps the same fields. Decomposed entries are placed into existing `moved`, `deleted`, and `added` dicts.
- **`migration.moved` → `update_manifest_keys()`** — The existing call in `main()` already handles all `moved` entries, including newly resolved ones. The additional change is passing recovered ref mappings as well.
- **`update_manifest_keys()`** — Currently accepts a `moved` dict. The extension merges recovered ref mappings into the same dict before calling (or calls twice). No signature change needed if the caller builds a combined mapping.
- **SD card safety** — This feature only reads from `DELUGE/SAMPLES/` and modifies XML files in `DELUGE/KITS/`, `DELUGE/SYNTHS/`, `DELUGE/SONGS/`. No SD card writes. Compliant with project standards.

## Cross-Cutting Concerns

| Concern (from Research) | Planned Mitigation |
|---|---|
| **Interaction between Approach E and recovery** | Resolved entries promoted from ambiguous to moved means fewer refs hit the ambiguous check in `classify_ref_changes()`, allowing more to reach recovery. The two mechanisms are complementary — no conflict. |
| **Manifest schema stability** | No manifest schema changes in this feature. The `MigrationResult` dataclass keeps the same fields. Approach A (schema change) is deferred. |
| **Impact on `sync_to_sd.py`** | `sync_to_sd.py` does not call `compute_migration_map()`. No impact. |
| **Impact on `sync_samples_to_cloud.py`** | Does not use the sync manifest. No impact. |
| **Manifest key update after apply** | Resolved N:1 entries go into `migration.moved`, which `update_manifest_keys()` already processes. Additionally, recovered ref mappings are now included. |

## Risk Mitigation

| Risk (from Research) | Plan Mitigation | Residual Risk |
|---------------------|-----------------|---------------|
| N:1 resolution incorrectly resolves a genuinely ambiguous case | N:1 with one surviving path is deterministic — all before-paths had identical content (same hash), so any surviving path is correct. Tests cover all sub-cases. | None — the algorithm is provably correct for same-hash files. |
| N:M decomposition logic has edge cases | Full test coverage for every decomposition path: overlap-only, overlap+residual, N:1, 1:M, 1:1, true N:M. Start with the complete algorithm rather than iterating. | Low — a missed edge case would fall through to ambiguous (safe default). |
| Raised `MAX_RECOVERY_CANDIDATES` produces false positives | `MAX_RECOVERY_CANDIDATES` is not changed. Recovery behaviour is unchanged. | None. |
| Approach A only helps future syncs, not past data | Approach E resolves the immediate 151 warnings from current data. Approach A is deferred to prevent recurrence. | Issue 1's 61 missing refs remain unresolved until Approach A is implemented. |
| Existing ambiguous tests break | Tests are explicitly updated in Phase 1 to reflect the new (correct) behaviour. | None. |

## Implementation Roadmap

## Phase 1: Core — N:M Decomposition in `compute_migration_map()`

> **Goal:** Replace the blanket `else: ambiguous` branch with overlap-removal decomposition that resolves N:1, 1:M, and partial N:M cases.
> **Prerequisites:** None

### Task 1.1: Implement overlap-removal decomposition logic

- **Description:** Replace the `else` branch (lines 144–148 of `compute_migration_map()`) with the decomposition algorithm described in the Architecture section. The new logic handles: overlap detection, residual classification (all seven sub-cases), and falls back to ambiguous only for true N:M (N>1, M>1, no overlaps).
- **Inputs:** Current `compute_migration_map()` function in [fix_references.py](../../scripts/fix_references.py)
- **Outputs:** Updated function with decomposition logic; existing 1:1 and empty-set branches unchanged
- **Acceptance Criteria:**
  - [ ] The `else` branch is replaced with overlap-removal + residual classification
  - [ ] N:1 cases (N before-paths, 1 after-path) produce `moved` entries for all non-overlapping before-paths
  - [ ] 1:M cases (1 before-path, M after-paths) produce a `moved` entry using `path_similarity()` as tiebreaker, with remaining after-paths as `added`
  - [ ] Partial N:M cases (overlaps reduce to a simpler sub-case) are decomposed correctly
  - [ ] True N:M cases (N>1, M>1, no overlaps after removal) remain in `ambiguous`
  - [ ] When residual before-paths exist but all after-paths were consumed by overlaps, moved entries point to the first survivor
  - [ ] A log/print line notes how many hash groups were decomposed (for traceability)
- **Implementation Notes:**
  > _Space for the Implement agent_

### Task 1.2: Update existing tests for changed ambiguity behaviour

- **Description:** Three existing tests in `TestComputeMigrationMap` assert that certain cases produce `ambiguous` entries. After the decomposition change, these cases are now resolvable. Update the assertions to match the new (correct) behaviour.
- **Inputs:** [test_fix_references.py](../../scripts/tests/test_fix_references.py) — `test_ambiguous_multiple_before_paths`, `test_ambiguous_multiple_after_paths`, `test_mixed_categories`
- **Outputs:** Updated test assertions
- **Acceptance Criteria:**
  - [ ] `test_ambiguous_multiple_before_paths` (2 before → 1 after, no overlap): asserts `moved` entries for both before-paths pointing to the after-path, no ambiguous
  - [ ] `test_ambiguous_multiple_after_paths` (1 before → 2 after, no overlap): asserts `moved` entry for the before-path to the best after-path (by path similarity), and the other after-path as `added`
  - [ ] `test_mixed_categories`: updated to reflect the 1:M entry (1 before → 2 after) being decomposed rather than ambiguous
  - [ ] All updated tests pass
- **Implementation Notes:**
  > _Space for the Implement agent_

### Task 1.3: Add new tests for decomposition sub-cases

- **Description:** Add new test cases covering every decomposition path to ensure comprehensive coverage. Use existing test helpers (`_make_deluge_tree`, `_make_manifest`).
- **Inputs:** [test_fix_references.py](../../scripts/tests/test_fix_references.py), existing test helpers
- **Outputs:** New test class or test methods covering decomposition cases
- **Acceptance Criteria:**
  - [ ] Test: N:1, no overlap — N before-paths, 1 after-path, no normalised match → all before-paths in `moved` pointing to the after-path
  - [ ] Test: N:1, with overlap — N before-paths, 1 after-path, one before matches after normalised → matching before unchanged, others in `moved`
  - [ ] Test: 1:M, no overlap — 1 before-path, M after-paths, no normalised match → before-path in `moved` to best path-similarity match, others in `added`
  - [ ] Test: 1:M, with overlap — 1 before-path matches one after-path → unchanged; other after-paths in `added`
  - [ ] Test: N:M partial overlap — overlaps removed, residual reduces to a simpler case (e.g. 1:1 or N:1)
  - [ ] Test: N:M, all overlapping — all pairs match → nothing in moved/deleted/added/ambiguous
  - [ ] Test: N:M, no overlap, N>1 M>1 — truly ambiguous, remains in `ambiguous`
  - [ ] Test: N before, 0 residual after (all after consumed by overlaps) — remaining before-paths in `moved` to first survivor
  - [ ] All new tests pass
- **Implementation Notes:**
  > _Space for the Implement agent_

## Phase 2: Integration — Manifest Key Update for Recovered Refs

> **Goal:** Extend manifest key updates to include recovered ref mappings, keeping the manifest consistent with rewritten XML state.
> **Prerequisites:** Phase 1 complete (so the full test suite passes)

### Task 2.1: Include recovered ref mappings in manifest key update

- **Description:** In `main()`, after `preview_and_apply`, build a mapping from recovered refs (normalised old path → original-case new path) and merge it with `migration.moved` before passing to `update_manifest_keys()`. This ensures the manifest reflects all path changes applied to XML files.
- **Inputs:** `main()` in [fix_references.py](../../scripts/fix_references.py), `BrokenRefResult.recovered`
- **Outputs:** Updated `main()` that passes combined moved+recovered mappings to `update_manifest_keys()`
- **Acceptance Criteria:**
  - [ ] After apply, recovered ref old→new mappings are included in the manifest key update
  - [ ] Duplicate mappings (same old_path in both moved and recovered) are handled gracefully — moved takes precedence
  - [ ] When no recovered refs exist, behaviour is identical to current
- **Implementation Notes:**
  > _Space for the Implement agent_

### Task 2.2: Add tests for manifest update with recovered refs

- **Description:** Add test cases verifying that recovered ref mappings are reflected in manifest key updates.
- **Inputs:** [test_fix_references.py](../../scripts/tests/test_fix_references.py), existing `TestManifestKeyUpdate` class
- **Outputs:** New test methods
- **Acceptance Criteria:**
  - [ ] Test: recovered ref mapping renames manifest key
  - [ ] Test: combined moved + recovered mappings both applied
  - [ ] Test: no recovered refs produces no additional manifest changes
  - [ ] All new tests pass
- **Implementation Notes:**
  > _Space for the Implement agent_

## Phase 3: Verification

> **Goal:** Ensure all changes work correctly end-to-end with no regressions.
> **Prerequisites:** Phases 1–2 complete

### Task 3.1: Full test suite pass

- **Description:** Run the complete `test_fix_references.py` suite and verify all tests pass, including the updated and new tests from Phases 1–2.
- **Inputs:** Complete codebase after Phases 1–2
- **Outputs:** Clean test run
- **Acceptance Criteria:**
  - [ ] All existing tests pass (updated where needed)
  - [ ] All new tests pass
  - [ ] No regressions in other test files
- **Implementation Notes:**
  > _Space for the Implement agent_

### Task 3.2: Manual smoke test (optional)

- **Description:** If real-world test data is available (the scenario from Issue 2 with 151 ambiguous warnings), run `fix_references.py` and verify the warnings are resolved to automatic changes.
- **Inputs:** Real DELUGE directory and manifest from Issue 2's test run (if available)
- **Outputs:** Console output showing resolved changes instead of warnings
- **Acceptance Criteria:**
  - [ ] Previously ambiguous refs now appear in CHANGES section
  - [ ] WARNINGS section is empty or reduced to genuinely ambiguous cases
  - [ ] No new ERRORS or MISSING entries
- **Implementation Notes:**
  > _Space for the Implement agent_

## Progress Tracker

| Phase | Status | Tasks Complete | Notes |
|-------|--------|---------------|-------|
| Phase 1: Core — N:M Decomposition | Not Started | 0/3 | |
| Phase 2: Integration — Manifest Key Update | Not Started | 0/2 | |
| Phase 3: Verification | Not Started | 0/2 | |

## Open Questions

1. **Should the 1:M `path_similarity` tiebreaker use the original-case after-path or the normalised form for comparison?**
   - **Impact:** Minor — affects which duplicate is selected as the move target when multiple after-paths exist for a single before-path.
   - **Recommendation:** Use original-case after-paths (as passed to `path_similarity()` currently). The function already does case-insensitive comparison internally.
   - **Blocking:** No
   - **Resolution:** _To be filled during implementation_

2. **Should Approach A (manifest move log) be planned as the immediate next feature after this one?**
   - **Impact:** Determines whether Issue 1's 61 missing refs are addressed soon or deferred indefinitely.
   - **Recommendation:** Yes — plan Approach A as a follow-up pipeline cycle after this feature is verified. It prevents recurrence of the manifest data loss.
   - **Blocking:** No — out of scope for this plan
   - **Resolution:** _To be filled after this feature is complete_

## References

### Research Document
- [fix-refs-improvements-research.md](../research/fix-refs-improvements-research.md) — Primary input

### Standards Applied
- [project.md](../../agent-system/standards/project.md) — SD card safety rules (no SD card writes in this feature)
- [standards/languages/python/](../../agent-system/standards/languages/python/) — Python language standards

### Project Files
- [fix_references.py](../../scripts/fix_references.py) — Primary file to modify (`compute_migration_map()`, `main()`)
- [test_fix_references.py](../../scripts/tests/test_fix_references.py) — Test suite to extend and update
- [syncing.py](../../scripts/deluge_lib/syncing.py) — Referenced for context (not modified in this feature)
- [temp/fix-refs-improvements.md](../../temp/fix-refs-improvements.md) — Original issue documentation

## Change Log

| Date | Change | Reason |
|------|--------|--------|
| 16 May 2026 | Initial plan created | — |
