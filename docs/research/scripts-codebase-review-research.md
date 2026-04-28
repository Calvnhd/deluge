# Research: Scripts Codebase Review

> **Document Type:** Research
> **Date:** 10 April 2026
> **Request:** Review the scripts codebase for code reuse opportunities, redundancies, and improvements across all scripts and library modules built during three separate implementation phases.
> **Pipeline:** Research → Plan → Implement

## Executive Summary

The scripts codebase is well-structured and broadly consistent, but organic growth across three implementation phases has produced specific redundancies and integration gaps. The most impactful finding is that `fix_references.py` contains its own WAV scanning and hashing logic that operates independently from the shared `scanning.py` module and the sync manifest. Integrating SHA256 hashes into the manifest would eliminate the slowest operation in the fix workflow (hashing ~5,500 files twice). Secondary findings include duplicated test helpers, an inefficient XML discovery path in `deluge_sdk.py`, and 9 Windows path separator failures caused by `str(Path.relative_to())` in `fix_references.py`.

## Objectives

- Identify duplicated logic across all scripts and library modules
- Evaluate whether `_find_wav_files()` and `hash_file()` in `fix_references.py` should move to shared modules
- Assess whether SHA256 hashes in the sync manifest could accelerate the fix_references workflow
- Diagnose the 9 pre-existing test failures on Windows
- Identify simplification opportunities and over-engineering

## Feature Overview

### Purpose and Value

This review enables consolidation of organically-grown code, reducing maintenance surface and improving performance of the most expensive operation (hashing ~5,500 WAV files).

### Scope

**In scope:**
- All files in `scripts/`, `scripts/deluge_lib/`, `scripts/tests/`
- `scripts/pyproject.toml`, `scripts/.env.example`, `scripts/data/manifest.json`

**Out of scope:**
- Deluge XML format changes, new script features, SD card sync workflow changes

## Existing Assets Analysis

| Capability | Status | Location | Notes |
|---|---|---|---|
| WAV file scanning | ⚠️ Duplicated | `fix_references.py:_find_wav_files()`, `scanning.py:scan_tree(file_filter="wav")` | Two independent implementations |
| SHA256 file hashing | ⚠️ Isolated | `fix_references.py:hash_file()` | Not shared; could benefit manifest |
| XML file discovery | ⚠️ Inefficient | `deluge_sdk.py:find_all_xml_files()` calls `scan_tree()` without filter | Scans for WAV+XML then post-filters |
| Test `_touch()` helper | ⚠️ Duplicated | 4 test files define their own copy | 3 identical, 1 simpler variant |
| Sync manifest | ✅ Ready | `scripts/data/manifest.json` | Tracks `{size, mtime}` per file |
| Shared sync primitives | ✅ Ready | `deluge_lib/syncing.py` | Clean extraction from sync_from_sd |
| Shared scanner | ✅ Ready | `deluge_lib/scanning.py` | Generic, well-tested |
| CLI utilities | ✅ Ready | `deluge_lib/cli_utils.py` | Clean, minimal |
| Deluge SDK | ✅ Ready | `deluge_lib/deluge_sdk.py` | Comprehensive XML handling |

## Findings

### 1. Code Reuse Opportunities

#### 1.1 `_find_wav_files()` vs `scan_tree(file_filter="wav")`

