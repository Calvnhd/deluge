# Research: Sample Library Overview Tool

> **Document Type:** Research
> **Date:** 21 April 2026
> **Request:** Expand `list_samples.py` into a comprehensive sample library overview tool (`sample_overview.py`) that provides insightful usage analysis, file info, and summary statistics across the Deluge SD card backup.
> **Pipeline:** Research → Plan → Implement

## Executive Summary

The existing `list_samples.py` prints a flat list of deduplicated sample paths from XMLs. All the building blocks for a comprehensive overview tool already exist in `deluge_lib/`: sample reference extraction with full metadata (`SampleRef`), filesystem scanning with size data (`scan_tree`/`FileEntry`), normalised path matching (`normalise_key`), and existing-sample discovery (`get_existing_samples`). The recommended approach is a new `sample_overview.py` script with subcommands (`summary`, `unused`, `missing`, `usage`) backed by a shared analysis module, producing aligned plain-text tables to stdout. Manifest/snapshot integration is not recommended — the overhead outweighs the benefit at the ~6000-file scale, and the tool runs in seconds without caching.

## Objectives

- Determine what analysis capabilities are already available vs what needs building
- Evaluate CLI design: subcommands vs flags
- Assess whether manifest/snapshot integration adds value
- Identify the right output format (plain text, structured data, or both)
- Evaluate performance implications at ~6000 sample files
- Recommend a design that fits existing codebase conventions

## Feature Overview

### Purpose and Value

The user maintains a ~6000-file sample library on a Deluge SD card backup. Understanding what's in use, what's unused, and where each sample appears is currently impossible without manually searching XMLs. This tool provides:

- **Disk space insight** — identify unreferenced samples for potential cleanup
- **Dependency awareness** — know which presets break if a sample is moved or deleted
- **Library health** — detect missing samples (referenced in XML but not on disk)
- **Quick overview** — summary stats at a glance

### Primary Use Cases

1. **Library cleanup** — "What samples can I safely delete?" → `unused` subcommand
2. **Pre-reorganisation** — "Which presets reference this sample?" → `usage` subcommand
3. **Health check** — "Are any references broken?" → `missing` subcommand
4. **Overview** — "What does my library look like?" → `summary` subcommand

### Inputs and Outputs

| Input | Source |
|-------|--------|
| All XML files | `DELUGE/KITS/`, `DELUGE/SYNTHS/`, `DELUGE/SONGS/` |
| All WAV files on disk | `DELUGE/SAMPLES/` |

| Output | Destination |
|--------|-------------|
| Formatted text reports | stdout |
| Optional: file output | TBD — may add `--output` flag if useful |

### Scope

**In scope:**
- Usage analysis: referenced, unreferenced, missing samples
- Usage context: which XMLs reference each sample, frequency, exclusive vs shared
- File info: per-sample size, folder breakdowns
- Summary statistics: totals, reclaimable space, top-N lists
- Plain-text tabular output to stdout

