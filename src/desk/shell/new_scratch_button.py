from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel

# Matches the accent color used by DeskPicker (see desk_picker.py) so
# hover feedback here reads as the same "this is interactive" language
# used elsewhere, not a one-off.
_ACCENT = "61, 174, 233"

BASE_STYLE = (
    "background-color: rgba(40, 42, 46, 220); color: #e8e8e8; font-weight: 600;"
    " padding: 6px 10px; border-radius: 6px;"
)
HOVER_STYLE = (
    f"background-color: rgba({_ACCENT}, 200); color: #ffffff; font-weight: 600;"
    " padding: 6px 10px; border-radius: 6px;"
)


class NewScratchButton(QLabel):
    """A small, always-visible HUD button floating over the Workspace
    Canvas's lower-left corner (a plain child widget of the viewport,
    not a scene item, matching DeskPicker/ZoomControl -- see
    plans/new-scratch-hover-button.md). Clicking it requests a new,
    focused Scratch widget centered in the current viewport."""

    clicked = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setText("+ Scratch")
        # Per CLAUDE.md: labels shouldn't be user-selectable.
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(BASE_STYLE)

    def enterEvent(self, event) -> None:
        self.setStyleSheet(HOVER_STYLE)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.setStyleSheet(BASE_STYLE)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)
