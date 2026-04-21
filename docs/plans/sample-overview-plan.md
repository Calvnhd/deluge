# Plan: Sample Library Overview Tool

> **Document Type:** Plan
> **Date:** 21 April 2026
> **Research:** [sample-overview-research.md](../research/sample-overview-research.md)
> **Pipeline:** Research → **Plan** → Implement
> **Status:** Draft

## Executive Summary

Build a new `sample_overview.py` script with 4 subcommands (`summary`, `unused`, `missing`, `usage`) backed by a shared `deluge_lib/analysis.py` analysis module. The tool scans the Deluge SD card backup fresh each run, cross-references filesystem state with XML sample references, and produces plain-text reports to stdout. The existing `list_samples.py` is deleted as it is fully superseded.

## Research Summary

The research found that ~80% of the data collection layer already exists in `deluge_lib/`. `extract_sample_refs()` provides rich per-reference metadata (`SampleRef` with path, source XML, type, preset name, ref type, element tag). `scan_tree()` returns `FileEntry` objects with `rel_path`, `size`, and `mtime`. The missing piece is an *analysis layer* — aggregation, cross-referencing, size totals, and formatted output.

Key constraints from research (Existing Assets Analysis):
- `get_existing_samples()` discards size data; the tool must call `scan_tree()` directly to retain `FileEntry` objects
- `find_all_xml_files()` discards size/mtime but that's fine — XML sizes aren't needed
- `_format_size()` is private to `create_backup.py` and must be extracted for reuse
- `check_references()` in `verify_references.py` has progress printing baked in and does its own scanning; simpler to cross-reference directly
- No subparser pattern exists in the codebase; this script will be the first
- Fresh scanning at ~6000 files takes ~3–5 seconds — no caching needed

## Decisions Log

| ID | Decision | Rationale | Alternatives Considered |
|----|----------|-----------|------------------------|
| D1 | Use subcommands (`summary`, `unused`, `missing`, `usage`) | 4 distinct modes with different output shapes and per-subcommand flags; clearer UX and help text than flat flags; more extensible (Research §2, §7) | Flat flags (`--unused`, `--missing`) — simpler but ambiguous combinations; Separate scripts — duplicated scanning and fragmented UX |
| D2 | `summary` is the default subcommand (bare invocation) | Bare `sample_overview.py` should produce useful output, matching user expectation (Research Open Q1) | Show help on bare invocation — less discoverable |
| D3 | Case-insensitive substring match for `usage` pattern | Simplest and most useful; covers the primary use case of "find samples matching this term". Glob support can be added later without breaking changes (Research Open Q4) | Glob patterns — more powerful but more complex to implement and explain |
| D4 | Folder-grouped output is the default for all sample-listing subcommands | Folder grouping matches how the user thinks about their library and is the most readable layout for all subcommands (`unused`, `missing`, `usage`). `summary` already has a folder breakdown. No flag needed — it's always the behaviour. (Research Open Q5, user feedback) | Optional `--by-folder` flag — unnecessary indirection when folder grouping is always preferred |
| D5 | Extract `_format_size()` to `deluge_lib/scanning.py` as a public function | Closely related to `FileEntry.size` data already in that module; avoids creating a single-function module (Research §5, Cross-Cutting Concerns) | New `formatting.py` module — overkill for one function; `cli_utils.py` — less related to file data |
| D6 | Call `scan_tree()` directly for SAMPLES/ instead of `get_existing_samples()` | The tool needs `FileEntry` objects with size data; `get_existing_samples()` discards this and returns only a path set (Research Existing Assets §Key Observations) | Modify `get_existing_samples()` to return sizes — would change its API and affect existing callers |
| D7 | Delete `list_samples.py` outright | No dependents; not registered in `pyproject.toml`; fully superseded by `summary` subcommand. A deprecation wrapper adds complexity for no audience (Research Open Q3) | Keep as deprecation wrapper — unnecessary indirection |
| D8 | No manifest/snapshot integration — scan fresh each run | No consumer exists for cached usage data; scanning takes ~3–5s; avoids staleness detection and invalidation complexity (Research §4) | Write usage manifest alongside snapshots — no concrete benefit, significant complexity |
| D9 | Plain-text output only; defer `--json`/`--output` | Matches every existing script; no downstream consumer; analysis module produces data structures that can be serialised later (Research §3, Open Q2) | Include `--json` in v1 — premature; easy to add later |
| D10 | Analysis logic in `deluge_lib/analysis.py`, script is a thin CLI wrapper | Follows established codebase pattern where `deluge_lib/` provides logic and scripts provide CLI (Research §9) | All logic in the script — harder to test and reuse |
| D11 | Frame the tool as an organisational overview, not a cleanup/disk-reclamation utility | Space is not a concern — the tool exists to support organisational choices (e.g. deleting samples that sound bad or are broken, not reclaiming disk space). All "reclaimable" language removed. Size info is retained for context but not framed as space to free. (User feedback) | Cleanup/reclaimable framing — inaccurate to user intent |

