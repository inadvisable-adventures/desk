# Case studies: existing `kind: "html"` widgets in peer projects

Supports `investigations/ux-dsl/dsl-for-agent-widgets.md` (read that first for the
hypothesis and the two UX principles these case studies are read against). This
doc is the evidence: real `DefineWidget`-authored `kind: "html"` widgets found by
searching every sibling project under `../` (`/Users/mphair/inadvisable-adventures/`)
and `../../claude-projects/` (`/Users/mphair/claude-projects/`) for a `.desk_temp/widgets/`
(un-promoted source) or `desk_widgets/` (promoted source) directory, 2026-10-14.

Projects searched with **no** widgets of this kind found: `FEEDBACK`, `desk-stable`,
`discussion-for-desk`, `research`, `sep-contacts`, and every project under
`claude-projects/` (`desk`, `gurdmaar`, `gurdmaar-old`, `hexsheet`, `ia-metacampaign`,
`inadvisable-archive`, `llm-dev-process`, `make-static`, `receipts`,
`riverside-download`, `tables-and-text`, `world-timelines`). `desk-dev-2` has one
(a throwaway test harness, included below for completeness). Four projects had real
widget families worth studying: **`file-tree`**, **`draw-with-desk`**, **`necro-4x`**,
and **`world-timelines`** (the largest, 9 widgets ported from one single-page app).

Each write-up below is a research subagent's own output (lightly reformatted, not
rewritten) from reading the actual widget source in full, with file:line citations
throughout so every claim is checkable. Two UX principles are referenced
constantly — see the main doc for their full statement:

1. **Sync** — if a value can be manipulated or viewed from more than one place at
   once, those views/controls must stay in sync.
2. **Vis-as-interface** (Tufte) — the visualization of data should itself be (or be
   a major part of) the interface to manipulating it, not a passive picture next to
   separate controls that do the real work.

---

## `file-tree`

Two widgets, `DeskConsole` and `DirectoryTreeView`, both navigating one parsed
snapshot of `directory-tree.md`'s ASCII tree, each independently tracking "current
directory" and trying to stay agreed via hand-rolled `desk.events` traffic. This
pair is also the subject of `../FEEDBACK/FEEDBACK-DESK-shared-state-with-semantic-edits-2026-08-10-2141.md`
and this project's own `investigations/app_structure_dsl_design.md` — the write-up
below confirms that characterization directly against the code.

### DeskConsole

**File:** `/Users/mphair/inadvisable-adventures/file-tree/.desk_temp/widgets/desk-console/desk-console.ts` (+ `widget.html`, `widget.json`)

**What it's for.** A terminal emulator (`cd`/`ls`/`pwd`) over a *static* directory listing. On init it reads one real file, `directory-tree.md` (`SOURCE_FILE`, line 36), via the `fs` capability, and parses the first fenced code block's ASCII tree (box-drawing characters `├── `/`└── `) into a `TreeNode` tree (`extractFencedBlock`/`parseTree`, lines 53-91). There is no real filesystem navigation — the console is a REPL over this one parsed snapshot, matched to the real project directory only to decide where `cd` starts (`manifest.directory` lookup, lines 168-176).

**Interaction model.** A single `<input>` (`widget.html` line 93) takes command text; Enter triggers `handleUserSubmit` (lines 252-282), which dispatches to `execCd`/`execLs`/`execPwd` (lines 216-250) via a `switch` (lines 262-274), appends a scrollback entry (`pushHistory`, lines 352-361), and updates the prompt label. That's the entire surface — no buttons, no clickable output; it's a classic text-in/text-out shell, not a manipulable picture.

**Multiple views / sync.** DeskConsole and DirectoryTreeView both track "current directory," and the characterization in `investigations/app_structure_dsl_design.md` holds up against the code, point for point:
- **Private copy per widget:** `private currentTreePath: string[] = []` (line 122) is this widget's own mutable copy; DirectoryTreeView keeps an entirely separate one (`directory-tree-view.ts` line 105). Nothing is shared by reference or by a common state object.
- **Command replay, not value sharing:** successful local `cd`/`ls` are broadcast as the *command*, not the resulting path — `publishCommand` (lines 284-292) does `desk.events.publish(CD_EVENT/LS_EVENT, { arg })`. The receiving side re-derives the new directory by calling its own `execCd`/`execLs` again inside `handleRemoteEvent` (lines 294-315, specifically 306-314) — each instance replays the command against its own private tree copy rather than being told the new value.
- **Late-join request/response:** lines 39-44 document the intent explicitly ("a newly-connected instance publishes REQUEST_EVENT once on startup; every already-open instance... answers with CWD_EVENT carrying its own absolute tree path"). Implemented as `respondToRequest` (317-322, publishes `CWD_EVENT` with `{ treePath: this.currentTreePath }`) and `adoptSyncedCwd` (324-331, validates and adopts it, sets `cwdSynced = true`). This one leg of the protocol *does* ship an actual value, unlike the ongoing `cd`/`ls` traffic which only ships commands.
- **Retry-on-race:** `requestSync` (337-350) fires `attempt()` immediately, then again at 500ms and 1500ms via `setTimeout`, gated by the `cwdSynced` flag, with the comment at lines 333-336 spelling out the exact race being patched ("two instances reloaded at nearly the same moment").
- Gap not called out in the design doc: late-join only syncs *current directory*, not the scrollback `history` array — a newly opened console starts with empty/persisted-only history even if its cwd gets adopted from a peer.

