import logging
import subprocess
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desk.file_watch import SingleFileWatcher
from desk.git_utils import find_git_root
from desk.questions_file import (
    QuestionEntry,
    find_nearest_questions_file,
    parse_questions_file,
    render_questions_file,
    with_answer,
)
from desk.shell import current_context

logger = logging.getLogger(__name__)

ENTRY_ROLE = Qt.ItemDataRole.UserRole
FILTERS = ("unanswered", "answered", "all")

# Same rationale as the TODO widget's own FILTER_BUTTON_STYLE (see
# widgets/todo/widget.py) -- a plain checkable QPushButton looks nearly
# identical checked vs. unchecked on some platform styles.
FILTER_BUTTON_STYLE = """
QPushButton {
    padding: 3px 10px;
    border: 1px solid #888;
    border-radius: 3px;
    background-color: transparent;
}
QPushButton:checked {
    background-color: #3daee9;
    color: white;
    border-color: #2a8cc4;
}
"""

ITEM_LIST_STYLE = """
QListWidget::item {
    border: 1px solid #888;
    border-radius: 4px;
    padding: 4px;
}
QListWidget::item:selected {
    background-color: #3daee9;
    color: white;
}
"""
ITEM_LIST_SPACING = 3


def _git_commit(questions_path: Path, message: str) -> bool:
    """Returns whether a real commit was made. False (not an error) if
    the target directory isn't a git repo -- mirrors
    widgets/todo/widget.py's _git_commit."""
    root = find_git_root(questions_path.parent)
    if root is None:
        return False
    try:
        subprocess.run(
            ["git", "-C", str(root), "add", str(questions_path)], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "-C", str(root), "commit", "-m", message], check=True, capture_output=True
        )
        return True
    except subprocess.CalledProcessError:
        return False


# Serializes git subprocess calls made by background threads started from
# _write_and_commit -- same rationale as the TODO widget's _GIT_LOCK.
_GIT_LOCK = threading.Lock()


def _write_and_commit(
    state: dict,
    message: str,
    watcher: SingleFileWatcher | None = None,
    on_committed: Callable[[bool], None] | None = None,
) -> threading.Thread | None:
    """Module-level (not a method) so the destroyed-triggered teardown
    closure can call it without touching `self` -- mirrors
    widgets/todo/widget.py's _write_and_commit exactly, adapted for
    QUESTIONS.md's own parse/render functions."""
    questions_path = state["questions_path"]
    if questions_path is None:
        return None
    text = render_questions_file(state["preamble"], state["entries"])
    questions_path.write_text(text)
    if watcher is not None:
        watcher.record_own_write(text)

    def run() -> None:
        with _GIT_LOCK:
            committed = _git_commit(questions_path, message)
        if on_committed is not None:
            on_committed(committed)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


class _CommitResultRelay(QObject):
    """A dedicated QObject purely to own a pyqtSignal, so a background
    commit thread can report its result back onto the GUI thread safely
    -- mirrors widgets/todo/widget.py's _CommitResultRelay."""

    finished = pyqtSignal(bool)


