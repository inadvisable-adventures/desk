# Markdown (Extended) widget — `markdown_ex` (COMPLETED)

TODO `a76e723`.

> **2026-07-13 (TODO 858752b):** the widget this plan describes,
> originally `widgets/markdown_ex/` id `markdown_ex`, was renamed to
> `widgets/markdown/` id `markdown`, becoming the new default
> "Markdown" widget and replacing the previous plain widget (now
> deprecated as `markdown_old_basic` -- see
> `plans/markdown-renderer-widget.md` and
> `plans/markdown-widget-identity-swap.md`). The rest of this plan is
> left as a historical record of what was actually built and is
> otherwise unchanged.

## Summary

"Implement a markdown viewer widget (`markdown_ex`) which can show
embedded SVGs as well as mermaid diagrams, with folding support and a
TOC treeview on the left-hand-side." A new `kind: "python"` widget
(`widgets/markdown_ex/`), separate from and additional to the existing
plain `markdown` widget (TODO `6bf83a9`, untouched by this item).

Per direct user instruction, Mermaid support is **partial and bespoke**
(no vendored `mermaid.js`/QtWebEngine, no network calls): a hand-rolled
parser + auto-layout + `QGraphicsScene` renderer supporting only
**flowchart** (basic shapes — no extended shapes like stadium/subroutine/
cylinder/hexagon) and **state diagrams** (flat — no nested/composite
states). Unsupported/unparseable Mermaid source degrades gracefully to
a plain code block rather than erroring.

## Key decisions

- **Bespoke Mermaid engine (`desk/mermaid.py`), not `mermaid.js`.**
  `CLAUDE.md`'s "avoid adding dependencies, prefer bespoke solutions"
  and explicit user direction. Scope is deliberately partial:
  - **Flowchart**: `flowchart`/`graph` + direction (`TD`/`TB`/`LR`/`BT`/
    `RL`), node shapes rect `[Label]`, rounded `(Label)`, diamond
    `{Label}`, circle `((Label))` (no other shapes), edges `-->`, `---`,
    `-.->`, `-.-`, with an optional `|label|` right after the operator,
    and multi-node chains (`A --> B --> C`) on one line.
  - **State diagram**: `stateDiagram`/`stateDiagram-v2`, `[*]` start/end
    pseudostates (each occurrence its own node, matching real Mermaid
    semantics), `A --> B` / `A --> B : label` transitions, `A : label`
    state-description lines. Composite/nested `state X { ... }` blocks
    and `direction` sub-statements are skipped (brace-depth-tracked, not
    an error) — a documented limitation, not silently wrong output.
  - **Layout**: a simplified layered (Sugiyama-style) algorithm —
    longest-path rank assignment (cycle-safe: any node stuck with
    unresolved in-edges after the main topological pass gets picked up
    and assigned past its known predecessors, so a cycle degrades to "a
    reasonable but not crossing-minimized" layout instead of hanging),
    first-seen ordering within a rank (no barycenter crossing
    minimization — a known simplification), grid placement sized from
    per-node text measurement, straight-line edge routing clipped to
    each shape's boundary with arrowheads (no orthogonal/curved
    routing).
  - **Rendering**: a `QGraphicsScene`/`QGraphicsView`
    (`MermaidDiagramWidget`), using the current `QPalette` for
    colors so it adapts to light/dark rather than hardcoded black-on-
    white.
  - Any diagram type other than flowchart/state (sequence, class, ER,
    gantt, pie, ...), or source that fails to parse, raises
    `MermaidParseError` — caught by the caller and shown as a plain
    fenced code block with a small "unsupported/unparseable Mermaid
    diagram" note, never a crash.
- **SVG/raster images: no new work, reuse `QTextBrowser`'s existing
  native/indirect handling** (per `qtextbrowser-images-svg-controls.md`
  in the repo root — `setMarkdown()` already resolves `<img>`/
  `![]()` through `QImageReader`, which covers raster natively and SVG
  via the bundled `QtSvg` image-format plugin, rasterized at load time).
  Same zero-dependency approach the existing `markdown` widget already
  uses; not worth a bespoke `QSvgWidget` path for this item.
