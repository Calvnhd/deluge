# Sync

## Purpose

Reconcile all agent system indexes, registries, and manifests with the actual filesystem, ensuring nothing has drifted out of sync.

---

## Scopes

| Scope | Source of Truth | Registry/Index |
|---|---|---|
| **Routing** | Agent files in `agents/` | `AGENTS.md` routing table + `README.md` Quick Reference |
| **Standards Index** | Standard files in `standards/` | `standards/standards.index.md` |
| **Skill Manifests** | Files in each `skills/{name}/actions/` and `skills/{name}/standards/` | Each `skills/{name}/SKILL.md` capabilities and standards tables |
| **Frontmatter** | VS Code UI (tools dropdown, model picker) | `tools` and `model` in each agent's YAML frontmatter |

---

## Flow

### Step 1: Sync Routing

#### 1a. Inventory Agents

List all `.agent.md` files in `agents/`. For each, extract:

- `name` from frontmatter
- `description` from frontmatter
- Associated skill path (from the Skill section body)

#### 1b. Diff Routing Table

Parse the routing table from `AGENTS.md` and compare:

| Status | Meaning |
|---|---|
| **Missing** | Agent exists in `agents/` but has no routing entry |
| **Stale** | Routing entry exists but no matching agent file |
| **Mismatched** | Routing entry exists but skill path or name doesn't match agent file |

#### 1c. Resolve 🛑

For **Missing** entries:

**🛑 STOP**: Ask the user: "What keywords should trigger routing to `{agent-name}`?"

For **Stale** entries: remove the row.

For **Mismatched** entries: update the row to match the agent file.

#### 1d. Update README.md Quick Reference

Ensure the Available Agents table in `README.md` lists every agent with its skill and capabilities.

---

### Step 2: Sync Standards Index

#### 2a. Inventory Standards

List all files in `standards/` (recursively, excluding `standards.index.md` itself).

#### 2b. Diff Standards Index

Parse `standards/standards.index.md` and compare:

| Status | Meaning |
|---|---|
| **Missing** | Standard file exists on disk but has no index entry |
| **Stale** | Index entry exists but no matching file on disk |
| **Mismatched** | Index entry exists but path or description is wrong |

#### 2c. Resolve

- **Missing** → add entry to the appropriate section in `standards.index.md`
- **Stale** → remove entry
- **Mismatched** → update entry

---

### Step 3: Sync Skill Manifests

#### 3a. For Each Skill

List all skill folders in `skills/`. For each:

1. Read `SKILL.md`
2. List files in `actions/`
3. List files in `standards/`

#### 3b. Diff Capabilities Table

| Status | Meaning |
|---|---|
| **Missing** | Action file exists in `actions/` but has no capabilities table entry |
| **Stale** | Capabilities table entry exists but no matching action file |

#### 3c. Diff Bundled Standards Table

| Status | Meaning |
|---|---|
| **Missing** | Standard file exists in `standards/` but has no bundled standards table entry |
| **Stale** | Bundled standards table entry exists but no matching file |

#### 3d. Resolve

- **Missing** → add row to the appropriate table in `SKILL.md`
- **Stale** → remove row from the table

---

### Step 4: Sync Frontmatter 🛑

Agent YAML frontmatter contains `tools` and `model` values that can only be verified against the VS Code UI — there is no programmatic API.

#### 4a. Read Current Frontmatter

For each agent in `agents/`, extract `tools` and `model` from frontmatter.

#### 4b. Compare Against Known Values

Check `tools` values against the Tool IDs table in `standards/conventions.md`. Flag any unrecognised tool IDs.

Check `model` values against the Models table in `standards/conventions.md`. Flag any unrecognised model names.

#### 4c. Prompt User 🛑

**🛑 STOP**: Present findings and ask:

> "I've checked agent frontmatter against the known tools and models in `standards/conventions.md`.
>
> **Tools**: {list any unrecognised or potentially outdated tool IDs}
> **Models**: {list any unrecognised or potentially outdated model names}
>
> Please check the VS Code tools dropdown and model picker for the current values. Let me know if any tools or models need to be added, removed, or renamed — I'll update the agent files and the conventions standard."

#### 4d. Apply Updates

If the user provides updated tools or models:

1. Update the affected agent frontmatter in `agents/`
2. Update the Tool IDs and/or Models tables in `standards/conventions.md`

---

## Success Criteria

- [ ] Every agent in `agents/` has a routing table entry in `AGENTS.md`
- [ ] `README.md` Quick Reference matches actual agents
- [ ] No stale entries in any routing table or index
- [ ] Every standard file in `standards/` is registered in `standards.index.md`
- [ ] Every skill's `SKILL.md` tables match its actual `actions/` and `standards/` files
- [ ] Agent frontmatter `tools` and `model` values verified against known values
- [ ] `standards/conventions.md` Tool IDs and Models tables are current
