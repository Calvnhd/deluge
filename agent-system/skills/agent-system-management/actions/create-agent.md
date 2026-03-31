# Create Agent

## Purpose

Scaffold a new agent definition file with correct frontmatter, structure, and conventions.

---

## Flow

### Step 1: Gather Requirements 🛑

**Goal:** Understand the agent's domain, responsibilities, and tool needs.

Ask:

| Area | Question |
|---|---|
| **Domain** | "What domain will this agent specialise in?" |
| **Capabilities** | "What tasks should this agent be able to perform?" |
| **Skill** | "Does an existing skill cover this domain, or do we need a new one?" |
| **Tools** | "What tools does this agent need? (search, edit, execute, read, web, etc.)" |
| **Model** | "Which model should back this agent?" |

**🛑 STOP**: Wait until domain, capabilities, and tool requirements are clear.

**Success Criteria:**
- [ ] Agent domain and name identified
- [ ] Capabilities listed
- [ ] Associated skill identified (existing or new)
- [ ] Tool requirements determined

---

### Step 2: Validate Name

Check against `standards/conventions.md` naming rules:

- [ ] Lowercase with hyphens only
- [ ] 2-5 words, descriptive
- [ ] Filename: `{name}.agent.md`
- [ ] No collision with existing agents in `.github/agents/`

---

### Step 3: Scaffold Agent File

Create `.github/agents/{name}.agent.md` using this structure:

```markdown
---
description: {One-line description}
name: {agent-name}
tools: [{tools}]
model: {model}
---

# {Agent Display Name}

## Overview

{1-2 sentences describing the agent's role.}

## Skill

Load the {Skill Name} skill from `agent-system/skills/{skill-name}/SKILL.md`...

| Capability | Description |
|---|---|
| {Name} | {Description} |

## Response Format

Structure responses with:

1. **Summary** — ...
2. **Details** — ...
3. **Next Steps** — ...
```

---

### Step 4: Update Routing

Run the Sync Routing action (`actions/sync-routing.md`) to add the new agent to the `AGENTS.md` routing table.

---

### Step 5: Scaffold Skill (if needed) 🛑

If no existing skill covers this agent's domain:

**🛑 STOP**: Ask the user whether to scaffold a new skill now.

If yes, hand off to the Create Skill action (`actions/create-skill.md`).

**Success Criteria:**
- [ ] Agent file created at `.github/agents/{name}.agent.md`
- [ ] Frontmatter is valid (name, description, tools, model)
- [ ] Routing table updated in `AGENTS.md`
- [ ] Associated skill exists or has been created
