# Research: Manifest Sync Comparison Logic

> **Document Type:** Research
> **Date:** 02 May 2026
> **Request:** The `sync_from_sd.py` manifest logic compares SD stats against the manifest only, silently skipping files when the local repo has diverged. Research the problem and evaluate solutions that uphold the core sync principle: after sync, DELUGE/ must exactly match the SD card.
> **Pipeline:** Research → Plan → Implement

## Executive Summary

The current `sync_from_sd.py` manifest was introduced to solve a real problem — FAT32-to-NTFS `shutil.copy2` mtime drift causing ~287 false-positive re-copies every sync. However, the manifest-only comparison creates a blind spot: local changes to `DELUGE/` (from extraction scripts, git operations, or manual edits) are never detected because the check asks "has the SD card changed since last sync?" instead of "does `DELUGE/` match the SD card?". This research evaluates five solution approaches; the recommended direction is a **two-source comparison** (SD vs manifest AND local vs manifest) that preserves the manifest's mtime-drift protection while restoring local-drift detection.

## Objectives

- Document the full data flow of the current manifest system (`compute_sync`, `_read_manifest`, `_write_manifest`, `_build_post_sync_manifest`)
- Identify exactly where and why the current logic fails to uphold the sync principle
- Evaluate at least four candidate solutions with concrete tradeoffs
- Walk each solution through four real-world scenarios
- Assess performance impact across ~7,940 files (large WAVs + small XMLs)
- Assess implementation complexity and reuse of existing code

## Feature Overview

### Purpose and Value

`sync_from_sd.py` is the primary backup tool: it copies new/changed files from a mounted Deluge SD card into the local `DELUGE/` directory and trashes files that no longer exist on the SD card. The core sync principle is:

> **After `sync_from_sd` completes, `DELUGE/` must exactly match the SD card.**

The SD card is the source of truth. Any divergence between `DELUGE/` and the SD card after a sync is a bug.

### Why the Manifest Exists

Through real testing, the user discovered that `shutil.copy2` from FAT32 (SD card) to NTFS (local filesystem) does **not** faithfully preserve modification times. Even immediately after a successful sync:

- **With manifest**: `sync → sync` = "Already up to date" ✅
- **Without manifest**: `sync → sync` = 287 files flagged for re-copy ❌
- **Without manifest**: `sync → do nothing → sync` = same 287 files always flagged ❌

The manifest records the SD card's own stats at sync time, creating a reliable "has the SD card changed?" signal that is immune to cross-filesystem mtime drift.

### Scope

- **In scope:** The comparison logic in `compute_sync()` and the manifest read/write lifecycle in `sync_from_sd.py`
- **Out of scope:** `sync_to_sd.py` and `sync_samples_to_cloud.py` (they pass `manifest=None` and are unaffected), the `.trash` system, the scan/filter layer

## Existing Assets Analysis

| Capability | Status | Location | Notes |
|------------|--------|----------|-------|
| File scanning with stat capture | ✅ Ready | [scripts/deluge_lib/scanning.py](../../scripts/deluge_lib/scanning.py) | `scan_tree()` returns `ScanResult` with `FileEntry(rel_path, size, mtime)` per file; mtime is already normalised to FAT32 2-second grid via `normalise_mtime()` |
| Sync plan computation | ⚠️ Partial | [scripts/deluge_lib/syncing.py](../../scripts/deluge_lib/syncing.py) | `compute_sync()` has the manifest parameter but its comparison block is currently commented out — falls back to direct dest stat comparison |
| FAT32 mtime tolerance | ✅ Ready | [scripts/deluge_lib/syncing.py](../../scripts/deluge_lib/syncing.py) | `_mtime_matches()` allows ±2 second tolerance; `normalise_mtime()` truncates to 2-second grid |
| Manifest read/write | ✅ Ready | [scripts/sync_from_sd.py](../../scripts/sync_from_sd.py) | `_read_manifest()` / `_write_manifest()` with atomic writes, corruption handling |
| Post-sync manifest build | ✅ Ready | [scripts/sync_from_sd.py](../../scripts/sync_from_sd.py) | `_build_post_sync_manifest()` handles copied, unchanged, trashed, and filtered-sync carry-forward |
| Manifest path constant | ✅ Ready | [scripts/deluge_lib/paths.py](../../scripts/deluge_lib/paths.py) | `MANIFEST_PATH = DATA_DIR / "manifest.json"` |
| Test coverage for manifest | ✅ Ready | [scripts/tests/test_sync_from_sd.py](../../scripts/tests/test_sync_from_sd.py) | Tests for `_read_manifest`, `_write_manifest`, `_build_post_sync_manifest` |
| Test coverage for compute_sync | ⚠️ Partial | [scripts/tests/test_syncing.py](../../scripts/tests/test_syncing.py) | Manifest tests exist but test the OLD behaviour (SD vs manifest only); no tests for local-drift detection |
| Hashing utilities | ❌ Missing | — | No content hashing exists in the codebase; `fix_references.py` uses SHA256 for samples but via `create_snapshot.py`, not in the sync path |

