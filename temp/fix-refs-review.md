# fix_references.py — Code Review

Review of `scripts/fix_references.py` after major refactor. Covers bugs, logic errors, stale code, TODO analysis, and path normalisation.

---

## Bugs (will crash at runtime)

### 1. `BrokenRefError` field name mismatch

**Severity: Critical — TypeError on every broken-ref path**

The dataclass defines `broken_path`:

```python
@dataclass
class BrokenRefError:
    ref: SampleRef
    broken_path: str
```

But all four construction sites in `_classify_ref_changes` use `deleted_path=`:

```python
result.errors.append(
    BrokenRefError(ref=xml_ref, deleted_path=xml_ref.path)  # ← TypeError
)
```

**Fix:** Change all `deleted_path=` to `broken_path=` (4 occurrences in `_classify_ref_changes`).

---

### 2. `_preview_and_apply` — broken apply loop

**Severity: Critical — crashes during apply phase**

```python
for xml_file, planned_change in sorted(changes_by_file):
```

`changes_by_file` is a `dict[Path, list[PlannedChange]]`. Iterating `sorted(dict)` yields keys only — unpacking a single `Path` into two variables will raise `ValueError`.

Even if fixed to `sorted(changes_by_file.items())`, the value is a **list** of `PlannedChange`, not a single item. The loop body treats it as singular:

```python
mapping[planned_change.old_path] = planned_change.new_path
```

**Fix:**

```python
for xml_file, planned_changes in sorted(changes_by_file.items()):
    mapping: dict[str, str] = {}
    for change in planned_changes:
        mapping[change.old_path] = change.new_path
    updated = _update_sample_refs(deluge_root / xml_file, mapping)
```

---

### 3. Recovery section looks up wrong dict

**Severity: Critical — KeyError at runtime**

In `_classify_ref_changes`, the basename-recovery paths do:

```python
new_path=migration.moved[matched_path]
```

`matched_path` is a **current library path** from `basename_index`. But `migration.moved` is keyed by **old normalised manifest paths**. A current library path will almost never be a key in `moved` — this raises `KeyError`.

The intent is to use the library path directly as the new path (the file was found there):

**Fix** (all 3 recovery sites):

```python
new_path=matched_path
```

---

## Logic Errors

### 4. Duplicate detection flags every file

```python
if len(library_paths) > 0:
    duplicate[h] = list(library_paths)
```

This marks **every hash with any library presence** as a duplicate, including files that exist exactly once. The `main()` function then triggers "Duplicates detected!" for all non-empty libraries.

**Fix:**

```python
if len(library_paths) > 1:
    duplicate[h] = list(library_paths)
```

---

### 5. Missing separator in summary line

```python
print(
    f"{len(ref_classification.changes)} planned changes"
    f"{len(ref_classification.errors)} errors to be manually resolved"
)
```

Python concatenates adjacent f-strings, producing: `"5 planned changes3 errors to be manually resolved"`.

**Fix:** Add a separator — e.g. `", "` or `" | "` or `"\n"`:

```python
print(
    f"{len(ref_classification.changes)} planned changes, "
    f"{len(ref_classification.errors)} errors to be manually resolved"
)
```

---

## Stale / Misleading Code

### 6. Misleading mtime comment

```python
and library_entry.mtime == manifest_entry["local_mtime"]
# scan_tree() will have normalised both these values already
```

`manifest_entry["local_mtime"]` comes from JSON, not `scan_tree()`. It works because the manifest was written with normalised values during sync, but the comment is wrong about **who** normalised it.

**Suggestion:** Update comment to: `# Both values are FAT32-normalised: library by scan_tree(), manifest at write time`

---

## TODO Analysis

| Location | TODO | Verdict |
|----------|------|---------|
| `_classify_ref_changes` — moved branch | `# TODO - should this be normalised?` | **No.** `migration.moved[xml_ref_norm]` returns the original-case library path. You want original case for writing to XML. Normalisation would break actual file references. Remove TODO. |
| `_classify_ref_changes` — recovery branches (×3) | `# TODO - check normalisation here?` | **Moot** — these lines have Bug 3 (wrong dict lookup). After fixing to `new_path=matched_path`, the library path from `basename_index` preserves original case, which is correct. Remove TODO. |
| `_update_manifest_keys` | `# TODO - unsure if the normalised note above is still true?` | **It is.** The `moved` dict keys are manifest paths (normalised by `read_manifest` consumers). The docstring "k: normalised_old_key" is accurate. Remove TODO. |
| `main()` | `# TODO - what about added?` | **Valid concern.** New samples (in library but not manifest) won't get manifest entries until next sync. Low priority — the fix-refs script isn't responsible for manifest completeness — but worth noting for future work. Keep TODO or convert to a comment. |
| `_handle_duplicates` | `# TODO - all of this!` | Acknowledged placeholder. Fine as-is. |

---

## Path Normalisation Assessment

The normalisation strategy is **sound in design** but has implementation gaps (Bugs 1–3 above). Here's the intended flow:

| Context | Key/Path Format | Correct? |
|---------|----------------|----------|
| Manifest dict keys | Normalised (lowercase, forward-slash) | ✓ |
| `migration.moved` keys | Normalised (from manifest) | ✓ |
| `migration.moved` values | Original-case library paths | ✓ — correct for XML writes |
| `library_hashes` keys | Hash string | ✓ |
| `library_hashes` values | Original-case library paths | ✓ |
| `deleted_paths` set | Normalised (from manifest keys) | ✓ |
| `library_paths` set | Normalised via `normalise_key()` | ✓ |
| `basename_index` keys | Lowercase basename | ✓ |
| `basename_index` values | Original-case library paths | ✓ |
| XML ref lookup (`xml_ref_norm`) | Normalised via `normalise_key()` | ✓ |

**One subtlety:** `manifest_hashes` values are manifest keys (normalised), while `library_hashes` values are original-case paths. The move comparison normalises the library side before comparing, which is correct:

```python
if manifest_paths[0] != normalise_key(library_paths[0]):
    moved[manifest_paths[0]] = library_paths[0]
```

The design is consistent. Once the three runtime bugs are fixed, the normalisation should work correctly throughout.

---

## Summary

| # | Category | Issue | Severity |
|---|----------|-------|----------|
| 1 | Bug | `BrokenRefError` — `deleted_path` vs `broken_path` | Critical |
| 2 | Bug | Apply loop — iterates keys, not items; treats list as single | Critical |
| 3 | Bug | Recovery — `migration.moved[matched_path]` KeyError | Critical |
| 4 | Logic | Duplicate threshold `> 0` should be `> 1` | Medium |
| 5 | Logic | Missing separator in summary print | Low |
| 6 | Stale | Misleading mtime normalisation comment | Cosmetic |
