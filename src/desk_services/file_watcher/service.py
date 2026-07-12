"""A single, process-wide, de-duplicating file-watcher service.

Every existing watcher in this codebase (`desk.file_watch
.SingleFileWatcher`, `desk.widgets.WidgetWatcher`, `desk.shell
.temp_ui_manager.TempUiManager`, and formerly a bespoke copy inside
`widgets/todo/widget.py`) used to construct its own
`watchdog.observers.Observer`. That caused a real, reproducible bug:
`RuntimeError: Cannot add watch <ObservedWatch: ...> - it is already
scheduled.` -- not from watching the exact same path twice (each
`Observer` tracks its own schedules fine), but from *separate*
`Observer` instances watching paths that overlap or nest (e.g. a Desk
directory and its own `.desk_temp/` subdirectory, watched by two
different watchers) -- macOS's FSEvents backend shares native state
across `Observer` instances in a way that trips on this, even though
each `Observer`'s own bookkeeping is internally consistent.

The fix: one shared `Observer` for the whole process. Every `watch()`
call schedules onto it, so there is never a second `Observer` to
collide with. As a secondary (also explicitly requested) feature,
identical `(path, recursive)` requests share one native schedule and
fan out to every subscriber -- "a single watcher might make more than
one notification."

Deliberately thin: no debouncing, no event classification, no self
-write suppression here -- each caller keeps that domain-specific
logic exactly as before, just swapping its own `Observer()` for a
`watch()` call into this shared service.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from watchdog.events import FileMovedEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import ObservedWatch

Callback = Callable[[Path], None]


@dataclass(frozen=True)
class _WatchKey:
    path: Path  # resolved
    recursive: bool


class _NormalizingHandler(FileSystemEventHandler):
    """Hoists the two watchdog gotchas this codebase has independently
    rediscovered per-consumer (see LEARNINGS.md): FSEvents reports the
    symlink-*resolved* path, and an atomic write (write-to-scratch,
    rename-into-place) lands as a FileMovedEvent whose meaningful path
    is `dest_path`, not `src_path`. Every consumer used to duplicate
    both fixes; now there's exactly one place that does."""

    def __init__(self, key: _WatchKey, dispatch: Callable[[_WatchKey, Path], None]) -> None:
        self._key = key
        self._dispatch = dispatch

    def on_any_event(self, event) -> None:
        raw = event.dest_path if isinstance(event, FileMovedEvent) else event.src_path
        self._dispatch(self._key, Path(raw).resolve())


class WatchHandle:
    """Returned by `FileWatcherService.watch()`. Call `cancel()` to
    unsubscribe -- safe to call more than once. When the last
    subscriber for a `(path, recursive)` key cancels, the underlying
    native watch is actually unscheduled."""

    def __init__(self, service: "FileWatcherService", key: _WatchKey, callback: Callback) -> None:
        self._service = service
        self._key = key
        self._callback = callback
        self._cancelled = False

    def cancel(self) -> None:
        if self._cancelled:
            return
        self._cancelled = True
        self._service._unsubscribe(self._key, self._callback)


class FileWatcherService:
    """Owns exactly one `watchdog.observers.Observer` for its whole
    lifetime. Construct one directly for isolated use (e.g. tests);
    the app itself uses the shared `get_service()` singleton so every
    watch request in the process lands on the same `Observer`."""

    def __init__(self) -> None:
        self._observer = Observer()
        self._observer.start()
        self._lock = threading.Lock()
        self._subscribers: dict[_WatchKey, list[Callback]] = {}
        self._observed_watches: dict[_WatchKey, ObservedWatch] = {}

    def watch(self, path: Path, callback: Callback, *, recursive: bool = False) -> WatchHandle:
        """Subscribe `callback` to changes under `path` (a directory --
        watchdog can't watch a single file directly; callers watching
        one file pass its parent and filter the resolved path
        themselves, same as before this service existed).  `callback`
        is invoked with the resolved, gotcha-normalized changed path,
        on the watchdog background thread -- exactly as every existing
        consumer already expected before migrating onto this service."""
        key = _WatchKey(path.resolve(), recursive)
        with self._lock:
            subscribers = self._subscribers.setdefault(key, [])
            subscribers.append(callback)
            if key not in self._observed_watches:
                handler = _NormalizingHandler(key, self._dispatch)
                watch = self._observer.schedule(handler, str(key.path), recursive=recursive)
                self._observed_watches[key] = watch
        return WatchHandle(self, key, callback)

    def _dispatch(self, key: _WatchKey, changed_path: Path) -> None:
        with self._lock:
            callbacks = list(self._subscribers.get(key, ()))
        for callback in callbacks:
            callback(changed_path)

    def _unsubscribe(self, key: _WatchKey, callback: Callback) -> None:
        with self._lock:
            subscribers = self._subscribers.get(key)
            if subscribers is None:
                return
            if callback in subscribers:
                subscribers.remove(callback)
            if subscribers:
                return
            del self._subscribers[key]
            watch = self._observed_watches.pop(key, None)
        if watch is not None:
            self._observer.unschedule(watch)

    def stop(self, timeout: float = 5.0) -> None:
        """Stops the shared Observer thread entirely -- for clean
        process shutdown (see desk.app), not per-subscriber teardown
        (use WatchHandle.cancel() for that)."""
        if self._observer.is_alive():
            self._observer.stop()
            self._observer.join(timeout=timeout)


_service: FileWatcherService | None = None
_service_lock = threading.Lock()


def get_service() -> FileWatcherService:
    """The process-wide shared instance every app/widget watcher uses.
    Lazily constructed (not at import time) so importing this module
    never starts a background thread as a side effect."""
    global _service
    with _service_lock:
        if _service is None:
            _service = FileWatcherService()
        return _service
