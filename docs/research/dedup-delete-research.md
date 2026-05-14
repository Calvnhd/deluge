# Research: Duplicate Sample Deletion

> **Document Type:** Research
> **Date:** 03 May 2026
> **Request:** Add a `--delete` flag to `sample_overview duplicates` that removes duplicate sample files, keeping one copy per hash group
> **Pipeline:** Research → Plan → Implement

## Executive Summary

The existing `cmd_duplicates` in `sample_overview.py` already computes exactly the data needed: SHA-256 hash groups with all duplicate paths. Adding `--delete` requires only a deletion loop with a TEMP-folder heuristic and a confirmation prompt. Broken XML references from deleted duplicates are acceptable — they will show up in `sample_overview missing` and can be addressed later when `fix_references.py` is enhanced to handle dedup scenarios (a TODO has been added).

## Objectives

- Confirm `cmd_duplicates` already has the data needed for deletion
- Determine whether `fix_references.py` can repair broken refs after dedup
- Verify SD card safety rules permit deleting files from `DELUGE/SAMPLES/`
- Confirm the TEMP folder path convention
- Recommend the simplest integration approach

## Feature Overview

**Purpose:** Remove duplicate sample files (identical SHA-256 content) to reclaim SD card space.

**Use case:** User runs `sample_overview duplicates --delete`, which keeps one copy per hash group and deletes the rest. If any copy is in `SAMPLES/CLIPS/TEMP/`, it is preferentially deleted.

**Scope:**
- In scope: deleting duplicate files, preferring TEMP copies for deletion, dry-run preview, confirmation prompt
- Out of scope: fixing XML references, moving/reorganising samples, handling non-WAV files, interactive per-group selection

## Existing Assets Analysis

