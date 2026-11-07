"""Watches a promoted custom widget's own real source directory
(`desk_widgets/<name>/`) for changes (TODO 4eb3d9e), so editing it
directly is enough on its own to mark every already-placed instance
`[STALE]` -- the same live experience a still-`.desk_temp`-sourced
`DefineWidget` custom widget's own live edits already have, without
depending on `.desk_temp/build_widget.py` being re-run against an
already-promoted widget at all (the documented workflow
`../FEEDBACK/FEEDBACK-DESK-promoted-widgets-no-stale-marker-2026-09-15-1744.md`
found silently broken).

TODO 8a65056: also watches the files its `tsconfig.json` `"files"` array
references from *outside* the widget directory (a shared base class or
module), so one edit to a shared file marks every dependent widget
`[STALE]` -- see plans/shared-file-staleness.md. Cites
`../FEEDBACK/FEEDBACK-DESK-shared-widget-file-edits-may-not-mark-dependents-stale-2026-10-21-0038.md`.

See plans/promoted-widget-source-staleness.md.
"""

import threading
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from desk.custom_widgets import external_source_files, source_watch_exclusions
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
        self._handles: dict[str, list[WatchHandle]] = {}
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def watch(self, keyword: str, widget_dir: Path) -> None:
        """(Re-)starts watching `widget_dir` (recursively) for
        `keyword`, plus every file its `tsconfig.json` `"files"` array
        references outside `widget_dir` (TODO 8a65056). Safe to call
        repeatedly for the same keyword --
        e.g. every time `_register_custom_widget` re-registers it --
        so a `source_path` relocation (promotion, or any future
        re-relocation) is automatically picked up on the very next
        registration, with no separate invalidation step needed. An edit
        to the widget's own `tsconfig.json` re-arms the watch too, so a
        newly added shared file is followed without a re-registration."""
        self.stop_watching(keyword)
        exclusions = source_watch_exclusions(widget_dir)
        tsconfig_path = (widget_dir / "tsconfig.json").resolve()

        # Sticky across debounce restarts: a tsconfig save usually comes
        # with other writes that restart the timer, and the re-arm must
        # still happen when it finally fires.
        pending = {"rearm": False}

        def _trigger(rearm: bool) -> None:
            with self._lock:
                pending["rearm"] = pending["rearm"] or rearm
                existing = self._timers.get(keyword)
                if existing is not None:
                    existing.cancel()
                timer = threading.Timer(DEBOUNCE_SECONDS, _fire)
                timer.daemon = True
                self._timers[keyword] = timer
                timer.start()

        def _fire() -> None:
            with self._lock:
                rearm, pending["rearm"] = pending["rearm"], False
            if rearm and keyword in self._handles:
                self.watch(keyword, widget_dir)
            self.changed.emit(keyword)

        def _on_change(path: Path) -> None:
            if any(path == excluded or excluded in path.parents for excluded in exclusions):
                return
            _trigger(path == tsconfig_path)

        handles = [get_service().watch(widget_dir, _on_change, recursive=True)]

        # A watch needs a directory, so each shared file is watched via
        # its parent (non-recursively) and filtered down to the file.
        shared_by_dir: dict[Path, set[Path]] = {}
        for shared in external_source_files(widget_dir):
            if shared.parent.is_dir():
                shared_by_dir.setdefault(shared.parent.resolve(), set()).add(shared.parent.resolve() / shared.name)
        for directory, files in shared_by_dir.items():

            def _on_shared_change(path: Path, files: set[Path] = files) -> None:
                if path in files:
                    _trigger(False)

            handles.append(get_service().watch(directory, _on_shared_change, recursive=False))
        self._handles[keyword] = handles

    def stop_watching(self, keyword: str) -> None:
        for handle in self._handles.pop(keyword, []):
            handle.cancel()
        with self._lock:
            timer = self._timers.pop(keyword, None)
        if timer is not None:
            timer.cancel()

    def stop_all(self) -> None:
        for keyword in list(self._handles):
            self.stop_watching(keyword)
