# Fix zoom control positioning (COMPLETED)

## Summary

Confirmed directly: the zoom control has the exact same underlying bug
`plans/fix-desk-picker-positioning.md` already found and fixed for the
Desk picker — a recurring internal Qt layout pass (plausibly
`QGraphicsView`'s own scrollbar/viewport geometry recalculation)
silently displaces a manually-positioned, non-layout-managed child
widget. `ZoomControl` starts hidden (`.hide()` right after construction)
and only becomes visible later, the first time the canvas zooms away
from 1.0× — so its *first real visible position* isn't confirmed correct
until that moment, not at the view's own first `.show()`. Confirmed
empirically: after resizing (while still hidden) and then triggering the
first zoom action, the control appears at a stale position (`(999,
774)`) rather than the freshly-computed correct one (`(819, 664)`) —
this is why the earlier Desk-picker investigation's zoom-control check
(which zoomed *before* resizing, masking the same bug behind a
subsequent correct resize-triggered reposition) didn't catch it.

## Affected files

- `src/desk/shell/canvas.py` (edit) — same fix shape as
  `_position_desk_picker`.

## Design

Defer `_position_zoom_control`'s reassertion via
`QTimer.singleShot(0, ...)`, exactly like `_position_desk_picker` — the
displacing Qt pass runs as a separate, later-queued layout event within
the same event-loop iteration, so a synchronous reassertion isn't late
enough (confirmed for the Desk picker; not re-litigated here, same
mechanism).

## Verification

Headless: reproduced the bug directly (resize while hidden, then trigger
the first zoom action, confirm the position was stale before the fix —
`(999, 774)` instead of the correct `(819, 664)`); applied the fix and
confirmed the control is positioned correctly at the moment it first
becomes visible, remains correct across a further resize, and correctly
hides again at unity zoom. Regression: confirmed the Desk picker's own
positioning and titlebar drag interaction are unaffected.

## Key design decisions / tradeoffs

- **Same fix as the Desk picker, not a new investigation.** The
  confirmed root cause and working fix are identical; no value in
  re-deriving it from scratch.
