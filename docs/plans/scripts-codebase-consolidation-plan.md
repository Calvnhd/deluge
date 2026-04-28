# Plan: Scripts Codebase Consolidation

> **Document Type:** Plan
> **Date:** 10 April 2026
> **Research:** [scripts-codebase-review-research.md](../research/scripts-codebase-review-research.md)
> **Pipeline:** Research → **Plan** → Implement
> **Status:** Complete

## Executive Summary

This plan addresses six targeted improvements to the scripts codebase identified during a post-implementation review: a Windows path separator bug causing 9 test failures, redundant WAV scanning, inefficient XML discovery, noisy scanner output, duplicated test helpers, and missing pyproject.toml entry points. Each change is small and independently verifiable. Manifest hash integration is deferred as a separate feature per the research recommendation.

## Research Summary

The research reviewed the entire `scripts/` codebase for redundancies and integration gaps after three implementation phases. Key findings:

- **Bug:** `fix_references.py` uses `str(Path.relative_to())` which produces backslashes on Windows, breaking snapshot path matching and causing 9 test failures (Research §3.1)
- **Redundancy:** `_find_wav_files()` duplicates `scan_tree(file_filter="wav")` (Research §1.1)
- **Inefficiency:** `find_all_xml_files()` calls `scan_tree()` without `file_filter="xml"`, scanning WAV files unnecessarily and triggering noisy skip messages (Research §1.3, §4.1)
- **Noise:** `scan_tree()` prints "Skipping" for every non-matching file (Research §4.2)
- **Duplication:** `_touch()` helper is defined identically in 4 test files (Research §1.4)
- **Missing config:** `fix_references.py` and `verify_references.py` lack pyproject.toml entry points (Research §4.4)
- **Deferred:** Manifest hash integration recommended as a separate feature (Research §2)

The research recommended Approach A (minimal refactor) plus the `_find_wav_files()` replacement from Approach B — all targeted fixes, no manifest changes.

## Decisions Log

| ID | Decision | Rationale | Alternatives Considered |
|----|----------|-----------|------------------------|
| D1 | Fix Windows paths with `PurePosixPath` conversion | Research §3.1 recommends Option A — `PurePosixPath` is explicit, has no dependency on `normalise_key()` (which lowercases), and preserves case sensitivity needed by Deluge XML references | `normalise_key()` (lowercases — wrong), `as_posix()` method |
| D2 | Remove "Skipping" print from `scan_tree()` before fixing callers | Foundational change — callers like `find_all_xml_files()` inherit the fix. Silently skipping non-matching extensions is expected filter behaviour (Research §4.2) | Keep print but reduce to debug level (over-engineering for a CLI tool) |
| D3 | Add `file_filter="xml"` to `find_all_xml_files()` and remove manual suffix check | Strict improvement — eliminates redundant WAV scanning and post-filter. Research §1.3 rates this as minimal trade-off | Keep current approach (wastes work) |
| D4 | Replace `_find_wav_files()` with a thin `scan_tree()` wrapper | Eliminates the only real code duplication. Gains `.trash` exclusion for free. Research §1.1 provides the exact wrapper pattern | Keep `_find_wav_files()` (maintains duplication) |
| D5 | Move `_touch()` to `conftest.py` using the full-featured variant (with `mtime`) | Standard pytest practice. `conftest.py` already exists and is empty. The simpler variant in `test_scanning.py` works unchanged since `mtime` defaults to `None` (Research §1.4) | Leave duplicated (low-risk but unnecessary) |
| D6 | Keep `hash_file()` in `fix_references.py` for now | Research §1.2: only one consumer exists. Move when/if manifest hashing adds a second consumer. Premature extraction adds a module where it doesn't fit | Move to `deluge_lib/hashing.py` (premature) |
| D7 | Defer manifest hash integration | Research §2.3 recommends this as a separate planned feature. Current full-hash approach works and is fast enough for ~5,500 files | Implement now (too much scope for a consolidation effort) |

## Technical Specification

### Language and Tooling

