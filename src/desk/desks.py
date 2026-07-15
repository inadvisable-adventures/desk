import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from desk.temp_ui import CustomWidgetDefinition

DESK_SUFFIX = ".desk"
DEFAULT_DESK_NAME = "default" + DESK_SUFFIX


def _new_instance_id() -> str:
    return uuid.uuid4().hex[:8]


@dataclass
class WidgetState:
    widget_id: str
    x: float
    y: float
    width: float
    height: float
    instance_id: str = field(default_factory=_new_instance_id)
    # "Widget-local storage" (TODO fb76057): an arbitrary, JSON
    # -serializable per-instance payload a widget can read back on
    # restore and update on every save -- see
    # desk.shell.window.DeskWindow's get/set_widget_local_storage
    # binding.
    state: dict = field(default_factory=dict)
    # Whether this widget is locked in place (TODO 8d05920) -- a
    # chrome-level concept WidgetFrame itself owns, not routed through
    # widget-local storage above (which is for the wrapped *content*
    # widget's own data). Defaults False so an old .desk file with no
    # "locked" key still loads correctly.
    locked: bool = False
    # The tempui-DSL-defined custom widget definition's content hash
    # (TODO 5995ffd, desk.shell.window.DeskWindow
    # ._custom_widget_content_hash) at the moment *this instance* was
    # placed -- None for an ordinary widget, or a custom widget's
    # instance placed before this field existed. Lets a restored
    # instance be compared against the definition's current hash to
    # show a passive "this instance predates the currently-registered
    # definition" indicator, without requiring a widget author to
    # write any code themselves.
    placed_content_hash: str | None = None


@dataclass
class Desk:
    path: Path
    widgets: list[WidgetState] = field(default_factory=list)
    pan_x: float = 0.0
    pan_y: float = 0.0
    scale: float = 1.0
    # Promoted tempui-DSL-defined custom widgets (TODO 91b3f42) -- once
    # a DefineWidget definition is promoted via a placed instance's
    # [TEMPUI] titlebar button, it's stored here (and the original
    # .desk_temp definition file removed) so it survives independently
    # of whatever tempui file originally defined it.
    custom_widgets: list[CustomWidgetDefinition] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.path.stem

    @property
    def directory(self) -> Path:
        return self.path.parent


def default_desk_path(directory: Path) -> Path:
    return directory / DEFAULT_DESK_NAME


def discover_desk_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    files = [p for p in directory.iterdir() if p.is_file() and p.suffix == DESK_SUFFIX]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def _load_custom_widget(data: dict) -> CustomWidgetDefinition:
    size = data.get("default_size")
    return CustomWidgetDefinition(
        keyword=data["keyword"],
        label=data["label"],
        html_b64=data["html_b64"],
        default_size=(size["width"], size["height"]) if size else None,
        # Defaults to [] for a .desk file saved before TODO f693275
        # added capabilities to CustomWidgetDefinition -- no
        # "capabilities" key at all there, same as a widget.json with
        # none declared.
        capabilities=data.get("capabilities", []),
    )


def load_desk(path: Path) -> Desk:
    data = json.loads(path.read_text())
    widgets = [WidgetState(**w) for w in data.get("widgets", [])]
    custom_widgets = [_load_custom_widget(cw) for cw in data.get("custom_widgets", [])]
    return Desk(
        path=path,
        widgets=widgets,
        pan_x=data.get("pan_x", 0.0),
        pan_y=data.get("pan_y", 0.0),
        scale=data.get("scale", 1.0),
        custom_widgets=custom_widgets,
    )


def _custom_widget_dict(cw: CustomWidgetDefinition) -> dict:
    return {
        "keyword": cw.keyword,
        "label": cw.label,
        "html_b64": cw.html_b64,
        "default_size": (
            {"width": cw.default_size[0], "height": cw.default_size[1]} if cw.default_size else None
        ),
        "capabilities": cw.capabilities,
    }


def desk_state_dict(desk: Desk) -> dict:
    """The JSON-serializable shape of a Desk's state -- shared by
    save_desk (writes it to disk) and the Bridge API's workspace.getState
    (returns it over HTTP), so the two never drift apart."""
    return {
        "name": desk.name,
        "widgets": [
            {
                "widget_id": w.widget_id,
                "instance_id": w.instance_id,
                "x": w.x,
                "y": w.y,
                "width": w.width,
                "height": w.height,
                "state": w.state,
                "locked": w.locked,
                "placed_content_hash": w.placed_content_hash,
            }
            for w in desk.widgets
        ],
        "pan_x": desk.pan_x,
        "pan_y": desk.pan_y,
        "scale": desk.scale,
        "custom_widgets": [_custom_widget_dict(cw) for cw in desk.custom_widgets],
    }


def save_desk(desk: Desk) -> None:
    desk.path.parent.mkdir(parents=True, exist_ok=True)
    data = desk_state_dict(desk)
    del data["name"]  # derived from the filename itself, not stored in it
    desk.path.write_text(json.dumps(data, indent=2))
