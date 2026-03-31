---
name: {skill-name}
description: {one-line description}
---

# {Skill Name} Skill

## Purpose

{2-3 sentences describing what this skill does and when to use it.}

## Configuration

### Capabilities

| Capability | Action | Description |
|------------|--------|-------------|
| {Name} | `actions/{name}.md` | {Description} |

### Bundled Standards

| Standard | File | Description |
|----------|------|-------------|
| {Name} | `standards/{name}.md` | {Description} |

### Customisable Standards

{Description of what customisable standards this skill references and where they are located.}

| Standard | File | Description |
|----------|------|-------------|
| {Name} | `standards/{domain}/{name}.md` | {Description} |

### Providers

{Optional section — include only if skill has platform-specific implementations.}

| Provider | File | Description |
|----------|------|-------------|
| {Name} | `providers/{name}.md` | {Description} |

## Flow

### Prerequisites

{Validation gates that MUST pass before execution proceeds.}

- [ ] {Validation gate 1 — e.g., detect platform/language}
- [ ] {Validation gate 2 — e.g., verify required context is available}

### Execution Steps

1. Load this skill manifest (`SKILL.md`)
2. Identify the required capability from the Capabilities table above
3. Load bundled standards: `standards/core.md`, `standards/checklist.md`
4. Load customisable standards from `standards/{domain}/` if applicable
5. Execute the action: `actions/{capability}.md`
