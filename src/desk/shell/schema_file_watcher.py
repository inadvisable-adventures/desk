"""Watches for top-level desk.state.* schema files (TODO 9aef267) --
files declaring a schema independent of any widget's manifest, at two
locations: an ephemeral `.desk_temp/schemas/` (created by
TempUiManager.provision alongside `.desk_temp`'s other subdirectories)
and a real, git-tracked `./desk-schemas/` that Desk never creates
eagerly, only watches for and picks up immediately once it exists. See
plans/state-store-top-level-schemas.md.

A schema file is a plain JSON object, `{"<key>": "<type expression>",
...}` -- the same shape a real widget.json's own `state_schema` field
already is (desk.schema_types.parse_type_expression handles both).
Only `*.json` files are considered; anything else in a watched
directory is ignored.
"""

import threading
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from desk_services.file_watcher import WatchHandle, get_service

SCHEMA_FILES_DIRNAME = "schemas"
TOP_LEVEL_SCHEMAS_DIRNAME = "desk-schemas"
# Same reasoning as TempUiManager's own tempui-file debounce: a single
# logical save can fire more than one raw watchdog event.
DEBOUNCE_SECONDS = 0.3
# ./desk-schemas/ can't be watched directly with watchdog until it
# exists -- polled at this interval rather than watching the entire
# project root just to catch its own creation (see the plan's own
# "Design decisions" for why: no real design goal here actually needs
# sub-second detection, just "no Desk restart needed").
POLL_INTERVAL_MS = 2000


class SchemaFileWatcher(QObject):
    """One instance per DeskWindow, for the app's lifetime -- re
    -provisioned on every desk open/switch via `provision`, the same
    lifecycle shape as `desk.shell.temp_ui_manager.TempUiManager`."""

    changed = pyqtSignal(Path)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._handles: list[WatchHandle] = []
        self._poll_timer: QTimer | None = None
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def provision(self, ephemeral_dir: Path | None, project_root: Path) -> None:
        self._stop()
        if ephemeral_dir is not None:
            self._watch_existing_directory(ephemeral_dir)

        top_level_dir = project_root / TOP_LEVEL_SCHEMAS_DIRNAME
        if top_level_dir.is_dir():
            self._watch_existing_directory(top_level_dir)
        else:
            self._start_polling(top_level_dir)

    def _start_polling(self, top_level_dir: Path) -> None:
        timer = QTimer(self)
        timer.setInterval(POLL_INTERVAL_MS)

        def _check() -> None:
            if top_level_dir.is_dir():
                timer.stop()
                self._watch_existing_directory(top_level_dir)

        timer.timeout.connect(_check)
        timer.start()
        self._poll_timer = timer

    def _watch_existing_directory(self, directory: Path) -> None:
        # Resolved (TODO 9aef267): the shared file-watcher service
        # reports every live event through a symlink-resolved path
        # (see desk_services.file_watcher's own _NormalizingHandler) --
        # this initial scan must match exactly, or the same physical
        # file gets a different `source` string depending on whether it
        # was seen here or via a later live edit, leaking a duplicate,
        # spuriously-conflicting registry entry for itself.
        resolved_directory = directory.resolve()
        for path in sorted(resolved_directory.glob("*.json")):
            if path.is_file():
                self.changed.emit(path)
        handle = get_service().watch(directory, self._on_change, recursive=False)
        self._handles.append(handle)

    def _on_change(self, path: Path) -> None:
        if path.suffix != ".json":
            return
        with self._lock:
            existing = self._timers.get(str(path))
            if existing is not None:
                existing.cancel()
            timer = threading.Timer(DEBOUNCE_SECONDS, self.changed.emit, args=(path,))
            timer.daemon = True
            self._timers[str(path)] = timer
            timer.start()

    def _stop(self) -> None:
        for handle in self._handles:
            handle.cancel()
        self._handles = []
        if self._poll_timer is not None:
            self._poll_timer.stop()
            self._poll_timer = None
        with self._lock:
            for timer in self._timers.values():
                timer.cancel()
            self._timers = {}
