# TODO widget: discard/save-changes buttons on the item editor, no click-away dismiss (TODO a629bea) (COMPLETED)

## Summary

TODO a629bea: the TODO widget's item editor (`_ItemDialog`, shared by
add and edit — see `plans/todo-widget-edit-on-doubleclick.md`) currently
has a single button always labeled "Add", even when editing, and
dismisses silently on click-away (inherited from `Qt.WindowType.Popup`,
same mechanism `WidgetSpawnMenu` uses — see `design-docs/widget-ux.md`
line ~268 and `LEARNINGS.md`'s "A `Qt.WindowType.Popup` widget can
silently self-destruct during headless testing").

Change `_ItemDialog` to:

1. Show two buttons: "Discard" (always) and either "Add" (add flow) or
   "Save changes" (edit flow).
2. Confirm before discarding whenever the field currently holds any
   non-whitespace text — whether reached via the Discard button or via
   Escape.
3. No longer dismiss when the user clicks outside it.

## Affected files

- `widgets/todo/widget.py` (edit): `_ItemDialog`, `_show_add_dialog`,
  `_show_edit_dialog`.

## Design

- **Window flags.** Drop `Qt.WindowType.Popup` (its auto-close-on-focus
  -loss is exactly the click-away dismissal being removed) in favor of
  `Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint`: a borderless,
  always-on-top-of-its-parent floating window that does *not* grab-close
  when focus moves elsewhere. Keep `WA_DeleteOnClose`. Positioning
  (`dialog.move(...)` in both `_show_add_dialog`/`_show_edit_dialog`) is
  unaffected. This only touches `_ItemDialog` — `WidgetSpawnMenu` keeps
  `Popup`, since a typeable-filter menu that dismisses on click-away (like
  a real `QMenu`) is the correct, unrelated behavior for that widget and
  isn't part of this TODO item.
- **Submit label.** `_ItemDialog.__init__` gains `submit_label: str =
  "Add"`. `_show_edit_dialog` passes `submit_label="Save changes"`;
  `_show_add_dialog` keeps the default. The button's text is the only
  thing that varies between add/edit — no separate mode enum needed.
- **Button row.** Replace the single `submit` button with a
  `QHBoxLayout` containing a "Discard" button (calls
  `self._attempt_discard`) and the submit button (unchanged: calls
  `self._submit`, label from `submit_label`).
- **Discard confirmation.** New `_attempt_discard(self) -> None`: if
  `self._field.toPlainText().strip()` is non-empty, ask
  `self._confirm_discard()`; close only if it returns `True` (or the
  field was already blank). New `_confirm_discard(self) -> bool` wraps a
  single `QMessageBox.question(...)` (Yes/No, default No) — split out as
  its own method (rather than inlined in `_attempt_discard`) specifically
  so headless verification can monkeypatch just this one method instead
  of driving a real modal `QMessageBox`.
- **Escape key.** `eventFilter`'s `Key_Escape` branch now calls
  `self._attempt_discard()` instead of unconditionally `self.close()`,
  so Escape and the Discard button share one code path and one
  confirmation rule.
- **Literal reading of "any non-whitespace text."** For the edit flow,
  the field is prefilled with the item's existing description, so it is
  never blank — clicking Discard right after opening the edit dialog
  (with zero changes made) will still prompt for confirmation. The TODO
  item's wording says "if there is any non-whitespace text," not "if the
  text has changed," and a dirty-check would need to store/compare the
  original text for no clear benefit the item asked for — implementing
  it literally (content-based, not diff-based) is simpler and matches
  what was actually requested.
- **Submit unaffected.** `_submit`'s own behavior (emit
  `item_submitted` if non-empty, then `self.close()`) doesn't change —
  submitting is never a "discard," so it never needs confirmation.

## Verification

Headless, extending the existing pattern (real `TodoWidget`/`_ItemDialog`
instances, no visible window required — and now safe to `.show()` /
`processEvents()` on `_ItemDialog` without the Popup self-destruction
caveat in `LEARNINGS.md`, since it no longer uses `Popup`):

1. Open the add dialog: confirm the submit button reads "Add"; open the
   edit dialog on an existing item: confirm it reads "Save changes" and
   the field is prefilled.
2. Blank field: call `_attempt_discard()`; confirm it closes without
   invoking `_confirm_discard` (monkeypatched to raise if called) and
   without emitting `item_submitted`.
3. Non-blank field: monkeypatch `_confirm_discard` to return `False`;
   confirm `_attempt_discard()` leaves the dialog open. Monkeypatch it to
   return `True`; confirm `_attempt_discard()` closes the dialog.
4. Escape key: feed a synthetic `Key_Escape` `QKeyEvent` through
   `eventFilter` with the field non-blank and `_confirm_discard`
   monkeypatched both ways; confirm it follows the same rule as step 3
   (same code path).
5. Regression: submitting non-empty text (button click or Ctrl+Enter)
   still emits `item_submitted` and closes, for both add and edit.
6. Confirm the dialog's window flags no longer include
   `Qt.WindowType.Popup` (`windowFlags() & Qt.WindowType.Popup` is
   falsy).

No step requires a visible window.

## Status

Implemented and verified headlessly (steps 1-6 above, plus a full
`TodoWidget` integration check: opening the real add/edit dialogs off a
`TodoWidget` backed by a temp git repo, confirming button labels and
window type, and a real add-item submit/commit). All passed.

While this was in progress, `TODO.md` was concurrently edited via the
live app (reprioritized `TODO 62e8b05` ahead of this item, and added
`TODO e60817a`, which refines this item's discard-confirmation rule —
dirty-check on edit instead of "any non-whitespace text", plus distinct
confirm messages). Per the user: this item is committed as implemented
(literal "any non-whitespace" rule, as designed above); `TODO e60817a`
picks up the refinement separately, in its own turn, following normal
list order.
