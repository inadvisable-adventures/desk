# TODO widget: larger, multiline add/edit textbox (COMPLETED)

## Summary

TODO 8db7891: the add/edit dialog's (`_ItemDialog`) text field should be
much larger and multiline — currently a single-line `QLineEdit`, cramped
for anything beyond a short one-liner.

## Affected files

- `widgets/todo/widget.py` (edit).

## Design

- `_ItemDialog._field`: `QLineEdit` → `QPlainTextEdit`, resized larger
  (both the field itself, via `setMinimumSize`, and the popup dialog as a
  whole, via `resize`).
- Text access: `.text()`/`.setText(...)` → `.toPlainText()`/
  `.setPlainText(...)`.
- Key handling changes now that the field is multiline: plain
  `Return`/`Enter` must insert a newline (normal multiline editing),
  not submit — only intercept `Ctrl+Return`/`Ctrl+Enter` (Qt's
  `ControlModifier`, which is Cmd on macOS via Qt's own platform
  abstraction) as the submit shortcut. `Escape` still cancels. The
  explicit "Add"/submit button is unchanged and still works by click
  regardless of keyboard shortcut.
- `selectAll()` on initial text (used for the edit-dialog case) works the
  same way on `QPlainTextEdit` as it did on `QLineEdit`.

## Verification

Headless: confirm the dialog's field is a `QPlainTextEdit` sized larger
than the old default; confirm plain Return inserts a newline rather than
submitting (field still open, text contains `\n`); confirm Ctrl+Return
submits; confirm Escape still cancels. Regression: confirm add and edit
(TODO d1205ef/d49f1cf) both still work end-to-end with the new field
type.

## Status

Implemented and verified headlessly:

1. Confirmed the field is a `QPlainTextEdit` with the new, larger
   minimum size.
2. Confirmed plain `Return` is *not* intercepted (returns `False` from
   `eventFilter`, letting `QPlainTextEdit` insert a newline natively) and
   doesn't submit; confirmed `Ctrl+Return` does submit; confirmed
   `Escape` still cancels without submitting.
3. Regression: add and edit both still work end-to-end. One clarified,
   pre-existing (not new) behavior along the way: a multi-line
   description is correctly preserved verbatim in the file itself
   (`raw_text`), but `parse_todo_file`'s own `.description` field is —
   as it always has been — whitespace-collapsed (including newlines) for
   display/truncation purposes; that's unrelated to this change and was
   already true before it.
