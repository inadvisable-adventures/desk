# TODO widget: items should look like items, not lines of text (COMPLETED)

## Summary

TODO 0f9445c: each row in the TODO widget's list should visually read as
a distinct, draggable item — a small frame around each one — rather than
plain unstyled lines of text with no visual separation.

## Affected files

- `widgets/todo/widget.py` (edit).

## Design

Style via `QListWidget::item` QSS (Qt's standard sub-control selector for
per-row styling — no need for a custom item delegate/widget-per-row for
a purely visual change like this): a visible border, rounded corners,
padding, and a distinct `:selected` background, plus `QListWidget
.setSpacing(...)` so adjacent items have a visible gap between their
frames instead of touching edge-to-edge. Applied once, to the list
itself, not per-item.

## Verification

Headless: confirm the list widget's stylesheet includes `QListWidget::
item` framing rules and that `setSpacing()` is set to a non-zero value.
Regression: confirm the list still populates, filters, reorders
(drag-and-drop), and opens the edit dialog on double-click exactly as
before — a styling-only change shouldn't touch any of that behavior.

## Status

Implemented and verified headlessly: confirmed the framing stylesheet
and non-zero spacing are applied; confirmed filtering, `InternalMove`
drag-and-drop mode, and double-click-to-edit all still work unchanged.
