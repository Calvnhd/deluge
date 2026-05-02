# Research: Manifest Sync Comparison Logic

> **Document Type:** Research
> **Date:** 02 May 2026
> **Request:** Fix `sync_from_sd.py` so that after sync completes, `DELUGE/` exactly matches the SD card — the manifest must detect both SD-side changes and local-side drift.
> **Pipeline:** Research → Plan → Implement

## Executive Summary

The `sync_from_sd.py` manifest has a specific, verified root cause: the Deluge firmware writes factory presets to FAT32 **without setting timestamps** (null/zero mtime). When Python reads these on Windows, the null FAT32 timestamp becomes `-11644473600.0` (January 1, 1601). `shutil.copy2` cannot preserve this on NTFS, so it falls back to the current time — creating a permanent mtime mismatch affecting ~287 of ~7940 files. The manifest was introduced to suppress these false positives, but it only checks "has the SD card changed?" and never checks "has the local file drifted?". The fix is a **dual-stat manifest** that stores both the SD mtime and the actual local mtime after copy, enabling both checks without cross-filesystem comparison.

## Objectives

- Document the verified root cause (null FAT32 timestamps) with real data
- Show exactly how the current manifest comparison creates a blind spot
- Evaluate focused solution approaches with scenario walkthroughs
- Recommend the simplest correct solution

## Feature Overview

### The Core Principle

> **After `sync_from_sd` completes, `DELUGE/` must exactly match the SD card.**

The SD card is the source of truth. Any divergence after sync is a bug.

### Scope

- **In scope:** `compute_sync()` comparison logic, manifest format and lifecycle
- **Out of scope:** `sync_to_sd.py`, `sync_samples_to_cloud.py` (pass `manifest=None`), the `.trash` system, the scan/filter layer

## Existing Assets Analysis

| Capability | Status | Location | Notes |
|------------|--------|----------|-------|
| File scanning with stat capture | ✅ Ready | [scripts/deluge_lib/scanning.py](../../scripts/deluge_lib/scanning.py) | `scan_tree()` returns `FileEntry(rel_path, size, mtime)`; mtime normalised via `normalise_mtime()` |
| Sync plan computation | ⚠️ Partial | [scripts/deluge_lib/syncing.py](../../scripts/deluge_lib/syncing.py) | `compute_sync()` has manifest parameter but comparison block is **commented out** — falls back to direct SD-vs-local stat |
| FAT32 mtime helpers | ✅ Ready | [scripts/deluge_lib/syncing.py](../../scripts/deluge_lib/syncing.py) | `_mtime_matches()` (±2s tolerance), `normalise_mtime()` (2s grid truncation) |
| Manifest I/O | ✅ Ready | [scripts/sync_from_sd.py](../../scripts/sync_from_sd.py) | `_read_manifest()` / `_write_manifest()` with atomic writes, corruption handling |
| Post-sync manifest build | ✅ Ready | [scripts/sync_from_sd.py](../../scripts/sync_from_sd.py) | `_build_post_sync_manifest()` — currently records SD-side stats only |
| Manifest tests | ✅ Ready | [scripts/tests/test_sync_from_sd.py](../../scripts/tests/test_sync_from_sd.py) | Tests for manifest I/O and post-sync build |
| Sync comparison tests | ⚠️ Partial | [scripts/tests/test_syncing.py](../../scripts/tests/test_syncing.py) | Tests exist for old SD-vs-manifest behaviour; no local-drift tests |

## Findings

### 1. Root Cause: Null FAT32 Timestamps (Verified)

The problem is **not** general "mtime drift between FAT32 and NTFS". It is a specific issue with the Deluge firmware.

**What happens:** The Deluge firmware writes factory presets (and some other files) to the SD card's FAT32 filesystem **without setting timestamps**. These files have null/zero modification times in the FAT32 directory entries.

**How Python interprets them:** On Windows, `stat().st_mtime` converts a zero FILETIME to Unix time, producing `-11644473600.0` — which is **January 1, 1601** (the NTFS epoch origin).

**Real data from `G:\SYNTHS\FACTORY` (SD card):**
```
000 Rich Saw Bass.XML       -11644473600.0   ← null timestamp (factory preset)
001 Sync Bass.XML           -11644473600.0   ← null timestamp (factory preset)
...
132 Organ Strings.XML        1775809066.0    ← real timestamp (user-modified)
154 Rich FM Pad 1.XML        1775809066.0    ← real timestamp (user-modified)
```

