# Codebase Review — 2026-04-28

Comprehensive review of the `scripts/` directory and supporting infrastructure after recent multi-branch merges.

---

## Executive Summary

The codebase is in **good shape overall**. The library architecture (`deluge_lib/`) is well-factored, the test suite is substantial (~300 tests), and the README accurately reflects the current state. The major scripts are all functional and documented. There are a handful of real bugs, some stale markers, and a few areas with missing test coverage.

**Severity Breakdown:**
- 🔴 **Bugs**: 2
- 🟡 **Inconsistencies/Issues**: 7
- 🟢 **Observations/Suggestions**: 8

---

## 🔴 Bugs

### B1. `extract_kit()` return type annotation is wrong

**File:** `deluge_lib/extraction.py` line ~964  
**Issue:** The function signature says `-> etree._Element` but it actually returns `tuple[etree._Element, list[str]]` (element + warnings list). The docstring correctly documents the tuple return, but the type hint is wrong.  
**Impact:** mypy strict mode would flag every call site that unpacks the tuple. All callers do correctly unpack (`element, warnings = extract_kit(...)`) so it doesn't cause runtime errors, but it's technically a type error.  
**Fix:** Change `-> etree._Element` to `-> tuple[etree._Element, list[str]]`.

### B2. `update_sample_refs()` uses naive string replacement

**File:** `fix_references.py` lines 208–224  
**Issue:** `data.replace(old_path, new_path)` does unbounded string replacement across the entire XML text. If an old path is a substring of another path (e.g. `SAMPLES/DRUMS/Kick.wav` appearing inside `SAMPLES/DRUMS/Kick.wav-backup`), the replacement could corrupt unintended locations. More concretely, if a sample path like `SAMPLES/foo/bar.wav` happens to appear in a comment, attribute name, or other non-reference context, it would be incorrectly replaced.  
**Impact:** Low probability in practice (Deluge XML structure is simple), but the approach is fragile. The `count` variable also counts occurrences before replacement, not after — if `old_path` appears inside `new_path`, a single replacement could shift subsequent counts.  
**Fix:** Use lxml to do targeted attribute/element replacement instead of raw text replacement, or at minimum constrain replacements to known XML contexts (quoted attribute values and element text).

---

## 🟡 Inconsistencies and Issues

### I1. `_strip_automation` is a private function used as public API

**File:** `deluge_lib/extraction.py` line 1116  
**Issue:** The function has a leading underscore (private convention) but is imported and called by `extract_instruments.py`, `dedup_threshold_test.py`, and tests. It's part of the extraction pipeline's public interface.  
**Fix:** Rename to `strip_automation` (no leading underscore).

### I2. Three files still marked "WORK IN PROGRESS"

**Files:**  
- `extract_instruments.py` (line 1)
- `sync_to_sd.py` (line 1)
- `deluge_lib/extraction.py` (line 1)

**Issue:** `extract_instruments.py` and `extraction.py` are mature — fully implemented with ~110 tests, cross-song dedup, extended mode, sidechain detection, etc. The WIP label is misleading. `sync_to_sd.py` is marked 🚧 in the README and is genuinely less mature, but it is also fully functional with 15 tests.  
**Fix:** Remove WIP markers from `extract_instruments.py` and `extraction.py`. Consider whether `sync_to_sd.py` is still WIP or can graduate.

### I3. 9 skipped tests in `test_extraction.py`

**File:** `tests/test_extraction.py`  
**Issue:** Three test classes have all their tests skipped with `pytest.skip("Not implemented")`:
- `TestDiscoverSongs` (4 tests) — discovery is complex and tested indirectly, but direct unit tests would be valuable
- `TestFirmwareValidation` (2 tests)
- `TestArpeggiatorHandling` (3 tests)

**Impact:** These represent gaps in the test suite for real functionality. The code they should test is already implemented.

### I4. `sample_overview.py` has zero test coverage

