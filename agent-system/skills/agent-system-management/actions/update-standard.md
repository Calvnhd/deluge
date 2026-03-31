# Update Standard

## Purpose

Modify an existing standard file — add rules, update examples, or restructure content.

---

## Flow

### Step 1: Locate Standard

Find the standard to update:

| Method | Action |
|---|---|
| User-specified | Use the file path provided |
| Shared | Search `standards/` and check `standards/standards.index.md` |
| Skill-bundled | Search `skills/{skill-name}/standards/` and check the skill's `SKILL.md` |

**Failure:** Standard not found → Recommend Create Standard action.

---

### Step 2: Load Current State

- Read the standard file
- Note current rules, structure, and examples

---

### Step 3: Gather Changes 🛑

Ask:

| Area | Question |
|---|---|
| **Add Rules** | "What new rules need to be added?" |
| **Update Rules** | "Which rules are changing and how?" |
| **Remove Rules** | "Are any rules being deprecated?" |
| **Examples** | "Do examples need updating?" |

**🛑 STOP**: Confirm the specific changes before applying.

---

### Step 4: Apply Changes

- Edit the standard file
- Maintain declarative style (MUST/SHOULD/MUST NOT)
- Preserve table formatting and existing structure where possible

---

### Step 5: Check Downstream Impact

If the standard is skill-bundled, check whether the change affects:

- [ ] Action files that reference these rules
- [ ] The skill's `SKILL.md` description of this standard

If the standard is shared, check whether it's referenced by any skill's Customisable Standards table.

**Success Criteria:**
- [ ] Standard file updated
- [ ] Changes are consistent with referencing actions and manifests
- [ ] Declarative style maintained