## Findings

### 1. Current Data Flow

The full lifecycle of a `sync_from_sd` run:

```
1. _read_manifest(MANIFEST_PATH)
   → (timestamp: str, manifest_files: dict[key → {size, mtime}])
   → Empty on first run or corrupt file

2. compute_sync(sd_path, deluge_root, manifest=manifest_files, file_filter=...)
   → scan_tree(sd_path)     → src_scan.files: dict[key → FileEntry]
   → scan_tree(deluge_root) → dst_scan.files: dict[key → FileEntry]
   → For each key in src_scan:
       - Not in dst_scan? → copy (new file)
       - In dst_scan? → compare SD stats vs comparison target → copy or skip
   → For each key in dst_scan not in src_scan: → trash
   → Returns (SyncPlan, src_scan)

3. execute_plan(plan, dest=deluge_root)
   → Copies files, trashes extras
   → Returns SyncResult

4. _build_post_sync_manifest(plan, src_scan, deluge_root, manifest_files, file_filter)
   → Copied files: records SD-side stats (size, mtime) from src_scan
   → Unchanged files with manifest entry: preserves old manifest entry
   → Unchanged files without manifest entry: uses SD-side stats
   → Trashed files: omitted
   → Filtered sync: carries forward entries for unscanned file types
   → Returns (timestamp, new_files)

5. _write_manifest(manifest_path, timestamp=..., files=new_files)
   → Atomically writes JSON to scripts/data/manifest.json
```

**Source:** [scripts/deluge_lib/syncing.py](../../scripts/deluge_lib/syncing.py) lines 108–174, [scripts/sync_from_sd.py](../../scripts/sync_from_sd.py) lines 44–165.

### 2. The Comparison Block (Current State — Manifest Commented Out)

The comparison logic in `compute_sync()` currently reads:

```python
# Choose comparison target: manifest entry if it exists, otherwise use destination stat
# if manifest is not None and key in manifest:
#     cmp_size: int = manifest[key]["size"]
#     cmp_mtime: float = manifest[key]["mtime"]
# else:
cmp_size = dst_entry.size
cmp_mtime = normalise_mtime(dst_entry.mtime)

if src_entry.size != cmp_size:
    plan.files_to_copy.append((src_path, dst_path))
elif not _mtime_matches(src_entry.mtime, cmp_mtime):
    plan.files_to_copy.append((src_path, dst_path))
else:
    plan.files_unchanged += 1
```

**Source:** [scripts/deluge_lib/syncing.py](../../scripts/deluge_lib/syncing.py) lines 148–163.

With the manifest commented out, the code falls back to direct SD-vs-local stat comparison, which re-introduces the 287-file false-positive problem.

### 3. The Original Manifest Logic (Before Commenting Out)

When the manifest block was active, the comparison was:

```python
if manifest is not None and key in manifest:
    cmp_size = manifest[key]["size"]
    cmp_mtime = manifest[key]["mtime"]
else:
    cmp_size = dst_entry.size
    cmp_mtime = normalise_mtime(dst_entry.mtime)
```

This compared **SD stats against the manifest only**. The local file's actual stats were never checked when a manifest entry existed. The question being asked was:

> "Has the SD card changed since the last sync?"

The question that **should** also be asked is:

> "Has the local file changed since the last sync?"

### 4. The Gap — Concrete Failure Scenario

**Scenario:** `sync → extract_instruments.py modifies XMLs in DELUGE/ → sync`

