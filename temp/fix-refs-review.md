# fix_references.py — Code Review

Review of `scripts/fix_references.py` and its library dependencies after major refactor.

---

## Summary

The script is well-structured and the overall flow is sound. Path normalisation is consistent throughout — the `SAMPLES/` prefix is correctly maintained across manifest keys, library hashes, and XML reference comparisons. The data classes are clean, the recovery logic (stale manifest → basename matching) is a good layered fallback design, and the duplicate handling with re-computation is clever.

Several issues found below, one real bug and a handful of robustness concerns.

---

## Bug

### 1. Unhandled 1:N migration case in `_compute_migration_map()`

**Lines 127–143.** The `elif` chain that categorises each hash has a gap. When one manifest entry maps to 2+ library files (same hash), no branch fires:

| Condition | mp=1, lp=2+ |
|---|---|
| `len(mp) == 1 and len(lp) == 1` | False (lp > 1) |
| `mp and not lp` | False (lp truthy) |
| `lp and not mp` | False (mp truthy) |
| `len(mp) > 1 and len(lp) > 0` | False (mp == 1) |

The hash falls through with no categorisation. The only thing captured is `lib_duplicates`.

**Impact:** If the original file was moved/renamed to one of the duplicate locations, the XML reference to the old path won't be in `moved`. It'll reach `_classify_ref_changes`, fail all early checks, and fall to basename recovery — which works but is accidental. If the filename also changed, it becomes a broken error with no explanation of the underlying cause.

**Fix:** Add an explicit branch for 1:N. Since there are multiple library candidates, you can't pick a single move target. Options:
- Treat the manifest path as stale (add to `stale` dict) so `_classify_ref_changes` can recover via the hash
- Or pick the library path matching the manifest path's basename as the move target, falling back to stale if ambiguous

---

## Robustness Concerns

### 2. Non-deterministic keeper selection in `_handle_duplicates()`

`paths[0]` is used as the keeper for each duplicate group. The order of `paths` depends on insertion order in `library_hashes`, which comes from `os.walk` — non-deterministic across platforms and runs.

**Impact:** Different runs may keep different files and delete different duplicates. The recovery logic handles this (stale manifest → reference fix), but the user sees inconsistent behaviour.

**Suggestion:** Sort each group before selecting the keeper. Prefer the shortest path, or alphabetically first, or — ideally — the path that's already referenced by XML files.

### 3. Stale manifest entries after duplicate deletion

After `_handle_duplicates()` deletes files, their manifest entries persist. `_update_manifest_keys()` only handles `moved` entries. The deleted duplicate paths remain as ghost entries.

**Impact:** 
- Running `fix_references` again before the next sync would re-flag the ghost entries as deleted/stale
- Manifest bloat over time

**Suggestion:** After applying reference fixes, purge manifest entries whose paths no longer exist on disk. Could be a small cleanup step at the end of `main()`.

### 4. Non-atomic XML writes in `_update_sample_refs()`

Uses `Path.write_text()` directly. If the process crashes mid-write, the XML is truncated. Compare with `write_manifest()` in `syncing.py` which uses a temp-file + atomic rename pattern.

**Impact:** Low probability, but data loss on crash. These are preset/song files.

**Suggestion:** Use the same temp-file pattern as `write_manifest()`, or extract a shared `atomic_write()` helper.

### 5. Cascading string replacement in `_update_sample_refs()`

Replacements are sorted longest-first, which prevents prefix collisions. But if a replacement's *new* path matches another replacement's *old* path, the second replacement corrupts the first's result.

Example: Replace `"SAMPLES/Old/test2.wav"` → `"SAMPLES/New/test.wav"` (longer, done first), then `"SAMPLES/New/test.wav"` → `"SAMPLES/Other/test.wav"` (shorter, done second) — the second replacement hits the text just inserted by the first.

**Impact:** Very unlikely in practice (requires one sample's new location to exactly match another sample's old location). But worth noting.

**Mitigation if needed:** Build all replacements into a single pass using `re.sub` with an alternation pattern, or process the XML via the parsed tree rather than raw text.

---

## Path Normalisation Audit

Traced normalisation through the full data flow. **No issues found.**

| Data | Format | Prefix |
|---|---|---|
| Manifest keys | Normalised (lowercase, fwd slash) | `samples/...` |
| `manifest_hashes` values | Raw manifest keys (normalised) | `samples/...` |
| `library_hashes` values | Original case, fwd slash | `SAMPLES/...` |
| `moved` keys | Normalised | `samples/...` |
| `moved` values | Original case | `SAMPLES/...` |
| `deleted` values | Normalised (from manifest) | `samples/...` |
| `stale` values | Normalised (from manifest) | `samples/...` |
| `xml_ref.path` | Original case (from XML) | `SAMPLES/...` |
| `xml_ref_norm` | Normalised via `normalise_key()` | `samples/...` |

All comparisons between manifest-sourced and XML-sourced paths go through `normalise_key()`. The `SAMPLES/` prefix is consistently present in all paths. Cross-domain lookups (e.g., checking an XML ref against `deleted_paths` or `library_paths`) normalise both sides. **Correct.**

---

## Minor / Style Notes

- **`continue` in stale recovery** (line ~185): Works correctly — skips basename recovery when stale recovery succeeds. Could be slightly cleaner as an `elif` chain but not wrong.
- **Unused argparse result** in `main()`: `parser.parse_args(argv)` result isn't captured. Fine since there are no args, but `_args = parser.parse_args(argv)` would be more conventional.
- **Comment about added samples** at end of `main()` is useful — keep it.

---

## No TODOs Found

`fix_references.py` contains no TODO/FIXME markers. The associated library files have one relevant TODO in `syncing.py:310` (`# TODO: test if you can break this by changing a very minor value`) — this is in the sync comparison logic, not directly related to fix_references but is used during manifest-based cache hits in `_compute_migration_map()`.

---

## What's Working Well

- Clean data class hierarchy: `MigrationResult` → `ReferenceStatus` → preview/apply is easy to follow
- Layered recovery strategy: moved → deleted → stale manifest → basename match → broken error
- Duplicate handling re-computes the migration map, so downstream classification automatically picks up the changes
- Deduplication of preview output (pair counting, error counting) is a nice touch
- The `confirm_apply` gate before destructive actions is consistent
