# Plan: sync_from_sd Simplification (Round 2)

> **Document Type:** Plan
> **Date:** 10 April 2026
> **Research:** N/A — based on direct code review findings
> **Pipeline:** Research → **Plan** → Implement
> **Status:** Complete
> **Predecessor:** [sync-from-sd-simplification-plan.md](sync-from-sd-simplification-plan.md) (round 1, complete)

## Executive Summary

This plan covers 12 targeted simplification and cleanup changes across `scripts/deluge_lib/scanning.py`, `scripts/sync_from_sd.py`, and supporting documentation. The changes remove dead-code defences (symlink checks), simplify directory pruning, eliminate a redundant parameter and output path, improve naming clarity, add a useful diagnostic print, tighten error-reporting responsibility, and update documentation to reflect the simplified CLI. No new features are added; this is a code-quality pass following the round 1 simplification.

## Research Summary

No formal research document was produced. The user reviewed the two core sync scripts after round 1 and identified 10 further cleanup items:

- **scanning.py** (items 1–6): Remove symlink checks, simplify `.trash` pruning, remove mid-scan counter and the `progress` parameter; rename a confusing variable; add a print for skipped files.
- **sync_from_sd.py** (items 7–10): Pre-compute a repeated path expression, simplify the post-scan flow in `main()`, improve the confirmation message, and consolidate duplicate error output.
- **Documentation** (items 11–12): Update `README.md` and agent-system standards to reflect the removal of `--confirm`.

All changes are low-risk, localised, and independently verifiable.

## Decisions Log

| ID | Decision | Rationale | Alternatives Considered |
|----|----------|-----------|------------------------|
| D1 | Remove symlink handling entirely | FAT32 (the SD card filesystem) has no symlink concept. The local `DELUGE/` backup is managed by this repo and should never contain symlinks either. The checks add complexity for zero practical benefit. | Keep checks but add a comment explaining they're precautionary |
| D2 | Keep `.trash` directory exclusion in the scanner | `scan_tree` is used to scan both the source (SD card) and the destination (`DELUGE/`). The destination has `.trash` folders created by previous syncs. Without the exclusion, `.trash` files would appear in the dest scan, get flagged as "not on source," and be re-trashed into a new timestamped subfolder — causing recursive `.trash` nesting on every sync. | Remove exclusion and handle at the `compute_sync` level |
| D3 | Rename `dir_path` to `current_dir` in `scan_tree()` | `dirpath` (string from `os.walk`) and `dir_path` (its `Path` conversion) differ by only an underscore, which is error-prone and confusing. `current_dir` is unambiguous. | `dir_as_path`, `walk_dir` |
| D4 | Print skipped files to stdout rather than using logging | The project uses print-based output consistently. Only 1–2 non-xml/wav files are expected on an SD card, so noise is minimal. | Use Python `logging` module; collect and summarise at the end |
| D5 | Remove `progress` parameter and always print | The parameter exists only to suppress output in tests and `deluge_sdk.py`. pytest captures stdout by default so test output is hidden unless a test fails. The single summary line is useful in all contexts. Removing the parameter simplifies the interface. | Keep the parameter; make it control verbosity levels |
| D6 | Remove `--confirm` flag from CLI | The simplified `main()` flow always shows the plan then prompts. `--confirm` previously skipped the preview, but since the preview is now the only path, it serves no purpose. `--dry-run` remains for non-interactive use. | Keep `--confirm` as a no-op with a deprecation warning |
| D7 | Let `main()` handle all error output for `SyncError` | The current pattern prints detailed errors inside `execute_plan`'s `except OSError` blocks AND propagates them via `SyncError` to `main()`, which prints its own message. Single-responsibility: `execute_plan` raises, `main()` reports. | Keep dual output; suppress the `main()` message instead |

## Technical Specification

### Language and Tooling

| Item | Choice | Notes |
|------|--------|-------|
| Language | Python 3.12+ | Existing project language |
| Test Framework | pytest | Already configured in `pyproject.toml` |
| Linter/Formatter | ruff | Already configured in `pyproject.toml` |
| Type Checker | mypy | Already configured in `pyproject.toml` |
| Key Dependencies | None new | All changes use stdlib only |

