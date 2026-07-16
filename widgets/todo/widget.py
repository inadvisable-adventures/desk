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
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desk.file_watch import SingleFileWatcher
from desk.git_utils import find_git_root
from desk.shell import current_context
from desk.todo_file import (
    TodoItem,
    find_nearest_todo_file,
    parse_todo_file,
    render_todo_file,
    status_of,
    truncate_description,
)
from desk.todo_ids import make_item_id

logger = logging.getLogger(__name__)

DEBOUNCE_SECONDS = 60
ITEM_ROLE = Qt.ItemDataRole.UserRole
STATUSES = ("incomplete", "pending", "completed", "superseded")
REPRIORITIZE_MESSAGE = "Reprioritize TODO items"

# Plain QPushButton(checkable=True) looks nearly identical checked vs.
# unchecked on some platform styles (macOS's native style included) --
# this makes the toggle state unambiguous regardless of style. QSS on a
# native Qt widget, not browser CSS -- see plans/todo-widget-filter-
# styling.md.
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

# Each row should read as a distinct, draggable item -- a small frame --
# rather than a plain unstyled line of text. Styled once, on the list
# itself, via Qt's standard QListWidget::item sub-control selector (no
# need for a custom per-row item delegate/widget for a purely visual
# change like this). See plans/todo-widget-item-framing.md.
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


def _git_commit(todo_path: Path, message: str) -> bool:
    """Returns whether a real commit was made. False (not an error) if
    the target directory isn't a git repo -- see plans/todo-widget.md."""
    root = find_git_root(todo_path.parent)
    if root is None:
        return False
    try:
        subprocess.run(["git", "-C", str(root), "add", str(todo_path)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(root), "commit", "-m", message], check=True, capture_output=True
        )
        return True
    except subprocess.CalledProcessError:
        return False


# Serializes the actual `git` subprocess calls made by background
# threads started from _write_and_commit below -- without this, two
# overlapping commits (e.g. the user edits again while a previous commit
# is still slow or hung) could run `git add`/`git commit` concurrently
# against the same repo. Only ever blocks a background thread, never the
# GUI thread. See TODO 62e8b05 / plans/fix-todo-editor-caret-focus-freeze.md.
_GIT_LOCK = threading.Lock()


def _write_and_commit(
    state: dict,
    message: str,
    watcher: SingleFileWatcher | None = None,
    on_committed: Callable[[bool], None] | None = None,
) -> threading.Thread | None:
    """Module-level (not a method): safe to call from the destroyed
    -triggered cleanup closure, which must not touch `self` or any Qt
    child object -- see LEARNINGS.md ("Connecting an object's own
    destroyed signal..."). `state` is a plain dict the widget keeps
    up-to-date, not a Qt object, so reading it after teardown is safe.
    `watcher`, if given, must be a plain captured reference (as in the
    teardown closure below) rather than accessed via `self` -- calling
    a method directly on an already-obtained QObject reference is fine
    even during teardown (see `watcher.stop()` in the same closure);
    reading `self._watcher` at call time would not be.

    Writes TODO.md synchronously (fast, and must happen in call order on
    the GUI thread so concurrent edits are never lost or applied out of
    order), then commits in a background thread. `git` subprocess calls
    can block for an unbounded time (a pre-commit hook, a lock file, a
    GPG prompt, etc.) and must never run on the Qt GUI thread -- doing so
    freezes the *entire* app, including QPlainTextEdit's own caret-blink
    timer, which is what TODO 62e8b05 actually was (not real focus loss).

    `on_committed`, if given, is invoked with the commit result from the
    background thread -- callers must only pass a thread-safe hook (a Qt
    signal's `.emit`, which Qt automatically queues onto the receiving
    object's own thread), never something that touches a QWidget
    directly. Returns the started background Thread (or None if there
    was no todo_path to write) so a caller that needs the old, fully
    -synchronous behavior (the destroyed-triggered teardown flush) can
    `.join()` it."""
    todo_path = state["todo_path"]
    if todo_path is None:
        return None
    text = render_todo_file(state["preamble"], state["items"])
    todo_path.write_text(text)
    # Recorded so the watcher (see _watcher/_on_external_change below)
    # can tell "the file changed because we just wrote it" apart from a
    # real external edit -- comparing against the file's fresh content
    # on the next change notification, not just a timestamp/flag, since
    # a real external edit could plausibly land in the same instant. See
    # desk.file_watch.SingleFileWatcher.record_own_write (TODO cee6f74).
    if watcher is not None:
        watcher.record_own_write(text)

    def run() -> None:
        with _GIT_LOCK:
            committed = _git_commit(todo_path, message)
        state["pending"] = False
        state["last_commit_ok"] = committed
        if on_committed is not None:
            on_committed(committed)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


