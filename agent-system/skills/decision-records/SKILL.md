---
name: decision-records
description: Create and review architectural decision records
---

# Decision Records Skill

## Purpose

This skill provides capabilities for creating and reviewing architectural decision records (ADRs) through guided discovery and standards compliance.

## Configuration

### Capabilities

| Capability | Action | Description |
|------------|--------|-------------|
| Create | `actions/create.md` | Guide the creation of a decision record through Socratic discovery |
| Review | `actions/review.md` | Analyse an existing decision record for completeness and quality |

### Bundled Standards

| Standard | File | Description |
|----------|------|-------------|
| Core | `standards/core.md` | When to create, naming conventions, required sections, status lifecycle |
| Checklist | `standards/checklist.md` | Validation checklist for decision record completeness |
| Template | `standards/template.md` | Decision record markdown template |

### Index Maintenance

Both capabilities are responsible for maintaining the decision records index at `project/decision-records/decision-records.index.md`:

| Action | Index Update |
|--------|--------------|
| Create | Add new entry to Active Records table |
| Review (status change) | Update status in Active Records table |
| Review (deprecation) | Move entry from Active Records to Deprecated Records table |

## Flow

### Prerequisites

- [ ] Verify `project/decision-records/` directory exists
- [ ] Verify `project/decision-records/decision-records.index.md` is accessible

### Execution Steps

1. Load this skill manifest (`SKILL.md`)
2. Identify the required capability from the Capabilities table above
3. Load bundled standards: `standards/core.md`, `standards/checklist.md`, `standards/template.md`
4. Execute the action: `actions/create.md` or `actions/review.md`
5. Update the index at `project/decision-records/decision-records.index.md` per Index Maintenance rules