**After `shutil.copy2` to `C:\source\deluge\DELUGE\SYNTHS\FACTORY` (NTFS):**
```
000 Rich Saw Bass.XML        1777722966.255  ← copy time (NOT preserved)
001 Sync Bass.XML            1777722966.255  ← copy time (NOT preserved)
...
132 Organ Strings.XML        1775809066.0    ← preserved correctly
154 Rich FM Pad 1.XML        1775809066.0    ← preserved correctly
```

**Why `copy2` fails for null timestamps:** `shutil.copy2` calls `os.utime()` to set the destination mtime. When the source mtime is `-11644473600.0`, NTFS cannot represent this date — `os.utime()` silently falls back to the current time.

**Why real timestamps are fine:** Files with normal mtimes (e.g. `1775809066.0`, which is a date in 2026) round-trip through `copy2` without issue. The FAT32 2-second granularity and `normalise_mtime()` handle any minor rounding.

**Impact:** ~287 out of ~7940 files have null timestamps and are re-flagged for copy on every sync, even though their content is identical.

**Source:** [scripts/debug_mtime.py](../../scripts/debug_mtime.py) — used to capture the data above.

### 2. The Current Comparison Logic (Manifest Commented Out)

The user has commented out the manifest comparison in `compute_sync()` during review. Current state:

```python
# if manifest is not None and key in manifest:
#     cmp_size: int = manifest[key]["size"]
#     cmp_mtime: float = manifest[key]["mtime"]
# else:
cmp_size = dst_entry.size
cmp_mtime = normalise_mtime(dst_entry.mtime)
```

This falls back to direct SD-vs-local stat comparison, which re-introduces the 287-file false-positive problem on every sync.

**Source:** [scripts/deluge_lib/syncing.py](../../scripts/deluge_lib/syncing.py) lines 148–163.

### 3. The Gap in the Original Manifest Logic

When the manifest block was active, the comparison asked only one question:

> SD stats == manifest stats? → **skip** (SD unchanged since last sync)

It never checked whether the local file still matches what was synced. This creates a blind spot:

1. **Sync** copies `KITS/MyKit.XML` (size=500, mtime=1700000000) to `DELUGE/`. Manifest records `{size: 500, mtime: 1700000000}`.
2. **`extract_instruments.py`** modifies `DELUGE/KITS/MyKit.XML` — local file now has size=520.
3. **Re-sync**: SD stats (500, 1700000000) match manifest (500, 1700000000) → **skip**. Local file (520 bytes) is never checked.
4. **Result:** `DELUGE/KITS/MyKit.XML` silently diverges from the SD card. The user sees "Already up to date".

This applies to any local modification: extraction scripts, `git checkout`, `git stash`, manual edits.

### 4. What the Manifest Currently Stores

`_build_post_sync_manifest()` always records **SD-side stats**:

- **Copied files:** `src_entry.size`, `src_entry.mtime` (from SD card scan)
- **Unchanged files with prior entry:** preserves old manifest entry (also SD-side)
- **Unchanged files, no prior entry:** uses SD-side stats

The manifest never records what the local file's mtime actually ended up as after `copy2`. This is the key missing piece — without it, there's no NTFS-to-NTFS reference value for local-drift detection.

**Source:** [scripts/sync_from_sd.py](../../scripts/sync_from_sd.py) lines 111–148.

### 5. Cross-Script Impact

| Script | Uses manifest | Affected |
|--------|---------------|----------|
| `sync_from_sd.py` | Yes | **Yes** — this is the target |
| `sync_to_sd.py` | No (no `manifest` arg) | No |
| `sync_samples_to_cloud.py` | No (`manifest=None`) | No |

The `manifest is None` code path in `compute_sync()` must remain untouched.

### 6. Performance Context

- ~7940 files total on SD card
- WAVs: large (tens to hundreds of MB each), SD card reader is the I/O bottleneck
- XMLs: small (1–100 KB), ~50 MB total
- Current scan: stat-only, fast
- Full SHA256 of all SD files: ~2–4 minutes (dominated by SD card read speed)
- SHA256 of XMLs only: ~1 second

## Approaches Considered

### Approach A: Dual-Stat Manifest (Recommended)

Store **two sets of stats** per file in the manifest:
- `sd_size`, `sd_mtime` — the SD card's stats at sync time
- `local_size`, `local_mtime` — the actual stats of the NTFS file after `copy2` completes

Comparison logic:

```python
if manifest is not None and key in manifest:
    m = manifest[key]
    sd_changed = (src_entry.size != m["sd_size"]
                  or not _mtime_matches(src_entry.mtime, m["sd_mtime"]))
    local_drifted = (dst_entry.size != m["local_size"]
                     or dst_entry.mtime != m["local_mtime"])
    if sd_changed or local_drifted:
        copy
    else:
        skip
else:
    # No manifest entry → direct SD vs local comparison (existing fallback)
```

**Why this works for null-timestamp files:** The local-drift check compares NTFS stat vs stored NTFS stat. No cross-filesystem comparison. The null-timestamp problem only exists when comparing FAT32 vs NTFS values — which is now confined to the SD-vs-manifest check, where the manifest stores the original FAT32 value.

**Manifest format:**

```json
{
  "last_sync_timestamp": "2026-05-02T10:00:00+00:00",
  "files": {
    "kits/mykit.xml": {
      "sd_size": 500,
      "sd_mtime": -11644473600.0,
      "local_size": 500,
      "local_mtime": 1777722966.255
    }
  }
}
```

**Implementation changes:**
1. `_build_post_sync_manifest()` — stat destination file after copy, record both SD and local stats
2. `compute_sync()` — uncomment and extend manifest block with dual check
3. `_read_manifest()` / `_write_manifest()` — handle new field names
4. Old-format manifests: treat as "no local stats" → triggers re-copy → refreshes manifest (one-time cost)