## Technical Specification

### Language and Tooling

| Item | Choice | Notes |
|------|--------|-------|
| Language | Python 3.12+ | Matches all existing scripts; `pyproject.toml` requires `>=3.12` |
| Key dependencies | `lxml`, `python-dotenv` | Already in project dependencies; no new packages needed |
| Test framework | `pytest` | Already in dev dependencies |
| Linter/Formatter | `ruff` | Already configured in `pyproject.toml` |

Standard reference: `agent-system/standards/languages/` (Python standard, if present)

### Architecture

The tool follows the existing codebase pattern: a thin CLI script backed by a library module.

**`deluge_lib/analysis.py`** — The analysis module. Responsible for:
- Building a usage index: cross-referencing all `SampleRef` objects against the disk scan to classify every sample as referenced, unreferenced, or missing
- Computing aggregate statistics: total counts, total sizes, per-folder breakdowns
- Filtering and sorting: top-N by reference count or size, pattern matching for the `usage` subcommand
- All functions accept pre-collected data (sample refs and scan results) — no direct filesystem or XML access

**`sample_overview.py`** — The CLI script. Responsible for:
- Argument parsing with `argparse` subparsers
- Data collection: calling `scan_tree()` for SAMPLES/ and `find_all_xml_files()` + `extract_sample_refs()` for XMLs
- Passing collected data to analysis functions
- Formatting and printing results to stdout

**`deluge_lib/scanning.py`** — Receives the extracted `format_size()` function (renamed from `_format_size()` to make it public).

**Data flow:**
1. Script collects raw data via existing `deluge_lib` functions
2. Script passes raw data to `analysis.py` functions
3. Analysis functions return structured results (plain data objects — dicts, named tuples, or dataclasses)
4. Script formats results as plain text and prints to stdout

### Interface Design

**CLI interface:**

```
sample_overview.py                     # runs summary (default)
sample_overview.py summary             # explicit summary
sample_overview.py unused              # list unreferenced samples (grouped by folder)
sample_overview.py unused --top 20     # show top 20 unreferenced by size
sample_overview.py missing             # list missing samples
sample_overview.py usage "Kick"        # show usage for samples matching "Kick"
```

**Inputs:**
- `DELUGE_ROOT` from `.env` via `get_deluge_root()` — same as all other scripts
- Subcommand selection via positional argument
- Pattern argument for `usage` subcommand (required positional)
- Optional flags: `--top N` (unused, summary)

**Outputs:**
- Plain-text reports to stdout
- Progress indicator during scanning (matching `scan_tree()` existing behaviour)
- Exit code 0 always (informational tool, not a validator)

**Error handling:**
- Invalid `DELUGE_ROOT` — handled by `get_deluge_root()` (existing behaviour: prints error and exits)
- No matches for `usage` pattern — print "No samples matching '{pattern}'"
- Empty library — print summary with zero counts (not an error)

### Integration Points

