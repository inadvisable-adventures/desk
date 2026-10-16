# Investigation: a targeted DSL (not just a control library) for agent-authored temporary widgets

**Status:** open; hypothesis and supporting case studies recorded. Open question 1
below has since been resolved into a concrete direction — see "Update
2026-10-15" and `grammar-ast-live-pane.md` — and a pressure-test against the
raycaster formula DSL is starting now. No TODO item filed yet — this is
pre-design research, the same stage `app_structure_dsl_design.md` was at before
TODO `48e3b39` turned part of it into real code.

## The hypothesis

Today, an agent building a quick, disposable interactive widget for a Desk user
(via `DefineWidget` — see `.desk_temp/tempui-custom-widgets.md`) writes it as
plain TypeScript + HTML + CSS: a custom element, a `<template>`, imperative DOM
wiring. This works, but it's easy for both the agent and the resulting widget to
get caught up in incidental detail — `querySelector` calls, manual event-listener
wiring, hand-rolled re-render-on-every-change logic, remembering to route a
mutation through whatever sync mechanism is in play rather than just poking the
DOM directly. None of that incidental work is about the widget's actual
purpose.

**Hypothesis:** a more targeted DSL — not just a richer control/component
library, though that might be part of it — would let an agent (and a human
collaborating with one) build a small interactive widget by describing *what it
shows and how it can be manipulated*, with the plumbing that currently has to be
hand-written every time handled by the DSL's own runtime instead. The scope
here is explicitly broader than "give widgets nicer buttons and sliders": a
control library alone doesn't address *how a widget's structure and data
relationships are declared*, which is where the two UX principles below keep
showing up as recurring, hand-solved-every-time problems in real widgets (see
`widget-case-studies.md`).

