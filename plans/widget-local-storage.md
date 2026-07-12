# Widget-local storage

TODO `fb76057`.

## Summary

"Ensure that 'widget-local storage' exists, a means by which widgets
can store data in the current .desk file. It is possible that this
capability already exists, but if so, rebrand it to be 'widget-local
storage' if it isn't already."

Checked directly (see this TODO's own text in `TODO.md` and
`PARKINGLOT.md`'s existing "Widgets can't persist an arbitrary
per-instance chosen file across reload" note): no such capability
exists today. `WidgetState` (the per-widget-instance record inside a
`.desk` file) holds only geometry and `instance_id` -- no general data
payload, and `build() -> QWidget` (every widget kind's fixed contract)
takes no arguments, so there's no way for a widget to receive anything
back on restore either. `PARKINGLOT.md` already scoped the shape of
the fix ("a `state: dict` on `WidgetState`, a widget-side read/write
protocol, and a generalized post-build binding") -- this builds exactly
that, named "widget-local storage" throughout per the TODO's own
branding request.

## Key decisions

- **`WidgetState.state: dict = field(default_factory=dict)`** -- a
  plain, JSON-serializable dict, round-tripped through `.desk` files
  the same way every other `WidgetState` field already is
  (`desk_state_dict`/`save_desk`/`load_desk`). Old `.desk` files with no
  `"state"` key load fine (`WidgetState(**w)` just omits the kwarg,
  falling back to the default `{}`) -- no migration needed.
- **Pull-based, not push-based** -- unlike TODO a053e3a's `external
  _path_changed` (which needed a live signal because it drives a
  titlebar marker in real time), widget-local storage only needs to be
  read *at the moments a Desk is actually saved* (quit, explicit save,
  switching Desks) -- exactly when `DeskWindow._capture_desk_state`
  already re-reads every other per-widget field fresh, not
  continuously. No new signal needed; a widget just answers "what's
  your current data" whenever asked.
- **Duck-typed method pair, matching TODO a053e3a's `external_path
  _changed`/`refresh_external_path_status` generalized-binding
  precedent exactly** (not a new pattern): a widget that wants
  widget-local storage implements `get_widget_local_storage() -> dict`
  (called from `_capture_desk_state`, via a new small
  `_get_widget_local_storage(frame)` helper so it's independently
  testable) and/or `set_widget_local_storage(data: dict) -> None`
  (called once, only during an actual Desk-restore, via a new
  `_bind_widget_local_storage(frame, data)` -- mirroring
  `_bind_temp_ui_widget`'s existing restore-path-only shape, since a
  *fresh* placement has no prior state to restore). Either method is
  optional independently -- a widget can offer only one direction if
  that's all it needs.
- **The returned/accepted dict must be JSON-serializable** -- same
  implicit constraint every other `WidgetState` field already has; not
  validated or enforced here, matching this codebase's existing
  trust-the-widget-author posture (e.g. `WidgetState`'s existing fields
  have no runtime type validation either).
- **Explicitly not in scope**: migrating the existing per-kind special
  -cases (`_bind_temp_ui_widget`/`_bind_claude_widget`) onto this new
  general mechanism, or wiring any *specific* widget (Markdown, Editor,
  the future Stack widget from TODO ac212bc) up to actually use it.
  `PARKINGLOT.md`'s own note already frames "should TempUI/Claude
  special-casing be replaced by this" and "should Markdown/Editor
  persist their open file across reload" as separate, later design
  decisions -- this TODO is specifically "ensure the capability exists,"
  not "migrate everything onto it." `PARKINGLOT.md` updated to reflect
  that the capability now exists, with those two follow-ons left as
  open, now-actionable ideas rather than removed outright.

## Affected files

- `src/desk/desks.py` -- `WidgetState.state`; `desk_state_dict` includes
  it; `load_desk`/`save_desk` need no changes beyond the dataclass field
  itself (both already round-trip via `**w`/`dataclass` generically).
- `src/desk/shell/window.py` -- `_capture_desk_state` gains a new
  `_get_widget_local_storage(frame)` helper, called per frame;
  `_load_desk_widgets`'s restore loop gains
  `_bind_widget_local_storage(frame, state.state)`.
- `PARKINGLOT.md` -- update the existing note to reflect the capability
  now existing, narrowing it to the two remaining, still-open follow-on
  questions.
- `design-docs/architecture.md` -- a short mention wherever `WidgetState`
  /the Desk Model is described.

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication`, no mocks):

- `WidgetState`/`desk_state_dict`/`save_desk`/`load_desk` round-trip: a
  `state` dict survives a save-then-load cycle through a real temp
  `.desk` file, byte-for-byte equal.
- Loading an old-shaped `.desk` file (no `"state"` key at all, written
  by hand to simulate a pre-existing file) succeeds and defaults to
  `{}`, not a `TypeError`/`KeyError`.
- `DeskWindow._get_widget_local_storage`/`_bind_widget_local_storage`
  (both callable unbound, like TODO f8d9cec's `_bind_temp_ui_content`
  verification, since neither touches other `self` state): exercised
  directly against a real, minimal fake `PythonWidgetHost`-shaped
  content object implementing both methods, confirming data flows
  correctly in both directions; a content object implementing neither
  method is a safe no-op (no crash, empty dict on capture).

## Status

Not yet implemented.
