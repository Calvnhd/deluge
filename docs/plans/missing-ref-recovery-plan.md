# Plan: Missing Reference Recovery

> **Document Type:** Plan
> **Date:** 16 May 2026
> **Research:** [missing-ref-recovery-research.md](../research/missing-ref-recovery-research.md)
> **Pipeline:** Research → **Plan** → Implement
> **Status:** Draft

## Executive Summary

This plan adds hash-based recovery for "missing" sample references in `fix_references.py`. The chosen approach (Approach A from the research) builds a basename index from the `after_hashes` dict already computed during migration map construction, matches missing refs by filename, and uses path similarity to disambiguate duplicates. This recovers 13 of 14 real missing references with zero additional filesystem I/O. The implementation also removes a redundant `scan_tree()` call by deriving the `existing` set from the newly-exposed `after_hashes`.

## Research Summary

- **Recommended approach:** Basename Index from `after_hashes` (Research §Approaches Considered, Approach A). Reuses data already computed in `compute_migration_map()` with no additional scanning or hashing.
- **Key constraint:** `after_hashes` is built locally inside `compute_migration_map()` and discarded. It must be exposed on `MigrationResult` to enable recovery (Research §Finding 1).
- **Recovery rate:** 13 of 14 real missing entries (6 of 7 unique paths) are recoverable via basename matching. The single unrecoverable case is a genuine filename mismatch (Research §Finding 2).
- **Disambiguation:** Two of the seven unique missing paths produce multi-candidate matches (duplicate files at different paths). All candidates share the same hash, so path similarity selects the better match (Research §Finding 3).
- **Redundant scan:** `classify_ref_changes()` calls `get_existing_samples()` which performs a second `scan_tree()`. This can be eliminated by deriving the `existing` set from `after_hashes` (Research §Finding 4).
- **Existing assets:** Test infrastructure with helpers for creating test trees, manifests, and XML files is ready for use (Research §Existing Assets Analysis).

## Decisions Log

| ID | Decision | Rationale | Alternatives Considered |
|----|----------|-----------|------------------------|
| D1 | Expose `after_hashes` on `MigrationResult` as a new field | Required for recovery and to eliminate redundant scan; dict already exists in memory, just needs to be retained (Research §Finding 1) | Rebuild the index separately in `classify_ref_changes` — wasteful duplication |
| D2 | Single confirmation step for both migration map changes and recovered refs | Simpler UX, consistent with existing flow; recovered refs are displayed in a distinct RECOVERED section for visibility (Research §Open Question 1, user confirmed) | Separate confirmation for recovered refs — adds friction for low-risk operation |
| D3 | Maximum 5 basename candidates before skipping recovery | Prevents noisy output for common filenames like `kick.wav`; tunable constant (Research §Open Question 2, user confirmed) | Threshold of 3 (too aggressive) or 10 (too permissive) |
| D4 | Remove redundant `get_existing_samples()` call | `after_hashes` provides the same data; eliminates a second `scan_tree()` of the SAMPLES directory (Research §Finding 4, user confirmed) | Separate cleanup — deferred scope creep, but this is a natural consequence of exposing `after_hashes` |
| D5 | Path similarity metric: count matching path components from the end (case-insensitive) | Simple, deterministic, and handles the two real disambiguation cases correctly (Research §Disambiguation Strategy). When all candidates share the same hash, any choice produces correct audio output — path similarity is a cleanliness tiebreaker | Levenshtein distance — over-engineered for this use case |
| D6 | New recovery dataclass for recovered refs, separate from `PlannedChange` | Recovered refs have different provenance (basename match vs migration map) and may carry candidate metadata; a distinct type preserves this distinction in the preview output | Reuse `PlannedChange` — obscures provenance, harder to display differently |
| D7 | Separate RECOVERED section in preview output, displayed between CHANGES and ERRORS | Clearest for user review; distinguishes recovery matches from migration map moves (Research §Interaction with `preview_and_apply`) | Add to CHANGES — obscures provenance; annotate MISSING — confusing |
| D8 | Recovered refs with different hashes across candidates are reported as ambiguous, not auto-recovered | Different hashes mean different audio content; auto-recovering could point the XML to the wrong file (Research §Risk Analysis) | Always pick the closest path regardless of hash — risks silent data corruption |

