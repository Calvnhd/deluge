---
name: execution-charts
description: 'Create or update standalone HTML execution flows with nested calls, source filenames, inputs, returns, and optional tier folding. Use when asked to chart execution, trace a call stack or startup/save/load process, or document execution flows for code review and planning. - Brought to you by Calvnhd/mg-toybox'
---

# Execution charts

## Overview

Represent source-verified execution as a continuous, nested HTML call tree. Child calls execute inside their parent; siblings appear in execution order. Use the bundled template so appearance, meaning, and optional folding stay consistent across processes and repositories.

## Prerequisites

* Follow the destination workspace's applicable guidance and ownership boundaries.
* Read the actual source for the requested path, including framework dispatch when it drives execution. Search results and existing diagrams are navigation aids, not implementation evidence.
* No packages, renderer installation, server, build, or application launch is required. Open the generated HTML directly in a browser or VS Code's integrated browser.

## Quick start

```text
/execution-charts trace how preferences load during startup
/execution-charts save the application's execution flow under docs/charts
```

Use [the standalone template](./assets/execution-trace.html). Copy the entire skill folder, including its asset, when moving this skill to another repository.

## Parameters reference

| Input | Default | Purpose |
|-------|---------|---------|
| Process or entry point | Infer from the request and selected code | Bound the path to explain |
| Scenario | Relevant normal path with consequential alternatives | Distinguish actual execution, conditional paths, and unused APIs |
| Output | A process-named HTML file under `docs/charts`, unless directed otherwise | Keep one canonical representation, not parallel Markdown and HTML versions |
| Detail | Fundamental calls, with large subsystems explicitly condensed | Support review and planning without reproducing the implementation |
| Folding | Fully expanded on every load | Allow optional per-call folding and depth 1 / 2 / 3 / All |

## Template reference

No scripts are bundled. The template contains inline CSS and dependency-free JavaScript; generated files must remain self-contained.

Replace every `{{...}}` placeholder before saving:

| Placeholder | Value |
|-------------|-------|
| `{{TITLE}}` | Escaped process title |
| `{{SUMMARY}}` | One short sentence describing the sequence |
| `{{LEGEND}}` | Layer labels using `app`, `library`, and/or `framework` classes |
| `{{TRACE}}` | Nested call/branch markup following the structure below |
| `{{NOTES}}` | Zero or a few essential process-specific `<p>` notes |
| `{{UPDATED}}` | Actual last-updated date in `YYYY-MM-DD` format |

### Tracing and authoring

1. Identify the entry point, scenario, scope, and destination. Reconcile existing edits before changing the artifact. Do not modify application code to explain it.
2. Follow the continuous call path directly. Resolve argument evaluation, constructors and initializers, overloads, inheritance, callbacks, queued work, loops, and returns. In particular, loading performed by a constructor stays inside the factory call that constructs it.
3. Keep the functions that own execution visible: entry points, framework run methods, scheduling loops, and update/draw dispatch are not merely arrows saying "the framework continues." Condense internals that warrant a separate subsystem trace and link that trace where available.
4. Check whether the path has a real caller. Identify an unused API explicitly, without inventing an active caller or implying feature approval.
5. Nest real calls beneath their actual caller, even within the same file. Keep state changes after a child returns at the parent's level. Object construction produces a result; it is not a normal return-valued method. A using scope does not keep its constructor executing.
6. Show inputs and returned outcomes. Use declared signatures with language-appropriate types, or valid call expressions with actual arguments; do not confuse a type with a supplied value. Show `out`/reference outputs, retained state, and important exception paths separately. Return-type badges are not returned values.
7. Label conditions, repeats, early returns, and scheduling boundaries. A static source-derived trace is not a runtime recording, and sibling calls do not imply parallel execution. For genuinely asynchronous work, identify scheduling, continuation, and thread boundaries rather than presenting a false synchronous stack.
8. Copy the template, retain its presentation and folding behavior, and replace its placeholders. Use relative source links within the repository and versioned external links for dependency source where possible. Adapt legend labels to the destination repository; do not hard-code Workshop, MonoGame, local machine paths, or project-specific commands into the reusable format.
9. Keep descriptions brief, bulleted, and free of trailing periods/full stops. Preserve dots in filenames and code names. Do not use `//` comments, phase-jump navigation, pilot labels, or repeated explanations of the format. The footer contains the updated date and only essential notes, not validation logs or a source-link tutorial.
10. When replacing an existing format, update inbound and cross-chart links. Retire superseded files only within the user's authorized scope; do not preserve duplicate representations or create archives merely to retain old layouts.
11. Use lightweight static checks: HTML/list nesting, local links and fragments, script syntax, required metadata, remaining placeholders, and unchanged scope. Do not install rendering tools, launch servers, or initiate browser automation unless the user asks. Report what was actually checked without claiming visual or runtime acceptance.

