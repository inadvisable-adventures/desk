# Widget UX chrome (drag/resize) (COMPLETED)

## Summary

Give every widget on the Workspace Canvas a common interactive frame,
regardless of widget kind (`python` or `html`): a titlebar across the top
that acts as a drag handle, and a frame with resize handles on the left,
right, and bottom edges. Full spec in the new `design-docs/widget-ux.md`
(split out from `design-docs/architecture.md`, which now references it).

This wraps both `PythonWidgetHost` (TODO 8) and `ChromiumWidget` (TODO 5)
uniformly — the chrome is built once, at the canvas-integration layer
(`WorkspaceView.add_widget`), not duplicated per widget kind.

## Affected files

- `design-docs/widget-ux.md` (new) — already written; the authoritative
  spec for this item.
- `design-docs/architecture.md` (edited) — already cross-references the
  new doc from the Workspace Canvas component and the Widget Model section.
- `src/desk/shell/widget_frame.py` (new) — `WidgetFrame(QWidget)` (the
  titlebar + content + resize-handle layout described in `widget-ux.md`),
  plus private `_TitleBar`/`_ResizeHandle`/`_DragHandle` helper classes.
- `src/desk/shell/canvas.py` (edit) — `WorkspaceView.add_widget()` now
  takes a `title` and builds a `WidgetFrame` internally (wrapping the
  passed-in content widget) instead of adding the raw content widget to
  the scene directly.
