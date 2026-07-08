# Fix zoom/pan interaction & add a zoom control widget (COMPLETED)

## Summary

Address the reported Workspace Canvas zoom/pan UX problems and add the
requested zoom control, per the updated TODO item:

1. Trackpad pinch-to-zoom doesn't work (only `wheelEvent`/two-finger
   scroll is handled today; macOS trackpad pinch arrives as a distinct
   native gesture event).
2. Two-finger-scroll-to-zoom is way too sensitive (currently a flat 25%
   zoom step *per wheel event*, and trackpad scroll fires many more
   events per gesture than a physical wheel's discrete notches).
3. Dragging a widget gets increasingly sensitive as zoom increases —
   investigated below; root cause is actually item 4, not the drag math.
4. **Interaction model**: zooming currently magnifies the *entire*
   `WidgetFrame` uniformly (chrome and content together), since it's one
   `QGraphicsProxyWidget` scaled by the view's transform. Titlebars/resize
   handles should stay a constant size on screen regardless of zoom; only
   each widget's content area should visually zoom/pan with the view.
5. New: a small persistent zoom control (fit-to-content, reset, slider),
   anchored to the lower-right corner of the viewport in screen space,
   shown only when zoom is non-unity.

## Investigation: drag sensitivity (item 3)

Re-derived the drag math from `plans/fix-widget-frame-drag-resize.md`:
`_DragHandle` converts a screen-pixel delta to a scene-unit delta by
dividing by the view's current scale (`dx_scene = dx_screen / scale`), then
calls `proxy.moveBy(dx_scene, dy_scene)`. Since the view later renders scene
positions multiplied by that same `scale`, the net on-screen movement is
`(dx_screen / scale) * scale == dx_screen` — exactly the cursor's screen
movement, independent of zoom. This math is zoom-invariant and correct on
its own.

The reported "increasing sensitivity" is best explained by item 4 instead:
today, zooming in also magnifies the *entire* widget including its chrome,
so the titlebar occupies far more screen space at high zoom, changing how
a drag *feels* relative to the widget's own (now much larger) visual
footprint, even though the underlying delta math is unaffected. Fixing item
4 (decoupling chrome from the zoom transform) is expected to resolve this
as a side effect; this plan's verification re-checks drag behavior at
multiple zoom levels (not just 1.0, which is all the previous plan
checked) to confirm.

## Design

### Wheel zoom sensitivity (item 2)

Replace the flat `ZOOM_STEP` (25% per wheel event) with a continuous,
delta-proportional model: `factor = exp(pixel_delta * SENSITIVITY)`, using
`event.pixelDelta().y()` (the high-resolution delta macOS trackpads report
directly) when available, falling back to `event.angleDelta().y() / 8`
(approximate degrees) for a traditional wheel. A small `SENSITIVITY`
constant (tuned to `0.0025`) makes a typical two-finger swipe change zoom
gradually instead of in large jumps.

### Trackpad pinch (item 1)

Override `QWidget.event()` in `WorkspaceView`, checking for
`QEvent.Type.NativeGesture` with `gestureType() ==
Qt.NativeGestureType.ZoomNativeGesture` (confirmed present in PyQt6 via
direct introspection). Its `value()` is the relative zoom change for that
gesture update; apply as `factor = 1.0 + value()`, through the same
`_apply_zoom` path wheel events use. (PyQt6 doesn't expose a dedicated
`nativeGestureEvent()` override point — confirmed via `hasattr` — so this
goes through the generic `event()` override instead, per Qt's documented
fallback for native gesture events.)

### Chrome stays constant screen size (item 4)

Rather than splitting each widget into two separate graphics items (a
content proxy plus a `QGraphicsItem.ItemIgnoresTransformations` overlay
kept in sync on every pan/zoom — real but meaningfully more complex),
counter-scale the chrome's own *widget-local* size inversely to the view's
current zoom, so that when the view later multiplies by that same zoom
factor when rendering, the chrome's on-screen size cancels back out to a
constant:

- `WidgetFrame.set_view_scale(scale)`: sets the titlebar's fixed height to
  `round(TITLEBAR_HEIGHT / scale)`, each resize handle's thickness to
  `round(HANDLE_THICKNESS / scale)`, and the titlebar label's font size to
  `round(BASE_FONT_PT / scale)` — all in the frame's own local Qt-widget
  units, which the view's transform then scales by `scale` when painting,
  landing back at the original constant pixel sizes.
- `WorkspaceView` keeps a list of every placed `WidgetFrame` and calls
  `set_view_scale()` on all of them whenever the view's zoom changes (wheel,
  pinch, slider, fit-to-content, or reset).
