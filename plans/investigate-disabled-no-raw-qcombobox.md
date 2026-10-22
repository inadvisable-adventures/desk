# (COMPLETED) Investigate disabled `verify_no_raw_qcombobox` (TODO `118d5ab`)

## Summary

`tests/verify/verify_no_raw_qcombobox.py` (from TODO `21e6e04`) was renamed
`disabled_verify_no_raw_qcombobox.py` because it fails on `QComboBox` mentions in
`src/desk/temp_ui.py`'s doc/changelog strings and comments (added by TODO `d4c0d68`), not on
real widget code. Suspected scanner false positive.

## Steps

1. Run it and list every flagged line; confirm none is a real `QComboBox(` use/import.
2. Make the scan AST-based (flag real names/imports only, ignore strings and comments), or
   exempt documentation text explicitly.
3. Confirm it still catches a deliberately planted raw `QComboBox` use.
4. Rename back to `verify_no_raw_qcombobox.py`, remove the DISABLED note.

## Affected files

- `tests/verify/disabled_verify_no_raw_qcombobox.py`

## Outcome (2026-10-21)

The script already passed when run: it had since gained a `temp_ui.py` allow-list, so the original
prose failure was stale. That whole-file exemption would still hide a real use in `temp_ui.py`, so the
scan is now AST-based (names, attributes, imports; comments and strings ignored) with no allow-list
beyond `qt_controls/`, plus in-script assertions that it catches planted uses and ignores prose.
Renamed back to `verify_no_raw_qcombobox.py`; the DISABLED note is gone.
