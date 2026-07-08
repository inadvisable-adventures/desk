# TODO widget list scrolling (TODO 8394e40) (COMPLETED)

## Summary

TODO 8394e40: "The TODO widget list should be scrollable (in a way that
doesn't get accidentally captured by Desk scrolling)."

`widgets/todo/widget.py`'s `QListWidget` is already a scrollable
`QAbstractScrollArea` subclass and would scroll its contents on a mouse
wheel / two-finger trackpad scroll exactly like any other Qt list — if it
ever received that event. It doesn't: `WorkspaceView.wheelEvent`
(`src/desk/shell/canvas.py`) unconditionally treats *every* wheel event
delivered to the view as a Workspace Canvas zoom gesture (see
`design-docs/widget-ux.md`'s "Trackpad Zoom Input" section) and never
forwards it to whatever is under the cursor. So today, scrolling over the
TODO widget's item list always zooms the whole canvas instead of
scrolling the list — the "accidentally captured by Desk scrolling"
symptom the item describes.

This isn't TODO-widget-specific: it's a gap in `WorkspaceView`'s wheel
handling that affects *any* widget with scrollable content (the one
concrete case today is the TODO list, but e.g. a future scrollable log
viewer would hit the identical bug). Fix it once, generically, in
`WorkspaceView`.

## Root cause

`WorkspaceView.wheelEvent` fully overrides `QGraphicsView.wheelEvent`
(computing a zoom factor from the delta and returning) without ever
calling `super().wheelEvent(event)` or otherwise checking what's under
the cursor. `QGraphicsView`'s default `wheelEvent` is what forwards wheel
events into the scene, where a `QGraphicsProxyWidget` under the cursor
delivers them to its embedded real `QWidget` (e.g. the TODO widget's
`QListWidget`) for native scrolling. Since that default path is never
reached, embedded scrollable widgets never see wheel events at all.

## Design

Mirror the existing `_hit_test_chrome` hit-testing pattern (same file):
before computing a zoom factor, hit-test the view position under the
cursor. If it lands inside a `QGraphicsProxyWidget`-embedded child that is
(or is inside) a `QAbstractScrollArea` — which is what every scrollable
Qt widget (`QListWidget`, `QScrollArea`, `QTextEdit`, etc.) is built on —
forward the event via `super().wheelEvent(event)` (letting Qt's normal
scene-forwarding deliver it to that widget for scrolling) instead of
zooming the canvas. Otherwise, keep today's zoom behavior unchanged.

This only affects wheel events whose cursor position is directly over a
scrollable widget's content; the two-finger-scroll-to-zoom and pinch-to
-zoom behavior described in `design-docs/widget-ux.md` is otherwise
unchanged everywhere else on the canvas (background, non-scrollable
widget content, chrome).

## Affected files

- `src/desk/shell/canvas.py` (edit) — add a `_scrollable_at(view_pos)`
  helper (same hit-testing shape as `_hit_test_chrome`: `itemAt` →
  confirm `QGraphicsProxyWidget` → map to the embedded frame's local
  point → `childAt` → walk `parentWidget()` looking for a
  `QAbstractScrollArea`); `wheelEvent` calls it first and forwards to
  `super().wheelEvent(event)` on a hit instead of zooming.
- `design-docs/widget-ux.md` (edit) — note the carve-out in "Trackpad
  Zoom Input": wheel/two-finger-scroll over a widget's scrollable content
  scrolls that content instead of zooming the canvas; pinch-to-zoom
  (`NativeGestureEvent`) is unaffected since it's handled separately in
  `event()`, not `wheelEvent`.

## Verification

Headless, via `QTest`/synthetic `QWheelEvent`s against a real
`WorkspaceView` (same style as the existing zoom/drag regression checks
in this codebase):

1. Place a widget wrapping a `QListWidget` with enough rows to need
   scrolling on the canvas; synthesize a wheel event with the cursor over
   the list's viewport — confirm the list's scrollbar position changes
   and the canvas's own zoom scale does *not* change.
2. Synthesize a wheel event with the cursor over empty canvas background
   (or non-scrollable widget content) — confirm the canvas zoom scale
   *does* change as before (no regression to existing zoom behavior).
3. Regression: confirm titlebar drag and resize-handle hit-testing
   (`_hit_test_chrome`) are unaffected.

No step requires real trackpad hardware or a visible window — this is
pure hit-testing/event-routing logic, same shape as `_hit_test_chrome`
which was already verified this way.
