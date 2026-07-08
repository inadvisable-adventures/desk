from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

DEFAULT_LABEL = "untitled"


class _DisplayLabel(QLabel):
    """Plain QLabel, except double-clicking it signals a request to enter
    edit mode (see _TitleRow) -- a QLabel has no click/double-click
    signal of its own."""

    double_clicked = pyqtSignal()

    def mouseDoubleClickEvent(self, event) -> None:
        self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)


class _TitleRow(QWidget):
    """Shows `Scratch: {label}`; double-clicking swaps to an editable
    QLineEdit, committing back to display form on Enter or focus-out.
    Falls back to DEFAULT_LABEL if committed to empty/whitespace-only."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._label_text = DEFAULT_LABEL

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._display = _DisplayLabel()
        self._display.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._display.double_clicked.connect(self._start_editing)

        self._edit = QLineEdit()
        self._edit.returnPressed.connect(self._commit_edit)
        self._edit.editingFinished.connect(self._commit_edit)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._display)
        self._stack.addWidget(self._edit)
        layout.addWidget(self._stack)

        self._refresh_display()

    def _refresh_display(self) -> None:
        self._display.setText(f"Scratch: {self._label_text}")

    def _start_editing(self) -> None:
        self._edit.setText(self._label_text)
        self._edit.selectAll()
        self._stack.setCurrentWidget(self._edit)
        self._edit.setFocus()

    def _commit_edit(self) -> None:
        # editingFinished fires on both Enter and focus-out (including
        # the focus-out caused by switching the stack back to _display
        # below) -- guard so the second firing is a no-op instead of
        # re-reading a field that's already been handled.
        if self._stack.currentWidget() is not self._edit:
            return
        text = self._edit.text().strip()
        self._label_text = text if text else DEFAULT_LABEL
        self._refresh_display()
        self._stack.setCurrentWidget(self._display)

    @property
    def label_text(self) -> str:
        return self._label_text

    def set_label(self, text: str) -> None:
        self._label_text = text.strip() or DEFAULT_LABEL
        self._refresh_display()

    def start_editing(self) -> None:
        """Exposed for headless verification (simulating a double-click
        without constructing a real QMouseEvent)."""
        self._start_editing()


class ScratchWidget(QWidget):
    """A simple multi-line scratch pad with an inline-editable label in
    its title row. See plans/scratch-widget.md."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._title_row = _TitleRow()
        self._body = QPlainTextEdit()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._title_row)
        layout.addWidget(self._body, stretch=1)

    @property
    def label_text(self) -> str:
        return self._title_row.label_text

    def set_label(self, text: str) -> None:
        """Exposed so another widget can spawn a Scratch instance and
        immediately label it -- e.g. the TODO widget's edit-conflict
        handling (TODO d25e557), via DeskWindow.open_widget_content."""
        self._title_row.set_label(text)

    @property
    def body(self) -> QPlainTextEdit:
        return self._body


def build() -> QWidget:
    return ScratchWidget()
