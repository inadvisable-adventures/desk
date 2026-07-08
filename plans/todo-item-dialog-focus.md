# TODO widget: give the item-editor text box real keyboard focus on popup (COMPLETED)

TODO `c8e3b28`.

## Summary

`_ItemDialog` (`widgets/todo/widget.py`), used for both "add item" and
"edit item" in the TODO widget, already called `self._field.setFocus()`
once, at the end of `__init__` -- but that call happened *before the
widget was ever shown* (`.show()` is called later, by the two call
sites), which is a documented no-op per Qt.

That alone turned out not to be the real-world bug, though: fixing just
the timing (moving the claim into a deferred `showEvent` handler that
also calls `raise_()`/`activateWindow()`) still failed to give the
dialog real, application-level keyboard focus once verified against a
*real*, running `DeskWindow` with the TODO widget actually embedded on
the canvas (as opposed to an isolated `_ItemDialog` constructed on its
own, where the naive fix looked like it worked).

**Actual root cause**, found by direct, controlled comparison in a real
running app (constructing the identical `_ItemDialog` with different
parents and checking `QApplication.focusWidget()`, not just the
dialog's own `hasFocus()`/`isActiveWindow()`, which both misleadingly
report success regardless): `_ItemDialog(self)`, where `self` is the
embedded `TodoWidget`, resolves `self.window()` to that widget's
`WidgetFrame` -- but `WidgetFrame` is never itself shown as an
independent OS-level window; it only exists as the source content for
a `QGraphicsProxyWidget`, embedded into the real top-level `DeskWindow`.
Qt still honors the `Tool` window flag and makes `_ItemDialog`
genuinely top-level regardless of parent, and every per-widget signal
(`hasFocus()`, `isActiveWindow()`) reports as if it worked -- but the
single, real, global `QApplication.focusWidget()` never actually moves
to it, so real keystrokes keep going to the `WorkspaceView` underneath.
See `LEARNINGS.md`'s new entry on this for the full comparison.

## Affected files

- `widgets/todo/widget.py` -- `_ItemDialog`, `TodoWidget._show_add_dialog`,
  `TodoWidget._show_edit_dialog`.

## Fix

- `_ItemDialog`: remove the premature `self._field.setFocus()` call
  from `__init__`; add a `showEvent` override that defers a new
  `_claim_focus` helper via `QTimer.singleShot(0, ...)` (the same
  "something else needs to settle right after this" shape already used
  elsewhere in this codebase), which calls `self.raise_()`,
  `self.activateWindow()`, then `self._field.setFocus()`.
- `TodoWidget`: new `_new_item_dialog(self, **kwargs)` helper,
  used by both `_show_add_dialog` and `_show_edit_dialog` in place of
  constructing `_ItemDialog(self, ...)` directly. It parents the dialog
  to `QApplication.activeWindow()` (the real `DeskWindow`, since that's
  necessarily the window that just delivered the Add/Edit click) instead
  of `self`, falling back to `self` only if nothing is active. Since
  the dialog is then no longer a Qt child of `TodoWidget`, its lifetime
  is no longer tied to it automatically -- wired explicitly instead via
  `self.destroyed.connect(dialog.close)`, so an open dialog is still
  torn down together with `TodoWidget` exactly as before (e.g. on hot
  reload).

No behavior change to `_needs_confirmation`, `eventFilter`,
`selectAll()`, discard-confirmation wording (TODO `e60817a`), or the
`_open_edits`/edit-conflict tracking (TODO `d25e557`) -- all unaffected
by *which* widget is used as the dialog's Qt parent.

## Verification

All headless, against a real, running `DeskWindow` (shown, per
`window.show()`) with a real `todo` widget placed on it, using
`QApplication.focusWidget()` (the actual, single, global focus target
real keystrokes go to) rather than the dialog's own, misleading
`hasFocus()`/`isActiveWindow()`:

- Reproduced the bug directly against the unfixed code: clicking the
  real "Add Item" button in a real, embedded `TodoWidget` left
  `QApplication.focusWidget()` on the `WorkspaceView`, not the popped
  -up dialog's field, despite the dialog itself reporting
  `isActiveWindow() == True` and `hasFocus() == True`.
- Confirmed the fix: clicking "Add Item" now moves
  `QApplication.focusWidget()` to the dialog's field. Same check for
  double-clicking an existing item to open the edit dialog.
- Regression: destroying the `TodoWidget` (`deleteLater()` + pump) while
  an edit dialog is open still tears the dialog down (confirmed via its
  `destroyed` signal), matching the previous Qt-parent-child-based
  auto-cleanup behavior exactly, despite no longer relying on it.
- Regression: an isolated `_ItemDialog` (no parent) still gets no focus
  before `.show()` and does get it after, with a pre-existing active
  main window present in the same process (ruling out a regression to
  the simpler, single-window case this bug doesn't affect).
- Regression: `selectAll()` on prefilled edit-mode text, and
  Ctrl+Enter-to-submit, both still work unchanged.

Also noted, but out of scope and unrelated to this fix (see
`PARKINGLOT.md`): a background-thread `FSEventsEmitter` "already
scheduled" warning observed only when a `todo` widget is opened in this
same test harness, not reproduced without one.

## Status

**Completed.** Root cause found by direct comparison against a real
running app (not just an isolated dialog, which misleadingly looked
correct); implemented and verified headlessly as described above.