1. **First sync:** SD card has `KITS/MyKit.XML` (size=500, mtime=1700000000). File is copied to `DELUGE/KITS/MyKit.XML`. Manifest records `{"size": 500, "mtime": 1700000000}`.

2. **Extraction script runs:** `extract_instruments.py` modifies `DELUGE/KITS/MyKit.XML` — the local file now has size=520 and a new mtime. The SD card is unchanged.

3. **Second sync:** `compute_sync()` checks SD stats (size=500, mtime=1700000000) against manifest (size=500, mtime=1700000000). They match → **skip**. The local file's actual content (size=520) is never checked.

4. **Result:** `DELUGE/KITS/MyKit.XML` has content that differs from the SD card. The sync principle is violated. The user sees "Already up to date" — a silent lie.

This same gap applies to:
- `git checkout` or `git stash` altering files in `DELUGE/`
- Manual edits to XML files in `DELUGE/`
- Any tool that modifies `DELUGE/` contents between syncs

### 5. What the Manifest Records

Examining `_build_post_sync_manifest()`:

- **Copied files:** Records the **source (SD card) stats** — `src_entry.size` and `src_entry.mtime` from the source scan
- **Unchanged files with prior entry:** Preserves the **old manifest entry** (which was also SD-side stats)
- **Unchanged files without entry (first run):** Records **SD-side stats**

The manifest therefore always stores **SD card stats at the time of last sync**. It never records local stats. This is the correct design for answering "has SD changed?" but insufficient for answering "has local drifted?".

**Source:** [scripts/sync_from_sd.py](../../scripts/sync_from_sd.py) lines 111–148.

### 6. Cross-Script Impact

| Script | Uses `compute_sync` | Uses manifest | Affected by this change |
|--------|---------------------|---------------|------------------------|
| `sync_from_sd.py` | Yes | Yes (`manifest=manifest_files`) | **Yes** — this is the target |
| `sync_to_sd.py` | Yes | No (`manifest` not passed, defaults via positional) | No — compares `DELUGE/` vs SD directly |
| `sync_samples_to_cloud.py` | Yes | No (`manifest=None`) | No — compares `DELUGE/SAMPLES/` vs cloud backup directly |

**Source:** [scripts/sync_to_sd.py](../../scripts/sync_to_sd.py) line 172 (`compute_sync(deluge_root, sd_path, file_filter=file_filter)` — no manifest arg), [scripts/sync_samples_to_cloud.py](../../scripts/sync_samples_to_cloud.py) line 49 (`manifest=None`).

### 7. The FAT32→NTFS Mtime Drift Problem (Detail)

The root cause: FAT32 stores mtimes with 2-second granularity. When `shutil.copy2` copies a file from FAT32 to NTFS, the mtime is set on the NTFS filesystem, but the value doesn't round-trip perfectly. Even with `normalise_mtime()` truncating to the 2-second grid, ~287 out of ~7,940 files consistently show mtime discrepancies beyond the ±2-second tolerance.

This is a known cross-filesystem issue. The drift is consistent (the same 287 files always differ), suggesting it's a systematic rounding/representation issue rather than random jitter.

### 8. Performance Context

From the user's workspace:
- Total files: ~7,940 (based on user testing)
- WAV files: large (recordings, resamples — can be tens or hundreds of MB each)
- XML files: small (typically 1–100 KB)
- Current scan time: fast (stat-only, no content reading)
- SHA256 of all WAVs: would be very slow (reading potentially gigabytes of data)
- SHA256 of all XMLs: fast (small files, likely <50 MB total)

## Approaches Considered

### Approach A: Two-Source Comparison (SD vs Manifest AND Local vs Manifest)

**How it works:** The manifest continues to record SD-side stats. When comparing, check **two** conditions:
1. SD stats vs manifest → "Has the SD card changed?"
2. Local stats vs manifest → "Has the local file drifted?"

If **either** check indicates a difference, copy the file from SD.

**Implementation:**

```python
if manifest is not None and key in manifest:
    m_size = manifest[key]["size"]
    m_mtime = manifest[key]["mtime"]
    
    sd_changed = (src_entry.size != m_size or not _mtime_matches(src_entry.mtime, m_mtime))
    local_drifted = (dst_entry.size != m_size or not _mtime_matches(normalise_mtime(dst_entry.mtime), m_mtime))
    
    if sd_changed or local_drifted:
        plan.files_to_copy.append((src_path, dst_path))
    else:
        plan.files_unchanged += 1
else:
    # No manifest entry — fall back to direct SD vs local comparison
    cmp_size = dst_entry.size
    cmp_mtime = normalise_mtime(dst_entry.mtime)
    # ... existing size/mtime comparison
```

