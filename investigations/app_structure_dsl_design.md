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

Both read in full:

- `../FEEDBACK/FEEDBACK-DESK-app-structure-dsl-and-editor-widget-2026-08-03-1634.md`
  -- a declarative DSL + codegen + editor widget for the hand-written
  wiring/layout/event/worker/cache code of a multi-component SPA,
  written from `world-timelines`.
- `../FEEDBACK/FEEDBACK-DESK-widget-extraction-communication-gaps-2026-08-03-1634.md`
  -- the sibling problem: what breaks when that same app's components
  become separate, independently-sandboxed Desk widget *instances*
  instead of one page sharing one JS object's memory.

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

## Where things were left

Nothing above has been turned into a TODO item or a plan -- this is
purely a discussion record, matching `investigations/feedback_review.md`'s
own established shape for exactly this situation. Open threads, not
yet started:

1. **Gaps 1-6 of `widget-extraction-communication-gaps`** haven't been
   discussed in the same depth the DSL inventory got -- the shared
   project-scoped state store's actual shape (capability model, change
   -notification mechanism, how it composes with `desk.events`), the
   retained-publish-mode idea mentioned in the FEEDBACK item's own
   suggested fix but not yet discussed here, the schema-declaration
   mechanism, and the coordinator-widget pattern all still need real
   design conversation.
2. **The editor widget's actual raw-text+structured-UI sync design**
   hasn't been started at all -- only prior-art research (confirming
   nothing to build on exists) has happened. This needs original
   design: how the two views detect and resolve conflicting edits,
   what "structured UI" actually renders for the event-wiring table
   vs. the layout tree, and how the "reusable building block, not a
   one-off" goal gets realized concretely (a shared TS base class
   alongside `document-editor-base`? something else?).
3. No decision has been made about **which of the two FEEDBACK items'
   threads to actually turn into a TODO/plan first**, or whether they
   should be filed as one combined item or several independent ones
   (the DSL, the editor widget, and the communication-gaps state store
   all have real inter-dependencies but are separable pieces of work).
