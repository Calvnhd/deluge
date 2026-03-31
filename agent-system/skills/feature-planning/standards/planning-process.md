# Planning Process Standard

Rules governing how the Feature Planner agent conducts planning.

---

## Input Requirements

### Research Document

The plan MUST be based on a research document from `docs/research/`. The planner:
- MUST read the complete research document before starting
- MUST cite the research document in all relevant sections
- MUST address all open questions from the research (resolve, defer with default, or escalate to user)
- MUST NOT conduct independent research beyond querying the user

### Research Sections to Extract

The planner must extract and use information from these research document sections:

| Research Section | How It Informs the Plan |
|-----------------|------------------------|
| Feature Overview | Scope boundaries, inputs/outputs |
| Existing Assets Analysis | What to reuse vs. build new |
| Approaches Considered | Basis for technical decisions |
| Recommendation | Primary approach to plan around |
| Cross-Cutting Concerns | Integration and system-wide considerations |
| Risk Analysis | Risk mitigations to build into the plan |
| Open Questions | Questions to resolve before or during planning |

## Decision-Making Rules

### Autonomous Decisions

The planner SHOULD make autonomous decisions when:
- The research provides a clear recommendation
- The choice is a standard engineering best practice
- The research provides enough context for a well-reasoned decision
- The decision is easily reversible

For every autonomous decision, document:
1. The decision itself
2. The rationale (referencing research findings, standards, or best practices)
3. Alternatives that were considered

### User Consultation Required

The planner MUST consult the user when:
- The research flags a question as blocking
- Multiple approaches are equally viable with significant trade-offs
- The decision has major implications (e.g., language choice, architectural direction)
- The specification is ambiguous and could be interpreted multiple ways
- The decision is hard to reverse once implementation begins

When consulting the user:
1. State the question clearly
2. Explain why it matters
3. Provide a recommendation with reasoning
4. Present alternatives if applicable

### Default Application

When the user defers a question or doesn't have a strong preference:
- Apply the recommended default
- Document the default in the Decisions Log
- Note it as "Default applied — can be revisited during implementation"

## Task Decomposition Rules

### Granularity

- The smallest unit of work (sub-task, or task without subs) should ideally represent no more than a few hours of focused work
- Exception: tasks of a large continuous nature where there is no natural dividing point
- The number of tasks should reasonably match the feature scope — no artificial inflation

### Ordering

- Tasks MUST be ordered so they can be followed sequentially
- Similar work should be grouped together
- Dependencies between tasks must be explicit
- No circular dependencies

### Acceptance Criteria

Every task and sub-task MUST have acceptance criteria that:
- Are specific and verifiable
- Use checkbox format (`- [ ]`) for tracking
- Describe the expected outcome, not the process

### Living Document Provisions

The plan is a living document. The following elements support updates during implementation:

| Element | Purpose |
|---------|---------|
| Acceptance criteria checkboxes | Track completion of individual criteria |
| Implementation Notes sections | Space for the Implement agent to document deviations, discoveries, and decisions |
| Progress Tracker | High-level status view |
| Change Log | Record structural changes to the plan |
| Open Questions Resolution field | Document how questions were ultimately resolved |

## Scope Boundaries

### In Scope

- Technical specification and design decisions
- Task decomposition and ordering
- Risk mitigation planning
- Open question resolution
- Integration point design
- Referencing applicable standards (language, project)

### Out of Scope

- Conducting new research (beyond querying the user)
- Writing implementation code
- Modifying existing code or files (other than creating the plan document)
- Modifying the research document

## Quality Rules

1. **Traceability** — Every decision must reference its basis (research finding, user answer, standard, or best practice)
2. **Completeness** — The Implement agent should be able to start work from the plan alone
3. **Consistency** — Technical choices must be consistent with each other and with existing codebase patterns
4. **Honesty** — If the plan has known weaknesses or areas of uncertainty, document them — don't hide them
5. **SD Card Safety** — All plans involving `DELUGE/` or the physical SD card must comply with `standards/project.md`

## Re-Review Mode

The planner may be invoked mid-implementation by the Implement agent for plan revision. This mode has different rules from initial planning.

### Input Requirements (Re-Review)

Instead of a research document, the planner receives implementation context:

| Input | Description |
|-------|-------------|
| Work completed | Which tasks and phases are done, with implementation notes |
| Reason for re-review | What triggered the review (phase transition, deviation, resolved question, incorrect assumption) |
| Sections to revise | Which plan sections the Implement agent believes need attention |
| New information | Constraints, discoveries, or decisions from implementation |

### Scope Rules (Re-Review)

1. **Preserve completed work** — Do not modify implementation notes, checked acceptance criteria, or other records of completed tasks
2. **Minimise disruption** — Make the smallest changes necessary to address the issue. Avoid restructuring the entire plan when a targeted fix will do.
3. **Maintain traceability** — Every change must reference the implementation context that motivated it
4. **Update the Change Log** — All re-review changes must be recorded
5. **No new research** — The re-review operates on existing information plus implementation findings. Do not investigate the codebase or external sources.

### Decision-Making (Re-Review)

The same autonomous decision and user consultation rules from initial planning apply, with this addition:

- **Consistency with completed work** — Decisions must be consistent with what has already been implemented. If a change would require reworking completed tasks, flag this explicitly to the user.