This also continues a direction already underway: some prior work here has
started moving toward **interactive Mermaid (Markdown) diagrams** specifically —
diagrams aren't just documentation, they could be the *interface* itself, with
nodes/edges as bound, manipulable marks rather than a static picture. See
"Interactive Mermaid: where this could go" below for why that specific notation
looks promising and what was (and wasn't) found already built toward it.

## Two UX principles

1. **Multiple simultaneous views/controls over one value must stay in sync.**
   If a value can be seen or changed from more than one place at once — two
   fields editing the same thing, a picker and a visualization both reflecting
   a selection, two widget instances pointed at the same underlying data — none
   of those views may show something stale or contradictory. This sounds
   obvious, but it is the single most common failure point found across every
   real widget examined for this investigation (see "What the case studies show"
   below).

2. **The visualization of the data should itself be (or be a major part of) the
   interface to manipulating it** — borrowing directly from Edward Tufte. A
   chart, map, or diagram that merely *displays* a value while a separate set of
   text fields or buttons does the actual work of changing it is a missed
   opportunity: if the picture already encodes the value, interacting with the
   picture directly (dragging a point, clicking a node, drawing a selection box)
   is usually both more discoverable and more honest about what's actually being
   changed than a disconnected form bolted on next to it.

Neither principle is novel UX theory, but neither is reliably *achieved* by
today's raw-HTML/CSS/JS widget-authoring path either — see below.

## What already exists here to build on

This repo and its sibling projects already have real, working pieces that bear
directly on this hypothesis, found before and during this investigation:

- **`app_dsl/`** (TODO `48e3b39`, `plans/app-structure-dsl.md`) — a declarative
  schema + codegen tool for a multi-component app's *structure*: a component
  registry, a layout tree (N-split-panes or windowed), an event-wiring table,
  and typed state slots, emitted as either real ES modules or
  `DefineWidget`-compatible global scripts. This solves **structure and wiring**
  for a whole app, but has nothing to say about *content* — what's actually
  rendered inside a pane, or how a value is visualized, is still up to
  hand-written component code. It's the right model for "several widgets, one
  app," not for "one widget, a rich interactive picture."
- **`desk.state`/`desk.events`** (TODO `f68383f`, `af7898b`) — the Bridge API's
  shared, project-scoped key/value store plus pub/sub, with a load-bearing
  platform guarantee found cited directly in multiple widgets across multiple
  projects during this research: a widget's own write to `desk.state` **never
  echoes back** to itself over `desk.events.changed`, removing a whole class of
  self-reentrancy bugs for free. This is the real transport underneath every
  *working* multi-view-sync story found in the case studies (`wt.dsl` in
  `world-timelines`; `raycaster-scene`'s cross-widget reload). It is not,
  by itself, a DSL for widget *content*, and it doesn't enforce principle 1 —
  it only makes principle 1 achievable *if* a widget's author remembers to
  route every mutation through it and re-derive every view from it fresh. Both
  halves of that sentence are things real widgets got wrong (see below).
- **`shared-components/document-editor-base/`** — a genuine, proven,
  reusable *file-lifecycle* abstraction (declare `directory`/`extension`/
  `parse`/`serialize` plus a few lifecycle hooks; the base handles path
  derivation, create-vs-load, restore-last-open, save-on-edit). A real success
  story for "declarative contract instead of hand-copied imperative glue" —
  extracted from `necro-4x` after ≥4 widgets independently hand-rolled and
  re-bugged the same load/save logic, now reused as-is by `draw-with-desk`'s
  `voice-brainstorm` widget. Scoped to lifecycle, not to UI or visualization —
  but exactly the kind of "generalize once a second real instance shows up"
  trajectory a content/visualization DSL would also need to earn.
- **Interactive Mermaid: not yet built, but not starting from nothing
  either — and there's a real cautionary lesson in this repo's own history.**
  `desk.mermaid` (this repo) is a real, bespoke, dependency-free Mermaid
  flowchart/state-diagram parser + layout + renderer — a fourth independent
  hand-rolled-parser data point alongside the three already listed above, see
  `markdown-and-mermaid-as-dsls.md`. Today it's **read-only** (static SVG via
  a transform), but it didn't start that way: a `QGraphicsScene`-based
  `MermaidDiagramWidget` once rendered a live, pannable diagram directly, and
  was *deliberately retired* (TODO `a9e2ba7`) because "nothing in the current
  UI actually depended on the scene being interactive (no click-to-navigate,
  no node dragging)" — i.e. the interactivity that existed was never load
  -bearing. See `markdown-and-mermaid-as-dsls.md` for the full story and why
  this sharpens (not contradicts) UX principle 2: any future interactive
  Mermaid effort needs its interactivity to be genuinely bound to editable
  values, not just technically present, or it risks the same fate. See
  "Interactive Mermaid" below for the fuller search and what a next step
  might look like.

## What the case studies show

Full write-ups, with file:line citations throughout, are in
`widget-case-studies.md` — four peer projects (`file-tree`, `draw-with-desk`,
`necro-4x`, `world-timelines`), roughly twenty real widgets plus a handful of
throwaway dev harnesses, every `.desk_temp/widgets/`/`desk_widgets/` directory
found across every sibling of this project under `../` and
`../../claude-projects/`. The pattern that emerged, independent of project:

**Principle 1 (sync) is solved well exactly once a pattern is found, and solved
badly whenever it isn't:**

- *Working*: `world-timelines` treats one text blob (`wt.dsl`) as the single
  source of truth for essentially every filter/selection concept across 9
  widgets, and every widget *re-derives* its display from it on every change
  rather than caching a parsed copy — explicitly reasoned about in several
  widgets' own comments (`entry-detail.ts`'s cross-widget pin-button sync;
  `laneset-picker.ts`'s "re-derive, never cache, even for changes we didn't
  cause" framing; `boundary-picker.ts`'s explicit refusal to write back on a
  passive re-sync, to avoid feedback loops). `raycaster-scene`'s text/structured
  -fields pair is a clean single-widget version of the same idea, and is also
  the one `raycaster` widget that correctly reacts to an *external* write (a
  sibling widget's hitmap click).
- *Not working*: `file-tree`'s `DeskConsole`/`DirectoryTreeView` hand-rolled,
  independently, nearly-verbatim-duplicated **private per-widget state +
  command-replay + late-join request/response + retry-on-race** — four
  non-trivial mechanisms built from scratch on top of raw `desk.events`,
  because no shared "this value lives here, ask for it, and get told when it
  changes" primitive existed for them to use instead. `raycaster-camera`/
  `raycaster-formula` simply never declared the `events` capability at all, so
  two simultaneous editors of the same camera/formula silently clobber each
  other with no indication anything went wrong. `world-timelines`'s own
  `timeline.ts` explicitly flags a case where the *current* state-key model
  (one scalar "selected entry" key) can't represent what the original
  single-page app could (which waypoint along a path was clicked) — a
  granularity gap in the sync model itself, not just an authoring mistake.
- The common thread: **every failure happened because no structural mechanism
  forced a second writer through the same path as the first** — it was always
  possible to just mutate local state directly and skip the shared store, and
  in roughly half the widgets examined, that's exactly what happened, including
  in projects where *other* widgets in the very same codebase demonstrate the
  correct pattern right next to the failing one. That inconsistency — the right
  answer and the wrong answer both existing side-by-side within one project
  built by one process — is itself evidence that "remember to sync" is not a
  reliable enough rule on its own; it needs to be closer to the path of least
  resistance than skipping it is.

**Principle 2 (vis-as-interface) is rare, and expensive when it's actually
achieved:**

- *Best example found*: `necro-4x`'s Domain Analysis widget (not yet promoted,
  `custom_widget_src/domain-analysis/`) — tagging is done by selecting text
  directly inside rendered content and dragging it onto a rendered category
  target; there's no separate dialog or dropdown step at all. It also carries
  an in-document, user-extensible schema (categories defined in a markdown
  table inside the very document being edited). This cost roughly 1800 lines of
  hand-written, carefully-reasoned imperative TypeScript — real evidence that
  achieving this *is* valuable enough to hand-build once, and therefore worth
  making cheaper to build again.
