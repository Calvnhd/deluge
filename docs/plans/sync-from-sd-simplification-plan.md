# Plan: sync_from_sd.py Simplification

> **Document Type:** Plan
> **Date:** 10 April 2026
> **Research:** Inline evaluation findings (code review of current implementation)
> **Pipeline:** Research → **Plan** → Implement
> **Status:** Complete
> **Predecessor:** [sync-from-sd-improvements-plan.md](sync-from-sd-improvements-plan.md) (original feature plan, now complete)

## Executive Summary

This plan addresses over-engineering identified in `scripts/sync_from_sd.py` and its associated modules. An evaluation of the implementation produced by the original improvements plan found ~195 lines of unnecessary complexity: an over-abstracted manifest module, unused empty-directory mirroring, orphan directory trash logic, verbose `SyncResult` error fields, a multi-line log format for a gitignored file, and an SD card validator that adds no practical value. This plan removes all six sources of bloat across 6 files in a sequenced 4-phase approach, keeping atomic manifest writes and all core sync logic intact.

No new features are introduced. This is purely a simplification and trimming effort.

## Research Summary

An evaluation of the codebase produced after the original improvements plan identified six areas of over-engineering:

1. **Manifest module over-abstraction** — `deluge_lib/manifest.py` (147 lines) has a full `ManifestData` dataclass, extensible `FileRecord = dict[str, Any]`, `last_sync_direction` (only ever `"sd-to-local"`), a `version` field with no migration logic, and `file_count` metadata redundant with `len(files)`. All of this serves a single consumer script.
2. **Empty directory mirroring** — Scanner detects empty dirs, `compute_sync` computes `dirs_to_create`, `execute_plan` creates them, `SyncResult` tracks `dirs_created`. Empty folders on a Deluge SD card are practically non-existent and carry no data value.
3. **Orphan directory trash logic** — `compute_sync` builds source/dest directory key sets, computes orphan directories sorted deepest-first, adds them to `dirs_to_delete`. `execute_plan` handles directory trashing with move/rmdir strategies. Stale empty dirs are harmless.
4. **Verbose `SyncResult`** — 8 fields including `error_file`, `error_message`, `remaining` to support stop-on-failure reporting. Can be replaced with a simple counts struct and a custom exception.
5. **Multi-line log format** — `append_sync_log` writes a custom delimited format with `---` separators and structured key-value pairs for a gitignored, machine-local file nobody will parse.
6. **`_validate_sd_card`** — Checks for expected Deluge directories on the SD card path. The path comes from an env variable the user explicitly sets, and dry-run preview immediately reveals misconfiguration.

### Existing Assets

- **`scripts/sync_from_sd.py`** (415 lines) — main script; all recommendations modify this file
- **`scripts/deluge_lib/manifest.py`** (147 lines) — to be deleted, core logic inlined
- **`scripts/deluge_lib/scanning.py`** (101 lines) — empty dir detection to be removed
- **`scripts/tests/test_manifest.py`** (167 lines) — to be deleted, relevant tests folded into `test_sync_from_sd.py`
- **`scripts/tests/test_scanning.py`** (149 lines) — empty dir tests to be removed
- **`scripts/tests/test_sync_from_sd.py`** (303 lines) — updated with inlined manifest tests, simplified assertions

## Decisions Log