**Local mtime precision:** NTFS mtimes have sub-second precision. Store raw values (don't normalise) since both sides of the comparison are NTFS. Use exact equality, not `_mtime_matches()` tolerance — the tolerance exists for FAT32's 2-second grid, which doesn't apply here.

### Approach B: Size-Only Comparison

Drop mtime from all comparisons. Compare only file sizes. No manifest needed.

**Pros:** Simplest possible. No timestamp issues at all.

**Cons:** Misses same-size edits (e.g. changing an XML parameter value from `50` to `60`). This is a real scenario — XML presets are edited on the Deluge, and parameter value changes often don't change file size.

### Approach C: Hybrid — Stat for WAVs, Hash for XMLs

WAVs: size + mtime with dual-stat manifest (same as Approach A).
XMLs: SHA256 comparison. No manifest needed for XMLs — hash both sides and compare directly.

**Pros:** 100% accurate for XMLs (the files most likely to be locally modified). Fast — hashing ~50 MB of XMLs takes ~1 second.

**Cons:** Two different comparison strategies adds complexity. Still needs the dual-stat manifest for WAVs. The accuracy gain over Approach A is marginal — mtime reliably detects modifications in practice.

### Comparison

| Approach | Detects SD changes | Detects local drift | Null-timestamp safe | Same-size edit safe | Complexity |
|----------|-------------------|--------------------|--------------------|--------------------|----|
| **A: Dual-stat manifest** | ✅ | ✅ | ✅ | ✅ (via mtime) | Medium |
| **B: Size-only** | ⚠️ misses same-size | ⚠️ misses same-size | ✅ | ❌ | Low |
| **C: Hybrid** | ✅ | ✅ | ✅ | ✅ (hash for XML) | Medium-High |

## Scenario Walkthroughs

Four scenarios every solution must handle correctly:

### Scenario 1: `sync → do nothing → sync` (idempotent re-run)

Expected: "Already up to date" — zero copies.

| Approach | Result |
|----------|--------|
| **A** | SD vs `sd_*`: match. Local vs `local_*`: match (NTFS-to-NTFS, exact). **Skip.** ✅ |
| **B** | SD size vs local size: match. **Skip.** ✅ |
| **C** | XML hashes match. WAV stats match. **Skip.** ✅ |

### Scenario 2: `sync → edit file on SD → sync` (SD change)

Expected: re-copy the changed file.

| Approach | Result |
|----------|--------|
| **A** | SD vs `sd_*`: size or mtime differs. **Copy.** ✅ |
| **B** | SD size vs local size: differs if size changed. ⚠️ Misses same-size edits. |
| **C** | SD hash vs local hash: differs. **Copy.** ✅ |

### Scenario 3: `sync → edit file locally → sync` (local drift)

Expected: re-copy from SD to restore source of truth.

| Approach | Result |
|----------|--------|
| **A** | SD vs `sd_*`: match. Local vs `local_*`: size or mtime differs. **Copy.** ✅ |
| **B** | SD size vs local size: differs if size changed. ⚠️ Misses same-size edits. |
| **C** | XML: hash differs → copy. WAV: local vs `local_*` differs → copy. ✅ |

### Scenario 4: `sync → null-timestamp file unchanged → sync`

Expected: skip — no re-copy of the ~287 factory presets.

| Approach | Result |
|----------|--------|
| **A** | SD mtime (`-11644473600.0`) vs `sd_mtime` (`-11644473600.0`): match. Local mtime vs `local_mtime`: match (both NTFS). **Skip.** ✅ |
| **B** | Sizes match. **Skip.** ✅ |
| **C** | Hashes match (content identical). **Skip.** ✅ |

## Cross-Cutting Concerns

### Manifest Migration

Old manifests use `{size, mtime}`. New format uses `{sd_size, sd_mtime, local_size, local_mtime}`. On encountering an old-format entry, treat it as having no local stats — the file will be re-copied and the manifest refreshed. This is a one-time cost (~287 null-timestamp files re-copied; files with real timestamps will match on direct comparison in the fallback path).

### `_build_post_sync_manifest()` Changes

Currently records SD-side stats only. Must also stat the destination file **after** `execute_plan()` copies it. Simplest approach: have the builder stat each copied file itself (it already receives `dest` as a parameter). The function is specific to `sync_from_sd`, so purity concerns are minimal.

### Filtered Sync (`--xml` / `--wav`)

Already handled — `_build_post_sync_manifest()` carries forward entries for unscanned file types. No change needed; carried-forward entries retain their format.

### Test Updates

Existing `TestComputeSyncManifest` tests need updating for dual-stat comparison. New test cases:
- Local file modified (size change) → detected
- Local file modified (mtime change, same size) → detected
- Null-timestamp file unchanged on both sides → not flagged
- Both SD and local changed → copy from SD

## Risk Analysis

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| NTFS mtime jitter between runs (antivirus, indexers) | Low | Low — wasteful re-copy but not incorrect | SD is source of truth; re-copying identical content is harmless |
| Old manifest format triggers one-time re-sync | Certain | Low — one-time, ~287 null-timestamp files | Acceptable cost; completes in seconds |
| `stat()` of copied files in manifest builder fails | Low | Low — manifest not updated; next sync re-copies | Already safe: manifest only written after builder completes |

## Recommendation

**Approach A: Dual-Stat Manifest.**

It's the simplest approach that is correct across all four scenarios. It solves the null-timestamp problem (NTFS-to-NTFS local comparison avoids cross-filesystem drift) and closes the local-drift blind spot (checks local file against stored local stats). No content hashing needed — stat-only performance is preserved. Changes are contained to the comparison block in `compute_sync()`, the manifest builder, and the manifest format.

Approach B is simpler but has a real accuracy gap (same-size edits). Approach C adds hashing complexity for marginal benefit over mtime-based detection.

## Open Questions

1. **Should `_build_post_sync_manifest()` stat copied files itself, or should `execute_plan()` return destination stats?**
   - **Impact:** Architectural cleanliness vs simplicity.
   - **Recommendation:** Builder stats files itself. It already receives `dest`. The purity concern is minor for a function specific to `sync_from_sd`.
   - **Blocking:** No.

2. **Should `normalise_mtime()` be applied to stored local mtimes?**
   - **Impact:** NTFS has sub-second precision. Normalising to the FAT32 2-second grid would lose information for no benefit (both sides of the local comparison are NTFS).
   - **Recommendation:** Store and compare raw NTFS values. Use exact equality for the local check.
   - **Blocking:** No.

## References

### Project Files
- [scripts/deluge_lib/syncing.py](../../scripts/deluge_lib/syncing.py) — `compute_sync()`, `_mtime_matches()`, `normalise_mtime()`
- [scripts/sync_from_sd.py](../../scripts/sync_from_sd.py) — `_read_manifest()`, `_write_manifest()`, `_build_post_sync_manifest()`
- [scripts/deluge_lib/scanning.py](../../scripts/deluge_lib/scanning.py) — `scan_tree()`, `normalise_mtime()`, `FileEntry`
- [scripts/deluge_lib/paths.py](../../scripts/deluge_lib/paths.py) — `MANIFEST_PATH`
- [scripts/debug_mtime.py](../../scripts/debug_mtime.py) — Script used to capture real mtime data
- [scripts/tests/test_syncing.py](../../scripts/tests/test_syncing.py) — Existing manifest comparison tests
- [scripts/tests/test_sync_from_sd.py](../../scripts/tests/test_sync_from_sd.py) — Manifest I/O tests

## Next Steps

1. Review this document and resolve any open questions
2. Invoke the Plan agent to create a feature plan from this research
