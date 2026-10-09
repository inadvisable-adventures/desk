"""Watches `<project>/desk_hmsvc/` (TODO c40c5c5) so a service directory
created or edited while Desk is running is noticed without a project
reopen or a manual Rescan click -- the same "no Desk restart needed"
goal `desk.shell.schema_file_watcher.SchemaFileWatcher` has for its own
directories, and the same shape: one instance per DeskWindow,
re-provisioned on every desk open/switch, polling for the directory
until it exists (it's created by the user, never by Desk).

Emits one debounced `changed` for any relevant change under the
directory; the receiver just calls `HmsvcManager.refresh()`."""

import threading
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from desk.hmsvc import HMSVC_DIRNAME
from desk_services.file_watcher import WatchHandle, get_service

DEBOUNCE_SECONDS = 0.3
POLL_INTERVAL_MS = 2000
# A running service writes these constantly; never a reason to rescan.
_IGNORED_PARTS = {"__pycache__", ".git", "node_modules"}
_IGNORED_SUFFIXES = {".pyc", ".pyo", ".log"}


def _is_relevant(path: Path) -> bool:
    # An event whose path is an *existing directory* is just that
    # directory's own mtime changing because something inside it did
    # (e.g. a service's __pycache__ appearing); the file inside has its
    # own event if it matters. A removed directory no longer exists, so
    # its removal still counts.
    if _IGNORED_PARTS & set(path.parts) or path.suffix in _IGNORED_SUFFIXES:
        return False
    return not path.is_dir()


class HmsvcDirWatcher(QObject):
    changed = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._handle: WatchHandle | None = None
        self._poll_timer: QTimer | None = None
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def provision(self, project_root: Path) -> None:
        self._stop()
        directory = project_root / HMSVC_DIRNAME
        if directory.is_dir():
            self._watch(directory)
            return
        timer = QTimer(self)
        timer.setInterval(POLL_INTERVAL_MS)

        def _check() -> None:
            if directory.is_dir():
                timer.stop()
                self._watch(directory)
                # The directory's contents appeared with it.
                self.changed.emit()

        timer.timeout.connect(_check)
        timer.start()
        self._poll_timer = timer

    def _watch(self, directory: Path) -> None:
        self._handle = get_service().watch(directory, self._on_change, recursive=True)

    def _on_change(self, path: Path) -> None:
        if not _is_relevant(path):
            return
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            timer = threading.Timer(DEBOUNCE_SECONDS, self.changed.emit)
            timer.daemon = True
            self._timer = timer
            timer.start()

    def _stop(self) -> None:
        if self._handle is not None:
            self._handle.cancel()
            self._handle = None
        if self._poll_timer is not None:
            self._poll_timer.stop()
            self._poll_timer = None
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
