import json
import threading
from dataclasses import dataclass
from pathlib import Path

from desk.hotreload import HotReloadBroker
from desk_services.file_watcher import WatchHandle, get_service

DEBOUNCE_SECONDS = 0.2
VALID_KINDS = ("python", "html")


@dataclass
class WidgetInfo:
    id: str
    path: Path
    kind: str  # "python" | "html"
    name: str
    entry: str
    capabilities: list[str]
    default_size: tuple[int, int] | None
    deprecated: bool = False


def _parse_manifest(manifest_path: Path) -> WidgetInfo:
    widget_id = manifest_path.parent.name
    manifest = json.loads(manifest_path.read_text())

    kind = manifest.get("kind")
    if kind not in VALID_KINDS:
        raise ValueError(
            f"widgets/{widget_id}/widget.json: 'kind' must be one of {VALID_KINDS}, got {kind!r}"
        )

    default_entry = "widget.py" if kind == "python" else "index.html"
    size = manifest.get("default_size")

    return WidgetInfo(
        id=widget_id,
        path=manifest_path.parent,
        kind=kind,
        name=manifest.get("name", widget_id),
        entry=manifest.get("entry", default_entry),
        capabilities=manifest.get("capabilities", []),
        default_size=(size["width"], size["height"]) if size else None,
        deprecated=manifest.get("deprecated", False),
    )


def discover_widgets(widgets_dir: Path) -> dict[str, WidgetInfo]:
    if not widgets_dir.is_dir():
        return {}

    widgets: dict[str, WidgetInfo] = {}
    for path in sorted(widgets_dir.iterdir()):
        manifest_path = path / "widget.json"
        if not path.is_dir() or not manifest_path.is_file():
            continue
        widgets[path.name] = _parse_manifest(manifest_path)
    return widgets


class _WidgetChangeDispatcher:
    """Extracts the changed widget's id (its directory's name -- the
    first path component under widgets_dir) from a resolved changed
    path and debounces per widget_id. Was a watchdog
    FileSystemEventHandler before TODO 578cb6b's migration onto the
    shared `desk_services.file_watcher` service, which now does the
    raw-event -> resolved-Path normalization (symlink resolution,
    FileMovedEvent handling -- see that module) this class used to
    skip entirely; widgets_dir is resolved here too so the
    relative_to comparison stays correct if it's ever symlinked (the
    same gotcha SingleFileWatcher already handled)."""

    def __init__(self, widgets_dir: Path, broker: HotReloadBroker) -> None:
        self.widgets_dir = widgets_dir.resolve()
        self.broker = broker
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def on_change(self, changed_path: Path) -> None:
        try:
            relative = changed_path.relative_to(self.widgets_dir)
        except ValueError:
            return
        if not relative.parts:
            return
        widget_id = relative.parts[0]
        self._schedule(widget_id)

    def _schedule(self, widget_id: str) -> None:
        with self._lock:
            existing = self._timers.get(widget_id)
            if existing is not None:
                existing.cancel()
            timer = threading.Timer(
                DEBOUNCE_SECONDS, self.broker.widget_changed.emit, args=(widget_id,)
            )
            timer.daemon = True
            self._timers[widget_id] = timer
            timer.start()


class WidgetWatcher:
    def __init__(self, widgets_dir: Path, broker: HotReloadBroker) -> None:
        self.widgets_dir = widgets_dir
        self._dispatcher = _WidgetChangeDispatcher(widgets_dir, broker)
        self._handle: WatchHandle | None = None

    def start(self) -> None:
        if self.widgets_dir.is_dir() and self._handle is None:
            self._handle = get_service().watch(self.widgets_dir, self._dispatcher.on_change, recursive=True)

    def stop(self, timeout: float = 5.0) -> None:
        # timeout kept for API compatibility (app.aboutToQuit calls this
        # with no args anyway) -- cancelling a subscription on the
        # shared, still-running service has nothing to join.
        if self._handle is not None:
            self._handle.cancel()
            self._handle = None
