# TODO widget: better-distinguished filter toggle buttons (COMPLETED)

## Summary

TODO 742727d: the filter buttons (Incomplete/Pending/Completed/
Superseded) need a visual frame grouping them as their own section, and
styling that makes their checked/unchecked toggle state obviously
distinct — plain `QPushButton(checkable=True)` with no custom styling
looks nearly identical checked vs. unchecked on some platform styles
(macOS's native style included), so it's currently unclear at a glance
which filters are active.

## Affected files

- `widgets/todo/widget.py` (edit).

## Design

- Wrap the four filter buttons in their own `QFrame`
  (`QFrame.Shape.StyledPanel`), visually separating them from the
  Reload/Add Item action buttons in the same toolbar row.
- A small QSS stylesheet applied to each filter button: a visible border
  in the unchecked state, and a distinct filled background/border color
  when `:checked` — the standard QSS way to make a toggle's on/off state
  unambiguous regardless of platform style. (QSS on native Qt widgets,
  not browser CSS — already this project's established pattern, e.g.
  `DeskPicker`/`_TitleBar`'s own `setStyleSheet` calls; `CLAUDE.md`'s
  "avoid CSS" guidance is about `kind: "html"` browser-widget code.)

## Verification

Headless: construct a `TodoWidget`, confirm the filter buttons are
children of a `QFrame` (not directly in the toolbar layout alongside
Reload/Add Item), and confirm each filter button has a non-empty
stylesheet applied. Regression: confirm toggling a filter button still
correctly shows/hides matching rows (existing `_apply_filter` behavior
unchanged).

## Status

Implemented and verified headlessly: confirmed each filter button's
parent is the new `QFrame` (not the toolbar directly) and each has the
stylesheet applied; confirmed toggling filters still correctly changes
which rows are shown (regression).