class _CommitResultRelay(QObject):
    """A dedicated QObject purely to own a pyqtSignal -- PyQt signals
    must be declared on a QObject subclass -- so a background commit
    thread (started by _write_and_commit) can report its result back
    onto the GUI thread safely: Qt automatically queues a signal emitted
    from another thread to run on the receiving object's own thread."""

    finished = pyqtSignal(bool)


# File watching is now desk.file_watch.SingleFileWatcher (backed by the
# shared desk_services.file_watcher service, TODO 578cb6b) -- this used
# to be a bespoke watchdog Observer/handler/relay trio here, extracted
# (TODO 6bf83a9) into SingleFileWatcher for the Markdown widget. Self
# -write-echo suppression also now happens inside SingleFileWatcher
# itself (via record_own_write, called from _write_and_commit) instead
# of this widget's own former state["last_written_text"] comparison --
# see TODO cee6f74.


class _ItemDialog(QWidget):
    """A small hovering popup for typing an item's description -- used
    both to add a new item (empty) and to edit an existing one
    (prefilled). Unlike WidgetSpawnMenu's Popup pattern, this dialog must
    not dismiss on click-away (TODO a629bea), so it's a floating Tool
    window rather than a Popup -- see LEARNINGS.md's "A
    `Qt.WindowType.Popup` widget can silently self-destruct during
    headless testing" for why Popup's auto-close-on-focus-loss is what's
    being avoided here. See plans/todo-widget-edit-on-doubleclick.md and
    plans/todo-widget-editor-discard-save.md."""

    item_submitted = pyqtSignal(str)

    def __init__(
        self,
        parent=None,
        initial_text: str = "",
        submit_label: str = "Add",
        editing: bool = False,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(420, 220)
        self._editing = editing
        self._initial_text = initial_text

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self._field = QPlainTextEdit()
        self._field.setPlaceholderText("New item description… (Ctrl+Enter to submit)")
        self._field.setPlainText(initial_text)
        self._field.setMinimumSize(400, 160)
        self._field.selectAll()
        self._field.installEventFilter(self)
        layout.addWidget(self._field)

        button_row = QHBoxLayout()
        discard = QPushButton("Discard")
        discard.clicked.connect(self._attempt_discard)
        button_row.addWidget(discard)
        submit = QPushButton(submit_label)
        submit.clicked.connect(self._submit)
        button_row.addWidget(submit)
        layout.addLayout(button_row)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # setFocus() before the widget is ever shown is a documented
        # no-op, and this is a frameless Tool window that isn't
        # guaranteed to be the OS-active window just because show() was
        # called -- raise/activate it too, deferred so the window
        # manager has settled its activation before we claim the field
        # (the same "something else reasserts state right after this"
        # shape as the Lightning Round widget's deferred setFocus()).
        QTimer.singleShot(0, self._claim_focus)

    def _claim_focus(self) -> None:
        self.raise_()
        self.activateWindow()
        self._field.setFocus()

    def current_text(self) -> str:
        """The field's live, possibly-unsaved text -- exposed for the
        TODO widget's edit-conflict handling (TODO d25e557), which needs
        to preserve in-progress edits into a Scratch widget rather than
        silently discard them when the underlying item changes out from
        under an open edit."""
        return self._field.toPlainText()

    def _submit(self) -> None:
        text = self._field.toPlainText().strip()
        if text:
            self.item_submitted.emit(text)
        self.close()

    def _attempt_discard(self) -> None:
        if self._needs_confirmation() and not self._confirm_discard():
            return
        self.close()

    def _needs_confirmation(self) -> bool:
        # Editing: only if the text has actually changed from what it
        # was prefilled with -- an edit dialog is never prefilled empty,
        # so checking mere non-whitespace presence (the add-mode rule)
        # would confirm on every single edit-discard, even a no-op one.
        if self._editing:
            return self._field.toPlainText() != self._initial_text
        return bool(self._field.toPlainText().strip())

    def _confirm_discard(self) -> bool:
        """Split out from _attempt_discard so headless verification can
        monkeypatch just this one method instead of driving a real
        popup. Uses the desk-internal popups service (TODO 359684f),
        not a QMessageBox parented to self -- that used to render as a
        real top-level window whose position didn't account for the
        canvas's own zoom/pan transform."""
        opener = current_context.get_popup_opener()
        if opener is None:
            return False
        message = "Discard changes?" if self._editing else "Discard this new item?"
        return opener(message, message, ["Yes", "No"], "No") == "Yes"

    def eventFilter(self, obj, event) -> bool:
        if obj is self._field and event.type() == QEvent.Type.KeyPress:
            # Multiline field: plain Return/Enter inserts a newline like
            # any normal multiline editing (handled natively by
            # QPlainTextEdit, not intercepted here) -- only Ctrl+Return/
            # Ctrl+Enter (Cmd on macOS, via Qt's own platform mapping of
            # ControlModifier) submits.
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    self._submit()
                    return True
                return False
            if event.key() == Qt.Key.Key_Escape:
                self._attempt_discard()
                return True
        return super().eventFilter(obj, event)


class TodoWidget(QWidget):
    """Reads the nearest TODO.md relative to the current Desk's directory
    (desk.shell.current_context) and displays it as a filterable,
    reorderable list. See plans/todo-widget.md.

    `find_nearest_todo_file` walks *up* through parent directories, so
    the resolved TODO.md can legitimately live outside the current Desk
    directory -- `external_path_changed` (TODO a053e3a) reflects that
    in the widget's titlebar."""

    external_path_changed = pyqtSignal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._filter_buttons: dict[str, QPushButton] = {}

        # Plain dict (not Qt state) so the destroyed-triggered flush
        # closure can read it safely after this widget is torn down --
        # see _write_and_commit's docstring and LEARNINGS.md.
        self._state = {
            "todo_path": None,
            "preamble": "",
            "items": [],
            "pending": False,
            "last_commit_ok": True,
        }

        # item_id -> (dialog, description as originally loaded) for every
        # currently-open edit dialog -- lets an external-change
        # notification (see _on_external_change) tell whether it actually
        # conflicts with an in-progress edit. Popped automatically when a
        # dialog closes (see _show_edit_dialog).
        self._open_edits: dict[str, tuple["_ItemDialog", str]] = {}
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
        for status in STATUSES:
            button = QPushButton(status.capitalize())
            button.setCheckable(True)
            button.setChecked(True)
            button.setStyleSheet(FILTER_BUTTON_STYLE)
            button.toggled.connect(self._apply_filter)
            filter_layout.addWidget(button)
            self._filter_buttons[status] = button

        toolbar = QHBoxLayout()
        toolbar.addWidget(filter_frame)
        toolbar.addStretch()
        add_button = QPushButton("Add Item")
        add_button.clicked.connect(self._show_add_dialog)
        toolbar.addWidget(add_button)

        self._list = QListWidget()
        self._list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._list.setStyleSheet(ITEM_LIST_STYLE)
        self._list.setSpacing(ITEM_LIST_SPACING)
        self._list.model().rowsMoved.connect(self._on_rows_moved)
        self._list.itemDoubleClicked.connect(self._show_edit_dialog)

        # A single floating "open plan" button that follows the mouse to
        # the hovered row (see _on_item_entered) rather than a per-row
        # setItemWidget -- the latter is fragile with InternalMove drag
        # -reorder. Only shown over a row whose item has a [planned: ...]
        # marker. See plans/todo-open-plan-button.md.
        self._list.setMouseTracking(True)
        self._list.viewport().setMouseTracking(True)
        self._list.itemEntered.connect(self._on_item_entered)
        self._list.viewport().installEventFilter(self)
        self._list.verticalScrollBar().valueChanged.connect(self._hide_plan_button)
        self._plan_button = QPushButton("📄 Plan", self._list.viewport())
        self._plan_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._plan_button.hide()
        self._plan_button.clicked.connect(self._open_hovered_plan)
        self._plan_item: QListWidgetItem | None = None

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(DEBOUNCE_SECONDS * 1000)
        self._debounce_timer.timeout.connect(self._flush_pending_commit)

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
        # Captured (not self._watcher) so this destroyed-triggered
        # closure never touches self -- same pattern as the Markdown/
        # Markdown (Extended)/Image Viewer widgets' own teardown.
        watcher = self._watcher

        def _flush_on_teardown() -> None:
            # No on_committed callback here: after teardown there's no
            # `self`/relay left to safely call back into. `.join()` so
            # this stays a bounded, synchronous flush-before-teardown,
            # exactly like before -- only the interactive paths
            # (_add_item/_edit_item/_flush_pending_commit) need to avoid
            # blocking the GUI thread. See TODO 62e8b05.
            if state["pending"]:
                thread = _write_and_commit(state, REPRIORITIZE_MESSAGE, watcher)
                if thread is not None:
                    thread.join()
            watcher.stop()

        self.destroyed.connect(_flush_on_teardown)

    def reload(self) -> None:
        directory = current_context.get_current_desk_directory()
        todo_path = find_nearest_todo_file(directory) if directory is not None else None
        self._ensure_watcher(todo_path)
        if todo_path is None:
            self._state.update(todo_path=None, preamble="", items=[], pending=False)
            self._status_label.setText("No TODO.md found near the current Desk's directory.")
            self._list.clear()
            self.refresh_external_path_status()
            return

        preamble, items = parse_todo_file(todo_path)
        self._state.update(todo_path=todo_path, preamble=preamble, items=items, pending=False)
        self._status_label.setText(str(todo_path))
        self._touch_timestamp("Reloaded")
        self._populate_list()
        self.refresh_external_path_status()

    def refresh_external_path_status(self) -> None:
        """Re-emits `external_path_changed` for the currently loaded
        TODO.md (TODO a053e3a) -- called here after every reload, and
        once more by DeskWindow right after wiring the signal, since
        this widget's own __init__ already calls reload() once,
        before that connection could possibly exist yet.

        Wrapped defensively (TODO 810a5d6): this is a purely cosmetic
        titlebar feature reached from a Qt-signal-invoked slot chain
        where an uncaught exception is fatal to the whole process in
        this PyQt6 setup -- see plans/isolate-hot-reload-crash.md and
        LEARNINGS.md."""
        todo_path = self._state["todo_path"]
        try:
            is_external = todo_path is not None and current_context.path_is_external(todo_path)
        except Exception:
            logger.error("Failed to compute external-path status for %s", todo_path, exc_info=True)
            return
        self.external_path_changed.emit(is_external)

    def _touch_timestamp(self, verb: str) -> None:
        self._timestamp_label.setText(f"{verb} {datetime.now().strftime('%H:%M:%S')}")

    def _ensure_watcher(self, todo_path: Path | None) -> None:
        # SingleFileWatcher.watch() is already a no-op when called again
        # for the same path (see desk.file_watch), so this no longer
        # needs its own "did the path actually change" guard -- it won't
        # restart (and briefly stop watching during) every single
        # external-change-triggered reload.
        if todo_path is None:
            self._watcher.stop()
        else:
            self._watcher.watch(todo_path)

    def _on_external_change(self) -> None:
        # No self-write-echo check needed here -- SingleFileWatcher
        # itself already suppresses the `changed` signal for our own
        # writes (see _write_and_commit's `watcher.record_own_write`
        # call, TODO cee6f74), so this only ever fires for a real
        # external edit.
        todo_path = self._state["todo_path"]
        if todo_path is None or not todo_path.is_file():
            return

        if self._state["pending"]:
            # Flush our own uncommitted reorder to disk first so it isn't
            # silently lost by the reload below -- see
            # plans/todo-widget-file-watcher.md.
            self._debounce_timer.stop()
            thread = _write_and_commit(self._state, REPRIORITIZE_MESSAGE, self._watcher)
            if thread is not None:
                thread.join()

        preamble, items = parse_todo_file(todo_path)
        new_by_id = {item.item_id: item for item in items}
        for item_id, (dialog, original_description) in list(self._open_edits.items()):
            new_item = new_by_id.get(item_id)
            if new_item is None or new_item.description != original_description:
                self._resolve_edit_conflict(item_id, dialog)

        self._state.update(preamble=preamble, items=items, pending=False)
        self._status_label.setText(str(todo_path))
        self._touch_timestamp("Reloaded")
        self._populate_list()

    def _resolve_edit_conflict(self, item_id: str, dialog: "_ItemDialog") -> None:
        text = dialog.current_text()
        opener = current_context.get_widget_opener()
        if opener is not None:
            scratch = opener("scratch")
            if scratch is not None:
                scratch.set_label(f"TODO Item ({item_id}) Edit Conflict")
                scratch.body.setPlainText(text)
        dialog.close()

    def _populate_list(self) -> None:
        self._hide_plan_button()
        self._list.clear()
        for item in self._state["items"]:
            if not self._filter_buttons[item.status].isChecked():
                continue
            row_text = f"[{item.status}] {truncate_description(item.description)}"
            list_item = QListWidgetItem(row_text)
            list_item.setData(ITEM_ROLE, item)
            list_item.setToolTip(f"TODO {item.item_id}\n{item.description}")
            self._list.addItem(list_item)

    def _apply_filter(self, _checked: bool) -> None:
        self._populate_list()

    def eventFilter(self, obj, event) -> bool:
        # Hide the floating plan button when the mouse leaves the list, so
        # it doesn't linger over an un-hovered row.
        if obj is self._list.viewport() and event.type() == QEvent.Type.Leave:
            self._hide_plan_button()
        return super().eventFilter(obj, event)

    def _on_item_entered(self, list_item: QListWidgetItem) -> None:
        item = list_item.data(ITEM_ROLE)
        if item is None or not item.plan:
            self._hide_plan_button()
            return
        self._plan_item = list_item
        rect = self._list.visualItemRect(list_item)
        self._plan_button.adjustSize()
        size = self._plan_button.size()
        x = rect.right() - size.width() - 6
        y = rect.center().y() - size.height() // 2
        self._plan_button.move(max(rect.left(), x), y)
        self._plan_button.show()
        self._plan_button.raise_()

    def _hide_plan_button(self) -> None:
        self._plan_item = None
        self._plan_button.hide()

    def _open_hovered_plan(self) -> None:
        if self._plan_item is None:
            return
        item = self._plan_item.data(ITEM_ROLE)
        todo_path = self._state["todo_path"]
        if item is None or not item.plan or todo_path is None:
            return
        plan_path = todo_path.parent / "plans" / item.plan
        opener = current_context.get_widget_opener()
        if opener is None:
            return
        widget = opener("markdown")
        if widget is not None and hasattr(widget, "set_file"):
            widget.set_file(plan_path)
        self._hide_plan_button()

    def _on_rows_moved(self, *_args) -> None:
        visible_order = [self._list.item(i).data(ITEM_ROLE) for i in range(self._list.count())]
        visible_ids = {item.item_id for item in visible_order}
        new_order_iter = iter(visible_order)
        self._state["items"] = [
            next(new_order_iter) if item.item_id in visible_ids else item
            for item in self._state["items"]
        ]
        self._state["pending"] = True
        self._debounce_timer.start()
        self._status_label.setText("Reprioritized -- commit pending...")

    def _flush_pending_commit(self) -> None:
        # Fire-and-forget: the existing "Reprioritized -- commit
        # pending..." label (set in _on_rows_moved) already covers the
        # interim state; _on_commit_finished reports the final status
        # once the background commit (started here) completes.
        _write_and_commit(self._state, REPRIORITIZE_MESSAGE, self._watcher, self._commit_relay.finished.emit)

    def _new_item_dialog(self, **kwargs) -> "_ItemDialog":
        # _ItemDialog must be parented to a widget whose .window() is a
        # real, actually-shown top-level OS window for raise_()/
        # activateWindow() to actually transfer real keyboard focus --
        # self.window() resolves to WidgetFrame, which is never itself
        # shown as an independent OS window (it's embedded into the
        # scene via QGraphicsProxyWidget, not a normal parent-child
        # chain), so parenting there silently breaks that. Qt still
        # requires a QWidget parent for the dialog to keep working, so
        # QApplication.activeWindow() (the real DeskWindow, since that's
        # necessarily the window that just delivered the Add/Edit click)
        # is used instead -- falling back to self if, unexpectedly,
        # nothing is active. Since the dialog is no longer a Qt child of
        # this widget, its lifetime is no longer tied to it automatically
        # -- wire that explicitly so it's still torn down together with
        # this widget exactly as before.
        dialog = _ItemDialog(QApplication.activeWindow() or self, **kwargs)
        self.destroyed.connect(dialog.close)
        return dialog

    def _show_add_dialog(self) -> None:
        dialog = self._new_item_dialog()
        dialog.item_submitted.connect(self._add_item)
        button = self.sender()
        if button is not None:
            self._position_dialog(dialog, button, button.rect().bottomLeft())
        dialog.show()

    def _resolve_view_and_proxy(self):
        """The Workspace Canvas view + this widget's enclosing proxy, or
        `None` if not actually embedded in one (e.g. a bare unit test).
        `self.window()` resolves to the `WidgetFrame` -- the exact
        widget passed to `scene.addWidget()` -- since a descendant's own
        `graphicsProxyWidget()` is `None` even though it's just as
        embedded (see LEARNINGS.md)."""
        proxy = self.window().graphicsProxyWidget()
        if proxy is None or proxy.scene() is None:
            return None
        views = proxy.scene().views()
        if not views:
            return None
        return views[0], proxy

    def _screen_point(self, widget: QWidget, local_point: QPoint) -> QPoint | None:
        """`local_point` (in `widget`'s own local coordinates) mapped to
        a real on-screen point, accounting for the Workspace Canvas's
        zoom/pan -- `QWidget.mapToGlobal()` itself is unreliable for a
        widget embedded in a `QGraphicsProxyWidget` under a non-unity
        view transform (confirmed directly: it silently ignores the
        widget's placed scene position while still applying the zoom
        scale to size -- TODO 10b0321), so this goes through the
        enclosing proxy/view chain explicitly instead. `widget` must be
        `self` or one of its descendants. Returns `None` if not
        actually embedded."""
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

    def _position_dialog(self, dialog: "_ItemDialog", anchor: QWidget, local_point: QPoint) -> None:
        """Positions `dialog` just past `local_point` (in `anchor`'s
        local coordinates), clamped to remain within this widget's own
        on-screen bounds (TODO 10b0321), capping the dialog's own size
        down too if this widget is currently smaller than the dialog's
        natural size (e.g. resized near `MIN_WIDTH`/`MIN_HEIGHT`) --
        `_field`'s own `setMinimumSize` still applies underneath, so an
        especially tiny widget just gets the dialog at its own practical
        minimum. Falls back to the old, unclamped `mapToGlobal`
        positioning if this widget isn't actually embedded in a canvas
        (e.g. a bare unit test)."""
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

    def _add_item(self, description: str) -> None:
        if self._state["todo_path"] is None:
            return
        item_id = make_item_id(description)
        new_item = TodoItem(
            item_id=item_id, status="incomplete", description=description, raw_text=f"{item_id}. {description}\n"
        )
        self._state["items"] = [*self._state["items"], new_item]
        self._debounce_timer.stop()
        self._status_label.setText("Saving…")
        _write_and_commit(
            self._state,
            f"Add TODO item: {truncate_description(description, 60)}",
            self._watcher,
            self._commit_relay.finished.emit,
        )
        self._populate_list()

    def _show_edit_dialog(self, list_item: QListWidgetItem) -> None:
        item = list_item.data(ITEM_ROLE)
        dialog = self._new_item_dialog(
            initial_text=item.description, submit_label="Save changes", editing=True
        )
        dialog.item_submitted.connect(lambda description: self._edit_item(item, description))
        self._open_edits[item.item_id] = (dialog, item.description)
        # Connecting a *different* object's (TodoWidget's) bound method to
        # this dialog's own destroyed signal is the case LEARNINGS.md
        # confirms works fine -- the never-fires gotcha is specifically
        # connecting an object's destroyed signal to its own bound method.
        dialog.destroyed.connect(lambda: self._open_edits.pop(item.item_id, None))
        rect = self._list.visualItemRect(list_item)
        self._position_dialog(dialog, self._list.viewport(), rect.bottomLeft())
        dialog.show()

    def _edit_item(self, item: TodoItem, description: str) -> None:
        if self._state["todo_path"] is None:
            return
        edited = TodoItem(
            item_id=item.item_id,
            status=status_of(description),
            description=description,
            raw_text=f"{item.item_id}. {description}\n",
        )
        self._state["items"] = [
            edited if existing.item_id == item.item_id else existing for existing in self._state["items"]
        ]
        self._debounce_timer.stop()
        self._status_label.setText("Saving…")
        _write_and_commit(
            self._state,
            f"Edit TODO item: {truncate_description(description, 60)}",
            self._watcher,
            self._commit_relay.finished.emit,
        )
        self._populate_list()

    def _on_commit_finished(self, _committed: bool) -> None:
        self._report_commit_status()

    def _report_commit_status(self) -> None:
        if self._state["last_commit_ok"]:
            self._status_label.setText(str(self._state["todo_path"]))
            self._touch_timestamp("Committed")
        else:
            self._status_label.setText(
                f"{self._state['todo_path']} (saved, but not a git repo -- not committed)"
            )
            self._touch_timestamp("Saved")


def build() -> QWidget:
    return TodoWidget()
