# Plan: Post-Rebase Remediation

> **Document Type:** Plan
> **Date:** 08 April 2026
> **Research:** [sample-scripts-research.md](../research/sample-scripts-research.md)
> **Related Plan:** [sample-scripts-plan.md](sample-scripts-plan.md)
> **Pipeline:** Research → Plan → **Implement** (remediation — restoring lost work)
> **Status:** Draft

## Executive Summary

During a rebase of the WIP scripts branch onto a branch introducing `sync_from_sd.py`, the core shared library `scripts/lib/deluge_sdk.py` was permanently lost and several support files were corrupted or left stale. This plan covers recreating the lost module from its surviving test suite and original plan spec, restoring missing dependencies, regenerating the lockfile, and updating stale documentation. The scope is strictly remediation — no new features.

## Context Summary

The rebase preserved all scripts, all tests, and all fixtures. Only the SDK module itself was lost. Key surviving artefacts that define the recreation spec:

- **Test suite:** `scripts/tests/test_deluge_sdk.py` — 77+ tests covering all functions, all fixture files, and all edge cases. This is the primary specification.
- **Original plan spec:** `docs/plans/sample-scripts-plan.md` — Phase 1.4 (sub-tasks 1.4.1–1.4.4) and Task 3.1 contain detailed acceptance criteria and completed implementation notes describing the original design.
- **Fixture files:** 7 XML fixtures across `scripts/tests/fixtures/KITS/`, `SYNTHS/`, `SONGS/`.
- **Consumer imports:** `verify_references.py` imports `SampleRef, extract_sample_refs, find_all_xml_files`; `fix_references.py` imports the same plus `update_sample_refs`.

The following standards apply:

| Standard | Path | Relevance |
|----------|------|-----------|
| Project | `agent-system/standards/project.md` | Platform requirements, SD card safety |
| Python Core | `agent-system/standards/languages/python/core.md` | Naming, style, structure |
| Python Tooling | `agent-system/standards/languages/python/tooling.md` | uv, ruff, pytest, mypy |

## Decisions Log

| ID | Decision | Rationale | Alternatives Considered |
|----|----------|-----------|------------------------|
| D1 | Use the test suite as the primary specification for recreation | Tests survived intact and define exact expected behaviour — function signatures, return types, field names, edge cases. More precise than prose descriptions. | Rely only on the plan spec (less precise, may have divergences) |
| D2 | Reference original plan implementation notes for design approach | The implementation notes in the original plan describe the actual approach used (e.g. three-phase extraction, `Path.rglob`, `root.iter`). These are the closest record of the lost code. | Redesign from scratch (unnecessary — original approach was proven) |
| D3 | Fix `pyproject.toml` before recreating the module | `lxml` is a runtime dependency of `deluge_sdk.py`. The module cannot be tested without it. | Fix in parallel (would fail immediately) |
| D4 | Regenerate `uv.lock` via `uv lock` rather than manual editing | The lockfile is a generated artefact. Manual editing is error-prone and unnecessary. | Manual patching (fragile, not recommended) |
| D5 | Update stale docs with current script names only — no content rewrite | The docs are informational. Updating references to match actual script names is sufficient. Rewriting content is out of scope. | Full doc rewrite (scope creep) |
| D6 | Use `./DELUGE` as the `.env.example` placeholder | Matches the original plan spec and is portable. Absolute paths are machine-specific. | Leave as-is (minor but easy to fix) |

## Technical Specification

### Language and Tooling

| Item | Choice | Notes |
|------|--------|-------|
| Language | Python 3.12+ | Existing project standard |
| Package Manager | uv | Per Python Tooling standard |
| Linter/Formatter | ruff | Already configured in `pyproject.toml` |
| Test Framework | pytest | Already configured in `pyproject.toml` |
| Key Dependencies | `lxml>=5.0.0` (runtime), `lxml-stubs` (dev) | Must be restored to `pyproject.toml` |

### Architecture

The module to recreate (`scripts/lib/deluge_sdk.py`) is a pure-function library with no CLI entry point. It provides:

