# Fix References — Issues Found During Testing (13 Apr 2026)

Issues discovered during the first real-data test of `fix_references.py` and related scripts.

## Critical

### 1. XML reformatting on write
`update_sample_refs` in `deluge_sdk.py` uses `lxml`'s `tree.write()` to save changes, which rewrites the entire XML file — changing quotes, whitespace, indentation, and attribute ordering. Only the sample path string should change. The current approach:
- Produces enormous git diffs that obscure the actual path change
- May alter XML structure in ways untested against the Deluge hardware
- Makes changes hard to track and review

**Fix:** Replace `lxml` tree serialization with targeted string replacement that only modifies the path value, leaving the rest of the file byte-identical.

## Bugs

### 2. Recovered XML silent skip
When an XML file triggers the recovery parser (3rd fallback in `parse_deluge_xml`), `update_sample_refs` detects matching references, increments the count internally, but then silently returns 0 without writing the file. Meanwhile, `extract_sample_refs` discards the `recovered` flag, so these refs appear normal during detection.

**Result:**
- Preview shows planned changes for the file
- Apply silently skips writing
- "Applied: N files modified" underreports with no warning
- User believes changes were applied but they weren't

**Fix:** Either warn the user during preview that a file cannot be auto-fixed (recovered XML), or find an alternative write strategy for recovered files.

## Minor

### 3. `list_samples.py` missing entry point
`list_samples.py` has no `[project.scripts]` entry in `pyproject.toml`, so it requires `uv run python list_samples.py` instead of a clean `uv run deluge-list` like the other scripts.

**Fix:** Add entry point to `pyproject.toml`.
