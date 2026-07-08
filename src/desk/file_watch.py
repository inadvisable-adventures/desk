"""A reusable single-file watcher for widgets that render/track one file
on disk. Extracted from the TODO widget's own watcher (widgets/todo/) so
its two hard-won correctness details -- see LEARNINGS.md -- live in one
place instead of being re-derived (and re-broken) per widget:

- FSEvents (the macOS watchdog backend) reports the *symlink-resolved*
  path in an event, and `tempfile.mkdtemp()` (plus some real Desk
  directories) is a symlink -- so both the target and each event path
  must be `.resolve()`d before comparing, or the watcher silently never
  matches.
- A common "atomic write" idiom (write a scratch file, then rename it
  over the target) lands as a `FileMovedEvent` whose meaningful path is
  `dest_path`, not `src_path` -- reading `src_path` unconditionally
  misses every editor/tool that saves via rename.

Widget directories can't import each other, so shared widget logic like
this lives in `desk.` proper (same pattern as `desk.terminal_widget`).
"""

import threading
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal
from watchdog.events import FileMovedEvent, FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

DEBOUNCE_SECONDS = 0.3


class _Handler(FileSystemEventHandler):
    def __init__(self, target_path: Path, relay: "SingleFileWatcher") -> None:
        self._target = target_path.resolve()
        self._relay = relay
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def on_any_event(self, event: FileSystemEvent) -> None:
        raw = event.dest_path if isinstance(event, FileMovedEvent) else event.src_path
        if Path(raw).resolve() != self._target:
            return
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(DEBOUNCE_SECONDS, self._relay.changed.emit)
            self._timer.daemon = True
            self._timer.start()


class SingleFileWatcher(QObject):
    """Watches one file for external changes, emitting `changed` (queued
    onto the GUI thread by Qt, since watchdog fires on its own thread) on
    any create/modify/rename-into-place, debounced. `watch(path)`
    (re)starts it -- a no-op if already watching that exact path;
    `stop()` tears the observer down and is safe to call from a
    `destroyed`-triggered teardown closure (it touches only the watchdog
    Observer, never Qt state)."""

    changed = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._observer: Observer | None = None
        self._path: Path | None = None

    def watch(self, path: Path) -> None:
        if path == self._path and self._observer is not None:
            return
        self.stop()
        observer = Observer()
        observer.schedule(_Handler(path, self), str(path.parent), recursive=False)
        observer.start()
        self._observer = observer
        self._path = path

    def stop(self) -> None:
        if self._observer is not None:
            self._observer.stop()
            self._observer = None
        self._path = None