- *Partial*: `world-timelines`'s `world-map`/`timeline` (direct drag/click/box-
  select on the rendered canvas for most but not all interactions);
  `HexMapViewer`'s drag-to-pan/wheel-to-zoom (camera state only — the actual
  per-cell data has no interaction at all); `raycaster-view`'s one hitmap click
  (object selection only — every other raycasting parameter is text/number
  fields with no graphical alternative, by explicit design in at least one
  sibling widget's own comment).
- *Absent despite an obvious opportunity*: the `raycaster` family as a whole
  (no drag-on-picture for camera pose/FOV/formula coefficients — the parameters
  a rendered 3D scene would seem to invite dragging); the `LifeforceHeart`/
  `LifeforceControl` pair (buttons sit *on top of* a heart-shaped gauge rather
  than the gauge itself being draggable); every `world-timelines` picker widget
  (boundary/laneset/category — conventional dropdowns/chips with zero
  visualization, by design, deliberately paired with the two widgets that do
  visualize).
- The common thread: when a widget's author chose the "separate controls, picture
  stays passive" path, it was consistently cheaper to build with the raw tools
  available (an `<input>` plus an event listener) than "a draggable mark bound to
  a value" would have been (hit-testing, drag-state management, converting
  pointer coordinates to data coordinates, redrawing). A good DSL/library should
  flip that cost asymmetry, not just make the harder path *possible* — it
  already is possible, Domain Analysis proves it — but make it the *default*,
  cheaper choice.

## Interactive Mermaid: where this could go

Searched for existing "interactive Mermaid diagram" work across every project
reachable from here (see `widget-case-studies.md`'s mermaid-search note for
`world-timelines` specifically, and a broader `grep -ril mermaid` sweep across
`desk-stable`/`desk-dev-2`/`draw-with-desk`/`file-tree`/`necro-4x`/
`discussion-for-desk`/`sep-contacts`/`research` run directly for this
investigation). Found:

- This repo's own `desk.mermaid` — real flowchart/state-diagram parsing +
  layout + rendering, strictly **read-only** today, used only inside the
  Markdown widget to show a diagram as a picture. No click/drag on any node,
  no path back to editing the source. **It wasn't always read-only**: see
  `markdown-and-mermaid-as-dsls.md` for the full history of
  `MermaidDiagramWidget`, a real `QGraphicsScene`-based live diagram that
  existed and was deliberately retired because its interactivity (pan/zoom
  only) was never load-bearing — the clearest cautionary data point this
  investigation has for what "interactive" needs to actually mean to survive.