### Architecture

No architectural changes. The module structure remains the same. All changes are internal to existing functions.

### Interface Design

**Inputs (changed):**
- `scan_tree()` loses the `progress` parameter. The `label` parameter is retained.
- `main()` loses the `--confirm` CLI flag. `--dry-run` is retained.

**Outputs (changed):**
- `scan_tree()` always prints a "Scanning {label}..." opening line and a final "{count} files found." closing line. When a file is skipped due to extension filtering, a message is printed.
- `main()` flow simplified: single plan display, single empty-plan check, single error output location.
- `confirm_apply()` message includes full absolute paths for source and destination.

**Error Handling (changed):**
- `execute_plan()` `except OSError` blocks no longer print error details. They raise `SyncError` with the same context as before.
- `main()` catches `SyncError` and is the sole place error details are printed to the user.

### Integration Points

- `deluge_sdk.py` calls `scan_tree(d, progress=False)` — must be updated to remove the `progress` kwarg.
- `test_scanning.py` calls `scan_tree(tmp_path, progress=False)` in every test — all calls must be updated to remove the kwarg. The `TestSymlinks` test class is deleted (symlink handling removed); `TestTrashExclusion` is retained (`.trash` exclusion kept).

## Cross-Cutting Concerns

| Concern | Mitigation |
|---------|-----------|
| SD Card Safety | No changes to sync direction or write behaviour. Scan-only changes do not affect SD card safety. |
| Cross-platform compatibility | No platform-specific code is introduced or removed. `pathlib` usage is unchanged. |
| Test coverage | Removed features (symlink, `.trash`) have their test classes removed. New behaviour (skipped-file print) can be verified by inspection or a lightweight test. |

## Risk Mitigation

| Risk | Plan Mitigation | Residual Risk |
|------|-----------------|---------------|
| Simplifying `.trash` pruning block introduces bugs | The block is only losing the symlink check; `.trash` exclusion logic is unchanged. | None |
| Removing `progress=False` causes noisy test output | pytest captures stdout by default; print output is hidden unless a test fails. | None |
| Removing `--confirm` breaks user scripts/muscle memory | Passing `--confirm` will produce a clear argparse error. The new flow (always show plan, then prompt) is better UX. | Low |
| Removing error prints from `execute_plan` loses detail | All error context is already carried on `SyncError` attributes. `main()` is updated to print the same detail. | None |

## Implementation Roadmap

### Phase 1: scanning.py Cleanup

> **Goal:** Remove dead-code defences, clean up naming, and simplify the `scan_tree` interface.
> **Prerequisites:** All tests passing on current codebase.

#### Task 1.1: Remove symlink checks

- **Description:** Remove three pieces of symlink handling from `scan_tree()`: (a) the `file_path.is_symlink()` guard on files, (b) the `is_symlink()` check in the directory pruning list comprehension, and (c) the `followlinks=False` parameter from `os.walk()`.
- **Files:** `scripts/deluge_lib/scanning.py`
- **Acceptance Criteria:**
  - [x] `os.walk()` is called without `followlinks`
  - [x] No `.is_symlink()` calls remain in `scanning.py`
  - [x] Existing tests still pass (symlink test class removed in Task 1.6)

- **Implementation Notes:**
  > Removed `followlinks=False` from `os.walk()`, removed `file_path.is_symlink()` guard, removed `not Path(dir_path / d).is_symlink()` from dirnames pruning.

#### Task 1.2: Simplify directory pruning block

- **Description:** Simplify the `dirnames[:] = [...]` pruning block in `scan_tree()`. After Task 1.1 removes the symlink check from the list comprehension, the pruning simplifies to only the `.trash` check: `dirnames[:] = [d for d in dirnames if d.lower() not in _SKIP_DIRS]`. Keep the `_SKIP_DIRS` constant.
- **Files:** `scripts/deluge_lib/scanning.py`
- **Acceptance Criteria:**
  - [x] `_SKIP_DIRS` constant is retained
  - [x] The `dirnames[:] = [...]` pruning block is simplified to only the `.trash` check (no symlink logic)
  - [x] Module docstring updated to remove mention of symlinks but still mentions `.trash` exclusion

