import json
import os
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
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
SAVE_DEBOUNCE_MS = 300


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

    label_changed = pyqtSignal()

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
        self.label_changed.emit()

    @property
    def label_text(self) -> str:
        return self._label_text

    def set_label(self, text: str) -> None:
        self._label_text = text.strip() or DEFAULT_LABEL
        self._refresh_display()
        self.label_changed.emit()

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

        # TODO a7618c8: set by set_backing_file for a Scratch that isn't
        # attached to a tempui file.
        self._backing_file: Path | None = None
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(SAVE_DEBOUNCE_MS)
        self._save_timer.timeout.connect(self.flush_pending_save)
        self._body.textChanged.connect(self._schedule_save)
        self._title_row.label_changed.connect(self._schedule_save)

    def set_backing_file(self, path: Path) -> None:
        """TODO a7618c8: persist this Scratch's label and text in `path`
        (JSON), restoring them from it if it already exists, so they
        survive a Desk restart. Called by `DeskWindow` only for a Scratch
        with no tempui file of its own."""
        self._backing_file = None  # don't write back while loading
        try:
            data = json.loads(path.read_text())
            label, text = str(data.get("label", "")), str(data.get("text", ""))
        except (OSError, ValueError, AttributeError):
            label, text = "", None
        if text is not None:
            self._title_row.set_label(label)
            self._body.setPlainText(text)
            self._body.document().setModified(False)
        self._save_timer.stop()
        self._backing_file = path

    def _schedule_save(self) -> None:
        if self._backing_file is not None:
            self._save_timer.start()

    def flush_pending_save(self) -> None:
        """Writes the backing file now (atomic replace). Also called by
        `DeskWindow` whenever it saves the desk, so a quit never loses
        the last edits to the debounce."""
        self._save_timer.stop()
        path = self._backing_file
        if path is None:
            return
        payload = json.dumps({"label": self.label_text, "text": self._body.toPlainText()})
        tmp = path.with_name(path.name + ".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(payload)
            os.replace(tmp, path)
        except OSError:
            pass

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

    def has_unsaved_local_edits(self) -> bool:
        """Duck-typed hook (TODO 67ab2df) letting `DeskWindow` know a
        blind tempui live-refresh would clobber real, in-progress user
        typing here -- unlike Question/LightningRound, this widget's
        body is a real editable buffer, not a pure re-render of the
        tempui file. `QPlainTextEdit.setPlainText()` (what a tempui
        -triggered refresh calls) always resets `document()
        .isModified()` to `False`; only genuine user edits (typing,
        `insertPlainText`, etc.) set it `True` -- confirmed directly,
        not assumed."""
        return self._body.document().isModified()


def build() -> QWidget:
    return ScratchWidget()