**Existing code used directly:**
- `deluge_lib/scanning.py`: `scan_tree()`, `FileEntry`, `ScanResult`, `normalise_key()`, and the newly-extracted `format_size()`
- `deluge_lib/deluge_sdk.py`: `extract_sample_refs()`, `find_all_xml_files()`, `SampleRef`
- `deluge_lib/cli_utils.py`: `get_deluge_root()`

**Existing code modified:**
- `deluge_lib/scanning.py`: add `format_size()` (extracted from `create_backup.py`)
- `create_backup.py`: update to import `format_size` from `deluge_lib.scanning` instead of using its private copy
- `pyproject.toml`: add `deluge-overview` entry

**Existing code removed:**
- `list_samples.py`: deleted (superseded)

**SD card safety:**
- This tool is strictly read-only. It reads XML files and scans the filesystem under `DELUGE/` but never writes to `DELUGE/` or the physical SD card. No safety concerns per `standards/project.md`.

## Cross-Cutting Concerns

| Concern (from Research) | Mitigation |
|------------------------|------------|
| `_format_size()` extraction | Extract to `scanning.py` as `format_size()`. Update `create_backup.py` import. Low-risk refactor — function is simple and standalone. |
| Overlap with `verify_references.py` | The `missing` subcommand is a lightweight overview; `verify_references.py` remains the authoritative pre-deployment check with regex fallback and exit codes. Help text for `missing` should note this. |
| `list_samples.py` deprecation | Delete outright. Not registered in `pyproject.toml`, no dependents, fully superseded. |
| Case-sensitivity | Use `normalise_key()` for all path matching, same as every other script in the codebase. |
| `get_existing_samples()` discards size data | Bypass it — call `scan_tree()` directly on SAMPLES/ to retain `FileEntry` objects. |

## Risk Mitigation

| Risk (from Research) | Plan Mitigation | Residual Risk |
|---------------------|-----------------|---------------|
| Case-sensitivity mismatches between XML refs and disk paths | Use `normalise_key()` consistently for all matching, as existing scripts do | Low — pattern is proven |
| Performance regression at scale (>6000 files) | Fresh scan each run; `scan_tree()` already proven at this scale | Low — ~3–5s total |
| Subcommand pattern unfamiliar to user | `summary` runs on bare invocation; `--help` available per subcommand | Low — standard CLI pattern |
| `_format_size()` extraction breaks `create_backup.py` | Extract, update import, run `create_backup.py` to verify | None after verification |
| Output format changes break user workflows | No downstream consumers parse this output | None |

## Implementation Roadmap

## Phase 1: Shared Utilities

> **Goal:** Extract `_format_size()` to a shared location so both `create_backup.py` and the new script can use it
> **Prerequisites:** None

### Task 1.1: Extract `format_size()` to `scanning.py`

- **Description:** Move the `_format_size()` function from `create_backup.py` to `deluge_lib/scanning.py`, renaming it to `format_size()` (public). Update `create_backup.py` to import from the new location.
- **Inputs:** `create_backup.py` (source of `_format_size()`), `deluge_lib/scanning.py` (destination)
- **Outputs:** `format_size()` available in `deluge_lib/scanning.py`; `create_backup.py` updated to import it
- **Acceptance Criteria:**
  - [ ] `format_size()` exists in `deluge_lib/scanning.py` with identical logic to the original
  - [ ] `create_backup.py` imports `format_size` from `deluge_lib.scanning` and no longer has a local copy
  - [ ] `create_backup.py` still functions correctly (manual run or test)
- **Implementation Notes:**
  > _(Space for the Implement agent)_

---

## Phase 2: Analysis Module

> **Goal:** Create the analysis layer that cross-references sample references with filesystem state
> **Prerequisites:** Phase 1 complete (for `format_size()` availability)

### Task 2.1: Create `deluge_lib/analysis.py` with core data structures

- **Description:** Create the analysis module with data structures to hold analysis results: a per-sample usage record (which XMLs reference it, reference count, file size, whether it exists on disk), a library summary (total counts, total sizes, missing count), and a folder breakdown record (folder path, file count, total size).
- **Inputs:** `SampleRef` and `FileEntry` structures from existing modules (for understanding the input shapes)
- **Outputs:** `deluge_lib/analysis.py` with result data structures
- **Acceptance Criteria:**
  - [ ] Module exists at `deluge_lib/analysis.py`
  - [ ] Data structures can represent: per-sample usage info, library-wide summary stats, per-folder breakdowns
  - [ ] Passes `ruff` linting
