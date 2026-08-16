# app_dsl global-script codegen mode (TODO `1e032f3`) (COMPLETED)

## Summary

`app_dsl/codegen.py` (TODO `48e3b39`) currently only emits real ES
modules (`import`/`export`). `.desk_temp/build_widget.py`'s
`DefineWidget` packaging model concatenates *global, non-module*
scripts (`tsconfig.json`'s `files` array, in declared order, into one
`<script>` tag) -- confirmed via a real `tsc` probe that a file using
`export`/`import` always gets CommonJS-style `exports`/`require`
boilerplate in its compiled output, regardless of the `module`
compiler option (including `"module": "None"`); there is no way to
get plain global-script output from a file containing ES module
syntax. This plan adds a second codegen mode that emits genuinely
module-free code, matching
`shared-components/document-editor-base/document-editor-base.ts`'s
own established convention for exactly this packaging model.

## Affected files

- `app_dsl/codegen.py` -- a `mode` parameter threaded through every
  emit function.
- `app_dsl/schema.py` -- an optional `class_name` override on
  `ComponentEntry`.
- `app_dsl/parse.py` -- parses the new optional field.
- `app_dsl/build.py` -- a `--mode` CLI flag.
- `app_dsl/README.md` -- documents the new mode and its constraints.
- `tests/verify/` -- new coverage.

## Design decisions