- `discussion-for-desk/design-docs/spec-dsls.md` — establishes Mermaid
  `stateDiagram`/`sequenceDiagram` as this project family's chosen notation for
  **documenting** client-operation lifecycles in design docs. Also static,
  also not interactive, and about a different kind of content (protocol/client
  lifecycle specs, not data a user manipulates).
- **Nothing anywhere searched implements an interactive/editable Mermaid
  diagram** — a rendered node that's also a bound, draggable/clickable/editable
  value, kept in sync with its own source text the way `wt.dsl` keeps
  `world-timelines`' nine widgets in sync. If prior work on this exists, it
  wasn't found by this sweep and should be pointed out directly rather than
  re-discovered from scratch.

Why Mermaid specifically looks like a promising starting point for *this*
hypothesis, not just a nice-to-have:

- It's already a widely-known, LLM-fluent textual notation — an agent
  generating correct Mermaid source needs little to no scaffolding, which
  matters if the whole point is lowering the cost of an agent authoring a
  widget's content declaratively rather than imperatively.
- It's inherently a **graph/state-machine notation** — already about nodes,
  edges, and values attached to them, which is exactly the shape principle 2
  wants: a rendered node *is* a value-bearing mark already, so making it also a
  bound, interactive control (drag to reposition, click to select/toggle, edit
  a label in place) is a comparatively small conceptual step, not a new
  paradigm bolted onto something that was never about data in the first place.
