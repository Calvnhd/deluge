# Plan

## Purpose

Create a structured, actionable implementation plan from a research document through research review, gap analysis, technical design, and task decomposition.

---

## Flow

### Step 1: Load Research Document 🛑

**Goal:** Identify and load the research document that will inform this plan.

If the user has specified a research document path, load it directly. Otherwise:

1. List files in `docs/research/`
2. Present available research documents
3. Ask the user which research document to plan from

**🛑 STOP**: Wait until a research document is identified and loaded.

After loading, read the complete research document and extract:
- Feature overview and scope
- Recommended approach
- Open questions (especially any marked as blocking)
- Cross-cutting concerns
- Risk analysis
- Existing assets analysis

**Success Criteria:**
- [ ] Research document identified and fully read
- [ ] Key sections extracted and understood

---

### Step 2: Gap Analysis and Open Questions 🛑

**Goal:** Identify gaps in the research and resolve open questions before designing the plan.

#### 2a: Research Gap Analysis

Review the research document for:

| Gap Type | What to Look For |
|----------|-----------------|
| **Missing information** | Are there areas the plan needs that the research doesn't cover? |
| **Ambiguous specs** | Are there requirements that could be interpreted multiple ways? |
| **Untested assumptions** | Does the research make assumptions that haven't been validated? |
| **Stale information** | Has anything changed since the research was conducted? |

#### 2b: Open Question Resolution

Compile all open questions from:
1. The research document's Open Questions section
2. New questions identified during gap analysis

For each open question:
- State the question clearly
- Explain why it matters for the plan
- Provide a recommendation with reasoning
- Indicate whether it blocks planning or can have a default applied

Present all questions to the user grouped by priority:

| Priority | Criteria |
|----------|----------|
| **Critical** | Blocks the plan — cannot proceed without an answer |
| **Important** | Significantly affects the plan design — a default can be applied but user input is preferred |
| **Deferrable** | Can be resolved during implementation — document the recommended default |

**🛑 STOP**: Wait for the user to respond to critical and important questions. Apply recommended defaults for any the user defers.

**Success Criteria:**
- [ ] Research gaps identified and documented
- [ ] All critical questions resolved
- [ ] Important questions resolved or defaults accepted
- [ ] Deferrable questions documented with recommended defaults

---

### Step 3: Technical Design

**Goal:** Make and document all technical decisions required for implementation.

For each area below, make a decision and document the rationale. Reference the research document's findings and the user's answers to open questions.

#### 3a: Language and Tooling

Decide on:
- Programming language (reference `agent-system/standards/standards.index.md` for supported language standards)
- Key libraries and dependencies
- Build and run tooling
- Testing approach

> **Note:** If the applicable language standard exists in `standards/languages/`, reference it in the plan. The implement agent will load the full standard.

#### 3b: Architecture and Patterns

Decide on:
- Overall architecture (scripts, modules, services, etc.)
- Key design patterns
- File and directory structure
- Naming conventions (consistent with existing codebase patterns from research)

#### 3c: Interface Design

Decide on:
- Inputs — CLI arguments, config files, environment variables, file inputs
- Outputs — Files produced, console output, logs, reports
- Error handling strategy
- User interaction model (interactive, batch, dry-run defaults, etc.)

#### 3d: Integration Points

Decide on:
- How this feature integrates with existing code (from research's Existing Assets Analysis)
- Shared utilities or libraries to use or create
- SD card safety compliance (reference `standards/project.md` rules)
- Impact on existing workflows

**Success Criteria:**
- [ ] Language and tooling decided with rationale
- [ ] Architecture and patterns decided with rationale
- [ ] Interface design decided with rationale
- [ ] Integration points identified and approach decided

---

### Step 4: Task Decomposition

**Goal:** Break the implementation into ordered, actionable phases and tasks.

#### 4a: Define Phases

Group work into logical phases that can be completed sequentially. Each phase should represent a coherent unit of work.

Common phase patterns (adapt to the feature):

| Phase | Purpose | Example |
|-------|---------|---------|
| **Setup** | Project scaffolding, tooling, dependencies | Create directory structure, install packages |
| **Core** | Primary feature logic | Build the main script/module |
| **Integration** | Connect to existing systems | Wire up to existing utilities, add to workflows |
| **Polish** | Error handling, validation, documentation | Add edge case handling, write README |
| **Verification** | Testing and validation | Run tests, manual verification |

#### 4b: Define Tasks

Within each phase, define specific tasks. For each task:

| Field | Description |
|-------|-------------|
| **ID** | Phase.Task numbering (e.g., 1.1, 1.2, 2.1) |
| **Title** | Clear, action-oriented description |
| **Description** | What this task accomplishes |
| **Inputs** | What's needed before this task can start |
| **Outputs** | What this task produces |
| **Acceptance Criteria** | How to verify the task is complete |

#### 4c: Define Sub-tasks (when needed)

Break tasks into sub-tasks when:
- A task represents more than a few hours of focused work
- There are natural dividing points within the task
- Different skills or contexts are needed for different parts

Do NOT break tasks into sub-tasks when:
- The work is of a large continuous nature with no natural dividing point
- Breaking it up would create artificial boundaries that reduce clarity

Sub-tasks use the format: Phase.Task.Subtask (e.g., 2.1.1, 2.1.2)

#### 4d: Verify Ordering

Review the full task list and verify:
- [ ] Tasks can be followed in order
- [ ] Similar work is grouped together
- [ ] Dependencies between tasks are explicit
- [ ] No circular dependencies exist
- [ ] The number of tasks reasonably matches the feature scope

**Success Criteria:**
- [ ] Phases defined with clear purpose
- [ ] Tasks decomposed with IDs, descriptions, and acceptance criteria
- [ ] Sub-tasks used where appropriate
- [ ] Ordering verified and dependencies documented

---

### Step 5: Generate Preview 🛑

**Goal:** Present the complete plan document for review.

Generate the plan document using the template from `standards/plan-document.md`:

1. **Filename**: `<feature-name>-plan.md` (lowercase, hyphens, descriptive — matching the research document's feature name)
2. **Location**: `docs/plans/`

Present the COMPLETE plan document for approval:

```
═══════════════════════════════════════════════════════════
📋 PLAN DOCUMENT PREVIEW
═══════════════════════════════════════════════════════════
File: docs/plans/{feature-name}-plan.md

{Full content using standards/plan-document.md}
═══════════════════════════════════════════════════════════

Ready to create this plan document? (yes/no/edit)
```

> ⚠️ **MANDATORY**: Do NOT create the file until user explicitly approves.

**🛑 STOP**: Wait for explicit user approval.

**Success Criteria:**
- [ ] Complete document presented using the template
- [ ] All sections populated
- [ ] User has approved the content

---

### Step 6: Create File

Create the plan document:

1. If `docs/plans/` directory doesn't exist, create it
2. Write the approved content to `docs/plans/<feature-name>-plan.md`
3. If filename conflicts with an existing document, ask the user whether to overwrite or use a new name

**Success Criteria:**
- [ ] File created in `docs/plans/`
- [ ] Filename follows naming convention

---

### Step 7: Confirm and Handoff

Confirm creation and provide pipeline context:

```
✓ Plan document created: docs/plans/{feature-name}-plan.md

Pipeline next steps:
- Invoke the Implement agent with this plan document to begin implementation
- The Implement agent will read this document and execute the phased task list
- As implementation proceeds, the plan document will be updated with progress notes and any deviations
```
