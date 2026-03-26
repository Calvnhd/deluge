# Research Document Standard

Template and format rules for feature research documents produced by the Feature Researcher agent.

---

## Quick Reference

| Item | Rule |
|------|------|
| **Location** | `docs/research/` at repository root |
| **Filename** | `<feature-name>-research.md` (lowercase, hyphens, descriptive) |
| **Template** | Use the template below |

## Naming Convention

**Format:** `<feature-name>-research.md`

**Rules:**
- Lowercase with hyphens only
- Descriptive of the feature or topic (2-5 words before `-research`)
- No dates in filenames — research documents capture a point-in-time investigation, versioning is handled by git

**Examples:**
```
✓ sample-migration-research.md
✓ xml-reference-updater-research.md
✓ sd-card-sync-research.md
✗ Research_SampleMigration.md        (uppercase, underscores, wrong format)
✗ 2025-03-26-sample-migration.md     (date prefix, missing -research suffix)
```

## Required Sections

Every research document MUST include all of the following sections:

### 1. Title and Metadata

```markdown
# Research: {Feature Name}

> **Document Type:** Research
> **Date:** {DD MMMM YYYY}
> **Request:** {Brief description of the feature request that prompted this research}
> **Pipeline:** Research → Plan → Implement
```

### 2. Executive Summary

A 2-4 sentence overview of findings and recommended direction. Must be useful to a reader with only 30 seconds.

### 3. Objectives

Bullet list of specific questions this research aimed to answer.

### 4. Feature Overview

Clear description of:
- The feature's purpose and value
- Key benefits — what problems it solves and what capabilities it enables
- Primary use case(s)
- Inputs and outputs
- Scope boundaries (in scope / out of scope)

### 5. Existing Assets Analysis

Audit of relevant existing code, documentation, and patterns.

**Required format:**

```markdown
| Capability | Status | Location | Notes |
|------------|--------|----------|-------|
| {Feature} | ✅ Ready / ⚠️ Partial / ❌ Missing | {path} | {Relevance} |
```

### 6. Findings

Organised investigation results. Include subsections as needed:
- SD card analysis findings
- Codebase patterns discovered
- Firmware/wiki insights
- External research results

Each finding MUST cite its source (file path, URL, or investigation method).

### 7. Approaches Considered

At least one viable approach with structured comparison:

```markdown
| Approach | Pros | Cons | Complexity |
|----------|------|------|------------|
| Option A | Benefits | Drawbacks | Low/Medium/High |
```

### 8. Cross-Cutting Concerns

Analysis of how this feature interacts with other parts of the system:
- Which existing files, scripts, or processes are affected
- Shared resources (XML schemas, sample paths, naming conventions) involved
- Implications for SD card sync, backup integrity, or other system-wide workflows

### 9. Risk Analysis

Identified risks with assessment and mitigation:

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| {Risk description} | Low/Medium/High | Low/Medium/High | {Mitigation strategy} |

### 10. Recommendation

Clear statement of the recommended approach with rationale linking back to project constraints, existing patterns, and the risk/benefit trade-offs.

### 11. Open Questions

Unresolved questions requiring decisions. Each question MUST include:
- The question itself
- Why it matters (impact on design/implementation)
- A recommended default or suggested answer where possible
- Whether it blocks planning or can be deferred

**Required format:**

```markdown
1. **{Question}?**
   - **Impact:** {Why this matters}
   - **Recommendation:** {Suggested answer or "Defer to planning"}
   - **Blocking:** Yes / No
```

### 12. References

All sources consulted, organised by category:

```markdown
### Project Files
- [{filename}]({relative-path}) — {How it relates}

### Firmware / Wiki
- [{page}]({relative-path}) — {What was learned}

### External Resources
- [{Title}]({URL}) — {What it provides}
```

### 13. Next Steps

What should happen after this research, specifically referencing the pipeline:

```markdown
1. Review this document and resolve any blocking open questions
2. Invoke the Plan agent to create a feature plan from this research
```

## Optional Sections

Include when relevant:

- **Firmware Compatibility** — Differences across firmware versions if applicable

## Document Principles

1. **Self-contained** — A reader (human or agent) should understand the full context without needing to repeat any investigation
2. **Source-linked** — Every finding cites its source
3. **Decision-ready** — Open questions include enough context for a decision-maker to choose
4. **Honest** — Present trade-offs transparently; do not advocate without acknowledging downsides
5. **Scoped** — Stay focused on the feature being researched; flag related but out-of-scope topics for separate investigation
