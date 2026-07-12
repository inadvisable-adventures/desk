import logging
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from desk.shell import current_context
from desk.stack_file import StackFrame, parse_stack_file, render_stack_file

logger = logging.getLogger(__name__)

TIMESTAMP_FORMAT = "%Y-%m-%dT%H-%M-%S"


class _FrameRow(QWidget):
    """One stack frame: an editable title + editable multi-line notes."""

    def __init__(self, title: str = "", notes: str = "", parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        self.title_edit = QLineEdit(title)
        self.title_edit.setPlaceholderText("Discussion title…")
        font = self.title_edit.font()
        font.setBold(True)
        self.title_edit.setFont(font)
        layout.addWidget(self.title_edit)

        self.notes_edit = QPlainTextEdit(notes)
        self.notes_edit.setPlaceholderText("Notes…")
        self.notes_edit.setFixedHeight(100)
        layout.addWidget(self.notes_edit)

    def to_frame(self) -> StackFrame:
        return StackFrame(
            title=self.title_edit.text().strip() or "(untitled)",
            notes=self.notes_edit.toPlainText(),
        )


class StackWidget(QWidget):
    """A LIFO stack of "discussion" frames (title + free-form notes) for
    tracking nested lines of investigation -- Push to go one level
    deeper, Pop to step back out to the parent. Persisted via
    widget-local storage (TODO fb76057). See plans/stack-widget.md."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._last_dir = current_context.get_current_desk_directory() or Path.home()
        # Index 0 = bottom of stack (oldest), last = top (current) --
        # the top is always shown at the top of the visual list.
        self._rows: list[_FrameRow] = []

        push_button = QPushButton("Push")
        push_button.clicked.connect(self._push)
        pop_button = QPushButton("Pop")
        pop_button.clicked.connect(self._pop)
        save_button = QPushButton("Save as Markdown")
        save_button.clicked.connect(self._save_as_markdown)
        load_button = QPushButton("Load…")
        load_button.clicked.connect(self._load)

        toolbar = QHBoxLayout()
        toolbar.addWidget(push_button)
        toolbar.addWidget(pop_button)
        toolbar.addStretch()
        toolbar.addWidget(save_button)
        toolbar.addWidget(load_button)

        self._status_label = QLabel()
        self._status_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        self._rows_container = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(0)
        self._rows_layout.addStretch(1)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setWidget(self._rows_container)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(toolbar)
        layout.addWidget(self._scroll, stretch=1)
        layout.addWidget(self._status_label)

        self._update_empty_placeholder()

    # -- stack manipulation, top of stack = top of the visual list -----

    def _push(self) -> None:
        row = _FrameRow()
        self._rows.append(row)
        self._rows_layout.insertWidget(0, row)
        self._update_empty_placeholder()
        row.title_edit.setFocus()

    def _pop(self) -> None:
        if not self._rows:
            return
        row = self._rows.pop()
        self._rows_layout.removeWidget(row)
        row.deleteLater()
        self._update_empty_placeholder()

    def _update_empty_placeholder(self) -> None:
        self._status_label.setText("(empty stack -- click Push to start)" if not self._rows else "")

    # -- export/import --------------------------------------------------

    def _current_frames(self) -> list[StackFrame]:
        return [row.to_frame() for row in self._rows]

    def _save_as_markdown(self) -> None:
        directory = current_context.get_current_desk_directory() or Path.cwd()
        timestamp = datetime.now().strftime(TIMESTAMP_FORMAT)
        target = directory / f"STACK-{timestamp}.md"
        try:
            target.write_text(render_stack_file(self._current_frames()))
        except OSError as error:
            logger.error("Failed to save stack to %s", target, exc_info=True)
            QMessageBox.warning(self, "Save as Markdown", f"Could not save: {error}")
            return
        self._status_label.setText(f"Saved to {target.name}")

    def _load(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Load Stack", str(self._last_dir), "Markdown (*.md);;All files (*)"
        )
        if not filename:
            return
        if self._rows:
            result = QMessageBox.question(
                self, "Load Stack", "Loading will replace the current stack. Continue?"
            )
            if result != QMessageBox.StandardButton.Yes:
                return
        path = Path(filename)
        self._last_dir = path.parent
        try:
            frames = parse_stack_file(path.read_text())
        except OSError as error:
            logger.error("Failed to load stack from %s", path, exc_info=True)
            QMessageBox.warning(self, "Load Stack", f"Could not read: {error}")
            return
        self._replace_frames(frames)

    # -- widget-local storage (TODO fb76057) ----------------------------

    def get_widget_local_storage(self) -> dict:
        return {"frames": [{"title": f.title, "notes": f.notes} for f in self._current_frames()]}

    def set_widget_local_storage(self, data: dict) -> None:
        frames = [
            StackFrame(title=entry.get("title", ""), notes=entry.get("notes", ""))
            for entry in data.get("frames", [])
        ]
        self._replace_frames(frames)

    def _replace_frames(self, frames: list[StackFrame]) -> None:
        for row in self._rows:
            self._rows_layout.removeWidget(row)
            row.deleteLater()
        self._rows = []
        for frame in frames:
            row = _FrameRow(frame.title, frame.notes)
            self._rows.append(row)
            # Same order _push() itself uses -- inserting each new row at
            # position 0 in turn reconstructs the exact layout sequential
            # pushes would have produced, so the last (topmost) frame ends
            # up visually first.
            self._rows_layout.insertWidget(0, row)
        self._update_empty_placeholder()


def build() -> QWidget:
    return StackWidget()
