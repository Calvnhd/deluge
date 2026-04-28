# Research: Zip Backup and Sync-to-SD Scripts

> **Document Type:** Research
> **Date:** 13 April 2026
> **Request:** Research the existing codebase to inform the creation of two new scripts: (1) a .zip backup archiver for the SD card or repo DELUGE/ directory, and (2) a reverse sync script that deploys repo DELUGE/ contents to the physical SD card.
> **Pipeline:** Research → Plan → Implement

## Executive Summary

The existing codebase provides a well-factored shared library (`deluge_lib/`) with reusable scanning, syncing, and CLI utilities that both new scripts can leverage directly. The zip backup script is straightforward — Python's `zipfile` stdlib module plus the existing `scan_tree()` scanner covers the entire requirement with no new dependencies. The sync-to-SD script is more nuanced: it can reuse `compute_sync()` and `print_plan()` from `syncing.py` but requires a custom trash strategy (SD deletions backed up to repo `.trash/` with an `SD-` prefix) and stricter safety guardrails (dry-run default, explicit confirmation). Two new `.env` variables are needed (`ZIP_SOURCE_PATH` and `ZIP_DEST_PATH`). No new third-party dependencies are required for either script.

## Objectives

- Catalogue all reusable components in `deluge_lib/` and existing scripts
- Determine how the zip script should filter files and structure the archive
- Determine how the sync-to-SD script should handle deletions safely
- Identify new `.env` variables needed
- Assess cross-platform risks (Windows/WSL)
- Define how both scripts integrate with entry points, tests, and project conventions

## Feature Overview

### Purpose and Value

1. **Zip backup (`create_backup.py`)** — Creates timestamped `.zip` archives of the SD card (or repo `DELUGE/`) as a last-resort backup. These archives represent the final fallback if both the physical SD card and the git repository are lost or corrupted. Archives are saved to a cloud-synced folder.

2. **Sync repo to SD (`sync_to_sd.py`)** — Deploys the curated repo `DELUGE/` directory back to the physical SD card. This is the reverse of `sync_from_sd.py` and completes the edit-review-deploy workflow: sync from SD → edit in repo → review via git → deploy back to SD.

### Primary Use Cases

| Script | Trigger | Frequency |
|--------|---------|-----------|
| `create_backup.py` | Before major reorganisation, periodic backup | Semi-regular |
| `sync_to_sd.py` | After reviewing repo changes, ready to deploy to hardware | After editing sessions |

### Inputs and Outputs

| Script | Inputs | Outputs |
|--------|--------|---------|
| `create_backup.py` | Source directory (SD card or `DELUGE/`), dest directory | Timestamped `.zip` at dest path |
| `sync_to_sd.py` | `DELUGE_ROOT`, `SD_CARD_PATH` | Updated SD card contents, SD trash in repo `.trash/` |

### Scope

**In scope:**
- Zip backup of XML and WAV files from either SD card or repo `DELUGE/`
- Reverse sync from repo `DELUGE/` to mounted SD card
- Dry-run preview for both scripts
- SD card safety (read-only for zip, confirmation-gated writes for sync)
- Cross-platform operation (WSL + Windows/Cmder)

**Out of scope:**
- Incremental/differential backups (zip is always a full snapshot)
- Zip restore (manual extraction, not scripted)
- Manifest updates from sync-to-SD (the existing manifest tracks SD→repo sync state)
- Sample-only sync (both scripts handle the full `DELUGE/` tree)

## Existing Assets Analysis

