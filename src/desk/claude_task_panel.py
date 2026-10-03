"""Background-tasks panel for the Claude (Desk) widget (TODO 90efef6): a
scroll area of framed per-task items, replacing a one-line-per-task
QListWidget. See plans/claude-desk-task-panel-and-log-widget.md.

Each item shows "[status] description" and a *tail* preview of the task's
own log (what it's doing now, not what it started with -- the reverse of
claude_history_view.collapse_preview). There is deliberately no inline
expansion: hovering reveals a "View Log" button, and a double-click does the
same thing, both emitting `view_log_requested(task_id)` for the owner to open
a separate log widget.
"""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from desk.claude_history_view import PREVIEW_LINES, PREVIEW_MAX_CHARS

TERMINAL_STATUSES = ("completed", "failed", "killed", "stopped", "cancelled")
NO_LOG_TEXT = "(no activity yet)"


def tail_preview(lines: list[str], max_lines: int = PREVIEW_LINES, max_chars: int = PREVIEW_MAX_CHARS) -> str:
    """The last `max_lines` of `lines` (each capped), prefixed with "…" if
    anything earlier was dropped; NO_LOG_TEXT for an empty log."""
    if not lines:
        return NO_LOG_TEXT
    tail = [line if len(line) <= max_chars else line[: max_chars - 1].rstrip() + "…" for line in lines[-max_lines:]]
    return ("…\n" if len(lines) > max_lines else "") + "\n".join(tail)


class TaskEntry(QFrame):
    view_log_requested = pyqtSignal(str)

    def __init__(self, task_id: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.task_id = task_id
        self.setObjectName("taskEntry")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.setStyleSheet("QFrame#taskEntry { border-top: 1px solid rgba(128,128,128,0.25); }")

        # Chrome labels aren't selectable (CLAUDE.md); the log preview is content.
        self._title = QLabel()
        self._title.setStyleSheet("font-weight: 600;")
        self._title.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._view_log_button = QPushButton("View Log")
        self._view_log_button.setFlat(True)
        self._view_log_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._view_log_button.setVisible(False)
        self._view_log_button.clicked.connect(self._request)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(self._title, stretch=1)
        header.addWidget(self._view_log_button)

        self._preview = QLabel()
        self._preview.setTextFormat(Qt.TextFormat.PlainText)
        self._preview.setWordWrap(True)
        self._preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(1)
        layout.addLayout(header)
        layout.addWidget(self._preview)

    def update_task(self, task: dict, log_lines: list[str]) -> None:
        status = task.get("status", "pending")
        title = f"[{status}] {task.get('description') or self.task_id}"
        self._title.setText(title)
        self._preview.setText(tail_preview(log_lines))
        self.setStyleSheet(
            "QFrame#taskEntry { border-top: 1px solid rgba(128,128,128,0.25); "
            + ("background: rgba(128,128,128,0.08); " if status in TERMINAL_STATUSES else "")
            + "}"
        )

    def title_text(self) -> str:
        return self._title.text()

    def preview_text(self) -> str:
        return self._preview.text()

    def _request(self) -> None:
        self.view_log_requested.emit(self.task_id)

    def enterEvent(self, event) -> None:
        self._view_log_button.setVisible(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._view_log_button.setVisible(False)
        super().leaveEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        self._request()


class TaskPanel(QScrollArea):
    """One TaskEntry per task, in first-seen order."""

    view_log_requested = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        container = QWidget()
        self._layout = QVBoxLayout(container)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._layout.addStretch(1)
        self.setWidget(container)
        self._entries: dict[str, TaskEntry] = {}

    def set_task(self, task_id: str, task: dict, log_lines: list[str]) -> TaskEntry:
        entry = self._entries.get(task_id)
        if entry is None:
            entry = TaskEntry(task_id)
            entry.view_log_requested.connect(self.view_log_requested)
            self._layout.insertWidget(self._layout.count() - 1, entry)
            self._entries[task_id] = entry
        entry.update_task(task, log_lines)
        return entry

    def entries(self) -> list[TaskEntry]:
        return list(self._entries.values())

    def entry(self, task_id: str) -> TaskEntry | None:
        return self._entries.get(task_id)

    def count(self) -> int:
        return len(self._entries)