## Technical Specification

### Language and Tooling

| Item | Choice | Notes |
|------|--------|-------|
| Language | Python | Existing codebase; follows project standards |
| Test Framework | pytest | Existing test infrastructure in `tests/test_fix_references.py` |
| Key Dependencies | None new | All work uses stdlib (`pathlib`, `collections`, `dataclasses`) and existing `deluge_lib` |

### Architecture

This feature modifies the existing `fix_references.py` script and its test file. No new modules or files are created.

The data flow changes are:

1. **`compute_migration_map()`** — retains and returns `after_hashes` on `MigrationResult` instead of discarding it
2. **`classify_ref_changes()`** — builds a basename index from `after_hashes`, derives the `existing` set from it (replacing `get_existing_samples()`), and attempts recovery on refs that would otherwise be classified as "missing"
3. **`preview_and_apply()`** — adds a RECOVERED section between CHANGES and ERRORS, includes recovered ref counts in the summary, and applies recovered refs alongside migration map changes

The recovery classification logic within `classify_ref_changes` follows this priority chain for each ref not matched by the migration map or existing set:

1. Look up the ref's basename (case-insensitive) in the basename index
2. If zero candidates: truly missing (unchanged behaviour)
3. If more than 5 candidates: skip recovery, treat as missing (too ambiguous)
4. If exactly one candidate: auto-recover
5. If multiple candidates with the same hash: pick the candidate with the best path similarity score, auto-recover
6. If multiple candidates with different hashes: do not auto-recover, report as ambiguous recovery (new warning-like output)

### Interface Design

**Inputs:** No new CLI arguments. Recovery is automatic when `after_hashes` data is available.

**Outputs:**
- New `RECOVERED` section in preview output showing each recovered ref with its old path and new path
- Updated summary line including recovered count (e.g. "5 changes, 3 recovered, 0 errors, 1 warning, 1 missing")
- Truly unrecoverable refs remain in the existing MISSING section

**Error handling:** Recovery failures (ambiguous multi-hash candidates, too many candidates) are reported informatively but do not block the tool. They remain as MISSING entries with additional diagnostic context.

**User interaction:** Recovered refs are included in the same apply confirmation as migration map changes (Decision D2). The `--apply` flag auto-applies both.

### Integration Points

- **`MigrationResult`** — New `after_hashes` field added. All existing consumers of `MigrationResult` are unaffected since the field has a default value.
- **`get_existing_samples()`** — No longer called from `classify_ref_changes()`. The function itself is not removed (it may be used elsewhere), only the call site is replaced.
- **`BrokenRefResult`** — New `recovered` list field added alongside existing `changes`, `errors`, `warnings`, `missing`.
- **`preview_and_apply()`** — Extended to handle the `recovered` list. The "nothing to do" check, summary line, `has_issues` logic, and apply flow are all updated to account for recovered refs.
- **SD card safety:** This feature only reads from and writes to `DELUGE/` (XML files). No SD card interaction. Compliant with project standards.

## Cross-Cutting Concerns

| Concern (from Research) | Planned Mitigation |
|---|---|
| Interaction with migration map classification | Recovery runs strictly after migration map checks. A ref only reaches recovery if it failed moved/deleted/ambiguous checks. No conflict possible. |
| Interaction with `preview_and_apply` | Separate RECOVERED section (Decision D7). Recovered refs included in apply step (Decision D2). Summary counts updated. |
| Interaction with `update_manifest_keys` | No manifest updates needed for recovered refs — the manifest already knows the file at its current path. |
| Redundant filesystem scan | Eliminated by deriving `existing` from `after_hashes` (Decision D4). |

## Risk Mitigation

| Risk (from Research) | Plan Mitigation | Residual Risk |
|---|---|---|
| False positive: basename matches wrong file | Multi-hash candidates are not auto-recovered (Decision D8). Single-hash or same-hash candidates are safe — same audio content regardless of path chosen. | Extremely low — requires same basename AND same hash for a wrong match, which means identical audio content. |
| Common basenames matching dozens of files | Cap at 5 candidates (Decision D3). Refs exceeding the threshold remain as MISSING. | None — threshold is conservative and tunable. |
| `after_hashes` on `MigrationResult` increases memory | The dict already exists in memory during `compute_migration_map`. Retaining it just extends its lifetime. ~6500 entries is negligible. | None. |
| Breaking existing test expectations | Recovery only applies to refs previously classified as missing. Existing tests for moved/deleted/ambiguous/valid are unaffected. New tests cover all recovery paths. | Low — verified by running existing test suite after changes. |

