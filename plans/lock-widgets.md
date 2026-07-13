# Lock widgets in place

TODO `8d05920`.

## Summary

A per-widget "locked" state: while locked, a widget's titlebar shows
only its title and an unlock icon (every other button -- lock,
bring-to-front, send-to-back, close -- collapses away), and the widget
can't be dragged, resized, or brought/sent in z-order. Persists across
Desk save/reload, since it's a durable per-instance preference, not
session-only UI state (unlike z-order, which this codebase's own docs
already note is deliberately session-only).

## Key decisions

- **A `locked: bool` field on `WidgetState`** (`desks.py`), defaulting
  to `False` -- an old `.desk` file with no `"locked"` key loads fine
  via the dataclass default, no migration needed. Captured in
  `_capture_desk_state` (reads `frame.locked`) and applied in
  `_load_desk_widgets` (calls `frame.set_locked(state.locked)` after
  placing). Not routed through the existing "widget-local storage"
  mechanism (TODO fb76057): that's for the wrapped *content* widget's
  own data via duck-typed get/set methods; lock is a chrome-level
  concept `WidgetFrame` itself owns, with no equivalent in arbitrary
  widget content.
- **Two more `_TitlebarButton`s**: `_LockButton` ("🔒") and
  `_UnlockButton` ("🔓"), sharing the same base class as
  close/bring-to-front/send-to-back. `_TitleBar.set_locked(bool)`
  toggles which set is visible: `[title, stretch, lock,
  bring_to_front, send_to_back, close]` unlocked, `[title, stretch,
  unlock]` locked -- a hidden `QHBoxLayout` child widget takes zero
  space by default, so this literally does collapse the row down to
  just the title and unlock icon, not just visually de-emphasize the
  others.
- **Reuses the exact same press-then-release-on-target click handling**
  the close/bring-to-front/send-to-back buttons already share
  (`_BUTTON_KINDS`, `_button_press`, generalized under TODO cdf45cb
  specifically so a new button kind wouldn't need new machinery) --
  `"lock"`/`"unlock"` are just two more entries in that same set.
- **A locked widget's titlebar still supports click-to-focus (TODO
  a1c701d)**, just not drag -- `mousePressEvent`'s titlebar branch
  always records the click-candidate tracking that feature added,
  before separately checking `frame.locked` to decide whether to *also*
  start a drag. A resize-handle press on a locked widget is swallowed
  (accepted, no resize) rather than silently falling through to
  something else.
- **No forced immediate save on lock/unlock.** Matches this app's
  existing convention (e.g. widget-local storage changes) of capturing
  state lazily at whatever save happens next (widget close, Desk
  switch, app quit), not forcing an extra one just for a chrome-state
  toggle.

## Affected files

- `src/desk/desks.py` -- `WidgetState.locked: bool = False`;
  `desk_state_dict` includes it.
- `src/desk/shell/widget_frame.py` -- `_LockButton`/`_UnlockButton`;
  `_TitleBar.set_locked`; `WidgetFrame.locked`/`set_locked`.
- `src/desk/shell/canvas.py` -- `_hit_test_chrome` recognizes the two
  new button kinds; `_BUTTON_KINDS` includes them;
  `mouseReleaseEvent`'s dispatch calls `frame.set_locked(...)`;
  `mousePressEvent` skips starting a drag/resize for a locked frame
  while still tracking the titlebar click candidate.
- `src/desk/shell/window.py` -- `_capture_desk_state`/
  `_load_desk_widgets` thread `locked` through.

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication`, real
`WidgetFrame`s embedded via a real `WorkspaceView`):

- `WidgetFrame.set_locked(True)` hides lock/bring-to-front/send-to
  -back/close and shows only unlock; `set_locked(False)` reverses it.
- `_hit_test_chrome` returns `(frame, "lock")`/`(frame, "unlock")` at
  the right screen positions, matching the currently-visible button.
- A synthetic press+release on the lock button locks the frame; on the
  unlock button (once locked) unlocks it -- mirroring the existing
  close-button click test shape.
- With a frame locked: a titlebar press does not set `_drag_frame` (no
  drag starts) but does still track the click candidate (a
  press+release still triggers `focus_last_widget`, TODO a1c701d); a
  resize-handle press is swallowed (accepted, `_drag_frame` stays
  `None`). With the frame unlocked, both behave as before (regression
  check).
- `_capture_desk_state`/`_load_desk_widgets` round-trip `locked`
  correctly (unbound-method-on-a-fake-double pattern, the established
  approach for `DeskWindow`-dependent logic); a `WidgetState` built
  from an old-shaped dict with no `"locked"` key still loads, defaulting
  to unlocked.

## Status

Not yet implemented.
