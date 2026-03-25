# Create Standard

## Purpose

Add a new standard file — either a shared standard in `standards/` or a skill-bundled standard in a skill's `standards/` folder.

---

## Flow

### Step 1: Determine Scope 🛑

Ask: "Is this a **shared** standard (applies project-wide) or a **skill-bundled** standard (domain-specific)?"

| Scope | Location | Index |
|---|---|---|
| Shared | `standards/` or `standards/{category}/` | Must be registered in `standards/standards.index.md` |
| Skill-bundled | `skills/{skill-name}/standards/` | Must be listed in the skill's `SKILL.md` Bundled Standards table |

**🛑 STOP**: Confirm scope and location before proceeding.

---

### Step 2: Gather Content 🛑

Ask:

| Area | Question |
|---|---|
| **Topic** | "What domain or topic does this standard cover?" |
| **Rules** | "What rules need to be codified?" |
| **Examples** | "Are there examples of correct and incorrect usage?" |

**🛑 STOP**: Wait until the rules to codify are clear.

**Success Criteria:**
- [ ] Topic and filename determined
- [ ] Rules to codify are understood
- [ ] Scope (shared vs skill-bundled) confirmed

---

### Step 3: Validate Name

Check against `standards/conventions.md`:

- [ ] Lowercase with hyphens, descriptive
- [ ] Filename: `{topic}.md`
- [ ] No collision with existing standards in the target location

---

### Step 4: Create Standard File

Write the standard file with:

1. **Title** — `# {Standard Name}`
2. **Rules** — tables, lists, examples organised by topic
3. **Examples** — correct/incorrect patterns where applicable

---

### Step 5: Update Index or Manifest

| Scope | Action |
|---|---|
| Shared | Add entry to `standards/standards.index.md` |
| Skill-bundled | Add row to the Bundled Standards table in the skill's `SKILL.md` |

**Success Criteria:**
- [ ] Standard file created at correct location
- [ ] Registered in index (shared) or manifest (skill-bundled)
- [ ] Follows format conventions from `standards/conventions.md`
