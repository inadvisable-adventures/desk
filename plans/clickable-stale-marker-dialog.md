# Plan: TODO 3e2c4f2 (COMPLETED) — clickable `[STALE]` marker with a hash/reload dialog

## Summary

TODO 5995ffd's `[STALE]` marker is currently just text appended to the
titlebar's title label (mirroring `[EXTERNAL]`) with an explanatory
tooltip -- not clickable, no way to act on it from the widget itself.
Change it to a real titlebar button (matching how `[TEMPUI]` already
works) that, when clicked, pops up a dialog showing both content hashes
and offering to reload this specific instance now or leave it as-is.

## `src/desk/shell/widget_frame.py`

- New `_StaleIndicatorButton(QWidget)`, styled identically to
  `_TempuiPromoteButton` (variable width sized to its own text, not a
  fixed square) but showing `"[STALE]"` -- add it to
  `_button_target_width`'s `isinstance` branch the same way.
- `_TitleBar.__init__`: add `self.stale_button = _StaleIndicatorButton()`
  to the layout (next to `tempui_promote_button`), with a static tooltip
  on it explaining what it means and that clicking shows details
  ("This instance predates the currently-registered widget definition
  -- click for details.").
- `_TitleBar.set_stale(is_stale)`: now just sets `self._stale` and calls
  `_refresh_button_visibility()` -- no more label-text/tooltip
  manipulation; `_update_label_text` goes back to only handling
  `[EXTERNAL]`.
- `_refresh_button_visibility`/`_visible_button_widgets_for_full_state`:
  add `stale_button`, gated by `self._stale` (same shape as
  `tempui_promote_button`/`self._tempui_promotable`).
- `_TitleBar.apply_scale`: counter-scale `stale_button` too.
- `WidgetFrame.set_stale` is unchanged (already just forwards to
  `_titlebar.set_stale`).

## `src/desk/shell/canvas.py` (`WorkspaceView`)

- New signal: `widget_stale_clicked = pyqtSignal(WidgetFrame)`.
- `_hit_test_chrome`'s `childAt` walk: add `_StaleIndicatorButton` to the
  tuple of recognized chrome types, return `(frame, "stale")` for it
  (mirroring `_TempuiPromoteButton`/`"tempui_promote"`).
- `mouseReleaseEvent`'s button-kind dispatch: `elif kind == "stale":
  self.widget_stale_clicked.emit(frame)`.

## `src/desk/shell/window.py` (`DeskWindow`)

- Connect `self.view.widget_stale_clicked.connect(self
  ._on_widget_stale_clicked)` alongside the existing
  `tempui_promote_requested` connection.
- New `_confirm_stale_reload(self, placed_hash: str, current_hash: str)
  -> bool`: a `QMessageBox` showing both hashes (`informativeText`) with
  two custom buttons, "Reload Now" (`AcceptRole`) and "Keep for Now"
  (`RejectRole`); returns whether "Reload Now" was clicked. Split out as
  its own method so headless verification can monkeypatch it, matching
  `_confirm_clear`/`_confirm_delete`'s established shape.
- New `_on_widget_stale_clicked(self, frame: WidgetFrame) -> None`:
  no-ops if `frame.content` isn't a `ChromiumWidget`, or if the
  keyword's current hash is missing/no longer differs from
  `frame.placed_content_hash` (a race: e.g. already reloaded, or the
  definition changed back). Otherwise calls `_confirm_stale_reload`; on
  "Reload Now", calls `frame.content.reload()` **on this specific
  frame's `ChromiumWidget` instance only** (not a broadcast via
  `HotReloadBroker.widget_changed`, which would reload *every* placed
  instance of that keyword regardless of which one's marker was
  clicked -- the whole point here is a per-instance choice), then
  updates `frame.placed_content_hash` to the current hash and calls
  `frame.set_stale(False)`. On "Keep for Now" (or the dialog otherwise
  not confirmed), does nothing -- the instance stays exactly as it was,
  still marked `[STALE]`.

## Existing verification to update

`verify_custom_widget_content_hash.py` (TODO 5995ffd's own script)
currently asserts `"[STALE]" in frame._titlebar._label.text()` -- update
those checks to `frame._titlebar.stale_button.isVisible()` instead, since
the marker is no longer text appended to the label.

## Verification

- `_StaleIndicatorButton` shows/hides correctly via `set_stale`, and
  contributes to `min_full_width_px` like `_TempuiPromoteButton` does.
- Clicking it (via `WorkspaceView`'s real hit-test/mouse-press-release
  flow, on a real `WorkspaceView`) emits `widget_stale_clicked` with the
  right frame.
- `_on_widget_stale_clicked`: confirms `_confirm_stale_reload` is called
  with the correct two hashes; "Reload Now" calls `.reload()` on the
  clicked frame's own `ChromiumWidget` (and only that instance, not a
  second placed instance of the same keyword), updates
  `placed_content_hash`, and clears `[STALE]`; "Keep for Now" changes
  nothing (still stale, no reload call).
- A frame that isn't a `ChromiumWidget`, or one that's no longer
  actually stale, is a no-op.
- Full scratchpad regression suite (`git stash` before/after).