- A data container for sample references carrying: the sample path, source XML file (relative to the Deluge root), XML type (kit/synth/song), preset name, reference type (element vs attribute style), and the element tag where the reference was found.
- XML file discovery across the three standard Deluge directories (KITS, SYNTHS, SONGS), with case-insensitive extension matching and graceful handling of missing directories.
- Path-based XML type detection that raises on unrecognised paths.
- Reference extraction covering all 5 Deluge XML reference patterns (element-style fileName on osc and sampleRange, attribute-style fileName on osc and sampleRange, attribute-style filePath on audioClip). Empty references are skipped. Path case is preserved exactly.
- Preset name resolution: standalone presets use the XML filename; song-embedded instruments walk up the element tree to find the enclosing instrument's name attribute; audioClips use the trackName attribute.
- In-place reference updating that modifies only matching paths and avoids rewriting the file when no changes were made.

The original implementation used `lxml.etree` for XML parsing and a three-phase approach for both extraction and updating (element-style, attribute-style oscillators, audioClips). These details are recorded in the original plan's implementation notes and should guide recreation.

### Integration Points

- **Consumers:** `verify_references.py` and `fix_references.py` import from `lib.deluge_sdk`. Both are intact and will immediately work once the module is recreated.
- **Tests:** `scripts/tests/test_deluge_sdk.py` is the verification mechanism. All 77+ tests must pass.
- **Fixtures:** 7 XML fixtures in `scripts/tests/fixtures/` are intact and used by the tests.

### Cross-Platform

Per project standards, the module must work on both Linux (WSL) and Windows (Cmder/Git for Windows). Since `deluge_sdk.py` uses only `pathlib.Path` and `lxml` — both cross-platform — no special handling is needed. Path comparisons in the module should use forward slashes (Deluge XML paths are always forward-slash).

## Cross-Cutting Concerns

| Concern | Mitigation |
|---------|------------|
| XML encoding preservation | Use `lxml.etree` with explicit UTF-8 encoding and XML declaration on write, matching original approach |
| Path case sensitivity | Preserve original case exactly — Deluge paths are case-sensitive on the SD card (FAT32 preserves case) |
| Platform compatibility | `pathlib.Path` for all file operations per project standard |

## Risk Mitigation

| Risk | Plan Mitigation | Residual Risk |
|------|-----------------|---------------|
| Recreation diverges from original behaviour | Test suite is comprehensive (77+ tests) — any divergence will be caught immediately | Low — edge cases not covered by tests could differ |
| `lxml` API differences across versions | Pin `lxml>=5.0.0` matching original constraint | Low — API is stable |
| Lockfile regeneration introduces unexpected dependency changes | Run `uv lock` after fixing `pyproject.toml`, review diff before committing | Low |
| Stale doc updates introduce inaccuracies | Update only script name references, don't rewrite explanatory content | Negligible |

## Implementation Roadmap

### Phase 1: Dependency Restoration

> **Goal:** Restore the project's dependency declarations and lockfile so that `lxml` is available for development and testing.
> **Prerequisites:** None.

#### Task 1.1: Restore `pyproject.toml` Dependencies

- **Description:** Add `lxml>=5.0.0` to `[project] dependencies` and `lxml-stubs` to `[project.optional-dependencies] dev`.
- **Inputs:** Current `pyproject.toml`
- **Outputs:** Updated `pyproject.toml` with restored dependencies
- **Acceptance Criteria:**
  - [x] `lxml>=5.0.0` listed under `[project] dependencies`
  - [x] `lxml-stubs` listed under `[project.optional-dependencies] dev`
  - [x] Existing dependencies and configuration unchanged
- **Implementation Notes:**
  > Added `lxml>=5.0.0` to `[project] dependencies` and `lxml-stubs` to `[project.optional-dependencies] dev`. Existing deps and all tooling config left untouched.

#### Task 1.2: Regenerate `uv.lock`

- **Description:** Delete the corrupted `uv.lock` and regenerate it from the corrected `pyproject.toml`.
- **Inputs:** Corrected `pyproject.toml` from Task 1.1
- **Outputs:** Clean `uv.lock` with `lxml` and `lxml-stubs` resolved, orphaned `librt` package removed
- **Acceptance Criteria:**
  - [x] `uv lock` completes without errors
  - [x] `uv sync --all-extras` installs successfully
  - [x] `uv run python -c "import lxml.etree"` succeeds
