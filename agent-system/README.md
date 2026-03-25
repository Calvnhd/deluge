# AI Agent System

## Origins

This system is adapted from the agent system available at https://github.com/mcaps-microsoft/ise-anz-studio-hypervelocity-engineering 

## Architecture

The system uses a three-layer architecture where agents route to skills, which bundle actions and standards:

```mermaid
flowchart TB
    subgraph AgentLayer["Agent (Subagent)"]
        Agent["Orchestrates 1 or more skills based on task requirements"]
    end

    subgraph SkillsLayer["Skills"]
        SkillA["Skill A"]
        SkillB["Skill B"]
    end

    subgraph SkillStructure["Skill Structure"]
        direction TB
        SM["SKILL.md<br/>Manifest"]
        SA["actions/<br/>Executable workflows"]
        SS["standards/<br/>Invariant rules"]
    end

    subgraph SharedStandards["Shared Standards"]
        Standards["Customizable<br/>project/org-specific policies"]
    end

    Agent --> SkillA
    Agent --> SkillB

    SkillsLayer --> SharedStandards

    SkillA -.-> SkillStructure
    SkillB -.-> SkillStructure
```

### Layer Responsibilities

| Layer | Location | Purpose |
|-------|----------|---------|
| **Agents** | `agents/*.md` | Thin routers that orchestrate 1+ skills based on task requirements |
| **Skills** | `skills/<domain>/` | Self-contained capability packages with actions and invariant standards |
| **Standards** | `standards/` | Customizable project/org-specific policies |

## Getting Started

### Using an Agent

When working with an AI assistant, reference the appropriate agent for your task:

| Task | Agent | Example Prompt |
|------|-------|----------------|
| Document a decision | Decision-Record-Expert | "Create a decision record for choosing PostgreSQL" |

## Quick Reference

### Available Agents

| Agent | Skill | Capabilities |
|-------|-------|--------------|
| Decision-Record-Expert | `skills/decision-records/` | create, review |

### Key Files

| File | Description |
|------|-------------|
| [`agent-system/AGENTS.md`](AGENTS.md) | Main routing table and skill references |
| [`agent-system/standards/standards.index.md`](standards/standards.index.md) | Index of all shared standards |