## Implementation Roadmap

### Phase 1: Data Plumbing

> **Goal:** Surface `after_hashes` from `compute_migration_map` and derive the `existing` set from it.
> **Prerequisites:** None

#### Task 1.1: Add `after_hashes` field to `MigrationResult`

- **Description:** Add a new field to the `MigrationResult` dataclass to carry the `after_hashes` dict (hash to list of original-case filesystem paths).
- **Inputs:** Current `MigrationResult` definition
- **Outputs:** Updated dataclass with the new field (default empty dict for backward compatibility)
- **Acceptance Criteria:**
  - [ ] `MigrationResult` has an `after_hashes` field with a default empty dict
  - [ ] Existing tests pass without modification

#### Task 1.2: Return `after_hashes` from `compute_migration_map`

- **Description:** Populate the new `after_hashes` field on the `MigrationResult` returned by `compute_migration_map` instead of discarding the local `after_hashes` dict.
- **Inputs:** Current `compute_migration_map` implementation
- **Outputs:** `after_hashes` included in the returned `MigrationResult`
- **Acceptance Criteria:**
  - [ ] `compute_migration_map` returns `after_hashes` on its result
  - [ ] Existing migration map tests pass unchanged
  - [ ] A new test verifies `after_hashes` is populated correctly (hash maps to original-case paths)

#### Task 1.3: Replace `get_existing_samples` call with `after_hashes` derivation

- **Description:** In `classify_ref_changes`, derive the `existing` set from `migration.after_hashes` instead of calling `get_existing_samples(deluge_root)`. This eliminates a redundant `scan_tree()` call.
- **Inputs:** `migration.after_hashes` (from Task 1.2)
- **Outputs:** Same `existing` set, without a second filesystem scan
- **Acceptance Criteria:**
  - [ ] `get_existing_samples` is no longer called from `classify_ref_changes`
  - [ ] `classify_ref_changes` signature loses its `deluge_root` parameter (it now only needs `migration`)
  - [ ] All existing `classify_ref_changes` tests pass unchanged (behaviour is identical)
- **Implementation Notes:**
  > The `classify_ref_changes` function currently takes `deluge_root` for two purposes: (1) scanning for existing files, and (2) finding XML files. After this change it still needs `deluge_root` for XML file discovery, so the parameter stays. The `existing` set derivation replaces only the `get_existing_samples` call.

### Phase 2: Recovery Logic

> **Goal:** Implement basename matching and disambiguation in `classify_ref_changes`.
> **Prerequisites:** Phase 1 complete

#### Task 2.1: Add recovery dataclass and update `BrokenRefResult`

- **Description:** Create a new dataclass for recovered refs, carrying the source ref, old path, new path, and the list of all candidates found. Add a `recovered` list field to `BrokenRefResult`.
- **Inputs:** Existing dataclass patterns in `fix_references.py`
- **Outputs:** New dataclass and updated `BrokenRefResult`
- **Acceptance Criteria:**
  - [ ] New dataclass has fields for: the sample ref, old path, new path, and candidates list
  - [ ] `BrokenRefResult` has a `recovered` field (default empty list)
  - [ ] Existing tests pass without modification (the new field defaults to empty)

#### Task 2.2: Build basename index and recovery classification

- **Description:** In `classify_ref_changes`, build a basename index from `after_hashes` mapping lowercase basenames to (original_path, hash) tuples. For each ref that would be classified as "missing", attempt recovery using this index. Apply the priority chain: zero candidates → missing, more than 5 → missing, one candidate → recovered, multiple same-hash → pick best path similarity → recovered, multiple different-hash → missing (ambiguous).
- **Inputs:** `migration.after_hashes`, basename index, path similarity function
- **Outputs:** Refs classified into `recovered` or `missing` lists
- **Acceptance Criteria:**
  - [ ] Basename index is built from `after_hashes` with case-insensitive basename keys
  - [ ] Single-candidate recovery works: ref with one basename match is added to `recovered`
  - [ ] Multi-candidate same-hash recovery works: best path similarity match is picked
  - [ ] Multi-candidate different-hash refs remain as `missing`
  - [ ] Refs with more than 5 candidates remain as `missing`
  - [ ] Zero-candidate refs remain as `missing` (unchanged behaviour)
  - [ ] Max candidates threshold is a named constant (value: 5)

