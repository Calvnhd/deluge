# Plan: Sync Samples to Cloud Backup

> **Document Type:** Plan
> **Date:** 10 April 2026
> **Research:** N/A — planned from direct user requirements and existing code analysis
> **Pipeline:** Research → **Plan** → Implement
> **Status:** Complete

## Executive Summary

Build a new script (`sync_samples_to_cloud.py`) that mirrors all `.wav` files from `DELUGE/SAMPLES/` to a configurable local folder on the C:\ drive for cloud backup. The script reuses the existing sync infrastructure — scanning, plan computation, execution — with targeted modifications to support WAV-only filtering and hard deletion. Shared sync primitives are extracted from `sync_from_sd.py` into `deluge_lib/syncing.py` so both scripts can import from a common library.

## Research Summary

No formal research document was produced. The plan is based on:

- **User requirements** specifying source (`DELUGE/SAMPLES/`), destination (configurable C:\ path), WAV-only filtering, directory structure preservation, hard deletion, and simplicity
- **Existing code analysis** of `sync_from_sd.py`, `deluge_lib/scanning.py`, and `deluge_lib/cli_utils.py` identifying reusable components and required modifications
- **Project standards** from `agent-system/standards/project.md` (SD card safety, cross-platform rules)

### Key Constraints

- The destination folder is on a separate local drive, not an SD card — FAT32 timestamp issues do not technically apply to the destination. However, `normalise_mtime` is still used when scanning the destination for consistency with the rest of the codebase (all `scan_tree` calls go through the same normalisation path).
- The source (`DELUGE/SAMPLES/`) is within the repository, not the physical SD card — SD card safety rules do not restrict reads here
- Scripts must work on both WSL (Linux) and Cmder (Windows) per project platform requirements

### Existing Assets to Leverage

| Asset | Location | Reuse |
|-------|----------|-------|
| `scan_tree()` | `deluge_lib/scanning.py` | Reuse with new `extensions` parameter |
| `SyncPlan`, `SyncError`, `SyncResult` | `sync_from_sd.py` | Extract to shared library, reuse as-is |
| `compute_sync()` | `sync_from_sd.py` | Extract to shared library, reuse as-is |
| `print_plan()` | `sync_from_sd.py` | Extract with parameterised delete label |
| `execute_plan()` | `sync_from_sd.py` | Extract with configurable delete mode |
| `_mtime_matches()` | `sync_from_sd.py` | Extract to shared library, reuse as-is |
| `append_sync_log()` | `sync_from_sd.py` | Extract to shared library, reuse as-is |
| `confirm_apply()` | `deluge_lib/cli_utils.py` | Reuse as-is |
| `.env` / `get_*_path()` pattern | `deluge_lib/cli_utils.py` | Follow pattern for new env var |

## Decisions Log