- **Implementation Notes:**
  > _(Space for the Implement agent)_

### Task 2.2: Implement the usage index builder

- **Description:** Implement a function that accepts a list of `SampleRef` objects and a `ScanResult` (from `scan_tree()` on SAMPLES/) and produces the per-sample usage index. For each sample on disk, determine whether it is referenced (and by which XMLs) or unreferenced. For each sample referenced in XML, determine whether it exists on disk (or is missing). Use `normalise_key()` for all path matching.
- **Inputs:** List of `SampleRef`, `ScanResult` from SAMPLES/ scan
- **Outputs:** A complete usage index covering every known sample (on disk, in XML, or both)
- **Acceptance Criteria:**
  - [ ] Correctly classifies samples as referenced, unreferenced, or missing
  - [ ] Includes per-sample reference count and list of referencing XMLs with metadata
  - [ ] Includes per-sample size (from `FileEntry`) for samples that exist on disk
  - [ ] Uses `normalise_key()` for case-insensitive matching
  - [ ] Unit tests cover: sample referenced and on disk, sample on disk but unreferenced, sample referenced but not on disk, case-insensitive matching
- **Implementation Notes:**
  > _(Space for the Implement agent)_

### Task 2.3: Implement aggregation functions

- **Description:** Implement functions that operate on the usage index to produce: (a) library summary statistics (total on disk, total referenced, total unreferenced, total missing, total sizes), (b) per-folder breakdown (group files by their top-level folder under SAMPLES/, with counts and sizes), (c) top-N samples by reference count or size, (d) filtered usage for the `usage` subcommand (case-insensitive substring match on sample path, returning matching entries with full usage detail).
- **Inputs:** The usage index from Task 2.2
- **Outputs:** Aggregation and filtering functions
- **Acceptance Criteria:**
  - [ ] Summary function returns correct totals for a known test dataset
  - [ ] Folder breakdown groups correctly by the first path component under SAMPLES/
  - [ ] Top-N returns items sorted by the specified metric, limited to N
  - [ ] Pattern filter matches case-insensitively on substrings of the sample path
  - [ ] Unit tests cover each aggregation function
- **Implementation Notes:**
  > _(Space for the Implement agent)_

---

## Phase 3: CLI Script

> **Goal:** Create the `sample_overview.py` script with all 4 subcommands
> **Prerequisites:** Phase 2 complete

### Task 3.1: Create `sample_overview.py` with argument parsing and data collection

- **Description:** Create the script with `argparse` subparsers for `summary`, `unused`, `missing`, and `usage`. Implement the shared data collection step that all subcommands use: call `get_deluge_root()`, scan SAMPLES/ via `scan_tree()`, find all XMLs via `find_all_xml_files()`, extract all refs via `extract_sample_refs()`, and build the usage index. When no subcommand is given, default to `summary`. The `unused` subcommand accepts `--top N`. The `summary` subcommand accepts `--top N`. The `usage` subcommand accepts a required positional `PATTERN` argument.
- **Inputs:** `deluge_lib` modules (analysis, scanning, deluge_sdk, cli_utils)
- **Outputs:** `sample_overview.py` with working CLI structure and data collection
- **Acceptance Criteria:**
  - [ ] `sample_overview.py` parses all 4 subcommands correctly
  - [ ] Bare invocation (no subcommand) defaults to `summary`
  - [ ] `--help` works at the top level and per subcommand
  - [ ] Data collection calls the correct `deluge_lib` functions
- **Implementation Notes:**
  > _(Space for the Implement agent)_

### Task 3.2: Implement `summary` output formatting

