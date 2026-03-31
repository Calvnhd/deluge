# Update Skill

## Purpose

Modify an existing skill — add or update capabilities, actions, or bundled standards.

---

## Flow

### Step 1: Locate Skill

Find the skill to update:

| Method | Action |
|---|---|
| User-specified | Use the skill name or path provided |
| Search | List skills in `skills/` for user to select |

**Failure:** Skill not found → Recommend Create Skill action.

---

### Step 2: Load Current State

- Read `skills/{skill-name}/SKILL.md`
- List files in `actions/` and `standards/`
- Note current capabilities, standards, and flow

---

### Step 3: Gather Changes 🛑

**Goal:** Understand what needs to change.

| Change Type | Questions |
|---|---|
| **Add Capability** | "What action should it perform? What should the action file be named?" |
| **Update Capability** | "Which capability is changing? What's the new behaviour?" |
| **Add Standard** | "What rules need to be codified? What should the standard file be named?" |
| **Update Standard** | "Which standard is changing? What rules are being added or modified?" |
| **Update Flow** | "Are prerequisites or execution steps changing?" |

**🛑 STOP**: Confirm the specific changes before applying.

---

### Step 4: Apply Changes

For each change:

1. **Add Capability** → create action file in `actions/`, add row to Capabilities table in `SKILL.md`
2. **Update Capability** → edit the action file, update table if description changed
3. **Add Standard** → create standard file in `standards/`, add row to Bundled Standards table in `SKILL.md`
4. **Update Standard** → edit the standard file, update table if description changed
5. **Update Flow** → edit Prerequisites or Execution Steps in `SKILL.md`

---

### Step 5: Verify Consistency

- [ ] Every capability in SKILL.md has a corresponding action file
- [ ] Every standard in SKILL.md has a corresponding standard file
- [ ] No orphan files in `actions/` or `standards/` without manifest entries
- [ ] Config-first ordering preserved in `SKILL.md`

**Success Criteria:**
- [ ] Skill files updated
- [ ] SKILL.md manifest matches actual files
- [ ] No broken references
