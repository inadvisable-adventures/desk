# Add a widget close button (COMPLETED)

## Summary

An "X" close button in the upper-right corner of every widget's
`WidgetFrame` titlebar (see item 10/`design-docs/widget-ux.md`), which
removes that widget instance from the canvas and the current Desk after a
confirmation prompt (guarding against accidental clicks/data loss).

## Affected files

- `src/desk/shell/widget_frame.py` (edit) — add a `_CloseButton` chrome
  element to `_TitleBar`.
- `src/desk/shell/canvas.py` (edit) — recognize a close-button hit in
  `_hit_test_chrome`, handle click (not drag) semantics for it in
  `mousePressEvent`/`mouseReleaseEvent`, add a `widget_close_requested`
  signal and a `remove_widget` method.
- `src/desk/shell/window.py` (edit) — connect the new signal, confirm, then
  remove the widget and save the Desk.

## Design

### `_CloseButton`: purely visual, like `_TitleBar`/`_ResizeHandle`

A small `QWidget` (an "✕" label) added to `_TitleBar`'s layout, after the
existing stretch, so it sits at the titlebar's right edge. Counter-scaled
via its own `apply_scale()` (called from `_TitleBar.apply_scale`) to stay a
constant on-screen size regardless of canvas zoom, exactly like the
existing chrome elements.

Deliberately has **no click handling of its own** — per
`design-docs/widget-ux.md`, all chrome interaction (titlebar drag, resize
handles) is already centralized in `WorkspaceView`'s own mouse events
because embedded-widget mouse coordinates don't reliably reflect real
screen coordinates at non-unity zoom (see `LEARNINGS.md`). A real
`QPushButton.clicked` signal would actually still fire correctly here (Qt's
own internal click-vs-drag detection doesn't depend on the coordinate APIs
that were found unreliable) — but `WorkspaceView.mousePressEvent` currently
intercepts and `accept()`s *every* press that lands anywhere in the
titlebar before it ever reaches an embedded child widget, so a real
`QPushButton` inside the titlebar would never actually receive the click.
Following the established pattern (a purely-visual chrome widget,
identified by type in `_hit_test_chrome`) keeps one consistent interaction
model for all chrome, rather than two different ones.

### `_hit_test_chrome` gains a third hit kind: `"close"`

Currently returns `(frame, None)` for a titlebar-drag hit or
`(frame, edge)` for a resize handle. Add `_CloseButton` to the walk-up-
from-`childAt()` type check (checked before `_TitleBar`, since a
`_CloseButton` is nested inside the titlebar's own layout and would
otherwise be misclassified as a plain titlebar hit) and return
`(frame, "close")` when it's the hit element.

### Click (not drag) semantics for the close button

`mousePressEvent`: a `"close"` hit is remembered (`self._close_press_frame`)
but does **not** start a drag session (no `self._drag_frame` set).
`mouseReleaseEvent`: if there's a pending close-press, re-run
`_hit_test_chrome` at the release position — if it's still the *same*
frame's close button (ordinary "click" semantics: press and release both
land on the button, not press-then-drag-away), emit
`widget_close_requested(frame)`; otherwise treat it as a cancelled click
(no-op).

### Removal: confirm, then remove from canvas + save the Desk

`DeskWindow` connects `widget_close_requested`, shows a confirm prompt
(reusing the existing `_confirm_fn` helper, so a fake confirm callable can
be injected for testing — same pattern as `switch_desk`/
`change_current_desk_directory`), and on confirmation calls a new
`WorkspaceView.remove_widget(frame)` (removes the proxy from the scene,
drops the frame from `self._frames`, and calls `frame.deleteLater()` — see
Key Design Decisions for why this differs slightly from `clear_widgets()`)
followed by `self.save_current_desk()`.

No separate "remove from Desk" bookkeeping is needed beyond the canvas
removal: `DeskWindow._capture_desk_state()` already builds Desk state
freshly from `self.view._frames` at save time, so a frame that's no longer
in that list is automatically excluded from the saved Desk.

