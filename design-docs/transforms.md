# Desk — Transforms

## Goals

- Introduce **transforms**: a new, first-class entity distinct from
  widgets. A transform converts data of one named type into data of
  another named type (`input_type -> output_type`), optionally taking a
  **config** (e.g. "only this subset of the input") and optionally
  exposing an **identity** mapping (a projection tying specific pieces
  of the output back to the input they came from — e.g. "this SVG
  element came from this source line").
- Transforms can be written in **Python**, **TypeScript**, or
  **JavaScript**, and stored in **`.desk_temp/transforms/<name>/`**
  (local/experimental) or **`desk_transforms/<name>/`**
  (project-level, committed) — the same two-tier "try it locally, then
  promote" shape `DefineWidget` custom widgets already use, but *not* a
  copy of that pipeline's mechanics (see "Why not copy the widget
  pipeline verbatim" below) .
- A **Transform Manager** widget lists every discovered transform (name,
  input type, output type, language, whether it has config/identity,
  and where it lives), with a one-click **promote to project-level**
  action for anything currently in `.desk_temp/`.
- A **Desk Service** (`desk_services.transforms`) is the single, shared
  way to actually *run* a transform — reachable by `kind: "python"`
  widgets (`current_context`) and `kind: "html"` widgets (Bridge API)
  alike, the same dual-reachability shape the Popups service already
  established.
- Prove the whole thing out by extracting the Markdown widget's two
  supported Mermaid diagram kinds (flowchart, state) into individual
  transforms (`diagram-type -> svg`, no config/identity for now), and
  switching the Markdown widget to render Mermaid blocks by calling the
  Desk Service instead of embedding `desk.mermaid`'s renderer directly.

## Non-Goals (for now)

- A generic file-type-registry integration. `desk.file_type_registry`
  models "which widget can view/edit/git-diff/consume/produce *this
  file extension/MIME type*" — a single type keyed by extension.
  Transforms model an **(input_type, output_type) pair** of short,
  free-form type tags that often have nothing to do with file
  extensions at all (`"mermaid-flowchart"` isn't a file extension).
  `ROLES`'s existing `"consume"`/`"produce"` strings are confirmed,
  directly in the code, to be unused placeholders today (no
  `find_consume_handler`/`find_produce_handler`, no code branching on
  either role, nothing exposes them) — there's no existing behavior to
  preserve or migrate, and shoehorning transforms into that shape would
  distort both. Transforms get their own, separate registry.
- Config and identity for the concrete Mermaid transforms this doc
  ships. The infrastructure supports both (a transform's manifest
  declares `has_config`/`has_identity`; the execution contract has a
  place for them), but the two Mermaid transforms themselves declare
  `has_config: false, has_identity: false` — per the user's own
  request, "no identity or config for now."
- A generic sandboxing/security model for arbitrary transform code.
  Same trust model as widgets and `DefineWidget` custom widgets today:
  code placed under a Desk's own directories runs with the same
  privileges as the rest of Desk. (One asymmetry *is* new here — see
  "Python only allowed at project level" below — but it's a narrower,
  specific decision, not a general sandboxing effort.)
- Rewriting `desk.mermaid`'s parser/layout engine. It's reused as-is,
  imported by the two new transform files; only a new
  scene-to-SVG-string step is added on top (nothing before today ever
  produced a real SVG from a Mermaid diagram — see below).
- Async/streaming transforms, transform *pipelines* (chaining multiple
  transforms), or a marketplace/sharing mechanism. Straight one-shot
  `input -> output` invocations only.

## Design

### The transform concept

A transform is identified by a `transform_id` (derived from its
directory name, exactly like `widget_id`), and described by a
`transform.json` manifest next to its entry file:

```json
{
  "name": "Mermaid Flowchart to SVG",
  "kind": "python",
  "entry": "transform.py",
  "input_type": "mermaid-flowchart",
  "output_type": "svg",
  "has_config": false,
  "has_identity": false
}
```

- `kind`: `"python"`, `"typescript"`, or `"javascript"`.
- `entry`: the source file to run (`transform.py`, `transform.ts`, or
  `transform.js`), resolved relative to the transform's own directory.
- `input_type`/`output_type`: short, free-form string tags (not file
  extensions or MIME types) — whatever names the transform's own
  producers/consumers agree on. `"svg"`, `"mermaid-flowchart"`,
  `"csv"`, `"json"` are all equally valid; nothing in this system
  interprets them beyond exact string equality when looking a transform
  up by type.
- `has_config`/`has_identity`: declared capabilities, surfaced by the
  Transform Manager and used by callers to know whether it's worth
  passing a `config` / calling `identity()` at all.

A Python transform's `transform.py` exposes:

```python
def run(input_data: str, config: dict | None) -> str: ...
def identity(input_data: str, config: dict | None) -> object: ...  # only if has_identity
```

A TypeScript/JavaScript transform's entry, once resolved to a plain
`.js` file (see "Build pipeline" below), is run directly as a Node
script (`node <entry>.js`) with **no generated harness or wrapper
code** — the script itself is responsible for the whole request/
response protocol, since (unlike a browser-embedded widget) there's no
HTML shell to inject compiled code into and nothing to make
browser-safe. The protocol is a single JSON object read from **stdin**
and a single JSON object written to **stdout**:

Request (stdin):
```json
{"action": "run", "input": "<string>", "config": null}
```
or `{"action": "identity", ...}` for the identity call.

Response (stdout), success:
```json
{"output": "<string>"}
```
or, on failure: `{"error": "<message>"}` (any non-JSON stdout, a
non-zero exit code, or a process that never terminates within a
timeout are all treated as failure too).

`input`/`output`/`config` are always plain strings/JSON-serializable
values (never raw bytes) — keeps both the Python and Node sides of the
contract simple, and covers every transform this doc actually ships
(Mermaid source text in, SVG text out). A future transform genuinely
needing binary data can base64-encode it inside the string; not
designed further here (no current transform needs it).

### Storage & discovery

Two directories are scanned, both directly (no build-artifact
indirection — see below):

- **`.desk_temp/transforms/<name>/`** — local/experimental,
  git-ignored (same `.desk_temp/` semantics as everywhere else in
  Desk). **TypeScript/JavaScript only** — `kind: "python"` is rejected
  here at discovery time (the Transform Manager shows it as an error
  row: "Python transforms aren't allowed in .desk_temp — move to
  desk_transforms/ or rewrite in TS/JS").
- **`desk_transforms/<name>/`** — project-level, committed to the
  repo. Python, TypeScript, or JavaScript all allowed.

On a `transform_id` collision between the two, `desk_transforms/` (the
"promoted"/authoritative location) wins — mirrors "project-level is
more authoritative than the local scratch copy," the same relationship
`desk_widgets/<name>/` (promoted) has to `.desk_temp/widgets/<name>/`
(authoring-only, pre-promotion) today.

**Why Python is disallowed in `.desk_temp/`, but not TypeScript/
JavaScript:** a Python transform runs **in-process** — Desk `import`s
it directly into its own running Python process (see "Execution model"
below), the same trust level as a `kind: "python"` widget. Auto-running
arbitrary, casually-dropped-in code from a git-ignored scratch
directory with full access to Desk's own process is a meaningfully
bigger step than auto-running a TypeScript/JavaScript transform, which
always executes in a **separate OS process** (`node`) with no direct
access to Desk's own memory/objects. Requiring Python transforms to go
through the deliberate "promote to project-level" step (a `.desk`-file
-adjacent, committed, reviewable location) is a small, specific safety
margin — not a general sandboxing claim (see Non-Goals).

**Why not copy the widget authoring pipeline verbatim:** `DefineWidget`
custom widgets' two-stage pipeline (`.desk_temp/widgets/<name>/` as a
pure, *never-auto-scanned* authoring workspace; `build_widget.py`
compiles it and emits a **separate discovered artifact** — a
`DefineWidget` tempui text file — elsewhere in `.desk_temp/`) exists
specifically because a widget must become **tempui-placeable**: the
thing Desk actually discovers and can place on the canvas is the
generated tempui file, not the source directory. Transforms have no
placement concept at all — nothing is ever "placed" on the canvas, a
transform is just invoked programmatically. Adding that same
indirection here would just be needless complexity copied from a
constraint that doesn't apply. Instead, `.desk_temp/transforms/<name>/`
and `desk_transforms/<name>/` are scanned **directly** — the same
straightforward directory-scan shape `discover_widgets(widgets_dir)`
already uses for Desk's own built-in `widgets/` directory.

### Build pipeline for TypeScript/JavaScript transforms

Plain JavaScript transforms (`kind: "javascript"`) need no build step
at all — `entry` is already a runnable `.js` file.

TypeScript transforms (`kind: "typescript"`) are compiled with `tsc`,
the same toolchain choice `DefineWidget` custom widgets already made
(no bundler, no `npx`/ambient-package-name confusion — `tsc` must
already be on `PATH` or the build fails immediately with a clear
error). Simpler than the widget pipeline in one respect: there's no
HTML file to substitute compiled code into, and no multi-file
concatenation step — Node resolves multi-file imports natively, so
`tsc -p <transform_dir>` (respecting the transform's own
`tsconfig.json`, which must set `compilerOptions.outDir`, exactly like
a widget's) is the whole build; `entry`'s compiled counterpart under
`outDir` is what actually gets run. Building happens on demand,
right before a TypeScript transform's first invocation in this Desk
session, and is cached (skipped) for subsequent invocations unless the
`.ts` source's own mtime is newer than its compiled output — no
file-watcher, no background rebuild service; simple and sufficient for
a one-shot `input -> output` call.

### Execution model

`desk_services.transforms.TransformsService` (module-level, lazily
-constructed `get_service()` singleton — the same shape as
`file_watcher`/`popups`) is the one shared implementation:

- **Discovery**: `discover() -> dict[str, TransformInfo]`, scanning
  both directories (see above), returning each transform's parsed
  manifest plus which directory it came from (needed by the Transform
  Manager to decide whether to show a Promote button) and any
  discovery-time error (e.g. a Python transform found under
  `.desk_temp/`).
- **`run(transform_id, input_data, config, on_result)`** — non-blocking,
  callback-based (the same shape `PopupsService.show`'s `on_result`
  already established), because the two `kind`s have genuinely
  different execution realities that a single synchronous call can't
  honor safely for both at once:
  - **Python**: imported once per Desk session (`importlib`, the same
    dynamic-module-loading approach `PythonWidgetHost` already uses for
    widgets) and called **in-process, synchronously, on whichever
    thread calls `run`** — not backgrounded. This isn't a shortcut: a
    Python transform that touches Qt (both Mermaid transforms do,
    building a `QGraphicsScene` to render to SVG) *must* run on the GUI
    thread, since Qt's graphics classes aren't thread-safe to construct
    off it. This is the same synchronous-on-the-GUI-thread contract
    every other piece of widget-content-building code in Desk already
    has (laying out a big table, rendering a markdown preview, ...) —
    not the "slow, unbounded-latency external process" case
    `LEARNINGS.md`'s blocking-subprocess lesson is actually about.
  - **TypeScript/JavaScript**: always run via a background
    `threading.Thread` invoking `node <entry>.js` as a real subprocess
    (writing the JSON request to stdin, reading the JSON response from
    stdout, with a timeout), reporting back through a `_Relay`
    `pyqtSignal` — the exact same shape `git_status`/`git_diff`'s own
    git-subprocess calls already use, per `LEARNINGS.md`'s "a blocking
    `subprocess.run()` on the Qt GUI thread freezes the whole app's UI
    feedback."
- **`run_blocking(transform_id, input_data, config) -> str`** — a
  synchronous convenience (a nested `QEventLoop`, quit by the same
  callback `run` already wires up — identical idea to
  `PopupsService.show_blocking`) for callers that want a plain return
  value, e.g. the Markdown widget's own rendering pipeline.
- **`identity(...)`/`identity_blocking(...)`** — same two-shape split,
  only called for a transform declaring `has_identity: true`.
- **`promote(transform_id)`** — `shutil.move`s
  `.desk_temp/transforms/<id>/` to `desk_transforms/<id>/` (a
  TypeScript/JavaScript transform only, per the Python-not-allowed
  -in-`.desk_temp` rule above — there's never a Python transform in
  `.desk_temp/` to promote in the first place). Mirrors
  `_relocate_promoted_widget_source`'s own `shutil.move` shape.

### Reaching the service

Same dual-reachability shape as Popups:

- `kind: "python"` widgets: `current_context.get_transform_runner()`
  (paired `set_transform_runner`/`get_transform_runner`, bound at
  `DeskWindow` startup to `TransformsService.run`), plus
  `get_transform_runner_blocking()` for `run_blocking`.
- `kind: "html"` widgets: `POST /api/bridge/transforms/run`
  (capability `transforms`), using `run_on_gui_async` (the same
  callback-resolves-later pattern already established for
  `introspect/snapshot`), since a transform invocation can genuinely
  take a while (a `node` subprocess) and must not block the FastAPI
  event loop or the GUI thread.
- The Transform Manager widget calls `discover()`/`promote()`
  directly (both fast, synchronous, no subprocess involved).

### Transform Manager widget

`widgets/transform_manager/` (`kind: "python"`) — modeled on
`EventLogWidget`'s plain `QTableWidget` shape (there's no existing
"list/introspect other widgets or definitions" widget precedent to
mirror instead — `filetype_registry_editor` is a bare `kind:"html"`
read/edit-plumbing demo, not a UI shape worth copying). One row per
discovered transform: **Name / Input Type / Output Type / Language /
Config? / Identity? / Location**, plus a **Promote** button column,
shown only for a `.desk_temp/`-sourced row. Clicking Promote shows a
confirmation **popup** (TODO `359684f`'s desk-internal popups — "Promote
`<name>` to `desk_transforms/`? This moves its source into the
project and commits it to version control going forward.") before
calling `TransformsService.promote`. Refreshes on demand (a Refresh
button, matching the TODO widget's own now-removed-in-favor-of
-watching precedent isn't warranted here — transforms aren't edited
anywhere near as often as `TODO.md`, and this is a manager/introspection
widget, not a live-edited document) rather than file-watching
`.desk_temp/transforms/`/`desk_transforms/`.

### Extracting Mermaid into transforms

`src/desk/mermaid.py` currently produces a **live `QGraphicsScene`**,
rendered directly by `MermaidDiagramWidget` (a `QGraphicsView`
subclass) — **no SVG is ever generated anywhere in the current
pipeline**. Only two diagram kinds are actually implemented today
(despite there appearing to be "several" from the outside): `flowchart`/
`graph` and `stateDiagram`/`stateDiagram-v2`; anything else already
raises `MermaidParseError`, caught by `MermaidDiagramWidget` today with
a plain-text fallback.

`desk.mermaid`'s `parse`/`layout`/`build_scene` functions (and their
supporting classes) are kept exactly as-is — reused, not rewritten —
as the shared parsing/layout engine. A new function is added:
`render_svg(scene: QGraphicsScene) -> str`, using `PyQt6.QtSvg
.QSvgGenerator` (a `QPaintDevice`) — write the scene to an in-memory
`QBuffer` via a `QPainter`, decode the buffer as UTF-8. This is
genuinely new code (nothing today serializes a `QGraphicsScene` to
SVG), not a rewire of existing SVG logic.

Two new transforms, each a thin wrapper around the shared engine:

- `desk_transforms/mermaid_flowchart_svg/transform.py` —
  `input_type: "mermaid-flowchart"`, `output_type: "svg"`. `run(text,
  config)` calls `parse` (expecting a `flowchart`/`graph` header —
  raises if not, same as today) `-> layout -> build_scene ->
  render_svg`.
- `desk_transforms/mermaid_state_svg/transform.py` — identical shape,
  `input_type: "mermaid-state"`, expecting a `stateDiagram`/
  `stateDiagram-v2` header.

Both ship at project level (`desk_transforms/`, not `.desk_temp/`)
from day one — they're part of Desk's own built-in behavior, not a
user's local experiment to promote later.

`MermaidDiagramWidget` (the `QGraphicsView` subclass) is deleted —
dead code once the Markdown widget no longer embeds a live,
interactive scene directly (see next section). `parse`/`layout`/
`build_scene`/`render_svg` and their supporting classes stay in
`desk.mermaid`, now a library the two transforms import rather than
something a widget embeds directly.

### Markdown widget: consuming transforms via the Desk Service

The Markdown widget's Mermaid-block handling changes from "build a
`MermaidDiagramWidget` inline" to:

1. Detect the block's diagram header (the same `flowchart`/`graph` vs.
   `stateDiagram`/`stateDiagram-v2` detection `desk.mermaid.parse`
   already does internally) to choose `mermaid_flowchart_svg` vs.
   `mermaid_state_svg` — or, for anything else, skip straight to the
   plain-text fallback without calling a transform at all (no
   transform exists for a diagram type not yet extracted, exactly
   today's "unsupported" case).
2. Call `current_context.get_transform_runner_blocking()(transform_id,
   block_text, None)`.
3. On success, display the returned SVG string via a small,
   **shared** `_AspectSvgView`-shaped widget (a bare `QSvgRenderer`
   into a letterboxed, aspect-preserving rect) — today this class
   lives private (`_AspectSvgView`) inside `widgets/image_viewer/
   widget.py`; it's extracted into a new shared `src/desk/svg_view.py`
   module so both `image_viewer` and `markdown` import the same
   implementation instead of duplicating it.
4. On failure (transform raised, or no transform for this diagram
   type), fall back to plain text + the same "(unsupported or
   unparseable Mermaid diagram)" note shown today.

This is the one piece of user-visible behavior change beyond "it's
extensible now": a Mermaid diagram becomes a **static, non-interactive
SVG image** instead of a live `QGraphicsView` (pannable/selectable
scene). Accepted deliberately — nothing in the current
`MermaidDiagramWidget` UI actually depended on the scene being
interactive (no click-to-navigate, no node dragging), and a static SVG
is what "extracted into a transform, consumed like any other
diagram-type-to-SVG conversion" naturally produces.

## Open Questions

- Should the Transform Manager also let a user *create* a new
  `.desk_temp/transforms/<name>/` scaffold from inside Desk (a
  "New Transform" button generating a starter `transform.json` +
  `transform.ts`/`.js` + `tsconfig.json`), the way `DefineWidget`
  authoring has its own generated `.desk_temp/build_widget.py`? Not
  designed here — v1 assumes a transform's source directory is
  hand-authored (or agent-authored) directly, the same as
  `desk_transforms/mermaid_flowchart_svg/` will be.
- Content-hash staleness (TODO `5995ffd`/`3e2c4f2`'s `[STALE]`
  mechanism for tempui-defined widgets) has no equivalent here — a
  transform has no "placed instance" to go stale relative to. Worth
  revisiting only if a future feature *caches* a transform's output
  somewhere persistent (nothing does yet).
- The TypeScript/JavaScript execution path (Node subprocess, stdin/
  stdout JSON protocol, on-demand `tsc` build) is exercised in this
  round only by verification fixtures (a hand-written `.ts`/`.js` test
  transform), not by a real, shipped product transform — both Mermaid
  transforms are Python. Worth watching for rough edges once a real
  TypeScript/JavaScript transform actually gets written.

## Future Work

- A real transform authoring/scaffold generator (see Open Questions).
- Config UI: today `has_config` is just a manifest flag with no
  generic UI to actually build/edit a config value — a future
  transform that uses config will need either a bespoke config editor
  in its own consuming widget, or a generic one added to the Transform
  Manager.
- Identity-mapping consumers: nothing in this Desk yet reads an
  `identity()` result for anything (e.g. click-an-SVG-element ->
  jump-to-source-line in the Markdown widget). The contract exists;
  no consumer does yet.
- Chaining transforms (`A -> B -> C`) if a real multi-step use case
  ever shows up.
