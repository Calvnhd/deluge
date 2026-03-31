---
name: agent-system-management
description: Create and update agents, skills, and standards within the agent system
---

# Agent System Management Skill

## Purpose

This skill provides capabilities for managing the agent system — scaffolding new agents, skills, and standards, updating existing ones, and keeping the routing table in sync. It codifies the structural conventions so that all artefacts are consistent.

## Configuration

### Capabilities

| Capability | Action | Description |
|---|---|---|
| Create Agent | `actions/create-agent.md` | Scaffold a new agent definition with correct frontmatter and structure |
| Update Agent | `actions/update-agent.md` | Modify an existing agent definition |
| Create Skill | `actions/create-skill.md` | Scaffold a full skill package (SKILL.md, actions/, standards/) |
| Update Skill | `actions/update-skill.md` | Add capabilities, actions, or standards to an existing skill |
| Create Standard | `actions/create-standard.md` | Add a new shared or skill-bundled standard |
| Update Standard | `actions/update-standard.md` | Modify an existing standard file |
| Sync | `actions/sync.md` | Reconcile routing, standards index, skill manifests, and agent frontmatter with actual state |

### Bundled Standards

| Standard | File | Description |
|---|---|---|
| Conventions | `standards/conventions.md` | Naming, structure, and format rules for all agent system artefacts |

### Customisable Standards

This skill references the following shared resources:

| Resource | File | Description |
|---|---|---|
| Skill Template | `skills/SKILL.template.md` | Canonical template for new skill manifests |
| Standards Index | `standards/standards.index.md` | Registry of all shared standards |

### Key System Files

The routing table and system overview live in `AGENTS.md` at the agent-system root. All capabilities that add or rename agents must update this file.

## Flow

### Prerequisites

- [ ] Verify `agent-system/` directory structure is intact (agents/, skills/, standards/)
- [ ] Load `standards/conventions.md` for naming and format rules
- [ ] Read `AGENTS.md` to understand current routing table state

### Execution Steps

1. Load this skill manifest (`SKILL.md`)
2. Identify the required capability from the Capabilities table above
3. Load bundled standard: `standards/conventions.md`
4. Execute the action from `actions/`
5. If an agent was created or renamed, run Sync (`actions/sync.md`)