| ID | Decision | Rationale | Alternatives Considered |
|----|----------|-----------|------------------------|
| S1 | Inline manifest read/write into `sync_from_sd.py` as simple helper functions; delete `manifest.py` module | The manifest has exactly one consumer. A dedicated module with a dataclass, extensible fields, and version tracking is unnecessary abstraction. Inlining reduces indirection and makes the sync script self-contained. | Keep module but simplify (still unnecessary indirection for one consumer) |
| S2 | Drop `ManifestData` dataclass; use a plain `dict` with `TypedDict` for file records | The dataclass wraps metadata fields that are being removed (version, direction, file_count). What remains is `last_sync_timestamp` and `files` — simple enough for a plain dict. `TypedDict` for file records gives type safety without `dict[str, Any]`. | Keep a slimmed dataclass (extra boilerplate for two fields) |
| S3 | Drop `last_sync_direction`, `version`, and `file_count` from manifest | `last_sync_direction` only ever writes `"sd-to-local"` — the reverse script doesn't exist. `version` is written but never checked; no migration logic exists. `file_count` is redundant with `len(files)`. All are dead weight. | Keep version for future-proofing (YAGNI — no migration logic exists or is planned) |
| S4 | Keep atomic write (tempfile + rename) for manifest | Atomic write protects against corruption from interrupted writes. This is genuine robustness, not over-engineering. | Direct write (risk of corrupt manifest on crash) |
| S5 | Remove empty directory mirroring entirely | Empty folders on a Deluge SD card almost never exist. The Deluge creates files in its directories. Even if they exist, they carry no data value. Removing this simplifies scanner, sync plan, execution, and result tracking. | Keep but simplify (complexity for a non-existent use case) |
| S6 | Remove orphan directory trash logic | Stale empty directories in the repo backup are harmless. The trash logic for directories (move non-empty, rmdir empty, sorted deepest-first) adds significant complexity for negligible benefit. File-level trashing remains. | Keep for completeness (complexity for harmless edge case) |
| S7 | Replace `SyncResult` with counts-only structure; raise custom exception on failure | Current 8-field dataclass exists to carry error context through return values. A custom exception is the idiomatic way to handle failure — it separates the success path (counts) from the error path (exception with details). | Keep SyncResult with fewer fields (still mixes success and failure concerns) |
| S8 | Simplify log to one-line-per-run format | The current multi-line delimited format with `---` separators is a gitignored, machine-local file. Nobody parses it. A single line per run with key=value pairs is equally informative and much simpler. | Keep structured format (over-engineered for a local debug log) |
| S9 | Remove `_validate_sd_card` and `_DELUGE_EXPECTED_DIRS` | The SD card path is explicitly set via env variable. A misconfigured path is immediately visible in the dry-run preview (wrong or missing files). The validation adds 10 lines for a check that the UX already provides. | Keep as a safety net (redundant with dry-run preview) |
| S10 | Sequence removals to keep tests green at each phase | Each phase should leave the test suite passing. This allows incremental commits and easy rollback. | Big-bang refactor (harder to debug if tests break) |

## Technical Specification

### 5a. Language and Tooling

| Item | Choice | Notes |
|------|--------|-------|
| Language | Python 3.12+ | Existing project language |
| Test Framework | pytest | Already configured in `pyproject.toml` |
| Linter/Formatter | ruff | Already configured in `pyproject.toml` |
| Type Checker | mypy | Already configured in `pyproject.toml` |
| Key Dependencies | None new | Standard library only (json, pathlib, shutil, tempfile) |

### 5b. Architecture

After simplification, the module structure changes:

**Before:**
- `sync_from_sd.py` — orchestration, sync logic, logging
- `deluge_lib/manifest.py` — manifest read/write/types (separate module)
- `deluge_lib/scanning.py` — file scanner with empty dir detection

**After:**
- `sync_from_sd.py` — orchestration, sync logic, logging, manifest read/write (inlined)
- `deluge_lib/scanning.py` — file scanner (simplified, no empty dir tracking)

The manifest read/write becomes two simple functions at the top of `sync_from_sd.py`: one to read a JSON file into a dict, one to atomically write a dict to a JSON file. The manifest format simplifies to `{"last_sync_timestamp": str, "files": {key: {"size": int, "mtime": float}}}`.

`SyncPlan` loses `dirs_to_create` and `dirs_to_delete`, retaining only `files_to_copy`, `files_to_delete`, and `files_unchanged`.

`SyncResult` is replaced by a simpler structure with just `copied`, `trashed`, and `unchanged` counts. Failure is communicated via a custom `SyncError` exception raised by `execute_plan`.

### 5c. Interface Design

**Inputs** — No changes to CLI interface. Same `--dry-run` / `--confirm` flags and `SD_CARD_PATH` env variable.

**Outputs** — Console output simplified:
- `dirs created` line removed from summary
- `dirs to create` removed from dry-run preview
- Directory trash lines removed from dry-run preview

**Error Handling** — `execute_plan` raises `SyncError` on failure instead of returning a `SyncResult` with error fields. `main()` catches `SyncError` and reports the error. Manifest is not updated on failure (unchanged behaviour).