**Vis-as-interface?** No. Output is plain text lines (`appendHistoryDom`, lines 370-390); there's nothing to drag or click on in the rendered history or prompt.

**DSL/declarative pattern.** None really. The one schema-ish artifact is the ASCII-tree parser (lines 53-91), which is a bespoke, position-based text parser tied to an external script's exact output format (comment lines 47-49, "Matches... gen_tree.py") — implicit, undocumented-outside-a-comment coupling, not a declared schema. Command dispatch is an ordinary imperative `switch`.

**Stated UX intent.** Lines 39-44 (late-join rationale) and 333-336 (retry rationale) are the only explicit UX/behavior comments; lines 168-172 clarify that *pwd and everything shown* come from the parsed tree data, never from the real absolute path, to avoid leaking real filesystem structure above the tree's root.

### DirectoryTreeView

**File:** `/Users/mphair/inadvisable-adventures/file-tree/.desk_temp/widgets/directory-tree-view/directory-tree-view.ts` (+ `widget.html`, `widget.json`)

**What it's for.** A visual companion to DeskConsole: same `directory-tree.md` tree, rendered as nested `<fieldset>` boxes (one per path segment, `renderChain`, lines 288-304) with the current directory's subdirectories as clickable boxes and its files as a plain list (`buildContents`/`buildSubdirRow`/`buildFileList`, lines 306-345).

**Interaction model.** Clicking a subdirectory box (`box.addEventListener("click", ...)`, line 326) calls `handleSubdirClick` (253-262), which runs `execCd(name)` locally, re-renders, persists to local storage, and publishes `CD_EVENT` so DeskConsole (and any other DirectoryTreeView instance) can follow. There is no control to go *up* a level or jump to root from this widget's own UI — the nested-fieldset "breadcrumb" is decorative (legends have no click handlers; only `.subdir-box` buttons do) — ascending only happens by typing `cd ..` in DeskConsole and having the event propagate here, or by a remote peer's `cd`.

**Multiple views / sync.** Identical architecture to DeskConsole, essentially line-for-line in places:
- **Private copy:** `private currentTreePath: string[] = []` (line 105), independent of DeskConsole's.
- **Command replay:** `execCd` (180-199) is a near-duplicate of DeskConsole's own method, with an explicit comment admitting the duplication is deliberate and must stay byte-for-byte compatible: "Mirrors Desk Console's own cd semantics exactly, so the same event payload produces the same resulting directory in both widgets" (lines 178-179).
- **Late-join + retry:** same `REQUEST_EVENT`/`CWD_EVENT` pair and the same 0/500/1500ms retry schedule, with comments **copied verbatim** from desk-console.ts (lines 30-39, 234-237).
- Explicit cross-widget coupling comment at lines 30-32: "both parse the same directory-tree.md and speak the same cd event so the two can mirror each other's current directory in real time" — the widgets know about each other by convention (same event names, same tree-parsing logic) with **no shared primitive enforcing it.**

**Vis-as-interface?** Yes — the clearest hit of principle 2 among all three `file-tree`/`desk-dev-2` widgets: the rendered tree boxes are the only navigation control, no separate text field or dropdown next to the picture. The shortfall is asymmetry: the view can go deeper by click but can't go shallower by click, and can't show DeskConsole's command history.

**DSL/declarative pattern.** Same verdict as DeskConsole: the tree parser is essentially copy-pasted rather than shared via any common module or schema.

**Bottom line on this pair:** the design-doc characterization matches the code precisely — private per-widget copy of current directory, sync-by-replaying-commands (not broadcasting resulting values), a one-shot request/response late-join handshake, and a 0/500/1500ms retry schedule patching a startup race — all hand-rolled on top of raw `desk.events`, duplicated almost verbatim across two separate files instead of factored into any shared state abstraction. This is the single clearest "what goes wrong without a real shared-state primitive" example in the whole sweep.

### `desk-dev-2`: RecordingLogCheck — not a real widget

**File:** `/Users/mphair/inadvisable-adventures/desk-dev-2/.desk_temp/widgets/recording-log-check/recording-log-check.ts`

Explicitly a throwaway dev/debug harness, not a real user-facing widget — its own header comment says so directly: "Live end-to-end check for TODO 0532852... The point isn't the widget itself; it's giving the agent/user something to record against" (lines 1-9). One button incrementing a counter, one `desk.log.line` call per `recording`/`stopped_recording` event. No cross-widget sync, no declarative patterns, no case study worth forcing onto it.

---

## `draw-with-desk`: the raycaster family

Five promoted widgets (`raycaster-camera`, `raycaster-scene`, `raycaster-formula`,
`raycaster-view`, `raycaster-histogram`) plus one still-un-promoted-but-current
sibling (`raycaster-runtimes`) and a shared grammar/helper module
(`_raycaster-shared/raycaster-dsl.ts`) — a raycasting-renderer demo deliberately
split into multiple simultaneous views/controls over **one** shared simulation
(camera pose, scene objects, color/postprocess formulas). The single best
real-world test of UX principle 1 in this whole sweep, because it's the one
family explicitly designed around "several widgets, one underlying simulation."
Two throwaway/superseded dev widgets (`raycaster`, plus `voice-brainstorm` and
`mobile-bridge-monitor` from elsewhere in the same project) are covered too, more
briefly.

### How the family actually shares state

