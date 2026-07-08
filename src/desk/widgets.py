import json
import threading
from dataclasses import dataclass
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from desk.hotreload import HotReloadBroker

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


class _DebouncedHandler(FileSystemEventHandler):
    def __init__(self, widgets_dir: Path, broker: HotReloadBroker) -> None:
        self.widgets_dir = widgets_dir
        self.broker = broker
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def on_any_event(self, event: FileSystemEvent) -> None:
        try:
            relative = Path(event.src_path).relative_to(self.widgets_dir)
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
        self._observer = Observer()
        self._observer.schedule(_DebouncedHandler(widgets_dir, broker), str(widgets_dir), recursive=True)

    def start(self) -> None:
        if self.widgets_dir.is_dir():
            self._observer.start()

    def stop(self, timeout: float = 5.0) -> None:
        if self._observer.is_alive():
            self._observer.stop()
            self._observer.join(timeout=timeout)
