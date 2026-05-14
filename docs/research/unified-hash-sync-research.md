# Research: Unified Hash-Based Sync and Reference-Fixing System

> **Document Type:** Research
> **Date:** 15 May 2026 (revised)
> **Request:** Research a unified hash-based sync and reference-fixing system that replaces the current mtime-based sync manifest and separate snapshot system with a single content-hash manifest
> **Pipeline:** Research → Plan → Implement

## Executive Summary

The current dual-stat mtime manifest (implemented May 2026) solved the null-timestamp false-positive problem but remains vulnerable to mtime drift caused by git branch switching, extraction scripts, and local file reorganisation — all of which change mtimes without changing content, producing hundreds of false "copy" decisions. Content hashing is the definitive solution: it makes change detection immune to mtime instability.

A unified manifest that stores per-file hashes alongside stat data serves both sync (content-change detection) and reference-fixing (hash→path move detection), **eliminating the separate snapshot system entirely**. The recommended approach uses SHA-256 (already in the codebase, no new dependency) and stat data as a fast-path cache to avoid re-hashing unchanged files (the same strategy git uses).

The key design principle is **graceful degradation**: `fix_references` works with whatever manifest state is available, with no ordering constraints. If the manifest has pre-reorganisation data, broken references are resolved via hash lookup. If the manifest is stale or was overwritten by a sync, references that can't be matched are marked unresolvable. No snapshots, no manifest backups, no required operation sequence.

First-run hash computation for ~5500 WAV files is estimated at 60–120 seconds on SSD, with subsequent incremental runs completing in under a second when few files change.

## Objectives

1. Evaluate hash algorithm choices (SHA-256 vs xxHash) for ~7500 files of varying sizes
2. Design an incremental hashing strategy that avoids re-hashing all files on every run
3. Design a unified manifest schema serving both sync and reference-fixing
4. Design a graceful degradation model for `fix_references` that works with any manifest state
5. Assess impact on cloud sync (`sync_samples_to_cloud.py`)
6. Plan first-run migration from the current dual-stat manifest
7. Estimate hashing performance and identify parallelisation opportunities
8. Address edge cases: concurrent Deluge use, ambiguous moves, missing files

## Feature Overview

### Purpose and Value

The unified system replaces three separate mechanisms with one:

| Current | Unified |
|---------|---------|
| Dual-stat mtime manifest (sync) | Single manifest with hashes + stat cache |
| Snapshot system (dated JSON files) | Eliminated — manifest is the "before" state |
| Separate `hash_all_samples()` calls in fix_references | Hash data already in manifest |

Key benefits:
- **Eliminates mtime false positives** — Content hashing is immune to mtime drift from git operations, extraction scripts, and cross-filesystem copies
- **Eliminates separate snapshot system** — Manifest is the "before" state; no separate `create_snapshot` step. `fix_references` reads manifest directly and updates keys after applying. Multi-round reorganisation just works.
- **Single source of truth** — One file tracks both sync state and content fingerprints
- **Incremental by default** — Stat-based cache prevents re-hashing unchanged files

### Primary Use Cases

1. **SD → local sync**: Detect which files actually changed (not just which mtimes drifted)
2. **Local → SD sync**: Same content-based change detection
3. **Post-reorganisation reference fix**: For broken XML references, look up the old path's hash in the manifest, then search the current filesystem for that hash to find where the file moved

### Inputs and Outputs

| Operation | Input | Output |
|-----------|-------|--------|
| Sync (either direction) | SD card + local DELUGE/ + manifest | Updated files + updated manifest |
| Fix references | Broken XML refs + manifest (optional) + current filesystem | Updated XML files + updated manifest keys |

### Scope

**In scope:**
- Manifest schema redesign with hash field
- Modified `compute_sync()` comparison logic
- Modified `hash_file()` / hashing infrastructure
- Graceful degradation model for `fix_references` (works with any manifest state)
- Modified `fix_references.py` (manifest-based hash lookup; manifest key update as optimisation)
- Deletion of `create_snapshot.py` (snapshot system fully removed)
- Migration from current dual-stat manifest

**Out of scope:**
- XML parsing changes (no firmware format changes involved)
- Cloud sync changes (operates NTFS→NTFS with reliable stats)
- New CLI scripts (modifications to existing scripts only)
- Audio content analysis or deduplication features

## Existing Assets Analysis

| Capability | Status | Location | Notes |
|------------|--------|----------|-------|
| File scanning with stat | ✅ Ready | [scripts/deluge_lib/scanning.py](../../scripts/deluge_lib/scanning.py) | `scan_tree()` returns `FileEntry(rel_path, size, mtime)` |
| SHA-256 file hashing | ✅ Ready | [scripts/deluge_lib/deluge_sdk.py](../../scripts/deluge_lib/deluge_sdk.py) | `hash_file()` with 64KB chunks; `hash_all_samples()` groups by digest |
| Dual-stat manifest I/O | ✅ Ready | [scripts/deluge_lib/syncing.py](../../scripts/deluge_lib/syncing.py) | `read_manifest()`, `write_manifest()` with atomic writes |
| Sync comparison logic | ✅ Ready | [scripts/deluge_lib/syncing.py](../../scripts/deluge_lib/syncing.py) | `compute_sync()` with dual-stat manifest support |
| Post-sync manifest builder | ⚠️ Needs extension | [scripts/sync_from_sd.py](../../scripts/sync_from_sd.py) | `_build_post_sync_manifest()` — needs hash computation |
| Snapshot creation | ❌ Delete | [scripts/create_snapshot.py](../../scripts/create_snapshot.py) | Entire snapshot system removed; manifest with graceful degradation replaces it |
| Migration map computation | ⚠️ Needs redesign | [scripts/fix_references.py](../../scripts/fix_references.py) | `compute_migration_map()` currently calls `hash_all_samples()` directly; will use manifest-based lookup chain with graceful degradation |
| XML reference classifier | ✅ Ready | [scripts/fix_references.py](../../scripts/fix_references.py) | `classify_ref_changes()` — no changes needed |
| XML reference updater | ✅ Ready | [scripts/fix_references.py](../../scripts/fix_references.py) | `update_sample_refs()` — no changes needed |
| Cloud sync | ✅ No change needed | [scripts/sync_samples_to_cloud.py](../../scripts/sync_samples_to_cloud.py) | Uses `manifest=None` path; NTFS→NTFS stats reliable |
| Manifest file | ✅ Ready | [scripts/data/sync_manifest.json](../../scripts/data/sync_manifest.json) | ~7940 entries with dual-stat format |
| Test suite | ⚠️ Needs updates | [scripts/tests/](../../scripts/tests/) | 377 tests; manifest and snapshot tests need updating |

