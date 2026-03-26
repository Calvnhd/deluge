# Research Process Standard

Rules governing how the Feature Researcher agent conducts research.

---

## Investigation Priorities

Research MUST follow this priority order. Earlier sources take precedence when information conflicts.

| Priority | Source | When to Use |
|----------|--------|-------------|
| 1 | Repository contents (`DELUGE/`, `scripts/`, `docs/`) | Always — this is the ground truth |
| 2 | Firmware wiki (`DelugeFirmware.wiki/`) | When feature involves Deluge functionality, XML, or hardware behaviour |
| 3 | Firmware source (`DelugeFirmware/`, `DelugeFirmware/contrib/`) | When wiki is insufficient or implementation details are needed |
| 4 | External resources (web, documentation) | When internal sources are insufficient |

## Mandatory Investigations

The following investigations MUST be performed for every research task, regardless of feature scope. Depth should be proportional to relevance.

### Repository Investigation

| Investigation | Minimum Requirement |
|---------------|---------------------|
| `DELUGE/` directory structure | List top-level contents; drill into relevant subdirectories |
| XML file analysis | Read at least one representative file from each relevant subdirectory (KITS/, SYNTHS/, SONGS/) |
| `scripts/` audit | Read every file in `scripts/` including `.env.example` |
| `docs/` review | Read every file in `docs/` |
| `docs/scripts-plan.md` | Always read — contains planned but unimplemented script designs |

### Firmware Investigation (when applicable)

| Investigation | When Required | How |
|---------------|---------------|-----|
| XML format documentation | Feature involves XML files | Read `DelugeFirmware.wiki/XML-file-format-documentation.md` |
| XML community changes | Feature involves XML files | Read `DelugeFirmware.wiki/XML-files--‐-community-changes-documentation.md` |
| Contrib tools | Feature overlaps with community tools | Search `DelugeFirmware/contrib/` subdirectories: `analysis/`, `debug/`, `dx7/`, `midi_follow/`, `midi-guide-csv2xml/`, `midi2deluge/`, `sd_card/` |
| Source code | Implementation details needed | Search `DelugeFirmware/src/` for relevant code |

## Clarifying Questions

### Questioning Strategy

1. **Start broad** — Understand the feature at a high level before drilling into details
2. **Surface the non-obvious** — The agent's value is in identifying what the user hasn't considered
3. **Accept uncertainty** — "I don't know" and "defer to planning" are valid answers
4. **Document everything** — Both answered and unanswered questions are valuable research output

### Required Question Areas

Every research session MUST explore these areas (adapt specific questions to the feature):

| Area | Purpose |
|------|---------|
| Purpose and value | Why does this feature exist? What problem does it solve? |
| Use cases | How will this be used? What triggers it? |
| Inputs and outputs | What goes in, what comes out? |
| Scope | What is and isn't included? |
| Edge cases | What happens in unusual situations? |
| Error handling | What happens when things go wrong? |
| Dependencies | What does this need to work? |
| Interactions | What existing functionality does this touch? |

### When to Stop Asking

Stop asking questions when:
- The feature's purpose, inputs, outputs, and scope are clear
- You have enough context to conduct meaningful investigation
- Further questions would be better answered by investigation than by the user
- The user indicates they want to proceed

Do NOT ask questions that can be answered by reading the codebase — investigate those yourself.

## Research Quality Rules

1. **No fabrication** — Only document findings that come from actual investigation. Never invent capabilities, patterns, or file contents.
2. **Source everything** — Every finding must reference a specific file path, URL, or investigation method.
3. **Verify claims** — When external sources make claims about the project, verify against the actual codebase.
4. **Current state only** — Document what exists now, not what might have existed in the past (unless version history is relevant).
5. **Distinguish facts from opinions** — Clearly separate observed facts ("the XML uses `firmwareVersion` attribute") from recommendations ("we should use Python for this script").

## SD Card Safety

Per `standards/project.md`:
- The research agent is **read-only** with respect to `DELUGE/` — it reads and analyses but never modifies SD card contents
- Research may recommend changes to `DELUGE/` contents, but those changes are executed by the Implement agent
- Never recommend scripts that write to the physical SD card without explicit user confirmation mechanisms

## Document Lifecycle

- Research documents are **point-in-time** — they capture the state of investigation at creation
- Research documents are **not updated** after the Plan agent creates a plan (the plan supersedes the research for ongoing work)
- If significant new information emerges, create a **new research document** rather than heavily modifying an existing one
- Minor corrections (broken links, factual errors) may be applied to existing documents
