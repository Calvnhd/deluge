---
name: feature-planning
description: Transform research documents into actionable implementation plans with technical specs, phased task breakdowns, and living checklists
---

# Feature Planning Skill

## Purpose

This skill transforms research documents into structured, actionable implementation plans. It guides the agent through research review, gap analysis, technical design, and task decomposition to produce a single authoritative plan at `docs/plans/<feature-name>-plan.md`. This document serves as the sole input to the Implement agent in the research → plan → implement pipeline.

## Configuration

### Capabilities

| Capability | Action | Description |
|------------|--------|-------------|
| Plan | `actions/plan.md` | Create an actionable implementation plan from a research document |

### Bundled Standards

| Standard | File | Description |
|----------|------|-------------|
| Plan Document | `standards/plan-document.md` | Template and format rules for the output plan document |
| Planning Process | `standards/planning-process.md` | Rules governing how planning is conducted |

### Customisable Standards

This skill references the following shared project standards:

| Standard | File | Description |
|----------|------|-------------|
| Project | `standards/project.md` | SD Card safety and project-wide rules |

### Key System Context

The planning agent operates within a multi-repository workspace:

| Resource | Path | Purpose |
|----------|------|---------|
| Research Documents | `docs/research/` | Input research documents from the Research agent |
| Plans | `docs/plans/` | Output location for plan documents |
| SD Card Backup | `DELUGE/` | Deluge SD card contents (referenced for context, not modified) |
| Project Docs | `docs/` | Existing project documentation |
| Scripts | `scripts/` | Existing scripts and utilities (for understanding current patterns) |
| Standards Index | `agent-system/standards/standards.index.md` | Language and project standards to reference in plans |

## Flow

### Prerequisites

- [ ] Verify `docs/plans/` directory exists (create if missing)
- [ ] Verify research document exists at the specified path
- [ ] Load bundled standards: `standards/plan-document.md`, `standards/planning-process.md`
- [ ] Load project standard: `standards/project.md` (SD Card safety rules)

### Execution Steps

1. Load this skill manifest (`SKILL.md`)
2. Identify the required capability from the Capabilities table above
3. Load bundled standards: `standards/plan-document.md`, `standards/planning-process.md`
4. Load customisable standard: `standards/project.md`
5. Execute the action: `actions/plan.md`
