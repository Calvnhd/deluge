# Research

## Purpose

Conduct structured research on a feature or topic through guided discovery, systematic investigation, and synthesis into an authoritative document.

---

## Flow

### Step 1: Feature Discovery 🛑

**Goal:** Develop a thorough understanding of the feature before investigating anything.

Start with ONE of these questions based on context:

- "What feature or capability are you looking to build?"
- "What problem are you trying to solve?"
- "What should be different after this work is done?"

After the initial response, explore systematically:

| Area | Questions |
|------|-----------|
| **Purpose** | "What is the primary goal of this feature? What value does it provide?" |
| **Use Case** | "Walk me through a typical usage scenario. When and how would this be used?" |
| **Inputs** | "What data, files, or user inputs does this feature consume?" |
| **Outputs** | "What does this feature produce? Files, reports, modified data?" |
| **Scope** | "What is explicitly in scope? What is out of scope?" |
| **Users** | "Who will use this — you directly, scripts, other agents, or a combination?" |

**🛑 STOP**: Wait until you can clearly articulate:
- The feature's purpose in one sentence
- The primary use case
- What goes in and what comes out
- What is and isn't in scope

**Success Criteria:**
- [ ] Feature purpose clearly understood
- [ ] Primary use case identified
- [ ] Inputs and outputs defined
- [ ] Scope boundaries established

---

### Step 2: Edge Cases and Clarifications 🛑

**Goal:** Identify gaps, assumptions, and edge cases that may be missed.

Based on your understanding from Step 1, proactively surface potential issues:

| Area | Questions |
|------|-----------|
| **Edge Cases** | "What happens when [specific edge case]? Have you considered [scenario]?" |
| **Error Handling** | "What should happen if [input is missing/malformed/unexpected]?" |
| **Dependencies** | "Does this depend on any existing scripts, libraries, or external tools?" |
| **Interactions** | "Could this affect or be affected by existing functionality?" |
| **Constraints** | "Are there performance, compatibility, or platform constraints?" |
| **Firmware Versions** | "Should this handle differences between firmware versions in XML files?" |

> **Note:** You do not need definitive answers to every question. The goal is to surface considerations so the Plan agent can make informed decisions. Record both answered and unanswered questions.

**🛑 STOP**: Wait for the user to address the most critical questions. Accept "I don't know" or "defer to planning" as valid answers — document them as open questions.

**Success Criteria:**
- [ ] Key edge cases identified and discussed
- [ ] Critical assumptions surfaced
- [ ] Dependency relationships understood
- [ ] Open questions documented with enough context for future decision-making

---

### Step 3: Repository Investigation

**Goal:** Thoroughly analyse the current repository state relevant to this feature.

Conduct all of the following investigations. Adjust depth based on relevance to the feature.

#### 3a: DELUGE/ SD Card Analysis

Examine the SD card backup to understand current state:

- [ ] Directory structure and file organisation
- [ ] XML file formats and variations across firmware versions (check `firmwareVersion` attributes)
- [ ] File naming patterns and conventions
- [ ] Sample path reference patterns in XML files
- [ ] Any relevant content in `MIDIFollow.XML`

**Investigate by:**
- Listing directory contents in `DELUGE/`
- Reading representative XML files from relevant subdirectories (KITS/, SYNTHS/, SONGS/)
- Comparing XML structure across files with different firmware versions
- Searching for patterns relevant to the feature

#### 3b: Existing Code and Scripts

Audit all existing scripts and code:

- [ ] Read every file in `scripts/`
- [ ] Read `scripts/.env.example` for configuration patterns
- [ ] Identify reusable utilities, libraries, or patterns
- [ ] Note coding conventions used in existing scripts

**Record as a capability matrix:**

| Capability | Status | Location | Notes |
|------------|--------|----------|-------|
| {Feature} | ✅ Ready / ⚠️ Partial / ❌ Missing | {path} | {Relevance} |

#### 3c: Existing Documentation

Read all documentation in the project:

- [ ] Read all files in `docs/`
- [ ] Read `docs/scripts-plan.md` for planned but unimplemented scripts
- [ ] Check for relevant information in the root `README.md`
- [ ] Check `AGENTS.md` for relevant context

#### 3d: Firmware and Wiki (when relevant)

Search the firmware source and wiki when the feature involves:
- XML file creation, parsing, or modification
- Deluge hardware features or behaviour
- Sample handling, audio processing, or MIDI
- Any Deluge-specific functionality

**Investigate by:**
- Searching `DelugeFirmware/` for relevant source code
- Checking `DelugeFirmware/contrib/` subdirectories for community tools related to the feature:
  - `analysis/` — analysis scripts and tools
  - `debug/` — debugging utilities
  - `dx7/` — DX7 patch conversion tools
  - `midi_follow/` — MIDI Follow configuration tools
  - `midi-guide-csv2xml/` — MIDI guide CSV to XML conversion
  - `midi2deluge/` — MIDI to Deluge conversion tools
  - `sd_card/` — SD card management utilities