The five promoted widgets plus `raycaster-runtimes` share live simulation data
**exclusively through Desk's shared `desk.state` store**, at fixed JSON keys:
`raycaster.camera.<id>`, `raycaster.scene.<id>`, `raycaster.formula.<id>`,
`raycaster.render.<cameraId>`, `raycaster.runtimes.<cameraId>`.
`_raycaster-shared/raycaster-dsl.ts` is **not** itself a sync mechanism — it has
zero `desk.state`/`desk.events` calls anywhere in its 851 lines. It's a
duplicated-on-purpose *parsing/serialization/validation* library (mirroring a
Python job's own DSL grammar) that every widget concatenates ahead of its own
`.ts` via `tsconfig.json`'s `"files"` ordering, so every widget gets identical
model types/parsers — but each widget still makes its own independent
`desk.state.get/set` calls; the DSL file never touches state itself.

So the real sync mechanism is: (a) `desk.state` as the single source of truth per
key, plus (b) `desk.events.subscribe(["desk.state.changed"])` + `onMessage` as the
*push* layer that lets a widget notice a key it cares about changed elsewhere. But
**not every widget in the family actually has (b)**: `raycaster-camera` and
`raycaster-formula` declare only `["state"]` in their manifests and never
subscribe to `desk.events` at all (grep confirms zero `subscribe`/`onMessage`
occurrences in either `.ts`). `raycaster-scene`, `raycaster-view`,
`raycaster-histogram`, and `raycaster-runtimes` all declare `"events"` too and do
subscribe. Concretely:

- **Camera pose and formula coefficients are NOT live-synced across multiple
  simultaneous editors.** If two `RaycasterCamera` instances are both pointed at
  `camera-1`, each loads its own private `this.model` once (`raycaster-camera.ts:71,185`)
  and never refreshes unless the user re-types the Camera ID or reopens the
  widget. An edit writes straight to `desk.state.set(this.stateKey(), this.model)`
  (line 233) with **no optimistic-concurrency `edit` token used** anywhere in the
  family. Two simultaneous camera editors can silently clobber each other,
  last-write-wins, with the loser's view showing stale data indefinitely. Same
  gap, same mechanism, for `RaycasterFormula`.
- **Object selection (one specific value inside scene state) IS live-synced, and
  across two different widget *types*.** `RaycasterView`'s hitmap click writes a
  new `selected` flag directly into `raycaster.scene.<id>` (`raycaster-view.ts:482-488`)
  without ever talking to a `RaycasterScene` instance. `RaycasterScene` is the one
  widget built to notice this: it subscribes to `desk.state.changed` and reloads
  whenever its own watched key changes (`raycaster-scene.ts:19-22,109-126`), so an
  open Scene panel's "selected" checkbox updates promptly after a hitmap click
  elsewhere. This is the family's one clean, verified instance of principle 1
  working across independent widget instances.
- **`RaycasterView` itself is the downstream convergence point** for
  camera+scene+formula: it watches all three keys and debounce-reschedules a full
  render (400ms) whenever any changes from any source, including a sibling
  widget's field edit (`raycaster-view.ts:386-396,497`). That direction of sync
  (editors → rendered view) is real and works. The reverse direction for camera
  pose (rendered view → editors) does not exist at all.

### Central interaction-model finding (principle 2)

**Nothing in this family lets a user drag on the rendered picture to change
camera position, look-at, FOV, or any formula coefficient.** The only
picture-driven mutation anywhere is `RaycasterView`'s hitmap **click** (not drag)
that toggles which object is "selected" (`raycaster-view.ts:464-493`). Every other
value — eye/look-at vector, resolution, Monte Carlo N, which scene/formula a
camera uses, every object's x/y/z/size/color/pattern, every formula line — is
edited exclusively through text-DSL `<textarea>`s or `<input type="number">`/`<select>`
fields. There are no sliders, no draggable handles, no canvas-based direct
manipulation anywhere in the family — even `RaycasterHistogram`'s canvas is
explicitly "no hover/tooltip interactivity" (line 33-35) read-only chart drawing.
So principle 2 is realized only for the single narrow case of object selection;
for every other parameter the rendered image is a strictly passive output sitting
next to the real controls — exactly the pattern Tufte's principle argues against.

### `.desk_temp/widgets/raycaster/` — superseded prototype, brief note

The original, self-contained monolithic widget that the promoted family replaced:
one text editor + one fields panel for the *whole* scene, no `desk.state`, no
`desk.events`, no shared DSL import, auto-re-rendering by calling
`desk.installedJobs.run` directly. Fully superseded by the camera/scene/formula/view
split; not a live member of the current family.

### `.desk_temp/widgets/raycaster-runtimes/` — live but not yet promoted

Unlike `raycaster/`, this one *is* live and current: its `tsconfig.json` lists the
shared DSL file ahead of its own, exactly the promoted pattern, and it reads
`raycaster.runtimes.<cameraId>`, written only by `RaycasterView`. A pure read-only
log of the 5 most recent job-run durations for one camera, correctly subscribed
to `desk.state.changed`. No manipulation at all — the opposite pole from
principle 2; its one virtue is that it *is* correctly, promptly kept in sync with
the one widget that produces its data.

### `desk_widgets/raycaster-scene/`

Owns one scene's world objects at `raycaster.scene.<id>`. A raw DSL `<textarea>`
and a structured "Objects" panel (number inputs/selects per object, a per-object
"selected" checkbox) sit side by side; typing re-parses and re-renders fields,
editing a field re-serializes to text — both paths funnel through one
`saveToState` (lines 168-203). This is the one widget that explicitly closes the
external-write loop its own top comment calls out (lines 16-22): `RaycasterView`'s
hitmap click writes `selected` directly into this same key, and this widget
subscribes to `desk.state.changed` to reload when it does. It's also the one
widget where two *instances* of the same type pointed at the same scene id would
correctly see each other's writes (both listen for the same key's change event) —
unlike camera/formula. No drag-on-canvas for geometry; the only picture-linked
affordance is indirect (the *other* widget's hitmap click flips this widget's
checkbox). DSL pattern: a clean declarative round-trip — one shared grammar, two
independent read/write views over the same parsed model, no state separate from
`this.state.objects`.

