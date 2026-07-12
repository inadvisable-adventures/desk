import json
from pathlib import Path

MRU_PATH = Path.home() / ".desk" / "recent_desks.json"
MAX_MRU_ENTRIES = 10


def _load_raw_mru() -> list[Path]:
    if not MRU_PATH.is_file():
        return []
    try:
        raw = json.loads(MRU_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    return [Path(p) for p in raw]


def load_mru() -> list[Path]:
    return [p for p in _load_raw_mru() if p.is_file()]


def prune_missing_mru_entries() -> list[Path]:
    """Like load_mru(), but also re-persists the pruned list if any
    entry's file no longer exists (TODO 8f5568f) -- load_mru() itself
    stays a plain, side-effect-free read (e.g. add_to_mru already
    re-saves its own updated list unconditionally right after calling
    it, so it doesn't need this too); this is for callers showing the
    MRU to the user, where a stale entry should actually be forgotten
    rather than silently re-filtered forever."""
    raw = _load_raw_mru()
    existing = [p for p in raw if p.is_file()]
    if len(existing) != len(raw):
        _save_mru(existing)
    return existing


def _save_mru(paths: list[Path]) -> None:
    MRU_PATH.parent.mkdir(parents=True, exist_ok=True)
    MRU_PATH.write_text(json.dumps([str(p) for p in paths], indent=2))


def add_to_mru(path: Path) -> list[Path]:
    path = path.resolve()
    existing = [p for p in load_mru() if p.resolve() != path]
    updated = [path, *existing][:MAX_MRU_ENTRIES]
    _save_mru(updated)
    return updated
