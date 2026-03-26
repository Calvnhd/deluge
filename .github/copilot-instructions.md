# Copilot Instructions

## Agent System (MANDATORY)

This repository uses a structured agent system defined in `agent-system/`. Using it is **not optional**.

Before performing ANY task:

1. Read `agent-system/AGENTS.md` to load the routing table and standards system
2. Match the user's request against the routing table keywords
3. If a match is found, **delegate to the specified subagent** — do not handle the task directly
4. If no match is found, load `agent-system/standards/standards.index.md` and apply all relevant standards

**You must not skip this process.** The routing table exists to ensure tasks are handled by specialised agents with isolated context and domain-specific skills. Bypassing it degrades quality.

## SD Card Safety

The `DELUGE/` directory is a local copy of a hardware device's SD card. Editing files in `DELUGE/` is permitted and expected — it is a core purpose of this repository. However, scripts must **never write to the physical SD card** without explicit user confirmation. Full rules are in `agent-system/standards/project.md` — load and follow them for any work involving `DELUGE/`, the SD card, or scripts.
