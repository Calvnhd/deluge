# Plan: Duplicate Sample Deletion

> **Document Type:** Plan
> **Date:** 04 May 2026
> **Research:** [dedup-delete-research.md](../research/dedup-delete-research.md)
> **Pipeline:** Research → **Plan** → Implement
> **Status:** Draft

## Executive Summary

Add a `--delete` flag to the existing `duplicates` subcommand in `sample_overview.py`. When set, the command picks one file to keep per hash group (preferring non-TEMP paths, then first alphabetically), previews what will be deleted, prompts for confirmation via `confirm_apply()`, deletes the files, and prints a summary. No XML reference fixing — broken refs are acceptable and detectable via `sample_overview missing`.

## Research Summary

Key findings from the [research document](../research/dedup-delete-research.md):

- **Data is ready:** `cmd_duplicates` already receives `hashes: dict[str, list[str]]` — the full SHA-256 → paths map. No new data collection needed.
- **Recommended approach:** Approach C — delete only, no reference fixing. Simplest possible implementation. ([Research §Approaches Considered](../research/dedup-delete-research.md))
- **TEMP convention:** `SAMPLES/CLIPS/TEMP/` holds throwaway clip recordings. Paths in the hash map use forward slashes (normalised by `PurePosixPath` in `hash_all_samples`). ([Research §Finding 5](../research/dedup-delete-research.md))
- **SD card safety:** Deleting from `DELUGE/SAMPLES/` is explicitly permitted by project standards. ([Research §Finding 4](../research/dedup-delete-research.md))
- **`fix_references` won't help:** After dedup, the N:1 path reduction falls into the ambiguous branch. Not worth changing. ([Research §Finding 2](../research/dedup-delete-research.md))
- **Existing pattern:** `confirm_apply()` from `deluge_lib/cli_utils.py` is the standard destructive-action gate used by `fix_references.py`, `extract_instruments.py`, `sync_to_sd.py`, and others.

### Existing Assets to Leverage

| Asset | Location | Reuse |
|-------|----------|-------|
| `cmd_duplicates` | `sample_overview.py` L364 | Extend with deletion logic |
| `hash_all_samples` | `deluge_lib/deluge_sdk.py` L93 | Already called by CLI; no changes |
| `confirm_apply` | `deluge_lib/cli_utils.py` L107 | Import and use as-is |
| `format_size` | `deluge_lib/scanning.py` | Already imported; reuse for summary |
| `print_path` | `deluge_lib/scanning.py` | Already imported; reuse for preview |
| CLI subparser | `sample_overview.py` L569 | Add `--delete` flag |

## Decisions Log

| ID | Decision | Rationale | Alternatives Considered |
|----|----------|-----------|------------------------|
| D1 | Add `--delete` as a boolean flag on the `duplicates` subparser | Minimal CLI surface. Mirrors the existing `--snapshot` optional flag. No separate `--apply` needed because `confirm_apply()` handles the gate. | (a) Separate `dedup` subcommand — over-engineers a single flag addition. (b) `--delete --apply` two-flag pattern — unnecessary since `confirm_apply()` already prevents accidental execution. |
| D2 | Survivor selection: prefer non-TEMP paths, then first alphabetically | TEMP files are throwaway by convention. Alphabetical tiebreak is deterministic and simple. | (a) Keep shortest path — less predictable. (b) Keep most-recently-modified — requires stat calls and FAT32 tolerance handling. |
| D3 | Check for TEMP using `"/CLIPS/TEMP/" in path` on the normalised forward-slash paths | `hash_all_samples` normalises all paths to forward slashes via `PurePosixPath`. A simple substring check is sufficient and cross-platform. | (a) Parse with `PurePosixPath` and check parts — heavier for no benefit. |
| D4 | All deletion logic stays in `sample_overview.py` | This is a small addition to one function. No new modules or library extractions needed. | (a) Create `deluge_lib/dedup.py` — over-engineers a ~40-line feature. |
| D5 | Preview reuses the existing duplicate display format, then appends which file is kept vs deleted | Users already understand the current output. Adding keep/delete markers to the same format is intuitive. | (a) Completely different preview format — unnecessary learning curve. |
| D6 | No `--dry-run` flag; `--delete` shows preview and prompts | Follows the `fix_references.py` pattern: show what will happen, ask for confirmation. Without `--delete`, the command shows the existing report (unchanged). | (a) `--dry-run` / `--apply` pair — adds flags for a flow that `confirm_apply()` already handles. |