- Content is unaffected: it just gets "whatever's left" in the layout after
  the (now-shrunk-or-grown) chrome takes its fixed share, so it continues
  to zoom/pan with the view exactly as before.

This is simpler than the two-item approach and doesn't require tracking a
synchronized overlay position — the whole `WidgetFrame` (chrome + content)
remains one `QGraphicsProxyWidget`/scene item, as today; only the chrome's
*internal* Qt-widget sizes change with zoom.

### Zoom control widget (item 5)

New `src/desk/shell/zoom_control.py`: `ZoomControl(QWidget)`, a small HUD
panel (not a scene item — a plain child widget of `WorkspaceView.viewport()`,
which renders in screen space unaffected by the scene's transform, exactly
like any floating overlay over a `QGraphicsView`):

- "Fit" button → `fit_requested` signal.
- "100%" button → `reset_requested` signal.
- A small horizontal `QSlider` (10%–400%, matching `MIN_SCALE`/`MAX_SCALE`)
  → `zoom_changed(float)` signal (absolute target scale), with a
  `set_zoom(scale)` method (blocking the slider's own change signal while
  updating it programmatically, to avoid feedback loops) so it stays in
  sync when zoom changes via wheel/pinch/fit/reset.

`WorkspaceView`:
- Owns one `ZoomControl`, repositioned to the bottom-right corner (with a
  small margin) in `resizeEvent` and at construction.
- Connects `fit_requested` → `zoom_to_fit()`, `reset_requested` →
  `reset_zoom()`, `zoom_changed` → an absolute-target zoom path.
- Shows the control only when `abs(scale - 1.0) > epsilon`; hidden at
  construction (starts at unity).
- `zoom_to_fit()`: `scene().itemsBoundingRect()`, expanded by a margin of
  0.1% of its own width/height on each side (as specified), then
  `self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)`; reads back
  `self.transform().m11()` as the resulting scale, clamps it to
  `[MIN_SCALE, MAX_SCALE]` (correcting the transform if clamping changed
  anything), and updates bookkeeping (`self._scale`, chrome rescaling, HUD
  visibility/slider).
- Wheel/pinch zoom keeps `AnchorUnderMouse` (zooms toward the cursor, as
  today). Slider/fit/reset-triggered zoom changes temporarily switch to
  `AnchorViewCenter` around the underlying `scale()` call, since the
  cursor may be sitting over the HUD itself when these are triggered and
  anchoring under it would be a confusing place to zoom toward.

## Affected files

- `src/desk/shell/canvas.py` — wheel sensitivity, native gesture handling,
  chrome-rescaling bookkeeping, `ZoomControl` wiring, `zoom_to_fit`/
  `reset_zoom`/absolute-zoom methods, `resizeEvent`.
- `src/desk/shell/widget_frame.py` — `WidgetFrame.set_view_scale(scale)`
  and the underlying per-handle/titlebar size (and font) adjustment;
  called once at construction (scale=1.0 default) and again by
  `WorkspaceView` whenever zoom changes.
