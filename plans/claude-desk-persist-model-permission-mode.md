# Persist the Claude (Desk) widget's model/permission-mode selections (TODO `1ceb701`) (COMPLETED)

## Summary

The Claude (Desk) widget's model and permission-mode combo boxes
(`widgets/claude_desk/widget.py`) always reset to their hardcoded
defaults (`DEFAULT_MODEL_INDEX`/`DEFAULT_PERMISSION_MODE_INDEX`) on
every Desk reboot, even for a widget instance that is *resuming* its
same underlying Claude session (`start_session(..., resume=True, ...)`)
-- a user who picked Opus and Plan mode for a given session loses both
choices the moment Desk restarts, even though the session itself
reconnects.

Persists both selections into the widget's own per-instance "widget
-local storage" (`WidgetState.state` in `src/desk/desks.py`, TODO
`fb76057`) -- the same generic, duck-typed
`get_widget_local_storage`/`set_widget_local_storage` mechanism several
other widgets (`job_runner`, `editor`, `git_diff`, ...) already use for
exactly this "survive a reload without a new persistence mechanism"
purpose -- and fixes an ordering gap in `DeskWindow` that would
otherwise apply the restored values too late to matter for this
particular widget.

## Affected files

- `widgets/claude_desk/widget.py` -- `get_widget_local_storage`/
  `set_widget_local_storage`.
- `src/desk/shell/window.py` -- `_place_widget` gains a
  `local_storage_data` parameter, applied (for this widget kind only)
  before `_bind_claude_desk_widget` starts the session, and
  `_load_desk_widgets` passes `state.state` through it.
- `tests/verify/verify_claude_desk_persist_model_permission_mode.py` --
  new.

## Design decisions

- **Widget-local storage, not the shared `desk.state.*` store** (TODO
  `f68383f`) -- that store is a shared, cross-widget, project-scoped
  key/value namespace (visible/editable via the State Manager widget),
  the wrong semantic home for one specific widget instance's own UI
  preference. It also has no generic "read a value" hook exposed to
  `python`-kind widgets on the GUI thread (only an overview/history/
  writer hook, built for the State Manager widget specifically) --
  widget-local storage already has the right read+write shape
  (`get_widget_local_storage`/`set_widget_local_storage`, called by
  `DeskWindow` on save/restore) and is the documented, existing
  mechanism for exactly this kind of per-instance persisted setting.
- **Store the SDK value (`"claude-sonnet-5"`, `"acceptEdits"`, ...),
  not the combo index** -- resilient to `MODEL_CHOICES`/
  `PERMISSION_MODE_CHOICES` gaining/losing/reordering entries later; on
  restore, look up the matching index by value and fall back to the
  existing hardcoded default index if the stored value no longer
  appears in the list (e.g. a model was retired).
- **A missing key is not the same as an explicit `None`** --
  `MODEL_CHOICES`' own `"Default"` entry's value *is* `None`, so
  `data.get("model")` alone can't tell "the user really had Default
  selected" apart from "this key was never saved" (old data, or an
  empty `{}` from an instance that predates this feature) -- both
  would otherwise resolve to the same value and silently pick
  `"Default"` even when the intended fallback is this widget's own
  hardcoded `DEFAULT_MODEL_INDEX` (`"Sonnet"`). Fixed with a small
  sentinel (`data.get("model", _NOT_SAVED)`), not `data.get("model")`.
- **The real ordering bug this item must fix**: `_load_desk_widgets`
  calls `_place_widget` (which, for `CLAUDE_DESK_WIDGET_ID`, calls
  `_bind_claude_desk_widget` -> `start_session` synchronously, reading
  the combo boxes' *current* index right then) and only afterward
  calls `_bind_widget_local_storage` to restore saved per-instance
  state -- so today, restoring the combo values into
  `set_widget_local_storage` would always arrive one step too late to
  affect the session `start_session` already began. Fixed narrowly: a
  new optional `local_storage_data` parameter on `_place_widget`,
  applied (only for this one widget id) immediately before
  `_bind_claude_desk_widget` runs. `_load_desk_widgets`'s own existing
  call to `_bind_widget_local_storage` afterward is left completely
  unchanged (still fires for every widget kind, including this one) --
  a harmless, idempotent second application for `claude_desk` (setting
  the same combo index again is a no-op), and the only way every other
  widget kind's restore timing stays byte-for-byte as it was.
- **No change to `current_context`/hook-wiring order** -- this is a
  synchronous, same-process, same-call-stack fix entirely inside
  `_place_widget`/`_load_desk_widgets`; no new hook is needed for this
  item (unlike TODO `551014c`, which does need one, and specifically
  avoids this same ordering trap a different way -- see that plan).

## Step-by-step implementation

1. `widget.py`: `get_widget_local_storage(self) -> dict` returns
   `{"model": MODEL_CHOICES[self._model_combo.currentIndex()][1],
   "permission_mode": PERMISSION_MODE_CHOICES[self._permission_mode_combo.currentIndex()][1]}`.
   `set_widget_local_storage(self, data: dict) -> None` looks up each
   stored value's index via a small `_index_for_value(choices, value,
   default_index)` helper, calling `setCurrentIndex` only if found.
2. `window.py`: `_place_widget` gains `local_storage_data: dict | None
   = None`; in the `elif widget_id == CLAUDE_DESK_WIDGET_ID:` branch,
   if `local_storage_data is not None`, call
   `self._bind_widget_local_storage(frame, local_storage_data)` before
   `self._bind_claude_desk_widget(...)`. `_load_desk_widgets`'s call
   to `_place_widget` passes `local_storage_data=state.state`.
3. New verify script (below); run the full `tests/verify/` suite.

## Key tradeoffs

- A freshly-*placed* (non-restored) widget instance never has saved
  local storage yet, so it always starts from the hardcoded defaults,
  same as today -- persistence only ever matters starting from a
  widget's second (restored) launch onward, which matches the actual
  ask ("if Desk reboots, they will return to their pre-reboot state").

## Verification

New `tests/verify/verify_claude_desk_persist_model_permission_mode.py`:
- `get_widget_local_storage()` round-trips a non-default combo
  selection for both combos.
- `set_widget_local_storage({"model": ..., "permission_mode": ...})`
  selects the right index for a real stored value, and falls back to
  the existing default index for an unknown/missing one (simulating a
  retired model).
- A real `DeskWindow._place_widget`-shaped restore ordering check:
  applying `set_widget_local_storage` before `start_session` (as
  `_place_widget` now does for this widget id) means the session
  actually starts with the restored model/mode, not the hardcoded
  default -- exercised the same "swap in a `_FakeSession`, call
  `start_session` directly" way `verify_claude_desk_widget.py`'s own
  permission-mode tests already do.
- Full `tests/verify/` regression suite passes.
