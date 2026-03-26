---
name: skill-writer
description: 'Create new skills, modify and improve existing skills, and translate existing prompts or agent instructions into reusable skills. Use when users want to create a skill from scratch, update or optimize an existing skill, convert an existing workflow or prompt into a skill, or bootstrap a set of skills for their project.'
---

# Skill Writer

Create new skills and iteratively improve them for use in VS Code with GitHub Copilot.

The core loop is simple:

1. Understand what the user wants the skill to do
2. Draft the SKILL.md
3. The user tests it by asking Copilot to perform a task that should trigger the skill
4. Review the output together, refine, repeat

Your job is to figure out where the user is in this process and help them move forward. Maybe they have a rough idea, maybe they have an existing prompt or workflow to convert, maybe they already have a draft that needs improvement. Meet them where they are.

---

## Creating a Skill

### Capture Intent

Start by understanding what the user wants. The current conversation might already contain a workflow they want to capture (e.g., "turn this into a skill"). If so, extract what you can from history first - the tools used, the sequence of steps, corrections made, input/output formats observed. The user fills the gaps and confirms before you proceed.

Key questions to answer:

1. What should this skill enable Copilot to do?
2. When should this skill trigger? (what user phrases/contexts)
3. What is the expected output format?
4. Are there existing prompts, instructions, or workflows to use as a starting point?

### Interview and Research

Proactively ask about edge cases, input/output formats, example files, success criteria, and dependencies. Look at existing skills in `.github/skills/` to understand the project's conventions and avoid overlap.

If the user is translating an existing prompt or agent instruction into a skill, read the source material carefully. Identify the core intent, strip out environment-specific details, and restructure the content to fit the skill format.

### Write the SKILL.md

Based on the interview, create the skill with these components:

- **name**: Skill identifier (kebab-case)
- **description**: What the skill does AND when to trigger it. This is the primary triggering mechanism - Copilot decides whether to consult a skill based on this field. Be specific about contexts where the skill applies. Err on the side of being slightly "pushy" with trigger conditions, because the model tends to under-trigger rather than over-trigger.

  Instead of: *"Create documentation for C# code."*
  Prefer: *"Ensure that C# types are documented with XML comments and follow best practices for documentation. Use whenever the user asks to document, add XML comments, or improve documentation on C# code."*

- **body**: The instructions themselves, in markdown.

---

## Skill Anatomy

```
skill-name/
+-- SKILL.md (required)
|   +-- YAML frontmatter (name, description required)
|   +-- Markdown instructions
+-- Bundled Resources (optional)
    +-- references/ - Docs loaded into context as needed
    +-- assets/     - Files used in output (templates, etc.)
```

Skills live in `.github/skills/<skill-name>/SKILL.md`.

### Progressive Disclosure

Skills load in layers:
1. **Metadata** (name + description) - always visible to Copilot (~100 words)
2. **SKILL.md body** - loaded when the skill triggers (aim for <500 lines)
3. **Bundled resources** - loaded on demand via explicit `read_file` instructions in the body

Keep the SKILL.md focused. If it is growing past 500 lines, move reference material into a `references/` subdirectory and point to it from the body with guidance on when to read each file.

### Domain Organization

When a skill supports multiple domains or frameworks, organize reference material by variant:

```
my-skill/
+-- SKILL.md (workflow + selection logic)
+-- references/
    +-- variant-a.md
    +-- variant-b.md
```

The SKILL.md tells Copilot which reference file to read based on context.

---

## Writing Guide

### Principles

1. **Explain the why.** Today's models are smart. Rather than rigid ALWAYS/NEVER rules, explain the reasoning behind instructions. The model can generalize from good reasoning better than it can follow brittle rules.

2. **Keep it lean.** Every instruction should earn its place. If something is not contributing to better output, cut it.

3. **Use the imperative form.** Write instructions as direct commands: "Use `<summary>` to provide a brief description" rather than "You should use `<summary>` to provide a brief description."

4. **Be concrete.** Include examples of good output. Show the format you want, don't just describe it.

5. **Generalize, don't overfit.** Skills will be used across many different prompts. Write instructions that work broadly, not just for the examples you tested with.

