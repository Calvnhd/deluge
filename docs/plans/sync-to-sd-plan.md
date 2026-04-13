# Plan: Sync Repo to SD

> **Document Type:** Plan
> **Date:** 13 April 2026
> **Research:** [new-scripts-research.md](../research/new-scripts-research.md)
> **Pipeline:** Research → **Plan** → Implement
> **Status:** Complete

## Executive Summary

This plan covers the implementation of `sync_to_sd.py`, a script that deploys the curated repo `DELUGE/` directory back to the physical SD card. Following the research recommendation, the script reuses `compute_sync()` and `print_plan()` from `syncing.py` but implements its own execution logic to keep the safety-critical SD write path fully visible in one file. Before deleting any file from the SD card, the script copies it to the repo `.trash/SD-<timestamp>/` folder as a local backup.

## Research Summary

- **Recommended approach:** Reuse `compute_sync()` and `print_plan()` from `syncing.py`; custom execution logic in the script itself (Research §9, Approach B)
- **Key constraints:** Dry-run default, explicit confirmation, SD trash backed to repo before deletion, cross-platform (WSL + Windows/Cmder), FAT32 mtime tolerance
- **Existing assets:** `compute_sync()`, `print_plan()`, `append_sync_log()`, `get_deluge_root()`, `get_sd_card_path()`, `confirm_apply()`, `SyncError`/`SyncResult` dataclasses, established test patterns

## Decisions Log

| ID | Decision | Rationale | Alternatives Considered |
|----|----------|-----------|------------------------|
| D1 | Custom execution logic in `sync_to_sd.py` rather than extending `execute_plan()` | The SD trash strategy is unique — trash goes to a completely different directory tree (repo `.trash/`) with an `SD-` prefix. Keeping this in the script makes the safety-critical write path auditable in one file. Avoids coupling shared module to SD-specific concerns. (Research §3.2, Approach B) | A: New `execute_plan()` delete mode — over-generalises for single consumer. C: Pre-copy then `execute_plan(delete_mode="delete")` — fragile two-phase execution |
| D2 | No manifest for sync-to-SD | The existing manifest tracks SD→repo state. Sync-to-SD is a different direction; direct stat comparison via `compute_sync()` (without manifest arg) is appropriate, matching `sync_samples_to_cloud.py` pattern. (Research §9.2) | Use/create a separate manifest — unnecessary complexity for a deploy operation |
| D3 | Match `sync_from_sd.py` CLI pattern: default shows preview + confirmation prompt, `--dry-run` shows preview only | Established codebase convention. The project standard's "dry-run default" is satisfied by the confirmation prompt gating all writes. (Research Open Question §2) | Require explicit `--apply` flag — deviates from established pattern |
| D4 | Separate log file at `data/to_sd_sync.log` | Distinguishes SD→repo and repo→SD sync histories. Follows `sync_samples_to_cloud.py` precedent of custom log paths. (Research §3.4) | Share `data/sync.log` — harder to audit direction-specific history |
| D5 | SD trash path: `DELUGE_ROOT/.trash/SD-<timestamp>/` | The `SD-` prefix distinguishes SD-sourced trash from repo-edit trash in the same `.trash` directory. Timestamp format matches existing convention. (Research §5.3) | Separate top-level `.sd-trash/` directory — fragments trash across locations |
| D6 | Copy-then-delete execution order: all copies first, then all trash-and-deletes | Ensures the SD card receives all new/updated files before anything is removed. If the script fails partway through copies, no SD data has been lost. (Research §9.1) | Interleaved per-file operations — riskier if interrupted mid-operation |

## Technical Specification

### Language and Tooling

| Item | Choice | Notes |
|------|--------|-------|
| Language | Python 3.12+ | Existing codebase standard |
| Dependencies | None new | `shutil`, `pathlib`, `argparse` (stdlib) + existing `deluge_lib` |
| Test Framework | pytest | Established pattern |
| Linter/Formatter | ruff | Existing config in pyproject.toml |