## Findings

### 1. The Remaining mtime False-Positive Problem

**Source:** Task description and analysis of [scripts/deluge_lib/syncing.py](../../scripts/deluge_lib/syncing.py) `compute_sync()`.

The dual-stat manifest (implemented per [docs/plans/dual-stat-manifest-plan.md](../plans/dual-stat-manifest-plan.md)) solved the null-timestamp problem (cause 1) and the `shutil.copy2` preservation issue (cause 5). However, three root causes remain:

| Root Cause | Dual-Stat Manifest Behaviour | Result |
|-----------|------|--------|
| **Local reorganisation** (extraction scripts modify XMLs, move samples) | Local mtime changes → `local_mtime != manifest.local_mtime` → flagged as "local drift" | **False positive** — content may be identical |
| **Git branch switching** | `git checkout` resets local mtimes to current time | **False positive** — content is identical if switching back to same branch |
| **FAT32↔NTFS mtime truncation** | Handled by `_mtime_matches()` tolerance on SD side; exact equality on local side | ✅ Solved |

The dual-stat manifest treats any local stat change as "the local file has drifted from the SD card's version" and triggers a re-copy. This is correct behaviour (SD is source of truth), but it's wasteful when the content hasn't actually changed. With ~7940 files, a `git checkout` can invalidate hundreds of entries, triggering hundreds of unnecessary copies on the next sync.

**Content hashing eliminates this class of false positives entirely.** If the hash matches the manifest, the file hasn't changed regardless of what happened to its mtime.

### 2. Hash Algorithm Analysis

