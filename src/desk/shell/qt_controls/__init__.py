"""Qt controls that replace a native Qt widget which misrenders or
misplaces itself when embedded in the Workspace Canvas.

Every control in this package exists because the matching native Qt
widget (`QComboBox`, a `QTreeView`'s branch arrows, a `QToolButton`'s
`setArrowType` arrow, ...) draws with the platform style and/or opens a
separate top-level popup positioned from untransformed screen
coordinates, and both go wrong once the widget is embedded via
`QGraphicsProxyWidget` at a non-1.0 zoom. If you are about to write
`QComboBox`, tree-branch handling, or another native-styled control
inside `src/desk/` or any `widgets/`/`desk_widgets/` widget, check here
first, and add a new control here (rather than working around it
locally) if one is missing.

- `PaintedComboBox` -- replaces `QComboBox` (TODO 0f2c458, 5303de6).
- `PaintedBranchTreeView`/`PaintedBranchTreeWidget` -- replace the
  native branch arrows of `QTreeView`/`QTreeWidget` (TODO b927389,
  333bebf).

See LEARNINGS.md for the history behind each, and
`python-widget-conventions.md` (once written; TODO d4c0d68) for the
rule. `zoom_control.py` is unrelated and deliberately not here.
"""

from desk.shell.qt_controls.painted_branches import PaintedBranchTreeView, PaintedBranchTreeWidget
from desk.shell.qt_controls.painted_combo import PaintedComboBox

__all__ = ["PaintedBranchTreeView", "PaintedBranchTreeWidget", "PaintedComboBox"]