**Log Format** — Changes from multi-line to single-line:
```
2026-04-10 12:00:00 SUCCESS copied=5 trashed=2 unchanged=100 elapsed=1m 23s
2026-04-10 13:00:00 FAILED copied=3 trashed=0 unchanged=0 elapsed=0m 5s error="Permission denied: KITS/Kit.XML"
```

### 5d. Integration Points

- `deluge_lib/scanning.py` — `ScanResult` loses `empty_dirs` field; `scan_tree` stops tracking empty directories
- `deluge_lib/manifest.py` — deleted entirely; imports in `sync_from_sd.py` replaced with inlined functions
- `deluge_lib/cli_utils.py` — unchanged
- `scripts/tests/test_manifest.py` — deleted; manifest read/write/corruption tests moved to `test_sync_from_sd.py`
- SD card safety — no impact; script remains read-only on SD card

## Cross-Cutting Concerns

| Concern | Mitigation |
|---------|-----------|
| Manifest backward compatibility | The simplified manifest format drops `version`, `direction`, and `file_count` from the metadata section. The read function should tolerate old manifests that contain these fields (ignore them). This ensures a seamless transition — no manual manifest deletion needed. |
| Test coverage | Each phase removes code and its tests together. Net test count decreases but coverage of remaining code stays equivalent. Manifest read/write/corruption tests are preserved (moved, not deleted). |
| Atomic writes | Kept intact. This is genuine robustness. |
| FAT32 tolerance | Unchanged. `_mtime_matches` with ±2s tolerance stays as-is. |

## Risk Mitigation

| Risk | Plan Mitigation | Residual Risk |
|------|-----------------|---------------|
| Breaking existing manifest files | Read function tolerates old format fields (ignores unknown keys). Writes produce new simpler format. | None — old manifests work, new manifests are simpler |
| Removing useful functionality (empty dirs, orphan dirs) | Evaluation confirmed these are unused in practice. If needed later, git history preserves the implementation. | Extremely low — Deluge doesn't create empty dirs |
| Test regressions during refactor | Phases are sequenced so tests pass at each step. Each phase is independently committable. | Low — standard refactoring risk |
| `_validate_sd_card` removal hiding misconfiguration | Dry-run preview (default mode) immediately shows what would be synced. A wrong path produces an obviously wrong file list (or empty list). | Low — UX provides equivalent feedback |

## Implementation Roadmap

### Phase 1: Remove Empty Directory Mirroring and Orphan Directory Logic

> **Goal:** Remove recommendations 2 and 3 together since they're tightly coupled — both deal with directory-level sync logic.
> **Prerequisites:** All tests passing on current codebase.

#### Task 1.1: Remove empty directory detection from scanner

- **Description:** Remove `empty_dirs` from `ScanResult` dataclass and remove empty directory tracking from `scan_tree` in `scanning.py`.
- **Inputs:** `scripts/deluge_lib/scanning.py`
- **Outputs:** Simplified `ScanResult` without `empty_dirs`; simplified `scan_tree` without `has_content` tracking
- **Acceptance Criteria:**
  - [x] `ScanResult` no longer has an `empty_dirs` field
  - [x] `scan_tree` no longer tracks or returns empty directories
  - [x] `has_content` variable and related logic removed from `scan_tree`
- **Implementation Notes:**
  > Removed `empty_dirs` field from `ScanResult`, removed `has_content` variable and the empty-dir detection block at the end of the loop body. Updated module and function docstrings.: Remove empty directory tests from test_scanning.py

- **Description:** Delete the `TestEmptyDirectories` test class from `test_scanning.py`.
- **Inputs:** `scripts/tests/test_scanning.py`
- **Outputs:** Test file without empty directory tests
- **Acceptance Criteria:**
  - [x] `TestEmptyDirectories` class removed
  - [x] No remaining references to `empty_dirs` in test file
- **Implementation Notes:**
  > Removed entire `TestEmptyDirectories` class (3 tests). No other references to `empty_dirs` existed in the test file.: Remove directory logic from compute_sync

