import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path

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


@dataclass
class Desk:
    path: Path
    widgets: list[WidgetState] = field(default_factory=list)
    pan_x: float = 0.0
    pan_y: float = 0.0
    scale: float = 1.0

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


def load_desk(path: Path) -> Desk:
    data = json.loads(path.read_text())
    widgets = [WidgetState(**w) for w in data.get("widgets", [])]
    return Desk(
        path=path,
        widgets=widgets,
        pan_x=data.get("pan_x", 0.0),
        pan_y=data.get("pan_y", 0.0),
        scale=data.get("scale", 1.0),
    )


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
            }
            for w in desk.widgets
        ],
        "pan_x": desk.pan_x,
        "pan_y": desk.pan_y,
        "scale": desk.scale,
    }


def save_desk(desk: Desk) -> None:
    desk.path.parent.mkdir(parents=True, exist_ok=True)
    data = desk_state_dict(desk)
    del data["name"]  # derived from the filename itself, not stored in it
    desk.path.write_text(json.dumps(data, indent=2))
