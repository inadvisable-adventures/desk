import json
from pathlib import Path

MRU_PATH = Path.home() / ".desk" / "recent_desks.json"
MAX_MRU_ENTRIES = 10


def load_mru() -> list[Path]:
    if not MRU_PATH.is_file():
        return []
    try:
        raw = json.loads(MRU_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    paths = [Path(p) for p in raw]
    return [p for p in paths if p.is_file()]


def _save_mru(paths: list[Path]) -> None:
    MRU_PATH.parent.mkdir(parents=True, exist_ok=True)
    MRU_PATH.write_text(json.dumps([str(p) for p in paths], indent=2))


def add_to_mru(path: Path) -> list[Path]:
    path = path.resolve()
    existing = [p for p in load_mru() if p.resolve() != path]
    updated = [path, *existing][:MAX_MRU_ENTRIES]
    _save_mru(updated)
    return updated
