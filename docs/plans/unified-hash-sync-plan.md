# Plan: Unified Hash-Based Sync and Reference-Fixing System

> **Document Type:** Plan
> **Date:** 15 May 2026
> **Research:** [unified-hash-sync-research.md](../research/unified-hash-sync-research.md)
> **Pipeline:** Research → **Plan** → Implement
> **Status:** Draft

## Executive Summary

This plan refactors the sync and reference-fixing infrastructure to use SHA-256 content hashing as the definitive change-detection mechanism, replacing the current mtime-only comparison that produces hundreds of false positives after git branch switches, extraction scripts, and local file reorganisation. The manifest gains a `hash` field per entry with a stat-based fast-path cache (git's proven approach) to avoid re-hashing unchanged files. The separate snapshot system is eliminated entirely — `fix_references` reads hash→path data directly from the manifest with graceful degradation when data is stale or missing.

The work is structured in four phases: (1) manifest schema v2 with transparent v1 migration, (2) hash-aware sync with stat-cache fast-path, (3) manifest-based reference fixing, and (4) snapshot system cleanup.

## Research Summary

The research document ([unified-hash-sync-research.md](../research/unified-hash-sync-research.md)) identified the following key findings:

- **mtime false positives are the primary pain point.** The dual-stat manifest solved null-timestamp and `shutil.copy2` issues but remains vulnerable to mtime drift from git checkout (~hundreds of files), extraction scripts, and local reorganisation. Content hashing eliminates this entire class of problems.
- **SHA-256 is the recommended algorithm.** Already in the codebase (`hash_file()` in `deluge_sdk.py`), no new dependency needed. Performance difference vs xxHash is marginal in practice (I/O-bound on SSD, irrelevant on incremental runs).
- **Git-style stat cache is the right incremental strategy.** If current stat (size + mtime) matches the manifest entry, trust the cached hash without re-reading the file. Re-hash only on stat-cache miss. Files with null/invalid mtimes (mtime ≤ 0) always re-hash.
- **The snapshot system can be fully eliminated.** The manifest serves as the "before" state for reference fixing. `fix_references` degrades gracefully when the manifest is stale or missing — broken references are flagged as unresolvable rather than silently corrupted.
- **Cloud sync is unaffected.** `sync_samples_to_cloud.py` uses the `manifest=None` path and operates NTFS→NTFS where stats are reliable.
- **First-run cost is ~60–120 seconds** (SSD, ~7500 files), with subsequent incremental runs completing in under a second.

Existing assets to leverage:
- `hash_file()` in `deluge_sdk.py` — SHA-256 with 64KB chunks, ready to use
- `read_manifest()` / `write_manifest()` in `syncing.py` — atomic writes, extensible
- `FileRecord` TypedDict in `syncing.py` — gains the `hash` field
- `compute_sync()` in `syncing.py` — gains hash-comparison branch
- `classify_ref_changes()` and `update_sample_refs()` in `fix_references.py` — no changes needed

## Decisions Log

| ID | Decision | Rationale | Alternatives Considered |
|----|----------|-----------|------------------------|
| D1 | Use SHA-256 for content hashing | Already in codebase (`hash_file()`), no new dependency, negligible collision risk, stdlib `hashlib` | xxHash (faster CPU, but new dependency and I/O-bound in practice) |
| D2 | Stat cache fast-path: trust cached hash when `(size, mtime)` match and `mtime > 0` | Git's proven approach; keeps incremental runs at O(1) per file. Null-mtime files (Deluge firmware bug, ~287 files) always re-hash since their stats are unreliable | Hash-only (no stat cache) — unacceptable: 60–120s every sync |
| D3 | Manifest v2 format: add `version` and `hash` fields to existing structure | Transparent migration from v1; backward-compatible; single atomic change to the schema | Separate hash manifest file — complicates I/O, two files to keep in sync |
| D4 | `hash` field is nullable — `null` means "not yet computed" | Enables transparent v1→v2 migration without requiring immediate full re-hash; hash populated on next stat-cache miss | Require hash on all entries — blocks migration until full hash computed |
| D5 | `fix_references` uses manifest as primary data source with graceful degradation | Eliminates snapshot system, removes ordering constraints, and the lookup chain handles stale/missing manifest naturally | Keep snapshots alongside manifest — complexity for no benefit |
| D6 | `fix_references` updates manifest keys after apply (key rename, no re-hash) | Keeps manifest current for subsequent operations; enables multi-round reorganisation; O(n) in moved files, no I/O | Don't update manifest — next sync self-heals, but multi-round reorg would accumulate stale keys |
| D7 | Defer `sync_to_sd` hash-based comparison to a follow-up | Primary pain point is `sync_from_sd`; `sync_to_sd` uses the same comparison logic but the false-positive problem is less acute in the local→SD direction. However, `sync_to_sd`'s `_build_post_sync_manifest` will still write hashes to keep the manifest populated | Full hash support in both directions — adds scope without addressing the primary pain point |
| D8 | Keep single-threaded hashing for initial implementation | Sufficient for incremental runs (<1s); first-run cost is one-time. Threading can be added later if profiling shows need | ThreadPoolExecutor — 2–4x speedup on SSD but adds complexity for a one-time cost |
| D9 | Delete `create_snapshot.py` and all snapshot infrastructure | Snapshot system has a single purpose (before-state for `fix_references`) that the manifest now serves with graceful degradation. No remaining use case | Keep as optional tool — dead code with no purpose |
| D10 | `compute_sync()` signature unchanged; hash comparison is internal | Avoids breaking the `manifest=None` path used by cloud sync. The function uses hashes when available in manifest entries, falls through to existing stat comparison otherwise | New parameter for hash mode — unnecessary coupling |

## Technical Specification

### 5a. Language and Tooling

| Item | Choice | Notes |
|------|--------|-------|
| Language | Python 3.12+ | Existing codebase; reference `agent-system/standards/languages/` for Python standards |
| Key Dependencies | `hashlib` (stdlib) | No new dependencies; SHA-256 already used via `hash_file()` |
| Test Framework | pytest | Existing test infrastructure with 377 tests |
| Linter/Formatter | Existing project setup | No changes to tooling |

### 5b. Architecture

The changes modify existing modules rather than introducing new ones. The architectural change is conceptual: the manifest transitions from a stat-only record to a stat+hash record, becoming the single source of truth for both sync and reference-fixing.

**Module responsibilities after the change:**

- **`syncing.py`** — Owns `FileRecord` (now with optional `hash`), manifest I/O (v1 migration, v2 read/write), `compute_sync()` (hash-aware comparison), and the stat-cache match helper. This module is the custodian of the manifest format.
- **`deluge_sdk.py`** — Continues to own `hash_file()`. The `hash_all_samples()` function becomes unused after `fix_references` switches to manifest-based lookup, but is not deleted in this plan (it may have future uses or be removed in a separate cleanup).
- **`sync_from_sd.py`** — Its `_build_post_sync_manifest()` gains hash computation for copied/new files and hash preservation for unchanged files.
- **`sync_to_sd.py`** — Same `_build_post_sync_manifest()` changes as `sync_from_sd.py` to keep the manifest populated with hashes.
- **`fix_references.py`** — `compute_migration_map()` is replaced with a new function that reads the manifest, inverts it to a hash→paths mapping, and follows a lookup chain with graceful degradation. The `classify_ref_changes()` and `update_sample_refs()` functions are unchanged.
- **`paths.py`** — `SNAPSHOTS_DIR` is removed.

**Data flow for sync (after change):**

1. Read manifest (v2 with hashes, or v1 migrated with null hashes)
2. Scan source and dest trees (stat only — unchanged)
3. For each file pair, compare via manifest: stat-cache check first, hash comparison on miss
4. Execute plan (copy/delete — unchanged)
5. Build post-sync manifest: preserve hashes for unchanged files, compute hashes for copied/new files
6. Write manifest (v2 format)

**Data flow for fix_references (after change):**

1. Read manifest (optional — graceful degradation if missing)
2. Invert manifest to hash→paths mapping (the "before" state)
3. Scan current filesystem, hash only files at paths not in manifest (the "after" state)
4. Compare before and after hash maps to build migration map
5. Classify XML references against migration map (unchanged)
6. Apply fixes (unchanged)
7. Update manifest keys for moved files (key rename, no re-hash)

### 5c. Interface Design

**Inputs** — No new CLI arguments. The `--snapshot` flag on `fix_references.py` is removed. All scripts continue to read the manifest from `SYNC_MANIFEST_PATH` by default.

**Outputs** — Manifest JSON gains `"version": 2` at the top level and `"hash"` per file entry. Console output is unchanged for sync scripts. `fix_references.py` no longer prints "Using latest snapshot: ..." — it prints manifest status instead (e.g. "Using manifest with 7940 entries (7200 with hashes)").

**Error Handling** — Graceful degradation is the core error strategy for `fix_references`:
- Manifest missing → all broken refs flagged as unresolvable
- Manifest present but entry has no hash → that specific ref falls to "unresolvable"
- Hash found in manifest but no matching file on disk → "genuinely missing/deleted"
- Multiple current files share the same hash → suggest best match via path similarity, or flag as ambiguous

**User Interaction** — No changes to existing interaction patterns. Sync scripts retain `--dry-run` and confirmation prompts. `fix_references.py` retains `--apply` for auto-apply.

**CLI changes for `fix_references.py`:**

```
# Before (snapshot-based)
python fix_references.py --snapshot path/to/snapshot.json

# After (manifest-based, no flags needed)
python fix_references.py

# Explicit manifest path (optional, defaults to SYNC_MANIFEST_PATH)
python fix_references.py --manifest path/to/manifest.json
```

### 5d. Integration Points

- **`compute_sync()` internal change** — The function's public signature is unchanged. When a manifest entry contains a hash, the comparison uses hash-based logic. When the hash is null or the manifest is absent, the existing stat-based comparison is used. This means `sync_samples_to_cloud.py` (which passes `manifest=None`) is completely unaffected.
- **`hash_file()` reuse** — The existing function in `deluge_sdk.py` is imported by `syncing.py` and `fix_references.py`. No duplication.
- **Manifest as shared resource** — Both sync scripts and `fix_references.py` read/write the same manifest file. Concurrent access is not a concern (single-user tool), and atomic writes are already implemented.
- **SD card safety** — All hashing operations are read-only. The manifest is written to `scripts/data/` (not `DELUGE/`). No change to SD card safety posture per `standards/project.md`.

## Cross-Cutting Concerns

| Concern (from Research) | Plan Mitigation |
|------------------------|-----------------|
| Manifest file grows ~550KB (hash strings) | Acceptable. JSON remains compact at ~1.1MB total. Monitor but no action needed. |
| First-run hash computation 60–120s | One-time cost, clearly communicated via progress output. Optional `--populate-hashes` flag on sync scripts deferred to follow-up. |
| `compute_sync()` complexity increase | Comprehensive test matrix covering all comparison branches: stat-cache hit, stat-cache miss with hash match, stat-cache miss with hash mismatch, null hash (migration), null mtime, no manifest entry. |
| Concurrent Deluge use during sync | Unchanged — user-responsibility issue. Hashing doesn't help with mid-write reads. |
| FAT32 timestamp tolerance | Unchanged — `_mtime_matches()` continues to apply FAT32 ±2s tolerance on SD-side stats. |
| Platform portability | `hashlib.sha256()` is stdlib, works identically on Windows and Linux. No platform-specific concerns. |

## Risk Mitigation

| Risk (from Research) | Plan Mitigation | Residual Risk |
|---------------------|-----------------|---------------|
| First-run hash computation too slow (>2 min) | Progress indicator already exists in `hash_all_samples()`. Post-sync manifest builder will show similar progress. One-time event. | Low — SSD users: 60–120s. HDD users: 5–10 min (acceptable for one-time). |
| Manifest file size growth | ~550KB addition for ~7940 hash strings. Total ~1.1MB. | Negligible. |
| SHA-256 CPU bottleneck on NVMe SSD | Incremental runs are unaffected (<1s). First run may be CPU-limited at ~300–500 MB/s. | Low — one-time cost. xxHash swap is a single-function change if needed. |
| Manifest corruption (power loss during write) | Atomic write already implemented (tempfile + rename). Worst case: must re-hash everything on next run. | Very low. |
| `compute_sync()` complexity increase | Comprehensive test matrix (see Phase 2 task 2.3). Every comparison branch has dedicated test coverage. | Medium — more code paths, but well-tested. |
| Stat cache miss storm after git checkout | ~200–500 files re-hashed in 2–10s on SSD. Much better than copying ~200 files from SD. | Low — acceptable tradeoff. |
| `fix_references` degraded mode confusion | Clear console messaging: "Manifest has no entry for X — cannot determine hash, marking as unresolvable." | Low — user informed. |

## Implementation Roadmap

## Phase 1: Manifest Schema v2 and Migration

> **Goal:** Extend the manifest format to support content hashes with transparent migration from v1. After this phase, all manifest I/O handles both formats and all existing tests pass.
> **Prerequisites:** None — this is the foundation phase.

### Task 1.1: Extend FileRecord with Optional Hash Field

- **Description:** Add an optional `hash` field to the `FileRecord` TypedDict in `syncing.py`. The field is a string (hex digest) or `None` when not yet computed. Since `TypedDict` fields are required by default, this requires either a second TypedDict with `total=False` for the optional field, or a migration to a different approach — the implementer decides the specific mechanism.
- **Inputs:** Current `FileRecord` in `syncing.py`
- **Outputs:** Updated `FileRecord` that can carry a hash value alongside existing stat fields
- **Acceptance Criteria:**
  - [x] `FileRecord` supports an optional `hash` field that can be `None` or a hex digest string
  - [x] Existing code that creates `FileRecord` dicts without `hash` continues to work
  - [x] Type checking passes
- **Implementation Notes:**
  > Used two-class TypedDict pattern: `_FileRecordRequired` (required stat fields) inherits into `FileRecord(_FileRecordRequired, total=False)` with optional `hash: str | None`. This allows existing code to create FileRecord dicts without the hash field.

### Task 1.2: Update read_manifest() for v1/v2 Detection and Migration

- **Description:** Modify `read_manifest()` in `syncing.py` to detect the manifest version and handle both formats. A v2 manifest has a top-level `"version": 2` field. A v1 manifest has no `"version"` field. On reading a v1 manifest, stat fields are preserved and `hash` is set to `None`. Entries from pre-dual-stat formats (missing `sd_size`/`sd_mtime`/`local_size`/`local_mtime`) continue to be dropped as they are today.
- **Inputs:** Current `read_manifest()` in `syncing.py`
- **Outputs:** Updated function that returns `FileRecord` entries with hash field populated (v2) or set to `None` (v1 migration)
- **Acceptance Criteria:**
  - [x] v2 manifest with `"version": 2` loads correctly with hash values preserved
  - [x] v1 manifest (no `"version"` field) loads with all entries having `hash` set to `None`
  - [x] Corrupt or missing manifest returns empty state (existing behaviour preserved)
  - [x] Pre-dual-stat entries are still dropped
- **Implementation Notes:**
  > Detects version via `data.get("version", 1)`. For v1, hash is always set to `None` (even if a stray hash field exists in the JSON). For v2, hash is read via `val.get("hash")`. All existing validation (dual-stat field check) preserved.

### Task 1.3: Update write_manifest() for v2 Format

- **Description:** Modify `write_manifest()` in `syncing.py` to always write v2 format. The output JSON includes `"version": 2` at the top level, and each file entry includes the `"hash"` field (which may be `null` for entries not yet hashed). Atomic write behaviour is preserved.
- **Inputs:** Current `write_manifest()` in `syncing.py`
- **Outputs:** Updated function that writes v2-format manifests
- **Acceptance Criteria:**
  - [x] Written manifest JSON includes `"version": 2` at the top level
  - [x] Each file entry includes `"hash"` key (value is string or null)
  - [x] Atomic write via tempfile + rename is preserved
  - [x] Round-trip test: write v2 → read back → data matches
- **Implementation Notes:**
  > Normalises entries before writing: builds a new dict with explicit `"hash": rec.get("hash")` so entries without a hash key get `null` in JSON. Payload includes `"version": 2` at the top level. Atomic write logic unchanged.

### Task 1.4: Update Manifest Tests

- **Description:** Update existing manifest I/O tests in `test_syncing.py` and add new tests for v1→v2 migration and v2 round-trip. Existing tests that construct `FileRecord` dicts must include the `hash` field (or be updated to work with the new optional field).
- **Inputs:** Existing tests in `test_syncing.py`, `test_sync_from_sd.py`, `test_sync_to_sd.py`
- **Outputs:** Updated tests covering v1 migration, v2 read/write, and round-trip
- **Acceptance Criteria:**
  - [x] Test: v1 manifest (no version field) is read with all entries having `hash=None`
  - [x] Test: v2 manifest round-trips correctly (write → read → data matches including hashes)
  - [x] Test: v1 manifest with mixed entry quality (some missing dual-stat fields) drops bad entries, migrates good ones
  - [x] Test: manifest with `"hash": null` entries reads correctly
  - [x] All existing manifest-related tests pass (updated as needed for new field)
  - [x] All other tests in the suite continue to pass
- **Implementation Notes:**
  > Added 9 new tests in `test_sync_from_sd.py`: `TestManifestV2Format` (3 tests — version marker, null hash, hash with value), `TestManifestV2RoundTrip` (2 tests — with hashes, without hash field), `TestManifestV1Migration` (4 tests — hash=None, mixed quality, v2 preservation, v1 ignores stray hash). All 391 tests pass (382 existing + 9 new). No existing tests required modification.

---

## Phase 2: Hash-Aware Sync

> **Goal:** Add content-hash comparison to the sync workflow. After this phase, `sync_from_sd` and `sync_to_sd` use hash-based change detection when hashes are available, and populate hashes in the manifest for new/copied files. The stat-cache fast-path keeps incremental runs fast.
> **Prerequisites:** Phase 1 complete (manifest supports hash field).

### Task 2.1: Add Stat-Cache Match Helper

- **Description:** Add a helper function to `syncing.py` that determines whether the current file stat matches the manifest entry's stat (the fast-path check). The function returns `True` when size and mtime both match AND mtime is positive (non-null). When it returns `True`, the cached hash can be trusted without re-reading the file. When it returns `False`, the file must be re-hashed. This helper is used internally by `compute_sync()`.
- **Inputs:** A scanned `FileEntry` (size + mtime) and the corresponding manifest entry's stat fields
- **Outputs:** Boolean indicating whether the stat cache is valid
- **Acceptance Criteria:**
  - [x] Returns `True` when size and mtime both match and mtime > 0
  - [x] Returns `False` when size differs
  - [x] Returns `False` when mtime differs
  - [x] Returns `False` when mtime is 0 or negative (null FAT32 timestamps)
  - [x] Unit tests for all four cases
- **Implementation Notes:**
  > Added `_stat_cache_valid(entry, manifest_size, manifest_mtime)` to `syncing.py`. Takes a `FileEntry` and manifest stat fields. Returns `False` for mtime <= 0 (null FAT32 timestamps), then checks size and mtime equality. Five unit tests in `TestStatCacheValid`.

### Task 2.2: Modify compute_sync() for Hash-Aware Comparison

- **Description:** Modify the manifest-present branch of `compute_sync()` in `syncing.py` to use content hashing when available. The new comparison logic for files that exist on both sides with a manifest entry follows this flow:

  **SD-side check (unchanged from current):** Compare SD file stat against manifest `sd_*` fields. If SD stat changed, the file must be copied (SD is source of truth). This check continues to use `_mtime_matches()` with FAT32 tolerance.

  **Local-side check (enhanced):** If SD stat is unchanged, check local side. If local stat matches manifest `local_*` fields (using the new stat-cache helper), the file is unchanged — skip. If local stat differs, check the hash:
  - If manifest has a hash: compute local file hash and compare. If hashes match, this is mtime drift — skip (and update manifest local stat fields to current values). If hashes differ, the local file has genuinely changed — copy from SD to restore source of truth.
  - If manifest has no hash (null, migration): compute local hash, store it in the manifest entry, then treat as stat-cache miss resolved (the next run will have the hash for fast comparison).

  The `manifest=None` path (used by cloud sync) is completely unchanged.

  **Important:** `compute_sync()` needs access to the actual file paths to compute hashes on stat-cache miss. It already has `source` and `dest` Path parameters. For the local file, the path is `dest / entry.rel_path` (when `source_is_sd=True`) or `source / entry.rel_path` (when `source_is_sd=False`). The function should import `hash_file` from `deluge_sdk`.

  **Manifest mutation:** `compute_sync()` currently does not mutate the manifest dict. With hash-aware comparison, it needs to update manifest entries when: (a) a stat-cache miss is resolved by hashing (update stats + hash), or (b) a null hash is populated during migration. The simplest approach is to mutate the passed-in `manifest` dict in place and let the caller write it. Alternatively, the function could return the updated manifest. The implementer decides the specific mechanism, but the caller (`sync_from_sd.py` / `sync_to_sd.py`) must be aware that the manifest may be modified.

- **Inputs:** Current `compute_sync()` in `syncing.py`, `hash_file()` from `deluge_sdk.py`
- **Outputs:** Updated `compute_sync()` that uses hash comparison on local-side stat-cache miss
- **Acceptance Criteria:**
  - [x] SD stat change → copy (existing behaviour preserved)
  - [x] Both stats match manifest → skip (existing behaviour preserved, faster with hash trust)
  - [x] Local stat differs, hash matches manifest → skip (NEW: mtime drift detected and tolerated)
  - [x] Local stat differs, hash differs from manifest → copy (genuine local change)
  - [x] Manifest entry with null hash → local file hashed, hash stored, skip/copy based on comparison
  - [x] `manifest=None` path unchanged (cloud sync unaffected)
  - [x] No manifest entry for file → falls through to existing direct stat comparison
- **Implementation Notes:**
  > Restructured the manifest branch in `compute_sync()`: SD-side check first (unchanged), then local stat-cache check via `_stat_cache_valid()`. On local stat miss: if manifest has hash → `hash_file()` the local file and compare (match = mtime drift, skip + update manifest stats; mismatch = genuine change, copy). If null hash (v1 migration) → hash, store in manifest, copy (conservative). `hash_file` imported from `deluge_sdk`. Manifest is mutated in place on stat-cache miss resolution. `manifest=None` path completely unchanged.

### Task 2.3: Update _build_post_sync_manifest() in Both Sync Scripts

- **Description:** Update `_build_post_sync_manifest()` in both `sync_from_sd.py` and `sync_to_sd.py` to populate the `hash` field in manifest entries.

  For **unchanged files** (key exists in old manifest, not in copied set): preserve the existing hash from the old manifest entry.

  For **copied/new files** (copied from source, or no prior manifest entry): compute the hash of the destination file after copying. This means hashing the local file (for `sync_from_sd`) or the SD file (for `sync_to_sd`) after `execute_plan()` completes.

  Display progress during hash computation for copied files (e.g. "Hashing 42 synced files..."). This is important for the first-run experience when all ~7500 files are copied and hashed.

- **Inputs:** Current `_build_post_sync_manifest()` in both sync scripts, `hash_file()` from `deluge_sdk.py`
- **Outputs:** Updated function that produces manifest entries with `hash` field populated
- **Acceptance Criteria:**
  - [x] Unchanged files preserve their existing hash from old manifest
  - [x] Copied files have hash computed from destination file after copy
  - [x] New files (no prior manifest entry) have hash computed
  - [x] Entries migrated from v1 (hash=None) that were unchanged still have hash=None (they get hashed on next stat-cache miss in `compute_sync`)
  - [x] Progress indicator shown when hashing copied files
  - [x] Filtered syncs (--xml/--wav) preserve entries for unscanned file types including their hashes
- **Implementation Notes:**
  > Updated `_build_post_sync_manifest()` in both `sync_from_sd.py` and `sync_to_sd.py`. Unchanged files preserve the old manifest entry (including hash). Copied/new files are collected into a `keys_to_hash` list, then hashed after all entries are built, with progress output ("Hashing N synced files..."). Hashes are computed from the destination file. `hash_file` imported from `deluge_sdk`. Filtered sync preservation of unscanned types unchanged (preserves full old entry including hash).

### Task 2.4: Update Sync Tests

- **Description:** Update existing sync tests and add new test cases covering the hash-aware comparison logic. This is a critical task — the comparison matrix is significantly expanded.
- **Inputs:** Existing tests in `test_syncing.py`, `test_sync_from_sd.py`, `test_sync_to_sd.py`
- **Outputs:** Comprehensive test coverage for all comparison branches
- **Acceptance Criteria:**
  - [x] Test: stat-cache hit (stats match, hash trusted) → skip
  - [x] Test: local stat-cache miss, hash match → skip (mtime drift)
  - [x] Test: local stat-cache miss, hash mismatch → copy
  - [x] Test: SD stat change → copy regardless of hash
  - [x] Test: null hash in manifest → hash computed, stored, correct decision made
  - [x] Test: null mtime → always re-hash (no stat-cache trust)
  - [x] Test: no manifest entry → falls through to direct stat comparison
  - [x] Test: manifest=None → existing stat-only comparison (cloud sync path)
  - [x] Test: `_build_post_sync_manifest` preserves hashes for unchanged files
  - [x] Test: `_build_post_sync_manifest` computes hashes for copied files
  - [x] Test: `_build_post_sync_manifest` with filtered sync preserves hashes for unscanned types
  - [x] Test: source_is_sd=False (sync_to_sd) hash comparison works correctly
  - [x] All existing sync tests pass (updated for new manifest field)
- **Implementation Notes:**
  > Added 22 new tests across 3 files: `TestStatCacheValid` (5 tests in `test_syncing.py`), `TestComputeSyncHashAware` (9 tests in `test_syncing.py`), `TestBuildPostSyncManifestHashing` (5 tests in `test_sync_from_sd.py`), `TestBuildPostSyncManifestHashing` (3 tests in `test_sync_to_sd.py`). All 413 tests pass (391 existing + 22 new). No existing tests required modification.

---

## Phase 3: Manifest-Based Reference Fixing

> **Goal:** Replace the snapshot-based `fix_references` workflow with manifest-based hash lookup and graceful degradation. After this phase, `fix_references.py` reads the manifest directly, no longer requires snapshots, and handles all manifest states gracefully.
> **Prerequisites:** Phase 2 complete (manifest is populated with hashes after sync).

### Task 3.1: Implement Manifest Inversion and Lookup Chain

- **Description:** Replace `compute_migration_map()` in `fix_references.py` with a new function that builds the "before" state from the manifest and the "after" state from the current filesystem, using the manifest's stat cache to avoid unnecessary re-hashing.

  **Building the "before" state:** Read the manifest and invert it to a hash→paths mapping. Each manifest entry with a non-null hash contributes to this mapping. Entries with null hash are skipped (they can't participate in move detection).

  **Building the "after" state:** Scan the current filesystem. For each file, check if its path and stat match a manifest entry (using the same stat-cache logic from Phase 2). If they match, the file hasn't moved — use the cached hash. If the path is not in the manifest or stats differ, compute the hash. This means only files at NEW paths (moved or added files) need to be hashed, rather than all ~5500 WAV files.

  **Comparison logic:** Compare the "before" and "after" hash maps using the same categorisation as the current `compute_migration_map()`: moved (1:1 hash match, different paths), deleted (hash in before only), added (hash in after only), ambiguous (multiple paths for same hash in either state).

  **Graceful degradation:** If no manifest exists or manifest is empty, the "before" state is empty, and all broken references are classified as unresolvable (via the "missing" category). If the manifest has entries but no hashes, same result. The function should print clear status messages about the manifest state.

  The function should accept an optional manifest dict (defaulting to reading from `SYNC_MANIFEST_PATH`) to support testing.

- **Inputs:** Current `compute_migration_map()` in `fix_references.py`, manifest data from `syncing.py`
- **Outputs:** New function that produces a `MigrationResult` from manifest data + current filesystem
- **Acceptance Criteria:**
  - [x] When manifest has pre-reorganisation paths+hashes: moved files detected correctly
  - [x] When manifest is missing: all broken refs classified as missing/unresolvable
  - [x] When manifest has entries but all hashes are null: same as missing (no move detection possible)
  - [x] Only files at paths not in manifest (or with changed stats) are hashed — not all files
  - [x] Ambiguous cases (multiple paths sharing a hash) categorised correctly
  - [x] Deleted files (hash in manifest, no file on disk with that hash) categorised correctly
  - [x] Clear console output about manifest state: entry count, hash coverage, degradation warnings
- **Implementation Notes:**
  > Replaced `compute_migration_map()` with manifest-based implementation. "Before" state built by inverting manifest hash→paths. "After" state built from filesystem scan with stat-cache optimisation (matching stat = trust cached hash, no re-read). Comparison produces moved/deleted/added/ambiguous categories. Graceful degradation: empty manifest or null hashes → no move detection, clear console warnings.

### Task 3.2: Add Manifest Key Update After Apply

- **Description:** After `fix_references` applies fixes (updates XML references), update the manifest's path keys for moved files. For each moved sample (old_path → new_path), rename the manifest key from old_path to new_path, preserving the hash and stat data. This is a key-rename operation with no file I/O (no re-hashing).

  Write the updated manifest back to disk. If the write fails, print a warning but don't fail the operation — the next sync will self-heal the manifest.

  This enables multi-round reorganisation: after fixing references for one batch of moves, the manifest reflects the new paths, so a subsequent `fix_references` run sees the correct "before" state.

- **Inputs:** Migration result (moved dict), current manifest, manifest file path
- **Outputs:** Updated manifest with renamed keys written to disk
- **Acceptance Criteria:**
  - [x] Moved files have their manifest keys renamed (old_path → new_path)
  - [x] Hash and stat data preserved on renamed keys
  - [x] Manifest written to disk after key updates
  - [x] Write failure produces a warning, not an error
  - [x] Keys for non-moved files (deleted, ambiguous, unchanged) are not modified
- **Implementation Notes:**
  > Added `update_manifest_keys()` function. For each moved entry, pops old key and inserts under normalised new key, preserving all hash and stat data. Uses `write_manifest()` for atomic write. `OSError` on write caught and printed as warning. Called from `main()` after successful apply.

### Task 3.3: Update fix_references CLI

- **Description:** Update the `main()` function in `fix_references.py`:
  - Remove the `--snapshot` argument
  - Add an optional `--manifest` argument that defaults to `SYNC_MANIFEST_PATH`
  - The main flow becomes: read manifest → build migration map (new function from 3.1) → classify refs (unchanged) → preview and apply (unchanged) → update manifest keys (new from 3.2)
  - Remove all imports and references to `SNAPSHOTS_DIR` and snapshot-related code
  - Print manifest status on startup (entry count, hash coverage)

- **Inputs:** Current `main()` in `fix_references.py`
- **Outputs:** Updated CLI that uses manifest-based workflow
- **Acceptance Criteria:**
  - [x] `--snapshot` argument removed
  - [x] `--manifest` argument accepted (optional, defaults to `SYNC_MANIFEST_PATH`)
  - [x] Running without arguments uses the default manifest path
  - [x] Running with `--manifest path/to/manifest.json` uses the specified path
  - [x] Missing manifest file prints a degradation warning and proceeds (does not exit with error)
  - [x] Manifest status printed on startup
  - [x] No references to snapshots or `SNAPSHOTS_DIR` remain in the file
- **Implementation Notes:**
  > Removed `--snapshot` arg, added `--manifest` (optional, defaults to `SYNC_MANIFEST_PATH`). Main flow: read manifest → `compute_migration_map()` → `classify_ref_changes()` → `preview_and_apply()` → `update_manifest_keys()` (on apply with moves). All snapshot imports removed.

### Task 3.4: Update fix_references Tests

- **Description:** Rewrite tests in `test_fix_references.py` for the new manifest-based workflow. Existing tests for `classify_ref_changes()` and `update_sample_refs()` should need minimal changes (those functions are unchanged). Tests for `compute_migration_map()` need to be rewritten to use manifest data instead of snapshot data. Add new tests for graceful degradation, manifest key update, and the new CLI.
- **Inputs:** Existing tests in `test_fix_references.py`
- **Outputs:** Updated tests covering manifest-based workflow
- **Acceptance Criteria:**
  - [x] Test: manifest with moved files → correct migration map
  - [x] Test: manifest with deleted files (hash in manifest, not on disk) → correct categorisation
  - [x] Test: manifest with ambiguous hashes → correct categorisation
  - [x] Test: empty/missing manifest → graceful degradation (all unresolvable)
  - [x] Test: manifest with null hashes → graceful degradation for those entries
  - [x] Test: manifest key update after apply — keys renamed correctly
  - [x] Test: only new-path files are hashed (manifest stat-cache used for existing paths)
  - [x] Test: CLI with `--manifest` flag
  - [x] Test: CLI without flags uses default manifest path
  - [x] Tests for `classify_ref_changes()` pass unchanged (or with minimal adaptation)
  - [x] Tests for `update_sample_refs()` pass unchanged
  - [x] `TestMain.test_missing_snapshot_file_exits` replaced with manifest-aware equivalent
- **Implementation Notes:**
  > 53 tests in `test_fix_references.py` covering all Phase 3 functionality: `TestMain` (2 CLI tests), `TestComputeMigrationMap` (11 tests: moves, deletes, adds, ambiguous, unchanged, mixed), `TestGracefulDegradation` (4 tests: null hashes, missing SAMPLES dir, console output), `TestStatCacheOptimization` (3 tests: cache hit avoids hash, cache miss triggers hash, new path triggers hash), `TestManifestKeyUpdate` (4 tests: rename, no-op, write failure warning, data preservation), `TestClassifyRefChanges` (10 tests), `TestPreviewAndApply` (14 tests), plus 5 integration tests. All 425 tests pass (413 existing + 12 new Phase 3 tests).

---

## Phase 4: Snapshot System Cleanup

> **Goal:** Remove all snapshot-related code and data from the codebase. After this phase, the snapshot system is fully eliminated.
> **Prerequisites:** Phase 3 complete (fix_references no longer uses snapshots).

### Task 4.1: Delete create_snapshot.py and Its Tests

- **Description:** Delete `scripts/create_snapshot.py` and `scripts/tests/test_create_snapshot.py`. These files have no remaining purpose after the manifest replaces the snapshot system.
- **Inputs:** Files to delete: `scripts/create_snapshot.py`, `scripts/tests/test_create_snapshot.py`
- **Outputs:** Both files removed from the repository
- **Acceptance Criteria:**
  - [x] `scripts/create_snapshot.py` deleted
  - [x] `scripts/tests/test_create_snapshot.py` deleted
  - [x] No other file imports from `create_snapshot`
- **Implementation Notes:**
  > `TestHashFile` tests (2 tests for `hash_file()`) were moved to `test_deluge_sdk.py` since `hash_file` is still used by sync and fix_references. 8 snapshot-specific tests deleted. `deluge-snapshot` entry removed from `pyproject.toml`.

### Task 4.2: Remove SNAPSHOTS_DIR from paths.py

- **Description:** Remove the `SNAPSHOTS_DIR` constant from `scripts/deluge_lib/paths.py`. Verify no remaining references to `SNAPSHOTS_DIR` exist in the codebase.
- **Inputs:** `scripts/deluge_lib/paths.py`
- **Outputs:** Updated file without `SNAPSHOTS_DIR`
- **Acceptance Criteria:**
  - [x] `SNAPSHOTS_DIR` removed from `paths.py`
  - [x] No remaining imports or references to `SNAPSHOTS_DIR` in any file
  - [x] All tests pass
- **Implementation Notes:**
  > `SNAPSHOTS_DIR` was also imported by `sample_overview.py` — removed along with the `--snapshot` CLI flag and snapshot-loading logic from the `duplicates` subcommand.

### Task 4.3: Clean Up Remaining Snapshot References

- **Description:** Search the entire codebase for any remaining references to snapshots, `create_snapshot`, `SNAPSHOTS_DIR`, or snapshot-related concepts. This includes documentation files, comments, and any imports. Remove or update all references found.
- **Inputs:** Codebase search results
- **Outputs:** Clean codebase with no snapshot references
- **Acceptance Criteria:**
  - [x] No references to "snapshot" in Python source files (except historical references in docs/research if any)
  - [x] No references to `SNAPSHOTS_DIR` anywhere
  - [x] No references to `create_snapshot` anywhere
  - [x] `scripts/data/snapshots/` directory can be noted for manual deletion (do not delete data files automatically)
  - [x] Full test suite passes
- **Implementation Notes:**
  > Cleaned up: `fix_references.py` MigrationResult docstring ("before-snapshot" → "manifest state"), `docs/glossary.md` (removed Snapshot entry, updated Migration map entry), unused `json` import in `sample_overview.py`. Research/plan docs left as historical record. `scripts/data/snapshots/` directory left as-is (user data).

---

## Progress Tracker

| Phase | Status | Tasks Complete | Notes |
|-------|--------|---------------|-------|
| Phase 1: Manifest Schema v2 and Migration | **Complete** | 4/4 | All 391 tests pass. Implemented 2026-05-15. |
| Phase 2: Hash-Aware Sync | **Complete** | 4/4 | All 413 tests pass. Implemented 2026-05-15. |
| Phase 3: Manifest-Based Reference Fixing | **Complete** | 4/4 | All 425 tests pass. Implemented 2026-05-15. |
| Phase 4: Snapshot System Cleanup | **Complete** | 3/3 | All 415 tests pass. Implemented 2026-05-15. |

## Open Questions

1. **Should `compute_sync()` mutate the manifest in-place or return an updated copy?**
   - **Impact:** Affects the interface between `compute_sync()` and the post-sync manifest builder. In-place mutation is simpler but has side effects. Returning a copy is cleaner but requires the caller to merge.
   - **Recommendation:** In-place mutation. The manifest dict is already owned by the caller and is rebuilt by `_build_post_sync_manifest()` after sync completes. The mutation during `compute_sync()` (updating stats and populating null hashes) is an optimisation that the post-sync builder can incorporate.
   - **Blocking:** No — implementer decides during Phase 2.
   - **Resolution:**

2. **Should `hash_all_samples()` in `deluge_sdk.py` be deprecated or deleted?**
   - **Impact:** After Phase 3, `fix_references` no longer calls it. It may still be useful for standalone analysis or debugging.
   - **Recommendation:** Leave it in place. It's a small, self-contained function with no maintenance burden. If a future cleanup effort identifies it as truly dead code, it can be removed then.
   - **Blocking:** No.
   - **Resolution:**

3. **Should `sync_to_sd` use hash-based comparison (not just hash population)?**
   - **Impact:** Would eliminate mtime false positives in the local→SD direction. The research recommends deferring this.
   - **Recommendation:** Defer to follow-up. `sync_to_sd` already benefits from this plan because it writes hashes to the manifest (Task 2.3), keeping the manifest populated for `fix_references`. Adding hash-based comparison to `sync_to_sd` is the same pattern as `sync_from_sd` but is lower priority.
   - **Blocking:** No.
   - **Resolution:**

4. **What should happen to existing snapshot files in `scripts/data/snapshots/`?**
   - **Impact:** Historical data files on disk. Deleting them is a destructive action.
   - **Recommendation:** Note in Task 4.3 that the directory exists and can be manually deleted. Do not delete data files automatically in a script change.
   - **Blocking:** No.
   - **Resolution:**

## References

### Research Document
- [unified-hash-sync-research.md](../research/unified-hash-sync-research.md) — Primary input

### Standards Applied
- [project.md](../../agent-system/standards/project.md) — SD card safety rules (hashing is read-only, manifest written to scripts/data/)
- [standards.index.md](../../agent-system/standards/standards.index.md) — Standards registry

### Project Files
- [syncing.py](../../scripts/deluge_lib/syncing.py) — FileRecord, compute_sync, manifest I/O
- [scanning.py](../../scripts/deluge_lib/scanning.py) — scan_tree, FileEntry
- [deluge_sdk.py](../../scripts/deluge_lib/deluge_sdk.py) — hash_file, hash_all_samples
- [paths.py](../../scripts/deluge_lib/paths.py) — SNAPSHOTS_DIR (to be removed)
- [sync_from_sd.py](../../scripts/sync_from_sd.py) — _build_post_sync_manifest
- [sync_to_sd.py](../../scripts/sync_to_sd.py) — _build_post_sync_manifest
- [sync_samples_to_cloud.py](../../scripts/sync_samples_to_cloud.py) — unaffected (manifest=None)
- [fix_references.py](../../scripts/fix_references.py) — compute_migration_map, classify_ref_changes
- [create_snapshot.py](../../scripts/create_snapshot.py) — to be deleted
- [sync_manifest.json](../../scripts/data/sync_manifest.json) — current manifest (~7940 entries)

### Existing Plans
- [dual-stat-manifest-plan.md](dual-stat-manifest-plan.md) — Predecessor plan that introduced the dual-stat manifest

## Change Log

| Date | Change | Reason |
|------|--------|--------|
| 15 May 2026 | Initial plan created | Research document completed |
