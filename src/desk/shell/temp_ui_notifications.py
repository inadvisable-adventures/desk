from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

BANNER_STYLE = """
QFrame {
    background-color: rgba(40, 42, 46, 230);
    border: 1px solid #3daee9;
    border-radius: 6px;
}
QLabel {
    color: #e8e8e8;
}
"""


class _NotificationBanner(QFrame):
    """A single dismissable, clickable notification -- purely visual and
    "dumb": TempUiNotificationStack decides what a click/dismiss means."""

    clicked = pyqtSignal()
    dismissed = pyqtSignal()

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(BANNER_STYLE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 6, 6)
        layout.setSpacing(6)

        label = QLabel(text)
        label.setWordWrap(True)
        label.setMaximumWidth(260)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        layout.addWidget(label, stretch=1)

        close_button = QPushButton("✕")
        close_button.setFlat(True)
        close_button.setFixedSize(18, 18)
        close_button.clicked.connect(self.dismissed.emit)
        layout.addWidget(close_button)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class TempUiNotificationStack(QWidget):
    """Persistent, per-file temp-UI notification banners (TODO a02b001),
    stacked vertically in the app's upper-right corner -- a new
    notification for a file already showing one replaces it in place
    rather than stacking a duplicate. A "dumb" UI component like
    DeskPicker/ZoomControl: WorkspaceView positions it (see
    canvas.py's _position_temp_ui_notifications); DeskWindow decides what
    a clicked banner actually does."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._banners: dict[Path, _NotificationBanner] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)

    def notify(self, path: Path, text: str, on_clicked: Callable[[], None]) -> None:
        self._remove_banner(path)

        banner = _NotificationBanner(text, self)
        banner.clicked.connect(lambda: self._handle_click(path, on_clicked))
        banner.dismissed.connect(lambda: self._remove_banner(path))
        self.layout().addWidget(banner)
        self._banners[path] = banner
        self.adjustSize()

    def _handle_click(self, path: Path, on_clicked: Callable[[], None]) -> None:
        on_clicked()
        self._remove_banner(path)

    def _remove_banner(self, path: Path) -> None:
        banner = self._banners.pop(path, None)
        if banner is not None:
            self.layout().removeWidget(banner)
            banner.deleteLater()
            self.adjustSize()