| Item | Choice | Notes |
|------|--------|-------|
| Language | Python 3.12+ | Existing codebase; see `standards/languages/` if applicable |
| Test Framework | pytest | Existing; all changes must pass existing tests |
| Linter | ruff | Existing configuration in pyproject.toml |

### Architecture

No architectural changes. All modifications are within existing modules:
- `scripts/fix_references.py` — path normalisation fix and WAV scanning replacement
- `scripts/deluge_lib/scanning.py` — remove noisy print
- `scripts/deluge_lib/deluge_sdk.py` — add file filter to XML discovery
- `scripts/tests/conftest.py` — shared test helper
- `scripts/pyproject.toml` — entry point registration

### Interface Design

No interface changes. All fixes are internal. The `deluge-fix` and `deluge-verify` entry points are new CLI aliases but don't change script behaviour.

### Integration Points

- `fix_references.py` gains an import of `scan_tree` from `deluge_lib.scanning` (new dependency for WAV scanning replacement)
- `deluge_sdk.py` already imports `scan_tree` — just uses it more efficiently
- No SD card safety concerns — all changes are to code, not data

## Cross-Cutting Concerns

| Concern | Mitigation |
|---|---|
| Windows path separators | Phase 1 fixes the root cause with `PurePosixPath` conversion in `fix_references.py` |
| Scanner noise | Phase 2 removes the "Skipping" print before callers are updated |
| Test isolation | Shared `_touch()` in conftest uses default params; no coupling between test files |

## Risk Mitigation

| Risk | Plan Mitigation | Residual Risk |
|-----|-----------------|---------------|
| `PurePosixPath` changes snapshot format | Existing snapshots already use forward slashes (produced on Linux). Windows-produced snapshots were broken before — this is a fix, not a format change | None |
| Removing `_find_wav_files()` changes scan behaviour | `scan_tree()` skips `.trash` dirs (an improvement) and captures stats (discarded by wrapper). Functionally equivalent for WAV discovery. Verify with existing tests | Negligible — `.trash` exclusion is correct behaviour |
| Removing "Skipping" print hides unexpected files | Non-matching files are expected when a filter is active. Callers needing skip visibility can compare counts. OSError warnings are preserved | Low |

## Implementation Roadmap

### Phase 1: Fix Windows Path Separator Bug

> **Goal:** Fix the path separator bug in `fix_references.py` that causes 9 test failures on Windows
> **Prerequisites:** None

#### Task 1.1: Convert relative paths to POSIX format

- **Description:** In `fix_references.py`, replace `str(wav_path.relative_to(deluge_root))` with `str(PurePosixPath(wav_path.relative_to(deluge_root)))` at both locations (lines ~74 and ~153). Add `PurePosixPath` to the `pathlib` import.
- **Files:** `scripts/fix_references.py`
- **Acceptance Criteria:**
  - [x] Both `rel_path = str(...)` lines in `snapshot()` and `compute_migration_map()` use `PurePosixPath` conversion
  - [x] `PurePosixPath` is imported from `pathlib`
  - [x] All 9 previously-failing tests in `TestComputeMigrationMap` and `TestSnapshot` pass
  - [x] All other existing tests still pass
- **Implementation Notes:**
  > Changed `from pathlib import Path` → `from pathlib import Path, PurePosixPath`. Wrapped both `wav_path.relative_to(deluge_root)` calls with `PurePosixPath(...)` to ensure forward-slash paths on all platforms. All 192 tests pass.

---

### Phase 2: Fix Scanner Noise and XML Discovery

> **Goal:** Remove noisy "Skipping" output from `scan_tree()` and make `find_all_xml_files()` use the XML file filter
> **Prerequisites:** None (independent of Phase 1, but ordered here because Phase 3 depends on clean scanner behaviour)

#### Task 2.1: Remove "Skipping" print from `scan_tree()`

- **Description:** Remove the `print(f"\n  Skipping {rel} (unsupported extension)")` block from `scan_tree()` in `scanning.py`. Keep the `continue` — non-matching files should still be skipped, just silently.
- **Files:** `scripts/deluge_lib/scanning.py`
- **Acceptance Criteria:**
  - [x] The "Skipping" print and its preceding `rel = ...` line are removed
  - [x] The `continue` statement is preserved (non-matching files are still skipped)
  - [x] All existing scanning tests pass
