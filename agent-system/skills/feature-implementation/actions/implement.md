# Implement

## Purpose

Execute a plan document's phased task breakdown to build a feature end-to-end, updating the plan as a living document throughout.

---

## Flow

### Step 1: Load Plan Document 🛑

**Goal:** Identify and load the plan document that guides this implementation.

If the user has specified a plan document path, load it directly. Otherwise:

1. List files in `docs/plans/`
2. Present available plan documents
3. Ask the user which plan to implement

**🛑 STOP**: Wait until a plan document is identified and loaded.

After loading, read the complete plan document and extract:
- Technical specification (language, tooling, architecture)
- Implementation roadmap (phases, tasks, sub-tasks)
- Progress tracker (current state — what's already done, if any)
- Open questions (any unresolved items)
- Decisions log (for reference during implementation)

**Success Criteria:**
- [ ] Plan document identified and fully read
- [ ] Technical spec understood
- [ ] Current progress state assessed
- [ ] Open questions noted

---

### Step 2: Setup Environment and Standards

**Goal:** Prepare for implementation by loading all applicable standards and verifying the environment.

1. Read the plan's Technical Specification to identify the language and tooling
2. Load the applicable language standard from `agent-system/standards/languages/<language>/core.md`
3. Load additional language standards as needed (`tooling.md`, `security.md`)
4. Load `agent-system/standards/project.md` for SD card safety rules
5. Verify any tooling prerequisites specified in the plan (package managers, linters, etc.)

**Success Criteria:**
- [ ] Language standards loaded
- [ ] Project standards loaded
- [ ] Environment prerequisites verified

---

### Step 3: Determine Interactivity Mode 🛑

**Goal:** Establish the operating mode for this session.

Ask the user which mode to use (if not already specified):

| Mode | Description | When to Use |
|------|-------------|-------------|
| **Default** | Task-by-task with pause for review after each | Standard workflow — balanced autonomy and oversight |
| **Learning** | Piece-by-piece with tutoring and pair programming | User wants to learn and understand deeply |
| **Fast** | Autonomous multi-task execution | User trusts the plan and wants speed |

If the user selects **Fast mode**, ask for the scope:
- "How much should I implement? (e.g., next task, next phase, everything remaining)"

> The user may switch modes at any time. Watch for mode-switch requests.

**🛑 STOP**: Wait for mode selection (and scope if Fast mode).

**Success Criteria:**
- [ ] Interactivity mode established
- [ ] Scope defined (if Fast mode)

---

### Step 4: Resolve Open Questions 🛑 (if any)

**Goal:** Address any blocking open questions before implementation begins.

If the plan has open questions marked as blocking:

1. Present each blocking question to the user
2. Provide the plan's recommended answer and your own assessment
3. Wait for resolution

For non-blocking open questions:
- Note them and resolve as they become relevant during implementation

**🛑 STOP**: Wait if there are blocking open questions.

**Success Criteria:**
- [ ] All blocking open questions resolved
- [ ] Resolutions documented in the plan's Open Questions section

---

### Step 5: Execute Tasks

**Goal:** Implement the feature task by task according to the plan and the active interactivity mode.

For each task in the implementation roadmap:

#### 5a: Read Task

- Read the task description, inputs, outputs, and acceptance criteria
- Identify which files need to be created or modified
- Note any dependencies on previous tasks

#### 5b: Implement (mode-dependent)

**Default Mode:**
1. Implement the task fully:
   - Write code according to the technical spec and language standards
   - Create files in the planned locations
   - Run commands as needed (install dependencies, run tests, etc.)
2. Verify all acceptance criteria are met
3. Summarise the work in chat:
   - What was done
   - Key files created/modified
   - Any notable decisions
   - Any deviations from the plan
4. **Update the plan document:**
   - Check off completed acceptance criteria
   - Add implementation notes
   - Update progress tracker
   - Add to change log if deviations occurred
5. **🛑 PAUSE**: Wait for user review before proceeding to next task

**Learning Mode:**
1. Present the task to the user and explain what needs to be done
2. Wait for the user's direction on how to proceed:
   - Stubs, pseudocode, one section at a time, one line at a time — as requested
3. For each piece of work:
   - Implement the requested piece
   - Explain what it does and why — act as a tutor
   - Answer any questions
4. If the user writes code:
   - Review for correctness, functionality, and plan adherence
   - Provide constructive feedback with clear explanations
   - Correct issues with thorough reasoning
5. After the task is complete through collaboration:
   - Summarise and update the plan as in Default mode
6. **🛑 PAUSE**: Wait for user before proceeding

**Fast Mode:**
1. Implement the task fully (same as Default step 1-2)
2. Provide a brief summary in chat (more concise than Default)
3. Update the plan document (same as Default step 4)
4. **Do NOT pause** — proceed to the next task within the approved scope
5. After completing the approved scope, provide a full summary and **🛑 PAUSE**
6. **MANDATORY STOP** — regardless of scope, stop immediately when:
   - A significant deviation from the plan is needed
   - A critical bug or gap in the spec is discovered
   - An unexpected roadblock is encountered
   - An open question requires user input
   - Explain the situation clearly and await instruction

#### 5c: Handle Deviations

When implementation requires departing from the plan:

1. **Stop** — Do not proceed with the deviation silently
2. **Explain** — Describe what the plan says vs. what is actually needed
3. **Reason** — Why the deviation is necessary
4. **Propose** — The proposed alternative with trade-offs
5. **Document** — After user approval, record the deviation in:
   - The task's Implementation Notes
   - The plan's Change Log
   - Update any affected downstream tasks

#### 5d: Plan Re-Review Trigger

Evaluate whether a plan re-review is needed. Delegate to the `feature-planner` agent when:

- Transitioning between major phases (for large features)
- After resolving critical open questions that significantly affect the plan
- After deviations that affect downstream tasks
- When implementation reveals incorrect assumptions in the plan

To delegate:
1. Prepare context: work completed, current state, reason for re-review
2. Invoke the `feature-planner` agent with this context
3. After re-review completes, reload the updated plan
4. Continue implementation from the updated plan

**Success Criteria (per task):**
- [ ] Task implemented according to plan
- [ ] Acceptance criteria verified
- [ ] Work summarised in chat
- [ ] Plan document updated
- [ ] Deviations documented (if any)

---

### Step 6: Phase Completion

**Goal:** Mark phases complete and assess whether to continue.

After completing all tasks in a phase:

1. Update the progress tracker to mark the phase as Complete
2. Provide a phase-level summary:
   - Tasks completed
   - Key outputs produced
   - Any deviations from the plan
   - State of the feature at this point
3. Evaluate plan re-review trigger (Step 5d)
4. Proceed to the next phase (or pause for review, depending on mode)

**Success Criteria:**
- [ ] Phase marked complete in progress tracker
- [ ] Phase summary provided
- [ ] Re-review evaluated

---

### Step 7: Completion and Handoff

**Goal:** Finalise the implementation and close out the plan.

After all phases are complete:

1. Run a final verification:
   - All acceptance criteria checked off
   - All tests passing (if applicable)
   - No unresolved open questions
2. Update the plan document:
   - Set Status to `Complete`
   - Final entry in Change Log
   - Update all progress tracker entries
3. Provide a final summary to the user:
   - Features implemented
   - Files created and modified
   - Any deviations from the original plan
   - Known limitations or follow-up items

```
✓ Implementation complete: docs/plans/{feature-name}-plan.md

Summary:
- {Key accomplishments}
- {Files created/modified}
- {Any follow-up items}

The plan document has been updated to reflect completion.
```