- **Description:** Remove `dirs_to_create` and `dirs_to_delete` from `SyncPlan`. Remove orphan directory computation (`src_dir_keys`, `dst_dirs`, `orphan_dirs`) and empty dir creation logic from `compute_sync`.
- **Inputs:** `scripts/sync_from_sd.py`
- **Outputs:** Simplified `SyncPlan` with only `files_to_copy`, `files_to_delete`, `files_unchanged`; simplified `compute_sync` without directory logic
- **Acceptance Criteria:**
  - [x] `SyncPlan` has no `dirs_to_create` or `dirs_to_delete` fields
  - [x] `compute_sync` does not reference `empty_dirs`, `src_dir_keys`, `dst_dirs`, or `orphan_dirs`
  - [x] All references to `src_scan.empty_dirs` and `dst_scan.empty_dirs` removed
- **Implementation Notes:**
  > Removed `dirs_to_create` and `dirs_to_delete` from `SyncPlan`. Removed ~30 lines of orphan directory computation and empty dir creation logic from `compute_sync`.: Remove directory logic from execute_plan, print_plan, and _plan_is_empty

- **Description:** Remove directory creation and directory trashing from `execute_plan`. Remove directory lines from `print_plan`. Simplify `_plan_is_empty` to check only file lists.
- **Inputs:** `scripts/sync_from_sd.py`
- **Outputs:** Simplified execution and display functions
- **Acceptance Criteria:**
  - [x] `execute_plan` has no directory creation or directory trash logic
  - [x] `print_plan` does not print `mkdir` or directory trash lines; summary line drops "dirs to create"
  - [x] `_plan_is_empty` checks only `files_to_copy` and `files_to_delete`
- **Implementation Notes:**
  > Removed empty dir creation block and dir trashing block from `execute_plan`. Removed `mkdir` and dir trash lines from `print_plan`. Simplified `_plan_is_empty` to a one-liner.: Remove dirs_created from SyncResult and update consumers

- **Description:** Remove `dirs_created` field from `SyncResult`. Update `append_sync_log` and `main()` summary output to not reference `dirs_created`.
- **Inputs:** `scripts/sync_from_sd.py`
- **Outputs:** `SyncResult` without `dirs_created`; log and summary without dir count
- **Acceptance Criteria:**
  - [x] `SyncResult` has no `dirs_created` field
  - [x] `append_sync_log` does not write `dirs_created`
  - [x] `main()` summary does not mention dirs created
- **Implementation Notes:**
  > Removed `dirs_created` from `SyncResult`. Removed `dirs_created` line from `append_sync_log`. Updated `main()` summary format string.: Update sync tests for directory removal

- **Description:** Remove `TestExecutePlanDirs` test class from `test_sync_from_sd.py`. Update any remaining tests that reference `dirs_to_create`, `dirs_to_delete`, or `dirs_created`.
- **Inputs:** `scripts/tests/test_sync_from_sd.py`
- **Outputs:** Test file without directory-related assertions
- **Acceptance Criteria:**
  - [x] `TestExecutePlanDirs` class removed
  - [x] No remaining references to `dirs_to_create`, `dirs_to_delete`, or `dirs_created` in test file
  - [x] All tests pass
- **Implementation Notes:**
  > Removed `TestExecutePlanDirs` class (1 test). Updated `TestAppendSyncLog.test_creates_entry_on_success` to remove `dirs_created` from `SyncResult` construction and assertion. 2 pre-existing symlink test failures on Windows (privilege issue) are unrelated.: Simplify SyncResult and Error Handling

> **Goal:** Replace verbose SyncResult with counts-only structure and exception-based failure (recommendation 4).
> **Prerequisites:** Phase 1 complete, all tests passing.

#### Task 2.1: Create SyncError exception class

- **Description:** Add a simple `SyncError` exception class to `sync_from_sd.py` that carries error context: the file that failed, the error message, counts completed so far, and remaining count.
- **Inputs:** `scripts/sync_from_sd.py`
- **Outputs:** `SyncError` exception class
- **Acceptance Criteria:**
  - [x] `SyncError` exception defined with attributes for error details
  - [x] Exception is a subclass of `Exception`
- **Implementation Notes:**
  > Added `SyncError(Exception)` with `__init__` accepting `message`, `file`, `copied`, `trashed`, `unchanged`, `remaining` keyword args. All attributes stored on the instance.

#### Task 2.2: Simplify SyncResult to counts-only