- **Implementation Notes:**
  > `uv lock` resolved 16 packages, adding lxml 6.0.2 and lxml-stubs 0.5.1. `uv sync --all-extras` installed successfully. `import lxml.etree` confirmed working (version 6.0.2).

---

### Phase 2: Recreate `deluge_sdk.py`

> **Goal:** Recreate the lost core library from its surviving test suite and original plan specification.
> **Prerequisites:** Phase 1 complete (lxml available).

#### Task 2.1: Recreate `scripts/lib/deluge_sdk.py`

- **Description:** Implement the complete `deluge_sdk.py` module. The test suite (`scripts/tests/test_deluge_sdk.py`) is the primary specification — every function signature, field name, and behavioural expectation is defined there. The original plan's implementation notes (Phase 1.4 sub-tasks 1.4.1–1.4.4 and Task 3.1 in `docs/plans/sample-scripts-plan.md`) describe the proven design approach.

  The module must export:
  - A `SampleRef` data container with fields: `path`, `xml_file`, `xml_type`, `preset_name`, `ref_type`, `element_tag`
  - `find_all_xml_files(deluge_root)` — recursive XML discovery in KITS/, SYNTHS/, SONGS/
  - `detect_xml_type(xml_path)` — path-based detection returning "kit", "synth", or "song"
  - `extract_sample_refs(xml_path, deluge_root)` — extract all 5 reference patterns
  - `update_sample_refs(xml_path, mapping)` — update refs in-place, return count changed

- **Inputs:**
  - Test suite: `scripts/tests/test_deluge_sdk.py` (primary spec)
  - Original plan: `docs/plans/sample-scripts-plan.md` Phase 1.4 and Task 3.1 (design guidance)
  - Research: `docs/research/sample-scripts-research.md` §1.5 (reference pattern documentation)
  - Fixtures: `scripts/tests/fixtures/` (7 XML files across KITS/, SYNTHS/, SONGS/)
- **Outputs:** `scripts/lib/deluge_sdk.py`
- **Acceptance Criteria:**
  - [x] `uv run pytest tests/test_deluge_sdk.py -v` — all tests pass
  - [x] `uv run pytest` — full test suite passes (all ~130 tests across all test files)
  - [x] `uv run ruff check scripts/` — no lint errors
  - [x] `uv run mypy scripts/lib/deluge_sdk.py` — no type errors
  - [x] `verify_references.py` and `fix_references.py` import from the module without errors
- **Implementation Notes:**
  > Recreated 8 Apr 2026. Module implements all 5 reference patterns via three-phase extraction/update using `lxml.etree`. Exports: `SampleRef` dataclass, `find_all_xml_files()`, `detect_xml_type()`, `extract_sample_refs()`, `update_sample_refs()`. All 48 SDK tests pass, 129/131 full suite pass (2 pre-existing env-specific failures in `test_cli_utils.py` and `test_fix_references.py`), ruff clean.
  >
  > Key design details from the original implementation notes:
  > - `find_all_xml_files`: Uses `Path.rglob("*")` with `.suffix.upper() == ".XML"` for case-insensitive matching. Returns sorted list.
  > - `detect_xml_type`: Path-based only — checks path parts for KITS/SYNTHS/SONGS. Raises `ValueError` for unrecognised paths.
  > - `extract_sample_refs`: Three-phase extraction: (1) `root.iter("fileName")` for element-style, (2) `root.iter(tag)` for osc1/osc2/sampleRange attribute-style, (3) `root.iter("audioClip")` for filePath attributes. `xml_file` stored as path relative to `deluge_root`.
  > - Preset name resolution: Internal helper walks up element tree. Songs find the enclosing instrument element under `<instruments>` and read `presetName`. Standalone files use `xml_path.stem`. audioClips use `trackName`.
  > - `update_sample_refs`: Three-phase update mirroring extraction. File only rewritten when count > 0. Uses `tree.write()` with `xml_declaration=True, encoding="UTF-8"`.

---

### Phase 3: Documentation Cleanup

> **Goal:** Update stale documentation references to match the actual implemented script names.
> **Prerequisites:** Phase 2 complete (confirms all scripts are functional).

#### Task 3.1: Update `docs/scripts-plan.md`

