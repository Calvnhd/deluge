# Skills

This directory contains self-contained capability packages that AI agents use to perform domain-specific tasks.

## Structure

Each skill follows a consistent structure:

```
skills/{skill-name}/
├── SKILL.md           # Manifest (entry point)
├── actions/           # Executable workflows
└── standards/         # Invariant domain rules (bundled)
```

## Creating a New Skill

Use the template at [SKILL.template.md](SKILL.template.md) as your starting point.

### Why Config-First?

The template uses a **Config-First** document structure where Configuration sections (Capabilities, Standards, Providers) appear *before* the Flow section. This is intentional.

**Rationale:** AI agents — particularly sequential-processing models like Claude Opus — read documents top-to-bottom. When the Flow section references "the Capabilities table" or "bundled standards", those references should already exist in the agent's context. Forward references (mentioning something before it's defined) increase cognitive overhead and hallucination risk.

**Pattern:**
```
❌ Flow first (forward references)     ✅ Config first (resolved references)
─────────────────────────────────────  ─────────────────────────────────────
## Flow                                ## Configuration
1. See Capabilities table below        ### Capabilities
2. Load standards from Standards       | Create | actions/create.md | ... |

## Capabilities                        ## Flow
| Create | actions/create.md | ... |  1. See Capabilities table above ✓
                                       2. Load standards/core.md ✓
```

### Template Sections

| Section | Purpose |
|---------|---------|
| **Purpose** | Brief description of what the skill does |
| **Configuration** | Tables defining capabilities, standards, and providers |
| **Flow** | Prerequisites (validation gates) + Execution steps |

### Key Requirements

1. **Explicit file paths** — Every reference must include the full path (e.g., `standards/core.md` not "the core standard")
2. **Prerequisites as checklists** — Validation gates use `- [ ]` format
3. **Execution steps as numbered lists** — Sequential steps use `1.`, `2.`, etc.

## Future Enhancement

A **skill-builder** skill may be introduced to automate skill creation with guided discovery. Until then, manually copy and adapt the template.

## Available Skills

| Skill | Capabilities | Description |
|-------|-------------|-------------|
| `feature-research` | Research | Feature investigation and authoritative document production |
| `feature-planning` | Plan, Review | Implementation planning and mid-implementation plan revision |
| `feature-implementation` | Implement | End-to-end feature implementation with 3 interactivity modes |
| `agent-system-management` | Create Agent, Update Agent, Create Skill, Update Skill, Create Standard, Update Standard, Sync | Agent system scaffolding and maintenance |
