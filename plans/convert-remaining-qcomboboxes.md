# Convert remaining `QComboBox` uses (COMPLETED)

TODO a1f2bc7. `widgets/state_manager/widget.py` (two combos) and `widgets/side_by_side/widget.py` (one)
used native `QComboBox`; same canvas-zoom bug class as TODO 5303de6.

## Approach
Swap in `desk.shell.qt_controls.PaintedComboBox`, adding what those widgets use: `addItem(text, userData)`,
`itemData(i)`, `currentData()`, and disabled-state painting (state_manager disables its schema-location
field). Extend `verify_painted_combo.py` for the data API.

## Verification
Headless: `verify_painted_combo.py`, state_manager, side_by_side and state_store scripts. Not looked at live.
