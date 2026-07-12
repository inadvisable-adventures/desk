"""A reusable single-file watcher for widgets that render/track one file
on disk. Delegates the actual OS-level watching to the shared
`desk_services.file_watcher` service (TODO 578cb6b) -- previously this
constructed its own `watchdog.observers.Observer` per instance, which
is exactly the pattern that caused a real, reproducible `RuntimeError:
... already scheduled` (separate `Observer`s watching overlapping/
nested paths collide at macOS's FSEvents layer; see
`desk_services.file_watcher.service`'s module docstring and
`LEARNINGS.md`). The service also centralizes the two watchdog gotchas
this module used to handle itself (symlink-resolved event paths,
`FileMovedEvent`'s real path being `dest_path`) -- this class no longer
needs to.

Widget directories can't import each other, so shared widget logic like
this lives in `desk.` proper (same pattern as `desk.terminal_widget`).
"""

import threading
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from desk_services.file_watcher import WatchHandle, get_service

DEBOUNCE_SECONDS = 0.3


class SingleFileWatcher(QObject):
    """Watches one file for external changes, emitting `changed` (queued
    onto the GUI thread by Qt, since watchdog fires on its own thread) on
    any create/modify/rename-into-place, debounced. `watch(path)`
    (re)starts it -- a no-op if already watching that exact path;
    `stop()` cancels the underlying subscription and is safe to call
    from a `destroyed`-triggered teardown closure (it touches only the
    shared watcher service, never Qt state)."""

    changed = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._handle: WatchHandle | None = None
        self._path: Path | None = None
        self._timer: threading.Timer | None = None
        self._timer_lock = threading.Lock()
        self._expected_write: str | None = None

    def watch(self, path: Path) -> None:
        if path == self._path and self._handle is not None:
            return
        self.stop()
        target = path.resolve()

        def on_change(changed_path: Path) -> None:
            if changed_path != target:
                return
            if self._expected_write is not None:
                try:
                    fresh = path.read_text()
                except OSError:
                    fresh = None
                if fresh == self._expected_write:
                    return
            with self._timer_lock:
                if self._timer is not None:
                    self._timer.cancel()
                self._timer = threading.Timer(DEBOUNCE_SECONDS, self.changed.emit)
                self._timer.daemon = True
                self._timer.start()

        self._handle = get_service().watch(path.parent, on_change, recursive=False)
        self._path = path

    def record_own_write(self, text: str) -> None:
        """Suppresses the next change notification if the file's fresh
        content equals `text` -- same mechanism `desk.shell
        .temp_ui_manager.TempUiManager` already used (and still uses)
        for its own self-write suppression, now available to any
        `SingleFileWatcher` consumer that writes the file it's
        watching (e.g. the TODO widget, TODO 578cb6b's consolidation of
        its formerly-bespoke watcher onto this class). Not one-time:
        keeps comparing against the last-recorded text until called
        again, matching `TempUiManager`'s existing behavior exactly."""
        self._expected_write = text

    def stop(self) -> None:
        if self._handle is not None:
            self._handle.cancel()
            self._handle = None
        self._path = None
        self._expected_write = None
        with self._timer_lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