## Technical Specification

### Language and Tooling

| Item | Choice | Notes |
|------|--------|-------|
| Language | Python 3.12+ | Matches existing scripts |
| Test Framework | pytest | Matches existing test suite |
| Key Dependencies | None new | `confirm_apply` already available in `deluge_lib` |

### Architecture

This is a single-file change to `sample_overview.py` with no new modules. The modification extends `cmd_duplicates` with a deletion flow that runs after the existing duplicate report.

**Data flow when `--delete` is set:**

1. Hashes are computed (or loaded from snapshot) — existing code, unchanged
2. Duplicate groups are identified and displayed — existing code, unchanged
3. For each group, a survivor is selected using the TEMP heuristic
4. A deletion preview is printed showing which files will be deleted and which will survive
5. `confirm_apply()` prompts the user
6. On confirmation, files are deleted via `Path.unlink()`
7. A summary is printed (files deleted, space reclaimed)

**Survivor selection logic:**

For each duplicate group (list of paths sharing a hash):
- Partition into TEMP paths (containing `"/CLIPS/TEMP/"`) and non-TEMP paths
- If there are any non-TEMP paths, keep the first non-TEMP path alphabetically (case-insensitive sort)
- If all paths are TEMP, keep the first path alphabetically (case-insensitive sort)
- All other paths in the group are marked for deletion

### Interface Design

**Inputs:**

```
python sample_overview.py duplicates --delete
python sample_overview.py duplicates --delete --snapshot latest
```

`--delete` is a boolean flag, compatible with the existing `--snapshot` option.

**Outputs (preview):**

After the existing duplicate report, show a deletion plan listing each group with the survivor marked and deletions listed. The exact formatting is left to the implementer, but it should clearly distinguish kept files from deleted files and show a total count and space reclaimed.

**Outputs (summary after deletion):**

A brief summary: number of files deleted, total space reclaimed, and any files that failed to delete.

**Error handling:**

- If `Path.unlink()` fails for a file (permissions, file locked, etc.), catch the `OSError`, print a warning, and continue with the remaining files. Report failures in the summary.
- If no duplicates are found, `--delete` has no effect (existing "No duplicate samples found" message is sufficient).

**User interaction:**

- Without `--delete`: existing behaviour, unchanged
- With `--delete`: existing report → deletion preview → `confirm_apply()` prompt → execute → summary

### Integration Points

- **`confirm_apply`** — Import from `deluge_lib.cli_utils` (already used by 5 other scripts)
- **`cmd_duplicates` signature** — Currently takes `(deluge_root, hashes)`. Will need access to `args.delete`. Pass the flag as an additional parameter or pass `args` directly — implementer decides.
- **`format_size` and `print_path`** — Already imported in `sample_overview.py`; reuse for preview and summary formatting
- **SD card safety** — Deletion targets `DELUGE/SAMPLES/` (the repo copy), which is explicitly editable per project standards. No SD card writes involved.

## Cross-Cutting Concerns

| Concern | Mitigation |
|---------|-----------|
| **Broken XML references** | Accepted. Deleted samples may break XML refs. User runs `sample_overview missing` to identify them. Future enhancement: inline ref fixing (Approach A from research). |
| **Git tracking** | `DELUGE/SAMPLES/` is gitignored, so deletions won't appear in git diffs. No impact on version control. |
| **Snapshot compatibility** | `--delete` works with `--snapshot` (reads hashes from snapshot JSON). However, snapshot hashes may be stale — files listed might have already been moved or deleted. `Path.unlink()` errors are caught and reported, so stale entries are handled gracefully. |

