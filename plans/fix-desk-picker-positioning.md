# Fix Desk picker positioning (COMPLETED)

## Summary

Confirmed directly: the Desk picker (top-left HUD, item 13) is
positioned via a single `.move(DESK_PICKER_MARGIN, DESK_PICKER_MARGIN)`
call in `WorkspaceView.__init__`, and nothing repositions it afterward.
Empirically, its position silently drifts from the intended `(12, 12)`
to some other point (`(192, 122)` in one concrete run) at the moment the
view is first `.show()`n — some one-time internal Qt layout/geometry
pass (most likely related to `QGraphicsView`'s lazy viewport/scrollbar
setup, which only finalizes once the widget is actually shown) displaces
a manually-`.move()`d, non-layout-managed child widget. Re-asserting the
position afterward (calling `.move(12, 12)` again post-show) sticks
permanently and survives further resizes — the displacement is a single
event around first-show, not a continuous drift.

`ZoomControl` (the equivalent bottom-right HUD, item 11) doesn't exhibit
this bug because it already repositions itself on every `resizeEvent`
(`_position_zoom_control()`, needed there regardless, since a
bottom-right anchor's absolute pixel position depends on the viewport's
current width/height) — which incidentally also reasserts its position
past whatever one-time internal displacement affects the Desk picker.
The Desk picker's top-left anchor is a constant offset regardless of
viewport size, so nothing ever forced the same "reassert on resize"
treatment.

## Affected files

- `src/desk/shell/canvas.py` (edit) — reposition the Desk picker in
  `resizeEvent`, mirroring `ZoomControl`'s existing pattern.

## Design

Add `_position_desk_picker()` (trivial: always `(DESK_PICKER_MARGIN,
DESK_PICKER_MARGIN)`, since top-left anchoring doesn't depend on
viewport size) and call it both in `__init__` (as today) and in
`resizeEvent`, alongside the existing `_position_zoom_control()` call.

A first version of this fix called `.move(12, 12)` *synchronously* at the
end of `resizeEvent` — this fixed the *first*-show displacement, but a
follow-up test showed a *second* explicit `.resize()` on the view still
displaced the picker afterward, meaning the internal Qt pass causing this
isn't a one-time first-show-only event as initially assumed; it recurs on
every resize, and — critically — runs as a *separate, later* queued
layout pass within the same event-loop iteration, so a synchronous
reassertion at the end of `resizeEvent` itself was still getting
overwritten immediately after. Fixed by deferring the reassertion via
`QTimer.singleShot(0, lambda: self.desk_picker.move(...))`, scheduling it
to run after anything else queued during that same iteration — confirmed
this sticks correctly across first show, subsequent resizes, and a real
Desk switch.

Not investigated further: the *exact* Qt-internal mechanism causing the
displacement (plausibly `QAbstractScrollArea`/`QGraphicsView`'s lazy
scrollbar/viewport geometry finalization — confirmed scrollbars are
present given the workspace's effectively-infinite scene rect). Not
necessary to pin down the exact internal cause when deferred reassertion
is a simple, robust fix that doesn't depend on knowing why the
displacement happens.

## Verification

Entirely headless: construct a real `WorkspaceView`, `.show()` it, confirm
the Desk picker's position without the fix drifts away from `(12, 12)`
(reproducing the bug directly, not just trusting the report); apply the
fix and confirm it stays at `(12, 12)` after `.show()`, after further
resizes, and after a real Desk switch (`clear_widgets()`/
`set_view_state()` cycle) — matching the TODO item's specific concern
about the picker moving/disappearing "when the Desk changes."

## Key design decisions / tradeoffs

- **Defer the reassertion via `QTimer.singleShot(0, ...)` rather than
  reasserting synchronously inline in `resizeEvent`.** Confirmed directly
  that a synchronous reassertion isn't late enough — Qt's own displacing
  layout pass runs as a separate, later queued event within the same
  iteration. Scheduling this fix to run after that is what actually
  makes it stick, rather than tracking down and specifically
  countermanding whatever internal mechanism causes the displacement.

## Status

Implemented and verified headlessly:

1. Reproduced the bug directly against the unfixed code (picker drifted
   from `(12, 12)` to a different point on first `.show()`).
2. A first fix attempt (synchronous `.move()` at the end of
   `resizeEvent`) fixed first-show but was shown, via a follow-up test
   resizing the view a second time, to still let the picker drift again —
   corrected to the deferred `QTimer.singleShot(0, ...)` version described
   above.
3. Confirmed the corrected fix: picker stays at `(12, 12)` after first
   show, after a subsequent resize, in a real `DeskWindow`, and after a
   real Desk switch (`switch_desk`, which internally exercises
   `clear_widgets()`/`set_view_state()`) — directly matching the TODO
   item's stated concern.
4. Regression: confirmed `ZoomControl`'s own bottom-right positioning on
   resize is unaffected by this change.