### Architecture

`sync_to_sd.py` is a single-file script in `scripts/` that follows the established sync script pattern. It imports shared primitives from `deluge_lib/` for scanning, plan computation, plan display, logging, and CLI utilities. The safety-critical execution phase (copying to SD, trashing from SD) lives entirely within the script.

Data flow:
1. Load `DELUGE_ROOT` (source) and `SD_CARD_PATH` (dest) from `.env` via `cli_utils`
2. `compute_sync(deluge_root, sd_path)` scans both trees and returns a `SyncPlan`
3. `print_plan()` displays the plan
4. On confirmation, execute: copy phase (repo → SD), then trash-and-delete phase (SD → repo `.trash/`, then delete from SD)
5. `append_sync_log()` records the result

No modifications to `deluge_lib/` modules are required.

### Interface Design

**Inputs:**
- `DELUGE_ROOT` — repo `DELUGE/` directory (from `.env`)
- `SD_CARD_PATH` — mounted SD card path (from `.env`)
- `--dry-run` CLI flag — preview only, no prompt, no writes

**Outputs:**
- Console: source/dest paths, sync plan preview, result summary
- SD card: files copied/deleted per the plan
- Repo `.trash/SD-<timestamp>/`: backup of SD files before deletion
- Log: `scripts/data/to_sd_sync.log` — structured log entry

**Error handling:**
- `get_sd_card_path()` validates the SD card is mounted (exits if not)
- `get_deluge_root()` validates the repo directory exists (exits if not)
- Copy and delete failures are caught per-file, wrapped in `SyncError` with progress context (copied count, remaining count, failing file path)
- On `SyncError`, log the partial result, print a clear error, and exit non-zero

**User interaction:**
- Default: print source/dest, show plan, prompt with `confirm_apply()`
- `--dry-run`: print source/dest, show plan, print "Dry run complete.", exit
- Confirmation message clearly states the SD card path being modified

### Integration Points

- **`deluge_lib/syncing.py`**: consumes `compute_sync()`, `print_plan()`, `append_sync_log()`, `SyncPlan`, `SyncResult`, `SyncError`
- **`deluge_lib/cli_utils.py`**: consumes `get_deluge_root()`, `get_sd_card_path()`, `confirm_apply()`
- **`deluge_lib/scanning.py`**: consumed indirectly via `compute_sync()`
- **`DELUGE/.trash/`**: writes SD trash here; this directory is already gitignored and used by `execute_plan()` in trash mode
- **`scripts/data/to_sd_sync.log`**: new log file, sits alongside existing `sync.log` and `cloud_sync.log`

### SD Card Safety Compliance

Per `standards/project.md` §4 and §5:

1. **Dry-run gating** — No SD writes occur without passing through the confirmation prompt (or `--dry-run` exits before any write)
2. **Mount validation** — `get_sd_card_path()` validates the mount point before any operation
3. **Pre-deletion backup** — Every file deleted from the SD card is first copied to `DELUGE_ROOT/.trash/SD-<timestamp>/` preserving its relative path. The copy is verified (existence check) before the SD file is deleted
4. **Copy-before-delete ordering** — All repo→SD copies execute before any SD deletions. This means if the script fails during copies, no SD data is lost
5. **Per-file error handling** — Each file operation (copy, trash-copy, delete) is individually wrapped. On failure, `SyncError` reports exactly what succeeded and what remains
6. **Prominent path display** — Source and destination paths are printed before the plan, and the confirmation prompt includes the SD card path

## Cross-Cutting Concerns