| Capability | Status | Location | Notes |
|------------|--------|----------|-------|
| File scanning with filter | ✅ Ready | `deluge_lib/scanning.py` — `scan_tree()` | Supports `file_filter="wav"`, `"xml"`, `"both"`; skips `.trash`; case-normalised keys |
| Sync plan computation | ✅ Ready | `deluge_lib/syncing.py` — `compute_sync()` | Compares source/dest trees; returns copy/delete/unchanged plan |
| Sync plan display | ✅ Ready | `deluge_lib/syncing.py` — `print_plan()` | Human-readable preview with configurable delete label |
| Sync plan execution | ⚠️ Partial | `deluge_lib/syncing.py` — `execute_plan()` | Supports `"trash"` and `"delete"` modes; needs new mode for SD trash → repo .trash |
| Sync logging | ✅ Ready | `deluge_lib/syncing.py` — `append_sync_log()` | Structured log entries with timestamps and counts |
| DELUGE_ROOT loader | ✅ Ready | `deluge_lib/cli_utils.py` — `get_deluge_root()` | Loads from `.env`, validates existence |
| SD_CARD_PATH loader | ✅ Ready | `deluge_lib/cli_utils.py` — `get_sd_card_path()` | Loads from `.env`, validates mount |
| CLOUD_BACKUP_PATH loader | ✅ Ready | `deluge_lib/cli_utils.py` — `get_cloud_backup_path()` | Pattern for new env var loaders |
| Confirmation prompt | ✅ Ready | `deluge_lib/cli_utils.py` — `confirm_apply()` | `[y/N]` default-no prompt |
| FAT32 mtime normalisation | ✅ Ready | `deluge_lib/scanning.py` — `normalise_mtime()` | 2-second truncation |
| FAT32 mtime comparison | ✅ Ready | `deluge_lib/syncing.py` — `_mtime_matches()` | ±2-second tolerance |
| Entry point pattern | ✅ Ready | All scripts | `def main(argv=None)` + `if __name__` guard |
| Test patterns | ✅ Ready | `scripts/tests/` | `tmp_path`, `monkeypatch`, `_touch()` helper, `patch("deluge_lib.cli_utils.load_dotenv")` |
| .env.example | ⚠️ Needs update | `scripts/.env.example` | Needs `ZIP_SOURCE_PATH` and `ZIP_DEST_PATH` |
| pyproject.toml entry points | ⚠️ Needs update | `scripts/pyproject.toml` | Needs entries for new scripts |
| Python zipfile module | ✅ Ready | stdlib | No new dependency needed |

## Findings

### 1. Existing Script Conventions

**Source:** All files in `scripts/` and `scripts/deluge_lib/`.

Every script in the codebase follows a consistent pattern:

| Convention | Pattern | Used By |
|------------|---------|---------|
| Entry point | `def main(argv: list[str] \| None = None) -> None` | All 5 scripts |
| CLI parsing | `argparse.ArgumentParser` with `--dry-run` flag | `sync_from_sd.py`, `sync_samples_to_cloud.py` |
| Env loading | `get_*()` functions in `cli_utils.py` loading from `scripts/.env` | All scripts |
| Preview-then-confirm | Compute plan → print plan → prompt → execute | Both sync scripts |
| Progress output | Print source/dest paths, plan summary, result counts | Both sync scripts |
| Error handling | `SyncError` with context (file, copied count, remaining count) | Both sync scripts |
| Logging | `append_sync_log()` after execution | Both sync scripts |
| Dry-run | `--dry-run` flag prints plan then exits, no prompt | Both sync scripts |

#### Script-Level Patterns

**`sync_from_sd.py`** — The closest analogue to `sync_to_sd.py`:
- Loads `SD_CARD_PATH` (source) and `DELUGE_ROOT` (dest)
- Calls `compute_sync(sd_path, deluge_root, manifest=manifest_files)`
- Calls `print_plan(plan, dest=deluge_root)`
- Calls `execute_plan(plan, dest=deluge_root)` — uses default `delete_mode="trash"`
- Updates manifest after successful sync
- Logs result with `append_sync_log()`

