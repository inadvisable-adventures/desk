import subprocess
import threading
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from desk.file_type_registry import looks_like_text_file
from desk.git_utils import find_git_root
from desk.persisted_path import resolve_persisted_path

BINARY_MESSAGE = "(binary file, no diff)"
NO_DIFF_MESSAGE = "(no differences from the last commit)"
NOT_A_REPO_MESSAGE = "Not inside a git repository."
GIT_FAILED_MESSAGE = "(git diff failed)"
LOADING_MESSAGE = "Loading…"


class _Relay(QObject):
    """Owns the pyqtSignal a background git-diff thread reports through
    -- same shape as widgets/git_status/widget.py's/widgets/todo/widget
    .py's own relays. `path` is included so a stale result (from a file
    we've since navigated away from) can be told apart from a current
    one."""

    finished = pyqtSignal(object, object, bool)  # path: Path, output: str | None, not_a_repo: bool


def _run_git_diff(path: Path, relay: _Relay) -> None:
    """Module-level, not a method: runs on a background thread and must
    not touch any Qt widget directly -- only ever reports back via the
    relay's signal. Resolves the git root itself, on this same
    background thread (find_git_root is itself a blocking subprocess
    call) -- a blocking subprocess on the Qt GUI thread freezes the
    whole app's UI feedback, not just the caller (LEARNINGS.md)."""
    root = find_git_root(path.parent)
    if root is None:
        relay.finished.emit(path, None, True)
        return
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "diff", "HEAD", "--", str(path)],
            capture_output=True,
            text=True,
            check=True,
        )
        output = result.stdout
    except (subprocess.CalledProcessError, OSError):
        output = None
    relay.finished.emit(path, output, False)


class GitDiffWidget(QWidget):
    """Shows `git diff HEAD -- <path>` for a single file (TODO
    fd713a5) -- opened by clicking a file in the Git Status widget
    (widgets/git_status/widget.py), or via desk.file_type_registry
    .find_git_diff_handler/DeskWindow.open_git_diff from anywhere else
    that already looks up a file's view/edit handler. Read-only, no
    editing here -- this widget exists to show what changed, not to
    change it."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._path: Path | None = None

        self._status_label = QLabel("No file selected.")
        self._status_label.setWordWrap(True)
        self._status_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        self._text_view = QPlainTextEdit()
        self._text_view.setReadOnly(True)
        self._text_view.setFont(QFont("Menlo"))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._status_label)
        layout.addWidget(self._text_view, stretch=1)

        self._relay = _Relay()
        self._relay.finished.connect(self._on_diff_result)

    def set_file(self, path: Path) -> None:
        self._path = path
        self._status_label.setText(f"Git diff: {path.name}")
        self._text_view.setPlainText(LOADING_MESSAGE)
        thread = threading.Thread(target=_run_git_diff, args=(path, self._relay), daemon=True)
        thread.start()

    def _on_diff_result(self, path: Path, output: str | None, not_a_repo: bool) -> None:
        if path != self._path:
            return  # stale result from a file we've since navigated away from
        if not_a_repo:
            self._text_view.setPlainText(NOT_A_REPO_MESSAGE)
            return
        if output is None:
            self._text_view.setPlainText(GIT_FAILED_MESSAGE)
            return
        # TODO fd713a5: git's own diff output is authoritative (a
        # deleted file no longer exists on disk, so looks_like_text_file
        # on it returns False -- "can't tell, don't guess yes" -- which
        # would wrongly hide that file's real, meaningful diff if it
        # were checked unconditionally); the local-file check only adds
        # information when the file still exists to sniff.
        is_binary = "Binary files " in output or (path.is_file() and not looks_like_text_file(path))
        if is_binary:
            self._text_view.setPlainText(BINARY_MESSAGE)
            return
        self._text_view.setPlainText(output if output else NO_DIFF_MESSAGE)

    # -- widget-local storage (TODO fb76057/02eda20) ---------------------

    def get_widget_local_storage(self) -> dict:
        return {"path": str(self._path)} if self._path else {}

    def set_widget_local_storage(self, data: dict) -> None:
        path = resolve_persisted_path(data.get("path"))
        if path is not None:
            self.set_file(path)


def build() -> QWidget:
    return GitDiffWidget()