- **Description:** Reduce `SyncResult` to three fields: `copied`, `trashed`, `unchanged`. Remove `success`, `error_file`, `error_message`, `remaining`, and `dirs_created` (already removed in Phase 1).
- **Inputs:** `scripts/sync_from_sd.py`
- **Outputs:** Simplified `SyncResult` dataclass
- **Acceptance Criteria:**
  - [x] `SyncResult` has exactly three fields: `copied`, `trashed`, `unchanged`
  - [x] No `success`, `error_file`, `error_message`, or `remaining` fields
- **Implementation Notes:**
  > Reduced `SyncResult` from 7 fields to 3 (`copied`, `trashed`, `unchanged`), all defaulting to 0.

#### Task 2.3: Update execute_plan to raise SyncError on failure

- **Description:** Modify `execute_plan` to raise `SyncError` instead of returning a `SyncResult` with `success=False`. On success, return the simplified `SyncResult` with counts only.
- **Inputs:** `scripts/sync_from_sd.py`
- **Outputs:** `execute_plan` that raises on failure, returns counts on success
- **Acceptance Criteria:**
  - [x] `execute_plan` raises `SyncError` on copy failure
  - [x] `execute_plan` raises `SyncError` on trash failure
  - [x] `execute_plan` returns `SyncResult` (counts-only) on success
- **Implementation Notes:**
  > Replaced both `return SyncResult(success=False, ...)` blocks with `raise SyncError(...) from exc`. Used `from exc` to chain the original `OSError` per ruff B904.

#### Task 2.4: Update main() to catch SyncError

- **Description:** Modify `main()` to wrap `execute_plan` in a try/except for `SyncError`. Log the failure, print the error, skip manifest update, and exit with code 1.
- **Inputs:** `scripts/sync_from_sd.py`
- **Outputs:** Updated `main()` with exception handling
- **Acceptance Criteria:**
  - [x] `main()` catches `SyncError` and reports the error
  - [x] Manifest is not updated on `SyncError` (unchanged behaviour)
  - [x] `append_sync_log` is called for both success and failure
  - [x] Exit code 1 on failure
- **Implementation Notes:**
  > Wrapped `execute_plan` call in `try/except SyncError`. On failure, constructs a `SyncResult` from the exception's counts for logging, calls `append_sync_log` with `error=str(exc)`, then raises `SystemExit(1) from None`. Updated `append_sync_log` signature to accept optional `error: str | None` parameter instead of reading `result.success`.

#### Task 2.5: Update sync tests for SyncResult and SyncError

- **Description:** Update `TestExecutePlanFailure` to assert `SyncError` is raised instead of checking `result.success`. Update `TestExecutePlanCopy` and `TestExecutePlanTrash` to use simplified `SyncResult`. Update log tests if they reference removed fields.
- **Inputs:** `scripts/tests/test_sync_from_sd.py`
- **Outputs:** Updated test assertions
- **Acceptance Criteria:**
  - [x] Failure tests use `pytest.raises(SyncError)`
  - [x] Success tests check only `copied`, `trashed`, `unchanged`
  - [x] No references to `result.success`, `result.error_file`, `result.error_message`, or `result.remaining`
  - [x] All tests pass
- **Implementation Notes:**
  > Updated `TestExecutePlanFailure` to use `pytest.raises(SyncError)` and check `exc_info.value.copied` / `.file` / `.remaining`. Removed `result.success` assertions from copy/trash tests. Removed `success=True/False` from all `SyncResult` constructions in log tests. Updated failure log test to pass `error=` kwarg to `append_sync_log`. Fixed import ordering per ruff I001.

---

### Phase 3: Inline Manifest and Simplify Log

> **Goal:** Inline manifest module into sync_from_sd.py (recommendation 1) and simplify log format (recommendation 5). Grouped because manifest inlining changes imports and types that the log function uses.
> **Prerequisites:** Phase 2 complete, all tests passing.

#### Task 3.1: Define simplified manifest types and helpers in sync_from_sd.py

