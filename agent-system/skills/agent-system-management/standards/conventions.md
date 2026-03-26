# Agent System Conventions

Rules for naming, structuring, and formatting all agent system artefacts.

---

## Directory Structure

```
.github/
└── agents/                   # Agent definitions (VS Code discovery path)
    ├── orchestrator.agent.md # Default mode — routes to specialists
    └── <agent>.agent.md      # Specialist agents

agent-system/
├── AGENTS.md                 # System overview and routing table
├── skills/                   # Skill packages (one folder per skill)
│   ├── SKILL.template.md     # Canonical skill template
│   └── <skill-name>/
│       ├── SKILL.md           # Skill manifest (entry point)
│       ├── actions/           # Executable action workflows
│       └── standards/         # Skill-bundled invariant standards
└── standards/                 # Shared project-wide standards
    └── standards.index.md     # Standards registry
```

---

## Naming Conventions

### General Rules

- Lowercase with hyphens only — no spaces, underscores, or camelCase
- Descriptive but concise — 2-5 words

### Agents

| Item | Convention | Example |
|---|---|---|
| Filename | `{name}.agent.md` | `decision-record-expert.agent.md` |
| Frontmatter `name` | Matches filename stem | `decision-record-expert` |
| Location | `.github/agents/` | `.github/agents/decision-record-expert.agent.md` |

### Skills

| Item | Convention | Example |
|---|---|---|
| Folder name | `{skill-name}/` | `decision-records/` |
| Manifest | `SKILL.md` (always) | `skills/decision-records/SKILL.md` |
| Actions | `{verb or verb-noun}.md` | `actions/create.md`, `actions/review.md` |
| Standards | `{topic}.md` | `standards/core.md`, `standards/checklist.md` |

### Standards (Shared)

| Item | Convention | Example |
|---|---|---|
| Location | `standards/` or `standards/{category}/` | `standards/languages/python/` |
| Filename | `{topic}.md` | `core.md`, `tooling.md`, `security.md` |
| Index | `standards.index.md` (always at `standards/` root) | — |

---

## Agent File Format

```yaml
---
description: {One-line description of what the agent does}
name: {agent-name}
tools: [{tool-list}]
model: {model-name}
---
```

### Required Sections

1. **Overview** — 1-2 sentences describing the agent's role
2. **Skill** — Which skill(s) to load, with path to `SKILL.md` relative to workspace root (e.g., `agent-system/skills/{skill}/SKILL.md`) and capabilities table
3. **Response Format** — How the agent should structure its output

### Tool IDs

Use these built-in tool category IDs in the `tools` list:

| ID | Purpose |
|---|---|
| `agent` | Invoke other agents / subagents |
| `browser` | Browser interaction |
| `edit` | File create, edit, rename |
| `execute` | Terminal commands, terminal output |
| `read` | File reading |
| `search` | Semantic search, grep, file search |
| `todo` | Todo list management |
| `vscode` | VS Code-specific (memory, ask questions) |
| `web` | Fetch web pages |

Extension-contributed tools use `extensionId/toolName` format. Wildcards (e.g., `azure-mcp/*`) are supported.

### Models

Use these model names in the `model` frontmatter field:

| Model | Description |
|---|---|
| `Claude Opus 4.6` | High-capability reasoning model |
| `Claude Sonnet 4` | Balanced capability and speed |
| `GPT-4.1` | OpenAI high-capability model |
| `o4-mini` | OpenAI fast reasoning model |
| `Gemini 2.5 Pro` | Google high-capability model |

> **Maintenance note:** This table is not programmatically discoverable. Run the Sync action periodically — it will prompt you to verify these values against the VS Code model picker.

---

## Skill Manifest Format

```yaml
---
name: {skill-name}
description: {One-line description}
---
```

### Required Sections (Config-First Order)

1. **Purpose** — 2-3 sentences describing the skill
2. **Configuration**
   - **Capabilities** table — maps capability name → action file → description
   - **Bundled Standards** table — lists skill-internal standards
   - **Customisable Standards** table (if applicable) — references shared standards
3. **Flow**
   - **Prerequisites** — checklist of validation gates (`- [ ]` format)
   - **Execution Steps** — numbered steps referencing tables above

### Config-First Rationale

Configuration sections MUST appear before the Flow section. AI agents read top-to-bottom; forward references increase hallucination risk. See `skills/README.md` for details.

---

## Action File Format

### Required Sections

1. **Purpose** — one sentence describing the action
2. **Flow** — numbered steps with:
   - Stop gates (`🛑 STOP`) where user input is required
   - Success criteria checklists (`- [ ]`)
   - Tables for structured information

### Conventions

- Use `###` for step headings (e.g., `### Step 1: Discovery`)
- Include explicit file paths — never use ambiguous references
- Use tables for structured checks and questions

---

## Standards File Format

### Required Sections

1. **Title** — `# {Standard Name}`
2. **Content** — rules, tables, examples organised by topic

### Conventions

- Use tables for rules that map items to requirements
- Include examples of correct and incorrect usage where helpful
- Keep standards declarative — state what MUST/SHOULD/MUST NOT happen

---

## Routing Table

The routing table in `AGENTS.md` maps domains to subagents:

| Column | Content |
|---|---|
| Domain | Short domain name |
| Domain Keywords | Comma-separated trigger phrases |
| Subagent | Agent `name` from frontmatter (backtick-wrapped) |
| Skill | Path to skill folder relative to `agent-system/` |

Every agent MUST have a routing table entry. Run Sync after creating or renaming agents.
