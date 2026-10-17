# Python/PyQt widget conventions

Guidance for `kind: "python"` widget code (built-in `widgets/`, a project's `desk_widgets/`) and any PyQt
code under `src/desk/` that ends up inside the Workspace Canvas.

## Use `desk.shell.qt_controls`, not the native Qt control

Widget content is embedded in the Workspace Canvas through a `QGraphicsProxyWidget`, scaled by the canvas
zoom. Some native Qt controls go wrong there: they paint with the platform style, and/or open a separate
top-level popup positioned from untransformed screen coordinates. The result is controls that scale oddly,
arrows detached from their rows, and dropdown lists floating away from the control that opened them.

`src/desk/shell/qt_controls/` holds our replacements. **Check it before writing any native-styled control,
and use:**

- `PaintedComboBox` instead of `QComboBox` (`addItem(text, userData)`, `currentIndex`, `currentData`,
  `itemText`, `itemData`, `currentIndexChanged`; add methods as needed).
- `PaintedBranchTreeView` / `PaintedBranchTreeWidget` instead of `QTreeView` / `QTreeWidget` (expand/collapse
  arrows). For a section toggle, paint a `QIcon` rather than using `QToolButton.setArrowType`, whose size
  ignores the font.

If a control you need is missing, add it to that package rather than working around it locally.
`tests/verify/verify_no_raw_qcombobox.py` fails on a raw `QComboBox` anywhere in `src/desk/` or `widgets/`.

## Popups from embedded widgets

A `Qt.WindowType.Popup`/`ToolTip` window opened from embedded content:

- Construct it with `parent=None`. Parenting it to the embedded (alien) `WidgetFrame` makes macOS place it a
  constant offset from where you asked.
- Position it from the control's on-screen rect via proxy -> scene -> view, not `mapToGlobal`.
- With `WA_DeleteOnClose`, emit synchronously right after `close()` and never touch the popup again; defer on
  the long-lived container's side with `desk.shell.qt_utils.deferred`. Never use a `QTimer` closure over the
  popup.

## Verifying UI placement

A passing offscreen test, or Qt's own geometry getters agreeing with what you requested, is not evidence that
a popup landed in the right place; both agreed with the wrong answer in the combo-box investigation. Check
real screen pixels (`QScreen.grabWindow`) or confirm live in Desk. When investigating a UI bug, start on a
branch (`development-process.md`).

See `LEARNINGS.md` for the history behind each rule.
