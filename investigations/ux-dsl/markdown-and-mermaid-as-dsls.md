# Case study: Markdown and Mermaid-in-Markdown, as DSLs, in Desk's own code

Part of the `investigations/ux-dsl/` sweep (see `dsl-for-agent-widgets.md` for
the hypothesis and the two UX principles this is read against, and
`widget-case-studies.md` for the peer-project widget case studies this one
sits alongside). Unlike those, this one isn't about a Desk widget someone
else built -- it's about two DSLs Desk itself already consumes and partly
implements: **Markdown**, a domain-specific language for documentation, and
**Mermaid embedded inside Markdown**, a domain-specific language for
technical diagrams, nested inside the first one via its own generic
extension mechanism (a fenced code block tagged with a language). Both are
grounded directly in this project's own code (`widgets/markdown/widget.py`,
`src/desk/mermaid.py`) and design history (`markdown-rendering.md`,
`design-docs/transforms.md`, `plans/markdown-ex-widget.md`,
`plans/markdown-consumes-mermaid-transforms.md`), not external research.

## Markdown: reuse the platform's own DSL, don't rebuild it

Desk doesn't hand-roll a Markdown parser at all. Both Markdown widgets render
through `QTextDocument.setMarkdown()` (via `QTextBrowser`), with no custom
`MarkdownFeature` flags -- Qt's default `MarkdownDialectGitHub`
(`markdown-rendering.md:36-39`). That covers headings, emphasis, links,
lists, blockquotes, tables, fenced/indented code, and images natively;
footnotes, task-list checkboxes, and definition lists are explicitly *not*
supported, because Qt's own parser doesn't implement them, dialect or not
(`markdown-rendering.md:53-57`).

This is a useful, concrete data point for the broader investigation's own
build-vs-reuse question (see `grammar-ast-live-pane.md`'s generator-vs
-combinators decision): Markdown is exactly the case where a mature,
already-correct, already-available implementation exists for free (a real
browser-grade engine, bundled with the platform), so nothing here reaches for
a bespoke parser -- that's reserved for Mermaid below, precisely because no
comparably cheap off-the-shelf option exists there without a real dependency
(vendoring `mermaid.js` plus a `QtWebEngine` round-trip, explicitly rejected
per `CLAUDE.md`'s "avoid adding dependencies, prefer bespoke solutions" --
`src/desk/mermaid.py:1-9`). The lesson generalizes: build a bespoke
grammar/parser when nothing suitable exists cheaply; reuse a mature one when
it does. The DSL-design investigation's own choice to build a real
grammar/AST engine (`grammar-ast-live-pane.md`) is itself exactly this kind
of case -- there's no existing, already-correct engine for the small
project-specific DSLs it's aimed at (`wt.dsl`, the raycaster formula
language), unlike Markdown.

### No dual-pane raw/rendered sync exists yet -- a real gap, not a design choice