- The `wt.dsl` lesson from `world-timelines` generalizes directly here: **a
  DSL's own source text can double as the sync substrate**, not just as input
  to a renderer. If a diagram's Mermaid source is the single source of truth,
  and every rendered node/edge is *derived fresh* from it (the same discipline
  that made `wt.dsl` and `raycaster-scene`'s text/fields pair work), principle 1
  is satisfied by construction rather than by remembering to wire up
  `desk.events` correctly every time.

This is **not** a proposal yet — no plan, no TODO item — just the shape of the
most promising concrete next experiment this investigation points toward: take
the existing, real, dependency-free `desk.mermaid` parser/layout/renderer and
ask what the smallest change is that makes one rendered node a bound,
manipulable value, with the diagram's own text staying the single source of
truth for anything else (a second rendered view, a `kind:"python"` widget, a
sibling `kind:"html"` widget) to derive from.

## Update 2026-10-15: from a line-patch primitive to a grammar/AST engine

A design conversation about open question 1 below reframed it substantially —
recorded in full in the new `grammar-ast-live-pane.md`, which now supersedes
this section's original framing. Summary: `world-timelines`'s live DSL editor
pane is, in purpose, a small version of what any live-code tool/IDE editor pane
already does — continuously (re)parse the text to build a structured
representation, and render/validate/suggest from that, rather than from
scattered regex matches. Pulling on that thread surfaced that the raycaster
family (`draw-with-desk`) already needed *real* grammar parsing twice beyond
`wt.dsl`'s flat lines — a line-oriented keyword grammar for camera/scene text,
and a genuine tokenizer + recursive-descent parser for the formula DSL,
**hand-written independently in both TypeScript and Python** with nothing
keeping the two in sync. That's three independently-reinvented parsers in one
project family alone, and the richest of the three (the formula grammar) is
exactly the kind of thing a shared grammar-to-parser engine would remove the
need to duplicate.

This also **unifies with open question 4 below**: an AST with source-position
information per node is exactly the backbone the interactive-Mermaid thread
needs too (click a rendered node → its source span; edit text → reparse →
re-render) — both a live DSL-editor pane and a clickable diagram become
renderers over the same underlying engine, rather than two separate efforts.

**Decision made, with reasoning recorded here rather than just the outcome:**
the grammar will be declared using a dedicated grammar-definition DSL, compiled
into a generated parser — not hand-written parser combinators, even though
combinators are the more pragmatic, lower-effort choice given `CLAUDE.md`'s
"avoid dependencies, prefer bespoke solutions" (a combinator toolkit needs no
new notation or compile step, and `FormulaSyntaxChecker` already shows that
hand-writing a recursive-descent parser directly, without a generator, is
perfectly viable at this grammar's scale). The generator path was chosen
anyway, deliberately: this investigation is also in service of the project
owner's own broader, separate interest in DSL design itself, and a declarative
grammar-definition language is more directly in line with that broader goal
than a pragmatic combinator library would be, even at some extra up-front cost
for this one problem. Recorded explicitly so a future reader doesn't mistake
this for the "obviously correct" engineering choice in isolation — it's a
considered choice made for reasons beyond this investigation's own narrow
scope.

**Status of the new direction**: pressure-testing starts now against the
raycaster formula DSL (the richest real grammar found in the case studies) —
see `grammar-ast-live-pane.md` for the full write-up, the generator's required
properties (source-position tracking, statement/line-level error recovery
matching what all three hand-rolled parsers already settle on independently),
and open design questions the generator itself still needs answered.

## Open questions / possible next steps

Recorded for whoever picks this up next, not yet prioritized or planned. Item 1
is resolved into the new direction above; items 2-3 and 5 are still genuinely
open; item 4 is now understood as part of item 1's resolution, not separate.

1. ~~Formalize the line-patch primitive already proven in the wild.~~
   **Superseded, 2026-10-15** — see "Update" above and `grammar-ast-live-pane.md`.
2. **Decide whether "vis-as-interface" needs new Bridge API surface, or just a
   library.** Everything found so far builds hit-testing/drag-state/coordinate
   conversion by hand per widget (`world-map`, `raycaster-view`, Domain
   Analysis). Is a shared, reusable "bind this rendered mark to this value,
   handle the pointer math" component enough, or does achieving this cheaply
   enough to become the default choice need something declarative (e.g. "this
   SVG node's `cx`/`cy` are bound to state key X, draggable within bounds Y")
   that doesn't require hand-written pointer-event code at all?
3. **Test principle 1 against a second independent writer from day one of any
   prototype.** Every hand-rolled failure found in the case studies (`file-tree`,
   `raycaster-camera`/`-formula`) only became visible once a second writer of
   the same value actually existed — something worth building into whatever
   comes out of this investigation's test plan, not discovered the hard way
   again.
4. ~~The Mermaid-as-interface experiment itself~~ — **folded into item 1's
   resolution, 2026-10-15**: both this and item 1 need the same grammar/AST
   engine with source positions; see `grammar-ast-live-pane.md`. Once that
   engine exists, "one node, one bound value, one other view staying in sync"
   is still the right scoped-small shape for the Mermaid side specifically.
5. If an interactive-Mermaid artifact the project owner remembers building
   does exist somewhere this sweep didn't reach, find and read it before
   designing anything from scratch — it would change several of the
   conclusions above from "no prior art" to "here's what to learn from."
6. **A low-risk, near-term prototype of UX principle 1 itself, needing no new
   grammar at all**: a live raw-Markdown/rendered-preview dual pane for
   Desk's own Markdown widget, re-rendering via `QTextDocument.setMarkdown()`
   (already used today, just not called live) on every edit — the single
   most common, best-understood real-world instance of "derive, don't
   duplicate," and one Desk's own Markdown tooling doesn't have yet. See
   `markdown-and-mermaid-as-dsls.md`'s synthesis. Worth doing before or
   alongside the grammar/AST engine work, not gated on it.

## Related

`investigations/app_structure_dsl_design.md` (the sibling investigation this
one deliberately doesn't duplicate — that one is about multi-widget *app
structure*; this one is about one widget's *content and interaction*),
`.desk_temp/tempui-custom-widgets.md` ("Authoring from real source," the
current baseline this investigation is asking whether to go beyond),
`widget-case-studies.md` (this doc's own evidence base),
`grammar-ast-live-pane.md` (the active direction as of 2026-10-15, superseding
`line-patch-primitive.md`), `markdown-and-mermaid-as-dsls.md` (Markdown and
Mermaid as DSLs in this project's own code, including the retired
`MermaidDiagramWidget` history), `hexsheet-dsl-case-studies.md` (DSLs found in
the not-yet-Desk-integrated `hexsheet` project).