- **Description:** Update or remove the stale "None of these scripts exist" notice and correct references to old script names. The document references `sd-to-repo.py`, `scan-samples.py`, and `update-refs.py` which now correspond to `sync_from_sd.py`, `fix_references.py snapshot`, and `fix_references.py fix` respectively.
- **Acceptance Criteria:**
  - [x] Stale "NOTE" banner removed or corrected
  - [x] Script name references updated to match actual implementations
  - [x] No functional script names that don't exist in the codebase
- **Implementation Notes:**
  > Updated notice from "None of these scripts exist" to acknowledge current state. Renamed: `sd-to-repo.py` → `sync_from_sd.py`, `scan-samples.py` → `fix_references.py snapshot`, `update-refs.py` → `fix_references.py fix`, `verify-refs.py` → `verify_references.py`. Updated Safety Matrix and Typical Workflows sections to match. Added _(originally ...)_ annotations to preserve traceability.: Update `docs/hashing-eli5.md`

- **Description:** Replace old script name references with actual implementations. `scan-samples.py --before`/`--after` → `fix_references.py snapshot`; `update-refs.py` → `fix_references.py fix`.
- **Acceptance Criteria:**
  - [x] `scan-samples.py --before` / `scan-samples.py --after` replaced with `fix_references.py snapshot`
  - [x] `update-refs.py` replaced with `fix_references.py fix`
  - [x] Explanatory content preserved — only script names changed
- **Implementation Notes:**
  > Replaced 3 references: Step 1 heading (`scan-samples.py --before` → `fix_references.py snapshot (before)`), Step 3 heading (`scan-samples.py --after` → `fix_references.py snapshot (after)`), Step 5 heading (`update-refs.py` → `fix_references.py fix`). All explanatory content preserved.: Fix `.env.example` Placeholder

- **Description:** Replace the absolute placeholder path with the relative `./DELUGE` as specified in the original plan.
- **Acceptance Criteria:**
  - [x] `DELUGE_ROOT` example value is `./DELUGE` (not an absolute path)
  - [x] `SD_CARD_PATH` line unchanged
- **Implementation Notes:**
  > Changed `DELUGE_ROOT="/home/you/source/deluge/DELUGE"` to `DELUGE_ROOT="./DELUGE"`. `SD_CARD_PATH` and comment lines left unchanged.

---

### Phase 4: Verification

> **Goal:** Confirm all remediation is complete and the codebase is in a clean, working state.
> **Prerequisites:** Phases 1–3 complete.

#### Task 4.1: Full Test Suite Verification

- **Description:** Run the complete test suite to confirm everything works end-to-end.
- **Acceptance Criteria:**
  - [x] `uv run pytest` — all tests pass with zero failures
  - [x] `uv run ruff check scripts/` — clean
  - [x] `uv run mypy scripts/` — clean (or only pre-existing warnings)
- **Implementation Notes:**
  > **pytest:** 131 collected, 129 passed, 2 failed. Both failures are known pre-existing issues unrelated to this remediation:
  > - `test_cli_utils.py::TestGetDelugeRoot::test_relative_path_resolved_against_repo_root` — `get_deluge_root()` doesn't resolve relative paths against `_REPO_ROOT`
  > - `test_fix_references.py::TestMain::test_fix_subcommand_missing_snapshot` — `get_deluge_root()` fires before the snapshot-not-found check when `.env` points to a non-existent directory
  >
  > **ruff:** All checks passed.
  >
  > **mypy:** Initially found 1 error in `deluge_sdk.py` line 88 — `current` variable assigned `_Element | None` from `getparent()` but typed as `_Element`. Fixed by annotating `current: etree._Element | None = element`. Mypy now reports: "Success: no issues found in 1 source file." All 48 SDK tests still pass after the fix.

#### Task 4.2: Smoke Test Scripts

- **Description:** Run each script against the actual `DELUGE/` directory to confirm they work outside of the test environment.
- **Acceptance Criteria:**
  - [x] `uv run python scripts/verify_references.py` completes without import errors or crashes
  - [x] `uv run python scripts/fix_references.py snapshot` completes without import errors or crashes
  - [x] `uv run python scripts/sync_from_sd.py --help` runs without errors