- **Folding + TOC: pure native Qt composition, no HTML/JS at all.** The
  raw Markdown is split (regex over lines, fence-aware so `#` inside a
  code block is never mistaken for a heading) into a flat block list —
  `heading`, `text` (a raw Markdown chunk fed to a plain
  `QTextBrowser.setMarkdown()`, handling everything `QTextBrowser`
  already does for free: bold/italic/links/lists/tables/blockquotes/
  images/non-Mermaid code fences), and `mermaid` (fenced ```mermaid
  blocks, routed to `MermaidDiagramWidget` instead) — then folded into a
  heading-nested `Section` tree. Rendering recurses that tree into
  nested `_SectionWidget`s (a `QToolButton` disclosure header + a body
  `QVBoxLayout` of blocks/child sections) inside a `QScrollArea`, with a
  mirrored `QTreeWidget` TOC on the left whose clicks expand ancestors
  and `ensureWidgetVisible()` the target section. This sidesteps
  `QTextDocument`'s lack of native block-folding/live-widget-hosting
  entirely (see `qtextbrowser-images-svg-controls.md`) instead of
  fighting it.
- **`desk/mermaid.py` lives in `desk.` proper, not inside the widget
  directory**, even though only this widget uses it today — matches
  `desk.file_watch`/`desk.terminal_widget`'s existing pattern, and is
  the only clean option anyway: `PythonWidgetHost` loads a widget's
  `entry` file via `importlib.util.spec_from_file_location` with a
  synthetic module name (see `src/desk/shell/python_widget.py`), so a
  bare same-directory `import` from `widget.py` has no reliable
  `sys.path` entry to resolve against. The parse/layout logic is kept
  Qt-light (an injectable `measure(text) -> (w, h)` callable instead of
  a hard `QFontMetrics` dependency) so it's unit-testable without a live
  `QApplication`.
- **Per-block `QTextBrowser`s auto-size to content** (`setTextWidth` on
  resize + `documentSizeChanged` → `setFixedHeight`, scrollbars off) so
  they behave as inline flowed blocks inside the outer `QScrollArea`
  rather than each being its own nested scrollable viewport.
  `MermaidDiagramWidget` sizes to its diagram's bounding box, capped at
  a max height (its own scrollbars only kick in past the cap) — avoids
  nested-scroll-area UX problems.
- **No cross-reload persistence of the open file**, matching the
  Markdown/Editor/Sheet widgets (no per-instance state payload yet; see
  `PARKINGLOT.md`).

## New/affected files

- `src/desk/mermaid.py` (new) — parser (`parse(text) -> Diagram`,
  raises `MermaidParseError`), `Node`/`Edge`/`Diagram` dataclasses,
  `layout(diagram, measure) -> LayoutResult`, `build_scene(diagram,
  layout_result, palette) -> QGraphicsScene`, and
  `MermaidDiagramWidget(QGraphicsView)` (parses + lays out + renders a
  source string in its constructor; falls back to a plain text item on
  `MermaidParseError`).
- `widgets/markdown_ex/widget.json` (new) — `{name: "Markdown (Extended)",
  kind: "python", entry: "widget.py", capabilities: [], default_size:
  900x700}`.
- `widgets/markdown_ex/widget.py` (new) — `MarkdownExWidget(QWidget)`:
  - Toolbar (Open button + filename label), matching the `markdown`
    widget's `_open_file`/`set_file`/`SingleFileWatcher`/
    `current_context` pattern.
  - `_split_blocks(text) -> list[Block]` (fence-aware heading/text/
    mermaid splitter) and `_build_section_tree(blocks) -> list[Section]`
    (heading-level nesting).
  - `_SectionWidget(QWidget)` (disclosure header + body), the top-level
    `QScrollArea` block renderer, and the mirrored TOC `QTreeWidget`
    (`QSplitter` between the two).
  - `_AutoHeightTextBrowser(QTextBrowser)` helper for inline-sized text
    blocks.
- `design-docs/architecture.md` — new Markdown (Extended) Widget
  component entry.
- `LEARNINGS.md` — an entry if anything surprising turns up verifying
  `QGraphicsScene` rendering/`QTextBrowser` auto-sizing headlessly (per
  `development-process.md`).

## Verification

Headless, no browser needed (pure Qt widgets):

- `desk/mermaid.py` parser: flowchart with all 4 shapes + all 4 edge
  styles + a piped edge label + a 3-node chain on one line; a direction
  other than the default; a diamond decision node. State diagram with
  `[*]` start and end, a labeled transition, a state-description line,
  and a skipped composite `state X { ... }` block (asserting its
  contents don't leak into the parsed graph). Unsupported diagram type
  (e.g. `sequenceDiagram`) and garbage input both raise
  `MermaidParseError`.
- `layout()`: a small DAG (linear chain, a branch/merge diamond shape,
  and an intentional cycle) — assert every node gets a rank ≥ its
  predecessors' (or the cycle-fallback still terminates and assigns
  every node), and no two nodes in the same rank overlap given a fixed
  fake `measure()`.
- `MermaidDiagramWidget`: real `QApplication` (offscreen), build a
  flowchart and a state diagram from source strings, confirm the scene
  has the expected node/edge item counts; feed unsupported source and
  confirm the fallback text path (no exception, some text item present).
- `MarkdownExWidget`: a real temp `.md` file with nested headings,
  interleaved prose, a raster image reference, and two ```mermaid
  fences (one flowchart, one unsupported-type) — confirm the TOC tree
  matches the heading structure, clicking a nested TOC entry expands
  ancestors and scrolls to it, folding a section hides its body
  widgets, and both mermaid blocks render (one as a diagram, one as a
  graceful fallback). Also the file-watcher reload path (edit the file
  on disk, confirm the widget picks it up), matching the `markdown`
  widget's own verification.
- A full-app `DeskWindow` regression: place a real `markdown_ex`
  instance and open a file through it.

## Status

**Completed.** Implemented as described above:

- `src/desk/mermaid.py`: parser verified against flowcharts covering all
  4 supported shapes, all 4 edge styles, piped edge labels, and
  multi-node chains; state diagrams covering `[*]` start/end, labeled
  transitions, state descriptions, and a skipped composite block
  (confirmed its contents don't leak into the parsed graph); an
  unsupported diagram type (`sequenceDiagram`) and garbage input both
  correctly raise `MermaidParseError`. `layout()` verified on a linear
  chain, a branch/merge diamond, and an intentional 3-node cycle (the
  cycle-fallback ranking terminates and produces a reasonable, non
  -overlapping layout). `MermaidDiagramWidget` verified headless
  (offscreen `QApplication`): real scenes built for both diagram kinds
  (including the self-loop edge-routing path), and the plain-text
  fallback for unsupported source, with no exceptions in any case.
- `widgets/markdown_ex/`: verified `_split_blocks`/`_build_sections`
  against a real document (nested headings, an interleaved code fence,
  and two `mermaid` fences, one supported/one not) — correct block
  typing and section nesting. Verified the full widget end-to-end via
  the real widget-loading files: `desk.widgets.discover_widgets` picks
  up the manifest correctly, and `desk.shell.python_widget
  .PythonWidgetHost` (the exact class `DeskWindow._place_widget` uses
  for every `kind: "python"` widget) builds a real `MarkdownExWidget`,
  opens a file, populates the TOC to match the heading structure, and
  correctly reloads (TOC updates) on an external file edit via the
  file watcher. Also directly verified TOC-click behavior: clicking a
  nested entry re-expands a collapsed ancestor section (this caught a
  real bug — see the `LEARNINGS.md` entry on `QTreeWidgetItem`/`id()`
  — since fixed to use `QTreeWidgetItem.setData`/`.data()` instead of
  an `id()`-keyed side dict).
- **Skipped**: constructing a full, literal `DeskWindow` (rather than
  `PythonWidgetHost` directly) hit an unrelated stall in this
  environment during `WorkspaceView`/`canvas.py` construction —
  plausibly first-time offscreen `QtWebEngine` startup cost pulled in
  transitively by that module, not something `markdown_ex` itself
  triggers (`kind: "python"` widgets never touch `QWebEngineView`/
  `ChromiumWidget`/`ServerHandle` at all — see `window.py`'s
  `_place_widget`). Not investigated further since it's orthogonal to
  this item; `PythonWidgetHost` (the actual per-widget mechanism
  `DeskWindow` delegates to) was verified directly instead, and manifest
  discovery was verified separately with no `DeskWindow`/Qt involved at
  all.
- `design-docs/architecture.md` gained a Markdown (Extended) Widget
  entry; `LEARNINGS.md` gained the `QTreeWidgetItem`/`id()` entry.