- **Implementation Notes:**
  > Pruning simplified to `dirnames[:] = [d for d in dirnames if d.lower() not in _SKIP_DIRS]`. Module docstring updated: removed "and symlinks".

#### Task 1.3: Rename dir_path to current_dir

- **Description:** In `scan_tree()`, rename the `dir_path = Path(dirpath)` variable to `current_dir` and update all references within the function.
- **Files:** `scripts/deluge_lib/scanning.py`
- **Acceptance Criteria:**
  - [x] Variable is named `current_dir` throughout `scan_tree()`
  - [x] No remaining references to `dir_path` in `scan_tree()`

- **Implementation Notes:**
  > Renamed `dir_path = Path(dirpath)` to `current_dir = Path(dirpath)` and updated all references within `scan_tree()`.

#### Task 1.4: Print message when skipping non-xml/wav files

- **Description:** In the extension-filtering block where files not in `_ALLOWED_EXTENSIONS` are skipped via `continue`, add a print statement before `continue` that shows the skipped file's path relative to `root`.
- **Files:** `scripts/deluge_lib/scanning.py`
- **Acceptance Criteria:**
  - [x] A message is printed for each skipped file (e.g. `Skipping {rel_path} (unsupported extension)`)
  - [x] The path shown is relative to `root`, not absolute

- **Implementation Notes:**
  > Added `print(f"\n  Skipping {rel} (unsupported extension)", flush=True)` before the `continue` in the extension-filtering block. Uses `file_path.relative_to(root)` for the relative path.

#### Task 1.5: Remove progress parameter and mid-scan counter

- **Description:** Two related changes: (a) Remove the `_PROGRESS_INTERVAL` constant and the `if progress and file_count % _PROGRESS_INTERVAL == 0` block inside the loop. (b) Remove the `progress` parameter from `scan_tree()`. The function always prints the "Scanning {label}..." opening line and the final "{count} files found." closing line. Update all callers: `sync_from_sd.py`, `deluge_sdk.py`, and `test_scanning.py`.
- **Files:** `scripts/deluge_lib/scanning.py`, `scripts/sync_from_sd.py`, `scripts/deluge_lib/deluge_sdk.py`, `scripts/tests/test_scanning.py`
- **Acceptance Criteria:**
  - [x] `_PROGRESS_INTERVAL` constant is removed
  - [x] Mid-scan progress block (`if progress and file_count % _PROGRESS_INTERVAL == 0`) is removed
  - [x] `progress` parameter is removed from `scan_tree()` signature and docstring
  - [x] `scan_tree()` always prints the opening and closing progress messages
  - [x] `compute_sync()` in `sync_from_sd.py` calls `scan_tree()` without `progress` kwarg
  - [x] `find_all_xml_files()` in `deluge_sdk.py` calls `scan_tree()` without `progress` kwarg
  - [x] All test calls in `test_scanning.py` updated to remove `progress=False` kwarg

- **Implementation Notes:**
  > Removed `_PROGRESS_INTERVAL` constant, `progress` parameter from signature/docstring, and all conditional `if progress:` wrappers. Updated 3 callers: `sync_from_sd.py` (removed `progress=True`), `deluge_sdk.py` (removed `progress=False`), `test_scanning.py` (removed `progress=False` from all 17 call sites).

#### Task 1.6: Remove obsolete test class

- **Description:** Remove the `TestSymlinks` test class from `test_scanning.py` since symlink handling has been removed. Keep `TestTrashExclusion` since `.trash` exclusion is retained.
- **Files:** `scripts/tests/test_scanning.py`
- **Acceptance Criteria:**
  - [x] `TestSymlinks` class is removed
  - [x] `TestTrashExclusion` class is retained
  - [x] All remaining tests pass

- **Implementation Notes:**
  > Removed `TestSymlinks` class (2 tests). `TestTrashExclusion` retained. All 52 tests pass.

### Phase 2: sync_from_sd.py Cleanup

> **Goal:** Simplify `compute_sync()`, `main()`, and `execute_plan()` in the sync script.
> **Prerequisites:** Phase 1 complete (scanning.py changes landed).