### Markup structure

```html
<li class="call">
  <div class="call-head">
    <a class="file app" href="../../src/Caller.cs">Caller.cs</a>
    <code class="signature">Run(string path)</code>
    <span class="type">Preferences</span>
  </div>
  <p class="annotation">Load the preferences before starting the application</p>
  <ol class="steps">
    <li class="call">
      <div class="call-head">
        <a class="file app" href="../../src/PreferencesStore.cs">PreferencesStore.cs</a>
        <code class="signature">Load(path)</code>
        <span class="type">Preferences</span>
      </div>
      <div class="return"><span class="kind">Return</span>Validated preferences</div>
    </li>
  </ol>
  <div class="return"><span class="kind">Return</span>The loaded preferences</div>
</li>
```

The example is illustrative, not a claim that those files exist. Replace its links and calls with verified source. Each `li.call` has one direct `div.call-head` containing a filename link and `code.signature`. Put child calls in one direct `ol.steps`; do not put non-list elements directly inside that list.

### Visual meaning

| Element | Meaning |
|---------|---------|
| `.file.app`, green | Application-specific code |
| `.file.library`, purple | Reusable project-library code |
| `.file.framework`, blue | Framework, platform, or standard-library code |
| `.signature` | Monospace function/property signature or actual call expression |
| `.type` | Declared return type; omit for constructors |
| `.annotation` | Muted explanation with a bullet supplied by CSS |
| `.return` with `Return` | Returned outcome |
| `.return` with `Result` | Constructed object |
| `.state` with `State`, `Output`, or `Input` | Non-return state changes, side effects, or argument details |
| `li.branch` with `.condition` or `.repeat` | Conditional execution or repetition, with its own `ol.steps` |
| Nested `ol.steps` | Work performed while the parent call remains active |

Colour identifies ownership or row purpose, not success or severity. Keep textual labels so meaning does not depend on colour alone.

### Folding behavior

* Keep the complete tree visible without JavaScript and fully expanded by default.
* Fold only a call's child `ol.steps`; retain its header, notes, and direct return/result summary.
* Retain per-child fold state when a parent is closed and reopened. Show the number of documented nested calls hidden, not a runtime invocation count.
* Count depth by call nesting, not by condition/repeat wrapper lists. Global depth controls reset the displayed depth; individually folding a call produces a custom state.
* Use keyboard-operable buttons with `aria-expanded`, `aria-controls`, and labelled actions. Keep print output fully expanded and reveal folded ancestors when following an inline fragment link.

## Troubleshooting

* If execution order is unclear, fix nesting and returned control before adding explanatory prose.
* If the page is too dense, condense a genuine subsystem or use the existing folding controls; do not replace the continuous trace with closed per-call accordions.
* If a filename occurs on multiple calls, retain it: different invocations and returns can legitimately revisit a file.
* If a dependency's source version differs from the application's package, identify that limitation rather than implying it is the executed build.
* If source or runtime behavior remains uncertain, label the uncertainty and stop short of invented calls, inputs, outputs, or acceptance claims.

## Attribution

> Brought to you by Calvnhd/mg-toybox
