# Implementation Process Standard

Rules governing how the Feature Implementer agent conducts implementation.

---

## Plan Adherence

### Core Rules

1. **Follow the plan** — Implement tasks in the order specified by the plan's Implementation Roadmap. Do not skip, reorder, or merge tasks without explicit user approval.
2. **Match the spec** — Code must conform to the Technical Specification in the plan (language, architecture, patterns, interface design).
3. **Meet acceptance criteria** — Every task's acceptance criteria must be satisfied before marking it complete.
4. **Document everything** — Update the plan document after each completed unit of work.

### What Constitutes a Unit of Work

| Mode | Unit of Work |
|------|-------------|
| Default | One task (or one sub-task if the task has sub-tasks) |
| Learning | One piece as directed by the user (could be a single function, a stub, or a line) |
| Fast | One task (or sub-task) — summarise and update plan, but don't pause |

## Plan Document Updates

### After Each Unit of Work

The following plan sections MUST be updated after completing each unit of work:

| Section | Update |
|---------|--------|
| **Acceptance Criteria** | Check off completed criteria (`- [x]`) |
| **Implementation Notes** | Add a brief summary of work done, files created/modified, and any notable decisions |
| **Progress Tracker** | Update task counts and phase status |

### After Deviations

When deviating from the plan, additionally update:

| Section | Update |
|---------|--------|
| **Change Log** | Add entry with date, description of change, and reason |
| **Implementation Notes** (on affected task) | Describe how the deviation affects this task |
| **Downstream tasks** | Note any impacts on tasks that haven't been started yet |

### After Resolving Open Questions

| Section | Update |
|---------|--------|
| **Open Questions** | Fill in the Resolution field with the answer and how it was decided |

## Communication Rules

### Chat Summaries

After completing each unit of work, provide a chat summary that includes:
1. **What was done** — Brief description of the implementation
2. **Key files** — Files created or modified (with paths)
3. **Decisions** — Any notable decisions made or alternatives weighed
4. **Deviations** — Any departures from the plan (omit if none)

Chat summaries serve two purposes:
- Allow the user to track progress and review work
- Help the user learn and understand the implementation

### Deviation Flagging

Deviations from the plan MUST be:
1. **Explicitly flagged** in chat — do not silently deviate
2. **Explained** — why the plan's approach doesn't work or isn't optimal
3. **Proposed** — what the alternative is and its trade-offs
4. **Approved** — by the user before proceeding (except trivial adjustments like filename casing)
5. **Documented** — in the plan's Change Log and the task's Implementation Notes

### Open Question Resolution

When encountering an open question during implementation:
1. Present the question with context about why it matters now
2. Reference the plan's recommendation (if any)
3. Provide your own recommendation with reasoning
4. Wait for the user's decision
5. Document the resolution in the plan

## Mode-Specific Rules

### Default Mode

- Complete one unit of work at a time
- Provide detailed chat summaries
- **Always pause** after each unit for user review
- The user may ask questions, request changes, or approve before continuing

### Learning Mode

- **Do not implement full tasks autonomously** — work at the user's pace
- Act as a tutor: explain concepts, patterns, and decisions thoroughly
- When reviewing user code:
  - Be constructive and encouraging
  - Explain errors in terms the user can learn from
  - Reference the plan's technical spec and applicable standards
  - Suggest improvements with reasoning, don't just fix silently
- The goal is user understanding, not speed

### Fast Mode

- Implement tasks sequentially without pausing between tasks within the approved scope
- Chat summaries should be more concise (but still present for every task)
- Plan updates are still mandatory for every task
- **Mandatory stop conditions** override the fast mode — always stop for:
  - Significant deviations from the plan
  - Critical bugs or spec gaps
  - Unexpected roadblocks
  - Open questions requiring user input

## Mode Switching

The user may switch between interactivity modes at any time. Mode switches occur during pauses between tasks, invoked by the user's prompt.

### Rules

1. **Timing** — Mode switches happen at task boundaries, during a 🛑 PAUSE. The agent does not interrupt a task in progress to switch modes.
2. **No special protocol** — The user simply states the desired mode (e.g., "switch to learning mode", "let's go fast", "do the next 3 tasks"). The agent acknowledges and proceeds in the new mode.
3. **Fast mode scope** — When switching to Fast mode, the user specifies the scope (next task, next phase, everything remaining). If no scope is given, ask.
4. **State preservation** — All progress, plan updates, and implementation notes carry over. A mode switch does not reset or alter any work done.
5. **Mid-scope switch in Fast mode** — If the agent is executing a Fast mode scope and hits a mandatory stop condition, the user may choose to continue in a different mode rather than resuming Fast mode. This is a normal mode switch.

## Coding Standards

### Standard Loading

Before writing any code:
1. Check the plan's Technical Specification for the language
2. Load `agent-system/standards/languages/<language>/core.md`
3. Load `agent-system/standards/languages/<language>/tooling.md` if setting up tooling
4. Load `agent-system/standards/languages/<language>/security.md` when writing code that handles external input

### SD Card Safety

Per `standards/project.md`:
- Scripts may freely read and write to `DELUGE/` (the repository copy)
- Scripts MUST NOT write to the physical SD card without explicit user confirmation
- When implementing SD card sync features: dry-run must be the default, writes require a `--confirm` flag or interactive prompt

### Code Quality

- Follow the loaded language standards strictly
- Write code that matches existing codebase conventions (as identified in the research and plan)
- Implement error handling as specified in the plan's Interface Design
- Write tests if the plan specifies a testing approach

### Simplicity

The implementer owns implementation decisions. When the plan describes something that could be expressed more simply in code, simplify it — the plan describes *what*, not *how*.

**Data modelling:**
- Prefer built-in types and standard library types over single-field or two-field wrapper classes
- Only create a custom type when there are 3+ fields or it has behaviour beyond data storage
- Do not wrap a standard collection in a class just to add one computed property

**Testing:**
- Tests must cover behaviour, not implementation structure. If removing a test would not let a bug through, the test should not exist.
- Do not test standard library behaviour
- Do not write multiple tests for a trivial function — one test that exercises the meaningful behaviour is enough
- Prioritise tests at system boundaries (CLI entry points, file I/O, parsing) over internal helpers

**General:**
- Prioritise accuracy, safety, and reliability — but achieve them with the simplest correct solution
- Do not add abstraction layers, registries, or plugin architectures unless the plan explicitly requires extensibility
- A function that could be a plain loop should be a plain loop, not a pipeline of map/filter/reduce with helper lambdas

## Plan Re-Review

### When to Trigger

Delegate to the `feature-planner` for re-review when:

| Trigger | Threshold |
|---------|-----------|
| Phase transition | Large features (5+ phases) — evaluate at each phase boundary |
| Critical open question resolved | The resolution significantly changes the plan's assumptions |
| Plan deviation | The deviation affects 2+ downstream tasks |
| Incorrect assumptions | Implementation reveals the plan was based on wrong information |

### How to Delegate

Provide the planner with:
1. A summary of work completed so far (which tasks/phases are done)
2. The specific reason for re-review
3. Which plan sections need revision
4. Any new constraints or information discovered during implementation

### After Re-Review

1. Reload the updated plan document
2. Identify changes from the previous version
3. Adjust current task approach if needed
4. Continue implementation from the current position in the updated plan