| Concern | Mitigation |
|---------|------------|
| FAT32 mtime tolerance | Already handled by `compute_sync()` via `normalise_mtime()` and `_mtime_matches()` — no additional work |
| Cross-platform paths | `pathlib` throughout; `SD_CARD_PATH` in `.env` handles platform differences |
| Windows `PermissionError` | Caught in per-file try/except, wrapped in `SyncError` |
| SD card space exhaustion | `shutil.copy2` raises `OSError` on full disk — caught by `SyncError` handler |
| Concurrent SD card access | Not solvable in software; documented as user responsibility |
| `.trash` interaction | SD trash uses `SD-` prefix to distinguish from repo-edit trash created by `execute_plan()` |

## Risk Mitigation

| Risk (from Research) | Plan Mitigation | Residual Risk |
|---------------------|-----------------|---------------|
| Accidental SD card corruption | Dry-run default, explicit confirmation, SD trash backed to repo, copy-before-delete ordering, `SyncError` on partial failure | Power loss mid-operation could leave partial state |
| FAT32 mtime false positives | Handled by existing `normalise_mtime()` + `_mtime_matches()` | None — already battle-tested |
| Windows `PermissionError` on locked files | Per-file try/except with `SyncError` context | User must close programs accessing SD card |
| SD card unmounted mid-sync | Per-file atomic operations; `SyncError` reports progress | Partial sync, but no data loss (originals on repo) |
| Wrong `DELUGE_ROOT` pointed at SD | Source/dest printed prominently; confirmation prompt names the SD path | User must verify before confirming |

## Implementation Roadmap

### Phase 1: Script Core

> **Goal:** Working `sync_to_sd.py` with dry-run preview, confirmation, SD trash, and logging
> **Prerequisites:** None

#### Task 1.1: Create `sync_to_sd.py` with CLI and plan preview

- **Description:** Create the script file with argparse setup, env loading, `compute_sync()` call, `print_plan()` display, and `--dry-run` exit path
- **Inputs:** Existing `sync_from_sd.py` as structural reference
- **Outputs:** `scripts/sync_to_sd.py` — preview works, no execution yet
- **Acceptance Criteria:**
  - [x] Script loads `DELUGE_ROOT` and `SD_CARD_PATH` from `.env`
  - [x] Prints source and destination paths
  - [x] Calls `compute_sync(deluge_root, sd_path)` (repo as source, SD as dest)
  - [x] Calls `print_plan()` with `delete_label="delete"`
  - [x] `--dry-run` prints plan and exits without prompting
  - [x] "Already up to date." message when no changes detected
  - [x] Follows `def main(argv=None)` + `if __name__` guard pattern
- **Implementation Notes:**
  > Created `scripts/sync_to_sd.py` following `sync_samples_to_cloud.py` pattern. CLI and preview implemented in `main()`. All criteria verified by `TestDryRun` and `TestUpToDate` test classes.

#### Task 1.2: Implement execution logic with SD trash strategy

- **Description:** Add the copy phase (repo → SD) and trash-and-delete phase (SD → repo `.trash/SD-<timestamp>/`, then delete from SD). Wire up `confirm_apply()` before execution
- **Inputs:** Task 1.1 output
- **Outputs:** Full execution path in `sync_to_sd.py`
- **Acceptance Criteria:**
  - [x] `confirm_apply()` prompt includes the SD card path
  - [x] Abort path prints "Aborted." and exits cleanly
  - [x] Copy phase: for each file in `plan.files_to_copy`, creates parent directories and copies with `shutil.copy2`
  - [x] Trash phase: generates a single `SD-<timestamp>` folder name (format matching existing `.trash` convention)
  - [x] Trash phase: for each file in `plan.files_to_delete`, copies SD file to `DELUGE_ROOT/.trash/SD-<timestamp>/<rel_path>`, then calls `unlink()` on the SD file
  - [x] Trash phase: verifies the trash copy exists before deleting the SD original
  - [x] Empty parent directories on SD are cleaned up after file deletion (up to SD root)
  - [x] On `OSError` during any file operation, raises `SyncError` with file path, copied count, and remaining count
  - [x] Prints result summary on success (copied count, deleted count)
