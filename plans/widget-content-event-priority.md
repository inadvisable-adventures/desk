# Plan: TODO 3846190 — widget content under the cursor should get all events, not the canvas

## Summary

Bug report: "zoom/pan interactions on individual widgets are generally
unsuccessful... Desk seems to be grabbing the event." Investigated
`WorkspaceView` (`src/desk/shell/canvas.py`) directly (real, headless
repros — not just reading code) and confirmed **three independent,
real gaps**, all sharing the same root shape: canvas-level pan/zoom
handling doesn't consistently check whether the cursor is over a
placed widget's own content before acting.

1. **Right-click is always stolen.** `contextMenuEvent` (line 169)
   unconditionally builds and shows `WidgetSpawnMenu` — it never
   hit-tests what's under the cursor at all. A right-click landing on
   a widget's own content (e.g. a `QTextEdit`'s copy/paste menu, a
   `QWebEngineView`'s browser context menu) never reaches it; Desk's
   own add-widget menu appears instead, every time.
2. **Pinch-to-zoom always zooms the canvas.** The `event()` override's
   `QEvent.Type.NativeGesture`/`ZoomNativeGesture` handling (line 673)
   calls `self._apply_zoom(...)` unconditionally, with no
   `_scrollable_at`-style carve-out at all (confirmed:
   `design-docs/widget-ux.md`'s own "Trackpad Zoom Input" section
   explicitly says pinch was deliberately left out of that carve-out).
   Any pinch gesture over widget content zooms the whole Desk canvas,
   never the widget.
