from pathlib import Path


def resolve_persisted_path(raw: str | None) -> Path | None:
    """Recovers a widget-local-storage path at Desk-restore time,
    tolerating a since-moved/deleted file gracefully (TODO 02eda20):
    returns None for a missing/empty value or one that no longer
    points at a real file, letting the caller fall back to its normal
    no-file-open placeholder state instead of adopting a bogus path."""
    if not raw:
        return None
    path = Path(raw)
    if not path.is_file():
        return None
    return path