**Location:** [`scripts/fix_references.py`](scripts/fix_references.py#L46-L53) vs [`scripts/deluge_lib/scanning.py`](scripts/deluge_lib/scanning.py#L62-L96)

**What:** `fix_references.py` defines its own `_find_wav_files()` that recursively finds `.wav/.WAV` files using `Path.rglob("*")`. Meanwhile, `scanning.py` provides `scan_tree(file_filter="wav")` that does the same thing using `os.walk()` with additional features (stat capture, `.trash` exclusion, case-normalised keys).

**Comparison:**

| Feature | `_find_wav_files()` | `scan_tree(file_filter="wav")` |
|---|---|---|
| Finds WAV files recursively | ✅ | ✅ |
| Case-insensitive extension | ✅ (`.suffix.upper()`) | ✅ (`.lower()`) |
| Skips `.trash` dirs | ❌ | ✅ |
| Captures stat info | ❌ | ✅ (size, mtime) |
| Returns | `list[Path]` (absolute) | `ScanResult` (normalised keys → `FileEntry`) |
| Console output | None | Progress indicator |

**Verdict:** These are genuinely redundant. `_find_wav_files()` is a simpler variant that pre-dates `scan_tree()`. The key difference is the return type — fix_references needs a list of absolute paths to iterate and hash, while scan_tree returns a richer structure.

**Recommendation:** Replace `_find_wav_files(samples_dir)` with a thin wrapper around `scan_tree()`. Something like:

```python
def _find_wav_files(samples_dir: Path) -> list[Path]:
    scan = scan_tree(samples_dir, label="samples", file_filter="wav")
    return sorted(samples_dir / entry.rel_path for entry in scan.files.values())
```

This gains `.trash` exclusion for free and keeps the simple `list[Path]` interface. The stat data from scan_tree is discarded here but could become useful if hash caching is added (see §2).

**Trade-offs:** Adds a dependency on `scanning.py` from `fix_references.py`. The progress indicator from `scan_tree` will print during snapshot/fix, which is actually desirable for a long-running operation.

#### 1.2 `hash_file()` — Should It Move to a Shared Location?

**Location:** [`scripts/fix_references.py`](scripts/fix_references.py#L24-L36)

**What:** `hash_file()` is a 6-line chunked SHA256 hasher. Currently only used by `fix_references.py` (in `snapshot()` and `compute_migration_map()`).

**History:** Decision D15 in the [sample-scripts plan](docs/plans/sample-scripts-plan.md) explicitly moved `hash_file` into `fix_references.py` to avoid blocking the fixer on a non-essential utility module. At the time, no other consumer existed.

**Current situation:** If SHA256 hashes are added to the sync manifest (see §2 below), then `sync_from_sd.py` would also need `hash_file()`. That would make it a shared function.

**Recommendation:** Move `hash_file()` to `deluge_lib/` only if/when a second consumer exists (i.e., when manifest hashing is implemented). Until then, it's fine where it is. Moving it prematurely adds a module (or forces it into an existing module where it doesn't quite fit).

**If moved, where?** A new `deluge_lib/hashing.py` is the cleanest home. It doesn't belong in `scanning.py` (scanning is about directory walking, not content analysis) or `deluge_sdk.py` (which is about XML). The `_HASH_CHUNK_SIZE` constant would move with it.

#### 1.3 `find_all_xml_files()` vs `scan_tree(file_filter="xml")`

**Location:** [`scripts/deluge_lib/deluge_sdk.py`](scripts/deluge_lib/deluge_sdk.py#L46-L56)

**What:** `find_all_xml_files()` already calls `scan_tree()` internally, but does so **without** `file_filter="xml"`:

```python
def find_all_xml_files(deluge_root: Path) -> list[Path]:
    results: list[Path] = []
    for subdir in _DELUGE_SUBDIRS:
        d = deluge_root / subdir
        if not d.is_dir():
            continue
        scan = scan_tree(d)  # <-- scans for BOTH wav and xml
        for entry in scan.files.values():
            if entry.rel_path.suffix.upper() == ".XML":
                results.append(d / entry.rel_path)
    return sorted(results)
```

This scans for WAV files too, then filters them out in Python. On a real SD card with ~5,500 WAV files across KITS/SYNTHS/SONGS (unlikely, since WAVs are in SAMPLES/, but still) this is wasteful. More practically, it prints misleading "Skipping ... (unsupported extension)" messages for any non-XML/non-WAV files in those directories, and it prints progress messages for each subdirectory scan.

**Recommendation:** Pass `file_filter="xml"` to `scan_tree()`:

```python
scan = scan_tree(d, file_filter="xml")
```

This eliminates the post-filter and the redundant scan of WAV files. The manual `.suffix.upper() == ".XML"` check can also be removed since `scan_tree` already handles case-insensitive extension matching.

**Trade-offs:** Minimal — this is a strict improvement.

#### 1.4 Duplicated `_touch()` Test Helper

**Location:** Four separate definitions across test files:

| File | Signature | Has `mtime` param |
|---|---|---|
| [`test_scanning.py`](scripts/tests/test_scanning.py#L10) | `_touch(path, content=b"x")` | ❌ |
| [`test_syncing.py`](scripts/tests/test_syncing.py#L23) | `_touch(path, content=b"x", mtime=None)` | ✅ |
| [`test_sync_from_sd.py`](scripts/tests/test_sync_from_sd.py#L21) | `_touch(path, content=b"x", mtime=None)` | ✅ |
| [`test_sync_samples_to_cloud.py`](scripts/tests/test_sync_samples_to_cloud.py#L13) | `_touch(path, content=b"x", mtime=None)` | ✅ |

The three with `mtime` are identical (create file, set mtime via `os.utime`). The scanning variant is a simpler subset.

**Recommendation:** Move the full-featured `_touch()` to `tests/conftest.py` (currently empty). All four test files import from there. The simpler variant in `test_scanning.py` can use the shared one (the `mtime` parameter defaults to `None` so existing calls work unchanged).

**Trade-offs:** Very minor — adds a shared fixture but reduces 24 lines of duplication to 1 import per file. `conftest.py` already exists and is empty.

---

### 2. Manifest + Hash Integration

#### 2.1 Current State

The sync manifest at [`scripts/data/manifest.json`](scripts/data/manifest.json) tracks `{size, mtime}` per file using normalised lowercase forward-slash keys. It is written by `sync_from_sd.py` after each successful sync.

The `fix_references.py` workflow hashes **all** ~5,500 WAV files from scratch:
- `snapshot` subcommand: hashes all WAVs → writes to `docs/manifests/snapshot-<date>.json`
- `fix` subcommand: loads the before-snapshot, then hashes all current WAVs again to build the "after" state

Each full hash pass reads ~5,500 files. On a typical disk this takes seconds to low minutes, but it scales with sample library size and is pure I/O.

#### 2.2 Opportunity: Add SHA256 to the Manifest

If the sync manifest included SHA256 hashes, `fix_references.py` could:
1. Read hashes from the manifest for unchanged files (same size+mtime)
2. Only hash files that are new or have changed size/mtime
3. Skip the vast majority of hashing on both snapshot and fix runs

**Which script writes hashes?** `sync_from_sd.py` already writes the manifest after sync. It would compute SHA256 for each copied file (new or updated) and preserve existing hashes for unchanged files. The incremental cost per sync is low — only newly-copied files need hashing, and they were just read for copying anyway.

**Which scripts read hashes?** `fix_references.py` for snapshot and fix operations. It reads manifest hashes for files that haven't changed, only hashing files not in the manifest or with different size/mtime.

**First run / no manifest:** Falls back to hashing everything (current behaviour). No manifest = no cached hashes.

**Backward compatibility:** The manifest format adds a `"sha256"` field to each `FileRecord`:
```json
{
  "size": 56789,
  "mtime": 1712600100.0,
  "sha256": "a1b2c3..."
}
```
`_read_manifest()` already tolerates extra fields. Entries without `"sha256"` are treated as "hash unknown" — same as a new file. Old manifests work without modification.

#### 2.3 Manifest Key Mismatch Issue

There is a subtle issue: the manifest uses `normalise_key()` (lowercase, forward slashes) while `fix_references.py` uses `str(Path.relative_to())` which on Windows produces backslash paths. Any integration would need to normalise consistently. This is already the root cause of the 9 test failures (see §3.1).

**Recommendation:** This is a worthwhile improvement but has meaningful complexity. It should be a separate planned feature, not a quick refactor. The implementation involves:
1. Add `sha256` field to `FileRecord` in `sync_from_sd.py`
2. Move `hash_file()` to `deluge_lib/hashing.py` (now has two consumers)
3. Compute hashes of copied files during sync, preserve for unchanged
4. Modify `fix_references.py` to optionally read manifest hashes
5. Ensure consistent key normalisation (forward slashes everywhere)

**Trade-offs:**
- Pro: Dramatically faster snapshot/fix for incremental changes
- Pro: Enables future features (content-based dedup detection in sync)
- Con: Adds coupling between sync_from_sd and fix_references via shared manifest
- Con: Hashing during sync makes sync slightly slower (computing SHA256 for each copied file)
- Con: Not all WAVs transit through sync — manually-added files won't have hashes

---

### 3. Test Issues

#### 3.1 The 9 Failing Tests on Windows — Path Separator Issue

**Root cause:** [`fix_references.py`](scripts/fix_references.py#L74) lines 74 and 153 use `str(wav_path.relative_to(deluge_root))` to build relative paths for the snapshot and migration map. On Windows, `Path.relative_to()` returns a `WindowsPath`, and `str()` uses backslashes: `SAMPLES\kick.wav` instead of `SAMPLES/kick.wav`.

The before-snapshot stores paths from the Deluge (which uses forward slashes in XML references). When `compute_migration_map()` builds the "after" state with backslash paths, they never match the forward-slash paths in the before-snapshot, so **every file appears as simultaneously deleted and added** rather than matched.

**Affected lines:**
- [`fix_references.py`](scripts/fix_references.py#L74) line 74: `rel_path = str(wav_path.relative_to(deluge_root))` in `snapshot()`
- [`fix_references.py`](scripts/fix_references.py#L153) line 153: same pattern in `compute_migration_map()`

**The 9 failing tests** are in `TestComputeMigrationMap` and `TestSnapshot` — any test that asserts paths contain forward slashes after being produced by these lines.

**Fix:** Use `PurePosixPath` conversion or the existing `normalise_key()` from `scanning.py`:

```python
# Option A: Direct PurePosixPath (no new dependency)
rel_path = str(PurePosixPath(wav_path.relative_to(deluge_root)))

# Option B: Use existing normalise_key (but this lowercases, which may not be desired)
```

Option A is better because `normalise_key()` lowercases paths, which would lose the case-preserving behaviour that fix_references needs (Deluge paths are case-sensitive). A dedicated `to_posix_path()` helper that converts without lowercasing would be the cleanest solution.

**Severity:** Low — only affects Windows. The core logic is correct; it's just a path formatting issue. Estimated fix: change 2 lines in `fix_references.py`.

#### 3.2 Test Helper Duplication (covered in §1.4)

See §1.4 above. Not a test failure, but unnecessary maintenance burden.

---

### 4. Simplification Opportunities

#### 4.1 `find_all_xml_files()` Calls `scan_tree()` Three Times

**Location:** [`deluge_sdk.py`](scripts/deluge_lib/deluge_sdk.py#L46-L56)

`find_all_xml_files()` loops over `_DELUGE_SUBDIRS` (KITS, SYNTHS, SONGS) and calls `scan_tree()` separately for each. This means three separate `os.walk()` operations, three progress prints, and three `ScanResult` objects. The function could call `scan_tree()` once on `deluge_root` with `file_filter="xml"` and filter by subdirectory from the results.

However, scanning from `deluge_root` would also scan `SAMPLES/` (which has no XML files but has ~5,500 WAV files that would all be "skipped"). So the per-subdirectory approach is actually correct — it avoids scanning the large SAMPLES tree.

**Recommendation:** Keep the per-subdirectory scan, but add `file_filter="xml"` as noted in §1.3. The three separate scans are the right trade-off for avoiding the SAMPLES tree traversal. The three progress prints ("Scanning source...") are slightly noisy for a read-only SDK function, but not worth adding complexity to suppress.

#### 4.2 `scanning.py` Prints "Skipping" Warnings for Non-Target Files

**Location:** [`scanning.py`](scripts/deluge_lib/scanning.py#L101-L103)

When `scan_tree()` encounters a file with an extension not in the filter set, it prints a "Skipping" message:

```python
if ext not in allowed:
    rel = file_path.relative_to(root)
    print(f"\n  Skipping {rel} (unsupported extension)", flush=True)
    continue
```

This is noisy in practice. When `find_all_xml_files()` calls `scan_tree()` without `file_filter="xml"`, every non-XML/non-WAV file triggers a warning. Even with the filter fix from §1.3, any non-XML file in KITS/SYNTHS/SONGS (e.g. `.DS_Store`, `.gitkeep`) will produce a warning.

**Recommendation:** Remove the print statement. Silently skipping non-matching extensions is the expected behaviour of a filter. If callers want to know about skipped files, they can compare the count against a raw directory listing. The current message adds noise without actionable value.

#### 4.3 `deluge_sdk.py` `find_all_xml_files()` — Redundant Post-Filter

As noted in §1.3, the function calls `scan_tree()` without `file_filter` then manually checks `.suffix.upper() == ".XML"`. After adding `file_filter="xml"`, the manual suffix check becomes redundant and can be removed entirely. All entries in the scan result are guaranteed to be XML files.

#### 4.4 pyproject.toml — Missing Entry Points for fix_references and verify_references

**Location:** [`scripts/pyproject.toml`](scripts/pyproject.toml#L11-L12)

Currently only two scripts have entry points:
```toml
[project.scripts]
deluge-sync = "sync_from_sd:main"
deluge-cloud-sync = "sync_samples_to_cloud:main"
```

`fix_references.py` and `verify_references.py` are not registered. They work fine via `uv run python fix_references.py` but can't be invoked as `deluge-fix` or `deluge-verify`.

**Recommendation:** Add entry points:
```toml
deluge-fix = "fix_references:main"
deluge-verify = "verify_references:main"
```

**Trade-offs:** Minimal. These are convenience aliases only.

---

### 5. Other Observations

#### 5.1 Consistent Use of `pathlib` Throughout

The codebase consistently uses `pathlib.Path` for all file operations, which is good for cross-platform portability. The one exception is `os.walk()` in `scanning.py`, which is the correct choice there — `pathlib` has no equivalent for efficient tree walking.

#### 5.2 `scanning.py` `normalise_mtime()` vs `_mtime_matches()` in `syncing.py`

These serve complementary purposes and are not redundant:
- `normalise_mtime()` in `scanning.py` truncates to FAT32's 2-second grid at scan time
- `_mtime_matches()` in `syncing.py` compares two (already-normalised) timestamps with ±2s tolerance

The normalisation happens at scan, the tolerance at comparison. This is correct — there's no duplication.

#### 5.3 `deluge_sdk.py` Depends on `scanning.py`

`find_all_xml_files()` imports `scan_tree` from `scanning.py`. This creates a dependency from the XML SDK to the file scanning module. This is fine — it's a legitimate reuse of the scanner — but it means `deluge_sdk.py` is not a standalone XML parsing library. Any future extraction of the SDK into a separate package would need to carry `scanning.py` along.

This is not a problem to solve now. Noting for awareness.

#### 5.4 Plan Mentions `lib/` but Code Uses `deluge_lib/`

The [sample-scripts plan](docs/plans/sample-scripts-plan.md) references `scripts/lib/` throughout, but the actual implementation uses `scripts/deluge_lib/`. This happened during implementation (probably because `lib` is too generic or conflicts with something). The plan is now historical and doesn't need updating, but this is worth noting for anyone reading the plan alongside the code.

#### 5.5 Empty `conftest.py` and `__init__.py`

Both `scripts/tests/conftest.py` and `scripts/tests/__init__.py` are empty. The `__init__.py` exists to make the tests directory a package. `conftest.py` exists but is unused — it was created as scaffolding in Phase 1 with the note "empty initially". This is the natural home for the shared `_touch()` helper (see §1.4).

---

## Approaches Considered

### For Code Consolidation

| Approach | Pros | Cons | Complexity |
|---|---|---|---|
| **A: Minimal refactor** — fix `file_filter`, move `_touch`, fix Windows paths | Least risk, immediate value, fixes real bugs | Doesn't address hash integration | Low |
| **B: Full consolidation** — all of A plus move `hash_file` and replace `_find_wav_files` | Reduces all identified duplication | Requires more testing, `hash_file` move may be premature | Medium |
| **C: Full consolidation + manifest hashing** — all of B plus SHA256 in manifest | Maximum long-term value | Significant scope, touches sync workflow | High |

### For Manifest Hash Integration

| Approach | Pros | Cons | Complexity |
|---|---|---|---|
| **A: Hash during sync only** — sync_from_sd computes SHA256 for copied files | Incremental, backward-compatible | Manually-added files have no hash, sync becomes slower | Medium |
| **B: Separate hash command** — new `deluge-hash` command that hashes all files and updates manifest | Explicit, user-controlled | Another command to remember, manifest format still changes | Medium |
| **C: Lazy hashing in fix_references** — read manifest hashes when available, hash on miss | Transparent to user, backward-compatible | fix_references gains manifest dependency | Low-Medium |

**Recommended:** Approach C for manifest hashing if pursued — it's the most transparent and backward-compatible.

## Cross-Cutting Concerns

| Concern | Impact | Notes |
|---|---|---|
| Windows path separators | `fix_references.py` snapshot/fix | Root cause of 9 test failures; also a real bug if snapshots are created on Windows |
| Manifest format stability | `sync_from_sd.py`, `fix_references.py` | Adding SHA256 changes the format; backward compatibility is handled by ignoring unknown fields |
| Scanner import in SDK | `deluge_sdk.py` → `scanning.py` | Existing dependency; consolidation deepens it slightly |
| Test isolation | All test files | Shared `_touch()` in conftest is standard pytest practice; no test coupling concerns |

## Recommendations

Prioritised by impact (simplicity × value):

### Priority 1: Fix Windows Path Separators (Bug Fix)

**Files:** `fix_references.py` lines 74, 153
**Effort:** ~2 lines changed
**Impact:** Fixes 9 test failures, fixes a real bug where Windows-created snapshots produce backslash paths that don't match XML references

### Priority 2: Add `file_filter="xml"` to `find_all_xml_files()`

**Files:** `deluge_sdk.py` line 52
**Effort:** ~3 lines changed (add filter, remove manual suffix check)
**Impact:** Eliminates redundant WAV scanning during XML discovery, removes noisy "Skipping" output

### Priority 3: Remove "Skipping" Print from `scan_tree()`

**Files:** `scanning.py` lines 101-103
**Effort:** ~3 lines removed
**Impact:** Eliminates noisy console output for non-matching files

### Priority 4: Move `_touch()` to `conftest.py`

**Files:** `tests/conftest.py`, 4 test files
**Effort:** ~20 lines moved, 4 imports added
**Impact:** Eliminates test helper duplication

### Priority 5: Replace `_find_wav_files()` with `scan_tree()` Wrapper

**Files:** `fix_references.py`
**Effort:** ~10 lines changed
**Impact:** Eliminates WAV scanning duplication, gains `.trash` exclusion

### Priority 6: Add Entry Points for fix_references and verify_references

**Files:** `pyproject.toml`
**Effort:** 2 lines added
**Impact:** Convenience — enables `deluge-fix` and `deluge-verify` commands

### Deferred: Manifest Hash Integration

**Effort:** Medium feature (new module, manifest format change, two scripts modified)
**Impact:** Significant performance improvement for large sample libraries
**Recommendation:** Plan as a separate feature if/when snapshot/fix performance becomes a pain point. The current full-hash approach works correctly and is fast enough for the current ~5,500 file library.

## Open Questions

| # | Question | Context | Suggested Resolution |
|---|---|---|---|
| 1 | Should `hash_file()` move now or wait for a second consumer? | Currently only used by `fix_references.py`. Manifest integration would add a second consumer. | Wait. Move when manifest hashing is implemented. |
| 2 | Should the `find_all_xml_files()` progress output be suppressed? | `scan_tree()` prints "Scanning source... N files found" three times (once per subdirectory). | Accept for now — it provides useful feedback during XML operations on real data. |
| 3 | Should the plan doc be updated to reflect `lib/` → `deluge_lib/` rename? | Plans are point-in-time documents. | No — the plan is historical. Note the difference here for awareness. |
