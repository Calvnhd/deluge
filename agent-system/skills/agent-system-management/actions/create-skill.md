# Create Skill

## Purpose

Scaffold a complete skill package — manifest, action stubs, and standards folder — following the config-first template pattern.

---

## Flow

### Step 1: Gather Requirements 🛑

**Goal:** Define the skill's domain, capabilities, and standards needs.

Ask:

| Area | Question |
|---|---|
| **Domain** | "What domain does this skill cover?" |
| **Capabilities** | "What actions should this skill provide? (e.g., create, review, validate)" |
| **Standards** | "Are there invariant rules for this domain that should be bundled?" |
| **Shared Standards** | "Does this skill reference any shared standards from `standards/`?" |

**🛑 STOP**: Wait until capabilities and standards scope are defined.

**Success Criteria:**
- [ ] Skill name and domain identified
- [ ] Capabilities listed with descriptions
- [ ] Bundled standards identified
- [ ] Shared standard references identified (if any)

---

### Step 2: Validate Name

Check against `standards/conventions.md`:

- [ ] Folder name: lowercase with hyphens, 2-5 words
- [ ] No collision with existing skills in `skills/`

---

### Step 3: Scaffold Directory Structure

Create:

```
skills/{skill-name}/
├── SKILL.md
├── actions/
│   └── {capability}.md   (one per capability)
└── standards/
    └── {standard}.md     (one per bundled standard)
```

---

### Step 4: Create Skill Manifest

Use `skills/SKILL.template.md` as the base. Populate:

1. **Frontmatter** — name and description
2. **Purpose** — 2-3 sentences
3. **Capabilities table** — map each capability to its action file
4. **Bundled Standards table** — list each standard file
5. **Customisable Standards table** — reference shared standards if applicable
6. **Prerequisites** — validation gates
7. **Execution Steps** — load manifest → load standards → execute action

---

### Step 5: Create Action Stubs

For each capability, create `actions/{capability}.md` with:

1. **Purpose** — one sentence
2. **Flow** — placeholder steps with `🛑 STOP` gates where user input is needed

Action stubs should follow the patterns in existing actions (see `skills/feature-research/actions/` for reference).

---

### Step 6: Create Standard Stubs

For each bundled standard, create `standards/{name}.md` with:

1. **Title** — `# {Standard Name}`
2. **Placeholder content** — section headings and TODO markers for content

---

### Step 7: Verify Structure

- [ ] `SKILL.md` exists and has valid frontmatter
- [ ] Every capability in the manifest has a corresponding action file in `actions/`
- [ ] Every standard in the manifest has a corresponding file in `standards/`
- [ ] Config-first ordering is followed in `SKILL.md`

**Success Criteria:**
- [ ] Skill directory created with complete structure
- [ ] Manifest references all actions and standards
- [ ] All referenced files exist (even if stubs)