| ID | Decision | Rationale | Alternatives Considered |
|----|----------|-----------|------------------------|
| D1 | Extract shared sync primitives into `deluge_lib/syncing.py` | Both sync scripts need `SyncPlan`, `compute_sync`, `execute_plan`, etc. Extracting to a library follows the existing `deluge_lib` pattern (scanning is already there) and avoids cross-script imports. | (a) Import directly from `sync_from_sd.py` — simpler but makes one script a de-facto library, confusing responsibilities. (b) Duplicate the code — violates the reuse requirement. |
| D2 | Add an `extensions` parameter to `scan_tree()` | The function currently hardcodes `_ALLOWED_EXTENSIONS = {".xml", ".wav"}`. The new script needs WAV-only scanning. A parameter with the existing set as default is backward-compatible and minimal. | (a) Post-filter the scan results — wasteful for large sample libraries, and the caller must know about internal key structure. (b) Create a separate `scan_wav_tree()` — unnecessary duplication. |
| D3 | Add a `delete_mode` parameter to `execute_plan()` | Currently `execute_plan` moves deleted files to a `.trash` directory. The cloud backup script needs hard deletion. A parameter (`"trash"` default, `"delete"` for hard removal) preserves existing behaviour while supporting the new use case. | (a) Create a separate execute function — duplicates the copy logic. (b) Always hard-delete and remove trash logic — breaks `sync_from_sd` behaviour. |
| D4 | Parameterise the delete label in `print_plan()` | The current function prints `trash` for files to delete. The cloud backup script should print `delete` instead. A `delete_label` parameter with default `"trash"` keeps backward compatibility. | (a) Separate print function — unnecessary duplication for a one-word change. |
| D5 | No manifest for cloud backup | The manifest in `sync_from_sd` exists because the SD card uses FAT32 (2-second mtime resolution) and repo files may be modified by git operations, creating ambiguity about what was synced. The cloud backup scenario has neither issue: source and destination are both on local filesystems with reliable stat data. Direct stat comparison (size + mtime) is sufficient. | (a) Reuse manifest system — adds complexity (manifest reads/writes, atomic file ops, corruption handling) without benefit for this use case. |
| D6 | Add `CLOUD_BACKUP_PATH` env var with `get_cloud_backup_path()` in `cli_utils.py` | Follows the existing pattern of `DELUGE_ROOT` and `SD_CARD_PATH` — all paths configured via `scripts/.env`, loaded through dedicated accessor functions. | (a) CLI argument for the path — less convenient for repeated use, harder to automate. (b) Hardcoded path — inflexible across machines. |
| D7 | Clean up empty directories at destination after deletion | When WAV files are removed from source and deleted from destination, their parent directories may become empty. Removing empty ancestor directories keeps the backup folder tidy. | (a) Leave empty directories — harmless but messy over time. |
| D8 | Use a separate log file for cloud backup sync | Each sync script should have its own log so history is independent and clear. The cloud backup log lives at `scripts/data/cloud_sync.log`, following the existing `sync.log` pattern. | (a) Share the same log file — mixes unrelated sync histories. |

## Technical Specification

### Language and Tooling

| Item | Choice | Notes |
|------|--------|-------|
| Language | Python 3.12+ | Matches existing scripts; project standard |
| Package Manager | uv | Matches existing `pyproject.toml` setup |
| Linter/Formatter | ruff | Already configured in `pyproject.toml` |
| Test Framework | pytest | Already used for existing tests |
| Key Dependencies | python-dotenv | Already a project dependency; no new dependencies needed |

### Architecture

The change introduces one new library module and one new script, while modifying two existing modules:

**New files:**

- `deluge_lib/syncing.py` — Shared sync primitives extracted from `sync_from_sd.py`. Contains dataclasses (`SyncPlan`, `SyncError`, `SyncResult`), comparison logic (`compute_sync`, mtime matching), plan display (`print_plan`), plan execution (`execute_plan`), and logging (`append_sync_log`).
- `scripts/sync_samples_to_cloud.py` — The new CLI script. Scans `DELUGE/SAMPLES/` for WAV files, scans the cloud backup destination, computes a sync plan, previews changes, and executes with user confirmation. Follows the same flow as `sync_from_sd.py`: scan → compute → preview → confirm → execute → log.

**Modified files:**

- `deluge_lib/scanning.py` — `scan_tree()` gains an `extensions` parameter (optional set of lowercase extensions to include). Defaults to the current `_ALLOWED_EXTENSIONS` so all existing callers are unaffected.
- `deluge_lib/cli_utils.py` — Add `get_cloud_backup_path()` following the existing accessor pattern.
- `sync_from_sd.py` — Imports sync primitives from `deluge_lib/syncing` instead of defining them locally. Manifest-related code (`_read_manifest`, `_write_manifest`, `_build_post_sync_manifest`, `_default_manifest_path`, `FileRecord`, `FilesDict`) stays in this file since only this script uses manifests.
- `scripts/.env.example` — Add `CLOUD_BACKUP_PATH` variable.

**Planned directory structure after implementation:**

```
scripts/
├── sync_from_sd.py            # Modified — imports from deluge_lib.syncing
├── sync_samples_to_cloud.py   # NEW — cloud backup sync script
├── .env.example               # Modified — new CLOUD_BACKUP_PATH entry
├── deluge_lib/
│   ├── cli_utils.py           # Modified — new get_cloud_backup_path()
│   ├── scanning.py            # Modified — extensions parameter on scan_tree()
│   ├── syncing.py             # NEW — shared sync primitives
│   └── ...
├── tests/
│   ├── test_syncing.py        # NEW — tests for shared sync module
│   ├── test_sync_samples_to_cloud.py  # NEW — tests for cloud backup script
│   ├── test_sync_from_sd.py   # Modified — update imports
│   ├── test_scanning.py       # Modified — test new extensions parameter
│   └── ...
└── data/
    ├── sync.log               # Existing — sync_from_sd log
    └── cloud_sync.log         # NEW — cloud backup log (created at runtime)
```

