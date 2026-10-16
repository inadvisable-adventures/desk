# Case study: the DSLs inside `hexsheet`

Part of the `investigations/ux-dsl/` sweep (see `dsl-for-agent-widgets.md` for
the hypothesis and the two UX principles this is read against:
(1) **sync** -- multiple simultaneous views/controls over one value must stay
in sync, ideally by re-deriving one view fresh from a single source of truth;
(2) **vis-as-interface** -- the visualization of data should itself be, or be
a major part of, the interface to manipulating it). `hexsheet` ("a
spreadsheet for hex grids," `/Users/mphair/claude-projects/hexsheet/`) is
**not** a Desk project and has never been imported into one -- a plain
TypeScript/web-component app, examined here purely as a source of real,
working DSL examples, both user-facing and developer-facing. It turned out to
be the single richest source of DSL case studies found anywhere in this whole
investigation: **eight distinct DSLs or DSL-adjacent mechanisms** in one
small app, two of them genuinely novel data points (a real dependency-graph
computation engine, and an AST reused for both evaluation and visualization)
that the peer-Desk-project sweep (`widget-case-studies.md`) didn't surface.

Research performed by two parallel subagents reading the full source; findings
below are lightly reformatted, not rewritten, with file:line citations
preserved throughout so every claim is checkable.

## 1. Sheet-layout DSL (`sheet-dsl.ts` + `sheet-dsl-editor.ts`)

**What it's for.** A textual S-expression serialization of an entire
hexsheet "sheet": every item (`dice-pool`, `dice-map`, `hex-grid`,
`layered-grid`, `hex-flower`, `signal-logger`, `signal-chart`,
`subsheet-sheet`, ...), its component-specific state, and the signal
`connect`ions wiring items together. User-facing and user-editable: a human
opens a "Sheet DSL" button, edits the generated text, and clicks Apply to
rebuild the whole sheet from it -- stated directly in the design doc,
`plans/sheet-dsl.md:5-19`: "bi-directional... clicking Apply parses the DSL
and reloads the sheet from scratch."

**The grammar.** A real hand-written tokenizer + recursive-descent parser +
pretty-printer, not JSON-with-a-hat: `tokenize()` (`sheet-dsl.ts:24-60`,
parens, `;`-comments, quoted strings with escapes, numeric coercion),
`parseAt()`/`parseAll()` (lines 64-90), `emitAtom()`/`emitExpr()` (lines
94-120), plus a per-component serializer/deserializer pair for every item
type (e.g. `serializeDicePool`/`deserializeDicePool`, lines 162-168/403-409;
`serializeLayeredGrid`/`deserializeLayeredGrid`, lines 260-284/518-559;
a recursive case for nested subsheets, lines 323-363). Real accepted syntax
(`plans/sheet-dsl.md:25-87`):

```lisp
(sheet
  (item "uuid" "component-type" ; component state clauses
  )
  (connect "from-uuid" "SignalId" "to-uuid" "FilterId")
)
```
```lisp
(layer "number" "HP" (visible true) (formula "prev + 1")
  (cell "0,0,0" 5) (cell "0,0,1" 8))
```

**Sync pattern.** Deliberately *not* a two-way-bound structured view --
`sheet-dsl-editor.ts` (56 lines) is a single `<textarea>` with Apply/Close
buttons, no separate fields panel. Instead, the two things that must stay in
sync are *the live rendered sheet* and *the DSL text*, via a strict one-shot
re-derivation: opening the editor builds a fresh DSL string straight from the
live sheet state (`toggleDSLEditor()`, `hex-sheet.ts:145-164`); Apply does
**not** diff/patch -- it tears down every item and rebuilds the whole sheet
from the parsed result (`loadSheetFromDSL()`, `hex-sheet.ts:167-179ff`). This
is a strong instance of "single source of truth, re-derive the other view
fresh" -- there is no window where the live sheet and an open editor can
drift, because the editor is modal and Apply replaces the sheet atomically
rather than reconciling it. The design doc confirms this was a deliberate
simplicity trade-off (`plans/sheet-dsl.md:18`), not an oversight -- one that
also happens to make the sync question trivially safe, since there's no
reconciliation logic to get wrong in the first place.

**Vis-as-interface.** No -- text in, text out, full rebuild; no diagram at
this layer (the *content* the DSL describes has its own direct-manipulation
surfaces elsewhere, see below, but that's a property of those widgets, not
of the Sheet DSL itself).

## 2. Formula / cell-expression language (`formula-eval.ts` + `formula-types.ts` + `formula-editor.ts`)

**What it's for.** The one genuinely end-user-typed, non-trivial expression
language in the app: a Lisp-like notation typed directly into a grid layer's
formula box to compute a cell's value from other cells (same layer, other
layers, prior iterations), colors, hex coordinates, icons, and dice rolls.
Stored as raw text (`layer.config.formula`) and re-parsed/re-evaluated on
every render -- never pre-compiled into structured JSON.

