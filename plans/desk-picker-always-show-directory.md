# Desk picker: always show name and directory, even collapsed (COMPLETED)

## Summary

TODO 6034b1d: the top-left Desk picker should always show both the
current Desk's name *and* its associated directory, even when not
hovered. Currently the collapsed label shows only the name, and no state
(collapsed or hovered/expanded) ever displays the directory as readable
text at all — the expanded state only offers a *button* to change it, not
a display of what it currently is.

## Affected files

- `src/desk/shell/desk_picker.py` (edit).
- `src/desk/shell/window.py` (edit) — `_refresh_picker` passes the
  directory through too.
- `design-docs/widget-ux.md` (edit) — Desk Picker section no longer
  matches this behavior once changed.

## Design

- `DeskPicker.set_current(name, directory)`: gains a required `directory:
  Path` parameter; the label text becomes `f"{name} — {directory}"`
  instead of just `name`.
- `_set_expanded`: no longer hides the label on hover
  (`self._label.setVisible(not expanded)` removed) — the label (name +
  directory) is now always visible; hover still additionally shows the
  dropdown/directory-picker button alongside it, rather than replacing
  it. This is the actual behavior change "even when not hovered" calls
  for: previously the label (the *only* thing that ever showed the name)
  disappeared entirely while hovering.
- `DeskWindow._refresh_picker()` passes `self.current_desk.directory`
  through to the updated `set_current` call.

Not adding directory truncation/elision for long paths — not asked for,
and the picker's own `adjustSize()` (already fixed by TODO 4adfcad)
already correctly grows to fit whatever text is set.

## Verification

Headless: confirm `set_current(name, directory)` produces a label
containing both the name and the directory string; confirm the label
stays visible after `_set_expanded(True)` (hover) — regression against
the specific "disappears on hover" behavior being removed; confirm the
dropdown/button still correctly show only when expanded (that part of
the toggle is unchanged). Regression: confirm `DeskWindow` still
correctly resolves and displays the right name/directory for the actual
current Desk.

## Status

Implemented and verified headlessly: confirmed the label shows both name
and directory; confirmed it stays visible through `_set_expanded(True)`/
`(False)` while the dropdown/button correctly toggle with hover as
before. Full-app regression: a real `DeskWindow` correctly shows the
actual current Desk's name and directory in the label.
