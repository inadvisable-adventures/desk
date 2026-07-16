import re
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desk.shell import current_context

# Only these two, exact segment names -- this project only has these,
# not a general "look configurable" system. See plans/crash-log-widget.md.
_ANCHOR_DIRS = ("src", ".venv")
# Stops at whitespace or a quote -- traceback lines quote paths as
# `File "...", line N, in ...`, so this never swallows the trailing
# quote/comma into the matched path.
_PATH_RE = re.compile(r"/[^\s\"']+")


def sanitize_crash_log(text: str) -> str:
    """Strips the OS/user-specific prefix off any absolute path found in
    `text`, keeping from the first `src` or `.venv` path segment onward
    -- e.g. `/Users/alice/some-project/src/desk/foo.py` becomes
    `src/desk/foo.py`. A path containing neither segment is left
    unchanged (nothing safe to assume about it)."""

    def _strip(match: re.Match) -> str:
        path = match.group(0)
        parts = path.split("/")
        for i, part in enumerate(parts):
            if part in _ANCHOR_DIRS:
                return "/".join(parts[i:])
        return path

    return _PATH_RE.sub(_strip, text)


class CrashLogWidget(QWidget):
    """Reads and displays one crash log file (see
    src/desk/crash_handler.py, TODO 95f7ce9/7f51230), with a Sanitize
    button that strips local path prefixes from the *displayed* text
    (never touching the file on disk) and a Delete Log File button
    that removes the underlying file and closes this widget. See
    plans/crash-log-widget.md."""

    dismissed = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._path: Path | None = None

        self._status_label = QLabel()
        self._status_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        self._body = QPlainTextEdit()
        self._body.setReadOnly(True)

        button_row = QHBoxLayout()
        sanitize_button = QPushButton("Sanitize")
        sanitize_button.clicked.connect(self._sanitize)
        button_row.addWidget(sanitize_button)
        delete_button = QPushButton("Delete Log File")
        delete_button.clicked.connect(self._delete_log_file)
        button_row.addWidget(delete_button)
        button_row.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(self._status_label)
        layout.addWidget(self._body, stretch=1)
        layout.addLayout(button_row)

    def set_file(self, path: Path) -> None:
        self._path = path
        self._status_label.setText(str(path))
        try:
            self._body.setPlainText(path.read_text())
        except OSError as exc:
            self._body.setPlainText(f"Could not read this crash log: {exc}")

    def _sanitize(self) -> None:
        self._body.setPlainText(sanitize_crash_log(self._body.toPlainText()))

    def _delete_log_file(self) -> None:
        if not self._confirm_delete():
            return
        if self._path is not None and self._path.is_file():
            self._path.unlink()
        self.dismissed.emit()

    def _confirm_delete(self) -> bool:
        """Split out so headless verification can monkeypatch just this
        one method instead of driving a real popup -- mirrors the same
        pattern used elsewhere in this codebase (e.g. widgets/todo/
        widget.py's _ItemDialog._confirm_discard). Uses the
        desk-internal popups service (TODO 359684f), not a QMessageBox
        parented to self -- that used to render as a real top-level
        window whose position didn't account for the canvas's own
        zoom/pan transform."""
        opener = current_context.get_popup_opener()
        if opener is None:
            return False
        message = "Delete this crash log file? This can't be undone."
        return opener("Delete Log File", message, ["Yes", "No"], "No") == "Yes"


def build() -> QWidget:
    return CrashLogWidget()
