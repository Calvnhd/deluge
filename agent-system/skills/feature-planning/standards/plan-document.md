# Plan Document Standard

Template and format rules for feature plan documents produced by the Feature Planner agent.

---

## Quick Reference

| Item | Rule |
|------|------|
| **Location** | `docs/plans/` at repository root |
| **Filename** | `<feature-name>-plan.md` (lowercase, hyphens, descriptive) |
| **Template** | Use the template below |

## Naming Convention

**Format:** `<feature-name>-plan.md`

**Rules:**
- Lowercase with hyphens only
- Feature name should match the corresponding research document (e.g., `sample-migration-research.md` → `sample-migration-plan.md`)
- No dates in filenames — versioning is handled by git

**Examples:**
```
✓ sample-migration-plan.md
✓ xml-reference-updater-plan.md
✓ sd-card-sync-plan.md
✗ Plan_SampleMigration.md        (uppercase, underscores, wrong format)
✗ 2025-03-26-sample-migration.md (date prefix, missing -plan suffix)
```

## Required Sections

Every plan document MUST include all of the following sections:

### 1. Title and Metadata

```markdown
# Plan: {Feature Name}

> **Document Type:** Plan
> **Date:** {DD MMMM YYYY}
> **Research:** [{feature-name}-research.md](../research/{feature-name}-research.md)
> **Pipeline:** Research → **Plan** → Implement
> **Status:** Draft | Approved | In Progress | Complete
```

### 2. Executive Summary

A 2-4 sentence overview of the plan: what will be built, the chosen approach, and the expected scope. Must reference the research recommendation.

### 3. Research Summary

Brief summary of key research findings that inform this plan:
- Recommended approach from research (with citation)
- Key constraints and considerations identified
- Existing assets to leverage (from research's Existing Assets Analysis)

### 4. Decisions Log

All technical decisions made during planning, with rationale. This is a key section — it documents WHY choices were made.

**Required format:**

```markdown
| ID | Decision | Rationale | Alternatives Considered |
|----|----------|-----------|------------------------|
| D1 | {What was decided} | {Why this choice was made} | {What else was considered} |
```

### 5. Technical Specification

Detailed technical design covering:

#### 5a. Language and Tooling

| Item | Choice | Notes |
|------|--------|-------|
| Language | {language} | {Reference to language standard if applicable} |
| Package Manager | {tool} | |
| Linter/Formatter | {tool} | |
| Test Framework | {tool} | |
| Key Dependencies | {list} | {Version constraints if any} |

#### 5b. Architecture

- Overall structure (modules, scripts, services)
- Key design patterns used
- File and directory structure (planned layout)

#### 5c. Interface Design

- **Inputs** — CLI arguments, config, environment variables, file inputs
- **Outputs** — Files produced, console output, logs
- **Error Handling** — Strategy and user-facing error messages
- **User Interaction** — Interactive prompts, dry-run defaults, confirmation requirements

#### 5d. Integration Points

- How this integrates with existing code
- Shared utilities used or created
- SD card safety compliance notes

### 6. Cross-Cutting Concerns

How this plan addresses cross-cutting concerns identified in the research:
- Each concern from the research document should be addressed with the planned mitigation
- Any new cross-cutting concerns identified during planning

### 7. Risk Mitigation

How this plan addresses risks identified in the research:

| Risk (from Research) | Plan Mitigation | Residual Risk |
|---------------------|-----------------|---------------|
| {Risk} | {How the plan addresses it} | {Any remaining risk} |

### 8. Implementation Roadmap

The phased task breakdown. This is the living section that the Implement agent will use and update.

**Required format:**

```markdown
## Phase 1: {Phase Name}

> **Goal:** {What this phase accomplishes}
> **Prerequisites:** {What must be true before starting}

### Task 1.1: {Task Title}

- **Description:** {What this task accomplishes}
- **Inputs:** {What's needed}
- **Outputs:** {What's produced}
- **Acceptance Criteria:**
  - [ ] {Criterion 1}
  - [ ] {Criterion 2}
- **Implementation Notes:**
  > {Space for the Implement agent to add notes during execution}
```

For tasks with sub-tasks:

```markdown
### Task 2.1: {Task Title}

- **Description:** {What this task accomplishes}

#### Sub-task 2.1.1: {Sub-task Title}
- **Description:** {What this sub-task accomplishes}
- **Acceptance Criteria:**
  - [ ] {Criterion 1}
- **Implementation Notes:**
  > {Space for notes}
```

### 9. Progress Tracker

A high-level progress view intended to be updated as implementation proceeds:

```markdown
| Phase | Status | Tasks Complete | Notes |
|-------|--------|---------------|-------|
| Phase 1: {Name} | Not Started / In Progress / Complete | 0/{total} | |
| Phase 2: {Name} | Not Started | 0/{total} | |
```

### 10. Open Questions

Any questions that remain unresolved after planning. Format matches the research document:

```markdown
1. **{Question}?**
   - **Impact:** {Why this matters for implementation}
   - **Recommendation:** {Suggested answer}
   - **Blocking:** Yes / No
   - **Resolution:** {To be filled during implementation}
```

### 11. References

All sources consulted, organised by category:

```markdown
### Research Document
- [{feature-name}-research.md](../research/{feature-name}-research.md) — Primary input

### Standards Applied
- [{standard}]({path}) — {How it applies}

### Project Files
- [{filename}]({path}) — {Why referenced}
```

### 12. Change Log

Track modifications to the plan after initial creation:

```markdown
| Date | Change | Reason |
|------|--------|--------|
| {DD MMM YYYY} | Initial plan created | — |
```

## Document Principles

1. **Actionable** — Every section should drive implementation forward. No filler.
2. **Traceable** — Decisions cite research, tasks cite decisions, everything links back.
3. **Living** — The document is designed to be updated during implementation. Checklists, notes sections, and the progress tracker are there to be used.
4. **Self-contained** — The Implement agent should be able to execute from this document without needing the research document (though it's linked for reference).
5. **Right-sized** — Task granularity matches the feature scope. A small feature may have 3-5 tasks. A large feature may have 30+. No artificial inflation or compression.
6. **Decision-transparent** — Every decision documents its rationale and alternatives. Future readers can understand WHY, not just WHAT.