**The grammar.** A real tokenizer + recursive-descent parser + typed AST +
separate evaluator, all in `formula-eval.ts`: `tokenize()` (lines 26-129:
parens/brackets, `#RRGGBB` color literals, strings, signed relative
-coordinate tokens like `+1`/`-1`, embedded `NdM` dice literals, bare idents);
`AstNode` union (lines 133-140); recursive-descent `parseTokens`/`parseAtom`
(lines 146-280), with real grammar quirks baked in on purpose: a bare `(num
num num [num])` is sugar for a hex-coordinate literal, disambiguated from a
function call purely by whether the first token after `(` is a number (lines
171-189); a fixed `BUILTINS` set (line 144) rejects a bare builtin name in
argument position unless parenthesized, an explicit disambiguation choice;
"outerless" top-level forms make the leading paren optional (`+ 1 2` and
`(+ 1 2)` both work, lines 256-272), a documented ergonomic convenience, not
an accident. The evaluator `evalNode` (lines 466-882) implements `ref`/`prev`
(cross-cell and prior-iteration lookups), `hsl`/`rgb`/`hex` constructors,
`blend`, `heatmap`, `roll`, tag predicates, `exref` (reads an externally
-injected "implicit move direction," letting a token's formula react to a
connected dice-map), and structured arithmetic with type-specific clamping.
Real accepted strings (`src/test/formula-eval.test.ts`, `plans/sheet-dsl.md:58,75`):
`42`, `(+ 1 2)`, `+ 1 2`, `ref +0 -1 +2`, `prev + 1`, `exref`,
`(hsl (* 120 (has-tag (ref 0 0 0 "tags") "forest")) 80 40)`.

**A second, independent consumer of the same AST -- real prior art for "one
parse, multiple derived views."** `extractRefs()`/`resolveRef()`
(`formula-eval.ts:306-384`) walk the AST to statically find every `ref`
target *without evaluating* -- used by two different downstream consumers:
the dependency-graph engine (§3) and a live "debug arrows" overlay (below).
This is a clean, already-proven instance of exactly the shape
`grammar-ast-live-pane.md` is reaching for: one real grammar/AST, multiple
independent things built on top of it, no duplicated parsing logic between
them.

**Sync pattern.** The only "view" of the formula itself is the one text box,
decorated three ways from the same underlying string on every keystroke, none
independently cached: a live syntax-highlight overlay re-tokenized from
scratch each time (`highlightFormula()`, `formula-editor.ts:12-106`), a
matched-paren indicator recomputed fresh from the current cursor position and
text on every event (`findMatchedParens()`, lines 108-127, called from
`input`/`selectionchange` at lines 166-173/204-211), and a suggestions/doc
popup likewise recomputed from scratch per keystroke (lines 219-269). One
level up, `layered-grid.ts`'s `handleFormulaInput()` stores the raw string as
the single source of truth, re-parses it just to surface an inline syntax
error, then fully rebuilds the SVG grid from scratch (lines 2025-2053) --
the whole rendered grid is re-derived on every keystroke, not incrementally
patched. Clean "re-derive, don't duplicate," at the grid level.

