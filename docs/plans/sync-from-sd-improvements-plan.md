# Plan: sync_from_sd.py Improvements

> **Document Type:** Plan
> **Date:** 09 April 2026
> **Research:** Inline context from code review (no standalone research document)
> **Pipeline:** Research → **Plan** → Implement
> **Status:** Draft

## Executive Summary

This plan addresses six bugs and feature gaps in `scripts/sync_from_sd.py` and introduces a sync manifest to solve the fresh-clone problem. The approach uses a simple stat-based comparison (size + mtime) unified across all file types, adds a persistent JSON manifest for cross-machine consistency (preserving mtimes that git destroys), filters file types, normalises paths for case-insensitive FAT32 matching, mirrors empty directories, adds error recovery, introduces execution logging, and registers a `deluge-sync` CLI entry point. The deprecated `scripts/old_sync.py` will be deleted.

## Research Summary

A code review of the current `sync_from_sd.py` identified six issues:

1. **mtime-only comparison is unreliable** — `_needs_copy` uses size + mtime, but git doesn't preserve mtime, causing every file to be flagged after a fresh clone. FAT32 mtime resolution is only 2 seconds.
2. **No file-type filtering** — `rglob("*")` syncs everything including OS junk files (.DS_Store, Thumbs.db).
3. **Case-sensitive path comparison on case-insensitive FAT32** — files with differing case are treated as distinct, causing duplicate syncs or missed matches.
4. **No error recovery** — a `shutil.copy2` failure propagates unhandled, leaving partially-applied state.
5. **No execution logging** — the old script logged to `docs/scripts.log`; the new script has none.
6. **No .trash exclusion on source scan** — a `.trash` directory on the SD card would be synced.

The old script (`old_sync.py`) already solved problems 2, 3, and 5. Its patterns — file-type filtering, case-insensitive dict keying, and `append_to_log` — inform several decisions below.

### Existing Assets to Leverage

- `scripts/deluge_lib/cli_utils.py` — provides `get_sd_card_path`, `get_deluge_root`, and `confirm_apply`. Already used by the current script; no changes needed.
- `scripts/old_sync.py` — contains working patterns for file-type filtering, case-insensitive comparison, and execution logging. Will be deleted after its ideas are absorbed.
- `scripts/pyproject.toml` — already configured with dependencies (python-dotenv, lxml), tooling (ruff, mypy, pytest), and project metadata. No new dependencies are required for these improvements — all work uses the Python standard library (json, pathlib, shutil, logging).

## Decisions Log