#### Task 2.3: Implement path similarity function

- **Description:** Implement a path similarity scoring function that counts matching path components from the end (case-insensitive). This is used as a tiebreaker when multiple same-hash candidates exist.
- **Inputs:** Two path strings (XML reference path and candidate filesystem path)
- **Outputs:** Integer score (number of matching trailing path components)
- **Acceptance Criteria:**
  - [ ] Compares path components from the end, case-insensitively
  - [ ] Basename match counts as the first matching component
  - [ ] Returns 0 for paths with no matching components
  - [ ] Handles paths of different depths correctly

### Phase 3: Preview and Apply Integration

> **Goal:** Display recovered refs in the preview output and include them in the apply step.
> **Prerequisites:** Phase 2 complete

#### Task 3.1: Add RECOVERED section to `preview_and_apply`

- **Description:** Add a RECOVERED section to the preview output, displayed between CHANGES and ERRORS. Show each recovered ref with its old and new path, grouped by XML file (matching the CHANGES display pattern). Update the summary line to include the recovered count.
- **Inputs:** `BrokenRefResult.recovered` list
- **Outputs:** Preview output with RECOVERED section
- **Acceptance Criteria:**
  - [ ] RECOVERED section appears between CHANGES and ERRORS when recovered refs exist
  - [ ] Output format matches the CHANGES section style (grouped by XML file, old → new path)
  - [ ] Summary line includes recovered count
  - [ ] No RECOVERED section when there are no recovered refs

#### Task 3.2: Include recovered refs in the apply step

- **Description:** When the user confirms, apply recovered refs alongside migration map changes. Build per-file mappings from recovered refs the same way changes are applied. Update the "nothing to do" check and `has_issues` logic to account for recovered refs.
- **Inputs:** `BrokenRefResult.recovered` list, apply confirmation
- **Outputs:** Recovered refs applied to XML files
- **Acceptance Criteria:**
  - [ ] Recovered refs are applied in the same confirmation step as migration map changes
  - [ ] The "nothing to do" check considers recovered refs (if only recovered refs exist, there is work to do)
  - [ ] `has_issues` is True only when there are errors or remaining missing refs (recovered refs reduce `has_issues`)
  - [ ] The apply summary counts include recovered refs
  - [ ] `--apply` flag auto-applies recovered refs alongside changes

### Phase 4: Tests

> **Goal:** Comprehensive test coverage for all recovery paths and edge cases.
> **Prerequisites:** Phase 3 complete (or can be developed in parallel with Phases 2-3)

#### Task 4.1: Test `after_hashes` exposure

- **Description:** Verify that `compute_migration_map` returns `after_hashes` on its result with correct contents.
- **Acceptance Criteria:**
  - [ ] Test that `after_hashes` maps hashes to original-case filesystem paths
  - [ ] Test that `after_hashes` is empty when SAMPLES dir is empty
  - [ ] Test that stat-cache hits produce correct `after_hashes` entries

#### Task 4.2: Test single-candidate recovery

- **Description:** A missing ref whose basename matches exactly one file on disk is recovered.
- **Acceptance Criteria:**
  - [ ] Ref appears in `result.recovered` with correct old and new paths
  - [ ] Ref does not appear in `result.missing`
  - [ ] Candidate list has exactly one entry

#### Task 4.3: Test multi-candidate same-hash recovery (duplicates)

- **Description:** A missing ref whose basename matches multiple files that all share the same hash is recovered using path similarity.
- **Acceptance Criteria:**
  - [ ] Best path-similarity candidate is selected as the new path
  - [ ] Ref appears in `result.recovered`
  - [ ] Candidates list contains all matches

#### Task 4.4: Test multi-candidate different-hash (ambiguous)

