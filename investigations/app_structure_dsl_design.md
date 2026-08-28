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

### Validated vs. non-validated state, and schema lifecycle

Resolved in a follow-up round of clarifying questions (this file's own
earlier draft had "per-key JSON Schema declared in the widget
manifest" without saying whose manifest, or what happens on
conflict -- both now answered):

**Every state key is either validated or non-validated, decided by
whether a schema is currently registered for it, not declared per
access:**

- **Validated**: a schema (a TypeScript type expression, stored as a
  string -- e.g. `"string | null"`) is currently registered for the
  key. A schema can be declared two ways, both optional -- **schema
  declaration is never required to use a key at all** (see the
  undeclared-access case below):
  1. **In a widget's own manifest**, for a widget that reads/writes
     that key.
  2. **"Top-level"**, in a schema's own standalone file, independent
     of any widget's manifest -- for state that should have a
     canonical schema without tying its lifecycle to any one widget's
     placement (see enforcement lifetime, below). Same schema syntax
     either way.
  - **Conflict resolution**: first-loaded-while-still-active wins. A
    widget attempting to load with a schema that conflicts with an
    already-active one for the same key **does not load at all** --
    no placement, not even a normal placement notification. Instead,
    a distinct, clickable notification appears (the same UI shape as
    every other tempui-style notification -- Job/Scratch/Question)
    that explains the validation conflict when clicked, **and** the
    same error message is appended to a new, well-known, optional
    manifest field, `desk_widget_loading_errors: string[]`, on the
    failing widget's own manifest -- so the conflict is discoverable
    both in-the-moment (the notification) and later, just by reading
    that widget's own definition, without needing to have seen the
    notification live.
  - **Enforcement lifetime differs by how the widget got there**:
    - A **tempui-DSL-placed widget instance** (`DefineWidget`-sourced,
      or any tempui-registered kind) keeps its declared schema
      enforced only while at least one **placed widget instance**
      referencing it still exists on the canvas ("placed widget
      instances," not "active widgets" -- the DSL's own established
      instance-tracking vocabulary). Removing the last such instance
      makes the schema **dormant, not deleted** -- neither the schema
      nor the underlying data is destroyed, so a later instance of the
      *same* definition can keep using the data if its schema is
      unchanged, and a later instance with a genuinely *different*
      schema is allowed to replace the dormant one (only a conflict
      against a *currently enforced* schema blocks loading -- a
      dormant one doesn't).
    - Before checking for a conflict at widget-load time, Desk first
      does maintenance on the schema's own placed-instance list,
      pruning any instance that's no longer actually placed -- this is
      what lets a schema correctly go dormant once its last real
      referent is gone, rather than staying wrongly "active" forever
      because nothing ever re-checked.
    - A **built-in widget** (a real `widgets/<id>/` directory, `kind:
      "python"`/`"html"`, found via `discover_widgets` -- not a
      tempui-DSL registration) declaring a schema has it validated at
      **discovery time** and **permanently enforced** from then on,
      regardless of whether any instance is ever placed -- no
      placed-instance tracking or dormancy for these; the manifest
      itself is the permanent commitment.
    - A **top-level schema file** is enforced the same permanent way a
      built-in widget's schema is -- it isn't tied to any widget's own
      placement lifecycle at all, by construction.
  - **Undeclared access to an already-validated key**: a widget can
    read/write a key that has an active schema (from some *other*
    widget's manifest, or a top-level file) without declaring that
    schema itself -- its calls are checked against the key's currently
    -active schema **at runtime**, and a mismatch is a real runtime
    error (not a load-time failure, since nothing was declared to
    conflict with in the first place).
- **Non-validated**: no schema is currently registered for the key at
  all. Access is purely call-site-local: `get(key, typeHint)` attempts
  to coerce the raw stored value to `typeHint`; `set(key, value,
  typeHint)` coerces `value` to `typeHint` before writing. Nothing
  persisted or declared -- a different call elsewhere can use a
  completely different hint (or none) against the same key with no
  cross-checking at all. This is deliberately the loose, no-guarantees
  end of the spectrum -- validated state is what a widget author opts
  into when they want the real guarantee.
- **Schema type expressions**: a pragmatic, intentionally-constrained
  subset of TypeScript type syntax for v1 (primitives, literal unions,
  arrays, simple object shapes -- not the full language), left open to
  grow later if a real need for more shows up. Matches
  `app_dsl/schema.py`'s own `StateSlot.type` convention exactly (a raw
  TS type string), not a new, separate schema language.

**New planned piece: a built-in schema/state-management widget.**
Lets a user/agent see what validated state currently exists (both
widget-declared and top-level schemas), their current enforcement
status (active/dormant, and for tempui-sourced ones, which placed
instances are keeping them active), current values, and history --
and is where a top-level schema file would actually get authored/
registered. **Whenever any schema is registered** (a widget's own
manifest declaring one, or a new top-level schema file), Desk must
guarantee an instance of this widget is already placed, or place one
if not -- so validated state is never invisible the moment it starts
existing. Worth noting for whoever implements this: `DefineWidget`
itself once tried auto-placing an instance on first registration
(TODO `5ff02d2`) and reverted it (TODO `dafbaab`) as "too confusing in
practice" -- but that was a *per-newly-registered-custom-widget-kind*
auto-placement (one new instance per kind, could happen often); this
is a *singleton* dashboard widget (auto-placed at most once, the same
instance keeps serving every subsequent schema registration), a
different enough shape that the earlier revert's own reasoning may not
transfer directly -- worth a real check against the actual UX, not
just assumed safe by analogy.

### Bookkeeping and call sites (implementation architecture)

Resolved in a follow-up round -- the state store's bookkeeping splits
into two pieces with genuinely different lifetimes, and each piece has
a clear existing precedent to mirror rather than a new mechanism to
invent:

- **Data (persisted)**: the actual `(value, edit, history)` per key.
  Exactly the same shape `Desk.custom_widgets`/`Desk.file_type_registry`
  already are (`src/desk/desks.py`) -- a new `Desk.state:
  dict[str, StateEntry]` field, read/written by `load_desk`/
  `save_desk`/`desk_state_dict` the same way those two already are. No
  new persistence mechanism.
- **Schema registry (runtime-only, never persisted)**: which key
  currently has an active schema, its source (a widget id or a
  top-level file path), and (tempui-placed sources only) which placed
  instance ids are keeping it active. This never needs its own
  persistence -- everything that populates it is already re-walked on
  every Desk open anyway (built-in widgets are re-discovered every
  startup/switch; placed instances are re-created every restore), so
  it can simply be rebuilt fresh each time, the same
  lock-protected-runtime-class shape `EventMediator` already is
  (constructed once per server run).

**Call sites this hooks into:**
- `discover_widgets` (`src/desk/widgets.py:65`) -- where a built-in's
  declared schema gets validated and registered **permanently** (no
  instance tracking at all for these). **Decided**: a built-in-vs
  -built-in conflict is resolved by `discover_widgets`' own existing
  alphabetical directory-sort order (first alphabetically wins,
  nothing new to add there) -- surfaced via the same notification +
  `desk_widget_loading_errors` treatment as any other conflict, just
  fired once at Desk startup/switch (whenever discovery re-runs)
  instead of at a click-to-place moment, since there's no placement
  moment for a built-in to hang it on.
- **A new discovery step for top-level schema files**, alongside the
  above -- same permanent-registration treatment. **Decided**: two
  possible locations, both watched: `.desk_temp/schemas/` (ephemeral,
  alongside the rest of `.desk_temp`) and `./desk-schemas/` (a real,
  git-tracked project-root convention, the same tier as `desk_widgets/`
  -- Desk **never creates this directory eagerly**, only watches for
  it and picks it up immediately if an agent or user creates it by
  hand). Both need their own **new** watch registrations --
  `TempUiManager`'s existing `.desk_temp` watch is non-recursive
  (`recursive=False`, `temp_ui_manager.py:249`), so it does not cover
  a `.desk_temp/schemas/` subdirectory at all today, and
  `./desk-schemas/` is outside `.desk_temp` entirely.
- `_place_widget` (a fresh placement) and `_load_desk_widgets`
  (`window.py:321`, a restore) -- where a schema-declaring widget's
  conflict check has to run *before* the instance is actually created:
  join an existing active/matching schema, reactivate/replace a
  dormant one, or hard-fail (no placement at all) on a genuine
  conflict against something still active.
- `close_widget`/`close_widget_by_instance_id` -- **Decided**: no
  special handling needed here. Instance-list maintenance stays
  **lazy only**, exactly as originally specified -- a closed
  instance's id is pruned the next time some *other* widget's load
  triggers the maintenance pass on that same schema, not eagerly at
  close time. `WorkspaceView.clear_widgets()` (a Desk switch, not a
  permanent close) needs nothing special either, for the same reason
  the schema registry itself needs no persistence: switching Desks
  discards the whole in-memory registry, which gets rebuilt fresh
  whenever that Desk is reopened.

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

**Update 3**: the shared, project-scoped state store's non-validated
core (item 2 below) is no longer just a discussion record either --
filed and implemented as TODO `f68383f` (`plans/shared-state-store.md`,
COMPLETED): `desk.state.get(key)`/`set(key, value, edit)`/
`getHistory(key, limit)`, gated by a new `state` capability, with
change notification via a single well-known `desk.events` message
(`desk.state.changed`) and a fixed-50-entry, latest-first, per-key
FIFO history, persisted alongside `Desk.custom_widgets`/
`file_type_registry`. The schema/validation layer designed alongside
it (conflict resolution, dormant-not-deleted schemas, top-level schema
files, the schema/state-management widget) is filed separately as TODO
`6e1c2fe`, still blocked on this landing first, deliberately not
started.

Open threads, not yet started:

1. **The editor widget's actual raw-text+structured-UI sync design**
   hasn't been started at all -- only prior-art research (confirming
   nothing to build on exists) has happened. This needs original
   design: how the two views detect and resolve conflicting edits,
   what "structured UI" actually renders for the event-wiring table
   vs. the layout tree, and how the "reusable building block, not a
   one-off" goal gets realized concretely (a shared TS base class
   alongside `document-editor-base`? something else?).
2. **The shared, project-scoped state store's schema/validation
   layer** (TODO `6e1c2fe`, blocked on `f68383f` -- now COMPLETED, see
   Update 3 above): conflict resolution, dormant-not-deleted schemas,
   permanent enforcement for built-ins, the new file-watcher wiring for
   `.desk_temp/schemas/`/`./desk-schemas/`, and the new schema/state
   -management widget are all thoroughly designed at a discussion level
   but not yet planned or implemented. Nothing structural left open;
   what remains is implementation-level detail that a real plan would
   work out, not further design discussion.
3. **Promoting `necro-4x`'s Domain Analysis widget to a genuine Desk
   built-in** (see the new data point folded into the "Editor widget"
   section above) is a real, separate, not-yet-scoped ask -- a design/
   code review against Desk's own built-in bar, a decision on what's
   generic core vs. `necro-4x`-specific, and (per the FEEDBACK item's
   own point 2) picking up `set_file`/`OpenWithWidget` tempui support
   and the `document-editor-base` auto-load/auto-save pattern along
   the way if adopted. Not filed as a TODO yet.