**Source:** [xxhash.com](https://xxhash.com/) benchmarks, Python `hashlib` documentation, existing `hash_file()` in [scripts/deluge_lib/deluge_sdk.py](../../scripts/deluge_lib/deluge_sdk.py).

#### Performance Comparison (native C, reference hardware)

| Algorithm | Throughput | Digest Size | Notes |
|-----------|-----------|-------------|-------|
| XXH3 (SSE2) | 31.5 GB/s | 64-bit | Non-cryptographic |
| XXH128 (SSE2) | 29.6 GB/s | 128-bit | Non-cryptographic |
| XXH64 | 19.4 GB/s | 64-bit | Non-cryptographic |
| SHA-1 | 0.8 GB/s | 160-bit | Cryptographic (broken) |
| SHA-256 | ~0.5 GB/s | 256-bit | Cryptographic |

These are raw CPU throughputs. In practice, file hashing is I/O bound:

| Storage | Read Speed | Bottleneck |
|---------|-----------|------------|
| SD card (USB 2.0 reader) | ~25–30 MB/s | I/O bound with any algorithm |
| SATA SSD | ~500 MB/s | I/O bound with xxHash; CPU-limited with SHA-256 |
| NVMe SSD | ~2000+ MB/s | I/O bound with xxHash; significantly CPU-limited with SHA-256 |

#### Python-Specific Considerations

Python's `hashlib.sha256()` delegates to OpenSSL's C implementation, so it runs at near-native speed (~300–500 MB/s on modern CPUs in practice). The `xxhash` Python package wraps the C library and achieves similar I/O-bound performance. For SSD workloads:

- **SHA-256**: CPU becomes the bottleneck at ~300–500 MB/s. Hashing 27.5 GB of WAV data takes ~55–90 seconds.
- **XXH3**: CPU is never the bottleneck. Same 27.5 GB is I/O bound at SSD read speed: ~55 seconds on SATA SSD.
- **Difference**: 0–35 seconds on first run. On incremental runs (few files change), both are sub-second.

#### Dependency Analysis

| Algorithm | Dependency | Status |
|-----------|-----------|--------|
| SHA-256 | `hashlib` (stdlib) | ✅ Already used in codebase |
| XXH3 | `xxhash` (PyPI) | ❌ New dependency; requires C compilation or pre-built wheels |

Current dependencies in [scripts/pyproject.toml](../../scripts/pyproject.toml): `lxml>=5.0.0`, `python-dotenv>=1.0.0`. Adding `xxhash` would be the third runtime dependency.

#### Collision Risk

For non-cryptographic use (detecting content changes, not security), collision probability matters:

| Algorithm | Digest Bits | Collision probability (7500 files) |
|-----------|------------|------|
| SHA-256 | 256 | Negligible (~$10^{-68}$) |
| XXH3/XXH64 | 64 | ~$2.8 \times 10^{-12}$ (birthday bound ~4 billion files) |
| XXH128 | 128 | ~$1.7 \times 10^{-31}$ |

For 7500 files, even XXH64's 64-bit digest has negligible collision probability. However, the snapshot system groups files by hash digest — a collision would cause two different files to be treated as the same content, silently corrupting a reference fix. Given that this is a personal-use tool (not a distributed system), the practical risk is effectively zero with any algorithm, but SHA-256 provides the most conservative safety margin at acceptable performance cost.

#### Recommendation: SHA-256

- Already in the codebase (`hash_file()` in `deluge_sdk.py`)
- No new dependency
- Performance difference vs xxHash is marginal in practice (I/O bound on first run, trivial on incremental runs)
- Existing snapshots already use SHA-256 digests — no migration needed for hash format
- If performance becomes an issue in practice, swapping to xxHash later is a single-function change

### 3. Incremental Hashing Strategy (Git's Approach)

**Source:** [git-scm.com/docs/index-format](https://git-scm.com/docs/index-format), [git-scm.com/docs/racy-git](https://git-scm.com/docs/racy-git).

Git's index stores both stat data (size, mtime, ctime, ino, dev, uid, gid) and the content hash (SHA-1/SHA-256) for every tracked file. The comparison strategy:

1. **Fast path (stat cache hit):** If current stat matches cached stat → trust the cached hash, don't re-read the file
2. **Slow path (stat cache miss):** If stat differs → read file, compute hash, compare

This is exactly the strategy for the unified manifest:

```
for each file in manifest:
    current_stat = stat(file)
    if current_stat matches manifest stat:
        # Fast path: trust cached hash
        file_hash = manifest.hash
    else:
        # Slow path: re-hash
        file_hash = sha256(file)
        update manifest stat + hash
```

#### The "Racy" Edge Case

Git documents a "racy clean" problem: if a file is modified within the same timestamp granularity as the index write, the stat may match but the content has changed. Git solves this by forcing a content comparison when the file's mtime matches the index file's mtime.

For this project, the racy window is less concerning:
- NTFS has 100-nanosecond timestamp resolution (vs FAT32's 2-second resolution)
- Sync operations take seconds to minutes, so the manifest write time is always well after file modifications
- The worst case (file modified during sync) is caught on the next sync run

**However**, there's a project-specific variant: the Deluge firmware writes files to FAT32 without setting timestamps (null mtime). These files always have the same "stat" — they can't be distinguished by stat alone. The solution is simple: **files with null/invalid mtimes always get hashed** (no fast-path for them). Since only ~287 files have this issue, the cost is minimal.

#### Recommended Fast-Path Logic

```python
def _stat_matches(entry: FileEntry, manifest_entry: ManifestEntry) -> bool:
    """Check if current stat matches manifest stat (fast-path cache check)."""
    return (
        entry.size == manifest_entry.size
        and entry.mtime == manifest_entry.mtime
        and entry.mtime > 0  # Don't trust null timestamps
    )
```

When stat matches: trust cached hash (O(1), no I/O).
When stat misses: compute hash (O(n) in file size, requires file read).

### 4. Manifest Schema Design

**Source:** Current manifest format in [scripts/data/sync_manifest.json](../../scripts/data/sync_manifest.json), snapshot format in [scripts/create_snapshot.py](../../scripts/create_snapshot.py).

#### Current Dual-Stat Manifest (v1)

```json
{
  "last_sync_timestamp": "2026-05-14T04:43:51+00:00",
  "files": {
    "samples/drums/kick.wav": {
      "sd_size": 776340,
      "sd_mtime": 1679120228.0,
      "local_size": 776340,
      "local_mtime": 1679120228.0
    }
  }
}
```

#### Current Snapshot Format

```json
{
  "date": "2026-05-01",
  "deluge_root": "/path/to/DELUGE",
  "hashes": {
    "a1b2c3d4...": ["SAMPLES/DRUMS/kick.wav", "SAMPLES/DRUMS/kick_copy.wav"]
  }
}
```

#### Proposed Unified Manifest (v2)

```json
{
  "version": 2,
  "last_sync_timestamp": "2026-05-15T10:00:00+00:00",
  "files": {
    "samples/drums/kick.wav": {
      "sd_size": 776340,
      "sd_mtime": 1679120228.0,
      "local_size": 776340,
      "local_mtime": 1679120228.0,
      "hash": "a1b2c3d4e5f6..."
    },
    "kits/mykit.xml": {
      "sd_size": 1200,
      "sd_mtime": 1775809066.0,
      "local_size": 1200,
      "local_mtime": 1775809066.0,
      "hash": "9f8e7d6c5b4a..."
    }
  }
}
```

Key design decisions:

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Hash field name | `"hash"` | Simple, unambiguous. Algorithm implicit (SHA-256). |
| Hash scope | All files (WAV + XML) | XMLs are small; hashing adds negligible cost. Enables move detection for XMLs too. |
| Hash storage | Per-path (forward index) | Natural for sync (lookup by path). Inverted index derivable: `{hash: [paths]}`. |
| Version field | `"version": 2` | Enables `read_manifest()` to distinguish from v1 format and handle migration. |
| Null hash | `"hash": null` or missing | For files not yet hashed (during migration). Triggers re-hash on next access. |

#### Deriving the Inverted Index (for fix_references)

```python
def invert_manifest(files: dict[str, ManifestEntry]) -> dict[str, list[str]]:
    """Build hash → [paths] mapping from manifest entries."""
    inverted: dict[str, list[str]] = defaultdict(list)
    for key, entry in files.items():
        h = entry.get("hash")
        if h:
            inverted[h].append(key)
    return dict(inverted)
```

This trivially replaces the current `hash_all_samples()` call in `compute_migration_map()`, eliminating the most expensive operation in the reference-fixing workflow.

### 5. Snapshot Elimination and Graceful Degradation

**Source:** [scripts/create_snapshot.py](../../scripts/create_snapshot.py), [scripts/fix_references.py](../../scripts/fix_references.py), [scripts/deluge_lib/syncing.py](../../scripts/deluge_lib/syncing.py).

#### Why Snapshots Are Removed Entirely

The snapshot system (`create_snapshot.py`) exists for one purpose: to provide the "before" hash→path mapping that `fix_references` compares against the current filesystem. With content hashes in the manifest, the manifest can serve as the "before" state — but the critical insight is that **`fix_references` doesn't need a stored "before" state at all**. It works with whatever data is available and degrades gracefully.

This means:
- **Delete `create_snapshot.py` entirely** — no historical snapshots
- **No manifest backups** — no `sync_manifest.backup.json`
- **No ordering constraints** — the user need not remember any particular sequence of operations
- **No `--snapshot` flag** — `fix_references` reads the manifest by default (if available)

#### The Lookup Chain for Broken References

For each broken reference (XML path doesn't resolve to a file on disk), `fix_references` follows this chain:

**Step 1 — Manifest lookup (happy path):**
1. Broken ref points to `SAMPLES/OLD/kick.wav`
2. Manifest has this path with hash `abc123`
3. Scan current filesystem → hash `abc123` found at `SAMPLES/NEW/kick.wav`
4. → **Resolved as a move.** Fix the reference.

**Step 2 — No manifest entry (degraded path):**
1. Broken ref points to `SAMPLES/OLD/kick.wav`
2. Manifest doesn't have this path (already updated by a sync, or never existed)
3. Cannot determine the old file's hash without the file itself
4. → **Unresolvable.** Mark as unresolvable (file was likely deleted, or the manifest was overwritten)

**Step 3 — Hash collision (multiple matches):**
1. Broken ref points to `SAMPLES/OLD/kick.wav`
2. Manifest has this path with hash `abc123`
3. Multiple current files share hash `abc123`
4. → **Suggest best match** using path similarity (same parent dir, similar name), or flag for user decision

**Step 4 — Genuinely missing (file deleted from disk):**
1. Broken ref points to `SAMPLES/OLD/kick.wav`
2. Manifest has this path with hash `abc123`
3. No current file on disk has hash `abc123`
4. → **Genuinely missing/deleted.** User must resolve manually.

#### Why No Ordering Constraint Is Needed

The graceful degradation model means `fix_references` produces useful results regardless of when it's run relative to sync operations:

| Scenario | Manifest State | fix_references Behaviour |
|----------|---------------|--------------------------|
| sync → reorganise → fix_references | Manifest has pre-reorg paths + hashes | **Best case:** full hash-based move resolution |
| reorganise → fix_references (no prior sync) | Manifest missing or stale | **Degraded:** unresolvable refs flagged, but no data loss |
| sync → reorganise → sync again → fix_references | Manifest overwritten with post-reorg state | **Degraded:** manifest already has new paths, so old paths aren't in it. Refs flagged as unresolvable. |
| Multiple reorganise rounds with fix_references between each | Manifest updated after each fix_references run | **Works correctly:** each round sees the right "before" state |

The manifest makes resolution *faster and more complete*, but its absence doesn't break anything. The worst case is that some references are flagged as unresolvable instead of auto-fixed — the user is informed and can resolve manually.

#### Ambiguous Case Improvement

The current system flags hash collisions (same content at multiple paths) as "ambiguous" and gives up. With the manifest, we can do better:
- We know WHICH old path the XML references
- The manifest has that specific path's hash
- Even if multiple current files share that hash, we can suggest the most likely match using path similarity (closest parent directory, similar filename)

This is an improvement over the current blanket "ambiguous" classification, which provides no guidance at all.

#### What fix_references Does to the Manifest

After applying fixes, `fix_references` should update the manifest's path keys for moved files (key rename from old_path to new_path, no re-hashing needed). This keeps the manifest current for subsequent operations and enables multi-round reorganisation.

**This is an optimisation, not a requirement.** If `fix_references` doesn't update the manifest (or crashes mid-update), the next sync will re-hash and correct the manifest anyway. The system is self-healing.

The manifest update is:
- For each moved sample: rename manifest key from old_path to new_path (preserving hash and stat data)
- For each deleted sample: leave in manifest (removal happens naturally on next sync)
- Do NOT re-hash anything — this is a key-rename operation, O(n) in moved files, no I/O

#### Minimal Changes to fix_references

Currently `compute_migration_map()` takes a `before_snapshot: dict` and calls `hash_all_samples(deluge_root)` to build the "after" state. The changes:

| Current | Unified |
|---------|--------|
| "Before": Read snapshot JSON file | "Before": Read manifest, invert to `{hash: [paths]}` (if available) |
| "After": `hash_all_samples()` — hashes ALL ~5500 WAV files (~60–90s) | "After": Scan filesystem, hash only files at NEW paths not in manifest |
| Hash collisions: "ambiguous", give up | Hash collisions: suggest best match via path similarity |
| No manifest update | Update manifest keys for moved files (optimisation) |
| `--snapshot` flag required | No flags needed; reads manifest by default |

The "after" scan can be optimised using the manifest's stat cache: files whose path AND stat match the manifest don't need re-hashing (they haven't moved). Only files at paths not in the manifest need hashing. In practice, if the user moved 50 files, only those 50 get hashed — not 5500.

#### Summary: Snapshot Elimination Verdict

| Question | Answer |
|----------|--------|
| Can the manifest replace snapshots? | **Yes** — and `fix_references` degrades gracefully when the manifest is stale |
| Can we delete `create_snapshot.py`? | **Yes** — no remaining purpose |
| Are ordering constraints needed? | **No** — the system works with any manifest state |
| Are manifest backups needed? | **No** — graceful degradation replaces safety nets |
| What about multi-round reorganisation? | `fix_references` updates manifest keys after each run (optimisation) |

### 6. Sync Algorithm with Content Hashing

#### `sync_from_sd` (SD → local)

For each file on the SD card:

```
1. If file not in local DELUGE/: COPY from SD, hash dest, add to manifest
2. If file in local DELUGE/:
   a. If manifest entry exists with hash:
      - Check SD stat vs manifest sd_*:
        - SD stat changed → COPY from SD (SD modified), re-hash dest, update manifest
        - SD stat unchanged:
          - Check local stat vs manifest local_*:
            - Local stat unchanged → SKIP (fast path, nothing changed)
            - Local stat changed:
              - Compute local hash
              - If local hash == manifest hash → SKIP (mtime drift, update manifest local_* stats)
              - If local hash != manifest hash → COPY from SD (local modified, restore from source of truth)
   b. If manifest entry exists without hash (migration):
      - Compute local hash, store in manifest
      - Fall through to (a) logic with hash available
   c. If no manifest entry:
      - COPY from SD (safe default), hash dest, add to manifest
```

#### `sync_to_sd` (local → SD)

Currently does not use the manifest (`manifest=None` path in `compute_sync()`). The task description's scope includes this script, but the bidirectional question is: should `sync_to_sd` use the manifest?

Analysis: `sync_to_sd` treats the local DELUGE/ as source of truth. It compares local files directly against SD card files via stat. The FAT32 mtime issues apply here (comparing NTFS source against FAT32 dest). Adding manifest support with hashing would improve accuracy for `sync_to_sd` as well.

**Recommendation:** Extend manifest usage to `sync_to_sd` in a follow-up phase. The primary value is for `sync_from_sd` where the false-positive problem is acute. `sync_to_sd` can continue using direct stat comparison initially.

### 7. Cloud Sync Impact

**Source:** [scripts/sync_samples_to_cloud.py](../../scripts/sync_samples_to_cloud.py).

`sync_samples_to_cloud.py` syncs `DELUGE/SAMPLES/` → cloud backup folder. It passes `manifest=None` to `compute_sync()`, which falls back to direct stat comparison. Both sides are NTFS (or same filesystem type), so mtimes are reliable.

**No changes needed.** The cloud sync operates on a separate code path (`manifest is None` in `compute_sync()`) and doesn't suffer from cross-filesystem mtime issues.

If hashing is desired in the future (e.g., to catch same-size cloud corruption), it would be a separate enhancement.

### 8. First-Run / Migration Strategy

#### Migration Path

1. `read_manifest()` detects the manifest format:
   - v2 (has `"version": 2`): Load normally with hashes
   - v1 (has `sd_size`/`sd_mtime`/`local_size`/`local_mtime`, no `"version"`): Load stat data, set `hash=None`
   - Old format (pre-dual-stat): Drop entries (existing behaviour)

2. On first sync after migration:
   - All entries have `hash=None`
   - Every file triggers a stat-cache miss (hash missing)
   - All local files are hashed → manifest updated with hashes
   - **One-time cost: ~60–120 seconds** (SSD, ~5500 WAV + ~2000 XML files)

3. Subsequent syncs:
   - Stat-cache hits for unchanged files → no re-hashing
   - Only files with changed stats are re-hashed
   - Typically <1 second for incremental runs

#### Optimisation: Background Hash Population

To avoid a slow first sync, the migration could be split:
1. A one-time `populate_hashes` command that hashes all local files and updates the manifest
2. The first sync then proceeds at normal speed

This is optional — the first sync simply takes longer, which is acceptable for a one-time event.

### 9. Performance Estimates

**Source:** File counts from [scripts/data/sync_manifest.json](../../scripts/data/sync_manifest.json), SHA-256 performance benchmarks.

#### File Inventory (from manifest)

| Category | Count | Estimated Total Size |
|----------|-------|---------------------|
| WAV files | ~5500 | ~25–30 GB |
| XML files | ~2400 | ~50 MB |
| **Total** | **~7940** | **~25–30 GB** |

#### Hashing Time Estimates

| Scenario | Files to Hash | Time (SSD) | Time (HDD) |
|----------|--------------|-----------|-----------|
| First run (all files) | ~7940 | 60–120s | 5–10 min |
| After git checkout (hundreds of stat changes) | ~200–500 | 2–10s | 10–30s |
| After minor edit | 1–10 | <1s | <1s |
| Snapshot extraction (no hashing) | 0 | <1s | <1s |
| Reference fix (manifest as "before", hash moved files only) | 0–50 (moved files only) | <1s | <1s |

#### Parallelisation Opportunities

The current `hash_file()` implementation is single-threaded. File hashing is I/O bound on most storage:

| Approach | Benefit | Complexity |
|----------|---------|------------|
| `concurrent.futures.ThreadPoolExecutor` | 2–4x speedup on SSD (overlapping I/O with CPU) | Low — drop-in replacement |
| `concurrent.futures.ProcessPoolExecutor` | Marginal over threads (GIL released during C hashlib calls) | Medium |
| Async I/O | Marginal (already I/O bound) | High |
| Single-threaded (current) | Simplest, sufficient for incremental runs | None |

**Recommendation:** Keep single-threaded for the initial implementation. The first-run cost is a one-time event, and incremental runs are already fast. Threading can be added later if profiling shows a need.

### 10. Edge Cases

#### 10.1 Concurrent Deluge Use During Sync

**Scenario:** User is playing the Deluge (which may write to the SD card) while syncing.

**Current behaviour:** No protection. Files could be read mid-write, producing corrupt copies.

**With hashing:** Same risk. Content hashing doesn't help here — a corrupt read produces a corrupt hash.

**Mitigation:** This is a user-responsibility issue, documented in existing workflow guidance ("don't use the Deluge during sync"). No change needed.

#### 10.2 Identical Content, Different Paths (Ambiguous Moves)

**Scenario:** Multiple files have the same content (e.g., a kick sample copied to two kits).

**Current behaviour:** `compute_migration_map()` in `fix_references.py` classifies these as "ambiguous" — `len(before_paths) > 1` or `len(after_paths) > 1`. The user must resolve manually.

**With unified manifest:** Improved. The manifest records which specific old path the broken XML reference points to. Even when multiple current files share the same hash, `fix_references` can suggest the most likely match using path similarity (closest parent directory, similar filename). This converts many "ambiguous" cases into actionable suggestions.

#### 10.3 Stale or Missing Manifest (Graceful Degradation)

**Scenario:** User reorganises samples without ever having synced (no manifest), or after running `sync_from_sd` which overwrote the manifest with current paths.

**Behaviour:** `fix_references` degrades gracefully — broken references that can't be looked up in the manifest are flagged as unresolvable. No data loss, no silent failures. The user is informed and can resolve manually.

This replaces the previous "accidental sync" edge case — it's no longer a special case requiring a backup, it's just the degraded path operating as designed.

#### 10.4 Files That Exist Only on SD (Not Yet Synced)

These files have no manifest entry and no local counterpart. They are always copied on sync (existing behaviour, unchanged). After copying, they get a hash in the manifest.

#### 10.5 Files That Exist Only Locally (Deleted from SD)

These are currently trashed/deleted (existing behaviour, unchanged). The manifest entry is removed.

#### 10.6 Hash Mismatch During Sync (Corruption Detection)

**Bonus capability:** If both SD and local files exist, and both have stat changes, we can hash both and compare. A hash mismatch confirms genuine content change. A hash match (despite stat changes) means the content is identical — skip.

This provides free corruption detection: if the SD file's hash doesn't match the expected hash from a previous sync, something modified it.

## Approaches Considered

### Approach A: Hash-Augmented Dual-Stat Manifest (Recommended)

Add a `hash` field to the existing dual-stat manifest. Use stat data as a fast-path cache (git's approach). Re-hash only on stat-cache miss. Derive snapshot data from manifest.

| Aspect | Detail |
|--------|--------|
| Algorithm | SHA-256 (stdlib, no dependency) |
| Manifest format | v2: existing fields + `"hash"` + `"version": 2` |
| Incremental strategy | Stat cache: `(size, mtime)` match → trust hash |
| Snapshot system | Eliminated — `create_snapshot.py` deleted; `fix_references` degrades gracefully with any manifest state |
| fix_references | Uses manifest-based lookup chain; updates manifest keys after apply (optimisation); no ordering constraints |
| Migration | Transparent: v1 entries loaded with `hash=null`, hashed on first access |

**Pros:**
- Definitive solution to mtime false positives
- Eliminates separate snapshot system's re-hashing cost
- Backward-compatible manifest migration (v1 entries coexist with v2)
- No new dependencies
- Stat cache makes incremental runs fast (<1s)
- Enables future features: corruption detection, deduplication analysis

**Cons:**
- First-run hash computation takes 60–120 seconds
- Manifest JSON grows by ~70 bytes per entry (hash string) — ~550 KB total for ~7940 files
- `compute_sync()` becomes slightly more complex (hash comparison branch)

### Approach B: xxHash with Same Architecture

Same as Approach A but using xxHash (XXH3_128) instead of SHA-256.

**Pros:**
- 10–40x faster CPU hashing (relevant for NVMe SSD users)
- 128-bit digest still has negligible collision probability

**Cons:**
- New dependency (`xxhash` PyPI package)
- Performance gain is marginal in practice (I/O bound on SSD, irrelevant on incremental runs)
- Not cryptographic (less conservative safety margin)

### Approach C: Replace Stat Cache Entirely with Hashing

Drop mtime from all comparisons. Hash every file on every sync. Use only content hashes for change detection.

**Pros:**
- Simplest logic: files either match or don't
- Immune to all timestamp issues by construction

**Cons:**
- Every sync re-hashes all ~7940 files: 60–120 seconds minimum, every time
- Unacceptable UX for a "quick check" sync that should complete in seconds
- Wastes I/O bandwidth reading files that haven't changed

### Approach D: Keep Dual-Stat Manifest, Add Hashing Only for Reference Fixing

Keep the current mtime-based sync as-is. Only add hashing to the manifest for fix_references consumption.

**Pros:**
- Minimal change to sync logic
- Reference fixing gets faster (no re-hashing)

**Cons:**
- Does not solve the mtime false-positive problem (the primary motivation)
- Two systems with different change-detection strategies sharing one manifest
- Hashes in manifest but not used by sync — confusing design

### Comparison

| Criterion | A: SHA-256 + stat cache | B: xxHash + stat cache | C: Hash only | D: Stat + hash for refs |
|-----------|------------------------|------------------------|-------------|------------------------|
| Solves mtime false positives | ✅ | ✅ | ✅ | ❌ |
| No new dependency | ✅ | ❌ | ❌ (if xxHash) or ✅ | ✅ |
| Incremental sync speed | <1s | <1s | 60–120s | <1s (same as current) |
| First-run cost | 60–120s | 50–60s | 60–120s | 60–120s |
| Eliminates snapshot system | ✅ | ✅ | ✅ | ✅ |
| No ordering constraints | ✅ | ✅ | ✅ | ✅ |
| Complexity | Medium | Medium | Low | Low |
| Future-proofing | ✅ (corruption detection, dedup) | ✅ | ✅ | ⚠️ Partial |

## Cross-Cutting Concerns

### Affected Files and Scripts

| File | Impact | Change Summary |
|------|--------|---------------|
| [scripts/deluge_lib/syncing.py](../../scripts/deluge_lib/syncing.py) | **Major** | `FileRecord` gains `hash` field; `compute_sync()` gets hash-comparison branch; `read_manifest()`/`write_manifest()` handle v2 format |
| [scripts/deluge_lib/deluge_sdk.py](../../scripts/deluge_lib/deluge_sdk.py) | **Minor** | `hash_file()` stays where it is (already shared); `hash_all_samples()` may be deprecated |
| [scripts/sync_from_sd.py](../../scripts/sync_from_sd.py) | **Major** | `_build_post_sync_manifest()` computes hashes for copied/new files |
| [scripts/sync_to_sd.py](../../scripts/sync_to_sd.py) | **Minor** | May add manifest support in follow-up phase |
| [scripts/create_snapshot.py](../../scripts/create_snapshot.py) | **Delete** | Entire snapshot system removed; graceful degradation replaces it |
| [scripts/fix_references.py](../../scripts/fix_references.py) | **Major** | `compute_migration_map()` replaced with manifest-based lookup chain; hash collision resolution via path similarity; manifest key update after apply; `--snapshot` flag removed |
| [scripts/sync_samples_to_cloud.py](../../scripts/sync_samples_to_cloud.py) | **None** | Uses `manifest=None` path; unaffected |
| [scripts/deluge_lib/scanning.py](../../scripts/deluge_lib/scanning.py) | **None** | Stat scanning unchanged |
| [scripts/deluge_lib/paths.py](../../scripts/deluge_lib/paths.py) | **None** | Path constants unchanged |
| [scripts/data/sync_manifest.json](../../scripts/data/sync_manifest.json) | **Format change** | Gains `"version": 2` and `"hash"` per entry |

### Shared Resources

- **Manifest file** (`sync_manifest.json`): Now serves sync AND reference-fixing. Concurrent access unlikely (single-user tool) but atomic writes (already implemented) protect against corruption.
- **Hash algorithm**: SHA-256 used by both sync and reference-fixing systems. Changing algorithm requires re-hashing all files.

### SD Card Safety

Per [agent-system/standards/project.md](../../agent-system/standards/project.md):
- Hashing only reads files — no writes to SD card or DELUGE/
- Manifest is written to `scripts/data/` (not DELUGE/)
- No change to SD card safety posture

## Risk Analysis

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| First-run hash computation too slow (>2 min) | Medium | Low — one-time event | Progress indicator; optional pre-population command |
| Manifest file grows too large (~550 KB → ~1.1 MB) | Low | Low — JSON is compact | Monitor; compress if needed (unlikely) |
| SHA-256 CPU bottleneck on NVMe SSD | Low | Low — incremental runs unaffected | Swap to xxHash later if needed (single-function change) |
| Hash mismatch false positive (file modified during hash) | Very Low | Low — retry resolves it | Atomic file reads (already chunked); next sync catches it |
| Manifest corruption (power loss during write) | Very Low | Medium — must re-hash everything | Atomic write already implemented (tempfile + rename) |
| `compute_sync()` complexity increase | Certain | Medium — more code paths to test | Comprehensive test matrix covering all comparison branches |
| Stat cache miss storm after git checkout | Medium | Low — hashing ~200 files takes ~2–5s | Acceptable; much better than copying ~200 files from SD |

## Recommendation

**Approach A: Hash-Augmented Dual-Stat Manifest with SHA-256.**

This is the right level of solution for the problem:

1. **It definitively solves mtime false positives.** Content hashing is immune to every root cause listed: null timestamps, FAT32 truncation, git checkout, extraction scripts, and `shutil.copy2` imprecision. The dual-stat manifest was a step in the right direction but was still fundamentally based on an unreliable signal (mtime) for this specific cross-filesystem, multi-tool environment.

2. **It eliminates the snapshot system entirely.** No separate `create_snapshot` step, no `--snapshot` flag, no dated JSON files, no manifest backups. `fix_references` works with whatever manifest state is available, degrading gracefully when data is stale or missing. The entire reference-fixing workflow drops from ~90 seconds (re-hashing all samples) to <1 second (read manifest + hash only moved files).

3. **It requires no ordering constraints.** The graceful degradation model means users don't need to remember "sync before reorganise before fix_references before sync again". The system produces the best results when the manifest has pre-reorganisation data, but still works correctly (with reduced resolution) when it doesn't.

4. **It uses the right incremental strategy.** The git-inspired stat cache keeps normal sync operations fast (<1 second) while providing accurate content comparison when stats change. This is the proven approach — git has validated it across millions of repositories.

5. **It has the right dependency posture.** SHA-256 via stdlib requires no new dependencies. The performance delta vs xxHash is irrelevant for incremental runs and marginal for the one-time first-run hash. If performance becomes an issue, xxHash can be swapped in with a single-function change.

6. **It future-proofs the system.** Content hashes enable capabilities beyond what's been requested: corruption detection (SD card bit-rot), cross-sync deduplication analysis, and intelligent move detection during sync (not just during reference fixing).

Implementation should proceed in phases:
1. Manifest format (v2 with hash field, migration from v1)
2. Hash computation in sync workflow (hash on stat-cache miss)
3. Updated `compute_sync()` with hash-aware comparison
4. `fix_references.py` redesigned with lookup chain, graceful degradation, and manifest key update
5. Delete `create_snapshot.py`; remove `SNAPSHOTS_DIR`; remove `--snapshot` flag

## Open Questions

1. **Should `sync_to_sd` also use the hash-based manifest?**
   - **Impact:** Would eliminate mtime false positives in the repo→SD direction too
   - **Recommendation:** Defer to a follow-up phase. The primary pain point is `sync_from_sd`. Adding manifest support to `sync_to_sd` is the same pattern but adds scope.
   - **Blocking:** No

2. **Should the manifest hash all files or only WAV files?**
   - **Impact:** XMLs are small (~50 MB total) and quick to hash. Including them provides move detection for XML presets, not just samples.
   - **Recommendation:** Hash all files. The cost is negligible (<1 second for all XMLs), and it enables a complete content-addressed manifest.
   - **Blocking:** No

3. **What's the right `_HASH_CHUNK_SIZE` for SHA-256?**
   - **Impact:** Current value is 64 KB. Larger chunks (256 KB, 1 MB) reduce Python call overhead and improve throughput on SSDs.
   - **Recommendation:** Benchmark with 64 KB, 256 KB, and 1 MB. If 256 KB shows meaningful improvement, use it. Defer to implementation.
   - **Blocking:** No

4. **Should the manifest record the hash algorithm name (e.g., `"hash_algo": "sha256"`)?**
   - **Impact:** Enables future algorithm migration without re-hashing everything
   - **Recommendation:** Yes — add `"hash_algo": "sha256"` to the manifest header. Low cost, high future value.
   - **Blocking:** No

5. **How should path similarity scoring work for ambiguous hash matches?**
   - **Impact:** When multiple current files share a hash, `fix_references` needs to suggest the best match for a broken reference. Path similarity (common parent directory, similar filename) is the proposed heuristic.
   - **Recommendation:** Defer exact algorithm to planning. Simple heuristic: prefer files in the same parent directory, then by longest common path prefix.
   - **Blocking:** No

### Resolved Questions

| Question | Resolution |
|----------|-----------|
| Should snapshots remain as separate files? | **No** — entire snapshot system deleted, replaced by graceful degradation |
| Are ordering constraints needed? | **No** — `fix_references` works with any manifest state |
| Should `sync_from_sd` auto-backup the manifest? | **No** — graceful degradation eliminates the need for safety-net backups |
| Should `fix_references` update the manifest? | **Yes**, as an optimisation (enables multi-round reorg), but not a hard requirement |
| Should `fix_references` derive "after" state from filesystem or manifest? | **Filesystem** — scan current state, hash only files at new paths not in manifest |
| What about the `--snapshot` flag? | **Remove** — no backward compatibility needed; `fix_references` reads the manifest by default |

## References

### Project Files
- [scripts/deluge_lib/syncing.py](../../scripts/deluge_lib/syncing.py) — `compute_sync()`, `FileRecord`, `read_manifest()`, `write_manifest()`, `_mtime_matches()`
- [scripts/deluge_lib/scanning.py](../../scripts/deluge_lib/scanning.py) — `scan_tree()`, `FileEntry`, `normalise_mtime()`
- [scripts/deluge_lib/deluge_sdk.py](../../scripts/deluge_lib/deluge_sdk.py) — `hash_file()`, `hash_all_samples()`
- [scripts/deluge_lib/paths.py](../../scripts/deluge_lib/paths.py) — `SYNC_MANIFEST_PATH`, `SNAPSHOTS_DIR`
- [scripts/sync_from_sd.py](../../scripts/sync_from_sd.py) — `_build_post_sync_manifest()`, SD→local sync
- [scripts/sync_to_sd.py](../../scripts/sync_to_sd.py) — Local→SD sync
- [scripts/sync_samples_to_cloud.py](../../scripts/sync_samples_to_cloud.py) — Cloud backup (unaffected)
- [scripts/create_snapshot.py](../../scripts/create_snapshot.py) — Current snapshot creation (to be deleted)
- [scripts/fix_references.py](../../scripts/fix_references.py) — `compute_migration_map()`, `classify_ref_changes()`
- [scripts/data/sync_manifest.json](../../scripts/data/sync_manifest.json) — Current dual-stat manifest
- [scripts/pyproject.toml](../../scripts/pyproject.toml) — Dependencies, entry points
- [scripts/tests/test_syncing.py](../../scripts/tests/test_syncing.py) — Sync comparison tests
- [scripts/tests/test_fix_references.py](../../scripts/tests/test_fix_references.py) — Reference fixer tests
- [scripts/tests/test_create_snapshot.py](../../scripts/tests/test_create_snapshot.py) — Snapshot tests (to be deleted with snapshot system)

### Prior Research and Plans
- [docs/research/manifest-sync-comparison-research.md](manifest-sync-comparison-research.md) — Dual-stat manifest research (the predecessor to this work)
- [docs/plans/dual-stat-manifest-plan.md](../plans/dual-stat-manifest-plan.md) — Dual-stat manifest implementation plan (complete)
- [docs/research/scripts-codebase-review-research.md](scripts-codebase-review-research.md) — Codebase review identifying hash_file sharing opportunity
- [docs/research/sample-scripts-research.md](sample-scripts-research.md) — Original sample scripts research
- [docs/hashing-eli5.md](../hashing-eli5.md) — User-facing hashing explanation

### External Resources
- [git-scm.com/docs/index-format](https://git-scm.com/docs/index-format) — Git index format specification (stat-cache design reference)
- [git-scm.com/docs/racy-git](https://git-scm.com/docs/racy-git) — Git's "racy clean" problem and timestamp-based cache invalidation
- [xxhash.com](https://xxhash.com/) — xxHash benchmarks showing SHA-256 at ~0.5 GB/s vs XXH3 at ~31.5 GB/s
- [github.com/ifduyue/python-xxhash](https://github.com/ifduyue/python-xxhash) — Python xxhash bindings (v3.7.0, hashlib-compatible API)

## Next Steps

1. Review this document and resolve any blocking open questions
2. Invoke the Plan agent to create a feature plan from this research