- **Description:** A missing ref whose basename matches multiple files with different hashes is not auto-recovered.
- **Acceptance Criteria:**
  - [ ] Ref remains in `result.missing`
  - [ ] Ref does not appear in `result.recovered`

#### Task 4.5: Test zero-candidate (truly missing)

- **Description:** A missing ref whose basename matches no file on disk remains as missing.
- **Acceptance Criteria:**
  - [ ] Ref remains in `result.missing` (unchanged behaviour)
  - [ ] Ref does not appear in `result.recovered`

#### Task 4.6: Test candidate threshold exceeded

- **Description:** A missing ref whose basename matches more than 5 files is not recovered.
- **Acceptance Criteria:**
  - [ ] Ref remains in `result.missing` when candidates exceed the threshold
  - [ ] Behaviour changes if the threshold constant is adjusted

#### Task 4.7: Test path similarity function

- **Description:** Unit tests for the path similarity scoring function.
- **Acceptance Criteria:**
  - [ ] Identical paths score highest
  - [ ] Paths sharing parent directories score higher than those that don't
  - [ ] Case-insensitive comparison works correctly
  - [ ] Different-depth paths handled correctly

#### Task 4.8: Test RECOVERED section in preview output

- **Description:** Verify the preview output includes the RECOVERED section with correct formatting.
- **Acceptance Criteria:**
  - [ ] RECOVERED section header appears in output
  - [ ] Recovered refs show old → new path
  - [ ] Summary line includes recovered count
  - [ ] No RECOVERED section when `recovered` list is empty

#### Task 4.9: Test apply includes recovered refs

- **Description:** Verify that applying changes also applies recovered refs to XML files.
- **Acceptance Criteria:**
  - [ ] XML file contents are updated with recovered paths after apply
  - [ ] Apply summary counts include recovered ref updates

#### Task 4.10: Test existing `get_existing_samples` call removed

- **Description:** Verify that `classify_ref_changes` no longer calls `get_existing_samples`.
- **Acceptance Criteria:**
  - [ ] No call to `get_existing_samples` in `classify_ref_changes`
  - [ ] Refs to existing files are still correctly identified as valid (not missing, not recovered)

## Progress Tracker

| Phase | Status | Tasks Complete | Notes |
|-------|--------|---------------|-------|
| Phase 1: Data Plumbing | Not Started | 0/3 | |
| Phase 2: Recovery Logic | Not Started | 0/3 | |
| Phase 3: Preview and Apply Integration | Not Started | 0/2 | |
| Phase 4: Tests | Not Started | 0/10 | |

## Open Questions

1. **Should the `classify_ref_changes` signature change?**
   - **Impact:** Currently takes `(migration, deluge_root)`. After removing `get_existing_samples`, it still needs `deluge_root` for `find_all_xml_files`. The parameter stays.
   - **Recommendation:** Keep the existing signature unchanged.
   - **Blocking:** No
   - **Resolution:** Signature kept as-is. Noted in Task 1.3 implementation notes.

2. **Should ambiguous recovery candidates (different hashes) be shown with extra detail?**
   - **Impact:** UX polish — could show candidate paths and hashes to help manual resolution.
   - **Recommendation:** For this iteration, keep them as standard MISSING entries. Adding diagnostic detail to MISSING entries for ambiguous recoveries is a future enhancement.
   - **Blocking:** No
   - **Resolution:** Defer to future iteration.

## References

### Research Document
- [missing-ref-recovery-research.md](../research/missing-ref-recovery-research.md) — Primary input

### Standards Applied
- [project.md](../../agent-system/standards/project.md) — SD card safety rules (compliant: feature only modifies files in `DELUGE/`)
- [plan-document.md](../../agent-system/skills/feature-planning/standards/plan-document.md) — Plan document template

### Project Files
- [fix_references.py](../../scripts/fix_references.py) — Main script being modified
- [deluge_sdk.py](../../scripts/deluge_lib/deluge_sdk.py) — SDK utilities (`get_existing_samples`, `hash_file`)
- [scanning.py](../../scripts/deluge_lib/scanning.py) — `normalise_key`, `scan_tree`
- [test_fix_references.py](../../scripts/tests/test_fix_references.py) — Test suite being extended

## Change Log

| Date | Change | Reason |
|------|--------|--------|
| 16 May 2026 | Initial plan created | — |