- **`generate(definition, components_dir, out_dir, mode="module")`**
  -- default unchanged (today's only behavior), so every existing
  call site/test keeps working without modification. `mode="global"`
  is the new, additive path.
- **`mode="global"` emits zero `import`/`export` anywhere** -- plain
  `class`/`let`/`function`/`const` global declarations. No relative
  import path computation needed at all in this mode (`_import_path`
  is a `mode="module"`-only concern) -- `components_dir`/`out_dir`
  stay in the signature for API consistency but are unused by the
  global-mode emit path.
- **A real, documented constraint, not a limitation to silently work
  around**: in `mode="global"`, component and handler source files
  must *also* avoid ES module syntax (the same file-level "does this
  file use `import`/`export` at all" classification `tsc` itself
  uses, per the probe above, has no per-mode override -- a component
  file with `export default class Foo` would still get CommonJS
  boilerplate no matter what mode `app_dsl` generates its *own* code
  in). Ordering (components' compiled JS before the generated wiring
  file's) is the *caller's* responsibility via `tsconfig.json`'s
  `files` array, the same as any other multi-file `DefineWidget`
  source already requires (TODO `3fc5331`'s own precedent).
- **Component class-name resolution**: `mode="module"` never needs to
  know a component's real declared class name (`import X from "..."`
  renames whatever's default-exported to `X` regardless of its
  original name) -- `mode="global"` has no such renaming step, so the
  generated code's references (`customElements.define(tag,
  <ClassName>)`) must name the *real* global identifier exactly.
  Default: `codegen._class_name_for_tag(tag)`'s existing deterministic
  derivation (already used and documented, e.g. `"map-panel"` ->
  `"MapPanelElement"`) -- but rather than *requiring* every component
  author to know and follow that convention exactly, `ComponentEntry`
  gains an **optional** `class_name` override (`None` by default,
  falls back to the derived name) so a component with an
  already-existing, differently-named class still works without
  renaming it. This is additive to the schema -- an existing
  definition with no `class_name` keeps behaving exactly as before.
- **Handlers need no new field.** `HandlerRef.export` already means
  "the name of the thing in the target file" -- in `mode="module"`
  that's the export name to `import ... as`; in `mode="global"` it's
  simply the real global function name, referenced directly with no
  import at all. Same field, no schema change needed here.
- **Escape-hatch call resolution changes per mode**: `mode="module"`'s
  generated call site uses the DSL's own local handler key (aliased
  via the generated `import { X as key }`); `mode="global"` has no
  alias step, so the call site must resolve and emit
  `definition.handlers[key].export` directly instead of the local key
  -- the same real value, just reached differently depending on
  whether an import statement did the renaming or not.

## Step-by-step implementation

1. `schema.py`: `ComponentEntry` gains `class_name: str | None = None`.
2. `parse.py`: `_parse_components` reads an optional `"class_name"`
   key per entry (a non-empty string if present, otherwise `None` --
   same `_require_str`-shaped validation, just optional).
3. `codegen.py`:
   - `_class_name_for_tag` unchanged (still the default-derivation
     path).
   - A small `_resolved_class_name(component: ComponentEntry) -> str`
     helper: `component.class_name or _class_name_for_tag(component.tag)`.
   - `_emit_registry(definition, components_dir, out_dir, mode)`:
     `mode="module"` unchanged (imports + `customElements.define`
     using the *imported* alias, which is always
     `_class_name_for_tag` today since the import itself picks that
     name -- unaffected by the new override, which only matters for
     `mode="global"`); `mode="global"` emits only
     `customElements.define(tag, <resolved class name>)` lines, no
     imports.
   - `_emit_state`/`_emit_layout`/`_emit_event_wiring`: each gains a
     `mode` parameter, conditionally including/omitting the `export `
     prefix on their own top-level declarations. Internal-only helper
     functions (the per-node layout builders) already have no
     `export` in either mode -- unaffected.
   - `_emit_handler_imports`: `mode="module"` unchanged;
     `mode="global"` returns `[]` (nothing to import).
   - `_emit_action`'s escape-hatch branch: for `mode="global"`, resolve
     `definition.handlers[handler_name].export` and emit a call to
     *that* identifier instead of `handler_name` itself; for
     `mode="module"`, unchanged (the local alias is correct, since the
     generated import already renamed it).
   - `generate(...)`: validate `mode in ("module", "global")`
     (`DslError` otherwise), thread it through every call above.
4. `build.py`: `--mode {module,global}` CLI flag (default `module`),
   passed through to `generate(...)`.
5. `README.md`: document `mode="global"`'s format/constraints (no
   module syntax in components/handlers when using it; the
   `class_name` override field; that `tsconfig.json`'s `files`
   ordering is the caller's own responsibility, matching
   `build_widget.py`'s existing multi-file convention).
6. New/extended verify coverage (see below); run the full
   `tests/verify/` suite.

## Key tradeoffs

- `mode="global"` genuinely requires component/handler source written
  without ES module syntax -- a project wanting *both* a standalone
  build and a Desk-widget build from the very same component files
  still can't do that with this fix alone (that would need a real
  bundler, the other option `PARKINGLOT.md` already named and
  explicitly didn't pursue here, per `CLAUDE.md`'s dependency
  -avoidance instruction). This fix makes the Desk-widget target real
  and usable *today*, at the cost of component source not being
  automatically shared between the two targets -- an explicit,
  documented tradeoff, not a silent gap.

## Verification

New checks, real (no mocking, real `tsc`/`node`):
- `tests/verify/verify_app_dsl_codegen.py` (extend): a representative
  definition generated with `mode="global"`, alongside real
  module-free component fixtures (plain global `class Foo extends
  HTMLElement {}`, no `export`), compiled with a real `tsc` using a
  `tsconfig.json` whose `files` array orders components before the
  generated file (matching `build_widget.py`'s own convention) --
  confirm the *compiled* output contains no `require`/`exports`
  reference anywhere (a real regression check for the exact bug this
  item fixes), then concatenate the compiled `.js` files textually
  (mirroring what `build_widget.py`'s own `_concatenate_compiled_js`
  actually does) and run the concatenated result under real `node`
  with no `require()` calls at all -- confirming a dispatched event
  still correctly mutates state and fans out to a real method call,
  the same behavioral assertion the `mode="module"` test already
  makes.
- Same file: a `class_name` override actually changes which
  identifier `customElements.define` references, confirmed by using a
  deliberately-non-conventional class name and checking the generated
  text names it exactly.
- Same file: the escape hatch under `mode="global"` calls the
  handler's real `export` name directly (no import, no local-alias
  mismatch), confirmed via a real compile+concatenate+run round trip
  matching the `mode="module"` escape-hatch test's own shape.
- `tests/verify/verify_app_dsl_parse.py` (extend): `class_name`
  parses when present, defaults to `None` when absent, and rejects a
  non-string/empty value the same way every other optional string
  field does.
- Full `tests/verify/` regression suite.