## Verification

All of the following are done headlessly — constructing widgets/views
directly, calling their methods, and synthesizing `QMouseEvent`s/injecting
fake confirm callables, the same techniques already used successfully for
this codebase's drag/resize and Desk-switching verification. No step
requires an actual visually-inspected, real interactive window.

1. Confirm a fresh `WidgetFrame` has a `_CloseButton` descendant positioned
   in the titlebar, and that `_hit_test_chrome` returns `(frame, "close")`
   for a point over it (using a real, `show()`n-but-not-visually-inspected
   view so layout geometry is real, same as prior drag/resize tests).
2. Confirm a press-then-release both landing on the close button emits
   `widget_close_requested` with the right frame; a press on the close
   button followed by a release *elsewhere* does not emit it and does not
   start a drag.
3. Confirm `WorkspaceView.remove_widget` removes the frame from `_frames`
   and its proxy from the scene.
4. Confirm `DeskWindow`'s close-request handler, with an injected
   confirm-callable returning `False`, leaves the widget in place; with one
   returning `True`, removes it and calls `save_current_desk` (checked via
   a spy/monkeypatch, not an actual file-system round trip since that's
   already covered by the Desk concept's own verification).
5. Regression: re-run a drag and a resize interaction (per
   `plans/fix-widget-frame-drag-resize.md`/
   `plans/fix-drag-scaling-when-zoomed-out.md`'s existing headless checks)
   to confirm the new close-button branch in `mousePressEvent`/
   `mouseReleaseEvent` doesn't interfere with ordinary titlebar-drag or
   resize-handle interactions.

## Key design decisions / tradeoffs

- **Click handled centrally by `WorkspaceView`, not a real
  `QPushButton.clicked`.** Consistent with every other piece of chrome
  interaction in this codebase (see `design-docs/widget-ux.md`) — one
  interaction model for all chrome, rather than titlebar/resize going
  through `WorkspaceView` while close goes through native Qt signals.
- **`remove_widget` calls `frame.deleteLater()`; `clear_widgets()` (used
  when switching Desks) does not.** This is a deliberate improvement, not
  an inconsistency left in by accident: a widget like the Console widget
  depends on its `destroyed` signal actually firing to clean up its PTY/
  subprocess (see `LEARNINGS.md`), which needs an explicit `deleteLater()`
  in a running event loop. `clear_widgets()`'s existing omission is
  pre-existing behavior out of scope for this change; `remove_widget` gets
  it right from the start since proper single-widget cleanup is directly
  relevant here.
- **No separate Desk-side "remove this widget" bookkeeping.** Desk state
  is already captured fresh from live frames at save time, so removing the
  frame from the canvas is sufficient — adding a parallel data structure to
  track "removed" widgets would be pure duplication.

## Status

Implemented and verified, entirely headlessly (per instruction, anything
needing real-window/visually-inspected testing would have been marked
blocked instead — nothing here did):

1. Confirmed `_hit_test_chrome` returns `(frame, "close")` for a point
   computed from the real, shown-but-not-visually-inspected `_CloseButton`
   widget's own layout geometry.
2. Confirmed a synthetic press+release both landing on the close button
   emits `widget_close_requested(frame)`; a press on the close button
   followed by a release elsewhere emits nothing and leaves no drag state
   behind (`_drag_frame`/`_close_press_frame` both `None` afterward).
3. Confirmed `WorkspaceView.remove_widget` removes the frame from
   `_frames` and detaches its proxy from the scene (`proxy.scene() is
   None` afterward).
4. Confirmed `DeskWindow.close_widget` with an injected `confirm=lambda:
   False` leaves the widget in place, and with `confirm=lambda: True`
   removes it and calls `save_current_desk` (checked via a spy wrapping
   the real method, not a full file-system round trip).
5. Regression: re-ran a synthetic titlebar drag and a right-handle resize
   against a view containing a widget with the new close button present,
   confirmed both still work exactly as before (position/size changed as
   expected, no interference from the new close-button branch).
