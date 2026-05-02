# Plan: Dual-Stat Manifest

> **Document Type:** Plan
> **Date:** 02 May 2026
> **Research:** [manifest-sync-comparison-research.md](../research/manifest-sync-comparison-research.md)
> **Pipeline:** Research → **Plan** → Implement
> **Status:** Draft

## Executive Summary

Extend the sync manifest to store both SD-side and local-side stats per file (`sd_size`, `sd_mtime`, `local_size`, `local_mtime`). Rework the commented-out manifest comparison block in `compute_sync()` to perform a dual check: SD stats vs manifest detect SD-side changes; local stats vs manifest detect local drift. This closes the local-drift blind spot and resolves the null-timestamp false-positive problem by keeping NTFS-to-NTFS comparisons on the local side.

## Research Summary

- **Root cause:** ~287 factory preset files have null FAT32 timestamps. `shutil.copy2` cannot preserve these on NTFS, creating a permanent mtime mismatch that triggers re-copy every sync. ([manifest-sync-comparison-research.md](../research/manifest-sync-comparison-research.md), Finding 1)
- **Blind spot:** The original manifest logic only checked "has the SD changed?" — it never checked whether the local file still matches what was synced. Local modifications (via `extract_instruments.py`, `git checkout`, manual edits) are silently ignored. ([research](../research/manifest-sync-comparison-research.md), Finding 3)
- **Recommended approach:** Approach A — Dual-Stat Manifest. Simplest correct solution across all four test scenarios. No content hashing needed. ([research](../research/manifest-sync-comparison-research.md), Recommendation)
- **Existing assets:** `_read_manifest()` / `_write_manifest()` with atomic writes (ready), `_build_post_sync_manifest()` (needs extension), `compute_sync()` with commented-out manifest block (needs rework), `_mtime_matches()` / `normalise_mtime()` (ready, reused for SD-side only).

## Decisions Log

| ID | Decision | Rationale | Alternatives Considered |
|----|----------|-----------|------------------------|
| D1 | Store `sd_size`, `sd_mtime`, `local_size`, `local_mtime` per manifest entry | Need both sets to detect SD changes and local drift independently. Research Approach A. | Single-stat manifest (current — has blind spot), size-only (misses same-size edits) |
| D2 | `_build_post_sync_manifest()` stats the destination file itself after copy | It already receives `dest` and knows which files were copied. Avoids changing `execute_plan()` return type. Simplest change. | Have `execute_plan()` return dest stats (cleaner separation but more invasive) |
| D3 | Store raw NTFS mtime values for `local_mtime` — no normalisation | Both sides of the local comparison are NTFS. Normalising to FAT32's 2-second grid loses sub-second precision for no benefit. | Normalise (loses precision, no upside) |
| D4 | Use exact equality for local-drift check (`dst_entry.mtime != m["local_mtime"]`) | NTFS-to-NTFS comparison. No cross-filesystem tolerance needed. | FAT32 tolerance (wrong — not FAT32) |
| D5 | Use `_mtime_matches()` (±2s tolerance) for SD-vs-manifest check | SD side is FAT32. Tolerance handles rounding. Consistent with existing comparison. | Exact equality (would break on FAT32 rounding) |
| D6 | Old-format manifest entries (missing `local_size`/`local_mtime`) trigger re-copy | One-time migration cost. ~287 null-timestamp files re-copied, others match on direct comparison fallback. No explicit migration code needed. | Write a migration function (over-engineering for a one-time cost) |
| D7 | Leave the `manifest is None` code path in `compute_sync()` untouched | Used by `sync_to_sd.py` and `sync_samples_to_cloud.py`. No changes to other scripts. | Refactor all callers (unnecessary scope creep) |

## Technical Specification

### 5a. Language and Tooling

| Item | Choice | Notes |
|------|--------|-------|
| Language | Python 3.12+ | Existing codebase |
| Test Framework | pytest | Existing test suite |
| Key Dependencies | None new | Standard library only (`json`, `pathlib`, `os`) |

### 5b. Architecture

No new modules or files. All changes are to existing functions in two files:

- [scripts/deluge_lib/syncing.py](../../scripts/deluge_lib/syncing.py) — `compute_sync()` comparison block and the `_FileRecord` TypedDict
- [scripts/sync_from_sd.py](../../scripts/sync_from_sd.py) — `FileRecord` TypedDict, `_read_manifest()`, `_build_post_sync_manifest()`

Data flow after changes:

