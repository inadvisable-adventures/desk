# Fix widget stacking on the canvas (TODO `d0a4c7b`) (COMPLETED)

## Summary
(1) `WorkspaceView.add_widget` never set the new proxy's z-value, so a freshly
placed widget could land behind others. (2) The chrome eye/greeked click only
zoomed, which can center a widget that is still hidden behind another.

## Affected files
`src/desk/shell/canvas.py`, `tests/verify/verify_canvas_widget_stacking.py`,
`TODO.md`.

## Design
- `add_widget` calls `bring_to_front(frame)` right after appending the frame.
  `bring_to_front` is relative (max existing z + 1), so restoring a saved desk
  keeps its load order stacking (later-restored on top), unchanged in effect
  from today's implicit scene insertion order.
- The `("eye", "greeked")` release branch calls `bring_to_front(frame)` before
  `zoom_to_widget(frame)`. The Event Subscribers / Claude (Desk) Status eye
  buttons go through `DeskWindow.zoom_to_widget_by_instance_id`, a separate
  path that still only zooms (the "zoom doesn't raise" wrinkle noted in TODO
  `a7d7c0a`); left for a follow-up so this item stays scoped to the two call
  sites it names.

## Verification
A real `WorkspaceView`: a fresh widget outranks existing ones; simulated chrome
release for the eye/greeked kinds raises a buried widget; other chrome kinds
are unaffected.