3. **Click-and-drag inside a widget's own content leaks into
   canvas-panning.** Confirmed empirically (a real, headless
   `WorkspaceView` + a plain `QLabel`-content `WidgetFrame`, a real
   press/move/move/release `QMouseEvent` sequence dispatched at the
   viewport level): dragging inside the *widget's own bounds*, on a
   part of its content that doesn't itself consume the drag (e.g. a
   `QLabel`, a paint-only widget like Image Viewer's view, or empty
   canvas background inside SVG Editor's own nested `QGraphicsView`),
   moves the *outer* Desk canvas's scrollbars by exactly the drag
   delta. Root cause: `WorkspaceView`'s `dragMode()` is
   `ScrollHandDrag` (line 95); Qt's own `QGraphicsView.mousePressEvent`
   only starts hand-drag-panning when the scene doesn't itself accept
   the press, and a "passive" embedded widget that never overrides
   `mousePressEvent` (or an inner view's own empty background) leaves
   the underlying native event unaccepted, which propagates all the
   way up through the `QGraphicsProxyWidget` embedding to the *outer*
   view's own hand-scroll fallback. `mousePressEvent`'s existing
   fallthrough (`if hit is None:` after the chrome check) reaches
   `super().mousePressEvent(event)` unconditionally today, with no
   awareness that the press actually landed inside some *other*
   widget's bounds rather than truly empty canvas.

Left-click on widget content that the widget itself *does* actively
consume (a button, a movable/selectable `QGraphicsItem`, text-field
click-to-position-cursor, ...) already works correctly today — Qt's
normal scene delivery handles it, confirmed by the code (nothing
intercepts it) and consistent with no complaints about that specific
case. Likewise, plain wheel-scroll is unaffected — `_scrollable_at`'s
existing `QAbstractScrollArea`/`QWebEngineView` carve-out (TODO
c44e88f, `plans/todo-widget-scrollable.md`) already handles it
correctly and deliberately still zooms the canvas over *non*-scrollable
content (e.g. wheel over a plain Image Viewer), which is intentional,
existing, working behavior — not part of this bug, not touched here.

No built-in widget currently implements its own zoom or pinch gesture
handling (`widgets/image_viewer/`, `widgets/svg_editor/`,
`widgets/browser/` all confirmed to have none) — this fix is entirely
about the canvas correctly *not stealing* these interactions, not about
teaching canvas events to route into a widget's not-yet-existing
gesture handler.

## Design

### 1. Right-click: `contextMenuEvent`

Hit-test first (same shape as `_hit_test_chrome`): if the position is
over a placed widget's *content* (not chrome — a right-click on a
titlebar/button doesn't have a sensible "widget's own context menu"
meaning anyway, and chrome doesn't currently show one), let Qt's normal
scene delivery handle it (`super().contextMenuEvent(event)`) instead of
building `WidgetSpawnMenu`. Otherwise (truly empty canvas, or chrome),
keep today's behavior unchanged.

### 2. Pinch-to-zoom: `event()`

Reuse the existing `_scrollable_at` check (the same one `wheelEvent`
already uses) — if the pinch lands on a scrollable/`QWebEngineView`
widget, don't zoom the canvas (just fall through to
`super().event(event)`, a no-op at the canvas level, same as "not
handled"). Deliberately **not** using the broader "any widget content"
check here — keeps pinch consistent with wheel's own already-correct,
deliberate behavior (still zooms the canvas over non-scrollable content
like a plain image viewer).

### 3. Click-and-drag: `mousePressEvent`

New helper `_frame_at(view_pos) -> WidgetFrame | None` (same `itemAt`
-based shape as `_hit_test_chrome`/`_scrollable_at`, but broader: *any*
placed widget's bounds, not just chrome and not just scroll areas).

In the existing `if event.button() == Qt.MouseButton.LeftButton:`
block, when `_hit_test_chrome` finds nothing (not chrome) but
`_frame_at` finds a frame (i.e., the press is somewhere inside a placed
widget's own content, not truly empty canvas): temporarily set
`self.setDragMode(QGraphicsView.DragMode.NoDrag)` around the
`super().mousePressEvent(event)` call, restoring `ScrollHandDrag`
immediately after. This prevents Qt's own internal hand-scroll-start
decision (made once, synchronously, inside that same call) from ever
engaging for this press, while scene delivery to the embedded widget
proceeds completely normally in the same call — the widget either
handles the drag itself (a `QGraphicsItem` drag, text selection, ...)
or does nothing, but either way the *canvas* no longer pans out from
under it. Truly empty canvas (`_frame_at` returns `None`) is untouched
— background click-drag-to-pan keeps working exactly as before.

Confirmed via the same empirical repro (dragMode toggled around the
call) that this actually stops the outer scrollbars from moving, before
committing to this as the real fix rather than a theoretical one.

## Verification

- Real, headless `WorkspaceView` + placed widget repro (the one already
  used to find the bug): drag inside a passive `QLabel`-content
  widget's bounds no longer moves the outer view's scrollbars/transform
  at all; drag starting on truly empty canvas still pans it exactly as
  before (regression check).
- `contextMenuEvent`: patch `WidgetSpawnMenu` in `desk.shell.canvas`
  and confirm it's *not* constructed for a synthetic context-menu event
  positioned over a placed widget's content, and *is* still constructed
  for one positioned over empty canvas (regression check) — avoids
  actually popping a real, blocking `QMenu`.
- Pinch: construct a synthetic `NativeGesture`/`ZoomNativeGesture` event
  positioned over a `QTextEdit`-backed widget's content and confirm
  `_apply_zoom`/the view's transform is untouched; same event over
  empty canvas still zooms (regression check).
- Existing wheel-scroll behavior (`_scrollable_at` itself, untouched)
  re-verified unaffected — re-run `tests/verify/verify_todo_widget.py`
  -style / any existing wheel-related script, plus the full
  `tests/verify/` regression suite (`git stash` before/after).
- Chrome interactions (titlebar drag, resize handles, close/lock/
  bring-to-front/send-to-back/eye/tempui-promote/stale buttons) are
  untouched by all three changes — confirmed by re-running the existing
  chrome-focused scripts (`verify_z_order_buttons.py`,
  `verify_lock_widgets.py`, `verify_widget_borders.py`,
  `verify_eye_button_persists_title_only.py`, ...).

## Non-Goals

- Teaching any built-in widget to implement its own pinch-zoom or
  drag-to-pan — none currently do; this is purely about the canvas no
  longer stealing the interaction, not adding new per-widget gesture
  features.
- Changing wheel-scroll's existing, deliberate behavior in any way.
- The `PARKINGLOT.md` "add a minimap" idea (paired with the *original*
  wheel-scroll fix) — unrelated to this bug, left parked.
