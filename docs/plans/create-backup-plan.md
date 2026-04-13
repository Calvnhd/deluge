# Plan: Create .zip Backup Script

> **Document Type:** Plan
> **Date:** 13 April 2026
> **Research:** [new-scripts-research.md](../research/new-scripts-research.md)
> **Pipeline:** Research → **Plan** → Implement
> **Status:** Complete

## Executive Summary

Create `scripts/create_backup.py` — a script that produces timestamped `.zip` archives of the SD card (or repo `DELUGE/`) as a last-resort backup. The script uses `scan_tree()` for file filtering (XML + WAV only) and Python's stdlib `zipfile` for compression. Two new `.env` variables (`ZIP_SOURCE_PATH`, `ZIP_DEST_PATH`) and two new `cli_utils` getters are the only shared-code changes. No new dependencies required.

## Research Summary

- **Recommended approach:** `zipfile` stdlib + `scan_tree()` (Research §Approaches Considered — Approach A)
- **Key constraint:** Script must never modify the source directory (Research §5.1)
- **Existing assets:** `scan_tree(root, file_filter="both")` provides exactly the needed file list with `.trash` exclusion; `cli_utils.py` provides the pattern for env var loaders (Research §2, §4)
- **Cross-platform:** Use `PurePosixPath` for zip archive entry names to ensure forward slashes on Windows (Research §7.1)

## Decisions Log

| ID | Decision | Rationale | Alternatives Considered |
|----|----------|-----------|------------------------|
| D1 | Use `scan_tree(source, file_filter="both")` for file discovery | Battle-tested scanner already filters XML+WAV and excludes `.trash`; no custom logic needed | Manual `os.walk()` with extension filtering |
| D2 | `ZIP_DEFLATED` compression for all files | WAV (PCM) and XML both benefit from deflate compression; `zlib` ships with CPython | `ZIP_STORED` (no compression — larger archives) |
| D3 | Archive name: `DELUGE-backup-YYYY-MM-DD_HHMMSS.zip` | Timestamp gives uniqueness and chronological sorting; matches research §8.1 | Include source indicator in name (deferred — timestamp is sufficient) |
| D4 | Archive root is source directory contents (no wrapping `DELUGE/` folder) | Matches SD card structure — contents of source become root of zip (Research §8.2) | Wrap in `DELUGE/` parent directory |
| D5 | Support `--dry-run` flag | Matches codebase convention; lets user preview file count and estimated size before creating a large archive (Research OQ1) | No dry-run (inconsistent with other scripts) |
| D6 | Print per-file progress counter during archiving | Archive may contain ~5,500 files; without progress the script appears hung (Research OQ3) | Silent archiving |
| D7 | Verify archive with `ZipFile.testzip()` after creation | Single method call that confirms archive integrity; fast relative to creation time (Research OQ4) | Skip verification |
| D8 | No confirmation prompt (unlike sync scripts) | This script is read-only on source and creates a new file at dest; no destructive operations to gate | Add `confirm_apply()` prompt |

## Technical Specification

### Language and Tooling

| Item | Choice | Notes |
|------|--------|-------|
| Language | Python 3.12+ | Matches existing scripts |
| Key Dependencies | `zipfile` (stdlib), `deluge_lib` | No new packages |
| Test Framework | pytest | Existing convention |
| Linter | ruff | Existing convention |

### Architecture

A single script (`create_backup.py`) that consumes `scan_tree()` and two new `cli_utils` getters. No new modules or abstractions. The flow is linear: load config → scan source → create zip → verify → print summary.

### File and Directory Structure

```
scripts/
├── create_backup.py          # NEW — main script
├── deluge_lib/
│   └── cli_utils.py          # MODIFIED — add get_zip_source_path(), get_zip_dest_path()
├── tests/
│   └── test_create_backup.py # NEW — tests
├── pyproject.toml             # MODIFIED — add deluge-backup entry point
└── .env.example               # MODIFIED — add ZIP_SOURCE_PATH, ZIP_DEST_PATH
```

### Interface Design

**Inputs:**
- `ZIP_SOURCE_PATH` — directory to archive (from `.env`)
- `ZIP_DEST_PATH` — directory where zip file is saved (from `.env`)
- `--dry-run` CLI flag — preview only, no zip created