### `desk_widgets/raycaster-formula/`

Owns one formula set's color/postprocess DSL text, capabilities `["state"]`
only — **no events capability at all**, confirmed by code. Two independent
`<textarea>`s (no structured-fields mirror here — the raw text *is* the only
view), each validated syntax-only on edit (never evaluated — the widget's own
comment is emphatic about this, lines 10-17) and only persisted on success. No
live sync across instances or to any other widget type: `RaycasterView` only
picks up a fresh formula because it separately watches that key itself, not
because this widget pushes anything. One of the two concrete principle-1 gaps in
the family (the other being `raycaster-camera`). No rendered feedback inside this
widget at all. DSL pattern: the most clearly "DSL-as-the-whole-interface" widget
in the family — a real recursive-descent syntax checker backs the two textareas,
with no structured/graphical alternative at all, by explicit design.

### `desk_widgets/raycaster-view/`

The orchestrator: resolves a camera id's state (incl. which scene/formula it
references), compiles it into a job config, runs the raycasting Installed Job,
and displays 5 output images. The richest capability set in the family
(`["state","events","fs","installed_jobs"]`). Interaction model: a Camera-ID text
field plus five read-only `<img>`s, of which exactly one — the hitmap — has a
click handler. Dragging any image is explicitly *blocked* (a defensive
workaround for a known Desk bug, not a feature) — so even accidental
drag-manipulation is disabled, reinforcing that this widget's picture is a strict
display surface outside the one hitmap click. This is the family's convergence
point: subscribes to `desk.state.changed` and watches up to three keys at once,
debounce-rescheduling a render on any change "from any source" (its own comment).
It also documents and works around Desk's self-publish suppression explicitly —
after its own hitmap-click write to the scene key, it calls its render-scheduler
directly rather than relying on the event echoing back, because it won't. Partial
principle-2 win: the hitmap image is literally clicked to mutate world state
(object selection) — genuine direct manipulation — but camera pose/FOV/resolution,
the parameters actually named in this investigation's framing, are never touched
through this widget's picture at all.

### `desk_widgets/raycaster-histogram/`

Reads a render's histogram data and draws six small-multiple bar+line charts on
canvas. Pure read, pure draw — "No hover/tooltip interactivity... consciously
scoped out for this small, internal debugging widget" (its own comment, lines
33-35). Subscribes to `desk.state.changed`, watches the render key, redraws
promptly on change — correct, verified downstream sync, but the purest "passive
picture" in the family by its own admission. Notably documents a deliberate,
informed exception to this project's own dataviz-skill guidance (dual y-axis,
normally discouraged, justified explicitly in a comment as "an informed, explicit
exception... not an oversight") — a good example of UX-principle reasoning made
verifiable in-code rather than left tacit.

### `desk_widgets/raycaster-camera/`

Owns one camera's resolution/eye/look-at/Monte-Carlo-N and which scene+formula it
renders against. Capabilities `["state"]` only — **no events**, confirmed by
code. A DSL textarea and a structured fields pane are kept in sync *within one
instance* perfectly (same in-memory model, each direction's handler calls the
other's render function) — a solid local win for principle 1. But across
instances or widget types there is **no live sync at all**: a second
`RaycasterCamera` instance on the same id, or any sibling widget, leaves this
instance showing stale data until the user manually re-selects the Camera ID.
This is the clearest, most consequential principle-1 gap in the whole family —
camera pose is exactly the parameter this investigation's framing names, and it
has the weakest cross-view guarantee of anything examined. No rendered picture
lives in this widget at all.

### `desk_widgets/_raycaster-shared/raycaster-dsl.ts`

Not a widget — a plain-global-script shared source file (no import/export, so
each widget's own `Window` augmentation still merges). Provides the camera DSL
grammar, the scene/objects DSL grammar, a hitmap-grey assignment algorithm that
exactly mirrors the Python job's own version (so the client can recompute
selection mapping with no round trip), a syntax-only formula-DSL checker (no
evaluator, by design), and the final job-config compiler. The common
vocabulary/grammar layer the family's widgets all compile against — but it
carries zero live-state responsibility; that's entirely `desk.state`/`desk.events`,
called independently by each widget.

### `.desk_temp/widgets/mobile-bridge-monitor/`

A developer/debug monitor for a Desk-hosted WebSocket relay microservice: one
address field, Connect/Disconnect/"Send hello" buttons, a scrolling log capped at
100 lines. Real, persistent widget (not one-off), but squarely a dev tool: the
"Send hello" button exists explicitly "so the loop can be tested from the Desk
side alone... by running two instances of this widget side by side" (its own
comment). No visualization, no cross-instance sync of any value (each instance is
fully independent), no declarative pattern — plain imperative DOM wiring. One
good anti-silent-failure design note: deliberately no hardcoded default address,
"because the relay's port is now allocated fresh each run... a stale hardcoded
address would silently fail to connect instead of obviously prompting for the
real one."

