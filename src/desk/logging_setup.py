"""Desk's own logging setup (TODO aa0ce76): the existing stderr output
plus a rotating file log at `~/.desk/logs/desk.log`, so a traceback or
warning is recoverable after the fact and there is a fixed, documented
place to look. Desk-wide rather than per-project, alongside
`~/.desk/recent_desks.json`.

Best-effort: if the log directory can't be created or opened, Desk falls
back to stderr-only rather than failing to start."""

import logging
import logging.handlers
from pathlib import Path

LOG_DIR = Path.home() / ".desk" / "logs"
LOG_FILENAME = "desk.log"
MAX_BYTES = 1_000_000
BACKUP_COUNT = 5
STDERR_FORMAT = "%(levelname)s %(name)s: %(message)s"
FILE_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def log_path(log_dir: Path | None = None) -> Path:
    return (log_dir or LOG_DIR) / LOG_FILENAME


def configure_logging(
    log_dir: Path | None = None,
    *,
    max_bytes: int = MAX_BYTES,
    backup_count: int = BACKUP_COUNT,
) -> Path | None:
    """Idempotent: never adds a second stderr or file handler. Returns
    the log file's path, or None if the file log couldn't be set up."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(getattr(h, "_desk_stderr", False) for h in root.handlers):
        stream = logging.StreamHandler()
        stream.setFormatter(logging.Formatter(STDERR_FORMAT))
        stream._desk_stderr = True  # type: ignore[attr-defined]
        root.addHandler(stream)
    for handler in root.handlers:
        if getattr(handler, "_desk_file", False):
            return Path(handler.baseFilename)  # type: ignore[attr-defined]
    path = log_path(log_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
    except OSError as exc:
        logging.getLogger("desk").warning("File logging unavailable (%s): %s", path, exc)
        return None
    file_handler.setFormatter(logging.Formatter(FILE_FORMAT))
    file_handler._desk_file = True  # type: ignore[attr-defined]
    root.addHandler(file_handler)
    return path