- **Description:** Add a `FileRecord` TypedDict (with `size: int` and `mtime: float`), a `FilesDict` type alias, and simple `read_manifest` / `write_manifest` helper functions directly in `sync_from_sd.py`. The read function should return a tuple of `(last_sync_timestamp: str, files: FilesDict)` or equivalent simple structure. Tolerate old manifest format (ignore unknown metadata fields). Keep atomic write.
- **Inputs:** `scripts/sync_from_sd.py`, `scripts/deluge_lib/manifest.py` (reference for logic)
- **Outputs:** Inlined manifest functions in `sync_from_sd.py`
- **Acceptance Criteria:**
  - [x] `FileRecord` TypedDict with `size` and `mtime` defined in `sync_from_sd.py`
  - [x] `read_manifest` function reads JSON, returns timestamp + files dict, tolerates missing/corrupt files
  - [x] `write_manifest` function writes JSON atomically (tempfile + rename)
  - [x] Manifest output format: `{"last_sync_timestamp": str, "files": {key: {"size": int, "mtime": float}}}`
  - [x] Old manifests with extra metadata fields (version, direction, file_count) are read without error
- **Implementation Notes:**
  > Added `FileRecord` TypedDict, `_read_manifest_inline`, and `_write_manifest_inline` alongside existing imports. Functions are underscore-prefixed to avoid shadowing the still-imported `read_manifest`/`write_manifest` from `deluge_lib.manifest` — Task 3.2 removes the old imports and renames these. `FilesDict` type alias deferred to 3.2 for the same reason (name conflict with import). The read function handles both old format (`metadata.last_sync_timestamp`) and new format (top-level `last_sync_timestamp`), ignoring unknown fields. Added `json`, `tempfile`, and `TypedDict` imports. All 63 tests pass, ruff clean, mypy clean.

#### Task 3.2: Update sync_from_sd.py to use inlined manifest

- **Description:** Replace all imports from `deluge_lib.manifest` with the new inlined functions. Update `_build_post_sync_manifest` to return the simplified structure (just timestamp + files dict) instead of constructing a `ManifestData` dataclass. Remove `make_timestamp` import (inline or use `datetime` directly). Update `main()` to use the new read/write signatures.
- **Inputs:** `scripts/sync_from_sd.py`
- **Outputs:** No imports from `deluge_lib.manifest`; all manifest logic is local
- **Acceptance Criteria:**
  - [x] No imports from `deluge_lib.manifest` remain
  - [x] `_build_post_sync_manifest` returns simplified dict structure
  - [x] `main()` calls inlined `read_manifest` / `write_manifest`
  - [x] `compute_sync` manifest parameter uses `FilesDict` (TypedDict-based)
- **Implementation Notes:**
  > Removed entire `deluge_lib.manifest` import block. Added `UTC` to datetime import. Added `FilesDict = dict[str, FileRecord]` type alias after `FileRecord` TypedDict. Renamed `_read_manifest_inline` → `_read_manifest` and `_write_manifest_inline` → `_write_manifest`. Added `_default_manifest_path()` helper. Updated `_build_post_sync_manifest` to accept `old_files: dict[str, FileRecord]` and return `tuple[str, dict[str, FileRecord]]` with inline `datetime.now(tz=UTC)` timestamp. Updated `main()` to destructure tuple returns and call inlined functions. Updated `test_sync_from_sd.py`: replaced `ManifestData` import with `FileRecord`, adapted both `_build_post_sync_manifest` tests to use new signature. 63 tests pass, ruff clean, mypy clean.

#### Task 3.3: Delete manifest.py module

- **Description:** Delete `scripts/deluge_lib/manifest.py`.
- **Inputs:** File deletion
- **Outputs:** Module removed
- **Acceptance Criteria:**
  - [x] `scripts/deluge_lib/manifest.py` no longer exists
  - [x] No imports of `deluge_lib.manifest` anywhere in the codebase
- **Implementation Notes:**
  > Deleted `scripts/deluge_lib/manifest.py`. Verified no production code imports from it. Only remaining import is in `scripts/tests/test_manifest.py` (handled by Task 3.4). Tests in `test_manifest.py` will fail until 3.4 migrates them.

#### Task 3.4: Migrate manifest tests to test_sync_from_sd.py