### `.desk_temp/widgets/voice-brainstorm/`

A file-backed Markdown brainstorming-document editor (title → auto-derived path →
auto-load/auto-save). Built on a genuinely reusable base class,
`DocumentEditorBase<Doc>` (`.desk_temp/shared-components/document-editor-base/`):
subclasses declare `directory`/`extension`/`parse`/`serialize`/lifecycle hooks,
and the base owns path derivation, create-vs-load-never-clobber semantics,
last-open-document restoration, and save-on-every-edit. This is the clearest
"declarative contract instead of imperative glue" pattern in the `draw-with-desk`
widgets — proven across at least two independent widgets (this one, and the
`necro-4x` widgets it was extracted from), though it's a file-*lifecycle*
abstraction, not a UI/visualization one. Interaction model is a single textarea —
trivially "in sync" because there's only ever one live view of the body. No
visualization. One substantive platform-limitation note: the widget originally
drove in-page voice dictation, but Desk's `kind:"html"` host never wires up the
browser permission prompt a mic-access call needs, so it crashes/blanks instead
of cleanly rejecting — filed as platform feedback, and the UI now just tells the
user to use the OS's own dictation feature into the focused textarea instead.

---

## `necro-4x`

Three small promoted widgets (`HexMapViewer`, `LifeforceHeart`, `LifeforceControl`)
plus one much larger, still-un-promoted widget this project's history
specifically flagged as worth studying: **Domain Analysis**, an entity-tagging
tool whose schema lives inside the edited document itself. That last one is the
single richest principle-2 example found anywhere in this sweep.

### HexMapViewer

A pan/zoom viewer for a large hex grid with typed per-cell data layers
(`number`/`string`/`colorhsl`/`colorrgb`/`hecs`/`tagset`). The shipped demo data
populates only one label layer, explicitly "to prove the serialization format's
per-cell data renders in the right place" — not real content yet. Interaction
model: the canvas itself is directly draggable (pan) and wheel-zoomable, plus a
small HUD with discrete +/-5% buttons and a "Reset view" button — all acting on
the *same* camera state, not a separate shadow copy. Strong principle-2 alignment
for navigation (drag/wheel directly on the canvas, HUD buttons as a secondary
affordance on the same state) — but the actual layer *data* has no interaction at
all: no click-to-inspect-a-cell, no edit path, so the principle holds for
camera/viewport but not for the domain data the layers exist to carry. Only one
view of the map exists at any time, so there's no multi-view-sync question to
ask. DSL/declarative note: the layer/state interfaces are a deliberately
documented, reusable serialization schema (explicitly ported from a sister
project, `hexsheet`) with a runtime type-guard rather than ad hoc shape-checking —
but it's an internal data-interchange format, never exposed as something the user
edits as text.

### LifeforceHeart + LifeforceControl

A heart-shaped SVG gauge (`LifeforceHeart`) paired with a two-button remote
control (`LifeforceControl`) — and tracing the actual wiring (via a shared
`EventMessageChannel` wrapper over `desk.events`) shows this is **not** a
passive-gauge/active-control split in the usual sense: `LifeforceControl` holds
and displays no value at all — it only *publishes* `lifeforce-increase-requested`/
`-decrease-requested` events with a fixed amount; it has no gauge, bar, or number
of its own. `LifeforceHeart` is the sole holder and sole renderer of the
lifeforce value, and it funnels both its own on-widget `+0.1`/`-0.1` buttons
*and* incoming remote events through the same single mutation point
(`applyLifeforce`), which clamps, animates, persists, and re-publishes a
`lifeforce-changed` event for any other (not-yet-built) listener. So there is no
"two views of one value" scenario active in the current code — only because the
second widget deliberately carries no state/display of its own; if a third
widget wanted to *display* lifeforce (referenced via a `TODO` in the shared
module for a not-yet-built HUD), it would have to independently subscribe and
maintain its own copy, since there's no central store, just broadcast-and-apply —
a plausible future drift risk, not a demonstrated one. On principle 2: the
heart's fill is a passive, nicely-animated readout with no pointer handlers — not
draggable/clickable to set a value directly. The two buttons sit visually
*on top of* the heart graphic but are conventional buttons, not direct
manipulation of it. The widget's own comment admits this is provisional: the
buttons are explicitly "stand-ins... until there's a real delivery mechanism to
wire up to," not the intended production UI. `LifeforceControl` on its own is the
clearest example anywhere in this sweep of the opposite of principle 2 — pure
controls, no picture at all, by construction (a deliberate test harness).

### DomainAnalysisElement ("Domain Analysis") — the standout case study

**Location:** `necro-4x/custom_widget_src/domain-analysis/` (1827-line `.ts`,
**not promoted**, backing data at `necro-4x/domain-analysis/*.md`). Referenced
directly in this research's parent project's own design history
(`investigations/app_structure_dsl_design.md`) as "a real, independent instance of
... structured, evolving, in-document schema + a UI over it."

**What it's for.** Building an entity/relationship model of an arbitrary domain by
tagging free-text "statements" with category labels, persisted as one markdown
file per domain.

**The in-document schema.** A category used to be a fixed compile-time set; now
"new ones can be added at runtime (the '+' button next to Drop to Tag), so a
document carries its own ordered category list" (the widget's own comment). The
schema is written into the markdown itself as a literal `## Category Definitions`
table, parsed as authoritative and fully replacing compiled-in defaults when
present. A category's display color is *derived from its position* in this list,
not stored — so reordering is a real structural schema edit, not cosmetic. New
categories can be added via a form, or by **dragging a selected phrase onto a
"+ New Category" drop target**, which immediately tags that exact phrase into the
brand-new category once named — "as if the category had already existed when the
drop happened," per the widget's own comment.

