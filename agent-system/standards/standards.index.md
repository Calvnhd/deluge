# Standards Index

## How to Use This Index

This file is the entry point for all shared standards in the agent-system. When you need to apply standards:

1. **Always** load `standards/project.md` first — it contains project-wide rules that apply to all work
2. Identify the relevant standards category below
3. Navigate to the specified path
4. For folder-based standards, read the category files applicable to your task
5. Load all relevant standards before performing work

---

## Project

Project-wide standards that apply to all code and scripts in this repository.

**Path:** `standards/project.md`

| Topic | Description |
|-------|-------------|
| SD Card Safety | Rules preventing accidental modification of the `DELUGE/` backup directory |

---

## Languages

Programming language standards for consistent development practices.

**Path:** `standards/languages/`

**Structure:** Each language has a subfolder containing standardised category files.

### Categories

| Category | Filename | Description |
|----------|----------|-------------|
| Core | `core.md` | Overview, principles, project structure, naming, coding style |
| Tooling | `tooling.md` | Package manager, linter, formatter, LSP, type checker, test framework |
| Security | `security.md` | Prohibited practices, secure practices, language-specific risks |

### Supported Languages

| Language | Path | Description |
|----------|------|-------------|
| Bash | `standards/languages/bash/` | Portable shell scripting with ShellCheck and shfmt |
| Python | `standards/languages/python/` | Modern Python with uv, Ruff, and strict typing |

### Loading Language Standards

When working with a specific language:

1. Read `standards/languages/<language>/core.md` for foundational requirements
2. Load additional category files based on the task:
   - Setting up tooling? Load `tooling.md`
   - Reviewing code? Load `security.md`

---

## Note on Skill-Bundled Standards

Domain-specific standards are bundled with their skills rather than in this shared standards folder.

When working in these domains, load standards from the skill's `standards/` folder instead of looking here.
