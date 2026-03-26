---
name: feature-research
description: Research features and topics to produce authoritative documents for downstream planning and implementation
---

# Feature Research Skill

## Purpose

This skill conducts structured research on features, scripts, and topics within the Deluge project. It guides the agent through discovery, codebase investigation, and external research to produce a single authoritative research document at `docs/research/<feature-name>-research.md`. This document serves as the sole input to the Plan agent in the research → plan → implement pipeline.

## Configuration

### Capabilities

| Capability | Action | Description |
|------------|--------|-------------|
| Research | `actions/research.md` | Conduct guided research through discovery, investigation, and synthesis |

### Bundled Standards

| Standard | File | Description |
|----------|------|-------------|
| Research Document | `standards/research-document.md` | Template and format rules for the output research document |
| Research Process | `standards/research-process.md` | Rules governing how research is conducted |

### Customisable Standards

This skill references the following shared project standards:

| Standard | File | Description |
|----------|------|-------------|
| Project | `standards/project.md` | SD Card safety and project-wide rules |

### Key System Context

The research agent operates within a multi-repository workspace:

| Resource | Path | Purpose |
|----------|------|---------|
| SD Card Backup | `DELUGE/` | Deluge SD card contents (KITS/, SYNTHS/, SONGS/, SAMPLES/) |
| Project Docs | `docs/` | Existing project documentation |
| Scripts | `scripts/` | Existing scripts and utilities |
| Firmware Source | `DelugeFirmware/` | Deluge Community Firmware source code |
| Firmware Wiki | `DelugeFirmware.wiki/` | Deluge firmware wiki documentation |
| Firmware Contrib | `DelugeFirmware/contrib/` | Community-contributed tools and scripts |

## Flow

### Prerequisites

- [ ] Verify `docs/research/` directory exists (create if missing)
- [ ] Load bundled standards: `standards/research-document.md`, `standards/research-process.md`
- [ ] Load project standard: `standards/project.md` (SD Card safety rules)

### Execution Steps

1. Load this skill manifest (`SKILL.md`)
2. Identify the required capability from the Capabilities table above
3. Load bundled standards: `standards/research-document.md`, `standards/research-process.md`
4. Load customisable standard: `standards/project.md`
5. Execute the action: `actions/research.md`