**Vis-as-interface -- partial, and worth calling out as a shortfall.** The
grid is read-only with respect to formula-computed cells (you cannot drag a
derived value to change it, since it's derived -- expected). What *does*
close part of the loop: hovering a cell in debug mode draws live SVG arrows
to every cell its formula references, reusing the exact same
`extractRefs`/`resolveRef` functions the dependency graph uses
(`buildDebugOverlaySvg`, `layered-grid.ts:1265-1306`) -- the diagram
visualizes the formula's own parsed structure, but doesn't let you
*manipulate* the formula by interacting with the diagram; authorship stays
entirely in the text box.

**A concretely relevant design precedent for the grammar/AST engine's own
future scope**: `plans/formula-editor-component.md:56-66` explicitly states
the syntax highlighter is a **second, independently hand-rolled, lightweight**
tokenizer, deliberately not reusing `formula-eval.ts`'s real one, and explains
why (textarea+overlay over `contenteditable`, to avoid cursor-jump bugs and
third-party dependencies, lines 60-66/131). This is a real, named instance of
the exact "duplicated grammar" risk the grammar/AST investigation is
concerned about -- here the duplication is scoped to cosmetic highlighting
only (a real bug in it could mis-color text, not silently diverge program
behavior, since real parsing stays routed through the one true parser), but
it's a direct, concrete illustration of the payoff a generated parser with
real AST-plus-positions would offer: syntax highlighting could be *derived*
from walking the one real AST and coloring by node type, instead of needing
a second, hand-maintained, drift-prone tokenizer at all.

## 3. The computation graph (`computation-engine.ts`) -- the cleanest "always rebuild fresh" example found in this entire investigation

**What keeps multiple views of a value honest.** `buildComputeGraph`
(`computation-engine.ts:132-311`) is a real, generic, pull-based dependency
-graph engine, not special-cased per call site. `ComputeNode` (lines 36-43)
tracks a status (`uncomputed`/`pending`/`computed`/`cycle-error`/
`pending-blocked`); dependency edges are built once per call by statically
extracting every formula's `ref`/`prev` targets (reusing §2's
`extractRefs`/`resolveRef`); evaluation is a stack-based, cycle-detecting
topological walk (lines 256-308) -- a node already `pending` when revisited
is a real cycle, flagged `cycle-error`, with everything still `pending`
marked `pending-blocked` (lines 274-288), not just "trust the author not to
write a cycle." Within one call, each node computes at most once (line 262)
-- memoization scoped to a single invocation, not a persistent cache.

**This is strictly pull, rebuild-from-scratch, every time** --
`buildComputeGraph` is called fresh inside `buildSvg()`, the debug overlay,
`bakeLayer`, the readonly cell-inspector popup, and the dependency-graph
-visualization panel (five call sites, `layered-grid.ts:1322` and others).
Every one of those visible renderings is a fresh projection of the same raw
state (per-layer cell storage plus formula strings); nothing caches an
independent "computed value" that a second view could read stale. This is,
across the entire investigation sweep so far (Desk peer projects and this
one), **the cleanest, most load-bearing embodiment of UX principle 1** found
anywhere -- stronger than `world-timelines`'s `wt.dsl` (which re-derives
*display* state from one text blob, but has no real dependency graph), because
this one actually detects cycles and tracks per-node computation status, not
just "re-render everything and hope."

**The one deliberate, bounded exception**: `prev()` reads from an explicit
snapshot history (`this.snapshots`, pushed in `handleStep()`, lines
2395-2408) to support multi-step iteration -- a conscious exception to
"always derive fresh," capped at 50 snapshots and explicitly invalidated
whenever the grid shape changes (four call sites: `expandGridToInclude`,
`removeCell`, etc.). Worth noting as a real example of *when* caching a prior
value is legitimate (representing genuine history, like "the previous
generation of a cellular automaton," not a convenience cache of a value that
could just be recomputed) versus when it's a sync hazard (everything else in
this engine deliberately avoids it).

**Debugging the dependency structure is itself visualized**, reinforcing
principle 2 in a diagnostic (not editing) context:
`buildGraphVizPanel`/`buildGraphVizTable` (`layered-grid.ts:1135-1254`) render
the whole node/edge graph as an SVG diagram colored by node status, reusing
the exact same `buildComputeGraph` call the grid itself uses -- the design
doc notes explicitly "there is no additional state to maintain"
(`plans/computation-graph-viz.md:89-90`). Read-only/diagnostic, not an editing
surface -- it visualizes the hidden structure but stops short of being an
*interface* to it (no drag-to-rewire-dependencies).

## 4. Dice notation (`dice-utils.ts`, consumed by `dice-pool.ts`)

**What it's for.** A compact textual notation for a multiset of polyhedral
dice (`"2d6+1d4"`), typed into a dice-pool's notation field or embedded
inline inside the formula grammar itself (`NdM` is a first-class token kind
in `formula-eval.ts`'s own tokenizer, lines 76-86 -- the two DSLs share
surface syntax at exactly this one point).

**The grammar.** Small, real, regex-based: `parseDiceNotation()`
(`dice-utils.ts:4-17`) splits on `+`, matches each term against
`/^(\d+)d(\d+)$/i`, validates the side count against a fixed polyhedral set
(`[2,4,6,8,10,12,20]`), expands into a flat `DieSides[]` array, and returns
`null` on any malformed term -- a real accept/reject grammar, not a
passthrough. `formatDiceNotation()` (lines 38-46) is the inverse.

