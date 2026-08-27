# App-structure DSL and editor widget: design discussion

Records a design conversation had with the user about
`../FEEDBACK/FEEDBACK-DESK-app-structure-dsl-and-editor-widget-2026-08-03-1634.md`
and its sibling `../FEEDBACK/FEEDBACK-DESK-widget-extraction-communication-gaps-2026-08-03-1634.md`
-- the cluster `investigations/feedback_review.md` (TODO `feff1ec`)
flagged as "the real design conversation... speculative and general in
a way that could grow arbitrarily large if not scoped deliberately."
This is a discussion record, not a finished design or a plan -- nothing
below has been turned into a TODO item, and none of it has been
implemented. See "Where things were left" at the end for what's still
open.

## Sources

All read in full:

- `../FEEDBACK/FEEDBACK-DESK-app-structure-dsl-and-editor-widget-2026-08-03-1634.md`
  -- a declarative DSL + codegen + editor widget for the hand-written
  wiring/layout/event/worker/cache code of a multi-component SPA,
  written from `world-timelines`.
- `../FEEDBACK/FEEDBACK-DESK-widget-extraction-communication-gaps-2026-08-03-1634.md`
  -- the sibling problem: what breaks when that same app's components
  become separate, independently-sandboxed Desk widget *instances*
  instead of one page sharing one JS object's memory.
- `../FEEDBACK/FEEDBACK-DESK-shared-state-with-semantic-edits-2026-08-10-2141.md`
  -- a small, concrete instance of the same gap (two widgets in the
  `file-tree` project agreeing on "current directory"), written from a
  different project, found while re-scanning `../FEEDBACK/` for new
  state-store-related items. Sharpens the state-store design below
  with a piece it didn't have yet: semantic edit records.

Also referenced, not re-read in full: `TODO.md`'s `a5f66cc` (COMPLETED)
and `d4368bd` (COMPLETED) entries -- see below.

## Design principles agreed

- **Generalize beyond `world-timelines` without becoming useless
  elsewhere.** The DSL should solve the general shape of problem
  `world-timelines` has, not just that one app -- but the inventory
  below is still grounded in its real, concrete needs rather than
  designed in the abstract.
- **Dual transpilation target / components stay Desk-unaware.**
  Individual web components should be ordinary TypeScript+HTML+CSS --
  no Desk imports, no `window.desk.*` calls, nothing Desk-specific in
  component source at all. All the work to integrate an app into Desk
  happens in the DSL's codegen layer, not in the components themselves,
  and building the app normally (outside Desk) should carry zero
  Desk-related overhead. This isn't a new pattern for Desk -- it
  generalizes `DefineWidget`'s existing "Authoring from real source"
  separation (component source is fully Desk-unaware; `build_widget.py`
  does 100% of the Desk-packaging as a distinct step) up from one
  widget to a whole app's structure. The practical consequence: the
  DSL/codegen needs (at least) two real output targets -- a standalone
  build with no Desk runtime dependency, and a Desk-widget build --
  with Desk-awareness confined to one pluggable codegen target, not
  woven into the generated wiring layer's own shape.

## Layout (part of the original 8-item DSL inventory)

Three modes, agreed:

1. **N-split-panes** (vertical/horizontal stacks, resizable, optional
   restructuring) -- `world-timelines`'s current shape. Tree-shaped
   JSON: `{"type": "hsplit"|"vsplit", "children": [...]}` recursing
   down to `{"type": "pane", "widget": "<name>"}` leaves (leaves
   reference the component registry by name, never inline markup),
   plus per-split resize constraints (min/max, matching
   `world-timelines`'s own clamp-range wiring).
   - **Decided**: "optional dynamic restructuring" scopes to **N named
     static layout trees, switched by name at runtime** -- matches
     `world-timelines`'s real usage (two grid-template-areas variants
     plus a fullscreen-expand-one-panel mode) -- not a general,
     runtime-computed tree. Nothing has asked for the general case yet,
     and it would be much harder to keep visually editable.