**Out of scope:**
- Destructive actions (no cleanup/deletion — list only per user request)
- Audio metadata extraction (duration, sample rate, etc.)
- Manifest/snapshot writing (evaluated and not recommended — see Findings §4)
- Hashing (not needed for this tool's purpose)

## Existing Assets Analysis

### `deluge_lib/scanning.py` — Filesystem scanning primitives

| Export | Type | What it actually does |
|--------|------|----------------------|
| `scan_tree(root, label, file_filter)` | Function | Walks a directory tree via `os.walk`, collects stat data for matching files (.wav, .xml, or both). Returns `ScanResult` containing a dict of normalised keys → `FileEntry`. Skips `.trash` directories. Prints progress to stdout. |
| `FileEntry` | Frozen dataclass | Holds `rel_path: Path`, `size: int`, `mtime: float` for a single scanned file. |
| `ScanResult` | Dataclass | Wraps `files: dict[str, FileEntry]` — the normalised-key lookup dict. |
| `normalise_key(path)` | Function | Converts any path to lowercase with forward slashes. Used everywhere for case-insensitive matching. |
| `print_path(path)` | Function | Formats a path with forward slashes, preserving case. Cosmetic only. |
| `normalise_mtime(raw)` | Function | Truncates timestamps to FAT32's 2-second resolution for cross-filesystem comparison. |

### `deluge_lib/deluge_sdk.py` — XML parsing and sample reference extraction

| Export | Type | What it actually does |
|--------|------|----------------------|
| `extract_sample_refs(xml_path, deluge_root)` | Function | Parses a single Deluge XML and extracts all sample references across 5 reference patterns (element/attribute `fileName` on osc1/osc2/sampleRange, `filePath` on audioClip). Returns `list[SampleRef]` with full metadata: path, source XML, XML type, preset name, ref type, element tag. |
| `SampleRef` | Dataclass | Fields: `path`, `xml_file` (relative to deluge_root), `xml_type` ("kit"/"synth"/"song"), `preset_name`, `ref_type`, `element_tag`. |
| `find_all_xml_files(deluge_root)` | Function | Finds all XMLs under KITS/, SYNTHS/, SONGS/ by calling `scan_tree()` per subdirectory. Returns sorted absolute paths. Note: discards size/mtime data from the scan. |
| `get_existing_samples(deluge_root)` | Function | Builds a normalised set of all WAV paths under SAMPLES/ via `scan_tree()`. Returns `set[str]` of lowercase forward-slash paths. Used for case-insensitive existence checks. Note: discards size/mtime — only returns paths. |
| `hash_all_samples(deluge_root)` | Function | Hashes all WAVs under SAMPLES/ with SHA-256. Returns `dict[str, list[str]]` mapping digest → paths. Used by `fix_references.py` and `create_snapshot.py`. Not needed for the overview tool. |
| `hash_file(path)` | Function | SHA-256 of a single file. Not needed for the overview tool. |
| `parse_deluge_xml(xml_path)` | Function | Three-stage XML parser with fallbacks for old firmware formats and malformed files. Returns `(tree, root, recovered)`. |
| `detect_xml_type(xml_path)` | Function | Infers "kit"/"synth"/"song" from the file's directory path. |
| `default_manifests_dir()` | Function | Returns `<repo>/docs/manifests/`. |

### `deluge_lib/cli_utils.py` — Environment and config

| Export | Type | What it actually does |
|--------|------|----------------------|
| `get_deluge_root()` | Function | Loads `DELUGE_ROOT` from `.env`, validates it exists. Used by every script. |
| `get_sd_card_path()` | Function | Loads `SD_CARD_PATH` from `.env`. Not needed for overview tool. |
| `get_cloud_backup_path()` | Function | Loads `CLOUD_BACKUP_PATH` from `.env`. Not needed for overview tool. |
| `get_zip_source_path()` / `get_zip_dest_path()` | Functions | Load ZIP paths from `.env`. Not needed for overview tool. |
| `confirm_apply(prompt)` | Function | Prompts user for Y/N confirmation. Available if needed. |

### `deluge_lib/syncing.py` — Shared sync primitives

Contains `compute_sync()`, `SyncPlan`, `SyncResult`, `SyncError`, plan display and execution utilities. Used by `sync_from_sd.py`, `sync_to_sd.py`, and `sync_samples_to_cloud.py`. **Not relevant to the overview tool** but included for completeness of the library landscape.

### `deluge_lib/extraction.py` — Instrument extraction logic (WIP)

Contains `InstrumentInfo`, `ClipInfo`, `InstrumentClipGroup`, extraction transforms, and version comparison logic. Used by `extract_instruments.py`. **Not relevant to the overview tool.**

### `verify_references.py` — Reference checking

| Export | Type | What it actually does |
|--------|------|----------------------|
| `check_references(deluge_root)` | Function | Calls `find_all_xml_files()`, `extract_sample_refs()`, and `get_existing_samples()` to check every XML sample reference against disk. Returns `CheckResult` containing `total_refs`, `broken: list[BrokenRef]`, and `unextracted: list[tuple]` (paths found by regex but missed by the structured extractor). Has print statements for progress but returns a clean dataclass. |
| `BrokenRef` | Dataclass | Fields: `xml_file`, `xml_type`, `preset_name`, `sample_path`. |
| `CheckResult` | NamedTuple | Fields: `total_refs: int`, `broken: list[BrokenRef]`, `unextracted: list[tuple[Path, str]]`. |

Note: `check_references()` is a reusable function that could be called directly by the overview tool's `missing` subcommand. However, it has progress-printing baked in and does its own scanning (calls `find_all_xml_files` and `get_existing_samples` internally), so the overview tool would either need to accept the duplicated scanning or refactor it. For the overview tool, it's simpler to do the cross-referencing directly since it already has all the data from its own scan.

### `create_backup.py` — `_format_size()` utility

| Export | Type | What it actually does |
|--------|------|----------------------|
| `_format_size(size_bytes)` | Private function | Formats bytes as human-readable string (B / KB / MB / GB). Currently private to `create_backup.py`. Needs extraction to a shared location for reuse by the overview tool. |

### `pyproject.toml` — Script registration

All scripts except `list_samples.py` are registered under `[project.scripts]`:

```
deluge-sync = "sync_from_sd:main"
deluge-cloud-sync = "sync_samples_to_cloud:main"
deluge-fix = "fix_references:main"
deluge-snapshot = "create_snapshot:main"
deluge-verify = "verify_references:main"
deluge-backup = "create_backup:main"
deluge-to-sd = "sync_to_sd:main"
deluge-extract = "extract_instruments:main"
```

`list_samples.py` is NOT registered. The new `sample_overview.py` will need an entry.

### Key observations for the overview tool

1. **`get_existing_samples()` discards size data** — it calls `scan_tree()` but only returns a set of normalised paths. The overview tool needs sizes too, so it should call `scan_tree()` directly on `SAMPLES/` and keep the full `ScanResult` with `FileEntry` objects.

2. **`find_all_xml_files()` discards size/mtime data** — same issue. It calls `scan_tree()` per subdirectory but only returns paths. Fine for the overview tool since XML sizes aren't needed.

3. **No subparser pattern exists** in the codebase — every script uses flat `argparse` flags. The overview tool would be the first to use `add_subparsers()`.

4. **`check_references()` is reusable but imperfect** — it returns clean data structures but has progress printing baked in and does its own scanning. The overview tool should do its own cross-referencing rather than calling this, since it already has all the data it needs from its own scans.

5. **`.trash` directories are automatically skipped** by `scan_tree()` — the overview tool won't accidentally count trashed files.

## Findings

### 1. Existing Code Covers 80% of Data Collection

The `deluge_lib` already provides everything needed to collect raw data:

**Reference collection** — `extract_sample_refs()` returns rich `SampleRef` objects with the sample path, source XML file, XML type (kit/synth/song), preset name, reference type, and element tag. This is all the metadata needed for usage analysis.

Source: [scripts/deluge_lib/deluge_sdk.py](../scripts/deluge_lib/deluge_sdk.py)

**Filesystem scanning** — `scan_tree()` returns `FileEntry` objects with `rel_path`, `size`, and `mtime`. Combined with `get_existing_samples()` for normalised path matching, this gives everything needed for file-level analysis.

Source: [scripts/deluge_lib/scanning.py](../scripts/deluge_lib/scanning.py)

**What's missing** is the *analysis layer* — aggregating references into usage counts, cross-referencing with disk state, computing size totals, and formatting output. This is the core new work.

### 2. CLI Design: Subcommands vs Flags

**Option A: Subcommands** (`sample_overview.py summary`, `sample_overview.py unused`)

Pros:
- Each subcommand has a clear, focused purpose
- Help text is scoped (`--help` per subcommand)
- Extensible — new subcommands can be added without affecting existing ones
- Matches the mental model: "show me unused samples" vs "show me a summary"

Cons:
- More argparse boilerplate
- No existing subcommand pattern in this codebase to follow (`fix_references.py` uses flat flags despite having subcommand-like behaviour)

**Option B: Flags** (`sample_overview.py --unused`, `sample_overview.py --summary`)

Pros:
- Simpler argparse setup
- Matches the existing codebase pattern (all scripts use flat flags)
- Can combine flags: `--unused --sizes`

Cons:
- Flag combinations create ambiguity (what does `--unused --missing` show?)
- Help text becomes cluttered as features grow
- Harder to add subcommand-specific flags later (e.g. `unused --min-size 1MB`)

**Option C: Subcommands with shared flags**

Each subcommand gets its own argument set, but common flags (like `--top N`) are shared via a parent parser. This gives the clarity of subcommands with the composability of shared options.

**Assessment:** The codebase currently has no subcommand pattern, but `fix_references.py` already has subcommand-like behaviour squeezed into flags — its design would have been cleaner with actual subparsers. The overview tool has at least 4 distinct modes (summary, unused, missing, usage) that benefit from separate help text and argument sets. Subcommands are the better long-term fit.

### 3. Output Format Patterns

Existing scripts use a consistent plain-text output style:

- **Headers** — section names in uppercase with `---` underlines (see `fix_references.py`)
- **Indented lists** — two-space indent for items under a header
- **Summary lines** — `f"Summary: {count} items, {n} issues"` at the end
- **Progress indicators** — `\r`-based overwriting for scans (see `scan_tree()`)
- **Size formatting** — `_format_size()` in `create_backup.py` (B / KB / MB / GB)

No script currently produces structured output (JSON, CSV). All output is human-readable text to stdout.

**Recommendation:** Match the existing plain-text style. Structured output (e.g. `--json`) can be deferred — it's easy to add later since the analysis layer will produce data structures that can be serialised.

Source: [scripts/create_backup.py](../scripts/create_backup.py), [scripts/fix_references.py](../scripts/fix_references.py), [scripts/verify_references.py](../scripts/verify_references.py)

### 4. Manifest/Snapshot Integration: Not Recommended

The user asked whether this tool should write a "usage manifest" alongside or integrated with `create_snapshot.py`. After analysis:

**Arguments for:**
- Could cache results to speed up repeated runs
- Other scripts could read usage data without re-scanning
- Provides a historical record of library state

**Arguments against:**
- **No consumer exists.** No current or planned script would read a usage manifest. The snapshot system (`create_snapshot.py`) serves `fix_references.py` and has a specific purpose (hash-based migration). Usage data doesn't fit that workflow.
- **Scan time is acceptable.** At ~6000 WAV files, `scan_tree()` completes in seconds. Reference extraction across ~80 XMLs is even faster. There's no performance reason to cache.
- **Complexity cost.** Adding manifest read/write, staleness detection, and invalidation logic adds significant complexity for no concrete benefit.
- **Snapshot format mismatch.** The existing snapshot format maps SHA-256 hashes to paths. Usage data (reference counts, source XMLs) has a fundamentally different shape. Overloading the format or creating a parallel format both add confusion.

**Conclusion:** Don't integrate with manifests. The tool should scan fresh each run. If a future need for cached usage data emerges, a `--json` output flag can serve that purpose without coupling to the manifest system.

Source: [scripts/create_snapshot.py](../scripts/create_snapshot.py), [docs/manifests/snapshot-2026-04-17.json](../docs/manifests/snapshot-2026-04-17.json)

### 5. Performance at ~6000 Files

The critical operations and their expected performance:

| Operation | Mechanism | Expected time |
|-----------|-----------|---------------|
| Scan SAMPLES/ for WAV files | `scan_tree()` via `os.walk` | ~1–2s for 6000 files |
| Find all XML files | `find_all_xml_files()` via `scan_tree()` | <1s (~80 XMLs) |
| Parse XMLs + extract refs | `extract_sample_refs()` with lxml | <2s for ~80 XMLs |
| Cross-reference (set lookups) | Python set/dict operations | negligible |
| Size aggregation | Sum `FileEntry.size` values | negligible |

**Total expected wall time: ~3–5 seconds.** This is fast enough to scan fresh every run without caching.

**One optimisation opportunity:** `find_all_xml_files()` currently calls `scan_tree()` per subdirectory (KITS, SYNTHS, SONGS) then discards size/mtime data. The overview tool needs both XML paths *and* sample file sizes, so it will call `scan_tree()` separately for SAMPLES/. This is fine — the operations are independent and fast.

**`_format_size()` extraction:** The size-formatting helper currently lives as a private function in `create_backup.py`. It should be extracted to `deluge_lib/` (e.g. `scanning.py` or a new `formatting.py`) so both scripts can use it. This is a small, low-risk refactor.

### 6. Overlap with `verify_references.py`

The `missing` subcommand overlaps with `verify_references.py`'s core function. Key differences:

| Aspect | `verify_references.py` | `sample_overview.py missing` |
|--------|------------------------|------------------------------|
| Purpose | Verify integrity before deployment | Quick overview of library health |
| Unextracted paths | Yes (regex fallback check) | No (not needed for overview) |
| Output detail | Per-reference with preset names | Simplified — just sample path + where used |
| Return code | `sys.exit(1)` on broken refs | Informational only |

**Recommendation:** The `missing` subcommand should be a simpler, overview-oriented view. It does not need to replicate `verify_references.py`'s thoroughness (regex fallback, exit codes). Users who need rigorous verification should still use `verify_references.py`. Cross-reference in help text: `"For detailed verification, see verify_references.py"`.

Source: [scripts/verify_references.py](../scripts/verify_references.py)

### 7. Proposed Subcommand Design

Based on the analysis, the recommended subcommands are:

#### `summary` (default when no subcommand given)

Quick overview of the sample library:
```
Sample Library Overview
=======================

On disk:     6,012 samples (2.3 GB)
Referenced:  1,847 samples (890 MB)
Unreferenced: 4,165 samples (1.4 GB)
Missing:     3 samples (referenced but not on disk)

By folder:
  SAMPLES/Artists/         3,200 files   1.1 GB
  SAMPLES/DRUMS/           2,400 files   980 MB
  SAMPLES/CLIPS/             280 files   180 MB
  SAMPLES/RECORD/            132 files    52 MB

Top 5 most-referenced samples:
  SAMPLES/DRUMS/Kick/808 Kick.wav          12 refs
  SAMPLES/DRUMS/Snare/Snappy.wav            9 refs
  ...
```

#### `unused`

List unreferenced samples with sizes:
```
Unreferenced samples (4,165 files, 1.4 GB):
  SAMPLES/Artists/Chaz/pad-warm.wav                   2.1 MB
  SAMPLES/Artists/Chaz/stab-bright.wav                1.8 MB
  ...

Total reclaimable: 1.4 GB
```

Optional flags: `--by-folder` (group by top-level folder), `--top N` (show only top N by size)

#### `missing`

List samples referenced in XMLs but not found on disk:
```
Missing samples (3):
  SAMPLES/DRUMS/Kick/OldKick.wav
    Referenced by: KITS/MyKit.XML, SONGS/Track01.XML

  SAMPLES/Artists/Unknown/pad.wav
    Referenced by: SYNTHS/Ambient.XML
```

#### `usage [PATTERN]`

Show usage details for samples matching a pattern:
```
$ sample_overview.py usage "DRUMS/Kick"

SAMPLES/DRUMS/Kick/808 Kick.wav (245 KB)
  KITS/DrumKit1.XML (kit)
  KITS/DrumKit2.XML (kit)
  SONGS/Track01.XML → Perc1 (song)
  12 total references (shared across 3 presets)

SAMPLES/DRUMS/Kick/Vinyl Kick.wav (180 KB)
  SONGS/Track03.XML → Drums (song)
  1 total reference (exclusive)
```

### 8. Script Naming and Registration

The user confirmed renaming to `sample_overview.py`. This requires:

1. Create `scripts/sample_overview.py` as a new file
2. Add a `pyproject.toml` entry: `deluge-overview = "sample_overview:main"` under `[project.scripts]`
3. Remove or deprecate the old `list_samples.py` (can keep it temporarily and have it print a deprecation message pointing to `sample_overview.py`)

Source: [scripts/pyproject.toml](../scripts/pyproject.toml)

### 9. Architecture: Analysis Module

The analysis logic should live in a new module `scripts/deluge_lib/analysis.py` rather than in the script itself. This matches the existing pattern where `deluge_sdk.py` provides data collection and scripts provide CLI wrappers.

The analysis module would contain:
- `build_usage_index()` — cross-references refs with disk state, returns a structured result
- `folder_breakdown()` — groups files by top-level folder with size totals
- `top_samples()` — returns the N most-referenced or largest samples
- Data classes for analysis results (e.g. `SampleUsage`, `LibrarySummary`, `FolderStats`)

The script (`sample_overview.py`) handles only CLI parsing and output formatting.

## Approaches Considered

| Approach | Pros | Cons | Complexity |
|----------|------|------|------------|
| **A: Subcommands** (`summary`, `unused`, `missing`, `usage`) | Clear UX, extensible, per-subcommand help and flags | More argparse boilerplate, no existing codebase precedent | Medium |
| **B: Flags** (`--unused`, `--missing`, `--summary`) | Simpler setup, matches current patterns | Ambiguous combinations, harder to extend, cluttered help | Low |
| **C: Separate scripts** (`list_unused.py`, `list_missing.py`, etc.) | Maximum simplicity per script | Duplicated scanning, more files to maintain, fragmented UX | Low per script, High overall |

## Cross-Cutting Concerns

### Shared utilities
- `_format_size()` needs extracting from `create_backup.py` to `deluge_lib/` for reuse. Both `create_backup.py` and `sample_overview.py` need it.

### Overlap with `verify_references.py`
- The `missing` subcommand overlaps with broken-reference checking. The overview tool provides a lighter-weight view; `verify_references.py` remains the authoritative pre-deployment check. Both should coexist.

### `list_samples.py` deprecation
- The existing `list_samples.py` will be superseded. It should either be deleted or kept as a thin wrapper that prints a deprecation warning and delegates to `sample_overview.py summary`.

### SD Card safety
- This tool is **read-only**. It reads XMLs and scans the filesystem but never writes to `DELUGE/` or the SD card. No safety concerns.

### `pyproject.toml` registration
- A new `[project.scripts]` entry is needed. The existing `deluge-list` entry (if one exists for `list_samples.py`) should be removed or redirected. Currently `list_samples.py` is not registered in `pyproject.toml`, so only an addition is needed.

## Risk Analysis

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Case-sensitivity mismatches between XML refs and disk paths | Medium | Medium (incorrect usage counts) | Use `normalise_key()` consistently, same as existing scripts |
| Performance regression at scale (>6000 files) | Low | Low (seconds, not minutes) | `scan_tree()` is already proven at this scale; fresh scan each run is fine |
| Subcommand pattern unfamiliar to user | Low | Low | Default subcommand (`summary`) means bare `sample_overview.py` still works |
| `_format_size()` extraction breaks `create_backup.py` | Low | Low | Simple refactor — import from new location, verify tests pass |
| Output format changes break user workflows | Low | Low | No downstream consumers currently parse this output |

## Recommendation

**Approach A: Subcommands** is recommended.

1. **Create `scripts/sample_overview.py`** with 4 subcommands: `summary` (default), `unused`, `missing`, `usage`
2. **Create `scripts/deluge_lib/analysis.py`** with the analysis logic, keeping the script as a thin CLI wrapper
3. **Extract `_format_size()`** to `scripts/deluge_lib/scanning.py` (or a new `formatting.py`) for shared use
4. **Do not integrate with manifests/snapshots** — scan fresh each run
5. **Plain-text output only** — defer `--json`/`--output` until there's a concrete use case
6. **Deprecate `list_samples.py`** — either delete or make it print a redirect message

**Rationale:**
- Subcommands provide the clearest UX for 4 distinct modes and allow per-subcommand flags (e.g. `unused --top 20`, `usage PATTERN`)
- The analysis module follows the established `deluge_lib/` pattern and keeps the script testable
- Fresh scanning avoids manifest complexity with negligible performance cost (~3–5s at 6000 files)
- Plain text matches every other script in the project

## Open Questions

1. **Should `summary` be the default subcommand (i.e. `sample_overview.py` with no args runs `summary`)?**
   - **Impact:** Determines whether bare invocation produces useful output or shows help
   - **Recommendation:** Yes — bare invocation should run `summary`. This matches user expectation ("just run the tool and see what's going on")
   - **Blocking:** No

2. **Should `--output` / `--json` flags be included in v1?**
   - **Impact:** Determines whether file output or structured data is available from day one
   - **Recommendation:** Defer. No downstream consumer exists, and stdout can be redirected. Easy to add later without breaking changes.
   - **Blocking:** No

3. **What happens to `list_samples.py`?**
   - **Impact:** Whether to keep, deprecate, or delete the old script
   - **Recommendation:** Delete it. It's a simple script with no dependents. The `summary` subcommand subsumes its functionality.
   - **Blocking:** No

4. **Should `usage` accept glob patterns or substring matches?**
   - **Impact:** Determines how flexible sample lookup is (e.g. `usage "DRUMS/*"` vs `usage "Kick"`)
   - **Recommendation:** Case-insensitive substring match is simplest and most useful. Glob support can be added later.
   - **Blocking:** No

5. **Should the `unused` subcommand support `--by-folder` grouping?**
   - **Impact:** Whether unreferenced samples can be viewed grouped by their folder structure
   - **Recommendation:** Include it — folder grouping makes large lists actionable ("I can delete all of `SAMPLES/Artists/Chaz/`")
   - **Blocking:** No

## References

### Project Files
- [scripts/list_samples.py](../scripts/list_samples.py) — Current script being replaced
- [scripts/deluge_lib/deluge_sdk.py](../scripts/deluge_lib/deluge_sdk.py) — `extract_sample_refs()`, `find_all_xml_files()`, `get_existing_samples()`, `SampleRef`
- [scripts/deluge_lib/scanning.py](../scripts/deluge_lib/scanning.py) — `scan_tree()`, `FileEntry`, `normalise_key()`
- [scripts/deluge_lib/cli_utils.py](../scripts/deluge_lib/cli_utils.py) — `get_deluge_root()`, `confirm_apply()`
- [scripts/create_backup.py](../scripts/create_backup.py) — `_format_size()` to extract
- [scripts/verify_references.py](../scripts/verify_references.py) — Overlapping `missing` functionality
- [scripts/create_snapshot.py](../scripts/create_snapshot.py) — Manifest/snapshot system evaluated
- [scripts/pyproject.toml](../scripts/pyproject.toml) — Script registration
- [docs/scripts-plan.md](../docs/scripts-plan.md) — Original scripts plan, references `create-manifest.py` (unimplemented)

### External Resources
- Python `argparse` subparsers: [docs.python.org/3/library/argparse.html#sub-commands](https://docs.python.org/3/library/argparse.html#sub-commands)

## Next Steps

1. Review this document and resolve any blocking open questions
2. Invoke the Plan agent to create a feature plan from this research