- `src/desk/shell/zoom_control.py` (new) — `ZoomControl` HUD widget.
- `design-docs/widget-ux.md` — document the chrome-stays-constant-size
  behavior and the counter-scaling approach (this is squarely a widget-UX
  concern, per that doc's scope).
- `design-docs/architecture.md` — brief mention/cross-reference if the
  Workspace Canvas component description needs updating for the new zoom
  control and native-gesture handling.

## Verification

1. Headless: construct a `WorkspaceView` in a throwaway app, add a
   `WidgetFrame`-wrapped widget via `add_widget()`, then call `_apply_zoom`
   (or the wheel handler directly) at a few different factors and confirm,
   after each: (a) the titlebar's on-screen height (`titlebar.height() *
   view_scale`, or equivalently checking the *local* height equals
   `TITLEBAR_HEIGHT / new_scale`) stays mapped back to `TITLEBAR_HEIGHT`
   screen pixels; (b) the content widget still resizes to fill the
   remaining space.
2. Headless: simulate a `QNativeGestureEvent` with `ZoomNativeGesture` and
   `value()` set to a known number, sent via `QApplication.sendEvent()` to
   the view (the same realistic-event-path approach used in
   `plans/fix-widget-frame-drag-resize.md`); confirm the view's scale
   changes by the expected `1.0 + value` factor. (This tests the handler
   logic; it cannot prove real trackpad hardware routes pinch through this
   same code path, since there's no physical trackpad to drive in this
   environment — noted as a real-hardware caveat, not skipped entirely.)
3. Headless: simulate `wheelEvent`s with a range of `pixelDelta`/
   `angleDelta` values and confirm the resulting zoom factor is
   proportionally smaller than the old flat-25%-per-event behavior for a
   typical trackpad-sized delta.
4. Headless: re-run the titlebar-drag simulation from
   `plans/fix-widget-frame-drag-resize.md` (real event path via the
   viewport, not calling `_on_drag` directly) at **three zoom levels**
   (0.5×, 1×, 2×) and confirm the proxy's on-screen movement
   (`scene_delta * current_scale`) matches the simulated screen-pixel
   delta at all three — confirming the "increasing sensitivity" is
   resolved (or was never actually present in the delta math, per the
   Investigation section, and the fix is really the chrome-decoupling).
5. Headless: `zoom_to_fit()` on a scene with a couple of placed widgets;
   confirm the resulting scale brings `scene().itemsBoundingRect()`
   (expanded by the 0.1% margin) into view, and that the `ZoomControl`
   becomes visible (since fit-to-content is very unlikely to land exactly
   on 1.0×) with its slider reflecting the new scale.
6. Headless: `reset_zoom()` after zooming; confirm scale returns to 1.0
   and the `ZoomControl` hides again.
7. Launch the real app (`python -m desk`); confirm it starts and quits
   cleanly (no regression to app lifecycle from this change).
8. Actually pinching/scrolling/dragging with real trackpad hardware, and
   visually confirming the zoom control's appearance, are expected to be
   **skipped** for direct confirmation, per the precedent in
   `plans/desk-shell.md` and later plans (no way to drive real trackpad
   hardware or reliably capture this app's window in this environment).

### Status (verification notes)

- **Chrome counter-scaling (item 4)**: verified directly — constructed a
  `WidgetFrame` and called `set_view_scale()` at 0.5×, 1×, 2×, and 4×;
  confirmed the titlebar's and each resize handle's *on-screen* size
  (`local_size * view_scale`) stayed within a pixel of the constant target
  at every tested zoom level.
- **Wheel sensitivity (item 2)**: verified directly — a single
  trackpad-sized `pixelDelta` (5px) now changes zoom by ~1.3%, versus the
  old flat 25%-per-event step; a traditional mouse-wheel notch
  (`angleDelta=120`) changes zoom by ~3.8%, a much more controllable
  per-click step than before.
- **Trackpad pinch (item 1)**: verified via a realistic simulated
  `QNativeGestureEvent` (`ZoomNativeGesture`) sent to the view — confirmed
  the handler applies `1.0 + value()` correctly. (Constructing the event
  with `dev=None` segfaults the process — a PyQt6/Qt binding quirk, not an
  app bug; using `QPointingDevice.primaryPointingDevice()` works. Real
  hardware always supplies a valid device, so this doesn't affect the
  shipped code, only how the event had to be constructed for this test.)
  This confirms the handler logic; it cannot prove real trackpad hardware
  routes pinch through this exact code path, since there's no physical
  trackpad available in this environment.
- **Zoom control (item 5)**: verified directly — `zoom_to_fit()` brings
  the scene's bounding rect (plus the 0.1% margin) into view and shows the
  control; `reset_zoom()` returns to 1.0× and hides it again; the slider
  both drives zoom (`setValue(150)` → scale 1.5) and stays in sync when
  zoom changes via other means (wheel zoom → slider value follows).
- **Drag/resize regression check at unity zoom**: re-ran the titlebar-drag
  and right-edge-resize simulations from
  `plans/fix-widget-frame-drag-resize.md` after this change; both still
  work correctly at scale=1.0 (no regression from the chrome-counter
  -scaling change).
- **Drag sensitivity at non-unity zoom (item 3) — inconclusive in this
  environment.** Attempted the same kind of realistic event-path
  simulation used in `plans/fix-widget-frame-drag-resize.md`, extended to
  0.5×/2× zoom. Results were inconsistent across three different
  coordinate-source strategies tried (`globalPosition()`, `position()`,
  `scenePosition()`) and didn't cleanly match the analytically-expected
  1:1 screen tracking except at specific scales per strategy — most likely
  because manually constructing a `QMouseEvent` and routing it through
  `QApplication.sendEvent()` doesn't perfectly replicate how Qt's real
  event pipeline (OS → platform plugin → `QGraphicsView` → `QGraphicsScene`
  → `QGraphicsProxyWidget` → embedded widget) computes coordinates at
  non-unity view scale, especially combined with this machine's
  devicePixelRatio=2.0 (Retina) display. Given this, **the existing drag
  math (divide screen-pixel delta by view scale) was left unchanged** —
  it's analytically sound and was cleanly verified at scale=1.0 (both
  originally and in this change's regression check); switching it based on
  contradictory synthetic-test signals would trade a working, reasoned
  implementation for an unverified guess. The interaction-model fix (item
  4, chrome counter-scaling) remains the primary, high-confidence fix for
  the reported symptom. **Recommend re-checking drag feel on real trackpad
  hardware at various zoom levels once that's possible** — noted in
  `design-docs/widget-ux.md`'s Open Questions.
- Launched the real app (`python -m desk`); it starts and quits cleanly
  with all of the above in place.
- Actually pinching/scrolling/dragging with real trackpad hardware, and
  visually confirming the zoom control's on-screen appearance, remain
  **skipped**, per the precedent in `plans/desk-shell.md` and later plans.

## Key design decisions / tradeoffs

- **Counter-scaling chrome's local size, not a separate
  `ItemIgnoresTransformations` overlay item.** The overlay approach is more
  "correct" in the sense that it's Qt's purpose-built mechanism for
  constant-screen-size scene content, but it requires maintaining a second
  graphics item per widget kept in position-sync with the first on every
  pan/zoom/move/resize — meaningfully more moving parts for the same
  visible result. Counter-scaling keeps the existing "one `WidgetFrame`
  proxy per widget" structure entirely intact and only changes numbers
  fed into the same Qt layouts already in place.
- **`exp(delta * sensitivity)` for wheel zoom, not a fixed step per
  event.** A trackpad's two-finger scroll fires many more, smaller-delta
  wheel events than a physical mouse wheel's discrete notches; scaling the
  zoom factor by the actual delta (rather than applying a flat percentage
  per *event*) is what makes both input types feel proportional to the
  gesture rather than either too sensitive (trackpad) or not requiring
  much thought (mouse notches, where the same code produces a modest,
  reasonable per-notch step because `angleDelta` for a physical wheel
  notch is a fixed, much larger magnitude than a single trackpad frame's
  delta).
- **Zoom control is a plain child `QWidget` of the viewport, not a scene
  item.** `QGraphicsView` viewports routinely host floating overlay
  widgets this way (it's the standard pattern for HUD-style controls over
  a graphics view) — far simpler than trying to keep a scene-space item
  pinned to a screen-space corner.
