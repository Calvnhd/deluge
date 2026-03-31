---
name: feature-implementation
description: Execute plan documents to implement features end-to-end with configurable interactivity, plan tracking, and living documentation
---

# Feature Implementation Skill

## Purpose

This skill executes plan documents to implement features from start to finish. It guides the agent through plan loading, standards setup, and iterative task execution across three interactivity modes (default, learning, fast). The plan document is treated as a living record — updated with progress, notes, and deviations throughout implementation.

## Configuration

### Capabilities

| Capability | Action | Description |
|------------|--------|-------------|
| Implement | `actions/implement.md` | Execute a plan document's task breakdown to build the feature |

### Bundled Standards

| Standard | File | Description |
|----------|------|-------------|
| Implementation Process | `standards/implementation-process.md` | Rules governing how implementation is conducted |

### Customisable Standards

This skill references the following shared project standards:

| Standard | File | Description |
|----------|------|-------------|
| Project | `standards/project.md` | SD Card safety and project-wide rules |
| Standards Index | `standards/standards.index.md` | Registry of language and project standards |

### Key System Context

The implementation agent operates within a multi-repository workspace:

| Resource | Path | Purpose |
|----------|------|---------|
| Plan Documents | `docs/plans/` | Input plan documents from the Plan agent |
| Research Documents | `docs/research/` | Background research (read-only reference) |
| SD Card Backup | `DELUGE/` | Deluge SD card contents (editable per project standards) |
| Scripts | `scripts/` | Target location for new and existing scripts |
| Project Docs | `docs/` | Project documentation |
| Language Standards | `agent-system/standards/languages/` | Language-specific coding standards |
| Firmware Source | `DelugeFirmware/` | Reference for Deluge-specific implementation |
| Firmware Wiki | `DelugeFirmware.wiki/` | Reference documentation |

## Flow

### Prerequisites

- [ ] Verify plan document exists at the specified path
- [ ] Load bundled standard: `standards/implementation-process.md`
- [ ] Load project standard: `standards/project.md` (SD Card safety rules)
- [ ] Identify the language(s) from the plan's Technical Specification
- [ ] Load applicable language standards from `standards/languages/`

### Execution Steps

1. Load this skill manifest (`SKILL.md`)
2. Identify the required capability from the Capabilities table above
3. Load bundled standard: `standards/implementation-process.md`
4. Load customisable standards: `standards/project.md`, applicable language standards
5. Execute the action: `actions/implement.md`
