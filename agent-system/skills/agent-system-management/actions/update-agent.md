# Update Agent

## Purpose

Modify an existing agent definition — update frontmatter, capabilities, skill references, or response format.

---

## Flow

### Step 1: Locate Agent

Find the agent to update:

| Method | Action |
|---|---|
| User-specified | Use the file path or name provided |
| Search | List agents in `agents/` for user to select |

**Failure:** Agent not found → Recommend Create Agent action.

---

### Step 2: Load Current State

- Read the agent file
- Read its associated skill manifest (`SKILL.md`)
- Note current frontmatter values, capabilities, and response format

---

### Step 3: Gather Changes 🛑

**Goal:** Understand what needs to change.

Ask:

| Area | Question |
|---|---|
| **Frontmatter** | "Do the tools, model, or description need updating?" |
| **Capabilities** | "Are capabilities being added, removed, or renamed?" |
| **Skill** | "Is the skill reference changing?" |
| **Response Format** | "Does the output format need updating?" |

**🛑 STOP**: Confirm the specific changes before applying.

---

### Step 4: Apply Changes

- Update the agent file
- If the agent name changed, update the routing table via Sync Routing (`actions/sync-routing.md`)
- If capabilities changed, verify the associated skill supports them

**Success Criteria:**
- [ ] Agent file updated
- [ ] Frontmatter remains valid per `standards/conventions.md`
- [ ] Capabilities table matches associated skill
- [ ] Routing table is in sync (if name changed)