## Risk Mitigation

| Risk (from Research) | Plan Mitigation | Residual Risk |
|---------------------|-----------------|---------------|
| Accidental deletion of wanted samples | Preview + `confirm_apply()` prompt before any deletion. User sees exactly what will be deleted. | User confirms without reading — low risk, standard CLI pattern. |
| Broken XML references left unfixed | Accepted by design. `sample_overview missing` identifies broken refs. | User must run a separate command to discover breakage. |
| TEMP heuristic deletes wrong copy | Content is preserved in the surviving copy (identical hash). TEMP files are throwaway by convention. | None — the surviving copy has identical content. |

## Implementation Roadmap

## Phase 1: Core Deletion Logic

> **Goal:** Add `--delete` flag and deletion functionality to `cmd_duplicates`
> **Prerequisites:** None

### Task 1.1: Add `--delete` flag to CLI subparser

- **Description:** Add a `--delete` boolean flag to the `duplicates` subparser in the CLI section of `sample_overview.py`. Pass the flag value through to `cmd_duplicates`.
- **Inputs:** Current CLI definition in `sample_overview.py` (around L569)
- **Outputs:** `--delete` flag registered and accessible in `cmd_duplicates`
- **Acceptance Criteria:**
  - [x] `--delete` flag added to the `duplicates` subparser
  - [x] `cmd_duplicates` receives the delete flag value
  - [x] Existing `duplicates` behaviour (without `--delete`) is unchanged
  - [x] `--delete` and `--snapshot` work together
- **Implementation Notes:**
  > Added `--delete` as `store_true` flag on the subparser. Updated `cmd_duplicates` signature to accept `*, delete: bool = False` (keyword-only). Call site passes `delete=args.delete`. Guard at end of function returns early when `delete` is False. 377 existing tests pass.

### Task 1.2: Implement survivor selection

- **Description:** Add a function or inline logic to select which file to keep in each duplicate group. Apply the TEMP heuristic: prefer keeping non-TEMP paths, tiebreak by alphabetical order (case-insensitive).
- **Inputs:** A duplicate group (list of paths sharing a hash)
- **Outputs:** One path to keep, remaining paths to delete
- **Acceptance Criteria:**
  - [x] When a group has TEMP and non-TEMP paths, a non-TEMP path is kept
  - [x] When all paths are TEMP or none are TEMP, first alphabetically (case-insensitive) is kept
  - [x] Deterministic — same input always produces same selection
- **Implementation Notes:**
  > Added `_pick_survivor(paths: list[str]) -> tuple[str, list[str]]` in the helpers section of `sample_overview.py` (after `_strip_folder`). Partitions paths by `"/CLIPS/TEMP/" in path`, sorts the preferred pool with `str.casefold`, returns (survivor, to_delete). Deterministic via stable `sorted()` + casefold key. Smoke-tested with mixed, all-TEMP, and no-TEMP inputs.

### Task 1.3: Implement preview, confirmation, and deletion

- **Description:** After the existing duplicate report (when `--delete` is set), show a deletion preview listing survivors and deletions per group, call `confirm_apply()`, and on confirmation delete files via `Path.unlink()`. Print a summary of results.
- **Inputs:** Duplicate groups with survivor selections, `deluge_root` for resolving absolute paths
- **Outputs:** Deletion preview on stdout, confirmation prompt, file deletions, summary
- **Acceptance Criteria:**
  - [x] Preview clearly shows which file is kept and which are deleted in each group
  - [x] Preview shows total files to delete and total space to reclaim
  - [x] `confirm_apply()` is called before any deletion
  - [x] If user declines, no files are deleted
  - [x] Files are deleted via `Path.unlink()`
  - [x] `OSError` on individual deletions is caught, warned, and skipped
  - [x] Summary prints: files deleted, files failed, space reclaimed
  - [x] `confirm_apply` is imported from `deluge_lib.cli_utils`