2. **Windowed interface** (like Desk's own canvas) -- flat entries,
   `{"type": "window", "widget": "<name>", "x", "y", "width",
   "height"}`, close enough to Desk's own `.desk`-file `WidgetState`
   shape that a "dump current layout" export could reuse that
   vocabulary almost directly.
3. **Raw HTML/CSS/TS** -- no DSL layout involvement; since components
   are plain custom elements by construction (see Design principles
   above), dropping them into hand-written markup already just works,
   nothing extra needed.

For modes 1/2: a simple JSON format with a `"type"` field on every
node (as above), plus a **visual layout-editing widget** (drag/resize
panes or windows, assign a widget by name to a slot) that reads/writes
the same JSON, and a **"dump current layout into HTML/CSS/TS"**
button as a migration path off the DSL.

- **Decided**: that dump is a **one-way eject** -- once dumped, the
  generated HTML/CSS/TS becomes real, hand-owned source for that
  project; the DSL layout file stops being the source of truth. No
  attempt to keep the two in sync after that (real reverse-engineering
  of arbitrary hand-edited HTML back into structured JSON, for a
  benefit nobody has asked for).

## Full DSL inventory: what's in v1

Going through the original FEEDBACK item's 8-part inventory:

1. **Component registry** -- explicit list, `{"tag": "map-panel",
   "source": "components/map-panel.ts"}[]`. Codegen emits the
   import + `customElements.define` boilerplate this replaces.
   Explicit list, not folder-convention auto-discovery (more magic for
   little savings over just listing them).
2. **Layout** -- see above.
3. **Event-wiring table** -- the central plumbing piece. Proposed
   shape: `{"event": "marker-selected", "from": "map-panel",
   "actions": [...]}`, where each action is either a state mutation
   (`{"set": "selectedId", "from": "event.detail.id"}`) or a child
   method call (`{"call": ["timeline-view", "highlightEvent"], "args":
   [...]}`) -- `actions` is an array specifically to support fan-out
   to multiple targets from one event, matching `world-timelines`'s
   own "one handler, several child calls" shape.
4. **State slots** -- plain typed slots with defaults,
   `{"name": "selectedId", "type": "string | null", "default":
   null}[]`, written only by event-wiring actions. Derived/computed
   state deferred to the escape hatch for v1 -- no expression language
   invented for it; nothing in the inventory demands it yet.
5. **Field<->DSL-text-line bidirectional sync sub-DSL** (the
   `query-editor.ts` pattern -- "value present -> emit this line;
   absent -> apply this default"). **Decided: deferred to the escape
   hatch**, not in v1. This is the most narrowly-shaped, single
   -component-specific piece in the inventory; generalizing it well
   from one example risks guessing wrong. Revisit once a second real
   use case shows up.
6. **Worker channel declarations** -- **decided: not a separate
   mechanism**, folded into the event-wiring table (3) instead. A
   worker is just another named "component" that can emit events
   (inbound responses) and be a call target (outbound requests,
   `call: ["query-worker", "postMessage"]`) -- one wiring vocabulary
   instead of two parallel ones.
7. **Cache/data-source declarations** (the slim-list-diff-batch
   -fetch-write-through pattern, IndexedDB wiring, named data-source
   selection). **Decided: deferred to the escape hatch**, not in v1.
   The heaviest, most `world-timelines`-specific piece (its own
   Wikipedia/Wikidata ingestion shape) -- closer in spirit to the
   sibling `batch-ingestion-job-concept` FEEDBACK item than to app
   *structure*. Keep v1 scoped to UI structure/wiring; data-fetching
   stays hand-written via the escape hatch for now.
8. **Escape hatch** -- named handler functions the generated code
   calls out to at declared extension points. Straightforward, and now
   also where items 5 and 7 above live until/unless they're promoted
   into the DSL proper later.

**Net v1 surface**: component registry, layout (3 modes), event-wiring
table (worker channels included), state slots, escape hatch. Items 5
and 7 explicitly out, living in the escape hatch instead.

## Editor widget

The FEEDBACK item's second half: a Desk widget for editing this DSL,
modeled on `world-timelines`'s own `query-editor.ts` (see
`world-timelines/plans/dsl-bidirectional-sync.md`) -- a raw-text view
of the DSL plus structured UI over the top (a visual grid/pane layout
editor, a table/graph view of the event-wiring rules), both writing
back to the same underlying text so neither view can drift from the
other. The FEEDBACK item explicitly frames this as a **reusable
building block** (a shared component/base class, not a one-off for
this one DSL) -- any project-specific DSL a Desk widget wants to edit
could use the same raw-text+structured-UI-sync shape.

**Prior-art research finding**: Desk's own recently-built
`shared-components/document-editor-base/document-editor-base.ts`
(TODO `d4368bd`, a `DocumentEditorBase<Doc>` abstract class a
`kind: "html"` widget extends) is **not** this pattern. It solves file
*lifecycle* only -- title-to-path derivation, create-vs-load
(never clobbers), auto-restoring the last-open document via
`desk.self.getLocalStorage`, and `save()` via `desk.fs.writeFile` on
every discrete edit -- extracted from a real `necro-4x` widget
(`DomainAnalysisElement`) and its siblings, who'd each independently
hand-rolled the same load/save/create lifecycle and hit the same
missing-parent-directory bug doing it. It has no notion of two views
of one document staying in sync; a subclass just holds one in-memory
`Doc`, mutated by whatever UI the subclass builds. It's not currently
used by any real widget in this repo yet (`grep` across `widgets/`
turns up nothing) -- shared-components infra built ahead of its first
real consumer.

No other Desk-side precedent for "raw text + structured view, one
source of truth, bidirectional, no drift" was found anywhere in
`TODO.md`/`PARKINGLOT.md`. **This piece needs genuinely original
design** -- `document-editor-base` remains a real, usable building
block for the "persist the DSL file to disk" half of the editor widget
(if it's authored as `kind: "html"`), but the actual dual-view sync
problem is untouched by anything already built.

**A second real-world data point, found later**:
`../FEEDBACK/FEEDBACK-DESK-domain-analysis-as-builtin-widget-2026-08-27-1236.md`
-- the *same* `necro-4x` widget `document-editor-base` was extracted
from (`DomainAnalysisElement`) has kept generalizing since. Across
~15 follow-up iterations, its own tagging categories went from a
closed TypeScript union, to nine hardcoded members, to a fully
dynamic `CategoryDef[]` stored *in the edited document itself* (a
`## Category Definitions` markdown table, addable at runtime with no
code change), plus multi-domain support (a title field, a
known-domains picker). Nothing in the widget's own code mentions
`necro-4x` anymore -- it's now a general "build a lightweight entity/
relationship model of any domain by tagging free text" tool, the data
format and its own schema both living entirely in the edited markdown
file, not the code. That's a real, independent instance of exactly
the "structured, evolving, in-document schema + a UI over it" shape
the editor-widget design above is reaching for -- a second concrete
argument (world-timelines' `query-editor.ts` being the first) that
building the raw-text+structured-UI sync mechanism as a genuinely
generic, reusable base is worth it, not over-engineering for one DSL.

That FEEDBACK item's own suggested fix is a **separate, narrower ask**
worth tracking on its own, not folded into the DSL/editor-widget work
above: promote Domain Analysis itself (or a reviewed/trimmed version
of it) to a genuine Desk built-in widget, same tier as Sheet/Markdown/
Image Viewer/Editor -- explicitly *not* "just copy the file in," since
real, `necro-4x`-shaped features (a hover-drag affordance, nested
list/tag segments, a proposed-statements review queue, a self-refining
guidance section) would need a real review to decide what's generic
core vs. what's reference-design-only. This is about promoting one
already-built widget, not about DSL tooling/codegen -- a different
piece of work from `app_dsl`/the editor widget above, even though both
stories are instances of the same broader pattern (something
project-specific generalizing into reusable Desk infrastructure).

## Sibling: widget-extraction-communication-gaps

`world-timelines` has 9 components (`world-map`, `timeline`,
`entry-detail`, `query-editor`, `category-picker`, `laneset-picker`,
`boundary-picker`, `settings-menu`, `app-root`) that would each make a
sensible standalone Desk widget, but today only work because they
share one JS object's memory: `app-root` holds every cross-cutting
piece of state, owns the one Worker and the one IndexedDB cache, and
mediates every interaction by calling methods directly on live
references to its children. Splitting them into separate,
independently-sandboxed `kind: "html"` widget instances (each its own
Chromium renderer, by design) breaks all of that.

What Desk already has that helps: the `events` Bridge capability
(`desk.events.subscribe`/`publish`/`onMessage`, TODO `6f9c51b`) is
real, shipped pub/sub between widget instances -- the right shape for
transient *notifications*, not for "what's the current value of X."

Seven concrete gaps identified, with a suggested fix per gap:

1. **No shared state store, only transient notifications** -- a widget
   created after a selection already happened has no way to learn the
   current value; `desk.events` has publish/subscribe, not
   get-current-value. Suggested: a shared, capability-gated,
   **project-scoped state store**, distinct from `getLocalStorage`'s
   per-instance isolation -- change notifications layered on the
   existing `events` mechanism rather than replacing it.
2. **No shared cache reachable from more than one widget** -- each
   `kind: "html"` widget is its own isolated renderer; a separate
   `entry-detail` widget getting only `{id}` over `desk.events` has no
   way to resolve it into a full record without redundant fetch/cache
   logic of its own. Same state-store fix as (1) addresses this.
3. **No shared Worker** -- one `query-worker.ts` owned by `app-root`
   today; splitting raises an undesigned question (duplicate the
   worker per widget, wasteful and risks divergent results, vs.
   designate one widget as query owner, a pattern Desk doesn't name
   yet). Same state-store fix as (1)/(2) gives this a natural home
   ("which widget currently owns query execution").
4. **The DSL<->UI-state sync (item 5, deferred above) becomes
   cross-widget, not intra-object**, and `desk.events` for `kind:
   "html"` widgets is a 30-second-clamped long poll, not synchronous
   or ordering-guaranteed -- real drift risk between widgets
   independently re-deriving state from the same event stream.
5. **Untyped payloads** -- `desk.events` messages carry arbitrary JSON
   with no schema Desk enforces, losing the compile-time safety a
   single-build `types/index.ts` currently gives this data flow.
   Suggested: **optional per-message-name schema declaration** in the
   widget manifest (a JSON Schema Desk validates publishes against).
6. **Cross-cutting orchestration rules have no home** (e.g. "entry
   selection and lane selection are mutually exclusive") -- they live
   in `app-root`'s imperative code today because one object holds live
   references to everything. Suggested: **no new primitive needed**
   once (1)/(5) exist -- a "coordinator" widget instance (or a
   `kind: "python"` headless one) that owns invariants and republishes
   derived events, documented as a recommended pattern rather than
   built into the Bridge API itself.
7. **Multi-file `kind: "html"` widgets don't reliably load** --
   sub-resource requests (`<script src>`, `fetch()` of a sibling file)
   don't carry the per-launch auth token and 401 silently. Flagged as
   *the* prerequisite -- "nothing else here matters if a multi-file
   widget can't load its own JS."

**Key finding**: gap 7 is **already fixed**. TODO `a5f66cc`
(COMPLETED, from earlier in this same session, before this design
conversation started) fixed exactly this -- a same-origin cookie
carrying the token, additive to the existing query-param/header
checks -- and its own `TODO.md` completion narrative explicitly cites
`FEEDBACK-DESK-widget-extraction-communication-gaps-2026-08-03-1634.md`
by name as one of the two independent reports (alongside the
`hex_flower` investigation, TODO `4ab5875`) that motivated it. The
item's own stated top blocker is off the table; gaps 1-6 are what's
actually left.

### Shared state store design (gaps 1-6)

Gaps 1/2/3 all reduce to the same fix, so the design conversation
started there rather than gap-by-gap:

- **Bridge API**: a new `state` capability; `desk.state.get(key)` /
  `desk.state.set(key, value, edit?)`. `set()` closes gap 1 (current
  selection/query results have a real home), gap 2 (a widget getting
  only `{id}` over `desk.events` can resolve it via `get()` instead of
  needing its own redundant cache), and gap 3 (a natural place to
  record "which widget currently owns worker execution" -- the actual
  coordination is then just ordinary read/write against the store plus
  `events`, not a new RPC primitive).
- **Change notifications reuse `desk.events`**, not a new transport --
  `set()` auto-publishes a well-known event (e.g. `desk.state.changed`,
  `{key, value, edit}` payload) rather than inventing a second delivery
  mechanism alongside the one that already exists.
- **Gap 4 (long-poll ordering/latency risk) is addressed by `get()`
  being pull-based, not by fixing the transport.** The drift risk the
  FEEDBACK item describes is specifically about notification-only
  state (nothing retained) -- once there's a real store behind it, a
  widget that missed or was delayed on a change notification can
  always re-fetch the current authoritative value on demand. No change
  to `desk.events`' own 30-second-clamped long-poll delivery is
  needed.
- **Gap 5 (untyped payloads)**: per-key JSON Schema declared in the
  widget manifest, validated on `set()` -- a schema violation returns
  a real error status, the same `err.status`-carrying pattern the
  Bridge client already uses elsewhere (TODO `e86a31b`).
- **Gap 6 (orchestration) needs no new primitive**, confirmed -- a
  coordinator widget is just ordinary code built on `state` + `events`,
  matching the FEEDBACK item's own read once (1) and (5) exist.

**Decided**:
- The store **persists across a Desk reload**, written into the
  `.desk` file -- same pull-based "saved at quit, not on every write"
  model `desk.self.getLocalStorage` already uses, and matches
  `world-timelines`'s own real use case (current selection/query
  results are exactly the kind of thing worth surviving a reload).
- The FEEDBACK item's separately-suggested **"retained" publish mode**
  for `desk.events` (deliver the last message for a name to a
  newly-subscribing widget) is **dropped, not built** -- once
  `desk.state.get()` exists, a retained-publish mode would solve a
  strict subset of the same problem through a second, parallel
  mechanism. Redundant surface area for no real gain.

This closes out `widget-extraction-communication-gaps` entirely: gap 7
already fixed, gaps 1-6 now have a real (if not yet planned/built)
design.

### Semantic edits (folded in from `shared-state-with-semantic-edits`)

`FEEDBACK-DESK-shared-state-with-semantic-edits-2026-08-10-2141.md`
(see Sources) is a small, concrete case -- two `file-tree` widgets,
`DeskConsole` and `DirectoryTreeView`, needing to agree on "current
directory" -- that independently hand-rolled four things on top of
`desk.events`: a private copy per widget, replaying commands instead
of sharing values, a request/response late-join protocol, and a
retry-on-race hack for that protocol. **Three of those four are
already solved by the design above**: `get()` returning the current
value immediately deletes the late-join protocol and its race-condition
retry hack outright (a widget never asks a peer and hopes one's
listening -- it asks Desk, which already knows), and a display-only
subscriber reading a value someone else already computed never needs
its own private copy.

The one piece the design above didn't have: **semantic edits, not just
value replacement**. `DeskConsole` doesn't just want to know the new
directory value -- it wants to know *that a `cd` with this argument
happened*, even when the change originated from the *other* widget (a
tree-view click), so it can render the right history line without
re-deriving "what command produced this transition" from a diff.

**Folded into the design**:
- `set(key, value, edit?)` -- the writer (whichever widget already
  knows the domain semantics) computes the resulting value itself and
  optionally attaches a structured `edit` record (e.g. `{"op": "cd",
  "arg": "desk"}`) describing what produced it. Desk never interprets
  `edit` -- it has no way to run arbitrary widget-authored reducer
  logic -- it's opaque, just stored and relayed, the same way
  `desk.events` payloads already are today.
- Subscribers receive `(value, edit)` on every change (change
  notifications, and history entries below, both carry the pair) -- a
  value-only subscriber ignores `edit`; a semantics-aware one (like
  `DeskConsole`) uses it directly instead of diffing.
- `edit`'s shape can reuse the same per-key JSON Schema validation
  already planned for gap 5 -- covering both the value's shape and the
  edit's shape, not just the value's.
- **Decided**: the store retains a **small, bounded history of past
  (value, edit) pairs per key**, not just the current one -- queryable
  via `getHistory(key, limit)`, so a widget that just reconnected or
  reloaded can catch up on what happened while it wasn't listening
  (e.g. reconstructing `DeskConsole`'s own command-log display),
  rather than only ever seeing "what's true now." **Decided**: the
  history is a **fixed-size-N FIFO queue** per key -- for a cap of N,
  the history always holds exactly the N most recent edits, oldest
  dropped as new ones arrive; entries are returned **latest-first**
  from `getHistory`. N is a **fixed, small default, not per-key
  configurable in v1**; and the history **persists across a Desk
  reload** alongside the value itself, for the same consistency reason
  the value's own persistence was decided (a widget reloading right
  after Desk restarts shouldn't see a value with no explanation of how
  it got there).

## Where things were left

**Update**: the app-structure DSL itself (schema/parser/codegen -- the
"Full DSL inventory" section above) is no longer just a discussion
record -- filed and implemented as TODO `48e3b39`
(`plans/app-structure-dsl.md`, COMPLETED). Layout mode 1, the
event-wiring table, state slots, and the escape hatch are real,
tested code (`app_dsl/` at this repo's root); layout mode 2 and the
eject feature remain deferred, as designed above. The rest of this
section's own open threads are otherwise unaffected -- this is a
discussion record for everything else below.

**Update 2**: the ES-modules-vs-`build_widget.py` packaging gap found
while implementing TODO `48e3b39` is also now resolved -- TODO
`1e032f3` (`plans/app-dsl-global-codegen-mode.md`, COMPLETED) added a
second, module-free codegen mode (`--mode=global`) matching
`document-editor-base.ts`'s own global-script convention, confirmed
via a real compile+concatenate+`vm.runInThisContext` round trip (the
same execution model a real concatenated `<script>` tag uses). The
app-structure DSL's "dual transpilation target" goal is now actually
proven for both targets, not just the standalone one -- with the
documented tradeoff that a Desk-widget-targeting project's component/
handler source must avoid ES module syntax (no automatic sharing of
component source between the two targets without a real bundler,
which was deliberately not pursued here).

Open threads, not yet started:

1. **The editor widget's actual raw-text+structured-UI sync design**
   hasn't been started at all -- only prior-art research (confirming
   nothing to build on exists) has happened. This needs original
   design: how the two views detect and resolve conflicting edits,
   what "structured UI" actually renders for the event-wiring table
   vs. the layout tree, and how the "reusable building block, not a
   one-off" goal gets realized concretely (a shared TS base class
   alongside `document-editor-base`? something else?).
2. **The shared, project-scoped state store** (`desk.state.*`,
   including the semantic-edits refinement) is fully designed at a
   discussion level but not yet filed as a TODO or implemented.
3. **Promoting `necro-4x`'s Domain Analysis widget to a genuine Desk
   built-in** (see the new data point folded into the "Editor widget"
   section above) is a real, separate, not-yet-scoped ask -- a design/
   code review against Desk's own built-in bar, a decision on what's
   generic core vs. `necro-4x`-specific, and (per the FEEDBACK item's
   own point 2) picking up `set_file`/`OpenWithWidget` tempui support
   and the `document-editor-base` auto-load/auto-save pattern along
   the way if adopted. Not filed as a TODO yet.