- `src/desk/shell/window.py` (edit) — pass `title=widget_id` to
  `add_widget()`; drop the now-redundant `.resize(640, 480)` calls on the
  raw content widgets (sizing is now the `WidgetFrame`'s job).

## Implementation approach

1. `src/desk/shell/widget_frame.py`:
   - `_DragHandle(QWidget)`: base class tracking a mouse drag in *scene*
     units. On press, records `event.globalPosition()`. On move, computes
     the incremental screen-pixel delta since the last event, divides by
     the enclosing view's current scale (`self.graphicsProxyWidget()
     .scene().views()[0].transform().m11()`, guarding for "not yet
     embedded"/"no views" by defaulting to `1.0`), and calls
     `self._on_drag(dx, dy)` (subclass hook) with that scene-unit delta.
     Clears the tracked position on release.
   - `_TitleBar(_DragHandle)`: fixed-height row with a non-selectable
     `QLabel` (title text) and `Qt.CursorShape.SizeAllCursor`; `_on_drag`
     calls `self.graphicsProxyWidget().moveBy(dx, dy)`.
   - `_ResizeHandle(_DragHandle)`: constructed with an `edge` in `{"left",
     "right", "bottom"}`; sets `SizeHorCursor`/`SizeVerCursor`
     accordingly; `_on_drag` resizes the proxy per the math in
     `widget-ux.md` (right/bottom: resize only; left: resize + `moveBy`
     to keep the right edge fixed), clamped to `MIN_WIDTH`/`MIN_HEIGHT`
     (200×120).
   - `WidgetFrame(QWidget)`: outer `QVBoxLayout` with no margins/spacing:
     `_TitleBar` on top; a `QHBoxLayout` row (left handle | content |
     right handle) with `content` given `QSizePolicy.Expanding` in both
     directions (set explicitly, regardless of the content widget's own
     default policy); a bottom `_ResizeHandle` strip. `content` is stored
     as-is (already handles its own internal hot-reload swapping, per
     `PythonWidgetHost`/`ChromiumWidget` — `WidgetFrame` doesn't need to
     know about that).
2. `src/desk/shell/canvas.py`: `add_widget(self, content: QWidget, title:
   str, pos=(0, 0)) -> QGraphicsProxyWidget` — builds `frame =
   WidgetFrame(title, content)`, calls `frame.resize(680, 520)` (a default
   overall size a bit larger than the previous raw-content default, to
   account for the added chrome), `proxy = self.scene().addWidget(frame)`,
   `proxy.setPos(*pos)`, returns `proxy`.
3. `src/desk/shell/window.py`: update both branches of the kind check to
   pass `title=widget_id` and drop the `.resize(640, 480)` calls on the
   raw `PythonWidgetHost`/`ChromiumWidget` instances (now redundant since
   `WidgetFrame`'s layout sizes them).

## Verification

1. Headless: construct a `WidgetFrame` wrapping a plain `QLabel` in a
   throwaway `QGraphicsScene`/`QGraphicsView` (not the full app) inside a
   short script, and confirm: the frame has the expected child widgets
   (titlebar with the right text, three resize handles with the right
   cursors), and that simulating drag/resize math (calling `_on_drag`
   directly with synthetic deltas) produces the expected `proxy.pos()`/
   `proxy.size()` changes.
2. Launch the real app (`python -m desk`) and confirm via `ps` that it
   starts and stays running (no crash constructing the new chrome around
   the existing `demo` Python widget).
3. Visual confirmation of dragging/resizing by actually moving the mouse
   is expected to be **skipped**, per the precedent in `plans/desk-shell.md`
   and later plans (screenshots haven't reliably shown this app's window
   contents in this environment, and driving real mouse-drag interaction
   isn't scriptable the way HTTP/log-line checks are for previous items).
4. Quit the app (via a `quit` Apple Event, as before); confirm the process
   exits and the server's port stops accepting connections, same as prior
   verifications — proves the new chrome didn't break app lifecycle.

### Status (verification notes)

- Headless check (throwaway `QGraphicsScene`/`QGraphicsView`, not the full
  app): confirmed `WidgetFrame` has exactly one `_TitleBar` and three
  `_ResizeHandle`s with edges `left`/`right`/`bottom`. Calling `_on_drag`
  directly with synthetic scene-unit deltas confirmed: the titlebar moves
  the proxy by exactly the given delta; the right handle resizes width
  only; the left handle resizes width *and* repositions to keep the right
  edge fixed; both width and height clamp correctly at `MIN_WIDTH`/
  `MIN_HEIGHT` when dragged far past the minimum.
- **Found and fixed a real bug during this verification**: `_on_drag` was
  calling `self.graphicsProxyWidget()` on the titlebar/handle widgets
  directly, but `QWidget.graphicsProxyWidget()` does **not** bubble up to
  an embedded ancestor for child widgets in PyQt6 (confirmed directly: a
  child's `graphicsProxyWidget()` returns `None` even though its parent's
  does not) — despite that being the assumption in this plan and in
  `design-docs/widget-ux.md`. Fixed by using `self.window()
  .graphicsProxyWidget()` instead (`QWidget.window()` correctly resolves
  to the top-level embedded ancestor, i.e. the `WidgetFrame` itself, whose
  proxy is what we want). Re-verified all drag/resize math with the fix in
  place (see above) — all correct.
- Launched the real app (`python -m desk`); it started cleanly with the
  `demo` widget now wrapped in a `WidgetFrame`, stayed running, and showed
  no `__pycache__` pollution under `widgets/`.
- Quit via a `quit` Apple Event; confirmed via `ps` the process exited and
  via `curl` the server's port stopped accepting connections — app
  lifecycle unaffected by the new chrome.
- Visual confirmation of actually dragging/resizing via the mouse was
  **skipped**, per the precedent in `plans/desk-shell.md` and later plans
  (this environment's screenshots haven't reliably shown this app's window
  contents, and real mouse-drag interaction isn't scriptable the way
  HTTP/log-line checks were for previous items).

## Key design decisions / tradeoffs

See `design-docs/widget-ux.md` for the full UX spec and rationale; the
main structural decision worth calling out here:

- **Chrome built once at `WorkspaceView.add_widget()`, not inside
  `PythonWidgetHost`/`ChromiumWidget` themselves.** Keeps those two
  classes focused purely on "how is this widget's content built/loaded,"
  or reused, and hot-reload continues to only replace *their* internal
  content — the `WidgetFrame` wrapping them never needs to be
  reconstructed on a hot reload, only what's inside the content area.
- **Screen-pixel deltas divided by view scale, not scene-local widget
  coordinates.** Considered relying on `event.position()` (widget-local)
  deltas directly (as used for a similar drag in earlier plans), but for
  resize handles specifically, the handle's own local coordinate frame
  shifts as the frame resizes mid-drag (it's repositioned by the layout on
  every intermediate resize), which would make naive local-coordinate
  deltas drift. Global screen coordinates are unaffected by any of the
  widget's own geometry changes mid-drag, so dividing by the view's scale
  factor is the robust choice for both the titlebar and the resize
  handles alike (one shared `_DragHandle` base class for both).
