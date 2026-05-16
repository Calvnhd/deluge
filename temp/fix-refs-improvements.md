# fix_references.py — Recovery Improvements Needed

## Problem

After implementing basename-based missing reference recovery (per `docs/research/missing-ref-recovery-research.md`), many missing files are still not recovered. The latest run shows 0 recovered, 61 missing.

## Issue 1: Manifest Lifecycle Data Loss

The manifest lifecycle destroys the data that recovery needs:

1. Manifest originally had entries like `samples/artists/kody nielson/1.wav` → hash X
2. Files were reorganized (e.g., `Artists/` moved under `FACTORY/`)
3. `sync_from_sd` ran — `build_post_sync_manifest()` in `syncing.py` iterates only `src_scan.files` (SD card's current state)
4. New key `samples/factory/artists/kody nielson/1.wav` gets created and hashed
5. Old key `samples/artists/kody nielson/1.wav` silently drops out — not in `src_scan.files`, never carried forward
6. By the time `fix_references` runs, the old path → hash mapping is gone
7. Migration map sees file as "unchanged" (manifest path = filesystem path)
8. Recovery falls back to basename matching — generic names like `1.wav` exceed `MAX_RECOVERY_CANDIDATES` (5) and are skipped

## Issue 2: Overly Aggressive Ambiguity Classification

After recovering files (restoring them to old paths), syncing the manifest (so it now has BOTH old and new paths with same hash), and deleting the duplicate, a second run of `fix_references.py` shows **0 changes, 0 recovered, 0 errors, 151 warnings, 2 missing**.

The problem is in `compute_migration_map()` around line 144-148 of `fix_references.py`:

```python
elif len(bpaths) == 1 and len(apaths) == 1:
    if bpaths[0] != apaths_norm[0]:
        moved[bpaths[0]] = apaths[0]
else:
    ambiguous[h] = (list(bpaths), list(apaths))
```

When the manifest has 2 entries for the same hash (old path + new path) and only 1 survives on disk, this is a 2:1 (N:1) case. The code classifies it as "ambiguous" but it's **fully resolvable**:
- The before-path that matches the after-path → unchanged
- The before-path that doesn't match → deleted
- XML refs to the deleted path should become moves to the surviving path

In `classify_ref_changes`, the ref hits the `ambiguous_paths` check before it can reach recovery, so it becomes a warning ("multiple files share this hash") instead of a fixable change.

## Test Runs

| Run | Log File | Changes | Recovered | Errors | Warnings | Missing |
|---|---|---|---|---|---|---|
| 1 — Initial (pre-recovery) | `scripts/fix-ref.log` | 0 | 0 | 0 | 0 | 61 |
| 2 — After file recovery + manifest sync + dedup | `scripts/fix-ref-2.log` | 0 | 0 | 0 | 151 | 2 |

Run 2 warnings include refs like:
- `SAMPLES/Artists/Kody Nielson/1.wav` — the deleted duplicate path
- `SAMPLES/FACTORY/Artists/Kody Nielson/1.wav` — the surviving path (also flagged as warning!)
- All the Double Bass, Hangdrum, Roman Hatz, Stefanie Franciotti, Stephanie Engelbrecht, and SLPSPK-Drumloop refs

Only 2 truly missing remain: `REC00000.WAV` and `uwahwah.wav`.

## Current Missing References (61 total)

- ~48 refs from `SAMPLES/Artists/*/...` paths (files exist at `SAMPLES/FACTORY/Artists/*/...`) — recoverable if we fix the system
- 17 refs to `SAMPLES/KERERU/DrumLoops/SLPSPK-Drumloop4-120bpm.wav` — truly missing (different filename in manifest: `slpspk-drumloop-120bpm.wav`)
- 1 ref to `SAMPLES/RECORD/REC00000.WAV` — not in manifest, truly missing
- 1 ref to `uwahwah.wav` — known unrecoverable (only `uwahwah2.wav` exists)

## Potential Approaches

| Approach | Description | Complexity |
|---|---|---|
| **A. Move log during sync** | `build_post_sync_manifest` detects old_key disappeared + new_key appeared with same hash → writes a moves dict to manifest or sidecar file | Low |
| **B. Run fix_refs as part of sync** | Before manifest rewrite, run migration map logic while old paths are still available | Medium |
| **C. Never delete manifest entries** | Mark old entries as "relocated → new_path" instead of dropping them | Medium |
| **D. Short-term: path similarity recovery** | Don't fix the manifest; improve recovery to use path similarity instead of giving up at >5 basename matches | Low (band-aid) |
| **E. Resolve N:1 hash mappings** | In `compute_migration_map`, when N before-paths map to 1 after-path: match the surviving path as unchanged, classify the rest as deleted. XML refs to deleted paths become moves to the survivor. | Low |

## Key Insight

The sync already has both old manifest and new scan side-by-side — it could trivially detect that an old hash appeared at a new path. Option A (move log during sync) is likely the cleanest fix. But this touches the manifest schema and sync logic, so it may warrant going through the research → plan pipeline.

## Related Files

- `scripts/fix_references.py` — recovery logic (basename matching, `MAX_RECOVERY_CANDIDATES`, `path_similarity()`)
- `scripts/deluge_lib/syncing.py` — `build_post_sync_manifest()` where old entries are dropped (line ~126)
- `scripts/sync_from_sd.py` — calls `build_post_sync_manifest` then `write_manifest`
- `docs/research/missing-ref-recovery-research.md` — original recovery research
- `scripts/fix-ref.log` — run 1 output showing 61 missing
- `scripts/fix-ref-2.log` — run 2 output showing 151 warnings, 2 missing