- **Description:** Format and print the summary report. Include: total on-disk count and size, referenced count and size, unreferenced count and size, missing count, per-folder breakdown table, and top-N most-referenced samples. Use `format_size()` for all size values. Match the existing codebase output style (headers with underlines, indented lists, summary lines).
- **Inputs:** Analysis results from the usage index and aggregation functions
- **Outputs:** Formatted summary printed to stdout
- **Acceptance Criteria:**
  - [ ] Summary shows all required sections (totals, folder breakdown, top-N)
  - [ ] Sizes are human-readable via `format_size()`
  - [ ] Output style matches existing scripts (see Research §3 for patterns)
  - [ ] `--top N` controls how many top samples are shown (default 5)
- **Implementation Notes:**
  > _(Space for the Implement agent)_

### Task 3.3: Implement `unused` output formatting

- **Description:** Format and print the unreferenced samples report. Default view: grouped by top-level folder under SAMPLES/, showing per-folder count and size, then individual samples within each group sorted by size (largest first). Footer shows total unreferenced count and size. With `--top N`: show only the N largest unreferenced samples (flat list, not grouped).
- **Inputs:** Analysis results (unreferenced samples from usage index)
- **Outputs:** Formatted unused report printed to stdout
- **Acceptance Criteria:**
  - [ ] Default output groups unreferenced samples by top-level SAMPLES/ subfolder
  - [ ] Each folder group shows count and total size, then individual samples with sizes
  - [ ] Footer shows total unreferenced count and size
  - [ ] `--top N` limits output to N largest entries (flat list)
- **Implementation Notes:**
  > _(Space for the Implement agent)_

### Task 3.4: Implement `missing` output formatting

- **Description:** Format and print the missing samples report. Default view: grouped by top-level folder under SAMPLES/. For each missing sample, show the sample path and which XMLs reference it (with XML type and preset name). If no samples are missing, print a confirmation message.
- **Inputs:** Analysis results (missing samples from usage index)
- **Outputs:** Formatted missing report printed to stdout
- **Acceptance Criteria:**
  - [ ] Each missing sample shows its path and all referencing XMLs
  - [ ] Referencing XMLs include type (kit/synth/song) and preset name
  - [ ] Clean output when no samples are missing
  - [ ] Help text mentions `verify_references.py` for thorough verification
- **Implementation Notes:**
  > _(Space for the Implement agent)_

### Task 3.5: Implement `usage` output formatting

- **Description:** Format and print the usage report for samples matching the given pattern. Default view: grouped by top-level folder under SAMPLES/. For each matching sample, show: sample path, size (if on disk), all referencing XMLs with type and preset name, total reference count, and whether the sample is exclusive (1 ref) or shared (multiple refs). If no samples match, print a message.
- **Inputs:** Analysis results (filtered usage from pattern match)
- **Outputs:** Formatted usage report printed to stdout
- **Acceptance Criteria:**
  - [ ] Shows all samples whose path contains the pattern (case-insensitive)
  - [ ] Each sample shows size, referencing XMLs with metadata, and total ref count
  - [ ] Indicates exclusive vs shared usage
  - [ ] Clean message when no samples match the pattern
- **Implementation Notes:**
  > _(Space for the Implement agent)_

---

## Phase 4: Cleanup and Registration

> **Goal:** Register the new script, remove the old one, and ensure everything is wired up
> **Prerequisites:** Phase 3 complete

### Task 4.1: Register in `pyproject.toml`

- **Description:** Add a `deluge-overview = "sample_overview:main"` entry under `[project.scripts]` in `scripts/pyproject.toml`.
- **Inputs:** `scripts/pyproject.toml`
- **Outputs:** Updated `pyproject.toml`
- **Acceptance Criteria:**
  - [ ] `deluge-overview` entry present in `[project.scripts]`
  - [ ] Entry points to `sample_overview:main`
- **Implementation Notes:**
  > _(Space for the Implement agent)_

### Task 4.2: Delete `list_samples.py`

- **Description:** Remove `scripts/list_samples.py`. It has no `pyproject.toml` registration, no downstream dependents, and is fully superseded by the `summary` subcommand.
- **Inputs:** Confirmation that `sample_overview.py summary` covers the same use case
- **Outputs:** `list_samples.py` removed from the repository
- **Acceptance Criteria:**
  - [ ] `list_samples.py` deleted
  - [ ] No remaining imports or references to `list_samples` in the codebase