- **Implementation Notes:**
  > Added `confirm_apply` to the existing `deluge_lib.cli_utils` import line. After the `if not delete: return` guard, the code: (1) builds a deletion plan by calling `_pick_survivor` for each group in `group_data`, accumulating total delete count/size; (2) prints a preview with `keep:`/`delete:` labels per group plus totals; (3) calls `confirm_apply("Proceed with deletion?")`; (4) on confirmation, iterates the plan, calls `Path.unlink()` with try/except OSError per file, tracking deleted/failed/reclaimed; (5) prints a summary. All 377 existing tests pass.

## Phase 2: Tests

> **Goal:** Add tests for the new deletion functionality
> **Prerequisites:** Phase 1 complete

### Task 2.1: Add tests for survivor selection

- **Description:** Test the survivor selection logic with representative cases: mixed TEMP and non-TEMP paths, all TEMP, no TEMP, single-copy groups (should be excluded), and case-insensitive alphabetical tiebreak.
- **Inputs:** Phase 1 implementation
- **Outputs:** Test cases in `scripts/tests/test_sample_overview.py` (new file)
- **Acceptance Criteria:**
  - [ ] Test: group with one TEMP and one non-TEMP → non-TEMP kept
  - [ ] Test: group with all TEMP → first alphabetically kept
  - [ ] Test: group with no TEMP → first alphabetically kept
  - [ ] Test: case-insensitive sort order is correct
  - [ ] All tests pass
- **Implementation Notes:**
  > 

### Task 2.2: Add tests for delete flow

- **Description:** Test the end-to-end `--delete` flow using a temporary directory with actual duplicate files. Verify preview output, confirmation gating, file deletion, and error handling.
- **Inputs:** Phase 1 implementation
- **Outputs:** Integration tests in `scripts/tests/test_sample_overview.py`
- **Acceptance Criteria:**
  - [ ] Test: `--delete` with confirmation → files deleted
  - [ ] Test: `--delete` with declined confirmation → no files deleted
  - [ ] Test: no duplicates + `--delete` → no crash, standard message
  - [ ] Test: file that fails to delete → warning printed, other deletions proceed
  - [ ] All tests pass
- **Implementation Notes:**
  > 

## Progress Tracker

| Phase | Status | Tasks Complete | Notes |
|-------|--------|---------------|-------|
| Phase 1: Core Deletion Logic | In Progress | 1/3 | Task 1.1 complete |
| Phase 2: Tests | Not Started | 0/2 | |

## Open Questions

1. **Should `--delete` with `--snapshot` warn about potentially stale data?**
   - **Impact:** Snapshot hashes may reference files that no longer exist or have been moved
   - **Recommendation:** No warning needed — `Path.unlink()` errors are caught and reported in the summary. The existing "Using snapshot: ..." message is sufficient context.
   - **Blocking:** No
   - **Resolution:**

## References

### Research Document
- [dedup-delete-research.md](../research/dedup-delete-research.md) — Primary input

### Standards Applied
- [project.md](../../agent-system/standards/project.md) — SD card safety (deletion from `DELUGE/` is permitted)
- [planning-process.md](../../agent-system/skills/feature-planning/standards/planning-process.md) — Planning process rules
- [plan-document.md](../../agent-system/skills/feature-planning/standards/plan-document.md) — Plan document format

### Project Files
- [sample_overview.py](../../scripts/sample_overview.py) — Target file for all changes
- [cli_utils.py](../../scripts/deluge_lib/cli_utils.py) — `confirm_apply()` function to import
- [deluge_sdk.py](../../scripts/deluge_lib/deluge_sdk.py) — `hash_all_samples()` (no changes needed)
- [scanning.py](../../scripts/deluge_lib/scanning.py) — `format_size()`, `print_path()` (no changes needed)

## Change Log

| Date | Change | Reason |
|------|--------|--------|
| 04 May 2026 | Initial plan created | Feature planning from research document |
| 04 May 2026 | Task 1.1 complete | `--delete` flag wired through CLI → `cmd_duplicates` |
