# Fix widget drag/resize scaling when zoomed out (COMPLETED)

## Summary

Confirmed on real trackpad hardware (following up on
`plans/zoom-pan-interaction-fixes.md`'s unresolved open question):
dragging a widget's titlebar or resize handles moves/resizes it too much
for a given cursor movement, specifically when the Workspace Canvas is
zoomed *out*.

## Root cause

`_DragHandle` (the base class behind `_TitleBar`/`_ResizeHandle` in
`src/desk/shell/widget_frame.py`) computes drag deltas from
`event.globalPosition()` read *inside the embedded widget's own
mouseMoveEvent* — i.e., from the `QMouseEvent` that `QGraphicsProxyWidget`
constructs when forwarding a scene-level mouse event down into the titlebar
(or a resize handle), which are themselves embedded widgets living inside
`WidgetFrame`, which is itself embedded in the scene via
`QGraphicsProxyWidget`.

Investigated directly (constructing real `QMouseEvent`s and routing them
through `QApplication.sendEvent()` at the viewport level — the same
technique used successfully in `plans/fix-widget-frame-drag-resize.md`,
extended here to non-unity zoom): at scale=0.5 (zoomed out), a simulated
40×20px cursor drag on the titlebar produced roughly **3.4× too much**
on-screen movement, using the *correct* scene-based coordinate mapping to
locate the click. (An earlier attempt at this same investigation, done for
`plans/zoom-pan-interaction-fixes.md`, tried three different coordinate
sources — `globalPosition()`, `position()`, `scenePosition()` — and got
three different, mutually-inconsistent results across zoom levels, which
was wrongly written off as a testing-environment artifact at the time. It
was not: all three are being read from the *embedded* widget's own event,
which is the actual problem, not which specific field of it is used.)

The fix: don't compute drag deltas inside the embedded chrome widgets'
own mouse events at all. Track the drag centrally in `WorkspaceView`
instead, using **its own** `mousePressEvent`/`mouseMoveEvent`/
`mouseReleaseEvent` — `WorkspaceView` is the actual top-level view widget
receiving events forwarded from its viewport (the standard way
`QGraphicsView` subclasses override mouse handling, exactly like this
class's existing `wheelEvent` already does), not an item embedded via
`QGraphicsProxyWidget` — so its event coordinates are not subject to
whatever recomputation `QGraphicsProxyWidget` does when translating a
scene event into an embedded widget's event.

Concretely: on a left-button press, hit-test whether the click landed on a
`_TitleBar` or `_ResizeHandle` (by finding the topmost
`QGraphicsProxyWidget` at that point, resolving its embedded `WidgetFrame`,
and walking up from `frame.childAt(local_point)` to see if it's inside one
of those two classes). If so, `WorkspaceView` itself owns the whole drag
from then on — computing deltas from its own `event.position()` (divided
by `self._scale`, same math as before) and calling `proxy.moveBy(...)`/
`proxy.resize(...)` directly — instead of the chrome widgets tracking and
reporting the drag themselves. If the click didn't land on chrome, fall
through to `super()` exactly as before (preserves normal content
interaction and background `ScrollHandDrag` panning).

## Affected files

- `src/desk/shell/widget_frame.py` — remove `_DragHandle` and all mouse
  event handling from `_TitleBar`/`_ResizeHandle`; they become plain
  "chrome" widgets (background, cursor shape, `apply_scale`) with no
  interaction logic of their own. `_ResizeHandle.edge` becomes a public
  attribute (was `_edge`) since `WorkspaceView` now needs to read it.
- `src/desk/shell/canvas.py` — `WorkspaceView` gains
  `mousePressEvent`/`mouseMoveEvent`/`mouseReleaseEvent` overrides
  implementing the centralized hit-test + drag/resize tracking described
  above (the resize-math per edge is moved here from
  `_ResizeHandle._on_drag`, unchanged).
- `design-docs/widget-ux.md` — update the
  "Zoom-Correct Dragging"/drag-implementation section to describe the new
  centralized-in-`WorkspaceView` approach and why the embedded-widget
  approach was wrong; resolve the Open Question this plan follows up on.

## Implementation approach

1. `widget_frame.py`: delete `_DragHandle`; `_TitleBar(QWidget)` and
   `_ResizeHandle(QWidget)` keep their `__init__`/`apply_scale` bodies
   unchanged but drop `mousePressEvent`/`mouseMoveEvent`/
   `mouseReleaseEvent`/`_on_drag`/`_view_scale`. Rename `_ResizeHandle
   ._edge` to `.edge` (public — read by `WorkspaceView`'s hit-test).
2. `canvas.py`:
   - Add `self._drag_frame: WidgetFrame | None`, `self._drag_edge: str |
     None`, `self._drag_last_pos: QPointF | None` to `__init__`.
   - `_hit_test_chrome(self, view_pos: QPointF) -> tuple[WidgetFrame, str |
     None] | None`: `item = self.itemAt(view_pos.toPoint())`; if not a
     `QGraphicsProxyWidget` wrapping a `WidgetFrame`, return `None`.
     Otherwise compute `local_point = (self.mapToScene(view_pos.toPoint())
     - item.pos()).toPoint()` (scene units, offset by the proxy's scene
     position — equal to the frame's own local widget coordinates, per the
     established 1-local-pixel-equals-1-scene-unit embedding model), then
     `frame.childAt(local_point)`, walking up `parentWidget()` until
     hitting a `_TitleBar`/`_ResizeHandle` or `None`. Return `(frame,
     None)` for a titlebar hit, `(frame, child.edge)` for a resize-handle
     hit, `None` otherwise.
   - `mousePressEvent`: on left-button press, call `_hit_test_chrome`; if
     it returns something, store it in `self._drag_frame`/`_drag_edge`,
     record `self._drag_last_pos = event.position()`, `event.accept()`,
     return — otherwise `super().mousePressEvent(event)`.
   - `mouseMoveEvent`: if `self._drag_frame` is set, compute `dx, dy =
     (event.position() - self._drag_last_pos) / self._scale`, update
     `self._drag_last_pos`, resolve `proxy =
     self._drag_frame.graphicsProxyWidget()`, and either `proxy.moveBy(dx,
     dy)` (titlebar) or apply the per-edge resize math (moved here from
     the old `_ResizeHandle._on_drag`) — otherwise `super()
     .mouseMoveEvent(event)`.
   - `mouseReleaseEvent`: clear the three `_drag_*` fields if a drag was
     in progress, `event.accept()` — otherwise `super()
     .mouseReleaseEvent(event)`.
3. Update `design-docs/widget-ux.md`.

## Verification

1. Re-run the realistic event-path drag/resize simulation (constructing
   `QMouseEvent`s and sending them to `WorkspaceView`'s **own**
   `mousePressEvent`/`mouseMoveEvent`/`mouseReleaseEvent` this time,
   rather than to embedded chrome widgets) at 0.25×, 0.5×, 1×, 2×, and 4×
   zoom, for both the titlebar (move) and each resize handle (left/right
   /bottom): confirm on-screen movement (`scene_delta * current_scale`)
   matches the simulated screen-pixel delta at **every** tested zoom
   level, including the specifically-reported zoomed-out cases.
2. Confirm clicking/dragging on widget *content* (not chrome) still falls
   through to normal interaction (hit-test returns `None`, `super()` runs)
   — e.g. that a click landing inside the content area doesn't get
   swallowed by the new chrome hit-testing.
3. Confirm background panning (`ScrollHandDrag`, dragging on empty canvas)
   still works — a press that hits neither a proxy nor chrome falls
   through to `super().mousePressEvent(event)` and default `QGraphicsView`
   panning takes over exactly as before.
4. Launch the real app (`python -m desk`); confirm it starts and quits
   cleanly.
5. Actually dragging with a physical trackpad remains the real
   confirmation this plan is following up on — expect the user to verify
   this fix in practice, but the realistic-event-path simulation in step 1
   is a materially stronger check than either of the two previous plans'
   verifications had (neither exercised the *centralized* view-level path
   this fix introduces).

### Status (verification notes)

- Re-ran the realistic event-path simulation (constructing `QMouseEvent`s
  and routing them through `view.viewport()`, exactly the path real
  interaction takes) for the titlebar drag at **five** zoom levels — 0.25×,
  0.5×, 1×, 2×, 4× — after the fix: on-screen movement matched the
  simulated cursor delta (40, 20) to within rounding at every single
  level, including the specifically-reported zoomed-out cases. Before the
  fix, 0.5× alone showed ~3.4× too much movement using the same technique.
- Re-ran the same simulation for all three resize handles (left/right
  /bottom) at the same five zoom levels: all matched the simulated cursor
  delta correctly at every level (initial attempt had a bug in the *test
  script* itself — using a resize handle's own local-rect center instead
  of its position within the frame — corrected and re-verified).
- Confirmed clicking inside a widget's content area, and clicking on empty
  canvas background, both still correctly hit-test to "not chrome" (`None`)
  — normal content interaction and background `ScrollHandDrag` panning are
  unaffected by the new centralized hit-testing.
- Launched the real app (`python -m desk`); it starts and quits cleanly
  with the new centralized drag/resize handling in place.
- Actually dragging with a physical trackpad remains the real, final
  confirmation — the realistic event-path simulation above is a
  meaningfully stronger check than either of the two prior plans had
  (neither exercised `WorkspaceView`'s own centralized event path, since
  it didn't exist until this change), but real-hardware verification is
  still recommended, per usual for interactive UX in this environment.

## Key design decisions / tradeoffs

- **Centralize drag/resize handling in `WorkspaceView`, not the embedded
  chrome widgets.** The chrome widgets' own mouse events go through
  `QGraphicsProxyWidget`'s embedded-widget event translation, which this
  investigation found does not reliably preserve real screen coordinates
  at non-unity view scale. `WorkspaceView` itself is not embedded in
  anything — it's the actual top-level view widget — so its own mouse
  events are ordinary, untranslated widget events, immune to this
  problem. This is a strictly more reliable coordinate source, at the
  cost of `WorkspaceView` needing to hit-test which chrome element (if
  any) a press landed on, rather than each widget knowing this about
  itself.
- **Chrome widgets keep no interaction logic of their own.** They become
  purely visual (background color, cursor shape) once drag/resize moves
  to `WorkspaceView` — simpler, and removes an entire class
  (`_DragHandle`) whose core assumption (that embedded-widget mouse events
  reliably reflect real screen coordinates) turned out to be false.
