# Schema/state-management widget (TODO `6330249`) (COMPLETED)

## Summary

The third and last item split out of the original TODO `6e1c2fe` (see
TODO `af7898b`'s entry in `TODO.md` for that split's own reasoning). A
real, built-in `kind: "python"` Desk widget -- **not** a "dashboard" (an
earlier draft of this design used that word; it's an ordinary,
placeable/closeable widget instance like any other, just one that
happens to give deep insight into shared state) -- that lets a Desk
user **view and edit** every currently-registered `desk.state.*`
schema (widget-declared and top-level) and **view and edit** the data
stored under those keys (including non-validated ones), with live
updates as either changes elsewhere.

Depends on TODO `af7898b` (schema core) and TODO `9aef267` (top-level
schema files), both COMPLETED.

Full design context, already had -- see
`investigations/app_structure_dsl_design.md`'s "Validated vs.
non-validated state, and schema lifecycle" section (its own "singleton
dashboard widget" phrasing is corrected by this plan -- it's a normal
widget with an auto-placement guarantee, not a distinct UI concept).

## Affected files

- `src/desk/schema_registry.py` -- `RegisteredSchema.source_kind`
  (`"widget"` | `"file"`, distinguishing "edit this schema through the
  widget" from "this is owned by a widget's own manifest, view-only
  here"); `SchemaRegistry` takes an `EventMediator` and publishes a new
  `desk.state.schema_changed` event on every successful mutation;
  `SchemaRegistry.all()` for a full snapshot.
- `src/desk/server/runner.py` -- `SchemaRegistry(event_mediator)`
  construction.
- `src/desk/shell/window.py` -- `_refresh_builtin_schemas`/
  `_check_schema_conflict`/`_on_schema_file_changed` pass
  `source_kind` explicitly; new `get_state_overview`,
  `write_schema_file`, `delete_schema_key` methods; an auto-placement
  guarantee hook called after every successful schema registration;
  wiring for five new `current_context` hooks.
- `src/desk/shell/current_context.py` -- five new provider hook pairs
  (overview, history, value-writer, schema-file-writer,
  schema-file-deleter).
- `widgets/state_manager/` (new) -- `widget.json` (`kind: "python"`),
  `widget.py` (the actual UI).
- `src/desk/temp_ui.py` -- a one-line cross-reference from the
  existing "Shared, project-scoped state" section pointing at this
  widget (no `TEMPUI_DOC_VERSION` bump -- nothing about the
  `desk.*` Bridge API surface itself changes).
- `tests/verify/` -- new coverage.

## Design decisions

- **Widget kind: `"python"`, not `"html"`.** Every comparable
  management widget in this codebase (`todo`, `parking_lot`,
  `event_log`, `project_files`, `questions`) is `kind: "python"` with
  native Qt widgets -- richer table/tree/form controls than hand-built
  HTML, and it sidesteps CLAUDE.md's TypeScript-strict-mode/
  `<template>` requirements entirely (those apply to code that runs in
  a browser; a `kind: "python"` widget never does). The one `kind:
  "html"` precedent that looks similar at a glance
  (`filetype_registry_editor`) is a deliberately minimal, pre-dates
  -this-codebase's-current-conventions "edit the whole registry as one
  JSON blob" widget -- not a model for a real per-key
  view/edit/history UI.
- **`RegisteredSchema.source_kind`**: a schema is only editable/
  deletable through this widget if it's file-backed (`source_kind ==
  "file"`) -- a widget-declared schema's own manifest is the source of
  truth and this widget never edits it, only displays it (type
  expression, source id, enforcement status) with a note like "declared
  by widget `<id>` -- edit its own manifest to change." Distinguishing
  by an explicit field (set by whichever call site registers the
  schema) rather than sniffing the `source_widget_id` string's shape
  (a file path vs. a bare widget id) avoids any ambiguity for a
  hypothetical widget id that happens to look path-like.
- **Live updates via the existing event mediator, not polling**: this
  widget subscribes to the *already-existing* `desk.state.changed`
  (value writes) via the established `bind_event_mediator`/
  `EventSubscription` duck-type (see `widgets/project_files/widget.py`
  for the precedent this follows exactly), plus a **new**
  `desk.state.schema_changed` event (`{}`  payload -- a full-registry
  refresh is cheap enough that a per-key payload isn't worth the extra
  complexity) published by `SchemaRegistry` itself on every successful
  `register_permanent`/`clear_source`/`join_or_conflict_placement`
  call, using a sentinel `sender_instance_id="desk"` for
  system-triggered changes (hot reload, a schema file edit) that have
  no real originating widget instance -- every subscriber receives it
  regardless (there's no "self" to exclude). Centralizing the publish
  inside `SchemaRegistry` itself (it already needs an `EventMediator`
  reference passed in at construction, mirroring `event_mediator`'s
  own "one shared instance for the server run" shape) means no future
  call site can forget to notify.
- **Editing a value still goes through `DeskWindow.set_state`**,
  unchanged -- a validated key's edit is checked against its schema
  exactly the same way a Bridge API call would be; this widget gets no
  bypass. A rejected edit shows the same error message inline rather
  than silently failing.
- **Creating/editing a top-level schema through the widget** writes the
  underlying `.json` file directly (`DeskWindow.write_schema_file`) and
  relies entirely on the *already-existing* `SchemaFileWatcher`/
  `_on_schema_file_changed` pipeline (TODO `9aef267`) to pick it up,
  validate it, and publish the change event -- no new registration
  code path, no risk of the widget's own idea of "did this succeed"
  drifting from the real registry's. The widget offers a location
  choice (ephemeral `.desk_temp/schemas/`, or git-tracked
  `./desk-schemas/`) -- picking the git-tracked location through this
  widget is treated as the explicit, informed user action the original
  "never create it eagerly" rule was always about avoiding
  *unintentional* creation of, so `write_schema_file` creates
  `./desk-schemas/` on demand when the user picks it here.
- **Deleting a top-level schema key** (`DeskWindow.delete_schema_key`)
  edits (or, if it was the file's only key, removes) the owning
  `.json` file -- refuses with an error for a widget-sourced key
  (`source_kind == "widget"`), since there's no file to edit.
- **The stored *value* under a key is never deleted by "deleting a
  schema"** -- removing a schema just makes the key non-validated again
  (or, if nothing else claims it, simply unregistered); `Desk.state`
  itself has no delete operation in this pass either (matches TODO
  `f68383f`'s own scope -- a key's history/value persisting indefinitely
  once written was always the design, not an oversight this item
  needs to revisit).
- **Auto-placement guarantee**: after every schema registration that
  succeeds (built-in discovery/hot-reload, a tempui placement's own
  join, or a schema file being picked up), `DeskWindow` checks whether
  any instance of this widget is currently placed and places one
  (centered in the current view) if not. Implemented literally as
  written in the original design note -- checked on *every*
  registration, not "once per session" -- so if a user closes the
  widget and a new schema registers later, it reappears. This is a
  deliberate, flagged judgment call: the DefineWidget auto-placement
  revert (TODO `dafbaab`) was for a materially different shape
  (per-newly-registered-*kind*, could fire often, one new instance
  each time); this is a placement-count-capped-at-one guarantee for a
  single widget kind, closer in spirit to "make sure the log viewer
  exists" than "spawn something new." If real usage shows the
  reappear-after-close behavior is unwelcome, a follow-up TODO can add
  a "don't re-auto-place after an explicit close" refinement with a
  concrete complaint to design against, rather than speculating now.

## Widget UI (`widgets/state_manager/widget.py`)

- A `QSplitter` (horizontal): a `QTreeWidget` on the left listing every
  known key (from `DeskWindow.get_state_overview`) -- columns Key,
  Schema (type expression or "—"), Source (widget id / file path /
  "—"), Status ("permanent" / "N placed instance(s)" / "dormant" /
  "—"); a detail panel on the right for whichever key is selected.
- Detail panel, top to bottom:
  - Key name.
  - Schema section: read-only type expression + source note for a
    widget-sourced schema; an editable type-expression field + Save/
    Delete buttons plus a location choice for a file-sourced or
    undeclared key (declaring one here is exactly "add a top-level
    schema for this key").
  - Value section: current value as pretty-printed JSON in an editable
    text box, an optional one-line "edit" note field, a Save button
    (calls the value-writer hook; a schema mismatch or invalid JSON
    shows inline, doesn't clear the box).
  - History section: a read-only, latest-first list of past
    `(value, edit)` pairs (the history-reader hook, capped the same
    50-entry way `desk.state.getHistory` already is).
- A toolbar action to declare a brand-new key (name + initial value +
  optional schema), for the case for state that doesn't exist yet.
- `bind_event_mediator`: subscribes to `desk.state.changed` (refresh
  the affected row's value column, and the detail panel if that key is
  selected) and `desk.state.schema_changed` (refresh the whole tree).

## Step-by-step implementation

1. `schema_registry.py`: `RegisteredSchema.source_kind: str`;
   `SCHEMA_CHANGED_EVENT = "desk.state.schema_changed"`;
   `SchemaRegistry.__init__(self, event_mediator: EventMediator |
   None = None)`; `register_permanent`/`clear_source`/
   `join_or_conflict_placement` gain a `source_kind` parameter
   (defaulted sensibly where an existing caller doesn't care) and
   publish `SCHEMA_CHANGED_EVENT` on every successful mutation, guarded
   by `if self._event_mediator is not None` (tests construct a
   registry with no mediator freely, matching every existing
   `SchemaRegistry()` call in `tests/verify/`); `SchemaRegistry.all()
   -> list[RegisteredSchema]`.
2. `runner.py`: `SchemaRegistry(event_mediator)`.
3. `window.py`: `_refresh_builtin_schemas` passes `source_kind="widget"`;
   `_check_schema_conflict` passes `source_kind="widget"`;
   `_on_schema_file_changed` passes `source_kind="file"`; each of
   those three call sites also calls a new
   `_ensure_state_manager_placed()` after a successful registration.
   `get_state_overview(self) -> list[dict]`; `write_schema_file(self,
   location: str, key: str, type_expr: str) -> str | None`;
   `delete_schema_key(self, key: str) -> str | None`. Wiring for the
   five new `current_context` hooks in `__init__`, following the exact
   `current_context.set_x(self.method)` shape already used for
   `set_popup_opener`/etc.
4. `current_context.py`: `set_state_overview_provider`/
   `get_state_overview_provider`; `set_state_history_provider`/getter;
   `set_state_writer`/getter; `set_schema_file_writer`/getter;
   `set_schema_file_deleter`/getter -- same doc-comment style as every
   existing pair in this file.
5. `widgets/state_manager/widget.json` (`kind: "python"`, `capabilities:
   []`, a sensible `default_size`); `widgets/state_manager/widget.py`
   per the UI section above.
6. `temp_ui.py`: one sentence in "Shared, project-scoped state"
   pointing at the new widget for inspecting/editing state and schemas
   live. No version bump.
7. New/extended verify coverage (below); run the full `tests/verify/`
   regression suite.

## Key tradeoffs

- The auto-placement guarantee's "every registration, not once per
  session" behavior is a real, flagged judgment call -- see Design
  decisions above.
- No delete operation for a state *value* (only for a schema) --
  matches TODO `f68383f`'s own original scope.
- `desk.state.schema_changed`'s payload is empty (a signal to
  re-fetch, not the new state itself) -- simpler than keeping a
  per-key payload's shape in sync with every possible mutation kind
  (register/replace/dormant/conflict-cleared), at the cost of the
  receiving widget always doing a full re-fetch rather than a
  targeted update.

## Verification

New checks, real (no mocking):
- `tests/verify/verify_schema_registry.py` (extended): `source_kind`
  round-trips through `register_permanent`/`join_or_conflict_placement`;
  a real `EventMediator` passed to `SchemaRegistry` actually receives
  `desk.state.schema_changed` on a successful mutation, and does *not*
  on a conflict; `all()` returns every currently-registered schema.
- `tests/verify/verify_state_manager_widget.py`: a real `DeskWindow`
  -adjacent fake (mirroring `verify_state_store_schema_placement.py`'s
  pattern) -- `get_state_overview` reflects both validated and
  non-validated keys correctly, including `source_kind`; `write_schema_file`
  creates a real file under `.desk_temp/schemas/` and (for the
  git-tracked choice) creates `./desk-schemas/` on demand, and the
  written key becomes registered for real (round-tripping through the
  actual `SchemaFileWatcher`); `delete_schema_key` refuses for a
  widget-sourced key and actually removes a file-sourced one;
  `_ensure_state_manager_placed` places exactly one instance the first
  time a schema registers, is a no-op while one is already placed, and
  re-places after the sole instance is closed and another schema
  registers (confirming the literal, flagged behavior above is what
  actually ships).
- `tests/verify/verify_state_manager_widget_ui.py`: real
  `StateManagerWidget` construction against a fake
  `current_context`-provided backend -- the tree populates from
  `get_state_overview`; selecting a row shows its schema/value/history;
  editing a value and clicking Save calls the writer hook with the
  edited JSON; a writer-hook error (schema mismatch) shows inline
  without clearing the edit box; `bind_event_mediator` + a real
  published `desk.state.changed`/`desk.state.schema_changed` refreshes
  the view live.
- Full `tests/verify/` regression suite (120 scripts as of TODO
  `9aef267`, plus this item's new/extended scripts).
