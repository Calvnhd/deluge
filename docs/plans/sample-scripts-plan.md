# Plan: Sample Management Scripts

> **Document Type:** Plan
> **Date:** 31 March 2026
> **Research:** [sample-scripts-research.md](../research/sample-scripts-research.md)
> **Pipeline:** Research → **Plan** → Implement
> **Status:** Draft

## Executive Summary

Build a suite of four modular Python scripts and a shared library (`deluge_sdk`) for managing samples on a Deluge SD card backup. The scripts provide: (1) a sample manifest generator for decision support, (2) a SHA256-based reference fixer for post-reorganisation repair, (3) a standalone reference verifier, and (4) a single-sample usage lookup tool. All scripts share XML parsing logic via `scripts/lib/deluge_sdk.py`, use `lxml` for parsing, and follow a compute-then-confirm workflow for XML modifications. A Makefile orchestrates common workflows. This plan follows the research recommendation of modular Python scripts with a shared library architecture (Research §Recommendation).

## Research Summary

**Recommended approach (Research §Recommendation):** Modular Python scripts with a shared `deluge_sdk` library, `lxml` for XML parsing, compute-then-confirm dry-run workflow.

**Key findings informing this plan:**

- **5 XML reference patterns** across 10 firmware versions in 2 format eras (element-style < 3.x, attribute-style ≥ 3.x), plus audio clip `filePath` (Research §1.5)
- **`wave` stdlib** sufficient for WAV metadata extraction; zero external audio dependencies (Research §3.2)
- **SHA256 hashing** validated for migration mapping at expected scale (~1000 files) (Research §4.1)
- **Song XMLs embed complete instrument definitions** — kits and synths inline — requiring careful traversal for manifest instrument names (Research §2)
- **CLIPS/, RECORD/, RESAMPLE/** have special constraints: directories must never be deleted, must never contain subdirectories (Research §8)
- **Case sensitivity** is critical — paths must be preserved exactly as-is (Research §1.6)

**Existing assets (Research §Existing Assets):**

- `scripts/.env.example` — existing env config template (needs `DELUGE_ROOT` addition)
- `docs/scripts-plan.md` — old unimplemented plan, useful for naming reference
- `docs/hashing-eli5.md` — user-facing hashing explanation

## Decisions Log

| ID | Decision | Rationale | Alternatives Considered |
|----|----------|-----------|------------------------|
| D1 | Python with `lxml` for XML, `wave` stdlib for audio | Research §3.2, §9. `lxml` mandated by Python Core Standard. `wave` is zero-dependency and WAV-only — matches Deluge format exactly | `xml.etree` (limited XPath), `soundfile` (unnecessary dependency for WAV-only) |
| D2 | `DELUGE_ROOT` env var with `./DELUGE` fallback | Research §OQ1. Consistent naming, clear purpose, sensible default for in-repo use | `DELUGE_DIR`, `DELUGE_PATH`, hardcoded path |
| D3 | `uv` as package manager | Python Tooling Standard mandates `uv` | `pip`, `poetry` |
| D4 | Flat scripts layout — `scripts/lib/` for shared modules, scripts at `scripts/` root | Python Core Standard §Project Structure — recommended layout for utility scripts | `src/` layout (over-engineered for scripts project) |
| D5 | Compute-then-confirm workflow: compute all changes → preview → prompt → apply without re-scan | Research §6.1, user requirement. Avoids slow re-scanning on apply | Separate dry-run/apply commands (requires re-scan), changeset file (extra complexity) |
| D6 | `fix` subcommand re-scans current filesystem as "after" state — only "before" snapshot is stored | Simpler workflow: user manages one snapshot file. Current filesystem IS the after state after rearrangement | Require separate before/after snapshot files (extra step, confusion about ordering) |
| D7 | Include audio metadata for ALL samples, not just referenced ones | Research §OQ2. Metadata on unused samples helps decision-making (keep/delete). Overhead trivial at ~1000 files | Metadata only for referenced samples (misses manifest purpose) |
| D8 | All-or-none reference fixing for v1 | Research §OQ3. Simpler implementation. User can re-run after resolving issues | Per-reference accept/skip (complex UI, deferred to future) |
| D9 | Flat CSV structure — one row per sample | Research §OQ5. Directly usable in spreadsheet tools. Counts as numeric columns; song lists as delimited strings | Nested/multi-row (not spreadsheet-friendly) |
| D10 | Minimal hand-crafted test fixture XMLs covering all 5 reference patterns | Small, focused fixtures are faster and less brittle than real files. Each fixture covers specific patterns with comments | Using real DELUGE/ XMLs (too large, brittle, change over time) |
| D11 | Format detection and preservation on XML write — element-style stays element-style, attribute-style stays attribute-style | Research §9 critical requirement. `lxml` preserves structure naturally when updating attributes/text in-place | Rewrite all refs to one format (changes XML structure unnecessarily, noisy git diffs) |
| D12 | Makefile for workflow orchestration | User preference. Simple, no dependencies beyond `make`. Wraps `uv run` commands | Bash wrapper scripts (less standard), Python CLI with subcommands (over-engineered for orchestration) |
| D13 | Snapshot format: JSON with `hash → [paths]` mapping | Naturally groups duplicate content (same hash, multiple paths). JSON is human-inspectable and Python-native | `path → hash` (doesn't group duplicates), CSV (less structured) |
| D14 | Defer `SampleCategory` and folder-based categorisation to a future version | Categorisation infers from folder structure which is about to be rearranged — output would be immediately stale. Core value is usage tracking and audio metadata, not path-based inference. Can be added later once folder structure stabilises | Build categorisation in v1 (scope creep, folder-dependent) |

## Technical Specification

### Language and Tooling

| Item | Choice | Notes |
|------|--------|-------|
| Language | Python 3.12+ | Per `.python-version` pin. Standard: `standards/languages/python/core.md` |
| Package Manager | `uv` | Standard: `standards/languages/python/tooling.md` |
| Linter/Formatter | Ruff | Standard: `standards/languages/python/tooling.md` |
| Type Checker | mypy (CI), Pylance (IDE) | Standard: `standards/languages/python/tooling.md` |
| Test Framework | pytest | Standard: `standards/languages/python/tooling.md` |
| XML Parsing | `lxml >=5.0.0` | Standard: `standards/languages/python/core.md` §XML Handling |
| Audio Metadata | `wave` (stdlib) | Research §3.2 — zero dependency, WAV-only |
| Hashing | `hashlib` (stdlib) | Research §4.1 — SHA256 |
| Env Loading | `python-dotenv` | Standard: `standards/languages/python/core.md` §Configuration |
| CLI Parsing | `argparse` (stdlib) | Standard: `standards/languages/python/core.md` §Entry Point |

### Architecture

#### Module Structure

```
scripts/
├── .env.example              # Updated — add DELUGE_ROOT
├── .env                      # Gitignored — user's local config
├── .python-version           # "3.12"
├── pyproject.toml            # Dependencies, tool config (ruff, mypy, pytest)
├── Makefile                  # Workflow orchestration
├── generate_manifest.py      # Script 1: Sample manifest generator
├── fix_references.py         # Script 2: Reference fixer (snapshot + fix subcommands)
├── verify_references.py      # Script 3: Reference verifier
├── sample_usage.py           # Script 4: Single-sample usage lookup
├── lib/
│   ├── __init__.py
│   ├── deluge_sdk.py         # XML parsing, reference extraction, reference updating
│   ├── sample_utils.py       # SHA256 hashing, WAV metadata
│   └── cli_utils.py          # Env loading, dry-run/confirm workflow, output formatting
└── tests/
    ├── conftest.py           # Shared fixtures (paths to fixture files, tmp_path helpers)
    ├── fixtures/             # Test XML files (minimal, hand-crafted)
    │   ├── element_kit.xml
    │   ├── element_synth_multisample.xml
    │   ├── attribute_kit.xml
    │   ├── attribute_synth_multisample.xml
    │   ├── song_with_clips.xml
    │   └── empty_refs.xml
    ├── test_deluge_sdk.py
    ├── test_sample_utils.py
    └── test_cli_utils.py
```

#### Key Design Patterns

1. **Shared library** — All XML parsing and reference logic lives in `lib/deluge_sdk.py`. Scripts import from it; they never parse XML directly.
2. **Dataclass API** — Typed return values (`SampleRef`, `WavMetadata`) for all library functions.
3. **Compute-then-confirm** — XML-modifying scripts compute all changes first, hold in memory, preview, then apply on confirmation. No re-scanning.
4. **Entry point pattern** — All scripts use `def main(argv: list[str] | None = None) -> None` with `if __name__ == "__main__"` guard per Python Core Standard.

#### Core Data Types

```python
@dataclass
class SampleRef:
    """A single sample reference found in an XML file."""
    path: str               # e.g. "SAMPLES/DRUMS/Kick/808 Kick.wav"
    xml_file: Path          # Absolute path to the XML file containing this reference
    xml_type: str           # "kit" | "synth" | "song"
    instrument_name: str    # Preset/sound name (e.g. "K01Perc2", "Rhythmace Kick")
    instrument_folder: str  # presetFolder for songs (e.g. "KITS/KERERU"), empty for standalone
    ref_type: str           # "fileName-element" | "fileName-attribute" | "filePath-attribute"
    element_tag: str        # "osc1" | "osc2" | "sampleRange" | "audioClip"

@dataclass
class WavMetadata:
    """Audio metadata extracted from a WAV file."""
    duration_seconds: float
    sample_rate: int
    channels: int
    bit_depth: int

```

### Interface Design

#### Inputs

| Script | CLI Arguments | Environment |
|--------|--------------|-------------|
| `generate_manifest.py` | `--output-dir` (optional, default `docs/manifests/`) | `DELUGE_ROOT` |
| `fix_references.py snapshot` | _(none)_ | `DELUGE_ROOT` |
| `fix_references.py fix` | `--snapshot <path>` (required), `--apply` (skip prompt) | `DELUGE_ROOT` |
| `verify_references.py` | _(none)_ | `DELUGE_ROOT` |
| `sample_usage.py` | `<sample_path>` (positional, required) | `DELUGE_ROOT` |

All scripts load `DELUGE_ROOT` from `scripts/.env` using `python-dotenv`, falling back to `<repo_root>/DELUGE` if unset. Repo root is derived from script location: `Path(__file__).resolve().parent.parent`.

#### Outputs

| Script | File Output | Console Output |
|--------|-------------|----------------|
| `generate_manifest.py` | `docs/manifests/sample-manifest-<YYYY-MM-DD>.json` + `.csv` | Summary: total samples, referenced count, unreferenced count |
| `fix_references.py snapshot` | `docs/manifests/snapshot-<YYYY-MM-DD>.json` | Summary: files hashed, duplicate warnings, snapshot path |
| `fix_references.py fix` | Modified XML files (on confirm) | Preview of all changes + errors, then apply summary |
| `verify_references.py` | _(none)_ | Reference check results, directory check results, pass/fail summary |
| `sample_usage.py` | _(none)_ | Detailed usage listing grouped by XML type |

#### Error Handling Strategy

| Scenario | Behaviour |
|----------|-----------|
| Non-existent `DELUGE_ROOT` | `SystemExit` with clear error message |
| No XMLs found | Warning (not error) — empty DELUGE/ is valid |
| Unreadable WAV file | Log warning, continue. Metadata fields set to `None` |
| Malformed XML | Log error with filename, skip file, continue processing remaining files |
| Broken reference in fix preview | Flag as **ERROR** — prominently displayed, distinct from fixable changes |
| Ambiguous hash mapping | Flag as **WARNING** — user must resolve manually |
| Deleted sample still referenced | Flag as **ERROR** — user has made a mistake, must resolve before deploying to hardware |

#### User Interaction Model

| Script | Interaction |
|--------|-------------|
| `generate_manifest.py` | Non-interactive — generate and exit |
| `fix_references.py fix` | Interactive — compute → preview → prompt `"Apply N changes to M files? [y/N]"` → apply. `--apply` skips prompt |
| `verify_references.py` | Non-interactive — report and exit with code 0 (pass) or 1 (fail) |
| `sample_usage.py` | Non-interactive — report and exit |

### Integration Points

| Integration | Notes |
|-------------|-------|
| **Existing `.env.example`** | Add `DELUGE_ROOT=./DELUGE` line. Preserve existing variables for future scripts |
| **`docs/manifests/` directory** | Created by scripts if it doesn't exist. Manifests and snapshots live here |
| **Git workflow** | All XML changes captured by git. No script-level backup needed (per user: "I am relying on git for backups") |
| **Future scripts** | `deluge_sdk.py` functions (`find_all_xml_files`, `extract_sample_refs`, `detect_xml_type`) designed for reuse by planned scripts like `rename_songs.py`, `sd-to-repo.py` |
| **SD Card safety** | All scripts operate on `DELUGE/` in the repo only. No SD card write paths. Compliant with `standards/project.md` |

## Cross-Cutting Concerns

| Concern (from Research) | Plan Mitigation |
|------------------------|-----------------|
| **XML Parsing Library** — central dependency, changes affect all scripts | `deluge_sdk.py` provides a version-agnostic API. Callers pass a `Path` and get `list[SampleRef]` — they never see firmware versions or format eras. Both read and write in one module. Comprehensive tests cover all 5 patterns |
| **Path Relativity** — all sample paths relative to DELUGE/ | `cli_utils.get_deluge_root()` provides the resolved path. All scripts use it consistently. Paths in XMLs stored as-is, never converted to absolute |
| **Git Integration** — changes captured automatically | Scripts do not create backups. XML modifications immediately visible in `git diff`. User commits when satisfied |
| **SD Card Safety** — scripts must never write to physical SD card | No script accepts an SD card path for writing. `DELUGE_ROOT` defaults to local repo copy. Compliant with `standards/project.md` |
| **Future Scripts** — library should support reuse | `deluge_sdk.py` exposes general-purpose functions: `find_all_xml_files()`, `extract_sample_refs()`, `detect_xml_type()`. Useful for `rename_songs.py` etc. |
| **Case Sensitivity** — paths must be preserved exactly | Library never normalises case. Comparisons use exact string matching. File existence checks are case-sensitive on Linux |

## Risk Mitigation

| Risk (from Research) | Plan Mitigation | Residual Risk |
|---------------------|-----------------|---------------|
| XML formatting corrupted on write | `lxml` updates attributes/text in-place, preserving structure. Round-trip tests for every format era. `verify_references.py` run after every fix | Low — lxml reliable; tests catch regressions |
| Missed sample reference type | All 5 patterns tested with dedicated fixtures. `verify_references.py` as post-fix validation | Low — comprehensively documented patterns |
| Hash collision | No mitigation needed — SHA256 collision practically impossible | Negligible |
| Duplicate file content (ambiguous mapping) | `fix` detects hashes with multiple paths, flags as ambiguous. User resolves manually | Low — flagged prominently |
| Large song XMLs cause slow parsing | `lxml` handles large files efficiently. No optimisation needed at expected scale | None |
| Deleted sample still referenced | `fix` flags deleted-but-referenced as ERRORS in preview. User must resolve | Low — explicit error surfacing |
| CLIPS/RECORD/RESAMPLE directories deleted | `verify_references.py` checks these directories exist and have no subdirectories | Low — automated check |
| Case sensitivity mismatch | Paths preserved exactly, never normalised. File existence checks case-exact on Linux | Low |

## Implementation Roadmap

### Phase 1: Project Setup + Shared Library

> **Goal:** Establish project scaffolding, core XML parsing module (`deluge_sdk.py`), env loading (`cli_utils.py`), and test infrastructure with fixtures covering all 5 reference patterns.
> **Prerequisites:** None — this is the foundation.

#### Task 1.1: Project Scaffolding

- **Description:** Create the directory structure, configuration files, and install dependencies.
- **Outputs:** Working Python project — `uv sync`, `ruff check`, and `pytest` all succeed.
- **Acceptance Criteria:**
  - [ ] `scripts/pyproject.toml` created with project metadata, dependencies (`lxml`, `python-dotenv`), and dev dependencies (`ruff`, `mypy`, `pytest`, `lxml-stubs`)
  - [ ] Ruff configuration in `pyproject.toml` per Python Tooling Standard (rule sets: E, W, F, I, B, C4, UP, ARG, SIM, PTH)
  - [ ] mypy configuration in `pyproject.toml` per Python Tooling Standard (`strict = true`)
  - [ ] pytest configuration in `pyproject.toml` (`testpaths = ["tests"]`)
  - [ ] `scripts/.python-version` created with `3.12`
  - [ ] `scripts/.env.example` updated — add `DELUGE_ROOT=./DELUGE` while preserving existing variables
  - [ ] `scripts/lib/__init__.py` created (empty)
  - [ ] `scripts/tests/conftest.py` created (empty initially)
  - [ ] `scripts/tests/fixtures/` directory created
  - [ ] `uv sync` succeeds
  - [ ] `uv run ruff check .` passes (no files to lint yet is OK)
  - [ ] `uv run pytest` runs without errors (0 tests collected)
- **Implementation Notes:**
  > _(Space for implementer notes)_

#### Task 1.2: Test Fixtures

- **Description:** Create minimal hand-crafted XML files covering all 5 reference patterns plus empty-reference edge cases. These fixtures are the foundation for all subsequent tests.
- **Outputs:** 6 fixture XML files in `scripts/tests/fixtures/`
- **Acceptance Criteria:**
  - [ ] `element_kit.xml` — element-style kit with `<fileName>` elements on `<osc1>` and `<osc2>`, one with a sample and one empty (pattern 1)
  - [ ] `element_synth_multisample.xml` — element-style synth with `<sampleRanges>` containing `<fileName>` elements (patterns 1, 2)
  - [ ] `attribute_kit.xml` — attribute-style kit with `fileName` attributes on `<osc1>` and `<osc2>` (pattern 3). One osc element should use `type="wavetable"` with a `fileName` to verify extraction is not filtered on `type="sample"`
  - [ ] `attribute_synth_multisample.xml` — attribute-style synth with `<sampleRanges>` containing `fileName` attributes (patterns 3, 4)
  - [ ] `song_with_clips.xml` — attribute-style song with embedded kit (pattern 3), embedded synth with sampleRanges (pattern 4), and `<audioClip>` with `filePath` (pattern 5)
  - [ ] `empty_refs.xml` — XML with `<fileName></fileName>`, `fileName=""`, and an osc element missing the `fileName` attribute entirely
  - [ ] Each fixture is minimal — smallest valid XML that exercises the target pattern(s)
  - [ ] Each fixture includes a comment header documenting which patterns it covers
- **Implementation Notes:**
  > _(Space for implementer notes)_

#### Task 1.3: `cli_utils.py` — Environment and Output Utilities

- **Description:** Create shared CLI utilities: environment loading, and the dry-run/confirm workflow pattern. These are used by all scripts.
- **Outputs:** `scripts/lib/cli_utils.py` with tests in `scripts/tests/test_cli_utils.py`
- **Acceptance Criteria:**
  - [ ] `get_deluge_root() -> Path` — loads `DELUGE_ROOT` from `scripts/.env` via `python-dotenv`, falls back to `<repo_root>/DELUGE`, validates directory exists
  - [ ] Repo root derived as `Path(__file__).resolve().parent.parent` (from `lib/` up to `scripts/` up to repo root)
  - [ ] Raises `SystemExit` with clear message if `DELUGE_ROOT` directory doesn't exist
  - [ ] `confirm_apply(message: str) -> bool` — print message, prompt `[y/N]`, return boolean
  - [ ] Tests verify: env loading, fallback when env unset, `SystemExit` on missing directory (using `tmp_path`)
- **Implementation Notes:**
  > _(Space for implementer notes)_

#### Task 1.4: `deluge_sdk.py` — XML Discovery and Reference Extraction (Read-Only)

- **Description:** Build the core XML parsing module with read-only operations: finding XML files, detecting XML types, and extracting sample references from all 5 patterns. Write operations are added in Phase 4.
- **Outputs:** `scripts/lib/deluge_sdk.py` with tests in `scripts/tests/test_deluge_sdk.py`

##### Sub-task 1.4.1: XML File Discovery

- **Description:** Implement `find_all_xml_files()` to recursively locate all `.XML` files in KITS/, SYNTHS/, SONGS/.
- **Acceptance Criteria:**
  - [ ] `find_all_xml_files(deluge_root: Path) -> list[Path]` — returns absolute paths to all `.XML` files in `KITS/`, `SYNTHS/`, `SONGS/` (recursive)
  - [ ] Case-insensitive extension matching (`.XML`, `.xml`)
  - [ ] Handles missing subdirectories gracefully (e.g. no `SONGS/` → empty list, not error)
  - [ ] Test with minimal directory structure using `tmp_path` pytest fixture
- **Implementation Notes:**
  > _(Space for implementer notes)_

##### Sub-task 1.4.2: XML Type Detection

- **Description:** Implement helper to detect XML type (kit, synth, song) from file path and/or root element.
- **Acceptance Criteria:**
  - [ ] `detect_xml_type(xml_path: Path) -> str` — returns `"kit"`, `"synth"`, or `"song"`
  - [ ] Primary: path-based detection — files under `KITS/` → kit, `SYNTHS/` → synth, `SONGS/` → song
  - [ ] Fallback: content-based — root element `<kit>` → kit, `<sound>` → synth, `<song>` → song
  - [ ] Handles both old format (root element is the type) and new format (root element has `firmwareVersion` attribute)
  - [ ] Tests cover path-based and content-based detection for all fixture files
- **Implementation Notes:**
  > _(Space for implementer notes)_

##### Sub-task 1.4.3: Reference Extraction — Core Logic

- **Description:** Implement `extract_sample_refs()` to find all sample references in a single XML file, handling all 5 reference patterns from Research §1.5.
- **Acceptance Criteria:**
  - [ ] `extract_sample_refs(xml_path: Path) -> list[SampleRef]`
  - [ ] Pattern 1: `<fileName>text</fileName>` element on `<osc1>`/`<osc2>` (element-style)
  - [ ] Pattern 2: `<fileName>text</fileName>` element within `<sampleRange>` (element-style)
  - [ ] Pattern 3: `fileName="..."` attribute on `<osc1>`/`<osc2>` (attribute-style)
  - [ ] Pattern 4: `fileName="..."` attribute on `<sampleRange>` (attribute-style)
  - [ ] Pattern 5: `filePath="..."` attribute on `<audioClip>` (songs only)
  - [ ] Skips empty references: `<fileName></fileName>`, `fileName=""`, missing attribute
  - [ ] Preserves original path case exactly
  - [ ] `ref_type` distinguishes format: `"fileName-element"`, `"fileName-attribute"`, `"filePath-attribute"`
  - [ ] Extraction must NOT filter on `type="sample"` — must capture `fileName` from oscillators regardless of osc `type` value (including `type="wavetable"`)
  - [ ] Tests cover all 6 fixture files, verifying correct count and paths extracted
- **Implementation Notes:**
  > _(Space for implementer notes)_

##### Sub-task 1.4.4: Instrument Name Extraction

- **Description:** For each `SampleRef`, extract the enclosing instrument name. Logic differs by XML type:
  - **Standalone kits/synths:** XML filename without extension
  - **Songs — embedded kits:** `presetName` attribute on the enclosing `<kit>` element
  - **Songs — embedded synths:** `presetName` attribute on the `<sound>` element that is a direct child of `<instruments>`
  - **Songs — audioClip:** `trackName` attribute on the `<audioClip>` element
- **Acceptance Criteria:**
  - [ ] `instrument_name` correctly populated for all `SampleRef` instances
  - [ ] `instrument_folder` populated from `presetFolder` attribute for song-embedded instruments; empty string for standalone kits/synths and audioClips
  - [ ] Song fixture tests verify embedded kit, synth, and audioClip instrument names
  - [ ] Standalone kit/synth fixture tests verify filename-based instrument names
  - [ ] Graceful fallback if name attribute is missing (e.g. `"unknown"`)
- **Implementation Notes:**
  > _(Space for implementer notes)_

---

### Phase 2: Reference Verifier

> **Goal:** Build `verify_references.py` — the simplest script. Validates the SDK works correctly and provides immediate standalone value.
> **Prerequisites:** Phase 1 complete (`deluge_sdk.py` and `cli_utils.py` working).

#### Task 2.1: `verify_references.py`

- **Description:** Standalone reference verifier that checks all XML sample references resolve to existing files and validates CLIPS/RECORD/RESAMPLE directory constraints.
- **Outputs:** `scripts/verify_references.py` with tests

##### Sub-task 2.1.1: Reference Existence Checking

- **Description:** For every `SampleRef` extracted from all XMLs, verify the referenced file exists on disk.
- **Acceptance Criteria:**
  - [ ] Uses `deluge_sdk.find_all_xml_files()` and `extract_sample_refs()` to collect all references
  - [ ] Checks each `SampleRef.path` exists relative to `DELUGE_ROOT`
  - [ ] Collects broken references: XML file, instrument name, missing sample path
  - [ ] Groups broken references by XML file for readable output
  - [ ] Reports summary: total references checked, total broken
- **Implementation Notes:**
  > _(Space for implementer notes)_

##### Sub-task 2.1.2: CLIPS/RECORD/RESAMPLE Directory Validation

- **Description:** Check that CLIPS/, RECORD/, RESAMPLE/ directories exist under SAMPLES/ and contain no subdirectories.
- **Acceptance Criteria:**
  - [ ] Checks `SAMPLES/CLIPS/`, `SAMPLES/RECORD/`, `SAMPLES/RESAMPLE/` exist under `DELUGE_ROOT`
  - [ ] Missing directories reported as warnings (they may not exist yet on a fresh setup)
  - [ ] Existing directories checked for subdirectories — any found are reported as errors
  - [ ] Tests using `tmp_path` for both passing and failing scenarios
- **Implementation Notes:**
  > _(Space for implementer notes)_

##### Sub-task 2.1.3: CLI Entry Point and Exit Codes

- **Description:** Wire up `main(argv)` with output formatting and exit codes.
- **Acceptance Criteria:**
  - [ ] `main(argv)` entry point per Python Core Standard
  - [ ] Exit code 0 = all references valid, all directory checks pass
  - [ ] Exit code 1 = one or more broken references or directory issues
  - [ ] Console output separates: reference check results → directory check results → summary line
  - [ ] Test for pass scenario and fail scenario
- **Implementation Notes:**
  > _(Space for implementer notes)_

---

### Phase 3: Sample Manifest Generator

> **Goal:** Build `generate_manifest.py` and `sample_utils.py` — full manifest with audio metadata and usage tracking.
> **Prerequisites:** Phase 2 complete (`deluge_sdk` proven end-to-end, verifier available).

#### Task 3.1: `sample_utils.py` — Hashing and Metadata

- **Description:** Build the sample utilities module.
- **Outputs:** `scripts/lib/sample_utils.py` with tests in `scripts/tests/test_sample_utils.py`

##### Sub-task 3.1.1: SHA256 File Hashing

- **Description:** Chunked SHA256 hashing for sample files (Research §4.2).
- **Acceptance Criteria:**
  - [ ] `hash_file(path: Path) -> str` — returns hex digest
  - [ ] Chunked reading (8192 bytes) for memory efficiency
  - [ ] Test with a known file producing a known hash
- **Implementation Notes:**
  > _(Space for implementer notes)_

##### Sub-task 3.1.2: WAV Metadata Extraction

- **Description:** Extract audio properties from WAV files using `wave` stdlib (Research §3.2).
- **Acceptance Criteria:**
  - [ ] `get_wav_metadata(path: Path) -> WavMetadata | None`
  - [ ] Extracts: `duration_seconds` (frames/rate, rounded 2dp), `sample_rate`, `channels`, `bit_depth` (sampwidth × 8)
  - [ ] Returns `None` with logged warning for corrupt/unreadable files
  - [ ] Test with a small WAV file (generate programmatically in test or include a tiny fixture)
- **Implementation Notes:**
  > _(Space for implementer notes)_

#### Task 3.2: `generate_manifest.py` — Manifest Generation

- **Description:** Full sample manifest combining metadata and usage tracking.
- **Outputs:** `scripts/generate_manifest.py`

##### Sub-task 3.2.1: Sample Scanning

- **Description:** Walk `DELUGE/SAMPLES/` for all audio files, extract metadata.
- **Acceptance Criteria:**
  - [ ] Recursive scan of `SAMPLES/` for `.wav` and `.WAV` files (case-insensitive extension)
  - [ ] For each: relative path (from `DELUGE/`), file size (bytes), mtime, SHA256 hash, WAV metadata
  - [ ] Flag non-WAV files encountered in `SAMPLES/` as warnings
- **Implementation Notes:**
  > _(Space for implementer notes)_

##### Sub-task 3.2.2: Usage Tracking — Reference Map

- **Description:** Build a map: for each sample path → which XMLs reference it and with what instrument context.
- **Acceptance Criteria:**
  - [ ] Scan all XMLs using `deluge_sdk` functions
  - [ ] Group `SampleRef` instances by `path`
  - [ ] **Songs:** List ALL referencing songs, each with its embedded instrument name(s) using the sample
  - [ ] **Songs count:** Number of distinct song files (a song counts as 1 even if multiple embedded instruments use the sample)
  - [ ] **Standalone kits:** List first standalone kit as example, count total
  - [ ] **Standalone synths:** List first standalone synth as example, count total
  - [ ] Unreferenced samples identified (present on disk but zero XML references)
- **Implementation Notes:**
  > _(Space for implementer notes)_

##### Sub-task 3.2.3: JSON Output

- **Description:** Generate dated JSON manifest.
- **Acceptance Criteria:**
  - [ ] Path: `docs/manifests/sample-manifest-<YYYY-MM-DD>.json`
  - [ ] Creates `docs/manifests/` if it doesn't exist
  - [ ] Per-sample entry: `path`, `file_size_bytes`, `mtime`, `hash`, `duration_seconds`, `sample_rate`, `channels`, `bit_depth`, `usage` object
  - [ ] `usage` object: `song_count`, `kit_count`, `synth_count`, `songs` (list of `{name, instruments: [...]}`), `first_kit`, `first_synth`
  - [ ] Top-level metadata: `generated`, `deluge_root`, `total_samples`, `total_referenced`, `total_unreferenced`
  - [ ] Pretty-printed (indent=2)
- **Implementation Notes:**
  > _(Space for implementer notes)_

##### Sub-task 3.2.4: CSV Output

- **Description:** Flat CSV companion for spreadsheet use.
- **Acceptance Criteria:**
  - [ ] Path: `docs/manifests/sample-manifest-<YYYY-MM-DD>.csv`
  - [ ] One row per sample
  - [ ] Columns: `path`, `file_size_bytes`, `duration_seconds`, `sample_rate`, `channels`, `bit_depth`, `mtime`, `hash`, `song_count`, `kit_count`, `synth_count`, `songs`, `first_kit`, `first_synth`
  - [ ] List columns (songs) use semicolon delimiter within cells
  - [ ] Uses Python `csv` module for proper escaping
- **Implementation Notes:**
  > _(Space for implementer notes)_

##### Sub-task 3.2.5: Console Summary and Entry Point

- **Description:** CLI entry point with summary output.
- **Acceptance Criteria:**
  - [ ] `main(argv)` entry point with `--output-dir` argument (default: `docs/manifests/`)
  - [ ] Console summary: total samples scanned, referenced/unreferenced counts, output file paths
  - [ ] Warnings for non-WAV files, unreadable WAVs
- **Implementation Notes:**
  > _(Space for implementer notes)_

---

### Phase 4: Reference Fixer

> **Goal:** Build `fix_references.py` with `snapshot` and `fix` subcommands — the most complex script. Adds write capability to `deluge_sdk.py`.
> **Prerequisites:** Phase 3 complete (`sample_utils.hash_file` available, SDK extraction proven).

#### Task 4.1: `deluge_sdk.py` — Reference Updating (Write)

- **Description:** Add write capability to the SDK: update sample references in XML files while preserving format and structure.
- **Outputs:** `update_sample_refs()` in `scripts/lib/deluge_sdk.py` with round-trip tests
- **Acceptance Criteria:**
  - [ ] `update_sample_refs(xml_path: Path, mapping: dict[str, str]) -> int` — update all matching refs in one file, return count updated
  - [ ] Element-style `<fileName>`: updates element text content
  - [ ] Attribute-style `fileName`: updates attribute value
  - [ ] Attribute-style `filePath` on `<audioClip>`: updates attribute value
  - [ ] Only modifies references where the current path matches a key in `mapping`
  - [ ] Preserves original XML structure, attributes, and declaration
  - [ ] Non-matching references are untouched
  - [ ] **Round-trip tests** for every fixture: parse → update one ref → write → parse again → verify only the targeted ref changed
  - [ ] Test with mapping containing paths not present in the file (no changes, no errors)
- **Implementation Notes:**
  > _(Space for implementer notes)_

#### Task 4.2: `fix_references.py snapshot` Subcommand

- **Description:** Hash all samples and save the state to a dated JSON snapshot file.
- **Outputs:** `snapshot` subcommand in `scripts/fix_references.py`
- **Acceptance Criteria:**
  - [ ] Scans `DELUGE/SAMPLES/` for all `.wav`/`.WAV` files
  - [ ] Computes SHA256 hash for each (via `sample_utils.hash_file`)
  - [ ] Saves to `docs/manifests/snapshot-<YYYY-MM-DD>.json`
  - [ ] Format: `{ "date": "...", "deluge_root": "...", "hashes": { "<hash>": ["<path>", ...], ... } }`
  - [ ] Console: total files hashed, snapshot path, warnings for duplicate content (same hash, multiple paths)
  - [ ] Creates `docs/manifests/` if needed
- **Implementation Notes:**
  > _(Space for implementer notes)_

#### Task 4.3: `fix_references.py fix` Subcommand

- **Description:** Load before-snapshot, re-scan current state, compute migration map, find broken references, preview, confirm, apply.
- **Outputs:** `fix` subcommand in `scripts/fix_references.py`

##### Sub-task 4.3.1: Migration Map Computation

- **Description:** Build the migration map from before-snapshot vs current filesystem.
- **Acceptance Criteria:**
  - [ ] Load before-snapshot from `--snapshot <path>`
  - [ ] Hash all current samples to build "after" state
  - [ ] Compare hashes: for each hash present in both, map old path(s) to new path(s)
  - [ ] Categorise results: **moved** (1 old → 1 new, fixable), **deleted** (in before, not in after), **added** (in after, not in before), **ambiguous** (1 hash → multiple paths in before or after)
  - [ ] Migration map: `dict[str, str]` — `{ old_path: new_path }` for unambiguous moves
- **Implementation Notes:**
  > _(Space for implementer notes)_

##### Sub-task 4.3.2: Broken Reference Detection

- **Description:** Find XML references that need updating or are broken.
- **Acceptance Criteria:**
  - [ ] Extract all sample refs from all XMLs
  - [ ] For each ref: if path is in migration map → **planned change** (old → new)
  - [ ] For each ref: if path is in "deleted" set → **error** (file removed but still referenced)
  - [ ] For each ref: if path is in "ambiguous" set → **warning** (cannot auto-resolve)
  - [ ] Build structured results: `changes: list[PlannedChange]`, `errors: list[FixError]`
- **Implementation Notes:**
  > _(Space for implementer notes)_

##### Sub-task 4.3.3: Preview and Confirm Workflow

- **Description:** Display all changes and errors, then prompt for confirmation per D5.
- **Acceptance Criteria:**
  - [ ] Preview changes grouped by XML file: `file.XML: "old/path" → "new/path"` (× N refs)
  - [ ] Errors displayed prominently (section header: "ERRORS — Requires Manual Resolution")
  - [ ] Ambiguous warnings displayed with context (which paths share the hash)
  - [ ] Summary line: "N changes across M files. X errors, Y warnings."
  - [ ] If errors exist: additional warning recommending resolution before applying
  - [ ] Prompt: `"Apply N changes to M files? [y/N]:"` — or skip prompt if `--apply`
  - [ ] On confirm: apply via `deluge_sdk.update_sample_refs()` for each affected XML file
  - [ ] On decline: `"No changes applied."`
  - [ ] Post-apply summary: files modified, total references updated
- **Implementation Notes:**
  > _(Space for implementer notes)_

##### Sub-task 4.3.4: CLI Entry Point with Subcommands

- **Description:** Wire up argparse with `snapshot` and `fix` subcommands.
- **Acceptance Criteria:**
  - [ ] `fix_references.py snapshot` — runs snapshot
  - [ ] `fix_references.py fix --snapshot <path>` — runs fix with before-snapshot
  - [ ] `fix_references.py fix --snapshot <path> --apply` — fix and apply without prompt
  - [ ] Missing `--snapshot` on `fix` → clear error message
  - [ ] `--help` and per-subcommand help text
  - [ ] Exit code 0 = success (changes applied or nothing to do), exit code 1 = errors found
- **Implementation Notes:**
  > _(Space for implementer notes)_

---

### Phase 5: Sample Usage Lookup + Makefile + Integration

> **Goal:** Build the final utility script, Makefile, and verify all scripts work together end-to-end.
> **Prerequisites:** Phase 4 complete (all core scripts functional).

#### Task 5.1: `sample_usage.py` — Detailed Usage Lookup

- **Description:** Single-sample usage tool for deep investigation when the manifest shows a sample is referenced.
- **Outputs:** `scripts/sample_usage.py`
- **Acceptance Criteria:**
  - [ ] Positional argument: sample path relative to `DELUGE/` (e.g. `SAMPLES/DRUMS/Kick/808 Kick.wav`)
  - [ ] Scans all XMLs using `deluge_sdk` for references matching the given path
  - [ ] For each match: XML file, XML type, instrument name, element context (osc1/osc2/sampleRange/audioClip)
  - [ ] Output grouped by type: Songs → Kits → Synths
  - [ ] Summary: total references found
  - [ ] If sample file doesn't exist on disk: warning (but still search XMLs — path may be in old references)
  - [ ] Exit code 0 = found references, 1 = no references found
- **Implementation Notes:**
  > _(Space for implementer notes)_

#### Task 5.2: Makefile — Workflow Orchestration

- **Description:** Create a Makefile wrapping all scripts with `uv run`.
- **Outputs:** `scripts/Makefile`
- **Acceptance Criteria:**
  - [ ] `make manifest` — `uv run python generate_manifest.py`
  - [ ] `make verify` — `uv run python verify_references.py`
  - [ ] `make snapshot` — `uv run python fix_references.py snapshot`
  - [ ] `make fix SNAPSHOT=<path>` — `uv run python fix_references.py fix --snapshot $(SNAPSHOT)`
  - [ ] `make usage SAMPLE=<path>` — `uv run python sample_usage.py $(SAMPLE)`
  - [ ] `make pre-rearrange` — snapshot, then manifest, then verify (sequential)
  - [ ] `make post-rearrange SNAPSHOT=<path>` — fix, then verify (sequential)
  - [ ] `make lint` — `uv run ruff check .`
  - [ ] `make test` — `uv run pytest`
  - [ ] Default target (`make` with no args) displays help listing available targets
  - [ ] `.PHONY` declarations for all targets
- **Implementation Notes:**
  > _(Space for implementer notes)_

#### Task 5.3: Integration Verification

- **Description:** Run all scripts against the real `DELUGE/` directory to verify end-to-end functionality.
- **Acceptance Criteria:**
  - [ ] `make verify` runs successfully against real data — check output makes sense
  - [ ] `make manifest` generates valid JSON and CSV from real data — spot-check entries
  - [ ] `make usage SAMPLE=<known-sample>` returns expected references for a sample known to be in use
  - [ ] All scripts produce clear, well-formatted console output
  - [ ] Edge cases handled: scripts cope with the full diversity of firmware versions in real XMLs
  - [ ] `uv run ruff check .` passes on all code
  - [ ] `uv run pytest` passes all tests
- **Implementation Notes:**
  > _(Space for implementer notes)_

## Progress Tracker

| Phase | Status | Tasks Complete | Notes |
|-------|--------|---------------|-------|
| Phase 1: Project Setup + Shared Library | Not Started | 0/4 | |
| Phase 2: Reference Verifier | Not Started | 0/1 | |
| Phase 3: Sample Manifest Generator | Not Started | 0/2 | |
| Phase 4: Reference Fixer | Not Started | 0/3 | |
| Phase 5: Usage Lookup + Makefile + Integration | Not Started | 0/3 | |