**Outputs:**
- Zip file at `ZIP_DEST_PATH/DELUGE-backup-YYYY-MM-DD_HHMMSS.zip`
- Console: source/dest paths, file count, archive size, verification result

**Error handling:**
- Missing/invalid env vars → `SystemExit` (from `cli_utils` getters)
- Write failure (full disk, permissions) → catch `OSError`, print context, exit non-zero
- Verification failure → print warning with `testzip()` result

**User interaction:**
- `--dry-run`: print file count and estimated uncompressed size, then exit
- Default: create archive, print progress counter, verify, print summary

### Integration Points

- **`scan_tree()`** from `deluge_lib/scanning.py` — file discovery
- **`cli_utils.py`** — two new getter functions following the existing pattern exactly
- **`pyproject.toml`** — `deluge-backup` entry point
- **SD card safety:** Script is read-only on source; compliant with project standard §1-2

## Cross-Cutting Concerns

| Concern | Mitigation |
|---------|------------|
| Cross-platform zip paths | `PurePosixPath` for all `arcname` values ensures forward slashes |
| `.env.example` update | Add both new variables with example values |
| `.trash` exclusion | Handled automatically by `scan_tree()` |
| FAT32 source | No mtime comparison needed — zip captures whatever `scan_tree()` returns |

## Risk Mitigation

| Risk (from Research) | Plan Mitigation | Residual Risk |
|---------------------|-----------------|---------------|
| Zip archive truncation on full dest disk | `zipfile` raises `OSError` on write failure — catch and report with context | Partial zip file left on disk (user can delete manually) |
| Windows `PermissionError` on locked files | Catch in archiving loop, report file path and continue or abort | Individual locked files may be skipped |
| Zip created on Windows has backslash paths | `PurePosixPath` conversion for all `arcname` values | None |
| Source modified during archiving | Document: safely eject SD card from Deluge before running | Unlikely but not preventable in software |

## Implementation Roadmap

### Phase 1: Infrastructure

> **Goal:** Add the .env variables and cli_utils getters needed by the script
> **Prerequisites:** None

#### Task 1.1: Add `get_zip_source_path()` and `get_zip_dest_path()` to `cli_utils.py`

- **Description:** Two new functions following the exact pattern of `get_cloud_backup_path()` — load dotenv, read env var, validate directory exists, raise `SystemExit` on failure.
- **Acceptance Criteria:**
  - [x] `get_zip_source_path()` loads `ZIP_SOURCE_PATH` from `.env` and returns a validated `Path`
  - [x] `get_zip_dest_path()` loads `ZIP_DEST_PATH` from `.env` and returns a validated `Path`
  - [x] Both raise `SystemExit` with clear messages when env var is missing or path doesn't exist
  - [x] Pattern matches existing getters exactly (no over-engineering)
- **Implementation Notes:**
  > Added two functions to `cli_utils.py` following the exact pattern of `get_cloud_backup_path()`.

#### Task 1.2: Update `.env.example`

- **Description:** Add `ZIP_SOURCE_PATH` and `ZIP_DEST_PATH` with example values and comments.
- **Acceptance Criteria:**
  - [x] Both variables present with descriptive comments
  - [x] Example values show typical usage (SD card path for source, cloud folder for dest)
- **Implementation Notes:**
  > Added `ZIP_SOURCE_PATH` and `ZIP_DEST_PATH` with comments and example values to `.env.example`.

### Phase 2: Script

> **Goal:** Implement the backup script
> **Prerequisites:** Phase 1 complete

#### Task 2.1: Create `scripts/create_backup.py`

- **Description:** Main script with `def main(argv=None)` entry point. Flow: parse args → load env → scan source → if dry-run print summary and exit → create zip with progress → verify → print summary.
- **Acceptance Criteria:**
  - [x] `def main(argv: list[str] | None = None) -> None` entry point with `if __name__` guard
  - [x] `argparse` with `--dry-run` flag
  - [x] Loads source and dest via `get_zip_source_path()` and `get_zip_dest_path()`
  - [x] Prints source and dest paths at start
  - [x] Uses `scan_tree(source, file_filter="both")` for file discovery
  - [x] Dry-run prints file count and total uncompressed size, then exits
  - [x] Creates zip with `ZIP_DEFLATED` compression
  - [x] Archive name follows `DELUGE-backup-YYYY-MM-DD_HHMMSS.zip` pattern
  - [x] Archive entries use `PurePosixPath` for forward-slash paths
  - [x] Archive root is source contents (no wrapping directory)
  - [x] Prints progress counter during archiving (e.g. `Archiving... 1234/5500`)
  - [x] Calls `ZipFile.testzip()` after creation and reports result
  - [x] Prints final summary: file count, archive size, archive path
  - [x] Catches `OSError` during zip creation with clear error message