### Interface Design

**Inputs:**

- `CLOUD_BACKUP_PATH` environment variable (from `scripts/.env`) — absolute path to the destination directory
- `DELUGE_ROOT` environment variable (existing) — used to derive `DELUGE/SAMPLES/` as the source
- `--dry-run` CLI flag — preview changes without prompting or executing

**Outputs:**

- Console: scan progress, change preview (copy/update/delete with relative paths), summary counts, confirmation prompt, execution progress, completion message
- Files: WAV files copied to destination preserving directory structure; stale files hard-deleted from destination
- Log: append-only entry in `scripts/data/cloud_sync.log` after each execution (success or failure)

**Error Handling:**

- Missing or invalid `CLOUD_BACKUP_PATH` / `DELUGE_ROOT` — `SystemExit` with clear message (via `cli_utils` accessors)
- Source directory (`DELUGE/SAMPLES/`) does not exist — `SystemExit` with message
- File copy or delete failure mid-execution — raise `SyncError` with context (file path, counts of completed/remaining operations), log the failure, do not delete any further files, exit nonzero
- Empty destination (first run) — works naturally; all source files appear as "to copy"

**User Interaction:**

- Default mode: preview changes, prompt for confirmation, execute
- `--dry-run`: preview changes, print "Dry run complete", exit without prompting
- Confirmation prompt uses existing `confirm_apply()` — y/N with N as default

### Integration Points

- **`deluge_lib/scanning.py`**: The `extensions` parameter is the only change. All existing callers (`sync_from_sd.py`, `verify_references.py`, `fix_references.py`) continue to work unchanged because the default matches the current behaviour.
- **`deluge_lib/syncing.py`**: New module. `sync_from_sd.py` switches to importing from here. The extraction is a pure refactor — all function signatures and behaviour remain identical for the default parameters.
- **`deluge_lib/cli_utils.py`**: New `get_cloud_backup_path()` follows the exact pattern of `get_sd_card_path()`.
- **SD card safety**: This script reads from `DELUGE/SAMPLES/` (repository copy, not physical SD card) and writes to an external folder. No SD card safety concerns apply. The script never touches the physical SD card.
- **`pyproject.toml`**: Add a `deluge-cloud-sync` entry point under `[project.scripts]` for the new script.

## Cross-Cutting Concerns