**But there's a problem with the local mtime check:** The same FAT32→NTFS mtime drift that necessitated the manifest in the first place means `dst_entry.mtime` may not match `manifest[key]["mtime"]` even for unmodified files. The manifest stores SD-side stats, but the local file was copied via `shutil.copy2` which introduces drift.

**Mitigation options for local mtime drift:**

- **Option A1:** Store **both** SD-side stats and local-side stats in the manifest. After copying, stat the destination file and record its actual mtime alongside the SD mtime. The local-drift check then compares local stat vs stored local stat — no cross-filesystem comparison needed.
- **Option A2:** Use size-only for the local drift check (skip mtime). Same-size edits would be missed, but this is a pragmatic tradeoff — most meaningful edits change file size.

### Approach B: Size-Only Comparison (No Mtime)

**How it works:** Remove mtime from all comparisons. Compare only file sizes between SD and local. Drop the manifest entirely.

**Pros:**
- Simplest possible implementation
- No manifest to maintain
- No cross-filesystem mtime issues
- Immune to git operations changing mtimes

**Cons:**
- Misses edits that don't change file size (e.g. changing a parameter value in an XML from `50` to `60`, or replacing a WAV with a same-length recording)
- Same-size-different-content is uncommon but possible, especially for XML edits

**Performance:** Very fast — no content reading, no manifest I/O.

### Approach C: Hash-Based Comparison

**How it works:** Compute SHA256 (or similar) of both SD and local files. Copy if hashes differ. No manifest needed — content comparison is always accurate.

**Pros:**
- 100% accurate content comparison
- No false positives or false negatives
- No mtime issues at all
- No manifest to maintain

**Cons:**
- **Performance:** Must read the full content of every file on both sides for every sync. With ~7,940 files including large WAVs (potentially gigabytes total), this could take minutes rather than seconds.
- I/O-heavy: reads from both SD card (slow USB/card reader) and local disk

**Performance estimate:** If the SD card has ~5 GB of content, reading all files from the SD card (typical SD card reader: ~30 MB/s) would take ~170 seconds just for the read pass. Local SSD reads would be fast. Total: likely 2–4 minutes per sync, even when nothing changed.

### Approach D: Hybrid — Size + Mtime for WAVs, Hash for XMLs

**How it works:**
- **WAV files:** Use size + mtime comparison (with manifest for mtime). WAVs are large and rarely edited in the repo — the risk of same-size-different-content is minimal.
- **XML files:** Use SHA256 comparison. XMLs are small (fast to hash) and are the files most likely to be modified locally (by extraction scripts, git operations, manual edits).

**Pros:**
- Accurate where it matters most (XMLs)
- Fast where accuracy matters least (WAVs)
- Hashing ~50 MB of XMLs is fast (~1 second)

**Cons:**
- Two different comparison strategies adds complexity
- Still needs manifest for WAV mtime (or tolerates the 287-file re-copy for WAVs)
- WAV files could theoretically be edited locally (user resamples, then a script processes them), though this is rare

**Performance:** Fast for typical case. XML hashing adds ~1 second. WAV comparison remains stat-only.

### Approach E: Two-Source Manifest with Dual Stats (Recommended Variant of A)

**How it works:** Extend the manifest to store **two sets of stats** per file:
- `sd_size`, `sd_mtime` — the SD card's stats at sync time
- `local_size`, `local_mtime` — the destination file's actual stats after `shutil.copy2` completes

Comparison logic:
1. Compare SD stats vs `sd_*` in manifest → "Has SD changed?"
2. Compare local stats vs `local_*` in manifest → "Has local file been modified?"
3. Copy if either differs.

**Why this solves the mtime drift problem:** The local-drift check compares NTFS stat vs stored NTFS stat (both from the same filesystem). No cross-filesystem comparison occurs. The 287-file drift issue is eliminated because the manifest records what the local file's mtime actually ended up as, not what it should have been.

**Manifest format change:**