1. `_read_manifest()` reads JSON → returns entries with `sd_size`, `sd_mtime`, `local_size`, `local_mtime` (or old-format entries missing local fields)
2. `compute_sync()` receives manifest dict, performs dual check per file
3. `execute_plan()` copies files (unchanged)
4. `_build_post_sync_manifest()` builds new entries: SD stats from `src_scan`, local stats by statting dest files after copy
5. `_write_manifest()` writes JSON (unchanged logic, new field names in data)

### 5c. Interface Design

- **Inputs:** No CLI changes. Manifest format change is internal.
- **Outputs:** Manifest JSON file gains four fields per entry instead of two. Human-readable (same JSON structure).
- **Error Handling:** No new error paths. `stat()` failures in manifest builder are already safe — manifest only written after builder completes successfully.
- **Migration:** Automatic. Old-format entries detected by missing `local_size` key → treated as if no manifest entry → file re-copied → fresh dual-stat entry written.

### 5d. Integration Points

- `sync_from_sd.py` — sole consumer of the manifest. All changes here.
- `sync_to_sd.py`, `sync_samples_to_cloud.py` — pass `manifest=None` to `compute_sync()`. Unaffected (D7).
- `compute_sync()` in `syncing.py` — the `manifest is None` path remains untouched. Only the `manifest is not None and key in manifest` branch changes.
- SD card safety: No writes to SD card. Reads only. Compliant with project standard.

## Cross-Cutting Concerns

| Concern | Mitigation |
|---------|-----------|
| **Manifest migration** | Old-format entries (missing `local_size`) trigger re-copy automatically. No migration code. One-time cost ~287 files. (D6) |
| **Filtered sync (`--xml` / `--wav`)** | `_build_post_sync_manifest()` already carries forward entries for unscanned file types. Carried-forward entries retain their format — no change needed. |
| **Cross-platform** | NTFS mtime precision differs from FAT32 but that's already handled: SD-side uses `_mtime_matches()` tolerance, local-side uses exact equality. Both work identically on WSL and Windows. |
| **`_FileRecord` TypedDict in syncing.py** | Update field names to match new format. This TypedDict is only used for type checking — `compute_sync()` accesses dict keys directly. |

## Risk Mitigation

| Risk (from Research) | Plan Mitigation | Residual Risk |
|---------------------|-----------------|---------------|
| NTFS mtime jitter (antivirus, indexers touch files) | Re-copy is harmless — SD is source of truth. Content is identical. | Rare extra copies, not incorrect behaviour |
| Old manifest triggers one-time re-sync | Acceptable: ~287 null-timestamp files re-copied in seconds | None — by design |
| `stat()` failure in manifest builder | Manifest only written after builder completes. Failure → manifest not updated → next sync re-copies. Already safe. | None |

## Implementation Roadmap

### Phase 1: Manifest Format and I/O

> **Goal:** Update the manifest data model and reader to handle dual-stat entries
> **Prerequisites:** None

#### Task 1.1: Update TypedDicts

- **Description:** Change `FileRecord` in `sync_from_sd.py` and `_FileRecord` in `syncing.py` to use the new field names: `sd_size`, `sd_mtime`, `local_size`, `local_mtime`.
- **Inputs:** Current TypedDict definitions
- **Outputs:** Updated TypedDicts
- **Acceptance Criteria:**
  - [ ] `FileRecord` in `sync_from_sd.py` has fields `sd_size: int`, `sd_mtime: float`, `local_size: int`, `local_mtime: float`
  - [ ] `_FileRecord` in `syncing.py` has the same four fields
  - [ ] No type errors reported by the editor
- **Implementation Notes:**
  > _(space for implementer)_

#### Task 1.2: Update `_read_manifest()`

- **Description:** Update the reader to parse the new four-field format. Old-format entries (with `size`/`mtime` instead of `sd_size`/`sd_mtime`) should be skipped (not loaded) — they'll be treated as missing entries, triggering re-copy.
- **Inputs:** Current `_read_manifest()` in `sync_from_sd.py`
- **Outputs:** Reader that loads dual-stat entries and gracefully drops old-format ones
- **Acceptance Criteria:**
  - [ ] New-format entries (`sd_size`, `sd_mtime`, `local_size`, `local_mtime`) are loaded correctly
  - [ ] Old-format entries (only `size` and `mtime`) are silently dropped (not loaded into the dict)
  - [ ] Missing file / corrupt JSON still returns `("", {})`