- Searching `DelugeFirmware.wiki/` for documentation
- Reading `DelugeFirmware.wiki/XML-file-format-documentation.md` for XML format details

> **Tip:** For complex or multi-step firmware/codebase searches, consider delegating to a subagent via the `agent` tool for focused, isolated exploration.

**Success Criteria:**
- [ ] SD card structure understood (where relevant)
- [ ] Existing code fully audited
- [ ] Documentation reviewed
- [ ] Firmware/wiki consulted (if applicable)

---

### Step 4: External Research

**Goal:** Gather information from external sources when needed.

Conduct external research when:
- The feature involves third-party libraries, APIs, or tools
- Best practices or established patterns exist for the feature type
- Technical specifications are needed (file formats, protocols, etc.)
- Community resources have relevant information

**Investigate by:**
- Fetching relevant web pages and documentation
- Searching for established patterns for similar tools/scripts
- Checking for existing open-source tools that solve similar problems
- Searching Deluge community resources:
  - Synthstrom Deluge official documentation
  - Deluge community forums and discussions
  - Community firmware documentation and release notes
  - Third-party Deluge tools, utilities, and libraries

> ⚠️ **CRITICAL**: Always verify external information against the actual codebase. External sources may be outdated or inaccurate for this specific project.

**Success Criteria:**
- [ ] External research conducted where needed
- [ ] Sources documented with URLs
- [ ] Information verified against codebase where possible

---

### Step 5: Synthesis and Recommendations

**Goal:** Synthesise all findings into coherent analysis.

Before writing the document, consolidate:

1. **Approaches** — Identify at least one viable approach based on findings. For each approach, document:
   - How it works
   - Pros and cons
   - Dependencies and complexity
   - Fit with existing codebase patterns

2. **Cross-Cutting Concerns** — Analyse how this feature interacts with other parts of the system:
   - Which existing files, scripts, or processes does this feature touch?
   - Could changes break or alter existing behaviour?
   - Are there shared resources (XML schemas, sample paths, naming conventions) that this feature depends on or affects?
   - Does this feature have implications for the SD card sync workflow, backup integrity, or other system-wide concerns?

3. **Risk and Benefit Analysis** — Evaluate risks and benefits:
   - **Benefits** — What value does this feature provide? What problems does it solve? What new capabilities does it enable?
   - **Risks** — What could go wrong? Consider data loss, breaking changes, complexity creep, maintenance burden
   - **Mitigations** — For each identified risk, suggest a mitigation strategy
   - **Reversibility** — How easy is it to undo this change if needed?

4. **Recommendation** — State which approach is recommended and why, considering:
   - Consistency with existing code patterns
   - Complexity vs. value
   - Maintainability and extensibility
   - Risk and reversibility

5. **Open Questions** — Compile all unresolved questions with:
   - The question itself
   - Why it matters
   - A recommended default or suggested answer where possible
   - Whether it blocks planning or can be deferred

**Success Criteria:**
- [ ] At least one viable approach identified with trade-offs
- [ ] Cross-cutting concerns analysed
- [ ] Risks and benefits evaluated
- [ ] Clear recommendation stated with rationale
- [ ] Open questions compiled with context for decision-making

---

### Step 6: Generate Preview 🛑

**Goal:** Present the complete research document for review.

Generate the research document using the template from `standards/research-document.md`:

1. **Filename**: `<feature-name>-research.md` (lowercase, hyphens, descriptive)
2. **Location**: `docs/research/`

Present the COMPLETE research document for approval:

```
═══════════════════════════════════════════════════════════
📋 RESEARCH DOCUMENT PREVIEW
═══════════════════════════════════════════════════════════
File: docs/research/{feature-name}-research.md

{Full content using standards/research-document.md}
═══════════════════════════════════════════════════════════

Ready to create this research document? (yes/no/edit)
```

> ⚠️ **MANDATORY**: Do NOT create the file until user explicitly approves.

**🛑 STOP**: Wait for explicit user approval.

**Success Criteria:**
- [ ] Complete document presented using the template
- [ ] All sections populated with findings
- [ ] User has approved the content

---

### Step 7: Create File

Create the research document:

1. If `docs/research/` directory doesn't exist, create it
2. Write the approved content to `docs/research/<feature-name>-research.md`
3. If filename conflicts with an existing document, ask the user whether to overwrite or use a new name

**Success Criteria:**
- [ ] File created in `docs/research/`
- [ ] Filename follows naming convention

---

### Step 8: Confirm and Handoff

Confirm creation and provide pipeline context:

```
✓ Research document created: docs/research/{feature-name}-research.md

Pipeline next steps:
- Invoke the Plan agent with this research document to create a feature plan
- The Plan agent will read this document and design the implementation approach
```