**Sync pattern -- close to ideal.** `dice-pool.ts` keeps `this.dice:
DieSides[]` as the sole source of truth and treats the notation text as a
purely derived, disposable view, never an independent cache: the notation
`<input>` is refilled from `this.dice` via `formatDiceNotation` on every
view refresh and after every programmatic mutation (adding/removing a die);
typing in that input re-parses immediately -- success overwrites `this.dice`
and refreshes the pool, failure leaves `this.dice` untouched and just flags
the input invalid, so a bad parse can never corrupt the authoritative array
(lines 233-258). Crucially, **persisted state stores `dice: DieSides[]`
directly, never the notation string** -- confirmed by a real fixture
(`hex-flower-2.json`: `"serializedData":"{\"dice\":[6,6],\"rollResults\":[]}"`).
The notation string never even round-trips through save/load; it's a
transient, always-recomputed convenience layered on top of the real state.

**Vis-as-interface -- yes, genuinely, in a limited scope.** Each rendered
die icon in the pool is directly clickable to remove it, and clicking a
palette icon adds one -- both paths go through the exact same `this.dice` →
refresh cycle as typing text, so the rendered dice are a real, bidirectional
part of the interface, not a passive picture next to "the real" text
control.

## 5. The "signal" mechanism (`signal.types.ts`, `signal-container.ts`) -- a pub/sub bus, and a real drift-risk example

**What it's for / who authors it.** Entirely non-user-facing: the wiring
protocol between widgets (dice-pool → dice-map → layered-grid, or any widget
→ `signal-logger`/`signal-chart`), authored by developers as TypeScript
custom-event contracts, never typed by an end user as text. The declarative
part an end user (or a hand-authored composition file, see §7) *does*
interact with is the `connections` table -- a real example from
`hex-flower-2.json:24-37`:
```json
"connections": [
  { "fromSheetItemId": "hf2-dice-pool", "fromSignalId": "DicePoolRolled",
    "toSheetItemId": "hf2-dice-map", "toSignalIdFilter": "DicePoolRolled" }
]
```

**Push-based, one-shot, no notion of "value" at all** -- `SignalContainer`
(`signal-container.ts:19-83`) routes a message to matching receivers per the
declarative `connections` table (`routeMessage`, lines 63-80; broadcasts to
all if `connections` is empty, "backward compat"). There's no recomputation,
no memoization, no dependency tracking -- this is choreography, not state.

**The real drift risk, worth citing as a direct instance of the pattern this
whole investigation keeps finding**: the actual message payload shape
(`{direction: number | 'stay'}`) is duplicated as an inline, unvalidated type
assertion in at least two independent files --
`signal-chart.ts:8-10` and the inline destructure in
`layered-grid.ts:1071-1075` -- with **no shared schema and no runtime
validation anywhere**. If a sender's payload shape ever drifted, nothing
would catch it generically; each receiver would just silently mis-parse.
This is the same failure shape already found in Desk peer projects
(`file-tree`'s `DeskConsole`/`DirectoryTreeView` hand-rolling the same sync
logic twice with no shared primitive; `raycaster-camera`/`-formula` missing
the events capability entirely) -- confirming it's a general pattern, not a
one-off quirk of any single codebase: **whenever two independent consumers
agree on a shape only by convention, with no shared declaration enforcing
it, that shape eventually drifts, and nothing notices until it breaks.**

**Vis-as-interface.** `signal-logger`/`signal-chart` are passive pictures
next to essentially no controls (a text log; a bar chart with only a "Clear"
button) -- clean counterexamples: they display signal traffic but are not
themselves an interface to anything.

## 6. Hex-flower movement / direction-map notation -- structured, UI-mediated, and duplicated across two independent interpreters

**What it's for.** The roll→direction mapping a hex-flower (or a standalone
`dice-map`) uses to move a token, authored by end users through a `<select>`
and an embedded `<hex-direction-map>` widget rather than typed text. Real
serialized example (`hex-flower-2.json`):
```json
"mapping": {"2":5,"3":0,"4":0,"5":1,"6":1,"7":"stay","8":2,"9":2,"10":3,"11":3,"12":4}
```

