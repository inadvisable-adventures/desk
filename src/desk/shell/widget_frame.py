import uuid

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

TITLEBAR_HEIGHT = 28
HANDLE_THICKNESS = 6
TITLEBAR_FONT_PT = 10
CLOSE_BUTTON_SIZE = 18
MIN_WIDTH = 200
MIN_HEIGHT = 120


class _CloseButton(QWidget):
    """Purely visual: background, cursor shape, and an 'x' glyph. Clicking
    is handled centrally by WorkspaceView (not by this widget itself) --
    see design-docs/widget-ux.md for why."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._label = QLabel("✕")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        layout.addWidget(self._label)

        self.apply_scale(1.0)

    def apply_scale(self, view_scale: float) -> None:
        """See _TitleBar.apply_scale: keeps this button a constant
        on-screen size regardless of the WorkspaceView's current zoom."""
        view_scale = view_scale or 1.0
        size = max(1, round(CLOSE_BUTTON_SIZE / view_scale))
        self.setFixedSize(size, size)
        font_pt = max(1, round(TITLEBAR_FONT_PT / view_scale))
        self._label.setStyleSheet(f"color: #e8e8e8; font-size: {font_pt}pt;")


class _TitleBar(QWidget):
    """Purely visual: background, cursor shape, and a non-selectable title
    label. Dragging is handled centrally by WorkspaceView (not by this
    widget itself) — see design-docs/widget-ux.md for why."""

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setStyleSheet("background-color: #3a3d41;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        self._label = QLabel(title)
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        layout.addWidget(self._label)
        layout.addStretch()
        self.close_button = _CloseButton()
        layout.addWidget(self.close_button)

        self.apply_scale(1.0)

    def apply_scale(self, view_scale: float) -> None:
        """Counter-scales this titlebar's local height/font so that, once
        the WorkspaceView multiplies by view_scale when rendering, it lands
        back at a constant on-screen size regardless of zoom. See
        design-docs/widget-ux.md."""
        view_scale = view_scale or 1.0
        self.setFixedHeight(max(1, round(TITLEBAR_HEIGHT / view_scale)))
        font_pt = max(1, round(TITLEBAR_FONT_PT / view_scale))
        self._label.setStyleSheet(f"color: #e8e8e8; font-size: {font_pt}pt;")
        self.close_button.apply_scale(view_scale)


class _ResizeHandle(QWidget):
    """Purely visual: background and cursor shape. Resizing is handled
    centrally by WorkspaceView (not by this widget itself) — see
    design-docs/widget-ux.md for why."""

    def __init__(self, edge: str, parent=None) -> None:
        super().__init__(parent)
        self.edge = edge
        self.setStyleSheet("background-color: #2a2d2f;")
        if edge in ("left", "right"):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        else:
            self.setCursor(Qt.CursorShape.SizeVerCursor)

        self.apply_scale(1.0)

    def apply_scale(self, view_scale: float) -> None:
        """See _TitleBar.apply_scale: keeps this handle a constant on-screen
        thickness regardless of the WorkspaceView's current zoom."""
        view_scale = view_scale or 1.0
        thickness = max(1, round(HANDLE_THICKNESS / view_scale))
        if self.edge in ("left", "right"):
            self.setFixedWidth(thickness)
        else:
            self.setFixedHeight(thickness)


class WidgetFrame(QWidget):
    """Wraps any widget content (a PythonWidgetHost or ChromiumWidget) with
    the common Desk widget chrome: a draggable titlebar and left/right/
    bottom resize handles. Built once at the canvas-integration layer
    (WorkspaceView.add_widget) rather than duplicated per widget kind. See
    design-docs/widget-ux.md.

    The chrome (titlebar, resize handles) stays a constant size on screen
    regardless of the Workspace Canvas's zoom level — see set_view_scale.
    Only the wrapped content zooms/pans with the view.

    Note: the chrome widgets here are purely visual. Drag/resize
    interaction is handled centrally by WorkspaceView's own mouse events,
    not by these embedded widgets' own mouse events — see
    design-docs/widget-ux.md for why (embedded-widget mouse events don't
    reliably reflect real screen coordinates at non-unity view scale)."""

    def __init__(
        self, title: str, content: QWidget, instance_id: str | None = None, parent=None
    ) -> None:
        super().__init__(parent)
        self.instance_id = instance_id or uuid.uuid4().hex[:8]
        content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._titlebar = _TitleBar(title)
        outer.addWidget(self._titlebar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self._left_handle = _ResizeHandle("left")
        body.addWidget(self._left_handle)
        body.addWidget(content, stretch=1)
        self._right_handle = _ResizeHandle("right")
        body.addWidget(self._right_handle)
        outer.addLayout(body, stretch=1)

        self._bottom_handle = _ResizeHandle("bottom")
        outer.addWidget(self._bottom_handle)

        self.content = content

    def set_view_scale(self, view_scale: float) -> None:
        for chrome in (self._titlebar, self._left_handle, self._right_handle, self._bottom_handle):
            chrome.apply_scale(view_scale)