class _AnswerDialog(QWidget):
    """A small hovering popup for answering (or re-answering) one
    question entry: the question's own text is shown read-only (but
    still selectable/copyable, in case the user wants to quote part of
    it back), with an editable field below for the answer, pre-filled
    with the current answer if there is one. Same floating Tool-window
    shape as the TODO widget's _ItemDialog (must not dismiss on
    click-away) -- see that class's docstring and LEARNINGS.md for why
    a Popup won't do."""

    answer_submitted = pyqtSignal(str)

    def __init__(self, parent=None, title: str = "", body: str = "", initial_answer: str = "") -> None:
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(460, 420)
        self._initial_answer = initial_answer

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        title_label = QLabel(title)
        title_label.setWordWrap(True)
        title_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(title_label)

        self._body = QPlainTextEdit()
        self._body.setPlainText(body)
        self._body.setReadOnly(True)
        self._body.setMaximumHeight(180)
        layout.addWidget(self._body)

        layout.addWidget(QLabel("Answer:"))
        self._answer_field = QPlainTextEdit()
        self._answer_field.setPlaceholderText("Type an answer… (Ctrl+Enter to submit)")
        self._answer_field.setPlainText(initial_answer)
        self._answer_field.setMinimumHeight(120)
        self._answer_field.installEventFilter(self)
        layout.addWidget(self._answer_field, stretch=1)

        button_row = QHBoxLayout()
        discard = QPushButton("Discard")
        discard.clicked.connect(self._attempt_discard)
        button_row.addWidget(discard)
        submit = QPushButton("Save Answer")
        submit.clicked.connect(self._submit)
        button_row.addWidget(submit)
        layout.addLayout(button_row)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Deferred for the same reason as _ItemDialog's showEvent -- see
        # widgets/todo/widget.py.
        QTimer.singleShot(0, self._claim_focus)

    def _claim_focus(self) -> None:
        self.raise_()
        self.activateWindow()
        self._answer_field.setFocus()

    def current_text(self) -> str:
        """The field's live, possibly-unsaved answer text -- exposed for
        edit-conflict handling, mirroring _ItemDialog.current_text()."""
        return self._answer_field.toPlainText()

    def _submit(self) -> None:
        self.answer_submitted.emit(self._answer_field.toPlainText().strip())
        self.close()

    def _attempt_discard(self) -> None:
        if self._answer_field.toPlainText() != self._initial_answer and not self._confirm_discard():
            return
        self.close()

    def _confirm_discard(self) -> bool:
        """Split out so headless verification can monkeypatch just this
        one method instead of driving a real modal QMessageBox --
        mirrors _ItemDialog._confirm_discard."""
        message = "Discard changes to this answer?"
        return (
            QMessageBox.question(
                self,
                message,
                message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        )

    def eventFilter(self, obj, event) -> bool:
        if obj is self._answer_field and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    self._submit()
                    return True
                return False
            if event.key() == Qt.Key.Key_Escape:
                self._attempt_discard()
                return True
        return super().eventFilter(obj, event)


class QuestionsWidget(QWidget):
    """Reads the nearest QUESTIONS.md relative to the current Desk's
    directory (desk.shell.current_context) and displays it as a
    filterable list of question entries the user can answer. See
    plans/questions-widget.md -- mirrors widgets/todo/widget.py's
    overall shape (file watching, external-path indicator, git-commit
    -backed writes) adapted for QUESTIONS.md's own format (answered/
    unanswered rather than TODO.md's four-way status, no drag-reorder
    since entry order isn't a priority signal here)."""

    external_path_changed = pyqtSignal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._filter_buttons: dict[str, QPushButton] = {}

        # Plain dict (not Qt state), same rationale as TodoWidget's
        # _state -- safe to read from the destroyed-triggered teardown
        # closure after this widget is gone.
        self._state = {
            "questions_path": None,
            "preamble": "",
            "entries": [],
        }

        # A stable per-entry key (todo_ids tuple) -> (dialog, original
        # answer as loaded) for every currently-open answer dialog --
        # lets an external-change notification tell whether it actually
        # conflicts with an in-progress edit. Mirrors TodoWidget's
        # _open_edits.
        self._open_edits: dict[tuple, tuple["_AnswerDialog", str]] = {}
        self._watcher = SingleFileWatcher(self)
        self._watcher.changed.connect(self._on_external_change)

        self._status_label = QLabel()
        self._status_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._timestamp_label = QLabel()
        self._timestamp_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._timestamp_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        filter_frame = QFrame()
        filter_frame.setFrameShape(QFrame.Shape.StyledPanel)
        filter_layout = QHBoxLayout(filter_frame)
        filter_layout.setContentsMargins(4, 4, 4, 4)
        filter_layout.setSpacing(4)
        for name in FILTERS:
            button = QPushButton(name.capitalize())
            button.setCheckable(True)
            button.setChecked(name == "unanswered")
            button.setStyleSheet(FILTER_BUTTON_STYLE)
            button.toggled.connect(self._apply_filter)
            filter_layout.addWidget(button)
            self._filter_buttons[name] = button

        toolbar = QHBoxLayout()
        toolbar.addWidget(filter_frame)
        toolbar.addStretch()

        self._list = QListWidget()
        self._list.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self._list.setStyleSheet(ITEM_LIST_STYLE)
        self._list.setSpacing(ITEM_LIST_SPACING)
        self._list.itemDoubleClicked.connect(self._show_answer_dialog)

        # A single floating "Discuss" button that follows the hovered
        # row (TODO 46e1b42), mirroring widgets/todo/widget.py's own
        # "📄 Plan" button -- not a per-row setItemWidget, matching that
        # sibling widget's established convention. Shown over every
        # entry (unlike the Plan button, which only shows for entries
        # that have one) -- clicking it starts a new claude session to
        # discuss that entry, via the same flow as the tempui
        # DiscussParkingLotItem keyword (TODO c0875bc).
        self._list.setMouseTracking(True)
        self._list.viewport().setMouseTracking(True)
        self._list.itemEntered.connect(self._on_item_entered)
        self._list.viewport().installEventFilter(self)
        self._list.verticalScrollBar().valueChanged.connect(self._hide_discuss_button)
        self._discuss_button = QPushButton("Discuss", self._list.viewport())
        self._discuss_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._discuss_button.hide()
        self._discuss_button.clicked.connect(self._discuss_hovered_entry)
        self._discuss_item: QListWidgetItem | None = None

        status_row = QHBoxLayout()
        status_row.addWidget(self._status_label, 1)
        status_row.addWidget(self._timestamp_label)

        layout = QVBoxLayout(self)
        layout.addLayout(toolbar)
        layout.addWidget(self._list, stretch=1)
        layout.addLayout(status_row)

        self.reload()

        self._commit_relay = _CommitResultRelay()
        self._commit_relay.finished.connect(self._on_commit_finished)

        state = self._state
        watcher = self._watcher

        def _flush_on_teardown() -> None:
            watcher.stop()

        self.destroyed.connect(_flush_on_teardown)

    def reload(self) -> None:
        directory = current_context.get_current_desk_directory()
        questions_path = find_nearest_questions_file(directory) if directory is not None else None
        self._ensure_watcher(questions_path)
        if questions_path is None:
            self._state.update(questions_path=None, preamble="", entries=[])
            self._status_label.setText("No QUESTIONS.md found near the current Desk's directory.")
            self._list.clear()
            self.refresh_external_path_status()
            return

        preamble, entries = parse_questions_file(questions_path)
        self._state.update(questions_path=questions_path, preamble=preamble, entries=entries)
        self._status_label.setText(str(questions_path))
        self._touch_timestamp("Reloaded")
        self._populate_list()
        self.refresh_external_path_status()

    def refresh_external_path_status(self) -> None:
        """Re-emits `external_path_changed` for the currently loaded
        QUESTIONS.md -- mirrors TodoWidget.refresh_external_path_status,
        including the same defensive wrapping (TODO 810a5d6): an
        uncaught exception escaping a Qt-signal-invoked slot is fatal to
        this whole process."""
        questions_path = self._state["questions_path"]
        try:
            is_external = questions_path is not None and current_context.path_is_external(questions_path)
        except Exception:
            logger.error("Failed to compute external-path status for %s", questions_path, exc_info=True)
            return
        self.external_path_changed.emit(is_external)

    def _touch_timestamp(self, verb: str) -> None:
        self._timestamp_label.setText(f"{verb} {datetime.now().strftime('%H:%M:%S')}")

    def _ensure_watcher(self, questions_path: Path | None) -> None:
        if questions_path is None:
            self._watcher.stop()
        else:
            self._watcher.watch(questions_path)

    @staticmethod
    def _entry_key(entry: QuestionEntry) -> tuple:
        return tuple(entry.todo_ids)

    def _on_external_change(self) -> None:
        # No self-write-echo check needed -- SingleFileWatcher already
        # suppresses the `changed` signal for our own writes.
        questions_path = self._state["questions_path"]
        if questions_path is None or not questions_path.is_file():
            return

        preamble, entries = parse_questions_file(questions_path)
        new_by_key = {self._entry_key(entry): entry for entry in entries}
        for key, (dialog, original_answer) in list(self._open_edits.items()):
            new_entry = new_by_key.get(key)
            if new_entry is None or new_entry.answer != original_answer:
                self._resolve_edit_conflict(key, dialog)

        self._state.update(preamble=preamble, entries=entries)
        self._status_label.setText(str(questions_path))
        self._touch_timestamp("Reloaded")
        self._populate_list()

    def _resolve_edit_conflict(self, key: tuple, dialog: "_AnswerDialog") -> None:
        text = dialog.current_text()
        opener = current_context.get_widget_opener()
        if opener is not None:
            scratch = opener("scratch")
            if scratch is not None:
                scratch.set_label(f"Question ({'/'.join(key)}) Edit Conflict")
                scratch.body.setPlainText(text)
        dialog.close()

    def _populate_list(self) -> None:
        self._hide_discuss_button()
        self._list.clear()
        for entry in self._state["entries"]:
            status = "answered" if entry.answer.strip() else "unanswered"
            if not (self._filter_buttons["all"].isChecked() or self._filter_buttons[status].isChecked()):
                continue
            marker = "✓" if status == "answered" else "?"
            row_text = f"[{marker}] {entry.title}"
            list_item = QListWidgetItem(row_text)
            list_item.setData(ENTRY_ROLE, entry)
            list_item.setToolTip(entry.title)
            self._list.addItem(list_item)

    def _apply_filter(self, _checked: bool) -> None:
        self._populate_list()

    def eventFilter(self, obj, event) -> bool:
        # Hide the floating Discuss button when the mouse leaves the
        # list, so it doesn't linger over an un-hovered row -- mirrors
        # widgets/todo/widget.py's own plan-button eventFilter.
        if obj is self._list.viewport() and event.type() == QEvent.Type.Leave:
            self._hide_discuss_button()
        return super().eventFilter(obj, event)

    def _on_item_entered(self, list_item: QListWidgetItem) -> None:
        self._discuss_item = list_item
        rect = self._list.visualItemRect(list_item)
        self._discuss_button.adjustSize()
        size = self._discuss_button.size()
        x = rect.right() - size.width() - 6
        y = rect.center().y() - size.height() // 2
        self._discuss_button.move(max(rect.left(), x), y)
        self._discuss_button.show()
        self._discuss_button.raise_()

    def _hide_discuss_button(self) -> None:
        self._discuss_item = None
        self._discuss_button.hide()

    def _discuss_hovered_entry(self) -> None:
        if self._discuss_item is None:
            return
        entry = self._discuss_item.data(ENTRY_ROLE)
        starter = current_context.get_discuss_starter()
        if entry is None or starter is None:
            return
        starter("QUESTIONS.md", entry.raw_text)
        self._hide_discuss_button()

    def _new_answer_dialog(self, **kwargs) -> "_AnswerDialog":
        # Same parenting rationale as TodoWidget._new_item_dialog -- see
        # that method's docstring.
        dialog = _AnswerDialog(QApplication.activeWindow() or self, **kwargs)
        self.destroyed.connect(dialog.close)
        return dialog

    def _resolve_view_and_proxy(self):
        """Mirrors TodoWidget's own method of the same name -- see that
        class's docstring."""
        proxy = self.window().graphicsProxyWidget()
        if proxy is None or proxy.scene() is None:
            return None
        views = proxy.scene().views()
        if not views:
            return None
        return views[0], proxy

    def _screen_point(self, widget: QWidget, local_point: QPoint) -> QPoint | None:
        resolved = self._resolve_view_and_proxy()
        if resolved is None:
            return None
        view, proxy = resolved
        window_point = widget.mapTo(self.window(), local_point)
        scene_point = proxy.mapToScene(QPointF(window_point))
        return view.viewport().mapToGlobal(view.mapFromScene(scene_point))

    def _screen_rect(self, widget: QWidget) -> QRect | None:
        top_left = self._screen_point(widget, QPoint(0, 0))
        bottom_right = self._screen_point(widget, QPoint(widget.width(), widget.height()))
        if top_left is None or bottom_right is None:
            return None
        return QRect(top_left, bottom_right)

    def _position_dialog(self, dialog: "_AnswerDialog", anchor: QWidget, local_point: QPoint) -> None:
        """Mirrors TodoWidget._position_dialog -- see that method's
        docstring (TODO 10b0321)."""
        bounds = self._screen_rect(self)
        desired = self._screen_point(anchor, local_point)
        if bounds is None or desired is None:
            dialog.move(anchor.mapToGlobal(local_point))
            return
        width = min(dialog.width(), bounds.width())
        height = min(dialog.height(), bounds.height())
        if (width, height) != (dialog.width(), dialog.height()):
            dialog.resize(width, height)
        x = bounds.left() + max(0, min(desired.x() - bounds.left(), bounds.width() - width))
        y = bounds.top() + max(0, min(desired.y() - bounds.top(), bounds.height() - height))
        dialog.move(x, y)

    def _show_answer_dialog(self, list_item: QListWidgetItem) -> None:
        entry = list_item.data(ENTRY_ROLE)
        dialog = self._new_answer_dialog(title=entry.title, body=entry.body, initial_answer=entry.answer)
        key = self._entry_key(entry)
        dialog.answer_submitted.connect(lambda answer: self._save_answer(entry, answer))
        self._open_edits[key] = (dialog, entry.answer)
        dialog.destroyed.connect(lambda: self._open_edits.pop(key, None))
        rect = self._list.visualItemRect(list_item)
        self._position_dialog(dialog, self._list.viewport(), rect.bottomLeft())
        dialog.show()

    def _save_answer(self, entry: QuestionEntry, answer: str) -> None:
        if self._state["questions_path"] is None:
            return
        updated = with_answer(entry, answer)
        key = self._entry_key(entry)
        self._state["entries"] = [
            updated if self._entry_key(existing) == key else existing for existing in self._state["entries"]
        ]
        self._status_label.setText("Saving…")
        _write_and_commit(
            self._state,
            f"Answer question: {'/'.join(entry.todo_ids) or entry.title}",
            self._watcher,
            self._commit_relay.finished.emit,
        )
        self._populate_list()

    def _on_commit_finished(self, committed: bool) -> None:
        questions_path = self._state["questions_path"]
        if committed:
            self._status_label.setText(str(questions_path))
            self._touch_timestamp("Committed")
        else:
            self._status_label.setText(f"{questions_path} (saved, but not a git repo -- not committed)")
            self._touch_timestamp("Saved")


def build() -> QWidget:
    return QuestionsWidget()