**A second, independent drift-risk instance.** `HexFlower.doStep()`
(`hex-flower.ts:673-717`) looks up `directionMap[total]` and applies
`boundaryRule` with its own inline bounce/wrap logic
(`computeWrapTarget`, lines 744-753). Separately, `layered-grid.ts`'s token
-movement path (`resolveMovementTarget`, lines 1052-1068) re-implements its
*own* bounce/wrap logic, reading a *different* representation entirely (a
`token-movement-rules` formula layer evaluated via `getMovementRule`, lines
1023-1039) -- rather than sharing boundary-rule code with `hex-flower.ts` at
all. So "boundary rule" as a concept is duplicated across two unrelated
implementations with no shared vocabulary enforcing agreement between
them -- the same drift-risk shape as §5, found independently in a completely
different part of the same codebase.

**Vis-as-interface -- strong for navigation, absent for the mapping itself.**
`HexFlower`'s SVG is a genuine direct-manipulation surface: ghost hexes are
clickable to extend the flower, a hex click selects/tags/sets-as-starting,
and the current-position ring is always rebuilt fresh from live state, never
a cached DOM node that could desync (`partialRender`, lines 316-333). But the
roll→direction mapping itself is edited through an ordinary form widget in a
separate controls panel, not by interacting with the hex diagram -- a partial
shortfall against principle 2, structurally identical to the raycaster
family's split between "the rendered view is interactive for selection" and
"the actual parameters are text/number fields with no graphical alternative"
(`widget-case-studies.md`).

## 7. Layer-type schema (`layer-types.ts`) -- a clean non-user-facing developer DSL

**What it's for.** A closed, 9-variant TypeScript union (`LayerType`,
`layer-types.ts:3`) that generic machinery dispatches on consistently,
rather than ad hoc per-call-site branching. This is the cleanest instance in
this app of the investigation's "developer-facing DSL reduces boilerplate"
half -- not something an end user ever types, but a small declared
vocabulary that pays for itself by having exactly one canonical interpreter
per concern, not N hand-copied ones: one switch each for coercing a formula
result to the right cell type (`coerceForLayer`,
`computation-engine.ts:58-128`), rendering a cell (`cellDataSvg`,
`layered-grid.ts:301-375`), converting between layer types when a user
changes a layer's type (`convertLayer`, lines 511-689, with a real
"Clear vs Convert" confirmation dialog), and (de)serialization (lines
842-981). Adding a tenth layer type means touching these ~5 switches, not
auditing every place a layer is used anywhere in the codebase.

**Design note.** `plans/extract-computation-engine.md:59-64` records the
deliberate decision to pull this schema into its own dependency-free file
specifically to avoid a circular dependency between the UI module and the
computation engine -- i.e. the vocabulary was kept standalone on purpose so
multiple independent modules could consume it without coupling to each
other.

## 8. Icon-set definition format -- hybrid developer/end-user, with an embedded raw-SVG micro-DSL

**Who authors it.** Both: `BUILTIN_ICON_SETS` (`icon-sets.ts:5-32`) is
hand-written TypeScript data, but end users author their own sets live via
`icon-set-editor.ts` -- including typing **raw SVG markup directly into a
textarea** (`.ise-icon-svg-input`, saved verbatim in `saveIconEdit()`, lines
241-252), with a live preview (`updateIconPreview`, lines 189-192). This is a
small, genuine instance of vis-as-interface for a micro-DSL that isn't even
domain-specific to hexsheet (plain SVG) -- the preview *is* the validator;
there's no separate "compile" step, matching the broader investigation's
"the rendering is the feedback loop" theme even at this tiny scale.

**Cross-wired into the user-facing formula language**, not an island: icons
are referenced from formulas via a `[setname idx]`/`["name"]` bracket literal
(`formula-eval.ts:216-247`), and resolved uniformly for every consumer
(formula evaluator, cell renderer, cell-editor dropdown) via one `findIconSet`
/`resolveIcon` pair (`icon-sets.ts:42-62`) -- generic interpretation, not
special-cased per call site, the same payoff pattern as §7.

**Vis-as-interface, a second instance**: the SVG-import grid-slicer
(`buildGridOverlay`/`updateImportPreview`, `icon-set-editor.ts:361-411`) draws
a live grid overlay directly on the user's uploaded SVG, updating in real
time as row/col/hex-size inputs change -- the overlay *is* the direct
-manipulation surface for deciding how the SVG gets sliced into icons.

## 9. Subsheet composition format (`hex-flower-2.json`'s own top-level shape) -- the strongest "pure declarative composition, zero new code" example in this whole investigation

