# State store schema declaration, conflict resolution, and validation core (TODO `af7898b`) (COMPLETED)

## Summary

The first of three items split out of the original TODO `6e1c2fe` (see
that split's own reasoning in `TODO.md`). This item makes a `desk.state.*`
key **validated** when a widget declares a schema for it in its own
manifest, with conflict resolution and enforcement-lifetime tracking, and
makes an **undeclared** access to an already-validated key check against
that schema at runtime. Top-level schema files (TODO `9aef267`) and the
new schema/state-management widget (TODO `6330249`) are explicitly out of
scope here -- this item only covers a schema declared in a widget's own
manifest.

Full design context, already had -- see
`investigations/app_structure_dsl_design.md`'s "Validated vs. non-validated
state, and schema lifecycle" and "Bookkeeping and call sites" sections.

**Decided in this planning pass** (not yet nailed down at the design-doc
level): for a **built-in** widget (a real `widgets/<id>/widget.json`),
`desk_widget_loading_errors` is populated **in-memory only**, on the live
`WidgetInfo` -- Desk never writes back into the widget author's own
`widget.json` file on disk. This avoids a feedback loop with the existing
`widgets_dir` hot-reload watcher (which would otherwise see Desk's own
write as a change and re-trigger discovery) and avoids surprising a
widget's own git history with Desk-authored edits. The error is still
fully discoverable live (the notification banner) and via
`self.getManifest()` for as long as the conflict persists; it does not
survive past the point the underlying widget.json/`widgets_dir` state that
caused it changes (a live re-scan naturally re-derives it fresh each
time). A tempui-defined custom widget's `WidgetInfo` is populated exactly
the same way -- there was never a real on-disk manifest file for these
either, so no divergence in behavior between the two widget-registration
paths.

## Affected files

- `src/desk/schema_types.py` (new) -- the pragmatic TypeScript-subset type
  expression parser, JSON-value validator, best-effort coercer, and
  structural-equivalence check.
- `src/desk/schema_registry.py` (new) -- the runtime-only (never
  persisted) schema registry: which key currently has an active schema,
  its source widget id, whether it's permanently enforced (built-in) or
  placed-instance-tracked (tempui-sourced), and (for the latter) which
  placed instance ids are keeping it active.
- `src/desk/widgets.py` -- `WidgetInfo` gains `state_schema: dict[str,
  str]` and `desk_widget_loading_errors: list[str]`; `_parse_manifest`
  reads the new optional `state_schema` manifest key (never
  `desk_widget_loading_errors` -- that one is Desk-populated only, never
  read from the file).
- `src/desk/temp_ui.py` -- `CustomWidgetDefinition` gains `state_schema:
  dict[str, str]`; `parse_define_widget` gains a new repeatable
  `StateSchema<TAB>key<TAB>type_expr` DSL line (same shape as the existing
  `Capability<TAB>name` line); Bridge API doc section on `desk.state.*`
  updated to describe validated vs. non-validated behavior;
  `TEMPUI_DOC_VERSION` bump.
- `src/desk/server/runner.py` -- `ServerHandle.schema_registry: SchemaRegistry`,
  constructed once in `start_server` alongside `event_mediator`.
- `src/desk/server/app.py` -- `create_app` takes `schema_registry`;
  `state_set`/`state_get` routes become schema-aware (validate against an
  active schema, or best-effort-coerce via an optional `type_hint` when
  none is active); `self_get_manifest` resolves through the live
  `gui_bridge.window.get_widget_info` (when available) instead of trusting
  `require_caller`'s injected `WidgetInfo`, so `desk_widget_loading_errors`
  and `state_schema` are never stale.
- `src/desk/server/bridge_client.py` -- `desk.state.get`/`.set` gain an
  optional `typeHint` parameter.
- `src/desk/shell/window.py` -- `self._schema_registry = handle.schema_registry`;
  a new `_refresh_builtin_schemas()` method (called from `__init__` and
  from `_on_widget_changed_refresh_catalog`, mirroring how `self._widgets`
  itself gets rebuilt in both places); `_place_widget` gains the
  tempui-sourced conflict gate (returns `None` on a hard conflict instead
  of a `WidgetFrame`); every existing `_place_widget` call site updated to
  handle a `None` return; `close_widget`/`close_widget_by_instance_id`
  need no new code (pruning stays lazy, per the original design decision);
  `get_state`/`set_state` become schema-aware.
- `tests/verify/` -- new coverage (see below).

## Design decisions

- **Manifest field name**: `state_schema: { "<key>": "<TypeScript type
  expression as a string>", ... }` -- a dict, not a list, since a widget
  may declare schemas for more than one key. Lives alongside
  `capabilities` in `widget.json` (built-in) or as repeatable
  `StateSchema<TAB>key<TAB>type_expr` lines in a `DefineWidget` tempui
  file (mirroring `Capability<TAB>name`'s own shape exactly).
- **`desk_widget_loading_errors` is in-memory only, on `WidgetInfo`** --
  see the Summary section above. Never read from or written to a real
  `widget.json` file. Populated by whichever call site detects the
  conflict (`_refresh_builtin_schemas` for a built-in,
  `_place_widget`/`_load_desk_widgets` for a tempui-sourced one),
  directly appending to the already-live `WidgetInfo` instance in
  `self._widgets` (never replacing the dict entry, so the object identity
  a notification click-handler or a concurrent read might be holding
  stays valid).
- **Schema type expression language** (`schema_types.py`): a small,
  intentionally constrained recursive-descent grammar --
  `type := union`; `union := atom ("|" atom)*`; `atom := primitive |
  literal | array | object | "(" type ")"`; `primitive := "string" |
  "number" | "boolean" | "null"`; `literal := STRING | NUMBER | "true" |
  "false"`; `array := atom "[]"` (postfix, stackable: `string[][]`
  parses); `object := "{" (member SEPARATOR?)* "}"`; `member := IDENT
  "?"? ":" type` (`;` or `,` as a member separator, either accepted).
  No intersections, generics, tuples, or `unknown`/`any`/`never` in v1 --
  left to grow later if a real need shows up, per the original design
  note.
  - `validate(node, value) -> bool`: structural, JSON-value-shaped
    checking. An `object` type is **permissive about extra keys**
    (structural subtyping over the declared members only, not an exact
    shape match) -- matches real TypeScript's own structural typing for
    a value being checked against a type, not the stricter
    excess-property check TS only applies to a fresh object *literal*.
  - `coerce(node, value)`: best-effort, **never raises** -- returns the
    original value unchanged if no sensible coercion applies. Only used
    for the non-validated, call-site `typeHint` path; a validated key
    never coerces, it validates-or-rejects.
  - `type_expressions_equivalent(a, b) -> bool`: parses both and compares
    the resulting ASTs structurally (object members sorted by name, union
    options sorted by their own repr) -- so `"{ b: string; a: number }"`
    and `"{ a: number, b: string }"` count as the same schema, and
    `"A | B"` equals `"B | A"`. This is what decides "unchanged" (reactivate
    a dormant schema, keep its data) vs. "different" (replace it) when a
    new instance is placed against a dormant entry.
  - A syntax error while parsing a widget's own declared schema is itself
    a loading error -- appended to that widget's `desk_widget_loading_errors`
    the same way a genuine conflict is, and that key is simply not
    registered from this widget (as if it hadn't declared a schema for
    that key at all).
- **`SchemaRegistry`** (`schema_registry.py`): one instance per server
  run (`ServerHandle.schema_registry`, mirroring `EventMediator` exactly
  -- constructed once, shared between the Bridge API routes and
  `DeskWindow`, rebuilt fresh on process restart, **never persisted**,
  since everything that populates it is already re-walked on every Desk
  open/switch anyway: built-ins via `discover_widgets`/hot-reload,
  tempui-sourced ones via placement/restore).
  - `RegisteredSchema(key, type_expr, type_node, source_widget_id,
    permanent: bool, placed_instance_ids: set[str])`.
  - `register_permanent(key, type_expr, source_widget_id) -> None`,
    raising `SchemaConflict(message)` if a different schema (permanent or
    still-active-tempui) already claims `key`. Idempotent for the exact
    same `(key, type_expr, source_widget_id)` triple (a hot-reload
    re-registering the same built-in schema unchanged is not a conflict
    against itself).
  - `clear_source(source_widget_id) -> None` -- drops every permanent
    entry this source registered. Called at the start of
    `_refresh_builtin_schemas` before re-walking the fresh
    `discover_widgets` result, so a schema a widget author just removed
    (or a widget that's been deleted) doesn't linger forever; a
    conflict that's been fixed on disk also correctly clears this way.
  - `join_or_conflict_placement(key, type_expr, source_widget_id,
    instance_id, is_instance_placed) -> None`, raising `SchemaConflict`
    on a genuine conflict. `is_instance_placed` is a `Callable[[str],
    bool]` -- before deciding, this method first prunes any id already
    in the existing entry's `placed_instance_ids` for which
    `is_instance_placed(id)` is now `False` (the lazy maintenance pass).
    Then: no existing entry -> register fresh, non-permanent, with
    `{instance_id}`. An existing **permanent** entry -> conflict unless
    `type_expr` is equivalent, in which case this is just an ordinary
    join (no instance tracking needed for a permanent entry either way).
    An existing **non-permanent, still non-empty** entry -> conflict
    unless equivalent, in which case add `instance_id` to the set. An
    existing **non-permanent, now-empty (dormant)** entry -> if
    equivalent, reactivate (add `instance_id`, data/history untouched);
    if different, replace the entry outright with the new schema and
    `{instance_id}` (the prior dormant schema's own data is not deleted
    from `Desk.state` -- it's simply no longer the active schema for
    that key going forward, exactly as designed).
  - `get(key) -> RegisteredSchema | None` -- used by the Bridge API's
    `get`/`set` for runtime validation.
- **Conflict-resolution ordering for built-ins**: `discover_widgets`
  already iterates `sorted(widgets_dir.iterdir())`, and Python dicts
  preserve insertion order, so `_refresh_builtin_schemas` walking
  `self._widgets.values()` in order and registering greedily
  (first-one-in wins, later ones conflict) reproduces "alphabetical
  directory order, first wins" with no extra sorting logic needed.
- **`_place_widget` becomes fallible**: returns `WidgetFrame | None`.
  Every existing call site (`_load_desk_widgets`, the "invoke a defined
  widget" tempui path, the Job placement call, drag-from-catalog,
  Questions-widget-focus, and others -- grepped and enumerated in the
  implementation step below) is updated to skip its post-placement setup
  (binding tempui content, restoring local storage, etc.) when the
  result is `None`, rather than assuming success unconditionally. A
  conflict during a **restore** (`_load_desk_widgets`) means that one
  saved widget entry is silently skipped for this session (still present
  in the `.desk` file for next time) -- not a fatal error for the rest of
  the restore.
- **Where the tempui-sourced conflict check actually runs**: inside
  `_place_widget` itself, immediately before a frame is created, gated on
  `widget.state_schema` being non-empty and `widget.tempui_only` (or more
  precisely: not a real `discover_widgets`-sourced built-in -- built-ins
  are permanently registered already by the time any placement happens,
  so re-checking them at placement time would be redundant, not wrong,
  but the registry's `register_permanent` idempotency check makes this
  safe either way; the implementation only calls
  `join_or_conflict_placement` for a widget whose id is a registered
  custom-widget keyword, to avoid doing placement-time bookkeeping for
  ordinary built-ins that don't need it).
- **Notification**: reuses `WorkspaceView.notify_temp_ui(path, text,
  on_clicked)` exactly as tempui files already do, keyed by a
  content-free synthetic `Path` (`Path(f"schema-conflict:{widget_id}")`)
  so a widget with a live, unresolved conflict shows exactly one banner
  no matter how many times placement is retried, the same
  dedup-by-key behavior `_notify_temp_ui` already relies on for real
  tempui files. Clicking it shows a popup (`current_context
  .get_popup_opener()`, the same blocking popup service `kind:"python"`
  widgets already use) with the conflict's full message.
- **Bridge API validation semantics**:
  - `set(key, value, edit, typeHint?)`: if `schema_registry.get(key)` is
    not `None`, `value` is validated against its `type_node` --
    on failure, the route returns HTTP 400 (a real runtime error, per the
    design doc, not silently coerced or dropped) and nothing is stored or
    published. If no schema is active, `typeHint` (optional, a raw type
    expression string) is parsed and used to best-effort `coerce(value)`
    before storing -- a parse error in `typeHint` itself is a 400,
    distinct from a schema-validation failure. Omitting `typeHint`
    entirely preserves TODO `f68383f`'s existing behavior exactly
    (store as given, no coercion) -- fully backward compatible.
  - `get(key, typeHint?)`: if a schema is active for `key`, `typeHint` is
    ignored (the stored value is already schema-conformant by
    construction -- every write that reached storage already passed
    validation) and the raw value is returned as-is. If no schema is
    active and `typeHint` is given, the *returned* value is
    best-effort-coerced (the stored value itself is untouched).

## Step-by-step implementation

1. `schema_types.py`: tokenizer + recursive-descent parser for the
   grammar above; `PrimitiveType`, `LiteralType`, `ArrayType`,
   `UnionType`, `ObjectType` node dataclasses; `SchemaSyntaxError`;
   `parse_type_expression`, `validate`, `coerce`,
   `type_expressions_equivalent`.
2. `schema_registry.py`: `RegisteredSchema`, `SchemaConflict`,
   `SchemaRegistry` with `register_permanent`/`clear_source`/
   `join_or_conflict_placement`/`get`, per the Design decisions above.
3. `widgets.py`: `WidgetInfo.state_schema: dict[str, str] = field(default_factory=dict)`,
   `WidgetInfo.desk_widget_loading_errors: list[str] = field(default_factory=list)`;
   `_parse_manifest` reads `manifest.get("state_schema", {})`.
4. `temp_ui.py`: `CustomWidgetDefinition.state_schema: dict[str, str] =
   field(default_factory=dict)`; `parse_define_widget` collects
   `StateSchema<TAB>key<TAB>type_expr` lines into a dict (last one for a
   given key in file order wins, matching how a real `widget.json`'s
   `state_schema` dict would behave with a duplicate key); Bridge API doc
   section rewritten to describe validated/non-validated `get`/`set`;
   `TEMPUI_DOC_VERSION` bump with a changelog entry.
5. `runner.py`: `ServerHandle.schema_registry: SchemaRegistry`; `start_server`
   constructs one and passes it into `create_app`.
6. `app.py`: `create_app` accepts `schema_registry`; `SetStateRequest`
   gains `type_hint: str | None = None`; `state_set` validates/coerces
   per the Bridge API semantics above; `state_get` accepts an optional
   `type_hint` query param and coerces the returned value when
   applicable; `self_get_manifest` adds its own `x_desk_widget_id: str =
   Header(...)` parameter and prefers `gui_bridge.window.get_widget_info(...)`
   over the `require_caller`-injected `WidgetInfo` when the live window
   is attached and knows this id, falling back to the injected one
   otherwise (unauthenticated/pre-attach case unchanged);
   `_widget_info_dict` includes `state_schema` and
   `desk_widget_loading_errors`.
7. `bridge_client.py`: `state.get(key, typeHint)`/`state.set(key, value,
   edit, typeHint)` thread the new optional parameter through as an extra
   query param / body field.
8. `window.py`:
   - `self._schema_registry = handle.schema_registry` in `__init__`.
   - `_refresh_builtin_schemas()`: `self._schema_registry.clear_source(id)`
     for every currently-known built-in id, then walks
     `self._widgets.values()` in order, calling `register_permanent` for
     each declared `state_schema` entry; a `SchemaConflict` appends its
     message to the losing widget's `desk_widget_loading_errors` and
     fires the notification (see below); a `SchemaSyntaxError` from
     `schema_types.parse_type_expression` does the same instead of
     attempting registration. Called at the end of `__init__` (after
     `self._widgets` is first set) and at the end of
     `_on_widget_changed_refresh_catalog`.
   - `_place_widget`: before creating a frame, if `widget.state_schema`
     is non-empty and this is a registered custom-widget keyword (i.e.
     tempui-sourced, not a real built-in), resolve the eventual
     `instance_id` first (same `uuid.uuid4()`/default-8-hex logic already
     there, just hoisted above the new check), then call
     `self._schema_registry.join_or_conflict_placement(...)` once per
     declared key with `is_instance_placed=self._is_instance_currently_placed`
     (a new small helper: `self.find_frame_by_instance_id(id) is not
     None`). On any `SchemaConflict`, append the message to
     `widget.desk_widget_loading_errors`, fire the notification, and
     return `None` without creating a frame. Otherwise proceed exactly as
     today, using the already-resolved `instance_id`.
   - Every `_place_widget(...)` call site updated for a possible `None`
     result (grep-enumerated at implementation time; expected to include
     `_load_desk_widgets`, `_seed_new_desk_widgets`'s callers indirectly
     via `open_widget_content`, the tempui "invoke a defined widget" path,
     Job placement, drag-from-catalog, and `_focus_questions_widget`).
   - `_notify_schema_conflict(widget_id, message)`: builds the synthetic
     `Path(f"schema-conflict:{widget_id}")` key and calls
     `self.view.notify_temp_ui(path, f"Schema conflict: {widget_id}",
     lambda: self._show_schema_conflict_popup(widget_id, message))`.
   - `get_state`/`set_state` become schema-aware per the Bridge API
     semantics above, consulting `self._schema_registry.get(key)`.
9. New/extended verify coverage (below); run the full `tests/verify/`
   regression suite.

## Key tradeoffs

- `desk_widget_loading_errors` never surviving a restart for a built-in
  (in-memory only) is a real, deliberate limitation -- see the Summary's
  callout. If real usage shows this insufficient, a follow-up TODO can
  revisit persisting it, now with a concrete usage pattern to design
  against instead of speculating up front.
- The schema type language is deliberately small; a widget author who
  needs, say, TypeScript generics or tuple types has no escape hatch in
  this pass beyond leaving the key non-validated.
- `_place_widget` becoming fallible is a real, if mechanical, ripple
  across every call site -- worth double-checking each one lands its own
  "conflict means silently skip this one placement" behavior correctly
  rather than crashing on an unexpected `None`.

## Verification

New checks, real (no mocking):
- `tests/verify/verify_schema_types.py`: parser round-trips for every
  grammar production (primitives, literals, arrays including
  double-array, unions, objects with optional members, nested
  combinations); `validate` true/false cases per node type, including
  the "extra object keys are allowed" permissiveness; `coerce` for each
  primitive target plus a union and an object case, confirming it never
  raises on a hopeless input (returns the value unchanged instead);
  `type_expressions_equivalent` true for reordered object members/union
  options, false for a genuine type difference; `SchemaSyntaxError` on
  malformed input (unbalanced braces, an unknown primitive name, a
  trailing token).
- `tests/verify/verify_schema_registry.py`: `register_permanent` accepts
  a fresh key, is idempotent for the same source re-registering the same
  schema, conflicts against a different source's schema for the same
  key; `clear_source` lets a previously-conflicting schema through once
  the original registrant is cleared; `join_or_conflict_placement`
  covers fresh-registration, join-while-active, conflict-while-active,
  dormant-reactivate-if-unchanged, dormant-replace-if-different, and the
  lazy-pruning-via-`is_instance_placed` maintenance step actually being
  exercised (an instance considered no longer placed is dropped from the
  set before the dormant/active decision is made).
- `tests/verify/verify_state_store_schema.py`: a real Bridge-API-over
  -HTTP round trip -- a `set` matching an active schema succeeds and is
  retrievable; a `set` violating it is a 400 and neither stored nor
  published; `set` with a `typeHint` on a non-validated key coerces
  before storing; `set` with no `typeHint` and no active schema is
  byte-for-byte today's `f68383f` behavior (regression guard); `get`
  with a `typeHint` coerces the returned value without mutating storage;
  `self.getManifest()` reflects `state_schema`/`desk_widget_loading_errors`
  live (via the `gui_bridge.window.get_widget_info` fix), not the
  stateless `discover_widgets` scan's stale copy.
- A widget-placement-level test (real `DeskWindow`-adjacent, following
  `verify_define_widget_no_auto_place.py`'s established real-Qt-app
  pattern for exercising `_place_widget`/`_register_custom_widget`
  directly): two `DefineWidget`-sourced kinds declaring conflicting
  schemas for the same key -- first placement succeeds, second is
  refused (`_place_widget` returns `None`), a notification fires, and
  `desk_widget_loading_errors` is populated on the refused kind's
  `WidgetInfo`; closing the first instance and placing a third,
  schema-matching instance of the *first* kind succeeds (dormant
  -reactivate); placing a schema-*different* instance of the *first*
  kind after that succeeds too (dormant-replace) and the *second* kind
  can now also be placed with its own (still-different) schema without
  conflict.
- Full `tests/verify/` regression suite (115 scripts as of TODO
  `f68383f`, plus this item's new scripts).
