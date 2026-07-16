# Plan: TODO 86ba292 (COMPLETED) — accept wheel events forwarded to a widget, so ignored ones can't fall through to canvas pan/zoom

## Summary

Found while reading back the Event Recorder widget's second real
recording (after TODO `78bfa41`): a continuous two-finger scroll over
the widget produced only 2 zero-delta Wheel events before the *whole
Desk* started panning/zooming. The user separately confirmed the same
class of bug independently: scrolling a real scrollable widget past
the end of its scroll direction causes the whole Desk to scroll too —
"it seems like it is letting the events pass through since they can't
do anything with them."

Root cause: `WorkspaceView.wheelEvent`'s widget-forwarding branch
(`canvas.py:652-682`) never calls `event.accept()`. If the widget under
the cursor ignores the event — which any scroll area does once already
at its scroll limit, and any non-scrollable widget (e.g. Event
Recorder's recording surface) does unconditionally — the event is left
unaccepted, and Qt propagates it further out. The existing
`_forwarding_wheel` re-entrancy guard (added for `QWebEngineView`
bouncing an unconsumed wheel event back to its parent chain) already
shows this bounce-back mechanism isn't Chromium-specific — it's
`QGraphicsProxyWidget`'s general behavior for any embedded widget that
ignores a wheel event. TODO `78bfa41`'s policy is "a widget under the
cursor always wins, full stop" — an unaccepted event contradicts that
by letting the canvas have a second bite.

## Design

In `canvas.py`'s `wheelEvent`, once `_frame_at` confirms a widget owns
this event, accept it unconditionally before returning — in both the
re-entrant bounce-back early-return (`if self._forwarding_wheel:
return`) and after the normal forwarding call (`super().wheelEvent(event)`
... `return`). This doesn't change whether the widget itself can act on
the event (that's determined by `super().wheelEvent(event)`'s normal
dispatch, unchanged) — it only stops an *ignored* event from leaking
past `WorkspaceView` to whatever's beneath/around it once we've already
decided it belongs to the widget under the cursor.

## Verification

- New test in `tests/verify/verify_widget_content_event_priority.py`:
  embed a real `QScrollArea` already scrolled to its vertical maximum,
  send a real `QWheelEvent` with a downward (further-scrolling) delta
  at a position over it, and assert the event `isAccepted()` after
  `view.wheelEvent(event)` returns — before the fix this is `False`
  (the scroll area ignores it, having nothing left to scroll), after
  the fix it's `True`.
- Confirm existing wheel/pinch/click-drag tests in the same file are
  unaffected (`git stash` before/after).
- Full `tests/verify/` regression suite.
