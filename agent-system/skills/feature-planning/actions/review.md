# Review

## Purpose

Revise an existing plan document during implementation, incorporating new context from the Implement agent — resolved questions, deviations, incorrect assumptions, or phase transition assessments.

---

## Flow

### Step 1: Load Context 🛑

**Goal:** Understand the current implementation state and reason for re-review.

The Implement agent provides:
1. **Work completed** — Which tasks and phases are done
2. **Reason for re-review** — What triggered this review
3. **Sections to revise** — Which plan sections need attention
4. **New information** — Constraints or discoveries from implementation

If the context is insufficient, ask the Implement agent (via the user) for:
- Current task/phase position in the roadmap
- Specific problems encountered
- Decisions made during implementation that affect the plan

**🛑 STOP**: Wait until context is sufficient to understand the review scope.

Load the existing plan document from `docs/plans/`.

**Success Criteria:**
- [ ] Implementation context received and understood
- [ ] Existing plan document loaded and read
- [ ] Progress tracker state assessed
- [ ] Reason for re-review clearly identified

---

### Step 2: Assess Impact

**Goal:** Determine which plan sections need revision and the scope of changes.

Review the plan against the implementation context:

| Assessment Area | Questions |
|----------------|-----------|
| **Completed work** | Do implementation notes reveal issues with the plan's assumptions? |
| **Remaining tasks** | Are downstream tasks still valid given what's been learned? |
| **Technical spec** | Do any technical decisions need revision? |
| **Task decomposition** | Do remaining tasks need to be re-scoped, reordered, or split? |
| **Acceptance criteria** | Are criteria still appropriate given implementation realities? |
| **Open questions** | Have resolved questions changed the plan's direction? |
| **New risks** | Has implementation revealed new risks not in the original plan? |

Categorise each needed change:

| Change Type | Description |
|-------------|-------------|
| **Correction** | Fix something that was wrong in the original plan |
| **Adaptation** | Adjust the plan based on new information |
| **Extension** | Add new tasks or sections not originally planned |
| **Removal** | Remove tasks that are no longer needed |

**Success Criteria:**
- [ ] All affected sections identified
- [ ] Changes categorised by type
- [ ] Scope of revision understood

---

### Step 3: Resolve New Questions 🛑 (if any)

**Goal:** Address any new questions that arose during implementation.

If the implementation context includes new questions or decisions:

1. Present each question with the implementation context that raised it
2. Provide a recommendation based on:
   - The original research document (if applicable)
   - Implementation findings so far
   - Consistency with completed work
3. Wait for the user's decision

**🛑 STOP**: Wait for user input on any critical or important questions.

**Success Criteria:**
- [ ] New questions identified and presented
- [ ] Critical questions resolved
- [ ] Decisions documented

---

### Step 4: Revise Plan 🛑

**Goal:** Update the plan document with all needed changes.

For each change:

1. **Identify the section** — Which plan section is being modified
2. **State the current content** — What the plan currently says
3. **Propose the revision** — What it should say instead
4. **Explain the rationale** — Why this change is needed, referencing implementation context

Present ALL proposed changes for user approval:

```
═══════════════════════════════════════════════════════════
📋 PLAN REVISION PREVIEW
═══════════════════════════════════════════════════════════
File: docs/plans/{feature-name}-plan.md
Reason: {reason for re-review}

Changes ({count}):

1. Section: {section name}
   Change type: {Correction/Adaptation/Extension/Removal}
   Current: {what it says now}
   Proposed: {what it should say}
   Reason: {why}

2. ...

═══════════════════════════════════════════════════════════

Apply these changes? (yes/no/edit)
```

> ⚠️ **MANDATORY**: Do NOT modify the plan until user explicitly approves.

**🛑 STOP**: Wait for explicit user approval.

**Success Criteria:**
- [ ] All changes presented with rationale
- [ ] User has approved the revisions

---

### Step 5: Apply Changes

**Goal:** Update the plan document.

1. Apply all approved changes to the plan document
2. Update the **Change Log** with an entry for this review:
   ```markdown
   | {DD MMM YYYY} | Plan re-review: {brief reason} | {summary of changes made} |
   ```
3. Update the **Progress Tracker** if task counts or phase structure changed
4. Update **Open Questions** with any newly resolved questions
5. Do NOT modify completed task sections (implementation notes, checked criteria) — those are the Implement agent's records

**Success Criteria:**
- [ ] Plan document updated
- [ ] Change Log entry added
- [ ] Progress Tracker updated (if applicable)
- [ ] Completed task records preserved

---

### Step 6: Handoff Back

**Goal:** Return control to the Implement agent with clear guidance.

Provide a summary:

```
✓ Plan re-review complete: docs/plans/{feature-name}-plan.md

Changes made:
- {List of key changes}

Impact on remaining work:
- {How the changes affect upcoming tasks}
- {Any new tasks added or tasks removed}
- {Changes to technical approach}

The Implement agent should reload the plan and continue from {current position}.
```
