# Bring-to-front / send-to-back titlebar buttons (COMPLETED)

TODO `cdf45cb`.

## Summary

"Add 'bring to front' and 'send to back' buttons to the top-right of
widgets, left of the 'x' button, which move it in visual z-order to the
front or back, respectively."

Two new purely-visual titlebar buttons (`▲`/`▼`), positioned left of
the existing close button, following the exact same established
"chrome button" pattern the close button already uses (visual-only
widget, real click handling done centrally by `WorkspaceView`'s own
mouse press/release + `_hit_test_chrome`, since embedded-widget mouse
events don't reliably reflect real screen coordinates under zoom — see
`design-docs/widget-ux.md`). Clicking one calls a new
`WorkspaceView.bring_to_front`/`send_to_back`, which sets the widget's
`QGraphicsProxyWidget.setZValue()` above the current max (front) or
below the current min (back) among all placed frames.

## Key decisions

- **Reuse and generalize the close button's exact mechanism, not a
  parallel one.** Today's `_CloseButton` is genuinely just a glyph
  label with fixed styling/sizing; factored out a shared `_TitlebarButton
  (glyph)` base class it and the two new buttons both use, so there's
  one implementation of "constant-screen-size glyph button,
  counter-scaled the same way as the rest of the chrome."
  `WorkspaceView`'s own `_close_press_frame: WidgetFrame | None`
  generalizes to `_button_press: tuple[WidgetFrame, str] | None`
  (frame, one of `"close"`/`"bring_to_front"`/`"send_to_back"`) --
  same press-then-release-on-the-same-button click semantics (a
  press-then-drag-away is a cancelled click, matching normal button
  behavior), just no longer hardcoded to one specific button kind.
- **Z-order via `QGraphicsProxyWidget.setZValue()`**, the standard Qt
  mechanism for `QGraphicsScene` stacking order (also determines which
  item wins an overlapping click, not just paint order — exactly what
  "visual z-order" means here). `WorkspaceView` already tracks every
  placed frame (`self._frames`), so "front"/"back" are computed as
  `max(...) + 1` / `min(...) - 1` across all currently-placed frames'
  current z-values, not fixed constants -- so repeated clicks keep
  working correctly (e.g. bring-to-front twice in a row on two
  different widgets both end up on top, in the order clicked).
- **Session-only, not persisted across a Desk save/reload.** `WidgetState`
  has no z-order field today (stacking is implicit insertion order), and
  the TODO's own wording doesn't ask for persistence. Adding a persisted
  z-value is a bigger, separate decision (interacts with `WidgetState`'s
  schema, migration of already-saved `.desk` files, and the not-yet
  -built general "widget-local storage" question, TODO fb76057) that
  isn't warranted by what was actually asked -- not pursued here.
- **Button order in the titlebar layout**: `[title] [stretch]
  [bring-to-front ▲] [send-to-back ▼] [close ✕]` -- "respectively"
  in the TODO's own wording pairs bring-to-front with "front" (listed
  first) and send-to-back with "back" (listed second), and both sit
  left of the existing close button as asked.
- **Plain Unicode glyphs (`▲`/`▼`), not emoji** -- matches the existing
  close button's plain `✕` glyph precedent, not a new visual register.

## Affected files

- `src/desk/shell/widget_frame.py` -- `_TitlebarButton` (glyph) base
  class factored out of `_CloseButton`; new `_BringToFrontButton`/
  `_SendToBackButton`; `_TitleBar` lays out both, left of the close
  button.
- `src/desk/shell/canvas.py` -- `_close_press_frame` generalized to
  `_button_press`; `_hit_test_chrome` recognizes the two new button
  types; `mousePressEvent`/`mouseReleaseEvent` handle all three button
  kinds uniformly; new `bring_to_front`/`send_to_back` methods.
- `design-docs/widget-ux.md` -- "Close Button" section's description of
  the press/release mechanism updated to describe the now-generalized
  `_button_press` covering three buttons, not one; new short section
  for the two new buttons and the z-order semantics.

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication`, real
`WorkspaceView`, no mocks):

- Placing three widgets, clicking the middle one's bring-to-front:
  confirm its proxy's `zValue()` is now the highest of the three.
- Clicking a widget's send-to-back: confirm its `zValue()` is now the
  lowest.
- Repeated bring-to-front on two different widgets in sequence: confirm
  the *second* one clicked ends up with the higher `zValue()` (not a
  fixed value both would tie at).
- Press-then-drag-away-then-release (matching the close button's
  existing cancelled-click semantics): confirm the button click does
  *not* fire when the release lands off the button.
- The existing close button and drag/resize handles still work
  unaffected by the `_button_press` generalization (a quick regression
  check, not a new feature).

## Status

Implemented as planned: `_TitlebarButton` factored out of `_CloseButton`
in `widget_frame.py`, with `_BringToFrontButton`/`_SendToBackButton`
added alongside it and laid out left of the close button;
`WorkspaceView._close_press_frame` generalized to `_button_press`,
`_hit_test_chrome` recognizes both new button types, and
`bring_to_front`/`send_to_back` compute against the live max/min
`zValue()` across all placed frames.

All headless verification steps above passed against a real
`WorkspaceView` with real placed frames: bring-to-front/send-to-back
set the correct highest/lowest `zValue()`; repeated bring-to-front on
different widgets stacks correctly rather than tying; a real simulated
button click (synthetic `QMouseEvent` press+release routed through
`WorkspaceView`'s actual `mousePressEvent`/`mouseReleaseEvent`, not a
direct method call) works end-to-end for the new buttons; the
pre-existing close button still fires `widget_close_requested`
correctly after the `_button_press` generalization; a press-then
-release-elsewhere is still a cancelled click, not a mis-fire.

Updated `design-docs/widget-ux.md`'s "Close Button" section to
describe the generalized `_button_press` mechanism, and added a new
"Bring to Front / Send to Back Buttons" section.

No `LEARNINGS.md` entry needed -- this closely followed an existing,
well-documented pattern (the close button's own mechanism).