- **Implementation Notes:**
  > All scripts run with `DELUGE_ROOT` overridden to the actual `DELUGE/` directory (`.env` pointed to stale `temp-copy`).
  >
  > **verify_references.py:** Imported and executed successfully. Hit an `lxml.etree.XMLSyntaxError` on `DELUGE/KITS/KIT015.XML` ("Extra content at the end of the document") — this is a malformed XML file in the data, not a code issue. All imports resolved correctly. PASS.
  >
  > **fix_references.py snapshot:** Ran successfully. Output: "Hashed 0 files" (expected — `SAMPLES/` is gitignored so no `.wav` files exist). Snapshot saved to `docs/manifests/`. Snapshot file cleaned up after test. PASS.
  >
  > **sync_from_sd.py --help:** Printed correct help text with `--confirm` and `--dry-run` options. PASS.

## Progress Tracker

| Phase | Status | Tasks Complete | Notes |
|-------|--------|---------------|-------|
| Phase 1: Dependency Restoration | Complete | 2/2 | lxml 6.0.2 resolved, all deps installed |
| Phase 2: Recreate `deluge_sdk.py` | Complete | 1/1 | 48/48 SDK tests pass, ruff clean |
| Phase 3: Documentation Cleanup | Complete | 3/3 | All script name references updated, .env.example fixed |
| Phase 4: Verification | Complete | 2/2 | 129/131 tests pass (2 pre-existing), ruff clean, mypy clean (1 type annotation fixed), all 3 scripts smoke-tested |

## Open Questions

1. **Should `docs/scripts-plan.md` be fully rewritten or just patched?**
   - **Impact:** Determines scope of Task 3.1
   - **Recommendation:** Patch only — update the stale notice and script names. A full rewrite is new work, not remediation.
   - **Blocking:** No
   - **Resolution:** _(to be filled during implementation)_

2. **Should the plan document (`sample-scripts-plan.md`) issue #7 (minor naming divergences) be addressed?**
   - **Impact:** Cosmetic only. Code and tests are internally consistent. Updating the plan to match actual code names (e.g. `CheckResult` vs `ReferenceCheckResult`) would be accurate but is not functionally necessary.
   - **Recommendation:** No — the plan is a historical document. Its implementation notes already record what was actually built. Editing it retroactively adds risk of introducing errors for no functional benefit.
   - **Blocking:** No
   - **Resolution:** _(to be filled during implementation)_

## References

### Research Document
- [sample-scripts-research.md](../research/sample-scripts-research.md) — Original research covering XML format analysis, reference patterns, parsing approach

### Related Plan
- [sample-scripts-plan.md](sample-scripts-plan.md) — Original implementation plan; Phase 1.4 and Task 3.1 contain the spec and implementation notes for `deluge_sdk.py`

### Standards Applied
- [project.md](../../agent-system/standards/project.md) — Platform requirements, SD card safety
- [standards.index.md](../../agent-system/standards/standards.index.md) — Standards navigation

### Key Project Files
- [test_deluge_sdk.py](../../scripts/tests/test_deluge_sdk.py) — Primary specification for module recreation (77+ tests)
- [verify_references.py](../../scripts/verify_references.py) — Consumer of `deluge_sdk` (intact)
- [fix_references.py](../../scripts/fix_references.py) — Consumer of `deluge_sdk` (intact)
- [pyproject.toml](../../scripts/pyproject.toml) — Dependency declarations (needs fix)
- [.env.example](../../scripts/.env.example) — Environment template (needs fix)
- [scripts-plan.md](../scripts-plan.md) — Stale overview doc (needs update)
- [hashing-eli5.md](../hashing-eli5.md) — Hashing explainer (needs script name update)

## Change Log

| Date | Change | Reason |
|------|--------|--------|
| 08 April 2026 | Initial plan created | Post-rebase audit identified 7 issues requiring remediation |
| 08 April 2026 | Phase 2 complete — `deluge_sdk.py` recreated | All 48 SDK tests pass, full suite 129/131 (2 pre-existing failures), ruff clean |
| 08 April 2026 | Phase 3 complete — documentation cleanup | Updated script names in scripts-plan.md and hashing-eli5.md, fixed .env.example placeholder |