- **Implementation Notes:**
  > _(space for implementer)_

### Phase 2: Manifest Builder

> **Goal:** Make `_build_post_sync_manifest()` produce dual-stat entries
> **Prerequisites:** Phase 1 complete

#### Task 2.1: Update `_build_post_sync_manifest()` to stat dest files and record both SD and local stats

- **Description:** For copied files, stat the destination file after copy to get `local_size` and `local_mtime`. For unchanged files with existing manifest entries, preserve the old entry. For unchanged files with no prior entry (first run or old-format dropped), stat the dest file and use SD stats from `src_scan`.
- **Inputs:** Current `_build_post_sync_manifest()` in `sync_from_sd.py`
- **Outputs:** Builder that produces `{sd_size, sd_mtime, local_size, local_mtime}` entries
- **Acceptance Criteria:**
  - [ ] Copied files: entry has `sd_size`/`sd_mtime` from `src_scan` and `local_size`/`local_mtime` from `stat()` of dest file
  - [ ] Unchanged files with prior dual-stat entry: entry preserved as-is
  - [ ] Unchanged files with no prior entry: `sd_*` from `src_scan`, `local_*` from `stat()` of dest file
  - [ ] Trashed files: not in output (existing behaviour, unchanged)
  - [ ] Filtered sync carry-forward: entries for unscanned file types preserved (existing behaviour)
- **Implementation Notes:**
  > _(space for implementer)_

### Phase 3: Comparison Logic

> **Goal:** Uncomment and rework the manifest comparison block in `compute_sync()`
> **Prerequisites:** Phases 1–2 complete

#### Task 3.1: Rework the manifest comparison block in `compute_sync()`

- **Description:** Replace the commented-out manifest block with the dual-stat comparison logic. When a manifest entry exists for a file: check SD stats vs `sd_*` fields (using `_mtime_matches()` tolerance for mtime) AND check local stats vs `local_*` fields (exact equality for mtime). If either check fails → copy. If both pass → skip. When no manifest entry exists → fall through to existing direct SD-vs-local comparison.
- **Inputs:** Current commented-out block in `compute_sync()`, lines ~148–163 of `syncing.py`
- **Outputs:** Working dual-stat comparison
- **Acceptance Criteria:**
  - [ ] Manifest block is uncommented and reworked with dual-stat logic
  - [ ] SD-side check: `src_entry.size != m["sd_size"] or not _mtime_matches(src_entry.mtime, m["sd_mtime"])`
  - [ ] Local-side check: `dst_entry.size != m["local_size"] or dst_entry.mtime != m["local_mtime"]`
  - [ ] Either check failing → file added to `files_to_copy`
  - [ ] Both checks passing → `files_unchanged` incremented
  - [ ] `manifest is None` code path completely untouched
  - [ ] No-manifest-entry fallback (key not in manifest) falls through to existing direct comparison
- **Implementation Notes:**
  > _(space for implementer)_

### Phase 4: Tests

> **Goal:** Update existing tests and add new ones for dual-stat behaviour
> **Prerequisites:** Phases 1–3 complete

#### Task 4.1: Update existing manifest tests in `test_syncing.py`

- **Description:** Update `TestComputeSyncManifest` tests to use the new four-field manifest format. The existing two tests (`test_manifest_entry_used_when_available` and `test_fallback_to_dest_stat_when_no_manifest_entry`) need their manifest dicts updated.
- **Inputs:** Current tests in `test_syncing.py`
- **Outputs:** Updated tests passing with new manifest format
- **Acceptance Criteria:**
  - [ ] `test_manifest_entry_used_when_available` passes with dual-stat manifest entry
  - [ ] `test_fallback_to_dest_stat_when_no_manifest_entry` passes (manifest has entries for other files in new format)
  - [ ] All pre-existing non-manifest tests still pass unchanged
- **Implementation Notes:**
  > _(space for implementer)_

#### Task 4.2: Add new dual-stat comparison tests in `test_syncing.py`

- **Description:** Add test cases for the scenarios from the research document.
- **Inputs:** Scenario walkthroughs from research
- **Outputs:** New test cases in `TestComputeSyncManifest`
- **Acceptance Criteria:**
  - [ ] **Local size drift detected:** SD unchanged, local file has different size → copy
  - [ ] **Local mtime drift detected:** SD unchanged, local file has different mtime (same size) → copy
  - [ ] **SD change detected:** SD stats differ from manifest `sd_*` → copy (even if local matches `local_*`)
  - [ ] **Both sides changed:** SD changed AND local drifted → copy
  - [ ] **Null-timestamp idempotent:** SD mtime is `-11644473600.0`, manifest `sd_mtime` matches, local mtime matches `local_mtime` → skip (no false positive)
  - [ ] **Old-format entry treated as missing:** Manifest entry with only `size`/`mtime` not loaded → falls through to direct comparison