- **Implementation Notes:**
  > _(Space for the Implement agent)_

---

## Phase 5: Verification

> **Goal:** Validate the complete tool against real data
> **Prerequisites:** Phases 1–4 complete

### Task 5.1: End-to-end manual testing

- **Description:** Run all 4 subcommands against the actual `DELUGE/` backup and verify the output is correct and well-formatted. Verify that `create_backup.py` still works after the `format_size()` extraction.
- **Inputs:** `DELUGE/` directory with real data
- **Outputs:** Verified working tool
- **Acceptance Criteria:**
  - [ ] `sample_overview.py` (bare) produces a summary with plausible counts and sizes
  - [ ] `sample_overview.py unused` lists unreferenced samples
  - [ ] `sample_overview.py unused` groups by folder by default
  - [ ] `sample_overview.py unused --top 10` limits output
  - [ ] `sample_overview.py missing` shows missing samples (or confirms none are missing)
  - [ ] `sample_overview.py usage "Kick"` shows matching samples with usage detail
  - [ ] `sample_overview.py usage "nonexistent"` prints a clean "no matches" message
  - [ ] `create_backup.py` still runs correctly after `format_size()` extraction
  - [ ] All unit tests pass
- **Implementation Notes:**
  > _(Space for the Implement agent)_

---

## Progress Tracker

| Phase | Status | Tasks Complete | Notes |
|-------|--------|---------------|-------|
| Phase 1: Shared Utilities | Not Started | 0/1 | |
| Phase 2: Analysis Module | Not Started | 0/3 | |
| Phase 3: CLI Script | Not Started | 0/5 | |
| Phase 4: Cleanup and Registration | Not Started | 0/2 | |
| Phase 5: Verification | Not Started | 0/1 | |

## Open Questions

1. **Where should `format_size()` live long-term if more formatting utilities are needed later?**
   - **Impact:** If multiple formatting functions accumulate in `scanning.py`, it may warrant a separate `formatting.py` module
   - **Recommendation:** Put it in `scanning.py` for now. Extract to a dedicated module only if 2+ formatting functions accumulate there.
   - **Blocking:** No
   - **Resolution:** _(To be filled during implementation)_

## References

### Research Document
- [sample-overview-research.md](../research/sample-overview-research.md) — Primary input

### Standards Applied
- [project.md](../../agent-system/standards/project.md) — SD card safety and platform requirements (tool is read-only; no safety concerns)

### Project Files
- [scripts/list_samples.py](../../scripts/list_samples.py) — Script being replaced
- [scripts/deluge_lib/scanning.py](../../scripts/deluge_lib/scanning.py) — `scan_tree()`, `FileEntry`, `normalise_key()`; destination for `format_size()`
- [scripts/deluge_lib/deluge_sdk.py](../../scripts/deluge_lib/deluge_sdk.py) — `extract_sample_refs()`, `find_all_xml_files()`, `SampleRef`
- [scripts/deluge_lib/cli_utils.py](../../scripts/deluge_lib/cli_utils.py) — `get_deluge_root()`
- [scripts/create_backup.py](../../scripts/create_backup.py) — Source of `_format_size()` to extract
- [scripts/verify_references.py](../../scripts/verify_references.py) — Overlapping `missing` functionality; coexists
- [scripts/pyproject.toml](../../scripts/pyproject.toml) — Script registration

## Change Log

| Date | Change | Reason |
|------|--------|--------|
| 21 April 2026 | Initial plan created | Research document complete; all open questions resolved with defaults |
| 21 April 2026 | Plan revision: reframe as organisational tool | Removed all "reclaimable"/cleanup language (D11). Made folder-grouped output the default for `unused`, `missing`, and `usage` — removed `--by-folder` flag entirely (D4 updated). Updated interface design, Tasks 2.3, 3.1, 3.3, 3.4, 3.5, and 5.1 acceptance criteria. |