- **Implementation Notes:**
  > Execution logic in `_execute_to_sd()` — a standalone function with copy-then-trash ordering. Trash uses `shutil.copy2` + `is_file()` verification + `unlink()`. All criteria verified by `TestFullSync`, `TestAbort`, and `TestErrorHandling` test classes.

#### Task 1.3: Add sync logging

- **Description:** Call `append_sync_log()` with a custom log path after execution (success or failure)
- **Inputs:** Task 1.2 output
- **Outputs:** Logging integrated into success and error paths
- **Acceptance Criteria:**
  - [x] On success, logs to `scripts/data/to_sd_sync.log` with elapsed time and result counts
  - [x] On `SyncError`, logs partial result with error message before exiting
  - [x] Log path defined as a module-level constant
- **Implementation Notes:**
  > `_TO_SD_LOG_PATH` module constant. Both success and error paths call `append_sync_log()` with the custom log path. Verified by `test_log_entry_written` and `test_copy_failure_logs_partial_result`.

### Phase 2: Entry Point and Config

> **Goal:** Script is installable and discoverable
> **Prerequisites:** Phase 1 complete

#### Task 2.1: Register entry point in pyproject.toml

- **Description:** Add `deluge-to-sd = "sync_to_sd:main"` to the `[project.scripts]` section
- **Inputs:** `scripts/pyproject.toml`
- **Outputs:** Updated pyproject.toml
- **Acceptance Criteria:**
  - [x] Entry point `deluge-to-sd` registered and points to `sync_to_sd:main`
- **Implementation Notes:**
  > Added to `[project.scripts]` in `pyproject.toml`.

#### Task 2.2: Update .env.example

- **Description:** Ensure `.env.example` documents that `SD_CARD_PATH` is used by this script (add a comment if not already clear)
- **Inputs:** `scripts/.env.example`
- **Outputs:** Updated `.env.example` if needed
- **Acceptance Criteria:**
  - [x] `.env.example` mentions sync-to-SD usage for `SD_CARD_PATH`
- **Implementation Notes:**
  > Updated comment on `SD_CARD_PATH` to mention both sync directions.

### Phase 3: Tests

> **Goal:** Comprehensive test coverage for the script
> **Prerequisites:** Phase 1 complete

#### Task 3.1: Create test file with dry-run and up-to-date tests

- **Description:** Create `scripts/tests/test_sync_to_sd.py` with tests for dry-run preview and already-up-to-date scenarios
- **Inputs:** Existing test files for pattern reference (especially `test_sync_from_sd.py`, `test_sync_samples_to_cloud.py`)
- **Outputs:** `scripts/tests/test_sync_to_sd.py` with initial test classes
- **Acceptance Criteria:**
  - [x] `TestDryRun` class: verifies plan is printed, no files modified on "SD" (tmp_path), no prompt shown
  - [x] `TestUpToDate` class: verifies "Already up to date." output when source and dest match
  - [x] Uses `tmp_path`, `monkeypatch.setenv()`, `patch("deluge_lib.cli_utils.load_dotenv")`, `_touch()` helper
  - [x] Uses `capsys` for output assertions
- **Implementation Notes:**
  > Created `scripts/tests/test_sync_to_sd.py`. `TestDryRun` (2 tests) and `TestUpToDate` (1 test) classes follow existing patterns from `test_sync_samples_to_cloud.py`.

#### Task 3.2: Add full sync and SD trash tests

- **Description:** Test the complete execution path: copies, SD trash backup, SD deletion, and directory cleanup
- **Inputs:** Task 3.1 output
- **Outputs:** Additional test classes in `test_sync_to_sd.py`
- **Acceptance Criteria:**
  - [x] `TestFullSync` class: new files copied from repo to SD dest
  - [x] `TestFullSync`: modified files overwritten on SD dest
  - [x] `TestFullSync`: files only on SD are copied to `.trash/SD-<timestamp>/` then removed from SD dest
  - [x] `TestFullSync`: unchanged files left alone
  - [x] `TestFullSync`: result summary printed with correct counts
  - [x] `TestFullSync`: log entry written to `to_sd_sync.log`
  - [x] Confirmation decline test: prints "Aborted.", no changes made
