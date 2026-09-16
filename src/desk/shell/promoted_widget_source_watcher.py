"""Watches a promoted custom widget's own real source directory
(`desk_widgets/<name>/`) for changes (TODO 4eb3d9e), so editing it
directly is enough on its own to mark every already-placed instance
`[STALE]` -- the same live experience a still-`.desk_temp`-sourced
`DefineWidget` custom widget's own live edits already have, without
depending on `.desk_temp/build_widget.py` being re-run against an
already-promoted widget at all (the documented workflow
`../FEEDBACK/FEEDBACK-DESK-promoted-widgets-no-stale-marker-2026-09-15-1744.md`
found silently broken).

See plans/promoted-widget-source-staleness.md.
"""

import threading
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from desk.custom_widgets import source_watch_exclusions
from desk_services.file_watcher import WatchHandle, get_service

# Same reasoning/value as TempUiManager's and SchemaFileWatcher's own
# debounce: a single logical save can still fire more than one raw
# watchdog event.
DEBOUNCE_SECONDS = 0.3


class PromotedWidgetSourceWatcher(QObject):
    """One instance per `DeskWindow`, for the app's lifetime -- same
    lifecycle shape as `desk.shell.schema_file_watcher.SchemaFileWatcher`,
    but keyed per widget keyword rather than a single fixed directory,
    since each promoted widget has its own independent source tree."""

    changed = pyqtSignal(str)  # keyword

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._handles: dict[str, WatchHandle] = {}
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def watch(self, keyword: str, widget_dir: Path) -> None:
        """(Re-)starts watching `widget_dir` (recursively) for
        `keyword`. Safe to call repeatedly for the same keyword --
        e.g. every time `_register_custom_widget` re-registers it --
        so a `source_path` relocation (promotion, or any future
        re-relocation) is automatically picked up on the very next
        registration, with no separate invalidation step needed."""
        self.stop_watching(keyword)
        exclusions = source_watch_exclusions(widget_dir)

        def _on_change(path: Path) -> None:
            if any(path == excluded or excluded in path.parents for excluded in exclusions):
                return
            with self._lock:
                existing = self._timers.get(keyword)
                if existing is not None:
                    existing.cancel()
                timer = threading.Timer(DEBOUNCE_SECONDS, self.changed.emit, args=(keyword,))
                timer.daemon = True
                self._timers[keyword] = timer
                timer.start()

        self._handles[keyword] = get_service().watch(widget_dir, _on_change, recursive=True)

    def stop_watching(self, keyword: str) -> None:
        handle = self._handles.pop(keyword, None)
        if handle is not None:
            handle.cancel()
        with self._lock:
            timer = self._timers.pop(keyword, None)
        if timer is not None:
            timer.cancel()

    def stop_all(self) -> None:
        for keyword in list(self._handles):
            self.stop_watching(keyword)
