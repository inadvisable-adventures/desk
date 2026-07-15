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


class SelfWriteMemory:
    """Remembers the text a consumer most recently wrote to a given key
    (a resolved `Path` for a watcher of one file, a bare filename for a
    watcher of many files in a directory) so a change notification that
    merely echoes that write back can be told apart from a real external
    change -- shared by `SingleFileWatcher` and `desk.shell
    .temp_ui_manager.TempUiManager` (TODO cee6f74) so there's one
    implementation of this idea instead of two independently-written
    copies."""

    def __init__(self) -> None:
        self._last_written: dict[object, str] = {}

    def record(self, key: object, text: str) -> None:
        self._last_written[key] = text

    def is_own_write(self, key: object, text: str) -> bool:
        return text == self._last_written.get(key)


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
        self._writes = SelfWriteMemory()

    def watch(self, path: Path) -> None:
        if path == self._path and self._handle is not None:
            return
        self.stop()
        target = path.resolve()

        def on_change(changed_path: Path) -> None:
            if changed_path != target:
                return
            try:
                fresh = path.read_text()
            except OSError:
                fresh = None
            except UnicodeDecodeError:
                # TODO 6e731c1: every earlier SingleFileWatcher consumer
                # only ever watched text files (Markdown, SVG, TODO.md,
                # ...) -- a binary-backed one (e.g. the Image Viewer
                # widget) hits this on every real external change,
                # since read_text() can't decode arbitrary bytes as
                # UTF-8. Confirmed directly: uncaught, this propagated
                # out of watchdog's own dispatch thread and silently
                # killed the changed notification entirely (never even
                # reached the debounce timer below) -- self-write
                # suppression (record_own_write) simply doesn't apply to
                # binary content, so there's nothing to compare against;
                # treat it the same as an unreadable file (always
                # notify, never suppress).
                fresh = None
            if fresh is not None and self._writes.is_own_write(target, fresh):
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
        content equals `text` -- same `SelfWriteMemory` mechanism
        `desk.shell.temp_ui_manager.TempUiManager` uses for its own
        self-write suppression (TODO cee6f74). Used by any
        `SingleFileWatcher` consumer that writes the file it's
        watching -- e.g. the TODO widget's `_write_and_commit` and the
        Editor widget's save methods. Not one-time: keeps comparing
        against the last-recorded text until called again, matching
        `TempUiManager`'s existing behavior exactly."""
        if self._path is not None:
            self._writes.record(self._path.resolve(), text)

    def stop(self) -> None:
        if self._handle is not None:
            self._handle.cancel()
            self._handle = None
        self._path = None
        self._writes = SelfWriteMemory()
        with self._timer_lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