```json
{
  "last_sync_timestamp": "2026-05-02T10:00:00+00:00",
  "files": {
    "kits/mykit.xml": {
      "sd_size": 500,
      "sd_mtime": 1700000000.0,
      "local_size": 500,
      "local_mtime": 1700000002.0
    }
  }
}
```

**Implementation changes required:**
1. `_build_post_sync_manifest()` — after copying, stat the destination file and record both SD and local stats
2. `compute_sync()` — add local-drift check when manifest entry exists
3. `_read_manifest()` / `_write_manifest()` — handle new field names
4. Manifest migration: gracefully handle old-format manifests (fall back to SD-only check if `local_*` fields are missing)

| Approach | Pros | Cons | Complexity |
|----------|------|------|------------|
| **A: Two-source (SD-side stats only)** | Detects local drift; preserves mtime-drift protection for SD | Local mtime drift causes false positives (~287 files) unless mitigated via A1 or A2 | Medium |
| **B: Size-only** | Simplest; no manifest needed | Misses same-size edits | Low |
| **C: Hash-based** | 100% accurate; no manifest | Very slow for large WAV files (~2–4 min per sync) | Low (code) / High (runtime) |
| **D: Hybrid (hash XML, stat WAV)** | Accurate for XMLs; fast for WAVs | Two strategies; still needs manifest for WAVs | Medium-High |
| **E: Two-source with dual stats** | Detects local drift accurately; no cross-filesystem mtime comparison; no false positives | Manifest format change; slightly more complex manifest build | Medium |

## Scenario Walkthroughs

### Scenario 1: `sync → do nothing → sync` (Idempotent Re-Run)

| Approach | Behaviour | Correct? |
|----------|-----------|----------|
| **A (SD-side only)** | SD vs manifest: match. Local vs manifest: ~287 mtime mismatches → re-copies 287 files | ❌ False positives |
| **A1 (dual stats)** → same as **E** | SD vs manifest: match. Local vs manifest (NTFS vs NTFS): match | ✅ |
| **A2 (size-only local)** | SD vs manifest: match. Local size vs manifest size: match | ✅ |
| **B (size-only)** | SD size vs local size: match | ✅ |
| **C (hash)** | SD hash vs local hash: match (content identical) | ✅ |
| **D (hybrid)** | XML hashes match; WAV size+mtime: 287 WAV false positives (or correct if WAVs use manifest) | ⚠️ Depends on WAV strategy |
| **E (dual stats)** | SD vs sd_manifest: match. Local vs local_manifest: match | ✅ |

### Scenario 2: `sync → edit file on SD card → sync` (SD Change Detection)

| Approach | Behaviour | Correct? |
|----------|-----------|----------|
| **A/A1/A2/E** | SD vs manifest: size or mtime differs → copy | ✅ |
| **B** | SD size vs local size: differs (if size changed) or matches (if same-size edit) | ⚠️ Misses same-size edits |
| **C** | SD hash vs local hash: differs → copy | ✅ |
| **D** | Hash (XML) or stat (WAV) detects change | ✅ for XML, ⚠️ for same-size WAV edits |

### Scenario 3: `sync → edit file in repo → sync` (Local Drift Correction)

This is the critical scenario that the current manifest logic fails.

| Approach | Behaviour | Correct? |
|----------|-----------|----------|
| **Current (manifest commented out)** | SD vs local: mtime differs due to edit → copies ✅, but also 287 false positives ❌ | ⚠️ |
| **Current (original manifest active)** | SD vs manifest: match → **skip** | ❌ Silent divergence |
| **A (SD-side only)** | SD vs manifest: match. Local vs manifest: size or mtime differs → copy | ✅ |
| **A2 (size-only local)** | SD vs manifest: match. Local size vs manifest size: differs (if size changed) → copy | ⚠️ Misses same-size local edits |
| **B** | SD size vs local size: differs (if size changed) | ⚠️ Misses same-size local edits |
| **C** | SD hash vs local hash: differs → copy | ✅ |
| **D** | Hash catches XML drift; stat catches WAV size change | ✅ for XML, ⚠️ for same-size WAV edits |
| **E (dual stats)** | SD vs sd_manifest: match. Local vs local_manifest: size or mtime differs → copy | ✅ |

### Scenario 4: `sync → edit same file on both SD and repo → sync` (Conflict)

Note: None of these approaches implement conflict detection — the SD card is always the source of truth, so the SD version wins.