**File:** `sample_overview.py` (~620 lines)  
**Issue:** No `test_sample_overview.py` exists. This is the largest script without any tests. It has complex display formatting logic (`cmd_usage`, `cmd_unused`, `cmd_missing`, `cmd_duplicates`) that could break silently.  
**Impact:** The underlying `analysis.py` module IS well-tested (23 tests), so the core logic is covered. But the CLI entry point, subcommand routing, snapshot-based duplicates, and display formatting are untested.

### I5. `extract_instruments.py` CLI entry point untested

**File:** `extract_instruments.py`  
**Issue:** The `main()` function is ~250 lines with complex branching (extended mode, dedup, SD-direct, naming modes, sidechain filtering, trash backup). The library functions it calls are thoroughly tested, but the orchestration layer is not.  
**Impact:** Integration bugs in argument handling or execution flow would not be caught.

### I6. `docs/scripts-plan.md` references scripts that don't exist

**File:** `docs/scripts-plan.md`  
**Issue:** References to `sync-samples.sh`, `sd-to-zip.sh`, `verify_references.py`, `create-manifest.py`, and `rename_songs.py` — none of these exist. Their functionality has been absorbed into the current scripts:
- `sync-samples.sh` → `sync_samples_to_cloud.py` (Python, not bash)
- `sd-to-zip.sh` → `create_backup.py`
- `verify_references.py` → `sample_overview.py missing`
- `create-manifest.py` → `sample_overview.py` (partially)
- `rename_songs.py` → never implemented

The document has a header note ("written before implementation") but could confuse anyone reading it.

### I7. `cli_utils.py` calls `load_dotenv()` on every path getter

**File:** `deluge_lib/cli_utils.py`  
**Issue:** Each of the 5 `get_*()` functions calls `load_dotenv(_SCRIPTS_DIR / ".env")` independently. If a script calls multiple getters (which they all do), dotenv is loaded 2-3 times redundantly. This isn't a bug (dotenv is idempotent) but it's unnecessary work and makes the code harder to reason about.  
**Fix:** Load dotenv once at module level or in a single `load_config()` function.

---

## 🟢 Observations and Suggestions

### O1. `SONG-KITS-ex/` and `SONG-SYNTHS-ex/` directories exist but aren't referenced in code

The `DELUGE/KITS/SONG-KITS-ex/` and `DELUGE/SYNTHS/SONG-SYNTHS-ex/` directories contain extended-mode extraction outputs (filenames with section colour abbreviations like `-Lbl`, `-Pnk`, `-Gld`). The code writes to `SONG-KITS/` and `SONG-SYNTHS/` — the `-ex` directories appear to be previous extraction outputs that were manually preserved. They contain manifest.json files and are in git, so they're legitimate data, but there's no script logic that references or manages them.

### O2. `dedup_threshold_test.py` is a useful development tool but could use a `--help` improvement

The script's `--percent` and `--count` args take 3 positional values (lower, upper, step) which is unusual. The current help text explains it, but the UX could be improved with named arguments or defaults shown more clearly.

### O3. Architecture is clean and well-layered

The separation is excellent:
- `deluge_lib/scanning.py` — generic file scanning (no Deluge knowledge)
- `deluge_lib/syncing.py` — generic sync logic
- `deluge_lib/deluge_sdk.py` — Deluge-specific XML knowledge
- `deluge_lib/analysis.py` — pure analysis on pre-collected data
- `deluge_lib/extraction.py` — extraction transformation logic
- Top-level scripts — CLI orchestration only

This makes the code very testable and each module has a clear single responsibility.

### O4. FAT32 handling is thorough

The `normalise_mtime()` function in `scanning.py`, the `_MTIME_TOLERANCE_S` in `syncing.py`, and the `_ZIP_MIN_EPOCH` clamping in `create_backup.py` all show careful attention to FAT32 filesystem quirks. This is important for cross-platform SD card work.