#### Task 2.1: Pre-compute src_path in compute_sync

- **Description:** In the comparison loop in `compute_sync()`, the expression `source / src_entry.rel_path` is repeated in multiple `plan.files_to_copy.append()` calls. Compute `src_path = source / src_entry.rel_path` once at the top of the loop body, alongside the existing `dst_path` computation, and replace all inline occurrences.
- **Files:** `scripts/sync_from_sd.py`
- **Acceptance Criteria:**
  - [x] `src_path` is computed once at the top of the loop
  - [x] All `source / src_entry.rel_path` expressions in the loop are replaced with `src_path`
  - [x] No behavioural change — existing tests pass

- **Implementation Notes:**
  > Added `src_path = source / src_entry.rel_path` at top of loop body alongside `dst_path`. Replaced all 3 inline occurrences with `src_path`.

#### Task 2.2: Simplify post-compute_sync flow in main

- **Description:** Restructure the post-`compute_sync()` section of `main()` to eliminate the three separate empty-plan checks and the two plan-printing paths (DRY RUN vs DRY RUN PREVIEW). The new flow: (1) if plan is empty, print "Already up to date." and return; (2) print the plan (always); (3) if `--dry-run`, print "Dry run complete." and return; (4) call `confirm_apply()`, proceed or abort. Also remove the `--confirm` flag and its mutually exclusive group from argparse. Update the module docstring.
- **Files:** `scripts/sync_from_sd.py`
- **Acceptance Criteria:**
  - [x] Only one `_plan_is_empty()` check remains
  - [x] Plan is printed exactly once via a single `print_plan()` call
  - [x] `--confirm` flag and mutually exclusive group are removed
  - [x] `--dry-run` is a simple `add_argument` (no group)
  - [x] Module docstring updated to reflect simplified behaviour
  - [x] Flow is: empty check → print plan → dry-run exit → confirm → execute

- **Implementation Notes:**
  > Removed `--confirm` flag and `add_mutually_exclusive_group()`. `--dry-run` is now a direct `parser.add_argument()`. Restructured post-`compute_sync()` flow to: (1) empty check → return, (2) print plan, (3) dry-run exit, (4) confirm → execute. Updated module docstring.

#### Task 2.3: Include full paths in confirm_apply message

- **Description:** Change the `confirm_apply()` call in `main()` to include the full absolute paths for source and destination. Currently the message says "This will overwrite DELUGE/ to match the SD card" but DELUGE is the root name in both source and destination. Use `sd_path` and `deluge_root` variables which are already in scope.
- **Files:** `scripts/sync_from_sd.py`
- **Acceptance Criteria:**
  - [x] Confirmation message includes the actual source path (SD card)
  - [x] Confirmation message includes the actual destination path (DELUGE/ directory)
  - [x] No ambiguity about which directories are involved

- **Implementation Notes:**
  > Confirmation message now uses f-string with `{deluge_root}` and `{sd_path}` variables: `"This will overwrite {deluge_root} to match {sd_path}. Continue?"`

#### Task 2.4: Clean up duplicate error output in execute_plan

- **Description:** Remove the `print()` statements from the two `except OSError` blocks in `execute_plan()` (one in the copy loop, one in the trash loop). The `SyncError` exceptions already carry all the context. Update the `main()` `except SyncError` handler to print the error details that were previously printed inside `execute_plan()`: the failed file path, the error message, and progress counts.
- **Files:** `scripts/sync_from_sd.py`
- **Acceptance Criteria:**
  - [x] No `print()` calls remain inside `except OSError` blocks in `execute_plan()`
  - [x] `SyncError` is still raised with the same context fields
  - [x] `main()` `except SyncError` block prints: failed file path, error message, and copies/remaining counts
  - [x] Error output appears exactly once per failure (not duplicated)

- **Implementation Notes:**
  > Removed 7 `print()` calls from the two `except OSError` blocks in `execute_plan()`. Updated `main()`'s `except SyncError` handler to print: file path (`exc.file`), error message (`exc`), and progress counts (`exc.copied` copied, `exc.remaining` remaining).

#### Task 2.5: Update README.md to remove --confirm documentation

