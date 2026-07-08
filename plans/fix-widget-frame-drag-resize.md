# Fix widget frame drag/resize (COMPLETED)

## Summary

`WidgetFrame`'s titlebar and resize handles (`design-docs/widget-ux.md`,
`src/desk/shell/widget_frame.py`) render correctly, but dragging them
doesn't move or resize the widget in the running app. Root-caused (see
below): `_DragHandle.mousePressEvent`/`mouseMoveEvent`/`mouseReleaseEvent`
never call `event.accept()`, and delegate to `super().mousePressEvent(...)`
(the base `QWidget` implementation), which leaves the event unaccepted.

In a `QGraphicsProxyWidget`-embedded widget, `QGraphicsScene` only
continues delivering `mouseMoveEvent`/`mouseReleaseEvent` to a widget for
the duration of a drag if that widget accepted the initial
`mousePressEvent` — this is the mouse-grab mechanism the graphics
view/scene framework uses to route an in-progress drag to a single item.
Since our press was never accepted, the embedded titlebar/handle widgets
received exactly one `mousePressEvent` and then nothing else: no
`mouseMoveEvent` at all, so `_on_drag` (whose actual delta math was
already verified correct in `plans/widget-ux-chrome.md`) was simply never
invoked during real interaction.

## Root cause (confirmed via direct reproduction)

Reproduced with a real event path (constructing `QMouseEvent`s and sending
them to the `QGraphicsView`'s `viewport()`, i.e. the same path real mouse
interaction takes — not calling `_on_drag`/`mousePressEvent` directly,
which bypasses the scene's grab logic and would not have caught this):

- Traced `_TitleBar.mousePressEvent`: fires correctly, with the right
  `window()`/`graphicsProxyWidget()` resolved.
- Traced `_TitleBar.mouseMoveEvent`: **never fires** during a simulated
  press-then-move sequence routed through the viewport.
- Patching `mousePressEvent` to call `event.accept()` (instead of
  delegating to the base class) immediately fixed it: the subsequent
  `mouseMoveEvent` fired and the proxy moved by the expected delta.

## Affected files

- `src/desk/shell/widget_frame.py` — `_DragHandle.mousePressEvent`,
  `mouseMoveEvent`, `mouseReleaseEvent`.

## Implementation approach

1. In `_DragHandle.mousePressEvent`: when the left button is pressed, set
   `self._last_global` **and call `event.accept()`**; only delegate to
   `super().mousePressEvent(event)` for the case where we don't handle it
   (i.e. not the left button), so it can still get default handling.
2. In `mouseMoveEvent`: when a drag is in progress (`self._last_global is
   not None`), compute and apply the delta as before, **and call
   `event.accept()`**; otherwise delegate to `super()`.
3. In `mouseReleaseEvent`: when ending a drag (`self._last_global is not
   None` before clearing it), **call `event.accept()`**; otherwise
   delegate to `super()`.
4. No change needed to the drag/resize math itself (`_on_drag` in
   `_TitleBar`/`_ResizeHandle`) — already verified correct in
   `plans/widget-ux-chrome.md`; this was purely an event-acceptance bug.

## Verification

1. Reproduce-then-fix via the same realistic event-simulation approach
   used to root-cause this (constructing `QMouseEvent`s and sending them
   to a `QGraphicsView`'s `viewport()` wrapping a real `WidgetFrame`, not
   calling internal methods directly): confirm that, with the fix applied,
   a simulated press+move on the titlebar moves the underlying
   `QGraphicsProxyWidget` by the expected delta, and that a press+move on
   each resize handle (left/right/bottom) resizes it correctly — this is
   the regression test this bug needed and the previous plan
   (`plans/widget-ux-chrome.md`) didn't have, since it only tested
   `_on_drag` directly rather than the real event path.
2. Launch the real app (`python -m desk`); confirm it still starts and
   quits cleanly (no regression to app lifecycle from this change).
3. Actually dragging with a physical mouse in the running app is expected
   to be **skipped** for direct visual confirmation, per the precedent in
   `plans/desk-shell.md` and later plans (this environment's screenshots
   haven't reliably shown this app's window contents) — but unlike those
   prior items, step 1 above now exercises the *real* interactive event
   path (not just the isolated math), which is what was missing before
   and is what actually caught this bug.

### Status (verification notes)

- Re-ran the realistic viewport-routed event simulation (press + several
  incremental moves + release, sent to the `QGraphicsView`'s `viewport()`)
  against the fixed code for all four handles: the titlebar drag moved the
  proxy by exactly the simulated delta; the right handle resized width
  only by the simulated delta; the left handle resized width by the delta
  *and* moved `x` by the same amount (keeping the right edge fixed); the
  bottom handle resized height only. All four matched expected values
  within floating-point tolerance — confirms the fix actually works
  through the real interactive event path, not just in isolation.
- Launched the real app (`python -m desk`); it started cleanly with the
  fix in place, and quitting (via a `quit` Apple Event) stopped the
  process and the server's port cleanly — no lifecycle regression from
  this change.
- Actually dragging with a physical mouse was **skipped** for direct
  visual confirmation, per the precedent in `plans/desk-shell.md` and
  later plans (screenshots haven't reliably shown this app's window
  contents in this environment) — but per the Verification plan above,
  this item's real-event-path simulation is a meaningfully stronger check
  than what `plans/widget-ux-chrome.md` did, and is exactly what caught
  this bug in the first place.

## Key design decisions / tradeoffs

- **Accept only when we actually handle the event, delegate to `super()`
  otherwise.** Keeps default Qt behavior (e.g. right-click, or any event
  we're not tracking a drag for) intact, rather than unconditionally
  accepting everything that reaches these widgets.
- **No change to the drag/resize math.** The math was already verified
  correct in isolation; this was purely about the event *not reaching* the
  math at all during a real drag, which the previous plan's verification
  (calling `_on_drag` directly) couldn't have caught. Worth remembering for
  future widget-interaction work: verify through the real event path
  (`QGraphicsView.viewport()`), not just by calling handler methods
  directly.