### O5. `deluge_sdk.py` comment notes a potential optimisation

Line ~155: `"Not optimal to use scan_tree because we throw away so much of the result / Consider writing something bespoke"` — in `find_all_xml_files()`. This is a valid observation but unlikely to matter in practice given the small number of XML files on a Deluge SD card.

### O6. `sync_from_sd.py` manifest is more sophisticated than `sync_to_sd.py`

`sync_from_sd.py` maintains a `scripts/data/manifest.json` for smart change detection (avoiding re-scanning the SD card). `sync_to_sd.py` does not use a manifest — it rescans both trees every time. This asymmetry is reasonable since SD→repo happens more often, but it means `sync_to_sd.py` may be slower for large libraries.

### O7. The `--sd-direct` flag in `extract_instruments.py` has good safety

Double confirmation (`confirm_apply` + explicit "yes" input), SD backup to local `.trash/` before deletion, and clear warning output. This is well-designed for a destructive operation on hardware.

### O8. `Arp2-Bingbong.XML` appears in `SONG-SYNTHS/` but not in `SONG-SYNTHS-ex/`

This is expected — default mode extracts one version per instrument, extended mode may produce different results. But it's worth noting that the two output directories are not subsets/supersets of each other, so they represent independent extraction runs with different configs.

---

## Test Suite Health

| Area | Tests | Coverage |
|------|-------|----------|
| `deluge_lib/analysis.py` | 23 | ✅ Good |
| `deluge_lib/cli_utils.py` | 6 | ✅ Good |
| `deluge_lib/deluge_sdk.py` | 43 | ✅ Thorough |
| `deluge_lib/extraction.py` | ~110 | ✅ Very thorough (9 skipped) |
| `deluge_lib/scanning.py` | 14 | ✅ Good |
| `deluge_lib/syncing.py` | 22 | ✅ Good |
| `create_backup.py` | 7 | ✅ Good |
| `create_snapshot.py` | 11 | ✅ Good |
| `fix_references.py` | ~30 | ✅ Thorough |
| `sync_from_sd.py` | 11 | ⚠️ Moderate (no `main()` test) |
| `sync_to_sd.py` | 15 | ✅ Thorough |
| `sync_samples_to_cloud.py` | 8 | ✅ Good |
| `sample_overview.py` | 0 | ❌ None |
| `extract_instruments.py` | 0 | ❌ CLI untested |
| `dedup_threshold_test.py` | 0 | ❌ None (utility) |

**Total:** ~300 tests across 12 test files, 7 test fixtures.

---

## README vs Code Alignment

The README is **accurate and well-maintained**. All scripts listed exist. All CLI flags documented work. The status indicators (✅/🚧) are correct — only `sync_to_sd.py` is marked incomplete.

One minor issue: the Phase 3 "Update" table in the README starts numbering at step 2 (skipping step 1), likely from a previous edit.

---

## Planned but Unimplemented Features

From `docs/scripts-plan.md`, these planned scripts were never built:
- `rename_songs.py` — auto-rename songs after deleting old versions
- `create-manifest.py` — human-readable markdown/CSV manifests

These could still be useful but are not referenced anywhere in the current codebase.

---

## Summary of Recommended Actions

**Priority 1 (Fix):**
1. Fix `extract_kit()` return type annotation → `tuple[etree._Element, list[str]]`
2. Rename `_strip_automation()` → `strip_automation()`

**Priority 2 (Clean up):**
3. Remove "WORK IN PROGRESS" from `extract_instruments.py` and `extraction.py`
4. Implement the 9 skipped tests in `test_extraction.py`
5. Phase 3 table numbering fix in README

**Priority 3 (Improve):**
6. Add test coverage for `sample_overview.py`
7. Add integration tests for `extract_instruments.py` CLI
8. Consider whether `docs/scripts-plan.md` should be archived or updated
9. Investigate safer XML-aware replacement in `update_sample_refs()`
