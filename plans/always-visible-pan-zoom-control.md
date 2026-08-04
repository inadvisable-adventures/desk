# Make the pan/zoom control always visible (TODO `e4662a5`)

## Summary

`ZoomControl` (`src/desk/shell/zoom_control.py`), the HUD floating over
the Workspace Canvas's lower-right corner, is currently shown only when
the canvas is at non-unity zoom (`WorkspaceView._on_scale_changed`'s
`self.zoom_control.setVisible(abs(self._scale - 1.0) >
SCALE_EPSILON)`), and starts hidden (`.hide()` in `__init__`). This
hides the "Fit"/"100%"/zoom-slider control exactly when it's most
useful for getting oriented (e.g. right after opening a Desk at 100%
zoom, before the user has zoomed at all). This plan makes it always
visible, matching the existing `DeskPicker`/`TempUiNotificationStack`
pattern (`src/desk/shell/canvas.py`), which never hide.

## Affected files

- `src/desk/shell/canvas.py` — remove the hide/show logic.
- `src/desk/shell/zoom_control.py` — update the stale "shown only when
  non-unity zoom" docstring line.
- `tests/verify/` — no existing script references `zoom_control`
  visibility (confirmed via grep), so no fixture to update; new
  coverage added here.

## Design decisions

- **Just remove the visibility toggle entirely**, rather than adding a
  new "always visible" mode alongside the old conditional one — nothing
  else in the codebase needs the conditional behavior, and keeping dead
  branching around would be pure clutter.
- **Keep the existing deferred (`QTimer.singleShot(0, ...)`)
  positioning** in `_position_zoom_control` — that reasoning
  (`resizeEvent`/`scrollContentsBy` drift, per
  `plans/fix-zoom-control-positioning.md` and
  `plans/fix-hover-ui-scroll-zoom-drift.md`) is independent of whether
  the widget is ever hidden, and already matches what `DeskPicker`
  (also always-visible) does. Only the docstring's specific mention of
  "starts hidden and only becomes visible later" needs updating, since
  that's no longer why the first position needs deferring — the
  general "recurring internal Qt layout pass displaces this on every
  resize, including the first one" reasoning (already used by
  `_position_desk_picker`'s docstring) still applies and is what's kept.

## Step-by-step implementation

1. In `WorkspaceView.__init__` (canvas.py), delete
   `self.zoom_control.hide()`.
2. In `_on_scale_changed`, delete the
   `self.zoom_control.setVisible(...)` line entirely (keep
   `self.zoom_control.set_zoom(self._scale)`, which still needs to run
   on every scale change to keep the slider/percent in sync).
3. Remove the now-unused `SCALE_EPSILON` constant if nothing else
   references it (confirm via grep first).
4. Update `_position_zoom_control`'s docstring (drop the
   "starts hidden ... first real visible position isn't confirmed
   correct until that moment" framing; align with
   `_position_desk_picker`'s framing instead).
5. Update `ZoomControl`'s class docstring ("Shown only when the canvas
   is at non-unity zoom" — delete that sentence).
6. New verify coverage (see below).

## Key tradeoffs

- None of substance — this removes a conditional rather than adding
  one, so there's no real tradeoff surface. The one minor UX
  consideration (a small always-on HUD in the corner at 100% zoom,
  where it wasn't visible before) is exactly what was requested.

## Verification

New script `tests/verify/verify_zoom_control_always_visible.py`, real
`WorkspaceView`/`QApplication` (offscreen platform), no mocking:
- A freshly constructed, `.show()`n `WorkspaceView` at its default
  (100%) scale has `zoom_control.isVisible()` true immediately (after
  `app.processEvents()` to let the deferred position/show settle).
- Zooming in and back out to exactly 100% again leaves it visible
  throughout (previously it would have hidden again at exactly 1.0).
- Full `tests/verify/` regression suite.
