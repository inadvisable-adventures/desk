# Plan: TODO 05cfccc — extract Mermaid flowchart/state rendering into transforms

See `design-docs/transforms.md`'s "Extracting Mermaid into transforms"
section for the design rationale.

## Sequencing note (deviates slightly from this TODO's own `TODO.md`
text, in favor of never leaving the app in a half-migrated, broken
state between items)

This item adds `desk.mermaid.render_svg` and the two new transform
directories, and leaves `MermaidDiagramWidget` **in place, still
imported and used by `widgets/markdown/widget.py` exactly as today** --
deleting it now, before TODO `a9e2ba7` (part 4/4) actually changes the
Markdown widget's own Mermaid-block handling to stop using it, would
break Mermaid rendering in the running app for the length of time
between these two commits. `MermaidDiagramWidget`'s deletion happens as
part of TODO `a9e2ba7` instead, in the same commit that removes its one
remaining caller.

## Changed files

- **`src/desk/mermaid.py`**: add `render_svg(scene: QGraphicsScene) ->
  str` — new code (nothing here previously ever produced a real SVG
  string; `MermaidDiagramWidget` renders the scene live, directly, with
  no serialization step). Implementation: `PyQt6.QtSvg.QSvgGenerator`
  (a `QPaintDevice`) writing into an in-memory `QBuffer`, driven by a
  `QPainter`, sized/viewboxed to `scene.sceneRect()`; decode the
  buffer's bytes as UTF-8. `parse`/`layout`/`build_scene` and every
  supporting class stay completely untouched.

## New files

- **`desk_transforms/mermaid_flowchart_svg/transform.json`**:
  `{"name": "Mermaid Flowchart to SVG", "kind": "python", "entry":
  "transform.py", "input_type": "mermaid-flowchart", "output_type":
  "svg", "has_config": false, "has_identity": false}`.
- **`desk_transforms/mermaid_flowchart_svg/transform.py`**: `run(text,
  config)` calls `desk.mermaid.parse(text)`, checks
  `diagram.kind == "flowchart"` (raising a clear error otherwise --
  `parse` itself dispatches by header regardless of which transform
  calls it, so this is the one explicit type-guard each transform
  needs; `Diagram.kind` already carries `"flowchart"` | `"state"` for
  exactly this check, no header-regex duplication needed), then
  `layout` (a standalone `measure` callback built from a bare
  `QFontMetricsF(QFont())` — no live widget needed, matching this
  project's offscreen-friendly Qt usage throughout `tests/verify/`) ->
  `build_scene` (a bare `QPalette()`, no live application palette
  needed) -> `render_svg`.
- **`desk_transforms/mermaid_state_svg/transform.json`** /
  **`transform.py`**: identical shape, `input_type: "mermaid-state"`,
  checking `diagram.kind == "state"`.

Both ship at project level (`desk_transforms/`, not `.desk_temp/`) from
day one — built-in Desk behavior, not a user's local experiment (see
design doc).

## Verification

- New `tests/verify/verify_mermaid_svg_transforms.py`:
  - `desk.mermaid.render_svg` produces real, well-formed SVG (`<svg`
    present, parseable) from a real built scene.
  - Both new transform files' `run()` functions called directly
    (`importlib`, not through the full `TransformsService`) against
    real Mermaid flowchart/state source, producing real SVG containing
    expected content (e.g. a node's label text appears somewhere in
    the output — Qt's own SVG generator emits `<text>` elements with
    the rendered string content).
  - Each transform raises for the *other* diagram type's source (the
    flowchart transform given state-diagram source, and vice versa) —
    confirms the `diagram.kind` guard actually works, not just that
    `parse` doesn't crash.
  - Each transform raises `MermaidParseError` (propagated, not
    swallowed) for a genuinely unsupported diagram type (e.g. a
    `sequenceDiagram` header).
  - The same two transforms, this time invoked through the real
    `TransformsService` (discovery finds them under a real
    `desk_transforms/` directory, `run_blocking` executes them) — end
    -to-end, not just unit-testing the bare functions.
- Full `tests/verify/` regression suite.
