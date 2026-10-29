
# Pou

`pou` is a project operations CLI that gives humans and agents a shared way to run this repo's commands, check readiness, and record friction.

## Base commands

* `pou help [command]`: List available commands or describe one without executing it. Running `pou` alone also shows help.
* `pou instructions [command]`: Read the general workflow or a command's prerequisites, effects, and limitations.
* `pou version`: Report the installed pou version and Node runtime.
* `pou init`: Create missing `pou.config.mjs`, `AGENTS.md`, and `.pou/friction.md` in the current directory; preserve existing files.
* `pou doctor`: Run configured readiness checks; these are not a substitute for project build or test checks.
* `pou observe "message"`: Append a one-line friction observation to `.pou/friction.md`.

Arguments in brackets are optional. Add `--json` for machine-readable results, or `--help` to read command help without running it. Profiles and repo configuration can add commands; use `pou help` to discover them.

## Use pou

* Run from the repo root; pou loads only that directory's `pou.config.mjs`.
* Discover commands with `pou help`; read `pou instructions <command>` before using an unfamiliar command.
* At the start of a work session, run `pou doctor` to check the repo's configured prerequisites; resolve required failures before running project checks.
* To validate a change through pou, use `pou help` to find a relevant repo or profile command, then run `pou <command>`. The `base` profile provides no build or test commands.
* In pou's result, check `status`, reported targets, and skipped steps; follow `next_action` when present. Success applies only to the checks that command actually ran.
* Record friction with `pou observe "symptom and consequence"` for future review.

## Extend pou

* Add repo-specific commands under `verbs` in `pou.config.mjs`: shell command strings, arrays of commands, or JavaScript functions.
* Select a `profile` and configure its `params`. The `dotnet` profile adds `build`, `test`, and `checks` for explicitly selected targets.
* Add readiness checks under `doctor` and command descriptions under `briefings`.
* Review `.pou/friction.md` for recurring issues; propose a small, tested improvement for human approval before changing shared tooling.

# Repo conventions

* Do not hard-wrap Markdown prose. Keep each paragraph and list items on one source line and rely on VS Code's word wrap. Preserve structural line breaks for headings, lists, tables, and code blocks.