| Capability | Status | Location | Notes |
|------------|--------|----------|-------|
| Duplicate detection (hash grouping) | ✅ Ready | [sample_overview.py](../../scripts/sample_overview.py#L364) | `cmd_duplicates` receives `hashes: dict[str, list[str]]` — SHA-256 → paths |
| SHA-256 hashing | ✅ Ready | [deluge_sdk.py](../../scripts/deluge_lib/deluge_sdk.py#L93) | `hash_all_samples()` returns `dict[str, list[str]]` |
| Snapshot creation | ✅ Ready | [create_snapshot.py](../../scripts/create_snapshot.py) | `snapshot()` saves hash state as dated JSON |
| Reference fixing (moved files) | ⚠️ Partial | [fix_references.py](../../scripts/fix_references.py) | Handles 1:1 moves; treats N:1 reductions as ambiguous |
| CLI subparser for `duplicates` | ✅ Ready | [sample_overview.py](../../scripts/sample_overview.py#L569) | Already accepts `--snapshot`; adding `--delete` is trivial |
| TEMP folder convention | ✅ Documented | [AGENTS.md](../../AGENTS.md) | `SAMPLES/CLIPS/TEMP/` — temporary clip recordings |

## Findings

### 1. cmd_duplicates already has all required data

Source: [sample_overview.py](../../scripts/sample_overview.py#L364-L406)

`cmd_duplicates(deluge_root, hashes)` receives the full hash map and filters to groups with `len(paths) > 1`. The function already:
- Iterates each duplicate group
- Has access to all paths per group
- Computes file sizes and wasted space

Adding deletion logic requires only:
1. For each group, pick the path to **keep** (prefer non-TEMP paths)
2. Delete the other files via `Path.unlink()`
3. Return or print the deletion mapping (kept → deleted paths)

### 2. fix_references.py will NOT auto-fix dedup breakage

Source: [fix_references.py](../../scripts/fix_references.py#L56-L100)

`compute_migration_map` compares before-snapshot hashes with current state. The critical logic:

```python
elif len(before_paths) == 1 and len(after_paths) == 1:
    if before_paths[0] != after_paths[0]:
        moved[before_paths[0]] = after_paths[0]
else:
    ambiguous[h] = (list(before_paths), list(after_paths))
```

**After dedup scenario:** Before has `hash → [pathA, pathB]`, after has `hash → [pathA]`. Since `len(before_paths) == 2` and `len(after_paths) == 1`, this falls into the `else` branch → **ambiguous**. References to the deleted `pathB` will be flagged as warnings but not auto-fixed.

This means the workflow `snapshot → delete → fix_references` will **not** work as expected. `fix_references` will show ambiguous warnings for every deleted duplicate's references, requiring manual resolution.

### 3. Future enhancement: inline reference fixing

Since the `--delete` command already knows exactly which paths are being deleted and which path survives in each group, it *could* build a simple `old_path → new_path` mapping and apply it directly using the existing `update_sample_refs()` function from `fix_references.py`. This is noted as a **future enhancement** option — not part of the current scope. For now, broken references are acceptable and can be identified via `sample_overview missing`.

### 4. SD card safety — deletion is permitted

Source: [project.md](../../agent-system/standards/project.md)

> "The `DELUGE/` directory in this repository is editable. Modifying, reorganising, and fixing files within `DELUGE/` is a core purpose of this repository. Scripts may freely read and write to `DELUGE/`."

Deleting files from `DELUGE/SAMPLES/` is explicitly within the scope of permitted operations. No special safety checks are required beyond the standard dry-run/confirm pattern used by other scripts.

### 5. TEMP folder convention

Source: [AGENTS.md](../../AGENTS.md)

> `CLIPS/TEMP/` — Clip recordings are initially saved here and moved into `CLIPS/` when the SONG is saved

The TEMP path to check is `SAMPLES/CLIPS/TEMP/`. Detection heuristic: check if any path in the duplicate group contains `/CLIPS/TEMP/` (or `\CLIPS\TEMP\` on Windows, though paths in the hash map use forward slashes per `PurePosixPath` in `hash_all_samples`).

Since `hash_all_samples` normalises paths to forward slashes via `PurePosixPath`, the check should be `"/CLIPS/TEMP/" in path` or `path.startswith("SAMPLES/CLIPS/TEMP/")`.

## Approaches Considered

| Approach | Pros | Cons | Complexity | Status |
|----------|------|------|------------|--------|
| A: Delete + inline ref fix | Self-contained, no snapshot needed, unambiguous mapping | Adds `fix_references` import to `sample_overview` | Low | Future enhancement |
| B: Delete + fix_references workflow | Reuses existing tool pipeline | Broken — fix_references treats N:1 as ambiguous; would need fix_references changes | Medium | Not recommended |
| **C: Delete only, no ref fixing** | **Simplest possible, fast to implement** | **Leaves broken refs (acceptable — use `sample_overview missing` to check)** | **Low** | **✅ Recommended** |

## Cross-Cutting Concerns

- **XML references:** Deleting a duplicate sample may break XML files that referenced the deleted copy. This is accepted for now — broken refs will appear in `sample_overview missing` and can be addressed later when `fix_references.py` is enhanced to handle dedup scenarios (a TODO has been added to `fix_references.py`).
- **Snapshot workflow:** Snapshots are not needed for this feature. The existing snapshot workflow remains unchanged for other use cases.
- **Git tracking:** `DELUGE/SAMPLES/` is gitignored, so deleted samples won't appear as git changes. The XML reference updates in `KITS/`, `SYNTHS/`, `SONGS/` *will* show in git, which is good for review.
- **`confirm_apply` pattern:** Other scripts (e.g. `fix_references.py`) use `confirm_apply()` from `cli_utils` for destructive operations. The `--delete` command should follow this pattern — show what will be deleted, prompt for confirmation.

## Risk Analysis

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Accidental deletion of wanted samples | Low | High | Dry-run preview + confirmation prompt before deletion |
| Broken XML references left unfixed | Medium | Low | Accepted — user runs `sample_overview missing` to identify broken refs; `fix_references.py` will be enhanced later to handle dedup scenarios |
| TEMP heuristic deletes wrong copy | Low | Low | TEMP files are throwaway by convention; even if wrong, the content is preserved in the surviving copy |

## Recommendation

**Use Approach C: Delete only, no reference fixing.**

1. Add `--delete` flag to the `duplicates` subparser
2. In `cmd_duplicates`, when `--delete` is set:
   - For each hash group, pick the survivor (prefer non-TEMP paths; if all TEMP or none TEMP, keep first alphabetically)
   - Show preview of files to be deleted
   - Prompt for confirmation via `confirm_apply()`
   - Delete the files, print summary
3. Broken references are acceptable — user can check with `sample_overview missing`

This is the simplest possible implementation. Inline reference fixing (Approach A) can be added later as an enhancement.

## Open Questions

1. **Should `--delete` default to dry-run?**
   - **Impact:** Determines whether `--delete` alone is destructive or requires `--apply`
   - **Recommendation:** Follow `fix_references` pattern — show preview, prompt for confirmation. No separate `--apply` flag needed since `confirm_apply()` handles it.
   - **Blocking:** No

2. **What if ALL copies are in TEMP (or none are)?**
   - **Impact:** Edge case for the "keep non-TEMP" heuristic
   - **Recommendation:** If all copies are in TEMP, or none are in TEMP, keep the first path alphabetically (deterministic, simple)
   - **Blocking:** No

## References

### Project Files
- [sample_overview.py](../../scripts/sample_overview.py) — `cmd_duplicates` function and CLI subparser
- [fix_references.py](../../scripts/fix_references.py) — `compute_migration_map`, `update_sample_refs`, `classify_ref_changes`
- [deluge_sdk.py](../../scripts/deluge_lib/deluge_sdk.py) — `hash_all_samples()` returns SHA-256 → path list
- [create_snapshot.py](../../scripts/create_snapshot.py) — Snapshot creation for before/after comparison
- [project.md](../../agent-system/standards/project.md) — SD card safety rules
- [AGENTS.md](../../AGENTS.md) — TEMP folder convention documentation

## Next Steps

1. Review this document — no blocking open questions
2. Invoke the Plan agent to create a feature plan from this research