- **Implementation Notes:**
  > Created `scripts/create_backup.py`. Uses `\r` single-line counter for progress (resolves OQ1). Includes `_format_size()` helper for human-readable byte counts.

#### Task 2.2: Register entry point in `pyproject.toml`

- **Description:** Add `deluge-backup = "create_backup:main"` to `[project.scripts]`.
- **Acceptance Criteria:**
  - [x] Entry point registered and functional
- **Implementation Notes:**
  > Added `deluge-backup = "create_backup:main"` to `[project.scripts]` in `pyproject.toml`.

### Phase 3: Tests

> **Goal:** Test the script end-to-end
> **Prerequisites:** Phase 2 complete

#### Task 3.1: Create `scripts/tests/test_create_backup.py`

- **Description:** Tests following existing patterns (`tmp_path`, `monkeypatch.setenv`, `patch("deluge_lib.cli_utils.load_dotenv")`, `capsys`, class-based organisation).
- **Acceptance Criteria:**
  - [x] Test: dry-run prints summary without creating zip
  - [x] Test: full run creates zip with correct contents (XML + WAV only)
  - [x] Test: zip preserves directory structure
  - [x] Test: zip uses forward-slash paths internally
  - [x] Test: `.trash` contents excluded from zip
  - [x] Test: missing `ZIP_SOURCE_PATH` raises `SystemExit`
  - [x] Test: missing `ZIP_DEST_PATH` raises `SystemExit`
  - [x] All tests pass with `pytest scripts/tests/test_create_backup.py`
- **Implementation Notes:**
  > Created `tests/test_create_backup.py` with 7 tests across 4 test classes. All pass. Full suite (176 tests) passes with no regressions.

## Progress Tracker

| Phase | Status | Tasks Complete | Notes |
|-------|--------|---------------|-------|
| Phase 1: Infrastructure | Complete | 2/2 | |
| Phase 2: Script | Complete | 2/2 | |
| Phase 3: Tests | Complete | 1/1 | 7 tests, all passing |

## Open Questions

1. **Should progress output use `\r` carriage return (single updating line) or print each file?**
   - **Impact:** UX for large archives. Single-line counter is cleaner; per-file output is noisier but provides a log.
   - **Recommendation:** Single-line counter with `\r` and a final newline. Matches common archive tool UX. Print total at end.
   - **Blocking:** No
   - **Resolution:** Single-line counter with `\r` — matches plan recommendation.

## References

### Research Document
- [new-scripts-research.md](../research/new-scripts-research.md) — Primary input (§2 scanning, §4 .env, §5.1 safety, §7 cross-platform, §8 zip design, §10 testing, §11 pyproject)

### Standards Applied
- [project.md](../../agent-system/standards/project.md) — SD card safety (read-only source), platform requirements (cross-platform, pathlib)

### Project Files
- [scripts/deluge_lib/cli_utils.py](../../scripts/deluge_lib/cli_utils.py) — Pattern for new getter functions
- [scripts/deluge_lib/scanning.py](../../scripts/deluge_lib/scanning.py) — `scan_tree()` reuse
- [scripts/sync_samples_to_cloud.py](../../scripts/sync_samples_to_cloud.py) — Closest script pattern (no manifest, custom log)
- [scripts/pyproject.toml](../../scripts/pyproject.toml) — Entry point registration
- [scripts/.env.example](../../scripts/.env.example) — Env var template
- [scripts/tests/test_sync_samples_to_cloud.py](../../scripts/tests/test_sync_samples_to_cloud.py) — Test pattern reference

## Change Log

| Date | Change | Reason |
|------|--------|--------|
| 13 April 2026 | Initial plan created | Feature planning from research document |
| 13 April 2026 | All phases implemented | No deviations from plan |
