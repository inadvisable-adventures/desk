import uuid

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

TITLEBAR_HEIGHT = 28
HANDLE_THICKNESS = 6
TITLEBAR_FONT_PT = 10
CLOSE_BUTTON_SIZE = 18
MIN_WIDTH = 200
MIN_HEIGHT = 120
BORDER_THICKNESS = 1
BORDER_COLOR = "#4a4d51"
UNFOCUSED_TITLEBAR_COLOR = "#3a3d41"
FOCUSED_TITLEBAR_COLOR = "#4a4e54"


class _TitlebarButton(QWidget):
    """Purely visual: background, cursor shape, and a glyph label.
    Clicking is handled centrally by WorkspaceView (not by this widget
    itself) -- see design-docs/widget-ux.md for why. Shared base for
    the close, bring-to-front, and send-to-back buttons -- each is
    otherwise identical (a constant-screen-size glyph, counter-scaled
    the same way as the rest of the chrome)."""

    def __init__(self, glyph: str, parent=None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._label = QLabel(glyph)
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


class _CloseButton(_TitlebarButton):
    def __init__(self, parent=None) -> None:
        super().__init__("✕", parent)


class _BringToFrontButton(_TitlebarButton):
    def __init__(self, parent=None) -> None:
        super().__init__("▲", parent)


class _SendToBackButton(_TitlebarButton):
    def __init__(self, parent=None) -> None:
        super().__init__("▼", parent)


class _LockButton(_TitlebarButton):
    def __init__(self, parent=None) -> None:
        super().__init__("🔒", parent)


class _UnlockButton(_TitlebarButton):
    def __init__(self, parent=None) -> None:
        super().__init__("🔓", parent)


class _TitleBar(QWidget):
    """Purely visual: background, cursor shape, and a non-selectable title
    label. Dragging is handled centrally by WorkspaceView (not by this
    widget itself) — see design-docs/widget-ux.md for why."""

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self._title = title
        self._external = False
        self.set_focused(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        self._label = QLabel()
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._update_label_text()
        layout.addWidget(self._label)
        layout.addStretch()
        self.lock_button = _LockButton()
        layout.addWidget(self.lock_button)
        self.bring_to_front_button = _BringToFrontButton()
        layout.addWidget(self.bring_to_front_button)
        self.send_to_back_button = _SendToBackButton()
        layout.addWidget(self.send_to_back_button)
        self.close_button = _CloseButton()
        layout.addWidget(self.close_button)
        self.unlock_button = _UnlockButton()
        layout.addWidget(self.unlock_button)
        self.set_locked(False)

        self.apply_scale(1.0)

    def _update_label_text(self) -> None:
        self._label.setText(f"{self._title} [EXTERNAL]" if self._external else self._title)

    def set_external(self, is_external: bool) -> None:
        """Shows/hides the "[EXTERNAL]" marker (TODO a053e3a) -- for a
        widget whose loaded file is outside the current Desk's
        directory."""
        self._external = is_external
        self._update_label_text()

    def set_focused(self, focused: bool) -> None:
        """A subtle background-color shift (TODO 397770c) -- deliberately
        small, not a bold color swap that would compete with the
        widget's own default border (TODO ff6514a) or read as an
        error/warning state. Driven by WorkspaceView's app-wide
        QGraphicsScene.focusItemChanged tracking, not anything this
        class decides on its own."""
        color = FOCUSED_TITLEBAR_COLOR if focused else UNFOCUSED_TITLEBAR_COLOR
        self.setStyleSheet(f"background-color: {color};")

    def set_locked(self, locked: bool) -> None:
        """Shows only the title and an unlock icon while locked (TODO
        8d05920) -- every other button collapses away (a hidden
        QHBoxLayout child takes zero space by default), not just
        visually de-emphasized."""
        self.lock_button.setVisible(not locked)
        self.bring_to_front_button.setVisible(not locked)
        self.send_to_back_button.setVisible(not locked)
        self.close_button.setVisible(not locked)
        self.unlock_button.setVisible(locked)

    def apply_scale(self, view_scale: float) -> None:
        """Counter-scales this titlebar's local height/font so that, once
        the WorkspaceView multiplies by view_scale when rendering, it lands
        back at a constant on-screen size regardless of zoom. See
        design-docs/widget-ux.md."""
        view_scale = view_scale or 1.0
        self.setFixedHeight(max(1, round(TITLEBAR_HEIGHT / view_scale)))
        font_pt = max(1, round(TITLEBAR_FONT_PT / view_scale))
        self._label.setStyleSheet(f"color: #e8e8e8; font-size: {font_pt}pt;")
        self.lock_button.apply_scale(view_scale)
        self.bring_to_front_button.apply_scale(view_scale)
        self.send_to_back_button.apply_scale(view_scale)
        self.close_button.apply_scale(view_scale)
        self.unlock_button.apply_scale(view_scale)


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
        self._last_focused_widget: QWidget | None = None
        self.locked = False
        self._apply_border_scale(1.0)

    def _apply_border_scale(self, view_scale: float) -> None:
        """A small default border (TODO ff6514a) distinguishing this
        widget from the canvas and from adjacent widgets -- counter
        -scaled to a constant on-screen thickness, same convention as
        every other piece of chrome here (see _TitleBar.apply_scale).
        Scoped to the `WidgetFrame` class name, not a bare `QWidget`
        selector, since an unscoped QWidget stylesheet rule cascades
        to every nested child widget (buttons, fields, ...) inside
        arbitrary widget content."""
        view_scale = view_scale or 1.0
        thickness = max(1, round(BORDER_THICKNESS / view_scale))
        self.setStyleSheet(f"WidgetFrame {{ border: {thickness}px solid {BORDER_COLOR}; }}")

    def set_view_scale(self, view_scale: float) -> None:
        for chrome in (self._titlebar, self._left_handle, self._right_handle, self._bottom_handle):
            chrome.apply_scale(view_scale)
        self._apply_border_scale(view_scale)

    def set_external(self, is_external: bool) -> None:
        """Shows/hides the titlebar's "[EXTERNAL]" marker (TODO
        a053e3a). See `desk.shell.window.DeskWindow`'s generic
        `external_changed`-signal binding in `_place_widget`."""
        self._titlebar.set_external(is_external)

    def set_focused(self, focused: bool) -> None:
        """TODO 397770c -- called by WorkspaceView's app-wide
        QGraphicsScene.focusItemChanged tracking, not decided by this
        class itself."""
        self._titlebar.set_focused(focused)

    def set_locked(self, locked: bool) -> None:
        """Locks/unlocks this widget in place (TODO 8d05920): while
        locked, its titlebar shows only the title and an unlock icon
        (`_TitleBar.set_locked`), and WorkspaceView's mouse handling
        skips starting a drag or resize for it (still allows a
        titlebar click to focus its content, TODO a1c701d)."""
        self.locked = locked
        self._titlebar.set_locked(locked)

    @property
    def title(self) -> str:
        """Public read access to this widget's own title (TODO
        f2aede6's UI-element path descriptions want it) -- previously
        only reachable via the private `_titlebar._title`."""
        return self._titlebar._title

    def remember_focused_widget(self, widget: QWidget) -> None:
        """Records the most recently focused descendant inside
        `content` (TODO 397770c) -- also called by WorkspaceView's
        app-wide focus tracking, for `focus_last_widget` (TODO
        a1c701d) to restore later."""
        self._last_focused_widget = widget

    def focus_last_widget(self) -> None:
        """Re-focuses whichever control most recently had focus inside
        this widget (TODO a1c701d) -- triggered by a titlebar click, not
        a drag (see WorkspaceView.mouseReleaseEvent). Falls back to
        `content` itself if nothing has been focused inside this widget
        yet -- harmless even for a widget with no explicit focus proxy
        (Qt just makes the container itself the focus item), correct
        and useful for one that has."""
        target = self._last_focused_widget or self.content
        target.setFocus(Qt.FocusReason.MouseFocusReason)