**`sync_samples_to_cloud.py`** — Demonstrates alternative sync usage:
- Syncs a subset (`DELUGE/SAMPLES/`) to a different destination
- Uses `file_filter="wav"` to sync only WAV files
- Uses `delete_mode="delete"` (hard-delete, no trash) for cloud dest
- Custom log path: `data/cloud_sync.log`
- No manifest (cloud sync doesn't need one)

### 2. `scanning.py` — File Scanning

**Source:** [scripts/deluge_lib/scanning.py](scripts/deluge_lib/scanning.py)

`scan_tree()` is the universal file scanner used by all sync and analysis scripts. Key properties:

- **Filters:** `FileFilter = Literal["wav", "xml", "both"]` — can scan for WAV only, XML only, or both
- **`.trash` exclusion:** Automatically skips `.trash` directories (case-insensitive)
- **Case normalisation:** Keys are lowercase with forward slashes (`normalise_key()`)
- **Stat capture:** Each `FileEntry` has `rel_path` (original case), `size`, and `mtime` (FAT32-normalised)
- **Cross-platform:** Uses `os.walk()` with `pathlib.Path` for results

For the **zip script**, `scan_tree(root, file_filter="both")` provides exactly the file list needed — all XML and WAV files, excluding `.trash`.

For the **sync-to-SD script**, `compute_sync()` already calls `scan_tree()` internally, so no direct scanner call is needed.

### 3. `syncing.py` — Sync Primitives

**Source:** [scripts/deluge_lib/syncing.py](scripts/deluge_lib/syncing.py)

#### 3.1 `compute_sync()` Reuse for Sync-to-SD

`compute_sync(source, dest, *, manifest=None, file_filter="both")` is direction-agnostic — it compares any source tree against any dest tree and produces a `SyncPlan`. For sync-to-SD:

```python
plan, src_scan = compute_sync(deluge_root, sd_path)
```

This will:
- Scan `DELUGE/` as source and SD card as dest
- Identify files to copy (new or modified in repo)
- Identify files to delete (on SD but not in repo)
- Handle FAT32 mtime tolerance via `normalise_mtime()` and `_mtime_matches()`

**No modifications to `compute_sync()` are needed.**

#### 3.2 `execute_plan()` — Trash Mode Limitation

`execute_plan(plan, *, dest, delete_mode="trash"|"delete")` currently supports two delete modes:

1. **`"trash"`** — Moves deleted files to `dest/.trash/<timestamp>/`. This puts the trash **inside the destination directory**. For sync-to-SD, this would put trash on the SD card itself, which is explicitly unwanted.

2. **`"delete"`** — Hard-deletes files from dest. Too dangerous for SD card use.

Neither mode matches the requirement: **copy SD-side deletions to the repo `.trash/` directory (not the SD card), then delete from the SD card.**

**Options:**
- **A: New delete mode** — Add `delete_mode="remote-trash"` (or similar) to `execute_plan()` with a `trash_dest` parameter specifying where to put trash. This keeps execution in the shared module.
- **B: Custom execution in script** — Handle the copy-to-repo-trash-then-delete logic directly in `sync_to_sd.py`, reusing only `compute_sync()` and `print_plan()` from the shared module.
- **C: Separate trash step** — Execute plan with `delete_mode="delete"` but pre-copy files to repo `.trash/` before calling `execute_plan()`.

**Recommendation: Option B** — The sync-to-SD trash strategy is unique (trash goes to a completely separate directory tree with an `SD-` prefix). Adding this to the shared `execute_plan()` would over-generalise the interface for a single consumer. The script should implement its own execution loop (copy files, then handle SD deletions), mirroring the structure of `execute_plan()` but with the custom trash logic. The copy logic is simple (`shutil.copy2` + `mkdir`), and having it in the script makes the safety-critical SD write path fully visible in one file.

#### 3.3 Plan Display Reuse

`print_plan(plan, *, dest, delete_label="trash")` works as-is for sync-to-SD. The only adjustment is the label:

```python
print_plan(plan, dest=sd_path, delete_label="delete")
```

#### 3.4 Logging Reuse

`append_sync_log()` accepts an optional `log_path` parameter (defaulting to `data/sync.log`). The sync-to-SD script should use a separate log file:

```python
_TO_SD_LOG_PATH = Path(__file__).resolve().parent / "data" / "to_sd_sync.log"
append_sync_log(result, elapsed_seconds=elapsed, log_path=_TO_SD_LOG_PATH)
```

### 4. `.env` Configuration

**Source:** [scripts/.env.example](scripts/.env.example)

Current variables:

| Variable | Purpose | Used By |
|----------|---------|---------|
| `DELUGE_ROOT` | Repo `DELUGE/` directory (absolute path) | All scripts |
| `SD_CARD_PATH` | Mounted SD card path | `sync_from_sd.py` |
| `CLOUD_BACKUP_PATH` | Cloud-synced folder for sample backups | `sync_samples_to_cloud.py` |

#### New Variables Needed

**For zip backup:**

| Variable | Purpose | Example Value |
|----------|---------|---------------|
| `ZIP_SOURCE_PATH` | Directory to archive (SD card or `DELUGE/`) | `/media/$USER/DELUGE` or same as `DELUGE_ROOT` |
| `ZIP_DEST_PATH` | Directory where `.zip` files are saved | `C:/Users/you/OneDrive/DelugeBackup/Archives` |

The user noted that the zip source is "usually the mounted SD card" but "there may be special one-off cases where the repo DELUGE folder requires archiving, in which case the .env variable can be adjusted." A single `ZIP_SOURCE_PATH` variable with re-pointing is simpler than a CLI flag, since the use case is rare.

**For sync-to-SD:** No new variables needed — `DELUGE_ROOT` (source) and `SD_CARD_PATH` (dest) already exist.

#### New `cli_utils.py` Functions

Following the established pattern (`get_deluge_root()`, `get_sd_card_path()`, `get_cloud_backup_path()`):

```python
def get_zip_source_path() -> Path:
    """Load ZIP_SOURCE_PATH from scripts/.env."""

def get_zip_dest_path() -> Path:
    """Load ZIP_DEST_PATH from scripts/.env."""
```

These follow the exact same pattern: `load_dotenv()`, `os.environ.get()`, validate existence, `raise SystemExit` on failure.

### 5. SD Card Safety Analysis

**Source:** [agent-system/standards/project.md](agent-system/standards/project.md), [temp/new-scripts.md](temp/new-scripts.md)

#### 5.1 Zip Backup — Read-Only Guarantee

The zip script reads from the source directory and writes **only** to the zip destination. It never modifies the source. This is inherently safe — Python's `zipfile.ZipFile` in `"w"` mode creates a new file at the destination path. The source is accessed via `Path.read_bytes()` or `zipfile.write()`, both read-only operations.

**Risk:** Accidental write to source if paths are confused. **Mitigation:** The script reads from `ZIP_SOURCE_PATH` and writes to `ZIP_DEST_PATH` — these are separate variables that can never overlap (a zip file is a single file in the dest directory, not a directory itself).

#### 5.2 Sync-to-SD — Safety Guardrails

Per `standards/project.md` rule §4: "When syncing from the repository back to the SD card for deployment, dry-run should be the default behaviour."

Required safety measures:
1. **Dry-run by default** — Without `--apply` or explicit confirmation, only preview changes
2. **Explicit confirmation prompt** — `confirm_apply()` with clear messaging about what will be written to the SD card
3. **SD card mount validation** — `get_sd_card_path()` already validates the mount point exists
4. **SD trash → repo** — Before deleting any file from the SD card, copy it to `DELUGE_ROOT/.trash/SD-<timestamp>/` in the repo. This ensures no data is permanently lost from the SD card without a local backup.
5. **Atomic per-file operations** — Copy, then verify (size check), then proceed. On failure, report exactly what was completed and what remains.
6. **`SyncError` propagation** — Follow the `sync_from_sd.py` pattern of catching `OSError` during execution and wrapping in `SyncError` with context.

#### 5.3 SD Trash Naming Convention

Per requirements: "save SD trash to the local repo... in a folder with `SD` as a prefix."

Proposed path structure:
```
DELUGE/.trash/SD-20260413_120000/
  KITS/OldKit.XML
  SAMPLES/DRUMS/unused.wav
```

This follows the existing `.trash` convention (timestamped subdirectories) used by `execute_plan()` in trash mode, with the `SD-` prefix distinguishing SD-sourced trash from repo-edit trash.

### 6. File Filtering

**Source:** [scripts/deluge_lib/scanning.py](scripts/deluge_lib/scanning.py)

#### 6.1 Zip Backup Filtering

The user requirement: "The .zip should only archive xml and .wav files (similar to the sync script) unless doing so creates unnecessary complexity and potential bugs."

Using `scan_tree(root, file_filter="both")` gives exactly XML + WAV files with `.trash` exclusion. This is already battle-tested by the sync scripts. No additional filtering logic needed.

The zip archive should also include `MIDIFollow.XML` at the root level. The `scan_tree()` function scans recursively from the root, so this file will be captured — it's an XML file at the top level of `DELUGE/`.

**Edge case:** The SD card or `DELUGE/` may contain other files (`.DS_Store`, `Thumbs.db`, `.gitkeep`, etc.). These are correctly excluded by `scan_tree()`'s extension filter.

#### 6.2 Sync-to-SD Filtering

`compute_sync()` accepts `file_filter` (defaults to `"both"`). This means the sync-to-SD will only process XML and WAV files, matching the sync-from-SD behaviour. Non-XML/non-WAV files on the SD card will be left untouched (they won't appear in the dest scan and thus won't be marked for deletion).

### 7. Cross-Platform Considerations

**Source:** [agent-system/standards/project.md](agent-system/standards/project.md) §Platform Requirements

| Concern | Impact | Mitigation |
|---------|--------|------------|
| Path separators in zip | Zip entries should use forward slashes per ZIP spec | `zipfile` with `arcname=str(PurePosixPath(rel_path))` |
| SD card path format | Linux: `/media/$USER/DELUGE`, Windows: `D:\` | Already handled by `SD_CARD_PATH` .env variable |
| FAT32 mtime | 2-second resolution, already normalised by `scan_tree()` | No additional work needed |
| `shutil.copy2` on FAT32 | May not preserve all metadata; mtime preserved at FAT32 resolution | Acceptable — mtime is the only metadata that matters |
| File locking on Windows | Windows may lock files open in other programs | Catch `PermissionError` in copy/delete operations |
| Long path support on Windows | Paths > 260 chars may fail on older Windows | Unlikely for Deluge paths but `pathlib` handles `\\?\` prefix if needed |
| `zipfile` compression | `ZIP_DEFLATED` requires `zlib` (available in standard CPython) | No risk — CPython always includes zlib |

#### 7.1 Zip Path Handling

The ZIP specification requires forward slashes for path separators within the archive. On Windows, `Path.relative_to()` returns backslash paths. The established codebase pattern is to use `PurePosixPath` for normalisation:

```python
from pathlib import PurePosixPath
arcname = str(PurePosixPath(file_path.relative_to(source_root)))
```

This ensures zip archives created on Windows have correct internal paths and can be extracted on any platform.

### 8. Zip Script — Design Details

#### 8.1 Archive Naming

Timestamped filename for uniqueness and chronological sorting:

```
DELUGE-backup-2026-04-13_120000.zip
```

Pattern: `DELUGE-backup-<YYYY-MM-DD>_<HHMMSS>.zip`

#### 8.2 Archive Structure

The zip should mirror the source directory structure. If archiving from the SD card mounted at `/media/user/DELUGE`:

```
KITS/
  KIT001.XML
  COMMUNITY/
    ...
SYNTHS/
  ...
SONGS/
  ...
SAMPLES/
  DRUMS/
    Kick.wav
    ...
MIDIFollow.XML
```

The top-level `DELUGE/` is not included in the archive paths — the contents of the source directory become the root of the zip. This matches the pattern where `DELUGE/` is the mount point name, not a meaningful directory.

#### 8.3 Compression

WAV files are uncompressed PCM audio — they benefit from ZIP compression. XML files are highly compressible text. Use `ZIP_DEFLATED` (standard deflate compression) for meaningful size reduction. Python's `zipfile` module supports this natively.

#### 8.4 Implementation Approach

```python
# Pseudocode
source = get_zip_source_path()
dest_dir = get_zip_dest_path()
scan = scan_tree(source, file_filter="both")

zip_name = f"DELUGE-backup-{timestamp}.zip"
zip_path = dest_dir / zip_name

with zipfile.ZipFile(zip_path, "w", ZIP_DEFLATED) as zf:
    for key, entry in scan.files.items():
        file_path = source / entry.rel_path
        arcname = str(PurePosixPath(entry.rel_path))
        zf.write(file_path, arcname)
```

No modifications to `deluge_lib/` needed for this script. It's a consumer of `scan_tree()` and `cli_utils` only.

### 9. Sync-to-SD Script — Design Details

#### 9.1 Execution Flow

```
1. Load DELUGE_ROOT (source) and SD_CARD_PATH (dest)
2. Validate SD card is mounted
3. compute_sync(deluge_root, sd_path)  # reuse shared module
4. print_plan(plan, dest=sd_path, delete_label="delete")
5. If --dry-run: exit
6. confirm_apply("This will modify the SD card at {sd_path}. Continue?")
7. Execute copies: shutil.copy2 from repo to SD
8. Execute deletions: copy from SD to repo .trash/SD-<timestamp>/, then delete from SD
9. Log result
```

#### 9.2 No Manifest for Sync-to-SD

The existing manifest (`scripts/data/manifest.json`) tracks the SD→repo sync state. The sync-to-SD direction should **not** update this manifest — it represents a different sync direction. Using `compute_sync()` without a manifest (like `sync_samples_to_cloud.py` does) relies on direct stat comparison, which is appropriate here. The FAT32 tolerance handling in `compute_sync()` and `scan_tree()` ensures correct comparison.

#### 9.3 Custom Execution Logic

As discussed in §3.2 (Finding: Option B), the script implements its own execution loop rather than using `execute_plan()`:

```python
# Copy phase: repo → SD
for src, dst in plan.files_to_copy:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)