- **Implementation Notes:**
  > `TestFullSync` (7 tests) covers copies, overwrites, SD trash+delete, unchanged files, counts, logging, and empty dir cleanup. `TestAbort` (1 test) covers confirmation decline.

#### Task 3.3: Add error handling tests

- **Description:** Test `SyncError` propagation and partial failure reporting
- **Inputs:** Task 3.2 output
- **Outputs:** Error handling test classes in `test_sync_to_sd.py`
- **Acceptance Criteria:**
  - [x] Copy failure raises `SystemExit(1)` with error message showing failed file and progress
  - [x] Trash/delete failure raises `SystemExit(1)` with error message showing failed file and progress
  - [x] Partial result is logged on failure
  - [x] Missing `SD_CARD_PATH` or `DELUGE_ROOT` raises `SystemExit`
- **Implementation Notes:**
  > `TestErrorHandling` (5 tests). Copy failure uses patched `shutil.copy2`; trash/delete failure uses patched `Path.unlink`. Both verify `SystemExit(1)` and error messages. Missing env var tests verify `SystemExit` from `cli_utils`.

## Progress Tracker

| Phase | Status | Tasks Complete | Notes |
|-------|--------|---------------|-------|
| Phase 1: Script Core | Complete | 3/3 | All tasks implemented in single file `sync_to_sd.py` |
| Phase 2: Entry Point and Config | Complete | 2/2 | Entry point registered, `.env.example` updated |
| Phase 3: Tests | Complete | 3/3 | 16 tests, all passing |

## Open Questions

1. **Should empty directories be synced to the SD card?**
   - **Impact:** If repo has an empty `KITS/NEW/` directory, should it be created on SD? `scan_tree()` only tracks files, not directories. Directories are created implicitly when files are copied.
   - **Recommendation:** No — match current `sync_from_sd.py` behaviour where directories exist only as containers for files. Empty directories on SD serve no purpose to the Deluge.
   - **Blocking:** No
   - **Resolution:**

2. **Should the script handle the case where the SD card has less free space than required?**
   - **Impact:** FAT32 may silently fail or raise `OSError` on full disk during copies.
   - **Recommendation:** No pre-flight space check — `OSError` during `shutil.copy2` is caught by `SyncError` and provides a clear error message. Pre-flight space estimation adds complexity with little value (files are copied incrementally).
   - **Blocking:** No
   - **Resolution:**

## References

### Research Document
- [new-scripts-research.md](../research/new-scripts-research.md) — Primary input (§3, §5, §9, §10, §11 most relevant)

### Standards Applied
- [project.md](../../agent-system/standards/project.md) — SD Card safety rules (§4, §5), platform requirements

### Project Files
- [sync_from_sd.py](../../scripts/sync_from_sd.py) — Primary structural reference
- [sync_samples_to_cloud.py](../../scripts/sync_samples_to_cloud.py) — Alternative sync pattern (custom log path, no manifest)
- [deluge_lib/syncing.py](../../scripts/deluge_lib/syncing.py) — Shared sync primitives
- [deluge_lib/cli_utils.py](../../scripts/deluge_lib/cli_utils.py) — CLI utilities
- [pyproject.toml](../../scripts/pyproject.toml) — Entry point registration
- [tests/test_sync_from_sd.py](../../scripts/tests/test_sync_from_sd.py) — Test patterns
- [tests/test_sync_samples_to_cloud.py](../../scripts/tests/test_sync_samples_to_cloud.py) — Test patterns

## Change Log

| Date | Change | Reason |
|------|--------|--------|
| 13 April 2026 | Initial plan created | Pipeline stage 2 |
| 13 April 2026 | All phases implemented | Pipeline stage 3 — 16 tests passing, no deviations |
