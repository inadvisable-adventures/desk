import json
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path

from desk.hotreload import HotReloadBroker
from desk_services.file_watcher import WatchHandle, get_service

logger = logging.getLogger(__name__)

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
    # Set only for a tempui-DSL-defined custom widget (TODO 91b3f42,
    # desk.temp_ui's DefineWidget keyword) -- never by _parse_manifest
    # below, so every widget discovered from a real widgets/<id>/
    # directory always has this False. Excludes it from the right
    # -click "Add widget" catalog (see WorkspaceView.contextMenuEvent):
    # a widget defined this way can only ever be placed via tempui.
    tempui_only: bool = False
    # A short content hash of the currently-registered definition (TODO
    # 5995ffd) -- set only for a tempui-DSL-defined custom widget (see
    # DeskWindow._register_custom_widget), never by _parse_manifest
    # below. Surfaced over the Bridge API's self.getManifest() so a
    # widget's own JS can compare it against what it expects, and used
    # internally to detect a placed instance that predates the current
    # definition (see WidgetFrame.placed_content_hash).
    content_hash: str | None = None
    # desk.state.* schema declarations (TODO af7898b) -- key -> a
    # TypeScript type expression string (see desk.schema_types). Read
    # from a real widget.json's own "state_schema" key by _parse_manifest
    # below, or from CustomWidgetDefinition.state_schema for a
    # tempui-DSL-defined custom widget (see DeskWindow
    # ._register_custom_widget).
    state_schema: dict[str, str] = field(default_factory=dict)
    # Schema conflict/syntax-error messages Desk itself has appended
    # (TODO af7898b) -- never read from or written to a real widget.json
    # on disk (see plans/state-store-schema-core.md's "Decided in this
    # planning pass" note); purely in-memory, populated by
    # DeskWindow._refresh_builtin_schemas/_place_widget, and lost the
    # next time this WidgetInfo is freshly rebuilt (a hot reload, or the
    # underlying conflict being resolved).
    desk_widget_loading_errors: list[str] = field(default_factory=list)


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
        state_schema=manifest.get("state_schema", {}),
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


def discover_project_widgets(
    widgets_dir: Path, *, kinds: tuple[str, ...] = ("python",)
) -> dict[str, WidgetInfo]:
    """Like discover_widgets, but for a project's own desk_widgets/ (TODO
    99eb1bc) instead of Desk's shared, presumed-vetted widgets/ tree --
    used for a real, project-authored widget package (same widget.json
    shape as a built-in widgets/<id>/ directory) dropped straight into a
    project, no promotion step. `kinds` restricts which `"kind"` values
    are accepted (default: `"python"` only) -- `"html"` isn't wired up
    yet (the Local Web Server only ever serves the shared widgets_dir
    and tempui-DSL-registered custom widgets, see
    ServerHandle.mount_html_widget; PARKINGLOT.md's "Default to
    authoring an explicitly-requested widget as a real project widget"
    is the parked follow-up for that), so a `kind: "html"` entry here is
    skipped with an explanatory warning rather than silently doing
    nothing or being merged into a catalog that can't actually serve it.

    desk_widgets/ already has an older, unrelated tenant: a tempui-DSL
    -promoted custom widget's durable TypeScript/HTML source (TODO
    59c5a70), whose own widget.json is shaped `{"keyword", "label",
    "width", "height", ...}` -- no "kind" key at all. That's the one
    thing distinguishing the two conventions on disk, so any
    subdirectory whose widget.json lacks "kind" entirely is silently
    skipped here as belonging to that other convention, not treated as
    a malformed real widget.

    Also unlike discover_widgets (which happily lets _parse_manifest's
    ValueError propagate, since Desk's own bundled widgets/ is trusted,
    reviewed content), a directory that does declare "kind" but fails
    to parse -- an invalid kind value, unreadable/malformed JSON -- is
    skipped with a logged warning instead: this scans arbitrary,
    unreviewed project content, and one project's own typo must never
    take down widget discovery (built-in or otherwise) for every open
    Desk."""
    if not widgets_dir.is_dir():
        return {}

    widgets: dict[str, WidgetInfo] = {}
    for path in sorted(widgets_dir.iterdir()):
        manifest_path = path / "widget.json"
        if not path.is_dir() or not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text())
        except (OSError, json.JSONDecodeError):
            logger.warning("Skipping %s: unreadable or malformed widget.json", manifest_path)
            continue
        if not isinstance(manifest, dict) or "kind" not in manifest:
            # No "kind" key at all -- a promoted-tempui-widget source
            # directory (or something else entirely), not our concern.
            continue
        if manifest["kind"] not in kinds:
            logger.warning(
                "Skipping %s: kind %r not yet supported for a project widget (only %s)",
                manifest_path,
                manifest["kind"],
                ", ".join(repr(k) for k in kinds),
            )
            continue
        try:
            widgets[path.name] = _parse_manifest(manifest_path)
        except ValueError:
            logger.warning("Skipping %s: invalid widget.json", manifest_path, exc_info=True)
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