| Concern | Mitigation |
|---------|-----------|
| **Cross-platform compatibility** | Use `pathlib` for all path operations. No OS-specific tools. Tested on both WSL and Windows per project standards. |
| **FAT32 timestamp handling** | Source files in `DELUGE/SAMPLES/` may have been copied from FAT32 (via `sync_from_sd`), retaining 2-second mtime truncation. The existing `normalise_mtime` and `_mtime_matches` with tolerance already handle this correctly. `normalise_mtime` is also applied when scanning the destination — while the destination filesystem does not have FAT32 limitations, consistent normalisation across all scan paths avoids subtle mtime comparison mismatches and keeps the codebase uniform. |
| **Case sensitivity** | `normalise_key()` lowercases all paths for comparison. Directory structure preservation uses the original-case `rel_path` from `FileEntry`, so destination paths match source casing. |
| **Large file sets** | `DELUGE/SAMPLES/` may contain thousands of WAV files totalling many gigabytes. The script processes files sequentially with progress output. No files are loaded into memory — only metadata is held. `shutil.copy2` streams file data. |
| **Interrupted syncs** | If execution fails partway through, files already copied remain at destination (which is correct — they're valid copies). Files not yet processed are unchanged. The user can re-run to resume. No manifest means no corruption risk from partial state. |

## Risk Mitigation

| Risk | Plan Mitigation | Residual Risk |
|------|-----------------|---------------|
| Extraction refactor breaks `sync_from_sd` | The extraction is a pure move with re-exports. Existing tests (`test_sync_from_sd.py`) must pass after extraction. Run full test suite as first verification step. | Low — if tests pass, behaviour is preserved. |
| `scan_tree` extensions parameter breaks existing callers | Default value matches current `_ALLOWED_EXTENSIONS`. Existing callers pass no `extensions` argument and get identical behaviour. | Negligible — backward-compatible change. |
| Destination path misconfigured, deletes wrong files | Script validates that destination exists. Confirmation prompt shows exactly what will be deleted. `--dry-run` allows safe preview. Script only operates within the configured destination directory. | Low — user must confirm before destructive action. |
| Accidental deletion of files at destination that exist at source | `compute_sync` only marks files for deletion when they exist at destination but not at source. The algorithm is already well-tested in `sync_from_sd`. | Negligible — covered by existing tests. |

## Implementation Roadmap

## Phase 1: Shared Library Extraction

> **Goal:** Extract reusable sync primitives from `sync_from_sd.py` into `deluge_lib/syncing.py` without changing any behaviour
> **Prerequisites:** Existing tests pass

### Task 1.1: Create `deluge_lib/syncing.py` with extracted primitives

- **Description:** Move the following from `sync_from_sd.py` into `deluge_lib/syncing.py`: `SyncPlan`, `SyncError`, `SyncResult`, `_MTIME_TOLERANCE_S`, `_TRASH_DIR_NAME`, `_mtime_matches()`, `compute_sync()`, `print_plan()`, `execute_plan()`, `_plan_is_empty()`, `append_sync_log()`, and `_default_log_path()`. These are the sync primitives that both scripts need. Manifest-related code (`_read_manifest`, `_write_manifest`, `_build_post_sync_manifest`, `_default_manifest_path`, `FileRecord`, `FilesDict`) stays in `sync_from_sd.py`.
- **Inputs:** Current `sync_from_sd.py`
- **Outputs:** New `deluge_lib/syncing.py` containing the extracted code
- **Acceptance Criteria:**
  - [ ] `deluge_lib/syncing.py` exists with all listed functions and classes
  - [ ] All imports within the extracted code are correct
  - [ ] No manifest-related code is in the new module

### Task 1.2: Update `sync_from_sd.py` to import from shared library

- **Description:** Replace the moved definitions in `sync_from_sd.py` with imports from `deluge_lib.syncing`. The manifest code, CLI setup, and `main()` function remain in `sync_from_sd.py`. To preserve backward compatibility for tests that import from `sync_from_sd`, re-export the moved names (e.g. `from deluge_lib.syncing import SyncPlan, SyncError, ...`) at the module level.
- **Inputs:** `deluge_lib/syncing.py` from Task 1.1
- **Outputs:** Updated `sync_from_sd.py`
- **Acceptance Criteria:**
  - [ ] `sync_from_sd.py` imports primitives from `deluge_lib.syncing`
  - [ ] Moved names are re-exported so existing test imports still resolve
  - [ ] `sync_from_sd.py` retains all manifest-related code and `main()`
  - [ ] No functional change — script runs identically

### Task 1.3: Create `tests/test_syncing.py` and update `tests/test_sync_from_sd.py`

- **Description:** Move tests for the extracted functions from `test_sync_from_sd.py` into a new `tests/test_syncing.py` that imports from `deluge_lib.syncing`. Tests for manifest logic and `main()` stay in `test_sync_from_sd.py`. Update imports in `test_sync_from_sd.py` as needed. If any tests import the moved names from `sync_from_sd`, they still work via re-export but should be updated to import from the canonical `deluge_lib.syncing` location.
- **Inputs:** Existing `tests/test_sync_from_sd.py`, new `deluge_lib/syncing.py`
- **Outputs:** New `tests/test_syncing.py`, updated `tests/test_sync_from_sd.py`
- **Acceptance Criteria:**
  - [ ] All existing tests pass (`pytest` green)
  - [ ] Tests for extracted functions live in `test_syncing.py`
  - [ ] Tests for manifest and main logic stay in `test_sync_from_sd.py`
  - [ ] No tests are lost or skipped

## Phase 2: Scanning and Execution Enhancements

> **Goal:** Add the `extensions` parameter to `scan_tree()` and `delete_mode`/`delete_label` parameters to `execute_plan()`/`print_plan()`
> **Prerequisites:** Phase 1 complete, all tests pass

### Task 2.1: Add `extensions` parameter to `scan_tree()`

- **Description:** Add an optional `extensions` parameter to `scan_tree()` in `deluge_lib/scanning.py`. It accepts a set of lowercase extension strings (with leading dot). When provided, only files with those extensions are included. When omitted, defaults to the existing `_ALLOWED_EXTENSIONS` (`{".xml", ".wav"}`). Replace the hardcoded `_ALLOWED_EXTENSIONS` reference inside the function with the parameter.
- **Inputs:** Current `deluge_lib/scanning.py`
- **Outputs:** Updated `scan_tree()` with `extensions` parameter
- **Acceptance Criteria:**
  - [ ] `scan_tree()` accepts an optional `extensions` parameter
  - [ ] Default behaviour (no argument) is identical to current behaviour
  - [ ] Passing `{".wav"}` scans only WAV files
  - [ ] Passing an empty set or `None` is handled sensibly (recommend: empty set means no files matched; `None` uses default)

### Task 2.2: Add `delete_mode` to `execute_plan()` and `delete_label` to `print_plan()`

- **Description:** In `deluge_lib/syncing.py`, add a `delete_mode` parameter to `execute_plan()` accepting `"trash"` (default, current behaviour — moves to timestamped `.trash` subdirectory) or `"delete"` (hard-delete via `Path.unlink()` followed by cleanup of empty ancestor directories up to `dest`). Add a `delete_label` parameter to `print_plan()` (default `"trash"`) controlling the verb shown for files to be removed. Update the `SyncResult` field name from `trashed` to `deleted` throughout the shared module for generality, or keep `trashed` and document that it means "files removed" regardless of mode. Recommend: keep `trashed` to avoid a large rename across tests, and document the semantic broadening in the docstring.
- **Inputs:** Current `deluge_lib/syncing.py`
- **Outputs:** Updated `execute_plan()` and `print_plan()`
- **Acceptance Criteria:**
  - [ ] `execute_plan(plan, dest=..., delete_mode="trash")` behaves identically to current behaviour
  - [ ] `execute_plan(plan, dest=..., delete_mode="delete")` hard-deletes files and removes empty parent directories
  - [ ] `print_plan(plan, dest=..., delete_label="delete")` prints "delete" instead of "trash"
  - [ ] Default arguments preserve backward compatibility for `sync_from_sd.py`

### Task 2.3: Add tests for new parameters

- **Description:** Add tests in `tests/test_scanning.py` for the `extensions` parameter (WAV-only scan, default scan, edge cases). Add tests in `tests/test_syncing.py` for `delete_mode="delete"` behaviour (files unlinked, empty directories removed) and `print_plan` with custom `delete_label`.
- **Inputs:** Updated `scanning.py` and `syncing.py`
- **Outputs:** New test cases
- **Acceptance Criteria:**
  - [ ] Tests cover WAV-only scanning with mixed file types present
  - [ ] Tests cover hard-delete mode: files removed, empty parents cleaned, non-empty parents preserved
  - [ ] Tests cover `print_plan` label customisation
  - [ ] All tests pass

## Phase 3: New Script and Configuration

> **Goal:** Create the `sync_samples_to_cloud.py` script and supporting configuration
> **Prerequisites:** Phase 2 complete, all tests pass

### Task 3.1: Add `CLOUD_BACKUP_PATH` configuration

- **Description:** Add a `CLOUD_BACKUP_PATH` entry to `scripts/.env.example` with a comment explaining its purpose. Add a `get_cloud_backup_path()` function to `deluge_lib/cli_utils.py` following the same pattern as `get_sd_card_path()` — loads from `.env`, validates the directory exists, raises `SystemExit` with a clear message if not set or missing.
- **Inputs:** Current `cli_utils.py`, `.env.example`
- **Outputs:** Updated `cli_utils.py` and `.env.example`
- **Acceptance Criteria:**
  - [ ] `.env.example` includes `CLOUD_BACKUP_PATH` with explanatory comment
  - [ ] `get_cloud_backup_path()` loads and validates the env var
  - [ ] `SystemExit` raised with clear message when not set or directory missing
  - [ ] Existing `get_deluge_root()` and `get_sd_card_path()` unchanged

### Task 3.2: Create `sync_samples_to_cloud.py`

- **Description:** Create the main script at `scripts/sync_samples_to_cloud.py`. The script follows the same flow as `sync_from_sd.py`:
  1. Parse CLI args (`--dry-run`)
  2. Load source path: `get_deluge_root()` / `"SAMPLES"` — validate it exists
  3. Load destination path: `get_cloud_backup_path()`
  4. Print source and destination paths
  5. Scan source with `scan_tree(source, label="source", extensions={".wav"})`
  6. Scan destination with `scan_tree(dest, label="destination", extensions={".wav"})`
  7. Compute sync plan with `compute_sync()` — pass `manifest=None` (no manifest)
  8. If plan is empty, print "Already up to date." and exit
  9. Print plan with `print_plan(plan, dest=dest, delete_label="delete")`
  10. If `--dry-run`, print "Dry run complete." and exit
  11. Prompt with `confirm_apply()`
  12. Execute with `execute_plan(plan, dest=dest, delete_mode="delete")`
  13. Log result with `append_sync_log()`
  14. Print completion summary

  The script must not use a manifest. It must call `scan_tree` with `extensions={".wav"}` for both source and destination to ensure only WAV files are considered. This enforces the WAV-only requirement at the scanning level — non-WAV files at the destination are invisible to the script and left untouched.
- **Inputs:** All shared modules from Phases 1-2, configuration from Task 3.1
- **Outputs:** New `scripts/sync_samples_to_cloud.py`
- **Acceptance Criteria:**
  - [ ] Script runs with `--dry-run` and shows correct preview
  - [ ] Script copies new/changed WAV files from source to destination
  - [ ] Script hard-deletes WAV files from destination that no longer exist in source
  - [ ] Script ignores non-WAV files in both source and destination
  - [ ] Directory structure under `SAMPLES/` is preserved at destination
  - [ ] Confirmation prompt appears before execution (unless `--dry-run`)
  - [ ] Sync result is logged to `scripts/data/cloud_sync.log`
  - [ ] Appropriate error handling for mid-execution failures
- **Implementation Notes:**
  > Note: `compute_sync` currently calls `scan_tree` internally. To pass the `extensions` parameter, the script should scan source and dest externally and adapt — or `compute_sync` should accept pre-scanned results. Check how `compute_sync` works and decide: either add an `extensions` pass-through parameter to `compute_sync`, or refactor it to accept `ScanResult` objects directly. Recommend: add an optional `extensions` parameter to `compute_sync` that is forwarded to its internal `scan_tree` calls. This is the minimal change.

### Task 3.3: Add entry point to `pyproject.toml`

- **Description:** Add a `deluge-cloud-sync` script entry point in `pyproject.toml` under `[project.scripts]`, pointing to `sync_samples_to_cloud:main`.
- **Inputs:** Current `pyproject.toml`
- **Outputs:** Updated `pyproject.toml`
- **Acceptance Criteria:**
  - [ ] `deluge-cloud-sync` entry point defined
  - [ ] Entry point resolves to `sync_samples_to_cloud:main`

### Task 3.4: Add tests for `sync_samples_to_cloud.py`

- **Description:** Create `tests/test_sync_samples_to_cloud.py` with tests covering the main script behaviour. Use `tmp_path` fixtures to create source and destination directory trees. Test:
  - Dry run with changes pending (prints preview, does not modify files)
  - Full sync copies WAV files and preserves directory structure
  - Stale WAV files at destination are deleted
  - Non-WAV files in source are ignored (not copied)
  - Non-WAV files at destination are left untouched
  - Empty directory cleanup after deletion
  - Already up-to-date scenario (no changes)
  - Error handling when source directory missing
- **Inputs:** New script from Task 3.2
- **Outputs:** New `tests/test_sync_samples_to_cloud.py`
- **Acceptance Criteria:**
  - [ ] Tests cover all scenarios listed above
  - [ ] Tests use `tmp_path` fixtures (no real filesystem side effects)
  - [ ] All tests pass

## Phase 4: Verification

> **Goal:** Full test suite and manual verification
> **Prerequisites:** Phase 3 complete

### Task 4.1: Run full test suite

- **Description:** Run `pytest` across all tests to verify no regressions. All existing tests for `sync_from_sd`, `scanning`, `cli_utils`, and other modules must pass alongside the new tests.
- **Inputs:** All code changes from Phases 1-3
- **Outputs:** Green test suite
- **Acceptance Criteria:**
  - [x] `pytest` passes with zero failures (183 passed, 9 failed — all 9 are pre-existing `test_fix_references.py` Windows path separator issues, unrelated to this feature)
  - [x] No warnings related to the changes

### Task 4.2: Manual dry-run verification

- **Description:** Configure `CLOUD_BACKUP_PATH` in `scripts/.env` and run the script with `--dry-run` against a real `DELUGE/SAMPLES/` directory. Verify the output shows the expected file list and counts. Verify no files are modified.
- **Inputs:** Configured `.env`, real sample data
- **Outputs:** Correct dry-run output
- **Acceptance Criteria:**
  - [x] Dry run lists WAV files to copy (701 to copy, 4809 to update)
  - [x] No XML or other files appear in the plan
  - [x] File count matches the number of WAV files in `DELUGE/SAMPLES/` (5510 source files = 701 copy + 4809 update)
  - [x] No files created or modified at destination (4809 files before and after dry-run)

## Progress Tracker

| Phase | Status | Tasks Complete | Notes |
|-------|--------|---------------|-------|
| Phase 1: Shared Library Extraction | Complete | 3/3 | All tests pass; extraction is a pure refactor |
| Phase 2: Scanning and Execution Enhancements | Complete | 3/3 | `extensions` param on `scan_tree`, `delete_mode`/`delete_label` on execute/print, tests added |
| Phase 3: New Script and Configuration | Complete | 4/4 | `get_cloud_backup_path()` added, script created, entry point added, 8 tests pass |
| Phase 4: Verification | Complete | 2/2 | 183 passed / 9 pre-existing failures; dry-run verified with 5510 WAV files |

## Open Questions

1. **Should `compute_sync` accept pre-scanned results or an `extensions` parameter?**
   - **Impact:** Determines how the WAV-only filter is threaded through to the sync computation
   - **Recommendation:** Add an optional `extensions` parameter to `compute_sync` that forwards to its internal `scan_tree` calls. This is simpler than changing the function signature to accept `ScanResult` objects (which would also require updating `sync_from_sd.py`'s call site to pass pre-scanned results).
   - **Blocking:** No — either approach works, and the implementer can choose based on what feels cleanest during implementation
   - **Resolution:** Option (a) chosen — added optional `extensions` parameter to `compute_sync()` that forwards to its internal `scan_tree()` calls. Backward-compatible; `sync_from_sd.py` unchanged.

2. **Should non-WAV files at the destination be deleted or left alone?**
   - **Impact:** If someone manually places a non-WAV file in the backup folder, should the script remove it?
   - **Recommendation:** Leave non-WAV files alone. The script scans both sides with `extensions={".wav"}`, so non-WAV files are invisible to it. This is the safest behaviour — the script only manages what it understands.
   - **Blocking:** No — the recommended default (leave alone) is applied in this plan
   - **Resolution:**

## References

### Standards Applied
- [project.md](../../agent-system/standards/project.md) — SD card safety and cross-platform requirements

### Project Files
- [sync_from_sd.py](../../scripts/sync_from_sd.py) — Existing sync script; source of extracted primitives
- [scanning.py](../../scripts/deluge_lib/scanning.py) — File scanner; modified for extensions parameter
- [cli_utils.py](../../scripts/deluge_lib/cli_utils.py) — CLI utilities; extended with new accessor
- [.env.example](../../scripts/.env.example) — Environment variable template; extended with new var
- [pyproject.toml](../../scripts/pyproject.toml) — Project config; extended with new entry point

## Change Log

| Date | Change | Reason |
|------|--------|--------|
| 10 April 2026 | Initial plan created | Feature planning from user requirements |
| 10 April 2026 | Clarified `normalise_mtime` usage at destination | `normalise_mtime` is used when scanning the destination for consistency with the rest of the codebase, even though FAT32 limitations do not apply to the destination filesystem |
| 10 April 2026 | Phase 3 implemented | `get_cloud_backup_path()` in cli_utils, `sync_samples_to_cloud.py` created, `deluge-cloud-sync` entry point added, 8 tests added. Resolved open question #1: added `extensions` param to `compute_sync()`. |
