# Static check: no raw `QComboBox` (COMPLETED)

TODO 21e6e04, from `../FEEDBACK/FEEDBACK-DESK-painted-combo-crash-and-enforcement-gap-2026-10-16-1836.md`.

## Approach
`tests/verify/verify_no_raw_qcombobox.py`: substring scan of every `.py` under `src/desk/` and `widgets/`
except `src/desk/shell/qt_controls/`; fails listing `file:line`. Comments/docstrings count, so
`desk_picker.py`'s docstring was reworded earlier (same meaning, no token) instead of allowlisted.
A sanity floor (>= 50 files scanned) guards against wrong scan roots.

## Verification
Passes now; confirmed it fails against the pre-conversion code (3 offending lines in the two widgets).
Does not reach project `desk_widgets/` code (parked: runtime warning).