| ID | Decision | Rationale | Alternatives Considered |
|----|----------|-----------|------------------------|
| D1 | Unified stat-based comparison: size + mtime for all file types | Simple and fast. SD card is always the source of truth for this script. If size or mtime differs, just copy — no need to check content. For XMLs (few KB), copying is cheaper than any comparison logic. For WAVs, there is no realistic scenario where a file has the same name, same size, and same mtime but different content. | Tiered comparison with content hashing (unnecessary complexity — same-size-same-mtime-different-content is not a real scenario); filecmp.cmp (no manifest integration) |
| D2 | JSON manifest at `scripts/data/manifest.json` storing `{relative_path: {size, mtime}}`, with metadata header | Solves the fresh-clone problem — comparison against manifest instead of repo file stats means git's mtime destruction is irrelevant. The manifest is purely a performance optimisation: it lets the mtime comparison work even when git has destroyed all repo mtimes. JSON is human-readable and diffable. Machine-specific (gitignored). Metadata header aids debugging. Corrupt manifest is discarded with a warning and treated as empty. *(Updated by D17, D18)* | SQLite (overkill for flat key-value data); pickle (not human-readable); no manifest (leaves fresh-clone bug unfixed) |
| D3 | Filter to `.xml` and `.wav` only | Matches the Deluge's file types and the old script's behaviour. Excludes OS junk files (.DS_Store, Thumbs.db) and system files. | Extensible allowlist (premature — Deluge only uses .xml and .wav); blocklist approach (fragile — new junk types would slip through) |
| D4 | Case-insensitive path comparison, SD card casing wins | FAT32 is case-insensitive. Two files differing only in case are the same file. Using the SD card's actual casing as the canonical form respects the source of truth. Same approach as `old_sync.py`. | Normalise to uppercase (would rename repo files unnecessarily); normalise to lowercase (same tradeoff) |
| ~~D5~~ | ~~MD5 for hashing~~ | *Removed — hashing is not needed. The stat-based comparison (size + mtime) is sufficient for this use case. Hashing may be introduced later for sample management scripts, but that is a separate concern.* | — |
| D6 | Stop immediately on copy failure | Simplest error recovery strategy. Reports what was completed and what failed. Avoids compounding errors by continuing after a failure. The manifest is only updated for successfully-completed syncs. | Continue-on-error with summary (risk of cascading failures); retry with backoff (overkill for local file copy) |
| D6 | Stop immediately on copy failure | Simplest error recovery strategy. Reports what was completed and what failed. Avoids compounding errors by continuing after a failure. The manifest is only updated for successfully-completed syncs. | Continue-on-error with summary (risk of cascading failures); retry with backoff (overkill for local file copy) |
| D7 | Execution logging to `scripts/data/sync.log`, gitignored | Co-locates the log with the manifest data directory. The log serves as a local audit trail of sync operations. Machine-specific and gitignored (along with the rest of `scripts/data/`). Append-only format with structured fields. *(Updated by D19, ~~D20~~, D33)* | `docs/scripts.log` (original location — separates log from related data); Python logging module to stderr (no persistent record); separate log per run (clutters filesystem) |
| D8 | Delete `old_sync.py` | Fully superseded. Its useful patterns (file-type filtering, case-insensitive comparison, logging) are being absorbed into the improved `sync_from_sd.py`. Keeping it creates confusion about which script to use. | Keep as reference (creates confusion; git history preserves it) |
| D9 | Exclude `.trash` from source scan | A `.trash` directory on the SD card (if present) is not Deluge content and should not be synced. The current script already excludes `.trash` on the destination side — this extends the same logic to the source. | Sync everything (would import junk) |
| D10 | Sequential file copying, no parallelism | SD card I/O is the bottleneck. Parallel reads from a single SD card provide no benefit and may degrade performance on FAT32. Keeps the implementation simple. | ThreadPoolExecutor (no real benefit on single-device I/O) |
| D11 | Manifest written atomically after full sync completes | Writing only after success ensures the manifest never represents a partial state. If a sync fails, the old manifest (or no manifest) is preserved, and the next run re-evaluates correctly. | Write incrementally per-file (risk of partial manifest on failure); write at start (stale on failure) |
| D12 | Gitignore entire `scripts/data/` directory | Both the manifest and the execution log are machine-specific and should not be committed. The whole `scripts/data/` directory is gitignored. *(Updated by ~~D20~~, D33)* | Selective ignore of individual files (unnecessary complexity now that the log is also local-only) |
| D13 | Manifest tracks all synced files (both .xml and .wav) | The manifest's purpose is to preserve size + mtime across fresh clones where git destroys mtimes. This applies equally to all file types. Scoping to only some files would leave the others vulnerable to the fresh-clone problem. | Track only SAMPLES/ .wav files (leaves XMLs vulnerable to unnecessary re-copying after fresh clone) |
| ~~D14~~ | ~~Local edits flagged as conflicts (not overwritten)~~ | *Removed — conflict detection is unnecessary for this script. The SD card is always the source of truth. WAV content edits happen on PC only and will be synced back via a future reverse-sync script. XML content edits are only produced by the Deluge hardware. XML renames on PC appear as new+deleted files, not edits. There is no scenario where this script needs to protect local edits.* | — |
| D15 | Root-level files included in sync | MIDIFollow.XML sits at the SD card root, not inside any subdirectory. The source scan must include files at every level of the SD card directory tree, including the root. All .xml and .wav files at any depth are included. | Only scan subdirectories (would miss root-level files like MIDIFollow.XML) |
| D16 | Mirror empty directories from SD card | If the SD card has empty directories (e.g. an empty SAMPLES/RECORD/ folder), the sync creates them in the repo too. This preserves the full directory structure as a faithful backup. | Ignore empty directories (incomplete backup) |
| D17 | Manifest includes metadata header | The manifest JSON includes a top-level metadata section with: script version, last-sync ISO 8601 timestamp, and total file count. This aids debugging manifest issues and provides provenance information. | No metadata (harder to debug stale or mismatched manifests) |
| D18 | Corrupt manifest — discard with warning | If the manifest file contains invalid JSON, warn the user and treat it as empty (all files will be re-evaluated). Do NOT back up the corrupt file — simplicity over recovery of broken data. | Rename to .bak (unnecessary complexity — the corrupt manifest has no value); abort (too disruptive) |
| D19 | Execution log at `scripts/data/sync.log` | Co-located with the manifest in `scripts/data/`. Keeps all sync-related data files together rather than scattering them across the repo. | `docs/scripts.log` (original plan — separates log from manifest) |
| ~~D20~~ | ~~Execution log committed to git~~ | *Removed — reversed by D33. The log is machine-specific and gitignored along with the rest of `scripts/data/`. Version history of sync operations is not needed in git.* | — |
| ~~D21~~ | ~~Hash during copy (single read pass)~~ | *Removed — hashing is no longer performed. Files are copied with standard `shutil.copy2`.* | — |
| D22 | Trashed entries removed from manifest | When files are moved to `.trash` during sync (present in repo but absent from SD card), their entries are removed from the manifest. This keeps the manifest in sync with the actual file state and prevents stale entries from interfering with future comparisons. | Keep stale entries (causes incorrect behaviour on future syncs if file returns with different content) |
| ~~D23~~ | ~~Case-rename repo files to match SD card~~ | *Removed — replaced by D37. Case differences with matching content are treated as unchanged (skipped), not renamed. Eliminates rename operation type, two-step rename logic, and `safe_rename` utility.* | — |
| D24 | Register `deluge-sync` CLI entry point via `[project.scripts]` | Add a `[project.scripts]` section to `pyproject.toml` that registers `deluge-sync = "sync_from_sd:main"`. Since `pyproject.toml` has `src = ["scripts"]`, modules are importable from the `scripts/` directory — so `sync_from_sd` resolves to `scripts/sync_from_sd.py`. This pattern extends naturally to future scripts: each gets its own entry (e.g. `deluge-fix-refs = "fix_refs:main"`). *(Updated by D26)* | No entry point (requires remembering the script path); shell alias (not portable, not version-controlled) |
| D25 | Skip symlinks silently | Symlinks encountered during scanning are silently skipped. FAT32 does not support symlinks, so any found are artefacts of the local filesystem (not SD card content). Skipping avoids potential loops or broken link errors. | Follow symlinks (risk of loops or referencing outside the SD card); error on symlinks (too noisy) |
| D26 | Extract reusable functions into `deluge_lib/` shared modules | WIP scripts on another branch (broken reference finder, path fixer) need the same manifest, file scanning, and path normalisation utilities. Instead of duplicating code, extract these into `deluge_lib/` modules that `sync_from_sd.py` imports from. Sync-specific logic (SyncPlan, execute_plan) stays in `sync_from_sd.py`. The manifest format is designed as a shared "file inventory" — sync writes it, other scripts can read it. `deluge_lib/` already contains `__init__.py`, `cli_utils.py`, and `deluge_sdk.py`; the new modules sit alongside these. | All logic in sync_from_sd.py (no reuse — other scripts would duplicate scanning/manifest code); separate package (overkill for tightly-coupled scripts in the same repo) |
| D27 | Scanner accepts any root path (generic) | `scanning.py` accepts a root `Path` argument and works for any directory, not just SD cards. This lets the future reverse-sync script and sample management scripts reuse it for scanning `DELUGE/` (local). The scanner is not SD-card-specific — it's a general-purpose filtered file walker. | Hardcode SD card scanning (prevents reuse for local directory scanning) |
| D28 | Scanner returns stat info in the same pass | During the rglob walk, the scanner captures `stat()` info (size, mtime) for each file alongside the path. This avoids a second filesystem call during comparison. The return type includes path + stat data, not just paths. Benefits both the sync script and future scripts. | Separate stat pass (doubles filesystem calls); return paths only and stat later (wasteful for large directories) |
| D29 | Refactor `deluge_sdk.find_all_xml_files()` to use `scanning.py` | `deluge_sdk.py` has its own `find_all_xml_files()` that does a separate rglob of KITS/SYNTHS/SONGS for XMLs. After `scanning.py` is created, refactor this to use the shared scanner instead of duplicating the walking logic. Small change — Phase 4 task. | Keep separate rglob (duplicated walking logic across modules) |
| D30 | Manifest supports optional extra fields per entry | The manifest entry format allows optional additional fields beyond size and mtime. Future scripts (sample management) may add fields like `sample_refs`, `duration`, etc. The sync script only writes size and mtime, but the format does not break if other fields are present. In practice: manifest uses a dict-per-entry approach (not a fixed tuple), and the sync script ignores fields it doesn't recognise. | Fixed tuple format (breaks when other scripts add fields); separate manifests per script (fragmentation) |
| D31 | Single manifest with metadata-level direction tracking | The future reverse-sync (PC→SD) will use the same manifest file. The metadata section includes `last_sync_direction` (e.g. `"sd-to-local"` or `"local-to-sd"`) and `last_sync_timestamp`. This is metadata-level, not per-entry. For now, the sync script always writes `"sd-to-local"`. Future-proofing decision — no reverse-sync logic is implemented in this plan. | Separate manifests per direction (fragmentation); no direction tracking (ambiguous provenance) |
| D32 | Manifest paths always use forward slashes (POSIX-style) | Regardless of OS, manifest keys and stored paths use forward slashes. This makes the manifest portable across the user's Windows music machine and Linux dev machine. The `normalise_key` function in `scanning.py` handles this conversion. | OS-native separators (manifest is non-portable across platforms) |
| D33 | `sync.log` is gitignored (reverses D20) | The user changed their mind — `sync.log` is machine-specific and should be gitignored. This means the entire `scripts/data/` directory can be gitignored (simpler than selective ignoring). Reverses D20 and simplifies D12. | Commit the log (clutters git history with machine-specific data) |
| ~~D34~~ | ~~`paths.py` is minimal — 2 functions only~~ | *Removed — replaced by D38. `paths.py` eliminated as a module. `normalise_key` moved into `scanning.py` (its only consumer). `safe_rename` removed entirely (no longer needed without case-rename).* | — |
| D35 | Tests split per module | Test files: `test_manifest.py`, `test_scanning.py` (includes normalise_key tests), `test_sync_from_sd.py`. Each tests its corresponding module independently. | Single test file (harder to navigate and maintain as test count grows) |
| D36 | No trash auto-cleanup | The script does not warn about or auto-clean `.trash`. The user manages it manually. Confirms existing plan behaviour — documented explicitly. | Auto-cleanup on age or size threshold (unnecessary complexity; user preference) |
| D37 | Case differences with matching content treated as unchanged | When the SD card has `Kit001.XML` and the repo has `KIT001.XML` with the same size, treat it as unchanged (skip it). Do not rename repo files to match SD card casing. Replaces D23 (case-rename). Eliminates: `SyncPlan.files_to_rename`, rename handling in `execute_plan`/`print_plan`/`_plan_is_empty`, rename count in `SyncResult`/`append_sync_log`, and the case-rename detection branch in `compute_sync`. | Rename repo files to match SD card casing (D23 — unnecessary complexity; casing divergence is cosmetic, not functional, on case-insensitive FAT32) |
| D38 | Remove `paths.py` — move `normalise_key` into `scanning.py` | `paths.py` only contained `normalise_key` and `safe_rename`. With `safe_rename` gone (D37 removes case-rename) and `normalise_key` being a one-liner, a dedicated module is overengineered. Move `normalise_key` into `scanning.py` (where it's already used). Delete `paths.py` and `test_paths.py`; move `normalise_key` tests into `test_scanning.py`. Replaces D34. | Keep `paths.py` for future expansion (currently has one function; premature abstraction) |

## Technical Specification

### Language and Tooling

| Item | Choice | Notes |
|------|--------|-------|
| Language | Python 3.12 | Per `scripts/pyproject.toml` and Python core standard |
| Package Manager | uv | Per Python core standard |
| Linter/Formatter | Ruff | Already configured in `pyproject.toml` |
| Type Checker | mypy (strict) | Already configured in `pyproject.toml` |
| Test Framework | pytest | Already configured in `pyproject.toml` |
| Key Dependencies | None new | All improvements use the standard library (json, pathlib, shutil) |

### Architecture

The improved script uses a modular architecture with a plan-then-execute model. Reusable utilities (manifest I/O, file scanning, path normalisation) are extracted into `deluge_lib/` modules (D26), forming a shared library that `sync_from_sd.py` imports from. Sync-specific logic (SyncPlan, comparison engine, plan execution) remains in `sync_from_sd.py`. This separation enables other scripts (broken reference finder, path fixer) to reuse the same core utilities. The core changes are:

**Comparison engine** (in `sync_from_sd.py`, imports from `deluge_lib.scanning`). The current `_needs_copy` function is replaced with a unified stat-based comparison that applies identically to all file types (.xml and .wav). The flow for each file on the SD card is:

1. **On SD, not in repo** → COPY
2. **In repo/manifest, not on SD** → TRASH
3. **Size + mtime match** → SKIP (includes case differences — same normalised key, same size = unchanged)
4. **Size or mtime differ** → COPY

For step 3, the comparison target depends on manifest availability: if a manifest entry exists, compare against the manifest's recorded size and mtime (this handles the fresh-clone case where git has destroyed repo mtimes). If no manifest entry exists, compare against the actual repo file's stat. Mtime comparison uses a ±2-second tolerance for FAT32 rounding (kept as a minor safety margin, not a critical feature).

For XMLs specifically: since they're tiny (few KB), when size is the same but mtime differs, just copy — the cost of copying a few KB is negligible compared to any comparison logic.

**Manifest manager** (`deluge_lib/manifest.py`). A set of functions handles reading, writing, and updating the JSON manifest. The manifest is designed as a shared "file inventory" — sync writes it, and other scripts can read it to know what files exist and their stats without rescanning. The manifest tracks all synced files (both .xml and .wav). The manifest maps lowercased, forward-slash-normalised relative paths (D32) to records containing the file's size and mtime as of the last successful sync. The entry format is extensible: each entry is a dict, and the sync script only writes size and mtime but ignores any additional fields written by other scripts (D30). A metadata section records the script version, last-sync timestamp, total file count, and `last_sync_direction` (`"sd-to-local"` for this script — D31). The manifest is read at the start of a sync and written atomically (write to temp file, then rename) after a fully successful sync. Corrupt manifests are discarded with a warning and treated as empty. The manifest file lives at `scripts/data/manifest.json` and is gitignored.

**Source scanner** (`deluge_lib/scanning.py`). A generic, reusable file scanner that accepts any root `Path` argument — not SD-card-specific (D27). This lets the sync script scan the SD card, the future reverse-sync script scan `DELUGE/`, and sample management scripts scan arbitrary directories. The scanner replaces the current `source.rglob("*")` with a filtered scan that yields `.xml` and `.wav` files at any depth (including root level, to capture files like MIDIFollow.XML) and skips any `.trash` directory and any symlinks. During the walk, the scanner also captures `stat()` info (size, mtime) for each file in the same pass (D28), avoiding a second filesystem call during comparison. The return type includes path + stat data, not just paths. The scanner also identifies empty directories for mirroring. Path normalisation happens at scan time — each file's relative path is stored alongside a lowercased, forward-slash-normalised key for case-insensitive lookup. The module also contains the `normalise_key` utility (D38) — a one-liner that lowercases and converts to forward slashes, used for case-insensitive dict keying and manifest path normalisation.

**Path normalisation** (in `deluge_lib/scanning.py`). The `normalise_key` function (lowercase + forward slashes) lives in `scanning.py` alongside the scanner that uses it. This is a one-liner utility that doesn't warrant its own module. It is used for case-insensitive path matching: when two files match on normalised key and size, they are treated as unchanged regardless of casing differences.

**Empty directory mirroring.** The scanner identifies empty directories on the SD card and the execution phase creates corresponding directories in the repo, preserving the full directory structure.

**CLI entry point.** A `[project.scripts]` section in `pyproject.toml` registers `deluge-sync = "sync_from_sd:main"`. Since `pyproject.toml` has `src = ["scripts"]`, modules are importable by their filename — `sync_from_sd` resolves to `scripts/sync_from_sd.py`. This pattern extends to future scripts: each gets its own entry (e.g. `deluge-fix-refs = "fix_refs:main"`). Users can run `deluge-sync` from anywhere after installing the package.

**File structure.** The following files are modified or created:

```
scripts/
├── sync_from_sd.py          # Modified — sync-specific logic (SyncPlan, comparison, execution)
├── pyproject.toml            # Modified — CLI entry points added
├── data/
│   ├── manifest.json         # Created at runtime — gitignored
│   └── sync.log              # Execution log — gitignored (machine-specific)
├── deluge_lib/
│   ├── __init__.py           # Existing — unchanged
│   ├── cli_utils.py          # Existing — unchanged
│   ├── deluge_sdk.py         # Existing — refactored to use scanning.py (Phase 4)
│   ├── manifest.py           # New — manifest read/write/update, shared file inventory
│   └── scanning.py           # New — generic filtered file scanner with stat capture (D27, D28) + normalise_key (D38)
├── old_sync.py               # Deleted
└── tests/
    ├── test_manifest.py      # Tests for deluge_lib/manifest.py
    ├── test_scanning.py      # Tests for deluge_lib/scanning.py (includes normalise_key tests)
    └── test_sync_from_sd.py  # Tests for sync_from_sd.py
```

**Data flow.** The sync proceeds in four stages: (1) scan and filter the SD card using `deluge_lib.scanning`, which accepts any root path (D27) and returns path + `stat()` data (size, mtime) in a single pass (D28), building a dict keyed by lowercased, forward-slash-normalised relative paths (via `normalise_key` in `scanning.py`), plus a list of empty directories — no second stat call is needed during comparison; (2) compare each SD card file against the manifest (loaded via `deluge_lib.manifest`) or the repo file stat (when no manifest entry exists), building a `SyncPlan` with copy and trash actions (case differences with matching size are treated as unchanged — D37); (3) execute the plan sequentially — copies use `shutil.copy2`, empty directories are created; (4) write the updated manifest via `deluge_lib.manifest` (if sync succeeded) and append to the execution log.

### Interface Design

**Inputs.** The CLI interface is unchanged — `--dry-run` for preview only, `--confirm` to skip preview, or default behaviour (preview then prompt). Environment variables `SD_CARD_PATH` and `DELUGE_ROOT` are read from `scripts/.env` via `cli_utils`. Additionally, the `deluge-sync` CLI entry point provides a convenient command-line invocation.

**Outputs.**

- Console: scanning progress, dry-run/preview summary, copy progress, final summary with counts (copied, trashed, unchanged)
- `scripts/data/manifest.json`: written after each successful sync (gitignored)
- `scripts/data/sync.log`: append-only execution log with structured summary per run (gitignored — machine-specific per D33)

**Error handling.** On copy failure, the script stops immediately, prints a summary of what was completed and what failed, appends a FAILED entry to the execution log, and exits with a non-zero status. The manifest is not updated on failure — the next run will re-evaluate all files that were not yet recorded in the manifest.

**User interaction.** Unchanged from current behaviour — dry-run preview followed by confirmation prompt by default. The script remains read-only with respect to the SD card; it only writes to `DELUGE/`, `scripts/data/manifest.json`, and `scripts/data/sync.log` (both gitignored).

### Integration Points

- **cli_utils.py** — continues to provide `get_sd_card_path`, `get_deluge_root`, and `confirm_apply`. No changes needed.
- **deluge_sdk.py** — not used by the sync script directly. After `scanning.py` is created, `deluge_sdk.find_all_xml_files()` will be refactored to use the shared scanner instead of its own rglob (D29, Phase 4 task). Future sample management scripts may use both `deluge_sdk.py` (XML parsing) and the new `deluge_lib` modules (manifest, scanning).
- **deluge_lib/manifest.py** — new module providing manifest read/write/update. Used by sync to persist state; readable by other scripts as a file inventory. Entry format is extensible (D30) — dict-per-entry with optional fields beyond size and mtime. Metadata includes `last_sync_direction` (D31). Keys use forward-slash paths (D32).
- **deluge_lib/scanning.py** — new module providing generic filtered file scanning, path dict building, and `normalise_key` utility (D38). Accepts any root `Path` (D27) and returns path + stat data in a single pass (D28). Used by sync for SD card scanning; reusable by any script walking `DELUGE/` or other directories.
- **SD card safety** — the script is read-only with respect to the SD card (copies FROM, never writes TO). This is preserved. The only write targets are `DELUGE/` (permitted per project standard), `scripts/data/manifest.json`, and `scripts/data/sync.log` — both in the gitignored `scripts/data/` directory.
- **pyproject.toml** — updated with `[project.scripts]` entry for `deluge-sync` CLI command.
- **.gitignore** — the entire `scripts/data/` directory is gitignored. Both `manifest.json` and `sync.log` are machine-specific (D12, D33).

## Cross-Cutting Concerns

| Concern | Mitigation |
|---------|------------|
| **Cross-platform compatibility** | All file operations use `pathlib.Path`. No OS-specific tools or subprocess calls. FAT32 mtime tolerance (±2s) handles timestamp rounding differences. Manifest uses JSON (portable). Symlinks are skipped to avoid platform-specific behaviour. |
| **FAT32 filesystem limitations** | ±2-second mtime tolerance kept as a minor safety margin for FAT32 rounding. Case-insensitive path comparison added. Symlinks skipped (FAT32 cannot create them). |
| **Fresh clone scenario** | Manifest solves this — if manifest exists, compare SD card stats against manifest entries (preserved from last sync); if manifest is missing, fall back to repo file stat comparison (which will re-copy everything on a fresh clone — correct behaviour since mtimes are lost). First run on a fresh clone without a manifest is slow (one-time cost). |
| **SD card safety** | Script remains strictly read-only with respect to the SD card. Only reads and copies from it. Write targets are `DELUGE/`, `scripts/data/manifest.json`, and `scripts/data/sync.log` — all within the repository. |
| **Partial sync state** | Manifest is only written after a fully successful sync. On failure, the old manifest is preserved, and the next run re-evaluates correctly. |
| **Audit trail** | Execution log at `scripts/data/sync.log` provides a local history of all sync operations. Machine-specific and gitignored (D33). |
| **Shared library design** | Reusable functions in `deluge_lib/` have stable, minimal APIs — they accept and return simple types (paths, dicts, strings) rather than sync-specific domain objects. Module boundaries follow function grouping (manifest I/O, scanning + path normalisation). Sync-specific types like SyncPlan stay in `sync_from_sd.py`. The scanner is generic (any root `Path`, D27) and returns stat info in the same pass (D28). `normalise_key` lives in `scanning.py` alongside the scanner that uses it (D38). The manifest format is extensible (D30), uses forward-slash paths (D32), includes sync direction metadata (D31), and is documented and designed for multi-script consumption. `deluge_sdk.find_all_xml_files()` will be refactored to use the shared scanner (D29). |

## Risk Mitigation

| Risk | Plan Mitigation | Residual Risk |
|------|-----------------|---------------|
| Manifest corruption (truncated write, disk full) | Atomic write via temp file + rename. If rename fails, old manifest is preserved. Corrupt manifest on read is discarded and treated as empty (D18). | If both old and new manifest are lost, falls back to full comparison — recoverable |
| Case conflict where SD card and repo have different casing for same file | SD card and repo use case-insensitive matching via normalised keys. Same normalised key + same size = unchanged (skipped). No rename operation needed (D37). | Edge case: if both casings exist in the repo (impossible on FAT32, possible in git), the lowercased key match resolves to one. Manual cleanup may be needed. |
| Script fails mid-copy, leaving partially-applied state | Stop immediately. Report what succeeded and what failed. Manifest not updated. Next run picks up where it left off. | User sees partial state in `DELUGE/` until next successful sync. Acceptable — same as current behaviour. |
| `old_sync.py` deletion loses useful reference code | Git history preserves the file. Deletion commit message should note this. | None |
| Fresh clone without manifest re-copies everything | This is correct behaviour — without a manifest, the script cannot know which files are unchanged. The one-time cost is acceptable. The manifest is rebuilt on the first successful sync. | One-time slow sync after fresh clone. Unavoidable without a committed manifest. |

## Implementation Roadmap

## Phase 1: Core Comparison Engine

> **Goal:** Replace the mtime-only `_needs_copy` with the unified stat-based comparison, add file-type filtering, case-insensitive path handling, and empty directory mirroring
> **Prerequisites:** Understanding of current `_needs_copy`, `compute_sync`, and FAT32 behaviour

### Task 1.1: Implement unified comparison function

- **Description:** Replace `_needs_copy` with a new comparison function implementing the unified stat-based flow for all file types. The flow is: (1) on SD, not in repo → copy, (2) in repo, not on SD → trash, (3) size + mtime match → skip (including case differences with matching size — D37), (4) size or mtime differ → copy. When a manifest entry exists, compare SD card stat against manifest. When no manifest entry exists, compare against repo file stat. Mtime comparison uses ±2-second tolerance for FAT32 rounding. The function should return an action (copy, skip, trash).
- **Inputs:** Current `_needs_copy` function in `sync_from_sd.py`
- **Outputs:** New comparison function in `sync_from_sd.py` that returns an action. This is sync-specific logic and stays in `sync_from_sd.py`, importing from shared `deluge_lib` modules.
- **Acceptance Criteria:**
  - [x] Unified comparison logic implemented for all file types (on SD not in repo → copy; in repo not on SD → trash; size+mtime match → skip; differ → copy)
  - [x] When manifest entry exists, compare SD stat against manifest
  - [x] When no manifest entry exists, compare against repo file stat
  - [x] FAT32 mtime tolerance of ±2 seconds applied
  - [x] Type-annotated and passes mypy strict
- **Implementation Notes:**
  > Rewrote `compute_sync` to use `scan_tree()` from `deluge_lib.scanning` for both source and destination. Replaced `_needs_copy` with `_mtime_matches` (extracted FAT32/DST tolerance logic). Comparison iterates source scan keys: not-in-dest → copy, size differs → copy, mtime differs → copy, else skip (case differences with matching size treated as unchanged per D37). Manifest support via optional `ManifestDict` parameter — when entry exists, compare against manifest size/mtime instead of dest stat. Files in dest not in source → trash. Orphan directories derived from scan results (no extra walk). Passes mypy strict, ruff check, and ruff format.

### Task 1.2: Implement filtered file scanner in `deluge_lib/scanning.py`

- **Description:** Create `deluge_lib/scanning.py` with a generic, reusable file scanner. The scanner accepts any root `Path` argument — not SD-card-specific (D27). This lets the sync script scan the SD card, the future reverse-sync script scan `DELUGE/`, and sample management scripts scan arbitrary directories. Replace `source.rglob("*")` with a filtered scan that only yields files with `.xml` or `.wav` extensions (case-insensitive check). The scan must include files at the root level (not just subdirectories) to capture root-level files like MIDIFollow.XML. Exclude any `.trash` directory. Silently skip any symlinks encountered. During the walk, capture `stat()` info (size, mtime) for each file in the same pass (D28) — the return type should include path + stat data, not just paths. This avoids a second filesystem call during comparison. Also identify and collect empty directories for mirroring. Path normalisation happens at scan time — each file's relative path is stored alongside a lowercased, forward-slash-normalised key for case-insensitive lookup.
- **Inputs:** Current `compute_sync` source scanning loop
- **Outputs:** `deluge_lib/scanning.py` with generic filtered scan functions; `sync_from_sd.py` imports from this module
- **Acceptance Criteria:**
  - [x] Functions live in `deluge_lib/scanning.py`, not in `sync_from_sd.py`
  - [x] Scanner accepts any root `Path` argument (generic, not SD-card-specific — D27)
  - [x] Scanner returns path + stat data (size, mtime) per file in a single pass (D28)
  - [x] Scanner builds a case-normalised path dict (lowercased, forward-slash key → actual path + stat data)
  - [x] Only `.xml` and `.wav` files are yielded (case-insensitive extension check)
  - [x] Files at the SD card root level are included (e.g. MIDIFollow.XML)
  - [x] `.trash` directory on source is skipped entirely
  - [x] Symlinks are silently skipped (no warning, no error)
  - [x] Empty directories on the source are identified and collected
  - [x] Scanning progress output preserved
- **Implementation Notes:**
  > Created `scripts/deluge_lib/scanning.py` with `scan_tree()` function, `FileEntry` frozen dataclass, and `ScanResult` dataclass. Uses `os.walk(followlinks=False)` for efficient traversal with in-place directory pruning for `.trash` and symlink dirs. Contains `normalise_key` helper (moved from `paths.py` per D38) that uses `PurePosixPath` for forward-slash normalisation. Empty directory detection checks for no qualifying files AND no remaining subdirs after pruning. Passes mypy strict and ruff. The `sync_from_sd.py` import criterion is deferred to when the sync script is refactored to use this module.

### ~~Task 1.3: Implement path normalisation in `deluge_lib/paths.py` and case-rename in `sync_from_sd.py`~~ (Removed — D37, D38)

- **Description:** ~~Create `deluge_lib/paths.py` with exactly two functions (D34): `normalise_key(path) -> str` and `safe_rename(src, dst)`. In `sync_from_sd.py`, add rename actions to SyncPlan.~~ Removed by D37 (case-rename eliminated) and D38 (`paths.py` eliminated, `normalise_key` moved to `scanning.py`). `normalise_key` tests moved to `test_scanning.py`. `paths.py`, `test_paths.py`, `safe_rename`, `SyncPlan.files_to_rename`, and all rename handling in `execute_plan`/`print_plan`/`_plan_is_empty`/`SyncResult`/`append_sync_log` are removed.
- **Inputs:** N/A
- **Outputs:** N/A
- **Acceptance Criteria:** N/A — task removed
- **Implementation Notes:**
  > Task removed by D37 and D38. `normalise_key` was moved into `scanning.py`. `safe_rename` was deleted. All rename-related fields and logic in `sync_from_sd.py` (`SyncPlan.files_to_rename`, rename handling in `execute_plan`, `print_plan`, `_plan_is_empty`, rename count in `SyncResult`, `append_sync_log`) were removed. `paths.py` and `test_paths.py` deleted; `normalise_key` tests moved to `test_scanning.py`.

### Task 1.4: Implement empty directory mirroring

- **Description:** After identifying empty directories during the source scan (Task 1.2), create corresponding directories in the repo that don't already exist. This preserves the SD card's full directory structure in the backup.
- **Inputs:** List of empty directories from source scan
- **Outputs:** Empty directories created in the repo to mirror the SD card structure
- **Acceptance Criteria:**
  - [x] Empty directories from the SD card are created in the repo
  - [x] Directories that already exist are skipped (no error)
  - [x] Directory creation uses `pathlib.Path.mkdir(parents=True, exist_ok=True)`
  - [x] Created directories are reported in the sync summary
  - [x] `.trash` directories are not mirrored
- **Implementation Notes:**
  > Implemented in `compute_sync` (populates `dirs_to_create` from `src_scan.empty_dirs` not present in dest) and `execute_plan` (creates directories with `mkdir(parents=True, exist_ok=True)`, prints count). `.trash` is excluded by the scanner before empty-dir detection.

## Phase 2: Sync Manifest

> **Goal:** Implement the JSON manifest that persists sync state across runs, solving the fresh-clone problem
> **Prerequisites:** Phase 1 complete (comparison engine supports manifest lookup)

### Task 2.1: Implement manifest read/write in `deluge_lib/manifest.py`

- **Description:** Create `deluge_lib/manifest.py` with functions to read, write, and update the sync manifest at `scripts/data/manifest.json`. The manifest is designed as a shared "file inventory" — sync writes it, and other scripts can read it to know what files exist and their stats without rescanning the SD card. The manifest tracks all synced files (both .xml and .wav). The manifest maps lowercased, forward-slash-normalised relative paths (D32, via `normalise_key`) to records containing the file's size and mtime. The entry format is extensible (D30): each entry is a dict, and the sync script only writes size and mtime but ignores any additional fields written by other scripts (the read/update logic must not strip unknown fields). The manifest includes a metadata section with: script version, last-sync ISO 8601 timestamp, total file count, and `last_sync_direction` (D31 — the sync script always writes `"sd-to-local"`; the future reverse-sync will write `"local-to-sd"`). Writing must be atomic (write to temp file in the same directory, then rename). Reading must handle the missing-manifest case gracefully (return empty state). Corrupt JSON is discarded with a warning and treated as empty — no .bak backup.
- **Inputs:** Decisions D2, D11, D13, D17, D18, D26, D30, D31, D32
- **Outputs:** `deluge_lib/manifest.py` with manifest read/write/update functions; `sync_from_sd.py` imports from this module
- **Acceptance Criteria:**
  - [x] Functions live in `deluge_lib/manifest.py`, not in `sync_from_sd.py`
  - [x] Manifest API is reusable — other scripts can call read functions to inspect the inventory
  - [x] Manifest read returns empty state when file is missing
  - [x] Manifest read handles corrupt JSON gracefully (print warning, return empty state — no .bak file created)
  - [x] Manifest write is atomic (temp file + rename)
  - [x] `scripts/data/` directory is created automatically if missing
  - [x] Manifest keys are lowercased, forward-slash-normalised relative paths (D32)
  - [x] Manifest values are dicts containing at minimum size (int) and mtime (float)
  - [x] Entry format is extensible — unknown fields are preserved on read/update, not stripped (D30)
  - [x] Sync script only writes size and mtime per entry (other scripts may add more)
  - [x] All synced file types are tracked (.xml and .wav)
  - [x] Metadata section includes: script version, last-sync ISO 8601 timestamp, total file count, `last_sync_direction` (D31)
  - [x] Sync script writes `last_sync_direction: "sd-to-local"` in metadata
  - [x] Type-annotated and passes mypy strict
- **Implementation Notes:**
  > Created `deluge_lib/manifest.py` with: `ManifestData` dataclass (metadata + files dict), `FileRecord`/`FilesDict` type aliases, `read_manifest()`, `write_manifest()`, `default_manifest_path()`, `make_timestamp()`. Atomic write uses `tempfile.NamedTemporaryFile` with context manager + `Path.replace()`. Corrupt JSON caught via `json.JSONDecodeError` and `ValueError`. The `_parse_manifest` helper preserves all unknown per-file fields (D30 extensibility). `file_count` auto-updated on write to stay consistent with `files` dict. Timestamp uses `datetime.UTC` (Python 3.12). The existing `ManifestDict` type alias in `sync_from_sd.py` will be replaced by imports from this module in Task 2.2.

### Task 2.2: Integrate manifest into comparison flow

- **Description:** Modify `compute_sync` (or its replacement) to load the manifest at the start and pass manifest entries to the comparison function. When a manifest entry exists, comparison checks SD card stat against the manifest (handling the fresh-clone case). When no manifest entry exists, comparison falls back to repo file stat. After a successful sync, collect the size and mtime of all synced files and write the updated manifest. Entries for trashed files (in repo but not on SD card) must be removed from the manifest.
- **Inputs:** Manifest functions from Task 2.1, comparison function from Task 1.1
- **Outputs:** Manifest-aware sync flow with proper manifest updates
- **Acceptance Criteria:**
  - [x] Manifest is loaded at the start of sync
  - [x] Files with manifest entries compare SD stat against manifest
  - [x] Files without manifest entries fall back to repo file stat comparison
  - [x] Manifest entries for trashed files are removed (D22)
  - [x] Manifest is written only after fully successful sync (D11)
  - [x] Manifest entries are updated with current size + mtime for all synced files after copy
  - [x] First run without manifest works correctly (full comparison, manifest created)
  - [x] Subsequent runs with manifest are faster (stat-only for unchanged files)
- **Implementation Notes:**
  > Replaced local `ManifestDict` type alias with `FilesDict` imported from `deluge_lib.manifest`. Added imports for `ManifestData`, `read_manifest`, `write_manifest`, `default_manifest_path`, `make_timestamp`, `FilesDict`. Changed `compute_sync` return type to `tuple[SyncPlan, ScanResult]` so `main()` has access to the source scan for manifest building. In `main()`: manifest loaded via `read_manifest(default_manifest_path())` before `compute_sync`; `manifest_data.files` passed as the manifest dict. New `_build_post_sync_manifest()` helper builds the post-sync manifest: iterates all source scan entries — copied files get dest stat, renamed/unchanged files preserve old manifest entries (keeping D30 unknown fields), files without prior entries get source stat. Trashed files are automatically excluded (not in source scan). Manifest written atomically via `write_manifest()` only after `execute_plan` completes (if `execute_plan` raises, manifest is not written). Passes mypy strict, ruff check, ruff format.

### Task 2.3: Add `scripts/data/` to .gitignore

- **Description:** Add `scripts/data/` to the repository `.gitignore`. The entire directory is gitignored — both `manifest.json` and `sync.log` are machine-specific (D12, D33).
- **Inputs:** Current `.gitignore`, Decisions D12, D33
- **Outputs:** Updated `.gitignore` with directory-level ignore entry
- **Acceptance Criteria:**
  - [x] `scripts/data/` is listed in `.gitignore`
  - [x] Entry is placed near the existing Deluge-specific ignores at the end of the file
  - [x] A comment explains why the directory is ignored (machine-specific sync data)
- **Implementation Notes:**
  > Added `scripts/data/` with comment "Machine-specific sync data (manifest and logs)" after existing Deluge ignores in `.gitignore`.

## Phase 3: Error Recovery and Logging

> **Goal:** Add stop-on-failure error recovery and execution logging
> **Prerequisites:** Phases 1 and 2 complete

### Task 3.1: Implement stop-on-failure error recovery

- **Description:** Wrap the file copy loop in `execute_plan` with error handling. On any `shutil.copy2` failure, stop immediately, print a summary of what was completed (files successfully copied so far) and what failed (the file that caused the error plus remaining files), and exit with a non-zero status. The manifest must not be updated when a failure occurs.
- **Inputs:** Current `execute_plan` function
- **Outputs:** Error-resilient execution with clear failure reporting
- **Acceptance Criteria:**
  - [x] Copy failure is caught and does not propagate as an unhandled exception
  - [x] Summary of completed copies is printed on failure
  - [x] The failing file and error message are clearly reported
  - [x] Remaining (unattempted) file count is reported
  - [x] Script exits with non-zero status on failure
  - [x] Manifest is not written on failure
- **Implementation Notes:**
  > `execute_plan` now returns a `SyncResult` dataclass (success, counts, error info). Each operation phase (copy, mkdir, trash) is wrapped in try/except OSError. On failure: prints the failing file, error message, completed count, and remaining count, then returns `SyncResult(success=False, ...)`. `main()` checks `result.success` — on failure it logs, prints "Manifest was NOT updated", and raises `SystemExit(1)`.

### Task 3.2: Implement execution logging

- **Description:** After each sync (successful or failed), append a structured summary to `scripts/data/sync.log`. Format should follow the old script's pattern: delimited entries with timestamp, status, file counts, and elapsed time. Include counts for all action types: copied, trashed, renamed, unchanged. On failure, include the error message. The log file is machine-specific and gitignored (D33).
- **Inputs:** Old script's `append_to_log` function (pattern reference), Decisions D7, D19, D33
- **Outputs:** Execution log appended to `scripts/data/sync.log`
- **Acceptance Criteria:**
  - [x] Log entry appended after every sync run (success or failure)
  - [x] Entry includes: script name, timestamp, status (SUCCESS/FAILED), file counts (copied, trashed, unchanged), elapsed time
  - [x] Failed entries include the error message
  - [x] `scripts/data/` directory is created if missing
  - [x] Log format is human-readable
  - [x] Log file is gitignored (machine-specific per D33)
- **Implementation Notes:**
  > Added `append_sync_log(result, *, elapsed_seconds, log_path)` function in `sync_from_sd.py`. Follows old script's delimited pattern (`---` separator, key-value lines). Writes to `scripts/data/sync.log` (created via `mkdir(parents=True, exist_ok=True)`). Called from `main()` after `execute_plan` returns, before manifest write decision — so both success and failure are logged. Includes `dirs_created` field in addition to the required counts.

## Phase 4: Cleanup and Testing

> **Goal:** Delete the old script, register the CLI entry point, write tests, and verify the full implementation
> **Prerequisites:** Phases 1–3 complete

### Task 4.1: Delete `scripts/old_sync.py`

- **Description:** Remove `scripts/old_sync.py` from the repository. All its useful patterns have been absorbed into the improved `sync_from_sd.py`.
- **Inputs:** Confirmation that all old_sync.py patterns are implemented in sync_from_sd.py
- **Outputs:** `old_sync.py` deleted
- **Acceptance Criteria:**
  - [x] `scripts/old_sync.py` is removed
  - [x] No remaining imports or references to `old_sync` elsewhere in the codebase
- **Implementation Notes:**
  > File deleted. Grep confirmed no imports or references to `old_sync` in any script file. Plan-only references remain (expected).

### Task 4.2: Register `deluge-sync` CLI entry point

- **Description:** Add a `[project.scripts]` section to `scripts/pyproject.toml` that registers `deluge-sync = "sync_from_sd:main"`. Since `pyproject.toml` has `src = ["scripts"]`, modules are importable from the `scripts/` directory — `sync_from_sd` resolves to `scripts/sync_from_sd.py`. This pattern extends naturally to future scripts: each gets its own entry (e.g. `deluge-fix-refs = "fix_refs:main"`). This allows the user to run `deluge-sync` after installing the package with `uv pip install -e scripts/` (or equivalent).
- **Inputs:** Current `scripts/pyproject.toml`, Decisions D24, D26
- **Outputs:** Updated `pyproject.toml` with CLI entry point
- **Acceptance Criteria:**
  - [x] `[project.scripts]` section added to `pyproject.toml`
  - [x] Entry is `deluge-sync = "sync_from_sd:main"` (module path relative to `src = ["scripts"]`)
  - [ ] Running `deluge-sync` after install invokes the sync script
  - [x] Pattern supports future scripts via additional entries
  - [x] Existing `pyproject.toml` content is preserved (no unrelated changes)
- **Implementation Notes:**
  > Added `[project.scripts]` section between `[project]` dependencies and `[project.optional-dependencies]`. Runtime verification deferred to Task 4.5 (manual verification).

### Task 4.3: Write unit tests

- **Description:** Create tests covering the core logic across `sync_from_sd.py` and the `deluge_lib/` modules. Tests are split per module (D35): `test_manifest.py`, `test_scanning.py`, and `test_sync_from_sd.py`. Each tests its corresponding module independently. `normalise_key` tests live in `test_scanning.py` (D38). Tests should use temporary directories and mock files — no real SD card or `DELUGE/` directory needed. Focus on: manifest (read/write/corrupt handling/extensible fields/direction metadata), scanning (file-type filtering, .trash skip, symlink skip, empty dir detection, generic root path, stat capture, normalise_key), and comparison engine (stat-based comparison with and without manifest).
- **Inputs:** All implemented functions from Phases 1–3
- **Outputs:** Test files at `scripts/tests/`: `test_manifest.py`, `test_scanning.py`, `test_sync_from_sd.py`
- **Acceptance Criteria:**
  - [x] Unified comparison: test all cases (missing file → copy, size differs → copy, mtime within tolerance → skip, mtime differs → copy)
  - [x] Manifest-aware comparison: test that manifest entries are used when available, repo stat fallback when not
  - [x] Manifest: test read (missing file, valid file, corrupt file — no .bak created), test atomic write, test metadata section (including `last_sync_direction`)
  - [x] Manifest extensibility: test that unknown fields in entries are preserved on read/update (D30)
  - [x] Manifest paths: test that keys use forward slashes regardless of OS (D32)
  - [x] File-type filtering: test that only .xml and .wav are included, .DS_Store etc. are excluded
  - [x] Root-level files: test that files at the root are included in the scan
  - [x] Generic scanner: test that scanner works on any root path, not just SD card (D27)
  - [x] Scanner stat capture: test that scanner returns stat info (size, mtime) alongside paths (D28)
  - [x] Symlinks: test that symlinks in source are silently skipped
  - [x] Case-insensitive paths: test that files differing only in case are matched as unchanged
  - [x] Normalise_key: test `normalise_key` (lowercase + forward slashes) in `test_scanning.py`
  - [x] Empty directory mirroring: test that empty source directories are created in destination
  - [x] Trashed entries: test that trashed files are removed from manifest
  - [x] .trash exclusion: test that .trash directories are skipped on both source and destination
  - [x] Error recovery: test that copy failure stops execution and reports correctly
  - [x] All tests pass with `uv run pytest`
- **Implementation Notes:**
  > 72 tests across 3 test files: `test_manifest.py` (16), `test_scanning.py` (26 — includes normalise_key tests from former `test_paths.py`), `test_sync_from_sd.py` (30). All pass.

### Task 4.4: Run linting and type checking

- **Description:** Run Ruff and mypy across the modified files to ensure compliance with project tooling standards.
- **Inputs:** All modified files
- **Outputs:** Clean lint and type-check results
- **Acceptance Criteria:**
  - [x] `uv run ruff check scripts/` passes with no errors
  - [x] `uv run ruff format --check scripts/` passes
  - [x] `uv run mypy scripts/sync_from_sd.py scripts/deluge_lib/manifest.py scripts/deluge_lib/scanning.py scripts/deluge_lib/paths.py` passes in strict mode
  - [x] No new warnings introduced
- **Implementation Notes:**
  > All checks pass clean.

### Task 4.5: Manual verification

- **Description:** Run the improved script against a real or simulated SD card to verify end-to-end behaviour. Test dry-run, confirm, and default modes. Verify manifest creation, empty directory mirroring, logging, and error recovery.
- **Inputs:** Working script from Phases 1–3, test environment
- **Outputs:** Verified working script
- **Acceptance Criteria:**
  - [ ] `uv run python sync_from_sd.py --dry-run` shows correct preview without modifying anything
  - [ ] Default mode shows preview then prompts for confirmation
  - [ ] `--confirm` skips preview and prompts directly
  - [ ] Manifest is created at `scripts/data/manifest.json` after successful sync
  - [ ] Manifest contains metadata header (version, timestamp, count) and entries for all synced files
  - [ ] Subsequent runs with manifest are noticeably faster (stat-only for unchanged files)
  - [ ] Case differences with matching size are treated as unchanged (not renamed or re-copied)
  - [ ] Empty directories on SD card are mirrored in repo
  - [ ] `scripts/data/sync.log` contains a structured entry after each run
  - [ ] `deluge-sync` command works after package install
  - [ ] Only `.xml` and `.wav` files are synced
  - [ ] Root-level files (e.g. MIDIFollow.XML) are synced
  - [ ] `.trash` directories on source are excluded
  - [ ] Symlinks on source are silently skipped
- **Implementation Notes:**
  > _Space for the Implement agent_

### Task 4.6: Refactor `deluge_sdk.find_all_xml_files()` to use `scanning.py`

- **Description:** `deluge_sdk.py` has its own `find_all_xml_files()` that does a separate rglob of KITS/SYNTHS/SONGS for XMLs. Refactor this to use the shared `deluge_lib.scanning` module instead of duplicating the walking logic (D29). This is a small change — the function should call the scanner with appropriate parameters and filter/restructure the results to match its current return type.
- **Inputs:** Current `deluge_sdk.find_all_xml_files()`, `deluge_lib/scanning.py` from Task 1.2
- **Outputs:** Refactored `deluge_sdk.find_all_xml_files()` using the shared scanner
- **Acceptance Criteria:**
  - [x] `find_all_xml_files()` uses `deluge_lib.scanning` instead of its own rglob
  - [x] Return type and behaviour are unchanged from the caller's perspective
  - [x] Existing tests (if any) and callers continue to work
  - [x] No duplicated walking logic between `deluge_sdk.py` and `scanning.py`
- **Implementation Notes:**
  > Refactored to call `scan_tree(subdir, progress=False)` for each of KITS/SYNTHS/SONGS, then filter results to `.XML` suffix only. Returns sorted absolute paths as before. `scan_tree` already handles symlink skipping and `.trash` exclusion. Ruff + mypy strict pass clean.

## Progress Tracker

| Phase | Status | Tasks Complete | Notes |
|-------|--------|---------------|-------|
| Phase 1: Core Comparison Engine | Complete | 3/3 (Task 1.3 removed) | |
| Phase 2: Sync Manifest | Complete | 3/3 | |
| Phase 3: Error Recovery and Logging | Complete | 2/2 | |
| Phase 4: Cleanup and Testing | In Progress | 5/6 | Task 4.5 (manual verification) remaining |

## Open Questions

1. ~~**Should the manifest store the destination file's hash in addition to the source file's hash?**~~
   - **Resolution:** N/A — hashing has been removed from the plan entirely. The manifest stores size + mtime, not hashes. No hash-related questions remain.

2. ~~**Should the execution log format be YAML, JSON, or plain text?**~~
   - **Resolution:** Resolved by D19 and ~~D20~~ (D33). Plain text with structured key-value pairs, matching the old script's format. The log lives at `scripts/data/sync.log` and is gitignored (machine-specific). The log is primarily for human reading; machine parsing is not a current requirement.

## References

### Standards Applied
- [project.md](../../agent-system/standards/project.md) — SD card safety rules and platform requirements
- [Python core standard](../../agent-system/standards/languages/python/core.md) — Project structure, entry point pattern, pathlib usage, pyproject.toml configuration

### Project Files
- [sync_from_sd.py](../../scripts/sync_from_sd.py) — Current script being improved (sync-specific logic stays here)
- [old_sync.py](../../scripts/old_sync.py) — Deprecated predecessor with patterns to absorb (to be deleted)
- [cli_utils.py](../../scripts/deluge_lib/cli_utils.py) — Shared CLI utilities (env loading, confirmation prompts)
- [deluge_sdk.py](../../scripts/deluge_lib/deluge_sdk.py) — XML parsing utilities (existing, refactored in Phase 4 to use scanning.py — D29)
- [manifest.py](../../scripts/deluge_lib/manifest.py) — New: manifest read/write/update as shared file inventory (extensible format — D30)
- [scanning.py](../../scripts/deluge_lib/scanning.py) — New: generic filtered file scanner with stat capture (D27, D28) + normalise_key (D38)
- [pyproject.toml](../../scripts/pyproject.toml) — Project configuration and dependencies (to be updated with CLI entry point)
- [.gitignore](../../.gitignore) — Repository ignore rules (to be updated with `scripts/data/` directory ignore)

## Change Log

| Date | Change | Reason |
|------|--------|--------|
| 09 Apr 2026 | Initial plan created | — |
| 09 Apr 2026 | Plan revision: decisions D13–D25 incorporated | Second round of clarifying questions resolved 13 new decisions. Key additions: manifest scoped to SAMPLES/ only (D13), local-edit conflict detection (D14), root-level file scanning (D15), empty directory mirroring (D16), manifest metadata header (D17), simplified corrupt manifest handling (D18), log relocated to scripts/data/ and committed to git (D19, D20), hash-during-copy optimisation (D21), trashed manifest entries removed (D22), case-rename operations (D23), CLI entry point (D24), symlink skipping (D25). Updated D2, D7, D12 where superseded. Added 4 new tasks (1.4, 2.3, 2.4, 4.2), renumbered Phase 4 tasks. Total tasks: 12 → 15. Updated conflict detection specification, architecture, and acceptance criteria throughout. Closed both open questions. |
| 09 Apr 2026 | Shared library extraction (D26) and CLI entry point update (D24) | Extracted reusable functions into `deluge_lib/` modules: `hashing.py` (streaming MD5, hash-during-copy), `manifest.py` (read/write/update as shared file inventory), `scanning.py` (filtered scanner, path dict builder), `paths.py` (case-insensitive normalisation). Updated D24 with correct module path (`sync_from_sd:main`) and multi-script entry point pattern. Updated architecture section with new file structure, module location annotations, and import-aware data flow. Updated Tasks 1.1–1.3, 2.1, 2.3, 4.2–4.4 with module boundaries and acceptance criteria. Added shared library design to cross-cutting concerns. Added integration points for new modules. |
| 09 Apr 2026 | Major simplification: removed hashing, conflict detection, and DST tolerance | Based on detailed discussion about the user's actual workflow. **Removed:** (1) All MD5 hashing — `deluge_lib/hashing.py` dropped, D5 and D21 struck, Task 2.3 (hash-during-copy) removed. No realistic scenario where same-name, same-size, same-mtime files have different content. Hashing may return for future sample management scripts. (2) All conflict detection — three-way comparison replaced with two-way (SD vs manifest). SD always wins. D14 struck. WAV edits happen on PC only (future reverse-sync); XML edits come from hardware only; XML renames appear as new+deleted. (3) DST ±3600s tolerance — kept only ±2s for FAT32 rounding as a minor safety margin. **Simplified:** Manifest now stores `{size, mtime}` instead of `{size, md5}` and tracks all file types (D2, D13 updated). Unified comparison flow for all file types — no separate XML vs WAV logic. **Net effect:** Removed `deluge_lib/hashing.py` from file structure and all references, removed Conflict Detection Logic section, removed conflict-related risk rows, simplified architecture and cross-cutting concerns. Total tasks: 15 → 14. |
| 09 Apr 2026 | Pre-implementation review: decisions D27–D36 incorporated | Third round of decisions from pre-implementation review. **Key additions:** scanner is generic (any root path — D27), scanner returns stat info in same pass (D28), refactor `deluge_sdk.find_all_xml_files()` to use scanning.py (D29), manifest entry format is extensible with optional fields (D30), manifest metadata tracks sync direction (D31), manifest paths use forward slashes (D32), `paths.py` scoped to exactly 2 functions (D34), tests split per module (D35), no trash auto-cleanup confirmed (D36). **Reversed:** D20 struck (sync.log is now gitignored per D33). **Updated:** D7 (log is gitignored), D12 (reverted to whole-directory gitignore). **Task changes:** Task 1.2 updated (generic scanner, stat capture), Task 1.3 updated (2-function scope), Task 2.1 updated (extensible format, direction metadata, forward-slash paths), Task 2.3 simplified (whole-directory gitignore), Task 3.2 updated (log is local-only), Task 4.3 updated (per-module test files), new Task 4.6 (refactor deluge_sdk). Total tasks: 14 → 15. |
| 09 Apr 2026 | Post-implementation review: fixes applied | Removed DST ±3600s tolerance from `_mtime_matches` (was kept by previous implementer despite plan removing it). Fixed `scan_tree` progress label — added `label` parameter so source/destination scans show distinct messages. Added warning on `stat()` failure in scanner instead of silent skip. Cleaned up `manifest_data.files or None` masking in `main()`. Updated plan checkboxes and progress tracker to reflect actual completion state. |
| 09 Apr 2026 | Plan revision: removed case-rename (D37) and paths.py (D38) | **D37:** Case differences with matching content now treated as unchanged (skipped) instead of renamed. Eliminates `SyncPlan.files_to_rename`, rename handling in `execute_plan`/`print_plan`/`_plan_is_empty`, rename count in `SyncResult`/`append_sync_log`, case-rename detection branch in `compute_sync`, and the two-step rename safety logic. D23 struck. **D38:** `paths.py` removed as a module — `normalise_key` moved into `scanning.py`, `safe_rename` deleted. `test_paths.py` deleted, `normalise_key` tests moved to `test_scanning.py`. D34 struck. Task 1.3 removed. Updated architecture, file structure, data flow, integration points, cross-cutting concerns, risk mitigation, and references throughout. Total tasks: 15 → 14. |
