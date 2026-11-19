# Shared web components (TODO `d34f8ed`) (COMPLETED)

## Summary

Sharing a custom element across widgets only worked for its `.ts` (list it
in `tsconfig.json` "files"); its `<template>` had to be hand-copied from
another widget's `widget.html`, with a top-level-sibling requirement
documented nowhere. Source feedback:
`FEEDBACK-DESK-no-way-to-share-a-real-web-component-across-widgets-only-the-2026-11-13-0052.md`.
Added direction from the user: **two libraries** -- per-desk (dynamic,
mutable) and desk-wide (static, immutable except by changing Desk source).

## Design

- A widget lists `"components": [...]` in `widget.json`.
- A component is a directory `<name>/` with `<name>.ts` and optional
  `template.html` (+ README). Libraries:
  - **desk-wide**: Desk's `shared-components/` (mirrored at
    `.desk_temp/shared-components/`) -- static.
  - **per-project**: `desk_widgets/_shared/components/<name>/` -- mutable.
- Names: `desk:<name>`, `project:<name>`, or bare. Bare prefers the
  project library's copy, else the desk-wide one (changed from "error if in
  both" by TODO b04682e: a vendored project copy must win, and a component a
  later Desk adds must not change an existing build).
- Build: component `.ts` compiled ahead of the widget's own files (via a
  generated `.build/tsconfig.components.json` that `extends` the widget's,
  compiling into a wiped `.build/js/` since tsc's output layout follows the
  inputs' common root); `template.html` injected right after `<body>`, or
  at a `<!-- BUILD:COMPONENT_TEMPLATES -->` marker. A template the page
  already contains is not duplicated (hand-pasted widgets keep working).
- Implemented twice, as the build already is: `desk.custom_widgets`
  (promoted/source widgets) and the generated, self-contained
  `.desk_temp/build_widget.py` (desk-wide library read from its mirror).
  The test runs both and requires byte-identical HTML.
- Staleness: project-library component files join
  `external_source_files`, so editing one marks dependent promoted widgets
  `[STALE]`; `widget.json` edits re-arm the watch. Desk-wide: not watched
  (static).
- Docs: "Reusable UI components" in `tempui-custom-widgets.md` (usage,
  libraries, authoring contract incl. attribute-first APIs so `innerHTML`
  strings work -- the report's secondary point), component READMEs, tag
  `#d34f8ed`, changelog.

## Not done

- No UI/MCP listing of available components; the directory layout and the
  READMEs are the catalog.
- Nothing migrates existing widgets (the old way still works).
- `html_b64`-only `DefineWidget`s with no source directory have no build
  step, so no `"components"`; the manual copy path stays documented.

## Verification

`tests/verify/verify_widget_components.py` (29 checks): resolution rules and
errors; real build of a widget using one desk-wide and one project component
run in a QtWebEngine page; generated `build_widget.py` HTML identical;
no-`files` tsconfigs; marker/duplicate-template/failure cases; watch inputs;
docs. Build, promotion and staleness tests still pass. Not exercised in the
live app.
