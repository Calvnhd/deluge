# Follow-ups from sync/manifest/fixref review

Issues identified during code review (2026-05-15) that weren't immediately actionable.

## Duplicated code

**`_execute_to_sd` duplicates `execute_plan`** — `sync_to_sd.py` lines 34–111

The 77-line `_execute_to_sd` function is functionally identical to `execute_plan(plan, dest=sd_path, delete_mode="delete")` from `syncing.py`. Both copy files, then hard-delete with empty-parent cleanup. Could be replaced with a single call to `execute_plan`.

## Edge cases

**`update_sample_refs` uses naive string replacement** — `fix_references.py` lines 270–284

`data.replace(old_path, new_path)` operates on raw XML text. Two risks:
- Substring collisions: if `old_path` is a substring of another path in the file
- Cascading replacements: if a prior replacement's `new_path` contains a later replacement's `old_path`

In practice the migration map shouldn't produce these cases, but there's no guard.

**`compute_sync` mutates the manifest dict in-place** — `syncing.py` lines 321–361

When stat data is stale but hashes match, `compute_sync` silently updates `manifest_entry["sd_size"]`, `sd_mtime`, `local_size`, `local_mtime`, and `hash` on the caller's dict. This is relied upon by `build_post_sync_manifest` but undocumented.

**Double SAMPLES scan in `fix_references`** — `fix_references.py` lines 466–468

`compute_migration_map` and `classify_ref_changes` both independently scan the SAMPLES directory via `scan_tree`. The first scan result could be passed through to avoid redundant I/O.

## Minor inconsistencies

**Redundant `normalise_mtime`** — `syncing.py` line 368

In the no-manifest fallback: `normalise_mtime(dst_entry.mtime)` where `dst_entry.mtime` is already normalised by `scan_tree`. No-op.

**`_mtime_matches` tolerance stacks with normalisation** — `syncing.py` lines 259–265

Both mtimes are pre-truncated to 2-second FAT32 resolution, then `_mtime_matches` adds another ±2s tolerance. Timestamps 1 FAT32 tick (2s) apart are treated as equal.

**`sync_from_sd` error report omits trashed count** — `sync_from_sd.py` line 100

If `execute_plan` fails during the trash phase, `exc.trashed` is nonzero but the error message only prints copied and remaining.

**`_FILTER_MAP` accessed cross-module via private name** — `syncing.py` line 209

`build_post_sync_manifest` imports `_FILTER_MAP` (underscore-prefixed) from `scanning.py`.
