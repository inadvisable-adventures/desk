# Plan: TODO 78bfa41 (COMPLETED) — scroll/zoom events always go to the widget under the cursor

## Summary

Follow-up to TODO `3846190`. That fix made wheel-scroll and pinch-zoom
skip canvas-zooming only when the cursor was over a *scrollable*
widget (`_scrollable_at`: `QAbstractScrollArea`/`QWebEngineView`) —
deliberately still zooming the canvas over a non-scrollable widget
(e.g. a plain image viewer), to keep pinch consistent with wheel's own
pre-existing behavior.

Explicit user decision, overriding that default: broaden this to *any*
placed widget under the cursor, not just scrollable ones — "I care
more about active widgets getting the events" than canvas zoom/pan
staying conveniently reachable everywhere. This also happens to close
the exact blind spot found while reading back the Event Recorder
widget's first real recording (`.desk_temp/recorder.temp.md`'s task):
its own recording surface is a plain, non-scroll-area `QWidget`, so
under the old policy it could never see a real Wheel event no matter
what — this fix means it now can.

## Design

`_frame_at` (added by TODO `3846190` for the click-drag fix, and
already the gate `contextMenuEvent` uses) is already the broadest
"is there any placed widget under the cursor" check. Reuse it in the
two remaining places still gated on the narrower `_scrollable_at`:

- `wheelEvent`: `if self._scrollable_at(event.position()):` →
  `if self._frame_at(event.position()) is not None:`. Forwarding
  mechanics (`super().wheelEvent(event)`, the `_forwarding_wheel`
  re-entrancy guard for `QWebEngineView`'s own wheel-bounce-back) are
  unchanged — only the *gate* deciding whether to forward at all
  changes. A widget that doesn't itself handle wheel (most of them,
  today) simply does nothing with it — the point is the canvas no
  longer zooms out from under it either.
- `event()`'s `NativeGesture`/pinch handling: same swap. No widget
  implements its own pinch handling today, so "sent to the widget" in
  practice still just means "the canvas doesn't steal it" for pinch
  specifically — genuinely forwarding a native gesture event into an
  arbitrary embedded widget isn't something `QGraphicsProxyWidget`
  does for free the way wheel/mouse events already get; not attempted
  here since nothing would receive it yet.

`_scrollable_at` becomes dead code once both call sites move off it —
delete it rather than leave it unused.

## Docs

- `design-docs/widget-ux.md`'s "Trackpad Zoom Input" section: rewrite
  to describe the new, broader policy (any widget content, not just
  scrollable) and drop the `_scrollable_at` reference.
- `PARKINGLOT.md`'s "Scrolling while hovering over a widget scrolls the
  Desk instead of the widget" item: the wheel-scroll half of this is
  now resolved comprehensively (not just for scroll areas) — reword to
  note that and keep only the still-unbuilt minimap idea parked.

## Verification

- Update `tests/verify/verify_widget_content_event_priority.py`'s
  `test_pinch_over_non_scrollable_widget_still_zooms_canvas` (now
  asserting the *opposite* — pinch over non-scrollable content no
  longer zooms the canvas either) and add the equivalent wheel case
  (wheel over a non-scrollable widget no longer zooms the canvas).
  Empty-canvas cases for both stay unchanged (still zoom/scroll the
  canvas — nothing is under the cursor).
- Re-run `verify_event_recorder_widget.py` to confirm nothing there
  assumed the old policy.
- Full `tests/verify/` regression suite (`git stash` before/after).
