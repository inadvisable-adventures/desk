"""A single, shared implementation of "show a desk-internal popup"
(TODO 359684f).

Every widget that needed to confirm/warn the user used to construct its
own `QMessageBox` parented to `self` -- the embedded content widget,
living inside a `QGraphicsProxyWidget` on the Workspace Canvas. That
shows as a real top-level macOS window (the native three-dot titlebar
chrome), whose position/size Qt computes from the parent's own
`mapToGlobal` -- a computation that doesn't account for the canvas's
own zoom/pan transform, so at non-1.0 zoom the dialog can render in the
wrong place, or with content that appears to spill outside its own
window bounds.

The fix: one shared service that shows a popup as a `WidgetFrame(...,
is_popup=True)` placed directly on the canvas instead -- it scales and
positions correctly under zoom/pan for free, the same guarantee every
other widget's chrome already has (WidgetFrame.set_view_scale).

Deliberately not Qt-agnostic the way desk_services.file_watcher is: a
popup service's whole job is building and placing a Qt widget frame, so
this module imports PyQt6 and desk.shell.widget_frame.WidgetFrame
directly. It's given the one live WorkspaceView via attach_view()
(dependency injection, not a global import) rather than constructing or
importing one itself.
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QEventLoop, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from desk.shell.widget_frame import TITLEBAR_HEIGHT, WidgetFrame

POPUP_MARGIN = 16
POPUP_SPACING = 12
POPUP_MIN_WIDTH = 320


class _PopupBody(QWidget):
    """The message + button row shown inside a popup's WidgetFrame.
    Escape is treated the same as clicking the close (X) button --
    matching QMessageBox's own Escape-dismisses convention -- both
    resolve the popup with None."""

    def __init__(self, message: str, buttons: list[str], default: str | None, on_result: Callable[[str | None], None]) -> None:
        super().__init__()
        self._on_result = on_result
        self._resolved = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(POPUP_MARGIN, POPUP_MARGIN, POPUP_MARGIN, POPUP_MARGIN)
        layout.setSpacing(POPUP_SPACING)

        label = QLabel(message)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(label, stretch=1)

        button_row = QHBoxLayout()
        button_row.addStretch()
        default_button = None
        for text in buttons:
            button = QPushButton(text)
            button.clicked.connect(lambda _checked=False, t=text: self._resolve(t))
            button_row.addWidget(button)
            if text == default:
                default_button = button
        if default_button is not None:
            default_button.setDefault(True)
            default_button.setFocus()
        layout.addLayout(button_row)

        self.setMinimumWidth(POPUP_MIN_WIDTH)

    def _resolve(self, result: str | None) -> None:
        if self._resolved:
            return
        self._resolved = True
        self._on_result(result)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._resolve(None)
            return
        super().keyPressEvent(event)


class PopupsService:
    """Construct one directly for isolated use (e.g. tests); the app
    itself uses the shared get_service() singleton, attached to the
    single live WorkspaceView at startup (DeskWindow)."""

    def __init__(self) -> None:
        self._view = None

    def attach_view(self, view) -> None:
        self._view = view

    def show(
        self,
        title: str,
        message: str,
        buttons: list[str],
        default: str | None,
        on_result: Callable[[str | None], None],
    ) -> None:
        """Non-blocking: builds and places the popup, returns
        immediately. `on_result` is called exactly once, with the
        clicked button's label, or None if dismissed via the close (X)
        button, Escape, or a Desk switch happening while this popup is
        still open (WorkspaceView.clear_widgets)."""
        if self._view is None:
            raise RuntimeError("PopupsService: no WorkspaceView attached yet")
        view = self._view
        resolved = False

        def resolve(result: str | None) -> None:
            nonlocal resolved
            if resolved:
                return
            resolved = True
            view.popup_closed.disconnect(on_popup_closed)
            view.remove_popup(frame)
            on_result(result)

        def on_popup_closed(closed_frame: WidgetFrame) -> None:
            if closed_frame is frame:
                resolve(None)

        body = _PopupBody(message, buttons, default, resolve)
        frame = WidgetFrame(title, body, is_popup=True)
        frame.resize(max(POPUP_MIN_WIDTH, body.sizeHint().width()), body.sizeHint().height() + TITLEBAR_HEIGHT)
        view.popup_closed.connect(on_popup_closed)
        view.add_popup(frame)
        body.setFocus()

    def show_blocking(
        self, title: str, message: str, buttons: list[str], default: str | None = None
    ) -> str | None:
        """Synchronous convenience for widget call sites that used to
        call QMessageBox.question(...)/.warning(...) and use the return
        value immediately -- runs a nested QEventLoop, quit by the same
        resolver show() already wires up. Not a pre-existing pattern in
        this codebase (no prior QEventLoop usage), but the same idea
        QDialog.exec() already uses internally."""
        loop = QEventLoop()
        result_holder: dict[str, str | None] = {}

        def on_result(result: str | None) -> None:
            result_holder["value"] = result
            loop.quit()

        self.show(title, message, buttons, default, on_result)
        loop.exec()
        return result_holder.get("value")


_service: PopupsService | None = None


def get_service() -> PopupsService:
    """The process-wide shared instance every widget/Bridge-API call
    uses. Lazily constructed (not at import time), same convention as
    desk_services.file_watcher.get_service."""
    global _service
    if _service is None:
        _service = PopupsService()
    return _service