- **Description:** Update `README.md` line 68 which documents the `--confirm` flag. Since Task 2.2 removes `--confirm` from the CLI, the README usage examples must be updated to remove that line.
- **Files:** `README.md`
- **Acceptance Criteria:**
  - [x] The `uv run sync_from_sd.py --confirm` usage line is removed from `README.md`
  - [x] The comment for the default usage reflects the new flow (preview then prompt)
  - [x] No other `--confirm` references remain in `README.md`

- **Implementation Notes:**
  > Removed the `--confirm` usage line from the code block in README.md.

#### Task 2.6: Update standards to replace --confirm references with interactive prompt

- **Description:** Update two agent-system files that reference `--confirm` by name: (a) `agent-system/standards/project.md` line 18 currently says `a --confirm flag or interactive prompt` — simplify to `an interactive prompt`; (b) `agent-system/skills/feature-implementation/standards/implementation-process.md` line 142 currently says `a --confirm flag or interactive prompt` — simplify to `an interactive prompt`.
- **Files:** `agent-system/standards/project.md`, `agent-system/skills/feature-implementation/standards/implementation-process.md`
- **Acceptance Criteria:**
  - [x] `project.md` line 18 says "an interactive prompt" instead of "a `--confirm` flag or interactive prompt"
  - [x] `implementation-process.md` line 142 says "an interactive prompt" instead of "a `--confirm` flag or interactive prompt"
  - [x] No other meaning is changed in either file

- **Implementation Notes:**
  > Updated both files. `project.md` rule 4 now reads "...require explicit user confirmation (e.g. an interactive prompt)". `implementation-process.md` now reads "writes require an interactive prompt".

## Progress Tracker

| Phase | Status | Tasks Complete | Notes |
|-------|--------|---------------|-------|
| Phase 1: scanning.py Cleanup | Complete | 6/6 | All 52 tests pass |
| Phase 2: sync_from_sd.py Cleanup | Complete | 6/6 | All 52 tests pass |

## Open Questions

None — all items are well-defined with clear scope.

## References

### Predecessor Plan
- [sync-from-sd-simplification-plan.md](sync-from-sd-simplification-plan.md) — Round 1 simplification (complete)

### Standards Applied
- [project.md](../../agent-system/standards/project.md) — SD Card safety and platform requirements

### Project Files
- [scripts/deluge_lib/scanning.py](../../scripts/deluge_lib/scanning.py) — Primary target (items 1–6)
- [scripts/sync_from_sd.py](../../scripts/sync_from_sd.py) — Secondary target (items 7–10)
- [scripts/deluge_lib/deluge_sdk.py](../../scripts/deluge_lib/deluge_sdk.py) — Caller update (item 5)
- [scripts/tests/test_scanning.py](../../scripts/tests/test_scanning.py) — Test updates (items 1, 2, 5)
- [README.md](../../README.md) — Documentation update (item 11)
- [agent-system/standards/project.md](../../agent-system/standards/project.md) — Standards wording update (item 12)
- [agent-system/skills/feature-implementation/standards/implementation-process.md](../../agent-system/skills/feature-implementation/standards/implementation-process.md) — Standards wording update (item 12)

## Change Log

| Date | Change | Reason |
|------|--------|--------|
| 10 April 2026 | Initial plan created | Code review findings formatted into implementation plan |
| 10 April 2026 | Revision 1: Keep `.trash` exclusion | `scan_tree` scans both source and dest — removing exclusion would cause recursive `.trash` nesting on every sync. Task 1.2 changed to simplify pruning block (keep `.trash`, remove symlink check). D2 reversed. Risk row updated. Task 1.6 now only removes `TestSymlinks`. |
| 10 April 2026 | Revision 2: Add README.md update (Task 2.5) | `README.md` documents `--confirm` which is removed by Task 2.2 |
| 10 April 2026 | Revision 3: Add standards wording update (Task 2.6) | `project.md` and `implementation-process.md` reference `--confirm` — updated to say "interactive prompt" |
| 10 April 2026 | Phase 2 implemented (Tasks 2.1–2.6) | All 6 tasks complete, 52 tests pass, plan status set to Complete |