- **Description:** Move relevant manifest tests from `test_manifest.py` into `test_sync_from_sd.py`. Keep: missing file returns empty, corrupt JSON returns empty, corrupt JSON prints warning, valid manifest round-trip, atomic write (no temp file lingers), parent directory creation. Drop: tests for `version`, `direction`, `file_count` fields (removed). Update imports to reference inlined functions.
- **Inputs:** `scripts/tests/test_manifest.py` (source), `scripts/tests/test_sync_from_sd.py` (destination)
- **Outputs:** Manifest tests in `test_sync_from_sd.py`; `test_manifest.py` deleted
- **Acceptance Criteria:**
  - [x] `scripts/tests/test_manifest.py` deleted
  - [x] `test_sync_from_sd.py` has tests for: read missing, read corrupt, read valid, write creates file, write atomic, write creates parent dir
  - [x] No tests for `version`, `direction`, or `file_count` fields
  - [x] All tests pass
- **Implementation Notes:**
  > Migrated 7 tests into 2 new classes (`TestReadManifest`, `TestWriteManifest`) in `test_sync_from_sd.py`. Adapted assertions from old `ManifestData` dataclass to new `(timestamp, files)` tuple returns. Added `_read_manifest`, `_write_manifest`, `json` to imports. Dropped 10 tests that exercised removed fields (`version`, `direction`, `file_count`) or old-format-only behaviours (`ManifestData` dataclass, metadata wrapper). All 54 tests pass.

#### Task 3.5: Simplify append_sync_log to one-line format

- **Description:** Replace the multi-line `---`-delimited log format with a single line per run: `{timestamp} {status} copied={n} trashed={n} unchanged={n} elapsed={t}`. On failure, append `error="{message}"`. Remove `dirs_created` from log (already removed in Phase 1).
- **Inputs:** `scripts/sync_from_sd.py`
- **Outputs:** Simplified `append_sync_log` function
- **Acceptance Criteria:**
  - [x] Each sync run produces exactly one line in the log file
  - [x] Format: `{timestamp} {status} copied={n} trashed={n} unchanged={n} elapsed={Xm Ys}`
  - [x] Failed runs append `error="..."` to the line
  - [x] No `---` separators, no `script:` field, no multi-line structure
- **Implementation Notes:**
  > Replaced multi-line `---`-delimited block with a single `f.write(line + "\n")` call. Error field uses `error="{msg}"` format (quoted). Signature unchanged — optional `error: str | None` parameter was already added in Phase 2. All 54 tests pass.

---

### Phase 4: Remove SD Card Validation

> **Goal:** Remove `_validate_sd_card` (recommendation 6). Saved for last as it's the simplest, independent change.
> **Prerequisites:** Phase 3 complete, all tests passing.

#### Task 4.1: Remove _validate_sd_card and _DELUGE_EXPECTED_DIRS

- **Description:** Delete the `_validate_sd_card` function and the `_DELUGE_EXPECTED_DIRS` constant. Remove the `_validate_sd_card(sd_path)` call from `main()`.
- **Inputs:** `scripts/sync_from_sd.py`
- **Outputs:** Function and constant removed; `main()` no longer calls validation
- **Acceptance Criteria:**
  - [x] `_validate_sd_card` function does not exist
  - [x] `_DELUGE_EXPECTED_DIRS` constant does not exist
  - [x] `main()` does not call `_validate_sd_card`
  - [x] All tests pass
- **Implementation Notes:**
  > Removed `_DELUGE_EXPECTED_DIRS` constant, `_validate_sd_card` function (10 lines total), and the call in `main()`. No tests referenced these symbols. 54/54 tests pass, mypy clean, ruff clean.

#### Task 4.2: Final verification

- **Description:** Run full test suite, type checker, and linter. Verify approximate line counts to confirm expected savings (~195 lines net reduction across all files).
- **Inputs:** All modified files
- **Outputs:** Clean test/lint/type-check run
- **Acceptance Criteria:**
  - [x] `pytest` passes with no failures
  - [x] `mypy` passes with no errors
  - [x] `ruff check` passes with no errors
  - [x] `manifest.py` and `test_manifest.py` no longer exist
  - [~] Net line reduction: production code shrank by 43 lines; overall net is +21 lines due to test consolidation growth (see notes)
- **Implementation Notes:**
  > All checks pass (54 tests, mypy clean, ruff clean). `manifest.py` and `test_manifest.py` are deleted. Line counts — original total: 1282, current total: 1303 (net +21). Production code shrank by 43 lines (415+147+101=663 → 500+120=620). Test code grew by 64 lines (167+149+303=619 → 201+482=683) because manifest tests consolidated into test_sync_from_sd.py. The ~195 lines of identified over-engineering were all removed, but inlining manifest logic and migrating tests added replacement lines. The 150–200 net reduction estimate did not account for test consolidation growth.

