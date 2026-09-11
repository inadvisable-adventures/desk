# App-structure DSL: schema, parser, and codegen (TODO `48e3b39`) (COMPLETED)

## Summary

A declarative DSL + codegen tool for the wiring/layout code of a
multi-component SPA authored as a single `kind: "html"` widget --
generalized from `world-timelines`'s own hand-written `app-root.ts`.
Full design context, already had: `investigations/app_structure_dsl_design.md`.
This plan covers implementation only -- the design itself isn't
revisited here except where this pass has to pin down something the
investigation doc left at "needs a real plan" (chiefly: what language
the tool itself is written in, where it lives, and how "dual
transpilation target" is actually achieved).

**Scope of this pass**: component registry, layout mode 1
(n-split-panes -- `world-timelines`'s own real case), event-wiring
table (worker channels folded in, per the investigation doc), state
slots, and the escape hatch. Deferred to a later pass, each noted
explicitly rather than silently dropped: layout mode 2 (windowed)
codegen, the "dump current layout to HTML/CSS/TS" eject feature, and
(already separate TODOs) the visual layout-editing widget, the DSL
editor widget, and the shared state store.

## Affected files

- `app_dsl/` (new, repo root, git-tracked) -- the codegen tool's real
  Python source: schema/dataclasses, parser/validator, codegen.
- `src/desk/temp_ui.py` -- a new `sync_app_dsl_tool(temp_dir)`,
  mirroring `sync_shared_components`'s exact shape; wired into
  `TempUiManager.provision` alongside it; a doc mention (see Design
  decisions -- this is *not* a new tempui DSL keyword/split doc the
  way `Job`/`DefineWidget` are, so no `TEMPUI_DOC_VERSION` bump is
  needed for this pass, but `tempui-custom-widgets.md`'s "Authoring
  from real source" section gets a cross-reference added).
- `src/desk/shell/temp_ui_manager.py` -- calls the new sync function.
- `tests/verify/` -- new coverage.

## Design decisions

- **The tool itself is Python, not TypeScript/Node**, despite
  generating TypeScript. It reads a JSON DSL definition and
  string-templates real `.ts`/`.css` output -- the same shape
  `_BUILD_WIDGET_SCRIPT` already uses to emit output, just as a real,
  multi-file Python package instead of one generated-string script (see
  below for why). This avoids a new runtime dependency (no
  `ts-node`/`tsx` needed to *run* the codegen tool itself -- `CLAUDE.md`:
  "avoid adding dependencies, prefer bespoke solutions") and needs
  nothing beyond `tsc` already being on `PATH`, the same assumption
  `build_widget.py` already makes for compiling its *output*.
- **Mirrored into `.desk_temp/app_dsl/` the same way `shared-components/`
  already is** (`sync_shared_components`/`_repo_shared_components_dir`),
  not embedded as one giant string constant in `temp_ui.py` the way
  `_BUILD_WIDGET_SCRIPT` is. `_BUILD_WIDGET_SCRIPT`'s shape was right
  for a ~280-line, rarely-changing single script; this tool is real,
  actively-developed, multi-file Python (schema + parser + codegen as
  separate modules) -- keeping it as genuine git-tracked source under
  `app_dsl/` (unconditionally full-copied into `.desk_temp/app_dsl/`
  on every `provision`, exactly like `shared-components/`) keeps it
  normally lintable/testable/importable inside this repo, while still
  giving a target project a fresh, never-stale copy the same
  "regenerated on every open, nobody hand-edits it" way every other
  `.desk_temp`-mirrored asset already works.
- **"Dual transpilation target" needs no separate codegen mode.** The
  tool has exactly one job: given a DSL definition + a directory of
  plain, Desk-unaware components, emit real `.ts`/`.css` source files
  into a target directory. Those generated files have zero Desk
  -specific code in them (no Bridge API calls, nothing) unless the
  escape hatch's own handler code adds some -- which is the DSL
  author's choice, orthogonal to the tool. A **standalone build**
  target is just "the project's own existing `tsc`/build pipeline
  picks up the generated files like any other source" -- no Desk
  involvement at all. A **Desk-widget build** target is just "the
  generated files become input to the *already-existing*
  `build_widget.py` pipeline" (its `tsconfig.json` `files`-array
  ordering support, TODO `3fc5331`, already handles a multi-file
  compile unit) -- no second, Desk-aware codegen path needed inside
  this tool.
- **DSL definition format: a single JSON file** (not split across
  several, at least for this pass) with top-level keys `components`,
  `layout`, `events`, `state` -- simpler to parse/validate/keep
  internally consistent (e.g. an event action referencing an unknown
  component) than several separately-parsed files for a first pass.
  Splitting later, if a project's file grows unwieldy, is a
  non-breaking follow-up (the in-memory shape doesn't need to change,
  only how it's read from disk).
- **Schema validation via Python dataclasses + a hand-written
  validator, not a JSON Schema library** -- `CLAUDE.md`'s
  dependency-avoidance instruction, and the validation needed
  (required keys, known `type` discriminants, cross-references
  resolve to declared components/state slots) is straightforward
  enough to hand-write clear, specific error messages for, matching
  `_read_manifest`/`_read_tsconfig`'s own existing
  `build_widget.py`-established style (`BuildError` with a clear
  message, not a stack trace).
- **Codegen output**: one generated `.ts` file (component
  registration + event-wiring dispatch + state slot declarations) and,
  for layout mode 1, one generated `.css` file (the split-pane grid)
  plus the layout tree's own DOM-construction code folded into the
  same `.ts` file. Written to a directory the tool's caller specifies
  (a `--out` argument) -- never assumed to be `.desk_temp` or any
  Desk-specific location, since a standalone build has no reason to
  write there at all.
- **Event-wiring codegen**: each `{event, from, actions}` entry
  becomes a real `addEventListener` registration on the emitting
  component, dispatching to generated code that either mutates a
  generated state-slot variable (with a same-file, generated
  `setState`-style setter so future observers/re-render hooks have one
  place to hook, even though nothing in this pass consumes that hook
  yet) or calls the named method on the named target component
  directly -- one `addEventListener` per distinct `(event, from)`
  pair, fanning out to every action in `actions` in declared order.
- **State slots codegen**: a plain generated object/module-level
  `const state = { ... }` seeded with each slot's `default`, plus a
  generated setter per slot (`setSelectedId(value)`) that event actions
  call into -- no reactivity/observer system in this pass (nothing in
  the current scope needs one; the sibling shared-state-store design
  is a separate, later concern for *cross-widget* state, not
  intra-generated-code state).
- **Escape hatch**: a `handlers` field in the DSL naming a module + 
  export (e.g. `{"module": "./handlers", "export": "handleWeirdCase"}`),
  referenced by name from an event action
  (`{"call": "escape:handleWeirdCase", "args": [...]}`) -- codegen
  emits an `import` of the named module/export and calls it positionally
  with the same `args` resolution event-wiring actions already use.
  The handler module itself is hand-written, ordinary TypeScript --
  never generated, never overwritten.

## Step-by-step implementation

1. `app_dsl/schema.py`: dataclasses for `ComponentEntry`,
   `SplitLayoutNode` (recursive: `hsplit`/`vsplit`/`pane`),
   `EventWiringEntry` (+ `StateMutationAction`/`CallAction`),
   `StateSlot`, `HandlerRef`, and a top-level `AppDefinition`.
2. `app_dsl/parse.py`: `parse_app_definition(json_text) ->
   AppDefinition` -- required-key/type checks, resolves every
   component-name and state-slot-name reference in `layout`/`events`
   against the declared registry/state list, raising a clear
   `DslError` (mirroring `BuildError`'s own shape) naming the exact
   bad reference on failure.
3. `app_dsl/codegen.py`: `generate(definition: AppDefinition) ->
   dict[str, str]` (filename -> generated source text) -- the
   registration/layout/event-wiring/state-slot emission described
   above under Design decisions.
4. `app_dsl/build.py`: the actual CLI entry point --
   `python3 .desk_temp/app_dsl/build.py <definition.json> <components_dir> <out_dir>`
   -- reads, parses, generates, writes the output files.
5. `temp_ui.py`: `sync_app_dsl_tool(temp_dir)`, copying
   `_repo_app_dsl_dir()` (mirroring `_repo_shared_components_dir`'s
   exact shape) into `temp_dir / "app_dsl"`, unconditional full-copy
   like `sync_shared_components`. Call it from
   `TempUiManager.provision` right alongside the existing
   `sync_shared_components` call.
6. `tempui-custom-widgets.md`'s "Authoring from real source" section
   gains a short cross-reference to `app_dsl/README.md` for the
   "my widget is actually several wired-together components" case --
   not a new tempui DSL keyword, so no `TEMPUI_DOC_VERSION` bump.
7. `app_dsl/README.md`: the DSL's own format documentation (mirrors
   this plan's Design decisions section, written for whoever authors
   a DSL definition, not whoever's implementing the tool).
8. New/extended verify coverage (see below); run the full
   `tests/verify/` suite.

## Key tradeoffs

- No reactivity/observer hook consumed yet by generated state-slot
  setters -- deliberately inert plumbing for now (a real, if narrow,
  bit of speculative generality) since the alternative (regenerating
  this shape later, once something needs it) would be a real breaking
  change to already-generated output, whereas an unused setter costs
  nothing.
- JSON Schema validation was considered and rejected in favor of
  hand-written dataclass validation, per `CLAUDE.md`'s dependency
  -avoidance instruction -- accepted that error messages are only as
  good as what's hand-written, not schema-library-generic.
- This pass only implements layout mode 1 -- a DSL definition
  declaring `"layout": {"type": "windowed", ...}` is accepted by the
  parser (schema exists) but `codegen.py` raises a clear
  not-yet-implemented `DslError` rather than silently producing wrong
  output, so mode 2 support is a additive follow-up, not a breaking
  change to the definition format.

## Verification

New checks, real (no mocking, real `tsc`/`node`):
- `tests/verify/verify_app_dsl_parse.py`: `parse_app_definition`
  round-trips a real, representative definition (several components,
  an n-split-pane layout with a nested split, event actions of both
  kinds with fan-out, state slots with defaults); rejects each class
  of bad input with a clear, specific message (unknown component
  reference in layout, unknown state-slot reference in an action,
  missing required key, bad `type` discriminant).
- `tests/verify/verify_app_dsl_codegen.py`: a real, representative
  definition run through `generate()`, then the *actual output text*
  written to a real temp directory alongside real hand-written stub
  components, compiled with a real `tsc`, then *executed* with real
  `node` against a fixture that dispatches a real DOM-like event
  (a minimal `EventTarget`-based stub standing in for the DOM, since
  this runs under plain `node`, not a browser) -- confirms an event
  fired on the emitting component's stub actually mutates the
  generated state slot and calls the right method on the right target
  stub, not just that the generated text merely compiles.
- `tests/verify/verify_app_dsl_escape_hatch.py`: a definition
  referencing a hand-written handler module; confirms the generated
  code imports and calls it, verified via the same real-compile
  -and-run approach above.
- `tests/verify/verify_sync_app_dsl_tool.py` (or extending an existing
  `shared-components`-sync verify script, whichever fits): a real
  `TempUiManager.provision()` call actually mirrors `app_dsl/` into
  `.desk_temp/app_dsl/`, fresh on every call (matching
  `sync_shared_components`'s own always-fresh contract).
- Full `tests/verify/` regression suite.
