# Sample Scripts Manager — Status Report

> **Date:** 1 April 2026
> **Scope:** Analysis of research, plan, and implementation for the sample management scripts feature

## Current State

### Documents

| Document | Lines | Status |
|----------|-------|--------|
| Research (`docs/research/sample-scripts-research.md`) | 861 | Complete |
| Plan (`docs/plans/sample-scripts-plan.md`) | 617 | Phases 1–2 complete, 3–5 not started |
| Original plan (`docs/scripts-plan.md`) | 111 | Superseded |

### Implementation

| File | Lines | Purpose |
|------|-------|---------|
| `scripts/lib/deluge_sdk.py` | 168 | XML discovery and sample reference extraction |
| `scripts/lib/cli_utils.py` | 43 | Environment loading, confirm prompt |
| `scripts/verify_references.py` | 167 | Reference existence checking, special dir validation |
| **Production total** | **378** | |
| `scripts/tests/test_deluge_sdk.py` | 251 | |
| `scripts/tests/test_cli_utils.py` | 67 | |
| `scripts/tests/test_verify_references.py` | 438 | |
| **Test total** | **756** | 2:1 test-to-code ratio |

61 tests passing. Ruff clean. Phases 1 (shared library) and 2 (reference verifier) are complete.

## Assessment

### The production code is solid

The implementation is clean and well-structured. `deluge_sdk.py` handles all 5 XML reference patterns across 10 firmware versions. The verifier works end-to-end. No complaints about code quality.

### The plan is overengineered for the actual need

The original user need, traced back to `docs/scripts-plan.md`, is:

1. Reorganise samples on disk
2. Fix the broken XML references afterwards
3. Verify nothing is broken before deploying to hardware

That requires **two scripts** (`fix_references.py` and `verify_references.py`) and a shared library. The plan scopes four scripts, a Makefile, and a utility module.

| Component | In plan | Essential? | Notes |
|-----------|---------|-----------|-------|
| `verify_references.py` | Phase 2 ✅ | **Yes** | Safety gate before deploying to hardware |
| `fix_references.py` (snapshot + fix) | Phase 4 | **Yes** | Core value — automates the tedious part |
| `deluge_sdk.py` | Phase 1 ✅ | **Yes** | Shared XML parsing for the above two |
| `cli_utils.py` | Phase 1 ✅ | **Yes** | Env loading, confirm workflow |
| `generate_manifest.py` | Phase 3 | No | "Decision support" — user can inspect the directory and `git status` |
| `sample_utils.py` (hashing, WAV metadata) | Phase 3 | Partially | `hash_file` is needed by the fixer but WAV metadata is manifest-only |
| `sample_usage.py` | Phase 5 | No | Single-sample lookup — `grep` does this |
| `Makefile` | Phase 5 | No | Orchestration for 2 scripts doesn't need a Makefile |
| Unextracted reference detection | Phase 2 ✅ | Marginal | Defensive feature for a scenario that may never occur |

### The phasing serialised work unnecessarily

The plan's 5-phase structure requires the manifest generator (Phase 3) to be built before the reference fixer (Phase 4), because `hash_file` is defined inside `sample_utils.py` which is a Phase 3 deliverable. But hashing has nothing to do with manifests — it's a 6-line function that the fixer needs directly.

The fixer is the core value proposition. It's blocked behind a non-essential script.

### Test volume is disproportionate to value delivered

- 438 lines of tests for a 167-line verifier (2.6:1 ratio for this file alone)
- The plan's own Phase 1 review flagged over-testing (6 tests for a 2-line function, tests verifying stdlib behaviour) but deferred cleanup
- Some tests are effectively testing `Path.is_file()` and `re.findall()`

### The shared data model anticipates the full suite

`SampleRef` carries 6 fields (`path`, `xml_file`, `xml_type`, `preset_name`, `ref_type`, `element_tag`). The verifier and fixer only need `path` and `xml_file`. The additional fields (`preset_name`, `element_tag`, `ref_type`) exist to serve the manifest and usage scripts — scripts that may never be built.

This isn't a refactoring concern (the extra fields don't hurt), but it illustrates how the plan's full-suite scope influenced even the foundational data model.

## Recommendations

### 1. Skip Phase 3, build Phase 4 next

Move `hash_file` into `deluge_sdk.py` or directly into `fix_references.py` (it's 6 lines). Build the reference fixer immediately — it's the core value of this feature.

### 2. Drop Phase 5 scope

`sample_usage.py` and the Makefile add no value for the actual workflow. They can be added later if genuinely wanted.

### 3. Treat the manifest as a separate, future feature

`generate_manifest.py` is useful but independent. If the user wants it after completing a reorganisation, it can be scoped and built then — without blocking the critical path.

### 4. Reduce test ceremony going forward

Phase 4 tests should focus on non-trivial behaviour: migration map computation, ambiguous hash handling, XML write round-trips. Avoid testing stdlib behaviour or writing multiple tests for single-branch functions.

### Net effect

These changes would reduce the remaining work from ~3 phases (manifest, fixer, integration) to ~1 phase (fixer only), delivering a working end-to-end toolset: **snapshot → reorganise → fix → verify**.