Neither Markdown widget offers a live, side-by-side raw-text-plus-rendered
-preview view -- editing happens entirely in the separate Editor widget (or
externally), and the Markdown widget is read-only, re-rendering on file
change (`markdown-rendering.md:20-27` for the old-basic widget's own
auto-reload; the current widget's own file-watching is the same shape). This
is worth flagging explicitly against UX principle 1 (multiple simultaneous
views of one value must stay in sync, by re-deriving one view fresh from the
other): the single most common, most well-understood real-world instance of
exactly that principle -- a markdown source pane next to a live preview pane,
as basically every code editor and GitHub's own web editor already do -- is
*not yet built* in Desk's own tooling. Every other strong example of this
pattern found across this whole investigation (`world-timelines`'s
`wt.dsl`/`query-editor` folded view, `raycaster-scene`'s text/fields pair,
Domain Analysis's single mutable `doc`) had to be found by reading someone
else's code; this one is a well-trodden, low-risk, already-everyone-knows
-what-good-looks-like case that Desk could prototype the "derive, don't
duplicate" pattern against directly, without even needing a new grammar --
`QTextDocument.setMarkdown()` already *is* the render function; a live pane
just needs to call it on every edit instead of only at load time.

### Fenced code blocks are already a working DSL-composition primitive

`widgets/markdown/widget.py`'s `_split_blocks` (lines 65-117) is a
fence-aware splitter: a fenced code block's lines are never scanned for
headings, and specifically a ` ```mermaid ` fence is pulled out of the
surrounding text and tagged `kind="mermaid"` (lines 84-99) rather than being
left for `QTextBrowser` to render as an inert code block like any other
fenced language. Every other fenced language just stays in the ordinary
`"text"` block, handled by Qt's native renderer for free (comment,
`_RawBlock`'s own docstring, lines 53-58).

This is a real, already-working instance of exactly the composition
mechanism the broader investigation's live-pane vision will eventually need:
a host document format (Markdown) declares a generic embedding point (a
fenced block plus a language tag), and the *consumer* decides, per language
tag, whether to hand it to the generic renderer or route it to a specialized
one. Structurally, this is the same shape as `app_dsl`'s own "escape hatch"
(named handler functions at declared extension points,
`investigations/app_structure_dsl_design.md`'s "Full DSL inventory" item 8)
and as the eventual grammar/AST engine's own need to let one document embed
several different grammars. The instructive part: Markdown needed nothing
fancy to support this -- just "detect a fence, read its language tag,
dispatch" -- which is a good minimum bar to keep in mind for whatever the
live-pane's own embedding mechanism ends up looking like.

## Mermaid-in-Markdown: a fourth independent hand-rolled parser

`desk.mermaid` (`src/desk/mermaid.py`, 699 lines) is a real, bespoke,
dependency-free tokenizer + parser + layout engine + (formerly interactive,
see below) renderer for a deliberately partial subset of Mermaid: flowcharts
(five node shapes, several edge styles, quoted labels) and flat state
diagrams (module docstring, lines 1-45). Any other diagram type, or source
that doesn't match the supported grammar, raises `MermaidParseError`, which
callers must catch and fall back to plain text (lines 25-29) -- the fallback
granularity is the *whole diagram*, not a single bad line or node; one
unsupported construct anywhere degrades the entire block to plain text, a
coarser tier than the statement/line-level recovery
`grammar-ast-live-pane.md` settled on for the new grammar/AST engine, worth
keeping in mind as a *third*, even coarser recovery granularity that exists
in real Desk code (document-level fallback, statement-level recovery,
eventually node-level highlighting -- three real tiers, not two).

This is directly relevant to the grammar/AST engine investigation as a
**fourth independent data point** for the same underlying argument
`grammar-ast-live-pane.md` already made from three (`wt.dsl`'s flat lines,
the raycaster camera/objects line grammar, and the raycaster formula
tokenizer+recursive-descent parser, duplicated by hand in TypeScript and
Python): yet another real, working, hand-rolled, from-scratch
tokenizer/parser exists in this *very project*, built with no shared grammar
-to-parser machinery at all, because none existed to reach for. A real
grammar/AST engine, once it exists, would be a plausible target to
eventually re-implement `desk.mermaid`'s own grammar against too -- not
proposed here as a TODO, just noted as a further concrete candidate beyond
the ones already listed.

### A real interactive renderer already existed once -- and was deliberately retired

The single most important finding for the "interactive Mermaid" thread
specifically: Desk used to have exactly the shape of thing that thread is
reaching for. `MermaidDiagramWidget`, a `QGraphicsView` subclass, embedded a
live, pannable `QGraphicsScene` diagram directly into the Markdown widget
(`src/desk/mermaid.py`'s own module docstring, lines 40-44). It was deleted
by TODO `a9e2ba7` (`plans/markdown-consumes-mermaid-transforms.md`,
`design-docs/transforms.md:404-412`) when the Markdown widget switched to
rendering a diagram via a transform (`mermaid_flowchart_svg`/
`mermaid_state_svg`) into a shared, static SVG view instead (the same
`_AspectSvgView`-derived component the Image Viewer widget already used,
extracted into `src/desk/svg_view.py` so both share one implementation
rather than duplicating it).

The retirement was deliberate and explicitly reasoned, not a casualty of the
refactor: "nothing in the current `MermaidDiagramWidget` UI actually
depended on the scene being interactive (no click-to-navigate, no node
dragging)" (`design-docs/transforms.md:408-410`). The interactivity that
existed was pan/zoom only -- never value-editing, never click-to-select,
never anything the broader investigation's UX principle 2 (the visualization
*is* the interface) would count as real manipulation -- so when weighed
against consolidating onto a simpler, shared, already-correct static-SVG
code path, it lost on its own terms, not because interactivity in general
was rejected.

**The lesson to carry forward, explicitly**: this is not evidence against
building an interactive Mermaid diagram -- it's evidence that *merely
technically interactive* (pannable, zoomable, nothing more) is not enough to
survive the next refactor that offers a simpler alternative. Any future
interactive-Mermaid effort needs its interactivity to be load-bearing --
actually bound to editable values, actually the primary way something gets
changed -- or it risks the exact same fate: quietly judged not worth the
extra complexity once a simpler static alternative is good enough. This
sharpens (not just repeats) `dsl-for-agent-widgets.md`'s own framing of UX
principle 2: the bar isn't "can the picture be interacted with at all," it's
"is the picture doing real work as the interface," and this project's own
history already shows what happens to the former when it doesn't rise to the
latter.

### Dispatch-by-detected-kind, already a small working precedent

`desk.mermaid.detect_diagram_kind` decides which transform
(`mermaid_flowchart_svg` vs `mermaid_state_svg`) to call by recognizing the
diagram's own header line, without doing a full parse
(`design-docs/transforms.md:390-392`; added specifically so the Markdown
widget wouldn't have to duplicate `desk.mermaid`'s own private
header-detection regexes). This is a small, real instance of "dispatch to one
of several grammars/handlers by recognizing which one applies" -- the same
shape as the new PEG engine's own transparent-dispatch rule for `Primary <-
Neg / Group / Vector / Number / Name` (`grammar-ast-live-pane.md`'s pressure
test), just hand-coded via regex rather than grammar-driven. Worth noting as
yet another place a generic engine's dispatch mechanism could eventually
subsume something that's currently bespoke, if `desk.mermaid` itself were
ever rebuilt on it.

## Synthesis

- **Reuse vs. build, decided correctly here, generalizes as a heuristic**:
  Markdown reuses a mature platform engine; Mermaid is bespoke because
  nothing comparably cheap exists. Apply the same test to any future DSL
  this investigation considers building for: is there already a correct,
  dependency-light implementation to lean on, or is bespoke genuinely the
  only option?
- **A fourth hand-rolled parser**, found in this project's own code rather
  than a peer project, strengthens `grammar-ast-live-pane.md`'s case for a
  shared grammar/AST engine further still.
- **Fenced code blocks are free, working prior art** for the "one document,
  several embedded grammars, dispatched by a tag" composition the live-pane
  vision will eventually need -- and it didn't require anything elaborate to
  build.
- **A cautionary, specific lesson about what "interactive" has to mean**:
  Desk already tried the weak version (pan/zoom, no value-editing) and
  retired it because it wasn't pulling its weight. The live-pane/interactive
  -Mermaid thread should aim squarely at the strong version (direct
  manipulation of bound values) from the start, not reintroduce the weak
  version and risk the same fate.
- **A concrete, low-risk, well-understood prototype opportunity sits right
  here**: a live raw-Markdown/rendered-preview dual pane, re-rendering on
  every edit via the engine Desk already has (`QTextDocument.setMarkdown()`),
  would be a direct, almost risk-free demonstration of UX principle 1's
  "derive, don't duplicate" pattern, using infrastructure that already
  exists, before ever touching Mermaid's own grammar at all.

## Related

`dsl-for-agent-widgets.md` (the hypothesis and two UX principles),
`grammar-ast-live-pane.md` (the grammar/AST engine direction this adds a
fourth data point to, and the interactive-Mermaid thread this sharpens),
`widget-case-studies.md` (the peer-project widget evidence this sits
alongside), `markdown-rendering.md` and `design-docs/transforms.md` (this
project's own authoritative references for the material cited above).