- **Implementation Notes:**
  > Removed the `rel = file_path.relative_to(root)` and `print(...)` lines from the `if ext not in allowed:` block. The `if` check and `continue` remain. All 192 tests pass.

#### Task 2.2: Add `file_filter="xml"` to `find_all_xml_files()`

- **Description:** In `deluge_sdk.py`, pass `file_filter="xml"` to the `scan_tree()` call inside `find_all_xml_files()`. Remove the manual `.suffix.upper() == ".XML"` check — `scan_tree` already handles case-insensitive extension matching, so all entries in the result are guaranteed XML files.
- **Files:** `scripts/deluge_lib/deluge_sdk.py`
- **Acceptance Criteria:**
  - [x] `scan_tree(d)` call changed to `scan_tree(d, file_filter="xml")`
  - [x] Manual `.suffix.upper() == ".XML"` check removed
  - [x] All existing deluge_sdk and integration tests pass
- **Implementation Notes:**
  > Changed `scan_tree(d)` → `scan_tree(d, file_filter="xml")` and removed the `if entry.rel_path.suffix.upper() == ".XML":` guard. All entries returned by `scan_tree` with `file_filter="xml"` are guaranteed to be XML files. All 192 tests pass.

---

### Phase 3: Replace Redundant WAV Scanning

> **Goal:** Replace `_find_wav_files()` in `fix_references.py` with a `scan_tree()` wrapper
> **Prerequisites:** Phase 2 complete (scanner behaviour is clean)

#### Task 3.1: Replace `_find_wav_files()` with `scan_tree()` wrapper

- **Description:** Replace the body of `_find_wav_files()` to use `scan_tree(samples_dir, label="samples", file_filter="wav")` and return sorted absolute paths from the scan result. Add `scan_tree` to the imports from `deluge_lib.scanning`.
- **Files:** `scripts/fix_references.py`
- **Acceptance Criteria:**
  - [x] `_find_wav_files()` uses `scan_tree()` internally
  - [x] Returns sorted absolute `Path` objects (same interface as before)
  - [x] `scan_tree` is imported from `deluge_lib.scanning`
  - [x] All existing fix_references tests pass
  - [x] `.trash` directories are now excluded from WAV scanning (inherited from `scan_tree`)
- **Implementation Notes:**
  > Replaced `_find_wav_files()` body with `scan_tree(samples_dir, label="samples", file_filter="wav")` call, converting results back to sorted absolute paths via `sorted(samples_dir / entry.rel_path for entry in scan.files.values())`. Added `from deluge_lib.scanning import scan_tree` import. All 192 tests pass.

---

### Phase 4: Consolidate Test Helpers and Config

> **Goal:** Deduplicate `_touch()` test helper and add missing pyproject.toml entry points
> **Prerequisites:** None (independent of other phases)

#### Task 4.1: Move `_touch()` to `conftest.py`

