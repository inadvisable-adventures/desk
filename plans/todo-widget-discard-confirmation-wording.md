# TODO widget discard-confirmation: per-mode wording & real dirty-check (COMPLETED)

## Summary

TODO e60817a: `_ItemDialog`'s discard confirmation (added by TODO
a629bea) currently applies one uniform rule and message to both add and
edit: confirm whenever the field has any non-whitespace content, always
asking "Discard this text?". Refine this per-mode:

- **Add**: confirm exactly when there's non-whitespace content (same
  rule as today) — message becomes **"Discard this new item?"**.
- **Edit**: confirm only when the field's current text has actually
  *changed* from what it was prefilled with (not merely "is non
  -whitespace" — an edit dialog is never prefilled empty, so the old
  rule always confirmed on every edit-discard, even a no-op one) —
  message becomes **"Discard changes?"**.

## Design

`_ItemDialog.__init__` gains an explicit `editing: bool = False` flag
(inferred by the caller, not guessed from `initial_text` — an item's
description is never actually empty, but inferring intent from data
shape is fragile regardless) and keeps the passed-in `initial_text` as
a snapshot (`self._initial_text`) to diff against later.

`_attempt_discard`'s guard becomes a small `_needs_confirmation()`
predicate:
- editing: `self._field.toPlainText() != self._initial_text`
- adding: `bool(self._field.toPlainText().strip())`

`_confirm_discard`'s message is `"Discard changes?"` if editing else
`"Discard this new item?"` (title kept equal to the message, same as
the existing single-message version — the item only specifies message
wording, not a separate title).

`TodoWidget._show_add_dialog`/`_show_edit_dialog` pass `editing=False`/
`editing=True` respectively (add already implicitly defaults `editing`
to `False`, but passing it explicitly at the edit call site is clearer
than relying on a default).

## Affected files

- `widgets/todo/widget.py` — `_ItemDialog` only (`TodoWidget`'s two
  call sites gain one keyword argument each).

## Verification

Entirely headless:

1. Add dialog, empty field, discard: no confirmation prompt (message
   -box call not made).
2. Add dialog, typed content, discard: confirmation prompt shown with
   "Discard this new item?".
3. Edit dialog, no changes made, discard: no confirmation prompt (this
   is the actual behavior change from today, where every edit-discard
   confirmed unconditionally).
4. Edit dialog, content changed, discard: confirmation prompt shown
   with "Discard changes?".
5. Edit dialog, content changed then changed back to the exact original
   text, discard: no confirmation prompt (genuinely no resulting
   change, not just "looks similar").
6. Regression: confirming discard (Yes) still closes the dialog without
   submitting; declining (No) leaves it open with the typed text intact
   in both modes.

## Status

Implemented and verified, entirely headlessly:

1. Add + empty field: no confirmation.
2. Add + typed content: confirms with "Discard this new item?".
3. Edit + unchanged: no confirmation (the actual behavior change —
   previously confirmed unconditionally).
4. Edit + changed: confirms with "Discard changes?".
5. Edit + changed then reverted to the exact original text: no
   confirmation.
6. Regression: declining (No) leaves the dialog open with the typed
   text intact; the existing add/edit/reprioritize/watcher test suites
   (TODO d25e557) all still pass unchanged.