**What it is.** `hex-flower-2.json` -- explicitly built, per its own design
doc, "without modifying any code" (`plans/hex-flower-2.md:1-33`) -- has four
top-level declarative sections: `items` (widget instances), `connections`
(the §5 signal-routing table), `layout` (a recursive tree of
`side-by-side`/`vflex` containers and leaf `item` references -- itself a tiny
generic layout DSL interpreted uniformly rather than hand-laid-out per
sheet), and `exposedSenders`/`exposedReceivers` (empty here, implying a
mechanism for a subsheet to expose its internal signals outward, not explored
further in the files read). Composing a dice-pool, a dice-map, and a
layered-grid into a working hex-flower clone required **zero new imperative
code**, only this one declarative file.

**Why this matters most for the parent investigation's hypothesis**: this is
the single clearest real-world proof, found anywhere in this sweep, that a
genuinely useful interactive tool can be assembled purely by declaring data
over existing primitives, with no new hand-written glue at all -- exactly
the aspiration `dsl-for-agent-widgets.md` and `grammar-ast-live-pane.md` are
reaching for, already demonstrated, just not yet in Desk itself.

## Non-DSL counterexample, checked specifically: `dice-map.ts`

Has **no textual grammar at all** -- `DiceMapState.mapping` is a plain
`Record<number, number | 'stay'>`, mutated entirely through property/event
binding with a child `<hex-direction-map>` component (push via property
assignment, pull back via a `mapping-changed` custom event, lines 83-99), no
parse/serialize-to-text step anywhere in this file (it only becomes S
-expression text one layer up, inside the Sheet DSL's own
`serializeDiceMap`, §1). A clean, uncomplicated vis-as-interface example
precisely *because* there's no competing textual representation to keep in
sync -- the diagram simply *is* the interface, with nothing else to drift
against.

## Synthesis

- **One small app, eight distinct DSLs/DSL-adjacent mechanisms** -- a strong
  validating data point on its own: even a modest interactive tool naturally
  accumulates many small declared vocabularies, not one. Worth remembering
  when scoping what a future Desk-side DSL-authoring effort needs to
  support -- it's unlikely to be "one DSL fits all," more likely several
  small, purpose-fit ones cooperating, the same shape found here.
- **The computation graph (§3) is the strongest real-world model found
  anywhere in this investigation for UX principle 1** -- a genuine,
  cycle-detecting, pull-based dependency graph, rebuilt fresh on every
  render from one source of truth, with a narrow, explicit, invalidated
  -on-structural-change exception for legitimate history (`prev()`). Any
  future Desk-side sync primitive should be measured against this, not just
  against `wt.dsl`'s simpler "re-parse a text blob" pattern.
  "Which views get rebuilt" that engine's debug-overlay/graph-viz panels (§2,
  §3) reuse without any extra state is a second, directly actionable
  precedent: a real AST plus a real dependency graph, once built, pays for a
  diagnostic visualization almost for free.
- **A real, proven "one parse, multiple derived consumers" example (§2's
  `extractRefs`/`resolveRef`, shared between evaluation and the debug-arrow
  overlay) reinforces `grammar-ast-live-pane.md`'s core thesis** with working
  code, not just argument -- and the formula editor's own deliberate
  second, independent highlighting tokenizer (§2) is a concrete, named
  illustration of exactly the kind of duplication a real grammar/AST engine
  (with node-type information available for free) would let a future Desk
  widget avoid.
- **Two independent drift-risk examples (the signal payload shape in §5; the
  boundary-rule logic in §6), found in one project**, reconfirm -- now across
  three independent codebases total (`hexsheet`, `file-tree`, the raycaster
  family) -- that the recurring failure mode throughout this entire
  investigation is not "nobody wrote a shared schema," it's "two consumers
  agreed on a shape informally, and nothing enforces that agreement staying
  true." Any future shared-state/schema primitive this investigation
  produces should treat *enforced* agreement (a declared, checked shape) as
  the actual goal, not just *documented* agreement.
- **The subsheet composition format (§9) is the aspirational benchmark**:
  real end-user value assembled from pure declarative data with zero new
  code. If a future Desk-side DSL effort can get anywhere close to this for
  a comparable class of tool, that is a strong, concrete sign it's working.

## Related

`dsl-for-agent-widgets.md` (the hypothesis and two UX principles),
`grammar-ast-live-pane.md` (the grammar/AST engine direction this adds
several data points to -- especially §2/§3's AST-reuse and dependency-graph
evidence), `widget-case-studies.md` and `markdown-and-mermaid-as-dsls.md`
(the other evidence bases in this sweep), `/Users/mphair/claude-projects/hexsheet/`
(the project itself, plus its own `plans/` directory for the design
discussions cited throughout).