- **Description:** Copy the full-featured `_touch(path, content=b"x", mtime=None)` from any of the three identical implementations into `tests/conftest.py`. Remove the local `_touch()` definitions from all four test files and add `from conftest import _touch` (or use pytest's automatic conftest discovery if `_touch` is not prefixed with `_` — since it starts with `_`, an explicit import is needed).
- **Files:** `scripts/tests/conftest.py`, `scripts/tests/test_scanning.py`, `scripts/tests/test_syncing.py`, `scripts/tests/test_sync_from_sd.py`, `scripts/tests/test_sync_samples_to_cloud.py`
- **Acceptance Criteria:**
  - [x] `_touch()` defined once in `tests/conftest.py` with `mtime` parameter
  - [x] All four test files import from `conftest` instead of defining locally
  - [x] All tests in all four files pass
- **Implementation Notes:**
  > Added full-featured `_touch(path, content=b"x", mtime=None)` to `tests/conftest.py`. Removed local definitions and unused `import os` from all 4 test files. Used `from tests.conftest import _touch` (not `from conftest import ...`) because pytest's conftest isn't directly importable as a top-level module when tests is a package. Also added `[build-system]` (hatchling) to `pyproject.toml` — required by uv to install `[project.scripts]` entry points; without it, entry points were silently skipped. All 192 tests pass.

#### Task 4.2: Add missing pyproject.toml entry points

- **Description:** Add `deluge-fix` and `deluge-verify` entry points to `[project.scripts]` in `pyproject.toml`.
- **Files:** `scripts/pyproject.toml`
- **Acceptance Criteria:**
  - [x] `deluge-fix = "fix_references:main"` added
  - [x] `deluge-verify = "verify_references:main"` added
  - [x] `uv run deluge-fix --help` and `uv run deluge-verify` work (`verify_references` has no argparse so `--help` is not supported, but the entry point resolves and runs correctly)
- **Implementation Notes:**
  > Added both entry points to `[project.scripts]`. Added `[build-system]` with hatchling backend and `[tool.hatch.build.targets.wheel] packages = ["deluge_lib"]` so uv can build and install entry points. `deluge-fix --help` shows usage. `deluge-verify` runs the verification (no argparse in that script). All 192 tests pass.

## Progress Tracker

| Phase | Status | Tasks Complete | Notes |
|-------|--------|---------------|-------|
| Phase 1: Fix Windows Path Separator Bug | **Complete** | 1/1 | All 192 tests pass |
| Phase 2: Fix Scanner Noise and XML Discovery | **Complete** | 2/2 | All 192 tests pass |
| Phase 3: Replace Redundant WAV Scanning | **Complete** | 1/1 | All 192 tests pass |
| Phase 4: Consolidate Test Helpers and Config | **Complete** | 2/2 | All 192 tests pass |

## Out of Scope

- **Manifest hash integration** — Deferred per research recommendation (§2). Plan as a separate feature when snapshot/fix performance becomes a pain point.
- **Moving `hash_file()` to shared module** — Only one consumer exists. Move when manifest hashing adds a second consumer (D6).
- **Suppressing `scan_tree()` progress messages in `find_all_xml_files()`** — Research Q2: the "Scanning... N files found" output provides useful feedback during XML operations on real data. Not worth adding complexity to suppress.

## Open Questions

None — all research open questions resolved:

1. **Should `hash_file()` move now?** → No. Wait for a second consumer (D6).
2. **Should `find_all_xml_files()` progress output be suppressed?** → No. Useful feedback, not worth suppressing (Research Q2).
3. **Should the old plan doc be updated for `lib/` → `deluge_lib/`?** → No. Historical document (Research Q3).

## References

### Research Document
- [scripts-codebase-review-research.md](../research/scripts-codebase-review-research.md) — Primary input

### Standards Applied
- [project.md](../../agent-system/standards/project.md) — Platform requirements and SD card safety

### Project Files
- [fix_references.py](../../scripts/fix_references.py) — Windows path bug, WAV scanning replacement
- [scanning.py](../../scripts/deluge_lib/scanning.py) — Noisy "Skipping" output removal
- [deluge_sdk.py](../../scripts/deluge_lib/deluge_sdk.py) — XML file filter fix
- [conftest.py](../../scripts/tests/conftest.py) — Shared test helper destination
- [pyproject.toml](../../scripts/pyproject.toml) — Entry point registration

## Change Log

| Date | Change | Reason |
|------|--------|--------|
| 10 Apr 2026 | Phase 2 complete — Tasks 2.1 and 2.2 implemented | Scanner noise removed, XML discovery uses file_filter |

| Date | Change | Reason |
|------|--------|--------|
| 10 Apr 2026 | Initial plan created | — |
| 10 Apr 2026 | Phase 1 complete — Windows path separator bug fixed | Task 1.1: added `PurePosixPath` conversion at both `rel_path` locations in `fix_references.py` |
| 10 Apr 2026 | Phase 4 complete — Test helpers consolidated, entry points added | Task 4.1: `_touch()` moved to conftest.py; Task 4.2: `deluge-fix` and `deluge-verify` entry points added; `[build-system]` added to enable entry point installation |
| 10 Apr 2026 | Plan status → Complete | All 4 phases complete |
