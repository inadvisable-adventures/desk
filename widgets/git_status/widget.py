import subprocess
import threading
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from desk.git_utils import find_git_root
from desk.shell import current_context

POLL_INTERVAL_MS = 3000
CLEAN_PLACEHOLDER = "Working tree clean"
# TODO fd713a5: the resolved absolute Path for a status row, stashed on
# its QListWidgetItem the same Qt.ItemDataRole.UserRole pattern
# widgets/event_log/widget.py's own EVENT_ROLE already uses -- computed
# once at population time, not re-parsed from the displayed text at
# click time. The CLEAN_PLACEHOLDER row gets no such data, so clicking
# it is naturally a no-op.
PATH_ROLE = Qt.ItemDataRole.UserRole


def _path_from_status_line(root: Path, line: str) -> Path | None:
    """Parses a `git status --porcelain=v1` line: a fixed 2-char status
    code, one space, then the path -- for a rename/copy (`R  old ->
    new`), the part after " -> " is the file's *current* path, which is
    what a diff/view/edit action should target."""
    if len(line) < 4:
        return None
    rest = line[3:]
    if " -> " in rest:
        rest = rest.split(" -> ", 1)[1]
    rest = rest.strip()
    return root / rest if rest else None


class _Relay(QObject):
    """Owns the pyqtSignal a background polling thread reports through --
    same shape as widgets/todo/widget.py's _CommitResultRelay/
    _FileChangeRelay. `root` is included so a stale result (from a
    directory the widget has since moved away from) can be told apart
    from a current one."""

    finished = pyqtSignal(object, object, object)  # root: Path, branch: str | None, output: str | None


def _run_git_status(root: Path, relay: _Relay) -> None:
    """Module-level, not a method: runs on a background thread and must
    not touch any Qt widget directly -- only ever reports back via the
    relay's signal (Qt automatically queues a cross-thread signal emit
    onto the receiving object's own thread)."""
    try:
        branch = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        output = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain=v1"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, OSError):
        branch = None
        output = None
    relay.finished.emit(root, branch, output)


class GitStatusWidget(QWidget):
    """Shows the current Desk directory's git status (TODO ef77819),
    refreshed on a timer rather than a file watcher -- almost any change
    anywhere in a working tree can affect `git status`, so a precise
    watcher is both complex and the "too much compute burden" the TODO
    itself warns against. See plans/git-status-widget.md."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._root: Path | None = None
        self._last_branch: str | None = None
        self._last_output: str | None = None

        self._status_label = QLabel()
        self._status_label.setWordWrap(True)
        self._status_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        self._list = QListWidget()
        self._list.itemClicked.connect(self._on_item_clicked)

        layout = QVBoxLayout(self)
        layout.addWidget(self._status_label)
        layout.addWidget(self._list, stretch=1)

        self._relay = _Relay()
        self._relay.finished.connect(self._on_status_result)

        self._timer = QTimer(self)
        self._timer.setInterval(POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

        # initial=True: a freshly-constructed widget is never yet visible
        # (it hasn't been parented/shown by whoever placed it) -- the
        # isVisible() gate below is about skipping *later*, timer-driven
        # polls for a widget nobody's looking at, not about suppressing
        # the very first one, which would otherwise leave the widget
        # blank until the first timer tick fires.
        self._poll(initial=True)

    def _poll(self, initial: bool = False) -> None:
        # Cheap, direct cut at the compute burden: no point running a
        # real `git status` subprocess on a timer for a widget that
        # isn't even being looked at right now.
        if not initial and not self.isVisible():
            return

        directory = current_context.get_current_desk_directory()
        self._root = find_git_root(directory) if directory is not None else None
        if self._root is None:
            self._status_label.setText("Not a git repository.")
            self._list.clear()
            self._last_branch = None
            self._last_output = None
            return

        # Off the GUI thread: a slow/hung `git` invocation must never
        # freeze the whole app -- same reasoning as widgets/todo/widget
        # .py's _write_and_commit (see LEARNINGS.md).
        thread = threading.Thread(target=_run_git_status, args=(self._root, self._relay), daemon=True)
        thread.start()

    def _on_status_result(self, root: Path, branch: str | None, output: str | None) -> None:
        if root != self._root:
            return  # stale result from a directory we've since moved away from

        if output is None:
            self._status_label.setText(f"{root} (git status failed)")
            self._list.clear()
            self._last_branch = None
            self._last_output = None
            return

        if branch == self._last_branch and output == self._last_output:
            return  # nothing changed since the last poll -- skip the redundant redraw

        self._last_branch = branch
        self._last_output = output
        self._status_label.setText(f"{root} — {branch}" if branch else str(root))
        self._populate_list(output)

    def _populate_list(self, output: str) -> None:
        self._list.clear()
        lines = [line for line in output.splitlines() if line.strip()]
        if not lines:
            self._list.addItem(QListWidgetItem(CLEAN_PLACEHOLDER))
            return
        for line in lines:
            item = QListWidgetItem(line)
            if self._root is not None:
                path = _path_from_status_line(self._root, line)
                if path is not None:
                    item.setData(PATH_ROLE, path)
            self._list.addItem(item)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        path = item.data(PATH_ROLE)
        if path is None:
            return
        opener = current_context.get_git_diff_opener()
        if opener is not None:
            opener(path)


def build() -> QWidget:
    return GitStatusWidget()
