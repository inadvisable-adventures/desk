# Double-click empty canvas to create a focused Scratch (TODO `496d685`)

## Summary

`WorkspaceView` (`src/desk/shell/canvas.py`) has no
`mouseDoubleClickEvent` override at all — a double-click on empty
canvas today is a no-op at the canvas level (falls through to Qt's
default `QGraphicsView` handling). This adds one: double-clicking
truly empty canvas (not a placed widget's own content, not a widget's
chrome, and — automatically, since they're plain child widgets on top
of the viewport that intercept the event themselves — not any of the
pinned hovering UI, including the new lower-left Scratch button from
TODO `945b086`) places a new Scratch widget with its top-left corner
at the double-click point and focuses its body, so typed characters
start landing right where the double-click was.

## Affected files

- `src/desk/shell/canvas.py` — new `mouseDoubleClickEvent` override,
  new `empty_canvas_double_clicked` signal.
- `src/desk/shell/window.py` — connect the signal to
  `DeskWindow._open_focused_scratch` (built by TODO `945b086` — this
  item depends on that one landing first).
- `tests/verify/` — new coverage.

## Design decisions

- **Reuses `_hit_test_chrome`/`_frame_at`**, the exact same two checks
  `mousePressEvent`/`wheelEvent`/`contextMenuEvent`/the native-gesture
  handler in `event()` already use to distinguish "over some placed
  widget" (chrome or content) from "truly empty canvas" (TODO
  `3846190`/TODO `78bfa41`'s established precedent — "a widget under
  the cursor always wins, full stop"). Both returning `None` is what
  "empty canvas" means here too, for consistency with every other
  canvas-level interaction.
- **Only left-button double-clicks are handled**; anything else (and
  any double-click that *does* land on chrome or a frame) calls
  `super().mouseDoubleClickEvent(event)` — preserving today's existing
  behavior exactly for every case this doesn't touch, e.g. the
  Scratch widget's own label double-click-to-edit
  (`widgets/scratch/widget.py`'s `_DisplayLabel`) still works
  unchanged, since that double-click lands on a frame and is forwarded
  via `super()`, which delivers it into the embedded content the same
  way it always has.
- **No explicit exclusion check for the pinned HUD widgets** (Desk
  picker, zoom control, notifications, new Scratch button) — confirmed
  via how Qt delivers mouse events that these are all real, opaque
  child widgets of `self.viewport()` sitting on top of the graphics
  scene, so a double-click physically inside one of them is delivered
  directly to that widget (whichever one is topmost under the
  cursor), never to `WorkspaceView.mouseDoubleClickEvent` at all — the
  same reason `_hit_test_chrome`/`_frame_at` never need to special
  -case them either. Verified directly in this item's own coverage
  (see below), not just asserted.
- **Placement uses the double-click's scene position as the widget's
  top-left corner** (`open_widget_content(..., pos=(scene_x,
  scene_y))`), not centered on it — `QGraphicsProxyWidget.setPos`
  already treats `pos` as top-left everywhere else in this codebase
  (`add_widget`, `_on_widget_add_requested`'s widget-spawn-menu path),
  and a Scratch's body text starts at its own top-left, so this is the
  closest available approximation of "typed characters land directly
  starting where the double-click was" without needing pixel-level
  text-cursor placement math.
- **Depends on TODO `945b086`'s `_open_focused_scratch` helper** —
  implemented there first; this item just adds a second caller with a
  real `pos` instead of `None`.

## Step-by-step implementation

1. `canvas.py`: add `empty_canvas_double_clicked = pyqtSignal(QPointF)`
   near the other signals.
2. Add `mouseDoubleClickEvent(self, event)`: if
   `event.button() == Qt.MouseButton.LeftButton` and both
   `self._hit_test_chrome(event.position())` and
   `self._frame_at(event.position())` are `None`, compute
   `scene_pos = self.mapToScene(event.position().toPoint())`,
   `event.accept()`, emit `self.empty_canvas_double_clicked.emit(scene_pos)`,
   return. Otherwise `super().mouseDoubleClickEvent(event)`.
3. `window.py`: connect
   `self.view.empty_canvas_double_clicked.connect(self._on_empty_canvas_double_clicked)`
   near the other `self.view.*.connect(...)` calls. Add
   `_on_empty_canvas_double_clicked(self, scene_pos: QPointF) ->
   None`: calls `self._open_focused_scratch((scene_pos.x(),
   scene_pos.y()))`.
4. New verify coverage (see below); run the full `tests/verify/` suite.

## Key tradeoffs

- Placing the widget's top-left (not center) at the click point means
  a double-click near the bottom or right edge of the visible viewport
  can place most of the new Scratch off-screen (same edge behavior the
  existing widget-spawn-menu/drop-file placement already has at
  `pos=(scene_pos.x(), scene_pos.y())` — not a new problem introduced
  here, not fixed here either).
- No debounce/guard against an accidental double-click while, e.g.,
  panning — matches existing canvas interactions, which don't guard
  against this either.

## Verification

New script `tests/verify/verify_double_click_empty_canvas_scratch.py`,
real `WorkspaceView` + `_FakeWindow` (same recipe as TODO `945b086`'s
plan), no mocking, real `QMouseEvent`s (matching
`verify_lock_widgets.py`'s existing real-`QMouseEvent` pattern):
- Double-clicking truly empty canvas places a new Scratch widget frame
  at (approximately) the click's scene position, with its body
  focused.
- Double-clicking on top of an existing placed widget's content does
  *not* create a Scratch (falls through to normal behavior).
- Double-clicking the Scratch widget's own title label still enters
  its inline-rename edit mode unchanged (regression check for the
  `super()`-forwarding path).
- Double-clicking on top of the lower-left new-Scratch HUD button
  (TODO `945b086`) does not create a *second* extra Scratch from the
  canvas-level handler (only the button's own single-click behavior
  fires) — confirms the "no explicit exclusion needed" design
  decision above empirically, not just by assertion.
- Full `tests/verify/` regression suite.