| Approach | Behaviour | Correct? |
|----------|-----------|----------|
| **A/E** | SD vs manifest: differs → copy. (Local change is silently overwritten — correct per sync principle) | ✅ |
| **B** | SD size vs local size: may or may not differ | ⚠️ Could miss if both edits result in same size |
| **C** | SD hash vs local hash: differs → copy | ✅ |
| **D** | Depends on file type | ⚠️ |

## Cross-Cutting Concerns

### Manifest Format Migration

If Approach E is adopted, the manifest format changes from `{size, mtime}` to `{sd_size, sd_mtime, local_size, local_mtime}`. Existing manifests will have the old format. The implementation must:
- Detect old-format entries (check for `sd_size` vs `size` keys)
- Gracefully degrade: treat old entries as SD-only (equivalent to current behaviour for those files — they'll be re-synced on next run, which refreshes the manifest)
- Or: treat a format mismatch as "no manifest" for that file, triggering a fresh comparison and re-recording

### `_build_post_sync_manifest()` Changes

Currently, for copied files, the function records SD-side stats from `src_scan`. With dual stats, it would need to also stat the destination file **after copying** to get the actual local mtime. This means the manifest build step moves from a pure scan-data operation to one that touches the filesystem.

Two options:
1. Stat each copied file inside `_build_post_sync_manifest()` (simple but adds filesystem access to what was a pure-data function)
2. Have `execute_plan()` collect and return the destination stats for copied files, then pass them into the manifest builder (cleaner separation but more plumbing)

### Test Impact

Existing tests in [scripts/tests/test_syncing.py](../../scripts/tests/test_syncing.py) cover the manifest comparison path (`TestComputeSyncManifest`), but they test the **old** behaviour (SD vs manifest only). These tests would need updating to verify the two-source comparison. New test cases needed:
- Local file modified (size change) → detected
- Local file modified (mtime change only) → detected
- Local file unchanged → not flagged (no false positives from NTFS mtime)
- Both SD and local changed → copy from SD

### Filtered Sync (`--xml` / `--wav`)

`_build_post_sync_manifest()` already handles filtered syncs by carrying forward entries for unscanned file types. This behaviour must be preserved. With dual stats, carried-forward entries retain their existing format — they won't have fresh `local_*` values, but they also aren't being compared, so this is safe.

### Other Scripts

`sync_to_sd.py` and `sync_samples_to_cloud.py` pass `manifest=None`. The changes to `compute_sync()` must preserve the `manifest is None` code path exactly as-is. Since these scripts don't use the manifest at all, they are unaffected by manifest format changes.

## Risk Analysis

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Dual-stat manifest introduces false positives from NTFS mtime jitter between runs | Low | Medium — unnecessary re-copies | Store local mtime from the actual `stat()` after copy; same-filesystem comparison eliminates cross-FS drift |
| Migration from old manifest format causes one-time full re-sync | Medium | Low — one-time cost, ~7,940 files, ~5 minutes | Acceptable; document in release notes. Alternatively, run a one-time migration script |
| `_build_post_sync_manifest()` accessing filesystem (to stat copied files) fails mid-way | Low | Medium — manifest not updated, next sync re-copies | Already handled: manifest is only written after `_build_post_sync_manifest()` completes; failure leaves old manifest intact |
| Local mtime changes from antivirus scans, indexers, or backup tools | Low | Low — triggers re-copy of unchanged content | Harmless (SD is source of truth; re-copying identical content is wasteful but not incorrect) |
| Same-size edits missed by Approach B/A2 | Medium (for XMLs) | High — silent divergence | Avoid size-only approaches for XMLs, or accept the trade-off explicitly |

## Recommendation

**Approach E: Two-Source Manifest with Dual Stats** is recommended.

**Rationale:**

1. **Correctness:** It detects both SD changes and local drift with no known blind spots (unlike size-only approaches that miss same-size edits).

2. **Performance:** No content hashing needed. The only additional cost is stat-ing destination files after copying — which is negligible since we just wrote them. Re-run idempotency is preserved (no false positives) because local mtime comparison is NTFS-to-NTFS, eliminating the FAT32 drift issue.

3. **Consistency:** Keeps `compute_sync()` as a stat-based comparison engine — no file content is read during plan computation. This preserves the current architecture's separation of concerns (scan → plan → execute).

4. **Simplicity relative to alternatives:** Approach D (hybrid) requires two different comparison strategies and is harder to reason about. Approach C (hash) has unacceptable performance cost for WAVs. Approach B (size-only) has accuracy gaps for XMLs.

5. **Backward compatibility:** Old manifests degrade gracefully — files with old-format entries are re-synced (worst case: one full re-sync), which also refreshes the manifest to the new format.

6. **Existing code reuse:** `_mtime_matches()`, `normalise_mtime()`, `scan_tree()`, and the manifest I/O functions all remain relevant. The changes are contained to the comparison block in `compute_sync()`, the manifest builder, and the manifest format.

**Trade-off acknowledged:** Approach E still relies on mtime for change detection, which means hypothetical scenarios where a file is modified but its mtime is restored (e.g. `touch -t`) would be missed. This is acceptable — such scenarios are adversarial rather than realistic.

## Open Questions

1. **Should `execute_plan()` return destination stats for copied files, or should `_build_post_sync_manifest()` stat them itself?**
   - **Impact:** Architectural cleanliness vs implementation simplicity. If `execute_plan()` returns stats, the manifest builder stays pure. If the builder stats files itself, less plumbing but the function gains filesystem access.
   - **Recommendation:** Have `_build_post_sync_manifest()` stat the files itself — it's simpler, and the function already receives `dest` as a parameter. The purity concern is minor given this function is already specific to `sync_from_sd`.
   - **Blocking:** No — either approach works.

2. **Should old-format manifest entries trigger a re-copy or be treated as "unchanged with degraded confidence"?**
   - **Impact:** Determines whether adopting Approach E causes a one-time full re-sync (~7,940 files).
   - **Recommendation:** Treat old-format entries as having no local stats → local-drift check triggers → file is re-copied → manifest is refreshed. A one-time re-sync is the safest approach and takes only a few minutes.
   - **Blocking:** No — the one-time cost is acceptable.

3. **Should `normalise_mtime()` be applied to local stats before storing in manifest?**
   - **Impact:** NTFS mtimes have sub-second precision; FAT32 mtimes don't. If we store raw NTFS mtimes and compare against raw NTFS mtimes, the comparison is consistent. Normalising would lose information.
   - **Recommendation:** Do **not** normalise local mtimes — store and compare raw NTFS values. Normalisation is only needed for cross-filesystem comparisons (the SD side), which the dual-stat approach eliminates for the local check.
   - **Blocking:** No.

4. **Should the manifest also store content hashes for XMLs as a future enhancement?**
   - **Impact:** Would provide a belt-and-suspenders check for XML integrity. Low cost (~1 second for all XMLs).
   - **Recommendation:** Defer to a future iteration. The dual-stat approach is sufficient for the current problem. Hashes can be added later without changing the comparison architecture.
   - **Blocking:** No.

## References

### Project Files
- [scripts/deluge_lib/syncing.py](../../scripts/deluge_lib/syncing.py) — `compute_sync()`, `_mtime_matches()`, `execute_plan()`, `SyncPlan`, `SyncResult`
- [scripts/sync_from_sd.py](../../scripts/sync_from_sd.py) — `_read_manifest()`, `_write_manifest()`, `_build_post_sync_manifest()`, `main()`
- [scripts/deluge_lib/scanning.py](../../scripts/deluge_lib/scanning.py) — `scan_tree()`, `normalise_mtime()`, `FileEntry`, `ScanResult`
- [scripts/deluge_lib/paths.py](../../scripts/deluge_lib/paths.py) — `MANIFEST_PATH`
- [scripts/sync_to_sd.py](../../scripts/sync_to_sd.py) — Uses `compute_sync()` without manifest
- [scripts/sync_samples_to_cloud.py](../../scripts/sync_samples_to_cloud.py) — Uses `compute_sync()` with `manifest=None`
- [scripts/tests/test_syncing.py](../../scripts/tests/test_syncing.py) — Existing manifest comparison tests
- [scripts/tests/test_sync_from_sd.py](../../scripts/tests/test_sync_from_sd.py) — Manifest I/O and post-sync build tests
- [docs/scripts-plan.md](../../docs/scripts-plan.md) — Original script design document

## Next Steps

1. Review this document and resolve any blocking open questions
2. Invoke the Plan agent to create a feature plan from this research