# Trash phase: SD → repo .trash, then delete from SD
trash_base = deluge_root / ".trash" / f"SD-{timestamp}"
for sd_file in plan.files_to_delete:
    rel = sd_file.relative_to(sd_path)
    trash_dest = trash_base / rel
    trash_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(sd_file, trash_dest)  # backup first
    sd_file.unlink()                   # then delete from SD
```

Each phase wraps in try/except to produce `SyncError` with progress context on failure.

### 10. Testing Patterns

**Source:** All files in `scripts/tests/`.

#### 10.1 Established Patterns

| Pattern | Usage | Relevant To |
|---------|-------|-------------|
| `tmp_path` fixture | All tests use pytest's `tmp_path` for isolated filesystem | Both scripts |
| `_touch()` helper | Creates files with optional content and mtime in `conftest.py` | Both scripts |
| `monkeypatch.setenv()` | Sets env vars for test isolation | Both scripts |
| `patch("deluge_lib.cli_utils.load_dotenv")` | Prevents `.env` file from interfering with tests | Both scripts |
| `patch("module.confirm_apply", return_value=True)` | Auto-confirms prompts in tests | `sync_to_sd.py` |
| `capsys` fixture | Captures stdout for output assertions | Both scripts |
| Class-based test organisation | `class TestDryRun`, `class TestFullSync`, etc. | Both scripts |
| `pytest.raises(SystemExit)` | Tests for config validation failures | Env var tests |

#### 10.2 Test File Naming

Convention: `test_<script_name>.py` — e.g., `test_sync_from_sd.py`, `test_sync_samples_to_cloud.py`.

New test files: `test_create_backup.py`, `test_sync_to_sd.py`.

#### 10.3 Testing Strategy for Each Script

**`create_backup.py`:**
- Dry-run shows preview without creating zip
- Full run creates zip with correct contents
- Zip contains only XML and WAV files
- Zip preserves directory structure
- Zip uses forward-slash paths internally
- Missing source directory raises SystemExit
- Missing dest directory raises SystemExit

**`sync_to_sd.py`:**
- Dry-run shows preview without modifying SD (tmp_path)
- Full sync copies new files to dest
- Full sync overwrites modified files
- Full sync backs up SD-only files to repo `.trash/SD-<timestamp>/` then deletes from dest
- Unchanged files are left alone
- Abort on confirmation decline
- SyncError on copy failure with progress context
- SyncError on trash/delete failure with progress context
- Log entry written on success and failure

### 11. pyproject.toml Integration

**Source:** [scripts/pyproject.toml](scripts/pyproject.toml)

New entry points needed:

```toml
[project.scripts]
deluge-sync = "sync_from_sd:main"
deluge-cloud-sync = "sync_samples_to_cloud:main"
deluge-fix = "fix_references:main"
deluge-verify = "verify_references:main"
deluge-backup = "create_backup:main"       # NEW
deluge-to-sd = "sync_to_sd:main"           # NEW
```

Note: `deluge-fix` and `deluge-verify` are missing from the current `pyproject.toml` (documented in the [codebase review research](scripts-codebase-review-research.md) §4.4). These should be added alongside the new entries.

No new dependencies — `zipfile` is stdlib, and all other needs are covered by existing `lxml` and `python-dotenv` dependencies.

### 12. Prior Research and Plans

**Source:** [docs/scripts-plan.md](docs/scripts-plan.md), [docs/research/scripts-codebase-review-research.md](docs/research/scripts-codebase-review-research.md)

The original scripts plan (`docs/scripts-plan.md`) mentioned both scripts conceptually:
- `sd-to-zip.sh` — "Create a complete zip backup of the SD card for cloud storage"
- `sync_from_sd.py` — Existed as `sd-to-repo.py` in the original naming

The codebase review research (`scripts-codebase-review-research.md`) identified several consolidation items that are relevant context but not blockers for the new scripts:
- `_find_wav_files()` duplication (§1.1) — irrelevant, new scripts use `scan_tree()` directly
- Windows path separator issue in `fix_references.py` (§3.1) — irrelevant, new scripts don't use `fix_references` code
- Missing entry points for `deluge-fix` and `deluge-verify` (§4.4) — should be added alongside new entries

## Approaches Considered

### Zip Backup

| Approach | Pros | Cons | Complexity |
|----------|------|------|------------|
| **A: `zipfile` stdlib + `scan_tree()`** | Zero new dependencies, reuses scanner, cross-platform, filters XML+WAV automatically | None identified | Low |
| **B: `shutil.make_archive()`** | One-liner for basic zip | No file filtering (archives everything), no progress output, no `.trash` exclusion | Low but inadequate |
| **C: Shell script (`zip` command)** | Simple on Linux | Not cross-platform (Windows needs separate `zip.exe`), violates Python-first standard | Low but non-compliant |

**Recommended: Approach A** — Uses proven components, meets all requirements, no new dependencies.

### Sync-to-SD Execution Strategy

| Approach | Pros | Cons | Complexity |
|----------|------|------|------------|
| **A: Extend `execute_plan()` with new trash mode** | Keeps execution in shared module | Over-generalises for single consumer, SD-specific safety logic buried in shared code | Medium |
| **B: Custom execution in script, reuse compute/print** | Safety-critical SD logic fully visible in one file, no shared module changes | Some code duplication with `execute_plan()`'s copy loop | Low-Medium |
| **C: Pre-copy trash then `execute_plan(delete_mode="delete")`** | Reuses delete logic | Two-phase execution adds failure modes (trash succeeds but delete fails = orphaned backups, then re-run deletes without backup) | Medium, fragile |

**Recommended: Approach B** — The SD write path is safety-critical. Having all the logic in one file makes it auditable and avoids coupling the shared module to SD-specific concerns. The copy loop duplication is ~10 lines of `shutil.copy2()` — acceptable for the safety benefit.

## Cross-Cutting Concerns

| Concern | Scripts Affected | Notes |
|---------|-----------------|-------|
| `.env.example` update | Both | Add `ZIP_SOURCE_PATH` and `ZIP_DEST_PATH` |
| `cli_utils.py` update | Both (zip) | Add `get_zip_source_path()` and `get_zip_dest_path()` |
| `pyproject.toml` update | Both | Add `deluge-backup` and `deluge-to-sd` entry points |
| `.trash` directory interaction | `sync_to_sd.py` | Writes to `DELUGE_ROOT/.trash/SD-<timestamp>/`; existing sync-from-SD trash uses plain timestamps |
| Sync log files | `sync_to_sd.py` | Should use separate log file (`data/to_sd_sync.log`) to distinguish from SD→repo logs |
| SD card space | `sync_to_sd.py` | No space check implemented — FAT32 may silently fail on full disk. `OSError` caught by `SyncError` handler |
| Concurrent access | Both | No file locking. If user runs sync-to-SD while Deluge is reading the card, results are undefined. This is a hardware-level concern, not solvable in software |

## Risk Analysis

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Accidental SD card corruption from sync-to-SD | Low | High | Dry-run default, explicit confirmation, SD trash backed to repo before deletion, SyncError on partial failure |
| Zip archive truncation on full dest disk | Low | Medium | `zipfile` raises `OSError` on write failure — catch and report clearly |
| FAT32 mtime comparison false positives causing unnecessary copies | Low | Low | Already handled by `normalise_mtime()` + `_mtime_matches()` in shared modules |
| Windows `PermissionError` on locked files | Medium | Low | Catch in copy/delete loop, wrap in `SyncError` with file context |
| Zip created on Windows has backslash paths | Medium | Medium | Use `PurePosixPath` for all `arcname` values — explicit conversion |
| SD card unmounted mid-sync | Low | High | Each file operation is atomic (copy2/unlink). Partial sync leaves SD in consistent state (some files updated, others original). `SyncError` reports progress |
| User accidentally runs sync-to-SD with wrong `DELUGE_ROOT` | Low | High | Print source and dest paths prominently before confirmation prompt |
| Zip backup from SD card while Deluge is writing | Low | Medium | Document that SD card should be safely ejected from Deluge before running scripts |

## Recommendation

**Both scripts should proceed to planning and implementation.** The existing `deluge_lib/` infrastructure provides strong foundations:

1. **`create_backup.py`** is straightforward — `scan_tree()` + `zipfile` + two new `.env` variables. No shared module changes needed. Low risk, low complexity.

2. **`sync_to_sd.py`** reuses `compute_sync()` and `print_plan()` from `syncing.py` but implements its own execution logic for the safety-critical SD write path. The custom trash strategy (SD deletions → repo `.trash/SD-<timestamp>/`) ensures no SD data is permanently lost without a local backup.

Key design principles:
- **No new dependencies** — both scripts use stdlib and existing packages
- **No `syncing.py` modifications** — custom execution in `sync_to_sd.py` avoids coupling SD-specific safety logic into shared code
- **`cli_utils.py` extension** — two new `get_*()` functions following the established pattern
- **Dry-run default** for sync-to-SD per project standard
- **Cross-platform safe** — `PurePosixPath` for zip paths, `pathlib` throughout, FAT32 tolerance already handled

## Open Questions

1. **Should the zip script support a `--dry-run` flag?**
   - **Impact:** Consistency with other scripts; lets user preview what would be archived
   - **Recommendation:** Yes — print file count and estimated zip size, then exit. Matches the codebase convention where all scripts that modify anything have `--dry-run`.
   - **Blocking:** No

2. **Should `sync_to_sd.py` use `--dry-run` as default (no flag needed) or require `--apply` to execute?**
   - **Impact:** Safety model. `sync_from_sd.py` uses `--dry-run` as an explicit opt-in flag with a confirmation prompt as the default gate. The project standard says "dry-run should be the default behaviour" for SD writes.
   - **Recommendation:** Match `sync_from_sd.py`'s pattern — default mode shows preview + confirmation prompt, `--dry-run` shows preview only (no prompt). This is the established convention and the project standard's "dry-run default" can be interpreted as "don't write without explicit confirmation" which the prompt satisfies.
   - **Blocking:** No

3. **Should `create_backup.py` print progress per-file during archiving?**
   - **Impact:** UX for large archives (~5,500 files). Without progress, the script appears hung.
   - **Recommendation:** Yes — print a counter (`Archiving... 1234/5500`) similar to the sync scripts' copy progress pattern.
   - **Blocking:** No

4. **Should the zip script verify the archive after creation?**
   - **Impact:** Ensures the backup is not corrupted. Adds time but provides confidence.
   - **Recommendation:** Yes — call `ZipFile.testzip()` after creation. This is a single method call that verifies all entries. Fast relative to creation time.
   - **Blocking:** No

5. **Should the zip filename include information about whether the source was the SD card or repo?**
   - **Impact:** Distinguishing backup sources when browsing the archive directory.
   - **Recommendation:** Defer to planning. A simple timestamp is sufficient. The source is recorded in console output and could optionally be added as a zip comment.
   - **Blocking:** No

## References

### Project Files
- [scripts/sync_from_sd.py](scripts/sync_from_sd.py) — Primary analogue for sync-to-SD; manifest handling, compute-then-confirm workflow
- [scripts/sync_samples_to_cloud.py](scripts/sync_samples_to_cloud.py) — Alternative sync pattern; wav-only filter, hard-delete mode, custom log path
- [scripts/list_samples.py](scripts/list_samples.py) — Simple consumer of deluge_sdk
- [scripts/fix_references.py](scripts/fix_references.py) — Hashing, snapshot, migration logic
- [scripts/verify_references.py](scripts/verify_references.py) — Reference checking pattern
- [scripts/deluge_lib/scanning.py](scripts/deluge_lib/scanning.py) — `scan_tree()`, `normalise_key()`, `FileEntry`, `ScanResult`, `FileFilter`
- [scripts/deluge_lib/syncing.py](scripts/deluge_lib/syncing.py) — `compute_sync()`, `execute_plan()`, `print_plan()`, `SyncPlan`, `SyncError`, `SyncResult`, `append_sync_log()`
- [scripts/deluge_lib/cli_utils.py](scripts/deluge_lib/cli_utils.py) — `get_deluge_root()`, `get_sd_card_path()`, `get_cloud_backup_path()`, `confirm_apply()`
- [scripts/pyproject.toml](scripts/pyproject.toml) — Project configuration, entry points, dependencies
- [scripts/.env.example](scripts/.env.example) — Environment variable template
- [scripts/tests/conftest.py](scripts/tests/conftest.py) — Shared `_touch()` test helper
- [scripts/tests/test_sync_from_sd.py](scripts/tests/test_sync_from_sd.py) — Manifest test patterns
- [scripts/tests/test_syncing.py](scripts/tests/test_syncing.py) — Sync primitive test patterns
- [scripts/tests/test_sync_samples_to_cloud.py](scripts/tests/test_sync_samples_to_cloud.py) — End-to-end sync test pattern
- [agent-system/standards/project.md](agent-system/standards/project.md) — SD Card safety rules, platform requirements
- [agent-system/standards/languages/python/core.md](agent-system/standards/languages/python/core.md) — Python conventions, entry points, pathlib
- [temp/new-scripts.md](temp/new-scripts.md) — User requirements for both scripts

### Prior Research and Plans
- [docs/scripts-plan.md](docs/scripts-plan.md) — Original scripts overview (mentions `sd-to-zip.sh` conceptually)
- [docs/research/sample-scripts-research.md](docs/research/sample-scripts-research.md) — XML format analysis, reference patterns
- [docs/research/scripts-codebase-review-research.md](docs/research/scripts-codebase-review-research.md) — Codebase consolidation findings, missing entry points

## Next Steps

1. Review this document and resolve any blocking open questions
2. Invoke the Plan agent to create a feature plan from this research
