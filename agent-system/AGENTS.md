# Agent System

## Overview

This agent system provides a structured approach to AI-assisted development through specialised agents, skills, and standards. The system emphasises isolated context for specific tasks, ensuring optimal token usage and focused expertise.

## Philosophy

- **Specialisation** — Each agent focuses on a specific domain, providing deep expertise
- **Isolation** — Subagents operate with isolated context, reducing noise and improving accuracy
- **Skills** — Self-contained capabilities that agents can invoke, bundling actions with relevant standards
- **Standards** — Codified best practices that ensure consistency across all work

## Structure

```bash
.github/
└── agents/                          # Agent definitions (VS Code discovery path)
    ├── orchestrator.agent.md        # Default mode — routes to specialists
    ├── feature-researcher.agent.md  # Feature pipeline: stage 1 (Research)
    ├── feature-planner.agent.md     # Feature pipeline: stage 2 (Plan)
    ├── feature-implementer.agent.md # Feature pipeline: stage 3 (Implement)
    ├── decision-record-expert.agent.md
    └── agent-system-manager.agent.md

agent-system/
├── AGENTS.md                 # This file — system overview and routing
├── skills/                   # Self-contained skill packages
│   ├── feature-research/     # Research skill (1 action, 2 standards)
│   ├── feature-planning/     # Planning skill (2 actions: plan, review)
│   ├── feature-implementation/ # Implementation skill (1 action, 1 standard)
│   ├── decision-records/     # Decision record skill
│   └── agent-system-management/ # Agent system management skill
└── standards/                # Shared project standards
    ├── standards.index.md    # Standards registry
    ├── project.md            # SD Card safety and project rules
    └── languages/            # Language-specific standards (bash, python)
```

### Why Two Directories?

- **`.github/agents/`** — VS Code's agent discovery path. Files here are automatically registered as invocable agent modes and subagents. This is the **integration** layer.
- **`agent-system/`** — Skills, standards, and documentation. This is the **knowledge** layer. Agents reference skills here by path.

## Standards

Project specific standards are documented in `standards/standards.index.md`.

### Reading Standards

1. Start by reading `standards/standards.index.md` to identify relevant standards
2. The index lists each standards category with its path and structure
3. Navigate to the specified path and load the applicable files
4. For language standards, load only the category files relevant to your task 

### Skill-Bundled Standards

Skills will typically bundle their own standards in `skills/<skill>/standards/`. Each skill will document how it manages precedence across the skill's generalised standards and the project specific standards.

## Routing

**MANDATORY:** When a query matches a specific domain, you **MUST** delegate to the appropriate subagent for isolated, focused processing. Do not attempt to handle the task directly - subagents load skill-specific standards and provide higher quality outcomes.

| Domain           | Domain Keywords                                                                                  | Subagent                 | Skill                            |
| ---------------- | ------------------------------------------------------------------------------------------------ | ------------------------ | -------------------------------- |
| Decision Records | decision record, DR, architectural decision, ADR                                                 | `decision-record-expert` | `skills/decision-records/`       |
| Feature Research | research feature, investigate feature, research topic, feature research, research script         | `feature-researcher`     | `skills/feature-research/`       |
| Feature Planning | plan feature, feature plan, create plan, implementation plan, plan script                         | `feature-planner`        | `skills/feature-planning/`       |
| Feature Implementation | implement feature, implement plan, build feature, execute plan, implement script            | `feature-implementer`    | `skills/feature-implementation/` |
| Agent System     | agent system, create agent, update agent, create skill, update skill, create standard, update standard, sync | `agent-system-manager`   | `skills/agent-system-management/` |

### Orchestrator Enforcement

The `orchestrator` agent mode (`.github/agents/orchestrator.agent.md`) is the recommended default working mode. It deliberately lacks `edit` and `execute` tools, forcing all file modifications to be delegated to specialist subagents. This provides structural enforcement of the routing system.

### How to Route

1. Identify the primary domain of the user's query
2. Match against the keywords in the routing table
3. Delegate to the specified subagent
4. The subagent will load its skill manifest (`SKILL.md`) and relevant standards

### When NOT to Route

- General questions that don't match a specific domain
- Questions spanning multiple domains (handle at orchestrator level)
- Simple queries that don't require specialist knowledge