### Formatting Patterns

**Output templates:**
```markdown
## Report structure
Use this template:
# [Title]
## Executive summary
## Key findings
## Recommendations
```

**Examples:**
```markdown
## Commit message format
**Example 1:**
Input: Added user authentication with JWT tokens
Output: feat(auth): implement JWT-based authentication
```

### What Makes a Good Description

The `description` field in the frontmatter is critical - it is what Copilot uses to decide whether to consult the skill. A good description:

- States what the skill does
- Lists specific trigger contexts (user phrases, file types, task patterns)
- Is broad enough to catch relevant requests but narrow enough to avoid false triggers
- Considers adjacent skills that might compete for the same prompt

---

## Translating Existing Prompts into Skills

When converting an existing prompt, agent instruction, or workflow into a skill:

1. **Read the source material** - understand the full intent, not just the surface instructions
2. **Identify the core behavior** - what is it actually trying to achieve?
3. **Strip environment-specific details** - remove references to specific tools, CLIs, or platforms that don't apply
4. **Restructure for the skill format** - frontmatter + focused body
5. **Preserve domain knowledge** - the valuable part of most prompts is the domain expertise and edge-case handling; keep that
6. **Add trigger context** - the original prompt was invoked manually; the skill needs a description that tells Copilot _when_ to use it

---

## Testing and Iteration

Testing happens conversationally in VS Code. The loop is:

1. **Draft the skill** and save it to `.github/skills/<name>/SKILL.md`
2. **Suggest 2-3 test prompts** - realistic things a user would say that should trigger the skill. Share them with the user for confirmation.
3. **The user tests** by starting a new Copilot chat and using one of those prompts
4. **Review together** - did the skill trigger? Did it produce good output? What is missing?
5. **Refine** - update the SKILL.md based on what you learned
6. **Repeat** until the user is happy with the results

### Common Issues

- **Skill does not trigger**: The description probably does not match the user's phrasing well enough. Broaden the trigger contexts.
- **Skill triggers but output is wrong**: The body instructions need adjustment. Look at what Copilot actually did and figure out where the instructions led it astray.
- **Skill triggers when it should not**: The description is too broad. Narrow the trigger contexts or add exclusions.
- **Output is inconsistent**: Add more concrete examples or tighten the output format specification.

---

## Bootstrapping Multiple Skills

When helping a user set up several skills at once:

1. **Inventory first** - list all the skills they want, with a one-line description of each
2. **Check for overlap** - identify skills that might compete for the same prompts and decide on clear boundaries
3. **Prioritize** - start with the skills the user will use most often or that are easiest to get right
4. **Draft in batches** - write 2-3 skills, let the user test them, then move to the next batch
5. **Review the full set** - once all skills exist, review the descriptions together to make sure triggering is clean across the set

---

## Improving Existing Skills

When iterating on a skill that already exists:

1. **Understand the problem** - what is not working? Get specific examples of bad output.
2. **Read the current skill** - understand what it is telling Copilot to do.
3. **Trace the failure** - is the issue in the description (triggering) or the body (behavior)?
4. **Make targeted changes** - resist the urge to rewrite everything. Change one thing, test, repeat.
5. **Generalize from feedback** - if the user says "it didn't include X in this case," think about whether the fix should be specific ("always include X") or general ("consider the full context of the request"). Prefer general.
 `eval-viewer/generate_review.py` to help the user review them
  - Run quantitative evals
- Repeat until you and the user are satisfied
- Package the final skill and return it to the user.

Please add steps to your TodoList, if you have such a thing, to make sure you don't forget. If you're in Cowork, please specifically put "Create evals JSON and run `eval-viewer/generate_review.py` so human can review test cases" in your TodoList to make sure it happens.

Good luck!eval-viewer/generate_review.py` to help the user review them
  - Run quantitative evals
- Repeat until you and the user are satisfied
- Package the final skill and return it to the user.

Please add steps to your TodoList, if you have such a thing, to make sure you don't forget. If you're in Cowork, please specifically put "Create evals JSON and run `eval-viewer/generate_review.py` so human can review test cases" in your TodoList to make sure it happens.

Good luck!