- **Implementation Notes:**
  > _(space for implementer)_

#### Task 4.3: Update manifest builder tests in `test_sync_from_sd.py`

- **Description:** Update `TestBuildPostSyncManifest` to verify dual-stat output and update `TestReadManifest.test_valid_manifest_round_trip` for the new format.
- **Inputs:** Current tests in `test_sync_from_sd.py`
- **Outputs:** Updated tests passing with new manifest format
- **Acceptance Criteria:**
  - [ ] `test_creates_correct_entries_after_sync` verifies entry has all four fields (`sd_size`, `sd_mtime`, `local_size`, `local_mtime`)
  - [ ] `test_trashed_files_excluded` uses new format for `old_files`
  - [ ] `test_valid_manifest_round_trip` uses new four-field format and verifies round-trip
  - [ ] A new test verifies that unchanged files with no prior entry get local stats from `stat()` of dest file
- **Implementation Notes:**
  > _(space for implementer)_

### Phase 5: Verification

> **Goal:** Run full test suite and verify end-to-end
> **Prerequisites:** Phases 1–4 complete

#### Task 5.1: Run full test suite

- **Description:** Run `pytest` from the `scripts/` directory. All tests must pass.
- **Acceptance Criteria:**
  - [ ] `pytest` exits with 0 failures
  - [ ] No warnings related to manifest format or type mismatches
- **Implementation Notes:**
  > _(space for implementer)_

#### Task 5.2: Manual smoke test (optional)

- **Description:** If the SD card is mounted, run `python sync_from_sd.py --dry-run` and verify the output is sensible. First run after the change will show ~287 files to copy (old manifest migration). Second run should show "Already up to date".
- **Acceptance Criteria:**
  - [ ] First dry-run: ~287 null-timestamp files flagged (expected migration)
  - [ ] After a real sync + second dry-run: "Already up to date"
- **Implementation Notes:**
  > _(space for implementer)_

## Progress Tracker

| Phase | Status | Tasks Complete | Notes |
|-------|--------|---------------|-------|
| Phase 1: Manifest Format and I/O | Not Started | 0/2 | |
| Phase 2: Manifest Builder | Not Started | 0/1 | |
| Phase 3: Comparison Logic | Not Started | 0/1 | |
| Phase 4: Tests | Not Started | 0/3 | |
| Phase 5: Verification | Not Started | 0/2 | |

## Open Questions

No blocking open questions remain. All critical decisions were made prior to planning (see Decisions Log).

1. **Should unchanged files with no prior manifest entry stat the dest file for `local_*` fields?**
   - **Impact:** Affects first-run manifest accuracy. Without local stats, next sync would re-copy if local file is touched.
   - **Recommendation:** Yes — stat the dest file. It's already there; the stat call is cheap.
   - **Blocking:** No
   - **Resolution:** Included in Task 2.1 acceptance criteria.

## References

### Research Document
- [manifest-sync-comparison-research.md](../research/manifest-sync-comparison-research.md) — Primary input

### Standards Applied
- [project.md](../../agent-system/standards/project.md) — SD card safety, cross-platform requirements, FAT32 tolerance rules

### Project Files
- [scripts/deluge_lib/syncing.py](../../scripts/deluge_lib/syncing.py) — `compute_sync()`, `_mtime_matches()`, `_FileRecord` TypedDict
- [scripts/sync_from_sd.py](../../scripts/sync_from_sd.py) — `_read_manifest()`, `_write_manifest()`, `_build_post_sync_manifest()`, `FileRecord` TypedDict
- [scripts/tests/test_syncing.py](../../scripts/tests/test_syncing.py) — `TestComputeSyncManifest` and other sync tests
- [scripts/tests/test_sync_from_sd.py](../../scripts/tests/test_sync_from_sd.py) — `TestBuildPostSyncManifest`, `TestReadManifest`, `TestWriteManifest`
- [scripts/tests/conftest.py](../../scripts/tests/conftest.py) — `_touch()` helper

## Change Log

| Date | Change | Reason |
|------|--------|--------|
| 02 May 2026 | Initial plan created | — |
