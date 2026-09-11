# Bug: crash removing a popup from the scene during its own click event (TODO `74a8b78`) (COMPLETED)

## Summary

A real, reproducible SIGBUS crash (confirmed via a macOS crash report)
clicking any button in a desk-internal popup shown via
`PopupsService.show_blocking` (`current_context.get_popup_opener()` for
`kind: "python"`, `desk.popups.show(...)` for `kind: "html"` -- the only
popup mechanism in the app, so this affects every alert/confirmation
everywhere, not just the State Manager widget that surfaced it). The
crash trace shows a `QGraphicsScene`/`QGraphicsItem` mouse-event
dispatch (the click on the popup's own button) still unwinding when
`WorkspaceView.remove_popup` calls `self.scene().removeItem(proxy)`
**synchronously**, from inside that same click's own handler chain --
Qt's internal object-liveness bookkeeping
(`QSharedPointer::ExternalRefCountData::getAndRef`) then dereferences a
now-stale pointer. Removing a `QGraphicsItem` from its scene while the
scene is still mid-dispatch of the very event that triggered the
removal is a real, known Qt Graphics View reentrancy hazard, not
something specific to this app's own code beyond triggering it.

## Affected files

- `src/desk/shell/canvas.py` -- `WorkspaceView.remove_popup`.
- `tests/verify/verify_desk_internal_popups.py` -- new coverage for the
  deferred-removal behavior itself.

## Design decisions

- **Defer the scene mutation, don't avoid it** -- `remove_popup` still
  needs to actually remove the item and delete the frame eventually;
  the fix is *when*, not *whether*. `frame.hide()` and
  `self._popup_frames.remove(frame)` stay synchronous (neither mutates
  the scene's item list, so neither is subject to the same hazard) --
  the popup visually disappears immediately and is instantly excluded
  from `_popup_frames`-based bookkeeping (z-ordering,
  `clear_widgets`'s own membership check), exactly as before. Only
  `self.scene().removeItem(proxy)` and `frame.deleteLater()` move onto
  a `QTimer.singleShot(0, ...)` callback -- the same "defer past the
  current event dispatch" idiom this file already uses elsewhere
  (`_position_desk_picker`/`_position_temp_ui_notifications`/
  `_position_zoom_control`), just applied to a scene-graph mutation
  instead of a layout reassertion.
- **Why hiding is safe but removal isn't**: `QWidget.hide()` (and the
  `QGraphicsProxyWidget` mirroring it) is a property change, not a
  scene-graph structural mutation -- it doesn't touch the scene's own
  item list or z-order bookkeeping the way `removeItem` does, so it
  carries none of the reentrancy risk. A hidden proxy is also
  automatically excluded from `itemAt`-based hit-testing
  (`WorkspaceView._frame_at`), so nothing can be clicked on it in the
  brief window before the deferred removal actually runs.
- **`clear_widgets`'s own defensive fallback removal is left
  unchanged** -- it calls `self.scene().removeItem(proxy)` directly
  too, but only for a popup with *no* listener attached (an isolated
  test, not the normal `PopupsService`-mediated path) and only ever
  from `DeskWindow.switch_desk`-style code, never from inside the
  scene's own event dispatch -- not the same hazard. Its *normal* path
  (emitting `popup_closed`, letting `PopupsService`'s own resolver run)
  now goes through the fixed, deferred `remove_popup` regardless.
- **No fix needed in `PopupsService` itself** -- the reentrancy is
  entirely a property of *when* `WorkspaceView.remove_popup` mutates
  the scene, not of `PopupsService.resolve()`'s own call sequence.

## Step-by-step implementation

1. `canvas.py`: `remove_popup` calls `frame.hide()` and removes `frame`
   from `_popup_frames` synchronously (as today), then schedules the
   actual `self.scene().removeItem(proxy)` + `frame.deleteLater()` via
   `QTimer.singleShot(0, ...)`, guarding against `proxy`/`proxy.scene()`
   already being `None` (defensive, in case something else already
   tore it down in the interim).
2. Extend `tests/verify/verify_desk_internal_popups.py` (below); run
   the full `tests/verify/` regression suite.

## Key tradeoffs

- **This cannot be verified with an automated reproduction of the
  actual SIGBUS** -- the crash trace shows real, native
  `NSApplication`/`CFRunLoop` frames delivering an actual OS-level
  mouse click; a headless, offscreen test has no equivalent event
  source to reproduce the exact reentrant-dispatch timing. Verification
  here instead confirms the specific, deliberate behavior change this
  fix makes (scene removal is deferred, not synchronous) as the best
  available proxy for "the reentrancy hazard this bug depended on no
  longer exists on this path" -- not a reproduction of the crash
  itself before/after.

## Verification

- `tests/verify/verify_desk_internal_popups.py` (extended): clicking a
  popup's button hides it and removes it from `_popup_frames`
  synchronously (already covered, must still pass unchanged); its
  `QGraphicsProxyWidget` is still present in the scene immediately
  after the click, *before* any event-loop pump -- proving the scene
  mutation is genuinely deferred, not merely fast; after one
  `app.processEvents()` pump, the proxy is gone from the scene and the
  frame itself gets deleted (`sip.isdeleted`); the existing
  `test_clear_widgets_resolves_any_open_popup` still passes with the
  new deferred path (a popup resolved via `clear_widgets`'s
  `popup_closed.emit` also only actually leaves the scene after a
  pump).
- Full `tests/verify/` regression suite (124 scripts as of TODO
  `5242aeb`, plus this item's extended script).