## Progress Tracker

| Phase | Status | Tasks Complete | Notes |
|-------|--------|---------------|-------|
| Phase 1: Remove Empty Dir & Orphan Dir Logic | Complete | 6/6 | All tests pass (2 pre-existing symlink failures on Windows unrelated) |
| Phase 2: Simplify SyncResult & Error Handling | Complete | 5/5 | All tests pass (61/63, 2 pre-existing symlink failures). Ruff clean. Mypy clean. |
| Phase 3: Inline Manifest & Simplify Log | Complete | 5/5 | All tasks complete — manifest inlined, log simplified to one-line format |
| Phase 4: Remove SD Card Validation | Complete | 2/2 | All 6 recommendations implemented. All checks pass. |

## Open Questions

1. **Should `append_sync_log` accept error info as a parameter or should `main()` handle failure logging separately?**
   - **Impact:** Affects the signature of `append_sync_log` and the `main()` error handling flow.
   - **Recommendation:** Pass an optional `error: str | None` parameter to `append_sync_log`. This keeps logging centralised — `main()` calls it in both success and failure paths, passing the error string from the caught `SyncError` when applicable.
   - **Blocking:** No
   - **Resolution:** Implemented the recommended approach: `append_sync_log` accepts optional `error: str | None` parameter. `main()` calls it in both success and failure paths. On failure, the error string from the caught `SyncError` is passed; the `SyncResult` is constructed from the exception's count attributes.

## References

### Research Input
- Inline evaluation findings provided in task delegation (code review of current implementation)

### Standards Applied
- [project.md](../../agent-system/standards/project.md) — SD card safety, cross-platform requirements, FAT32 tolerance
- [plan-document.md](../../agent-system/skills/feature-planning/standards/plan-document.md) — Plan document template

### Project Files
- [sync_from_sd.py](../../scripts/sync_from_sd.py) — Main sync script (415 lines, primary modification target)
- [manifest.py](../../scripts/deluge_lib/manifest.py) — Manifest module (147 lines, to be deleted)
- [scanning.py](../../scripts/deluge_lib/scanning.py) — Scanner module (101 lines, simplified)
- [test_manifest.py](../../scripts/tests/test_manifest.py) — Manifest tests (167 lines, to be deleted)
- [test_scanning.py](../../scripts/tests/test_scanning.py) — Scanner tests (149 lines, simplified)
- [test_sync_from_sd.py](../../scripts/tests/test_sync_from_sd.py) — Sync tests (303 lines, updated)
- [sync-from-sd-improvements-plan.md](sync-from-sd-improvements-plan.md) — Original improvements plan (predecessor)

## Change Log

| Date | Change | Reason |
|------|--------|--------|
| 10 April 2026 | Initial plan created | Evaluation identified ~195 lines of over-engineering across 6 recommendations |
| 10 April 2026 | Phase 4 complete; plan marked Complete | All 4 phases done. Validation removed, all checks pass. Net line reduction lower than estimated due to test consolidation growth. |
| 10 April 2026 | Phase 1 complete | Removed empty directory mirroring and orphan directory trash logic across 4 files (~85 lines removed) |
| 10 April 2026 | Phase 2 complete | Simplified SyncResult to 3 fields, added SyncError exception, updated execute_plan/main/append_sync_log/tests. Resolved open question: append_sync_log takes optional `error: str | None` parameter. |
| 10 April 2026 | Task 3.2 complete | Removed all `deluge_lib.manifest` imports; inlined `_read_manifest`, `_write_manifest`, `_default_manifest_path`, `FilesDict` alias; updated `_build_post_sync_manifest` to return `(timestamp, files)` tuple; updated `main()` and tests. |
| 10 April 2026 | Task 3.3 complete | Deleted `scripts/deluge_lib/manifest.py`. Only remaining import is in `test_manifest.py` (Task 3.4). |
| 10 April 2026 | Task 3.4 complete | Migrated 7 manifest tests to `test_sync_from_sd.py`, deleted `test_manifest.py`. Dropped 10 tests for removed fields. 54/54 pass. |