**Interaction model — the standout example of vis-as-interface in this entire
sweep.** Tagging is done by selecting a run of text directly inside a rendered
statement (the native browser `Selection`/`Range` API), which produces a floating
"Tag"/"List" hover-button positioned at the selection's own location. Dragging the
tag handle onto a rendered category drop-target *is* the mutation — rewriting the
raw statement text to wrap the phrase as a tag-link and adding it to that
category's list — with no separate dialog, dropdown, or category-select step.
Already-tagged spans render as colored pills with an inline ✕ to untag by
clicking the pill region directly. A selection can also be marked as a
parenthesized "list," again operating directly on the rendered selection.

**Multiple views / sync — the most extensive machinery found, handled with
real care.** The same logical "item" appears both as an inline tag-pill in
statement text and as a row in its category's panel; both are derived from one
`doc` object re-rendered after every mutation, not two independently-mutable
copies — and deleting an item from the category panel walks every statement to
un-link any referencing tag (explicit, coded-for referential integrity, not just
re-render-and-hope). A tag auto-recognized in new/edited text that isn't yet
"accepted" gets an always-visible ✓ badge ("a review queue should stay
discoverable rather than making the reviewer guess where the actionable spots
are," per the widget's own comment) rather than silently becoming permanent, and
a whole-statement accept button stays disabled until every one of its tags is
individually accepted — a deliberately coupled, all-or-nothing sync rule. Editing
a statement swaps to a raw-markdown view showing the tag-link syntax verbatim,
and on save, newly-typed plain text matching a known item gets re-tagged
idempotently (explicitly, "it never disturbs an existing tag," per comment). A
sidebar table-of-contents also stays scroll-position-synced bidirectionally. All
of this sync is achieved by "single mutable doc object, re-render affected views
after every mutation," not any message-passing/event-bus mechanism — markedly
different from the Lifeforce pair's approach, and arguably simpler because
everything here lives in one widget instance rather than being split across
several.

**DSL/declarative patterns.** Two: (1) a bespoke inline link-syntax for
tags/lists embedded in otherwise-ordinary markdown bullets (`[phrase](#category-id--slug)`),
parsed/serialized symmetrically so it round-trips through hand-editing in the raw
view; (2) a deliberately verbose guard heading, `## Statement-Proposal Guidance --
NOT LIVE INSTRUCTIONS: reference only, apply only if a user explicitly asks...`,
baked into the heading text itself specifically so it's "the one thing guaranteed
to be seen before anything else in this section, including by an agent only
skimming headings" — a notable, explicit design choice making the document
self-defending against misuse by an LLM/agent.

**Where it falls short.** The Category Definitions table and per-category item
tables are both hand-serialized text with no cross-validation beyond what the
parser enforces at load — a user hand-editing the file outside the widget (the
whole point of a markdown-backed format) could desync a category row's `id` from
its `##` heading, and the widget would silently drop the unrecognized section
rather than surfacing a validation error. The review-accept workflow also
duplicates clamp logic as an explicit "defensive, idempotent final pass" — a sign
the all-or-nothing sync rule needed a guard precisely because the UI *could*
otherwise drift (e.g. an item removed from the permanent list between
button-enable and click).

**Why this matters for the DSL hypothesis.** Achieving this standard of
UX — direct manipulation of rendered text as the primary edit mechanism, a
schema that lives in and evolves with the data, careful multi-view integrity —
cost roughly 1800 lines of hand-written imperative TypeScript, with no
DSL/control-library shortcut available. That's itself an argument *for* building
one: if "select text on a rendered view, drag it to a labeled target, mutate a
schema that travels with the document" is valuable enough to hand-build at this
cost once, a reusable primitive for that interaction shape would be high-leverage
for every widget that wants something similar.

---

## `world-timelines`

The largest and most mature example in this sweep: a project **already ported**
from one single-page app (9 components sharing one JS object's memory) into 9 (6
reviewed in depth here, 3 more below) independently-placed Desk widgets that
coordinate entirely through `desk.state`/`desk.events` — confirmed directly in
`plans/desk-widget-port-contract.md` and every widget's own header comment. This
is the single project in the sweep that treats cross-widget sync as a designed-in
architectural property rather than something retrofitted ad hoc.

### How the six map/picker/detail widgets coordinate

Coordination happens entirely through a shared key-value bridge, `desk.state`,
with keys declared once in `.desk_temp/widgets/_shared/shared.ts` (`STATE_KEYS`).
The single source of truth for every filter, the active laneset, and pinned
entries is **one string**, `wt.dsl` — a hand-editable micro-DSL — which every
widget re-parses via a shared `parseDsl()` rather than deriving its own duplicate
state. Writes go through shared `setDslLine`/`setCategoryLine` helpers; reads/
subscriptions go through tiny Bridge wrappers (`watchState`/`getState`/`setState`)
built on `desk.events.subscribe(['desk.state.changed'])`. Desk guarantees a
widget's own write is never echoed back to it, so no self-authorship guards are
needed anywhere, confirmed in several widgets' own comments. Selection of an
entry vs. a lane is kept mutually exclusive by convention at every call site, not
by a coordinator. A separate widget, `query-engine`, is the only writer of
derived/output keys (`wt.queryResults`, `wt.eras`, `wt.lanesets`,
`wt.boundaryOptions`) the six widgets below consume read-only.

### World Map

A dark, full-bleed canvas map plotting historical events (points/polygons/paths/
circles), colored by category, with a geographic box-filter and lane-boundary
overlay. Everything happens directly on the canvas: wheel zooms, drag-to-pan,
left-click-drag draws a selection box that becomes a lat/lng filter (with
auto-snap to lat-only/lng-only bands), plain click selects an entry, plus a small
"mini-map" inset with its own click-drag-to-fit and Full/Fit buttons. A box-drag
writes `wt.dsl`'s `filter lat:`/`filter lng:` lines directly; a marker click
writes `wt.selectedEntryId` *and* immediately does a local highlight too, with
the widget's own comment explicitly framing this as "so this click feels instant
rather than waiting on the state round trip" — a deliberate optimistic-UI
concession to perceived latency. One explicitly flagged sync gap: a click here
can't convey *which waypoint along a path* was clicked back to the timeline
widget, because the selected-entry state is scalar — "No waypoint info available
when the selection originates elsewhere," per the widget's own comment.
Principle 2: largely realized (box-select-to-filter and click-to-select both
happen on the live map), with the one exception being a small floating "×"
button to clear the geo-box rather than a map gesture.

### Timeline

A horizontal canvas timeline: a time axis, collapsible per-region "lanes" with
packed entry markers and era bands. Click a chevron to collapse/expand a lane;
click the rest of a lane title to select it; drag inside a lane to select a year
range; drag outside it to pan; wheel zooms time; shift+wheel scrolls the lane
stack; click a marker selects an entry; a "fit" button snaps to selection (or
turns the current view into one). Six separate state subscriptions keep it
current with eras, laneset, query results, and both selection keys; pan/zoom
writes a debounced *viewport* key distinct from an explicit drag-selected *year
filter* line in `wt.dsl` — the widget's own comment explains this distinction is
deliberate, not accidental duplication: `query-engine` prefers the explicit
filter when present and falls back to the viewport otherwise. **The clearest,
most self-aware instance in the whole sweep of principle 1 silently degrading
under a real state-key model**: the original single-page version forwarded the
nearest-waypoint-to-a-click so world-map could highlight that exact point; the
ported widget drops this because there's no state key for "also highlight this
specific waypoint" — and says so directly in its own comment rather than quietly
losing the feature. Principle 2: almost entirely realized — panning, zooming,
lane collapse, and selection are all done by interacting directly with the
rendered timeline; the only separate control is the fit button.

### Entry Detail

A side panel showing full detail for whichever entry/lane is currently selected,
with a pin-toggle button. Pure read + one narrow write — but its sync story is
the most interesting of the six: it subscribes to `wt.dsl` purely to keep its own
pin button's checked state correct, because "the pin set can change from
elsewhere (e.g. query-engine's 'pin all results'/'unpin all' buttons) while this
same entry is open — keep the pin button's own visual state current rather than
only updating it from this widget's own togglePin()," per its own comment. A
textbook, explicitly-reasoned instance of principle 1: a value (pinned-ness)
mutable from more than one place, kept in sync via a shared watch rather than
assuming only local writes matter. No visualization — this widget is deliberately
the "separate controls" half of Tufte's dichotomy, paired with world-map/timeline
as the direct-manipulation surfaces.

### Boundary Picker, Laneset Picker, Category Picker

Three small popup/chip controls, each with the same pattern: **no state key of
its own** for its selection — each derives its current selection fresh from
`wt.dsl` on every change (including ones it didn't cause) and never writes back
except through the shared DSL-line helpers. Boundary Picker's own comment is
explicit about why its passive re-sync never writes back: "that would create a
redundant `desk.state.set` for every external DSL edit" — a reasoned guard
against write-amplification/feedback loops. Laneset Picker's own comment lays out
the cleanest statement in the whole sweep of "single value, multiple simultaneous
views, kept honest by always re-deriving from one source rather than caching,"
explicitly anticipating a *third* actor (the query-editor widget, covered below)
hand-editing the same DSL text directly. Category Picker explicitly flags a
dropped feature (a "Global Eras" toggle chip, now owned by a different widget
entirely) as "scope cut, flagged rather than silent." None of the three renders
any data as a picture — all are on the "separate form controls" side of
principle 2; the effect of their filters is visible only on world-map/timeline,
which they never render themselves.

### Settings Menu

A gear-icon popup with two unrelated settings (data source, a "show global eras"
toggle), both written straight to `desk.state` with **no** DSL representation at
all — the one deliberate exception in this project to routing everything through
`wt.dsl`. Its own comment states it doesn't subscribe to watch either key,
"because neither value is ever written by any other widget" — sidestepping
principle 1 by construction (single writer, nothing to drift against) rather than
solving the general case. No visualization.

### Query Engine

The one real "coordinator": owns a Web Worker that executes the DSL query, loads
reference data on connect, and exposes "Pin all results"/"Unpin all" buttons.
Visible UI is a status line and two buttons; the real work (re-querying on any
relevant state change, 150ms debounced) is invisible. The "pinned ids" concept is
mutated from two places (direct typing of a `pin:` line in query-editor, and
these buttons) but both funnel through the same textual representation via the
same shared line-patch helper, so there's nothing to drift *between those two
paths* — but there's a real principle-1 shortfall anyway: **this widget has no
visible representation of which ids are currently pinned**, so clicking "Unpin
all" gives no on-screen confirmation of what just changed short of opening the
editor and reading the (folded, truncated) `pin:` line there. Notable
documented risk: the DSL grammar's parser is **duplicated verbatim** in two
independently-maintained places — the main-thread TypeScript version, and a
hand-written plain-JS-string copy baked into the Worker's source (because a
Blob-URL Worker can't see main-thread globals) — a drift risk the project
accepted knowingly rather than solved.

### Query Editor — deep dive

The DSL raw-text editor: one `<textarea>` bound to `wt.dsl`, a non-editable
"folded" at-rest rendering, and a static clickable example-lines panel. This
project's own design history (`investigations/app_structure_dsl_design.md`)
describes this file as having a "field↔DSL-text-line bidirectional sync"
pattern worth generalizing — reading the actual code shows that description
needs correcting:

- **What triggers re-sync:** every keystroke fires a 150ms-debounced push to
  shared state (not gated on blur or a save button); `blur` triggers an
  *immediate*, display-only switch to the folded view; clicking a canned hint
  line writes immediately, bypassing the debounce; an *external* `wt.dsl` change
  from another widget is applied immediately too, but only when the textarea
  isn't currently focused — a guard against clobbering in-progress typing, not
  against self-echo (Desk's events already guarantee no self-echo, so that guard
  isn't needed here).
- **Single source of truth, confirmed**: `this.textarea.value`/`wt.dsl` is the
  only authoritative value; the folded view rebuilds its DOM from scratch on
  every call rather than caching a parsed model, so there's nothing to drift. The
  only state the folded view owns ("which rows are currently un-truncated") is
  explicitly transient UI-only state, cleared on every text change.
- **The "structured UI" is not form fields, and not visualization-like either —
  this is the key correction to the earlier characterization.** There are no
  form fields anywhere in this file: no category checkboxes, no range inputs, no
  dropdowns. What exists besides the raw textarea is (1) a folded view operating
  on raw *lines*, not parsed semantics — it never calls `parseDsl`, so a blank
  line, a comment, and a real filter line all render as identical opaque text
  rows; and (2) a static hints panel of six canned example lines, appended on
  click, write-only with no read side. Neither element visualizes the underlying
  historical-event *data*. The genuine "value present → emit line; absent →
  apply default" primitive the design history describes does exist in this
  project, but it's `_shared/shared.ts`'s generic `setDslLine`/`setCategoryLine`
  helpers — demonstrated by exactly one call site (query-engine's pin/unpin
  buttons), and even that example is unidirectional (write-only, no visible
  field reflecting the result, as noted above).
- **Could this be generalized?** The `setDslLine(dsl, pattern, newLine)` primitive
  already is grammar-agnostic — given any regex and replacement it finds/replaces/
  inserts/deletes-on-empty against a newline blob, reusable verbatim for a
  different DSL. Everything else is tightly coupled to this one grammar: per-field
  regexes/templates are hand-written at each call site, `parseDsl` is a monolithic
  hand-rolled parser with no reusable grammar schema, and the Worker's hand-synced
  duplicate copy would need either a build step compiling one canonical grammar
  into both forms, or dropping the Blob-Worker approach, to actually generalize.

**Revised bottom line on this file**: treat the generic `setDslLine` primitive —
not this file's folding mechanism — as the real reusable building block, and note
it still needs a declarative per-field schema layered on top (pattern +
serializer + deserializer + default, as a data structure rather than scattered
hand-written functions) before it stops requiring bespoke glue per field.

### `_shared/shared.ts`

Not a widget — a global-scope file concatenated ahead of every widget's own
source. Supplies: a single declarative registry of state-key names (`STATE_KEYS`,
"one constant per key, shared so a typo in one widget's own file doesn't silently
create a second, disconnected key" — itself a tiny DSL-adjacent pattern); the
shared DSL grammar parser; the `setDslLine`/`setCategoryLine` line-sync
primitives; and three Bridge convenience wrappers every widget calls rather than
touching `window.desk` directly. Documents the load-bearing "`desk.state.changed`
never echoes a widget's own write back to it" platform guarantee that underlies
every sync story in this project.

### Mermaid search

Searched the entire `world-timelines` repository — working tree, all branches,
full commit history/diffs — for "mermaid" and "diagram." **Zero matches
anywhere.** If the "little bit of work on interactive mermaid diagrams" exists,
it is not in this project.

---

## Cross-cutting synthesis

See the main investigation doc (`dsl-for-agent-widgets.md`) for how these
findings feed the DSL hypothesis and the two UX principles directly. In short:
principle 1 (sync) is solved well exactly when a single textual source of truth
exists and every view is *derived fresh* from it rather than cached (`wt.dsl`
project-wide; `raycaster-scene`'s text/fields pair; `query-editor`'s folded view;
Domain Analysis's single mutable `doc`), and solved badly or not at all whenever
two independent code paths can mutate the same logical value with no shared
primitive forcing them through one place (`DeskConsole`/`DirectoryTreeView`'s
hand-rolled replay-and-retry, duplicated almost verbatim across two files;
`raycaster-camera`/`raycaster-formula`'s missing events capability).
Principle 2 (vis-as-interface) is rare, and expensive when done well (Domain
Analysis's ~1800 lines; world-map/timeline's real canvas hit-testing), and the
dominant failure mode is not "no visualization" but "visualization plus separate
bolted-on controls that happen to share a value" (the raycaster family almost
entirely; the Lifeforce pair; every `world-timelines` picker widget).