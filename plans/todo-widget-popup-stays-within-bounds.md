# Restrict the TODO widget's add/edit popup to its own widget bounds (COMPLETED)

TODO `10b0321`.

## Summary

"in the TODO widget, please change the pop-up item adder/editor so that
it is restricted to remain visually within the TODO widget itself."

`_ItemDialog` (the add/edit popup, `widgets/todo/widget.py`) is a real,
separate, frameless top-level OS window (`Qt.WindowType.Tool |
FramelessWindowHint`), positioned today via `dialog.move(button
.mapToGlobal(button.rect().bottomLeft()))` /
`dialog.move(self._list.viewport().mapToGlobal(rect.bottomLeft()))` --
with no clamping at all, so it can currently render past the TODO
widget's own edges (overlapping other widgets on the canvas, or past
the screen edge) whenever the triggering button/list row is near the
widget's own boundary. Fix: compute the TODO widget's own current
on-screen bounding rect and clamp the popup's position (and, if
necessary, size) to stay inside it.

## Investigation

The obvious-looking approach -- `self.mapToGlobal(QPoint(0, 0))` /
`self.mapToGlobal(QPoint(width, height))` on the TODO widget itself --
was tried first and confirmed **wrong** before writing any of the
actual fix: built a real `WorkspaceView`, embedded a widget (mirroring
`WidgetFrame` -> `PythonWidgetHost` -> the actual built widget's real
nesting depth), placed it at scene position `(100, 50)`, then zoomed
the view 2x. The deeply-nested widget's own `mapToGlobal(0, 0)` /
`mapToGlobal(width, height)` reported a rect offset by exactly
`(-100, -50)` from the actual, correct on-screen rect (computed
independently via the `QGraphicsProxyWidget`/`QGraphicsView` chain
below) -- i.e. it silently ignored the widget's placed *position* in
the scene while still reporting the right *size* (correctly zoom
-scaled). This is the same general category `LEARNINGS.md` already
documents for *live mouse events* delivered into a
`QGraphicsProxyWidget`-embedded widget under zoom ("don't reliably
reflect real screen coordinates") -- confirming here that the *static*
`mapToGlobal()` geometry API has the analogous problem, not just event
coordinates.

The reliable alternative, confirmed against the same real setup: go
through the enclosing proxy/view explicitly, the same way
`LEARNINGS.md`'s very first entry already establishes for finding the
enclosing proxy at all (`self.window().graphicsProxyWidget()`, since a
proxy-embedded widget's own `graphicsProxyWidget()` is `None` -- only
the exact widget passed to `scene.addWidget()` has a real one):

```
window = self.window()                          # the WidgetFrame
proxy = window.graphicsProxyWidget()             # real QGraphicsProxyWidget
view = proxy.scene().views()[0]                  # the one WorkspaceView
top_left = self.mapTo(window, QPoint(0, 0))       # local -> window-local
scene_pt = proxy.mapToScene(QPointF(top_left))    # window-local -> scene
global_pt = view.viewport().mapToGlobal(view.mapFromScene(scene_pt))  # scene -> screen
```

This produced the correct rect in the real test (matching the widget's
actual placed position, correctly zoom-scaled), and is what the fix
uses.

## Key decisions

- **Clamp position, and cap size as a fallback, not just position.**
  Normally the widget is comfortably larger than the popup's default
  420x220 (`DEFAULT_WIDGET_SIZE` is 680x520), so position-clamping alone
  handles the common case. But `MIN_WIDTH`/`MIN_HEIGHT` (200x120) is
  *smaller* than the popup's default size, so a widget resized down to
  its minimum needs the popup capped to fit too, not just repositioned
  -- otherwise "restricted to remain visually within" wouldn't actually
  hold in that case. Capped via a plain `resize()`; `_field`'s own
  `setMinimumSize(400, 160)` still applies underneath, so an especially
  tiny widget just gets the popup at its own practical minimum rather
  than crashing or laying out incorrectly.
- **Clamp is computed fresh every time the popup is shown** (not cached)
  -- the widget's on-screen rect changes with every pan/zoom/resize/
  move, and the popup is only ever shown in response to a fresh click,
  so there's no staleness concern to guard against.
- **Falls back to the old, unclamped behavior if not actually embedded**
  (`graphicsProxyWidget()`/`views()` come back empty -- e.g. a widget
  constructed directly in a unit test with no real canvas) -- clamping
  to nothing would be worse than not clamping at all.
- **Only affects the add/edit popup's own positioning code** -- no
  changes to `_ItemDialog` itself, the Scratch-widget edit-conflict path
  (TODO d25e557), or anything else that opens a different top-level
  window.

## Affected files

- `widgets/todo/widget.py` -- new `_own_screen_rect()` helper; new
  clamping logic used by both `_show_add_dialog` and
  `_show_edit_dialog` in place of their current unclamped `dialog
  .move(...)` calls.
- `LEARNINGS.md` -- an entry recording that `QWidget.mapToGlobal()`
  itself (not just live mouse events) is unreliable for a
  `QGraphicsProxyWidget`-embedded widget under a non-unity view
  transform, and the working alternative.

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication`, no mocks):

- The `mapToGlobal`-is-wrong finding above, reproduced directly (kept
  as a standalone check, not just narrative).
- A real `TodoWidget` placed via a real `WorkspaceView.add_widget` (the
  actual `WidgetFrame` -> `PythonWidgetHost` -> `TodoWidget` nesting,
  not a stand-in), the view zoomed to a non-unity scale: triggering
  `_show_add_dialog` with the Add button positioned such that the
  naive/old computation would have placed the popup outside the
  widget's own bounds -- confirm the shown popup's actual geometry
  (`dialog.geometry()`) is fully contained within `_own_screen_rect()`.
- Same for `_show_edit_dialog` with a list row near the widget's bottom
  edge.
- A widget resized down near `MIN_WIDTH`/`MIN_HEIGHT`: confirm the
  popup is capped to fit (or as close as `_field`'s own minimum size
  allows) rather than overflowing.
- Not embedded (widget constructed directly, no canvas): confirm the
  old, unclamped behavior still works without raising (the fallback
  path).

## Status

Implemented as planned: `_resolve_view_and_proxy`, `_screen_point`,
`_screen_rect`, and `_position_dialog` added to `TodoWidget`;
`_show_add_dialog`/`_show_edit_dialog` now call `_position_dialog`
instead of their old, unclamped `dialog.move(widget.mapToGlobal(...))`.

All headless verification steps above passed, against a real
`WorkspaceView`/`PythonWidgetHost`/`TodoWidget` embedding (not a
stand-in): the popup's shown geometry is fully contained within
`_screen_rect(self)` at a non-unity zoom for both the add and edit
paths; a widget resized down to `MIN_WIDTH`/`MIN_HEIGHT` gets the
popup capped down from its default 420x220 rather than overflowing;
constructing a bare `TodoWidget` with no canvas at all still shows the
popup without raising (the fallback path). Also kept the
`mapToGlobal`-is-wrong finding itself as its own standalone
verification step, not just narrative.

Added a `LEARNINGS.md` entry for the `mapToGlobal()` finding (a real,
non-obvious, easy-to-repeat mistake -- the "obvious" approach was tried
first and was wrong), and corrected a now-stale cross-reference in the
adjacent "uncaught exception escaping a Qt slot" entry (TODO 95f7ce9
is implemented now, no longer "not-yet-implemented").
