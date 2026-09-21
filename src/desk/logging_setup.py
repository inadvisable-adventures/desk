"""Desk's own logging setup (TODO aa0ce76): stderr output plus a
rotating file log at `<project>/.desk_temp/logs/desk.log`, so a
traceback or warning is recoverable after the fact and there is a fixed,
documented place to look. Per project (each Desk directory's own
`.desk_temp`), not Desk-wide, and deliberately readable by an agent
working in that project.

Two steps, because the project directory isn't known when logging must
start: `configure_logging()` (stderr only, at import time) and
`set_log_directory()` (attaches, or re-points, the file handler once a
Desk's `.desk_temp` is known -- at startup and on every Desk switch).
Records logged before the first `set_log_directory` reach stderr only.

`.desk_temp` itself is created only by `TempUiManager.provision`, after
asking the user -- this module never creates it, so a project that
declined it simply gets no file log.

Best-effort: if the log file can't be opened, Desk falls back to
stderr-only rather than failing."""

import logging
import logging.handlers
from pathlib import Path

LOG_DIRNAME = "logs"
LOG_FILENAME = "desk.log"
MAX_BYTES = 1_000_000
BACKUP_COUNT = 5
STDERR_FORMAT = "%(levelname)s %(name)s: %(message)s"
FILE_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

logger = logging.getLogger("desk.logging_setup")


def log_path(temp_dir: Path) -> Path:
    return temp_dir / LOG_DIRNAME / LOG_FILENAME


def configure_logging() -> None:
    """Idempotent: never adds a second stderr handler."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if any(getattr(h, "_desk_stderr", False) for h in root.handlers):
        return
    stream = logging.StreamHandler()
    stream.setFormatter(logging.Formatter(STDERR_FORMAT))
    stream._desk_stderr = True  # type: ignore[attr-defined]
    root.addHandler(stream)


def _file_handlers() -> list[logging.Handler]:
    return [h for h in logging.getLogger().handlers if getattr(h, "_desk_file", False)]


def set_log_directory(
    temp_dir: Path | None,
    *,
    max_bytes: int = MAX_BYTES,
    backup_count: int = BACKUP_COUNT,
) -> Path | None:
    """Points the file log at `temp_dir`/logs/desk.log, replacing any
    previous file handler (closed). `temp_dir` is a project's existing
    `.desk_temp`; None, or a directory that doesn't exist, just detaches
    the file log. Idempotent for the same directory. Returns the log
    file's path, or None if there is no file log."""
    path = log_path(temp_dir) if temp_dir is not None and temp_dir.is_dir() else None
    for handler in _file_handlers():
        if path is not None and Path(handler.baseFilename) == path:  # type: ignore[attr-defined]
            return path
        logging.getLogger().removeHandler(handler)
        handler.close()
    if path is None:
        return None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
    except OSError as exc:
        logger.warning("File logging unavailable (%s): %s", path, exc)
        return None
    file_handler.setFormatter(logging.Formatter(FILE_FORMAT))
    file_handler._desk_file = True  # type: ignore[attr-defined]
    logging.getLogger().addHandler(file_handler)
    logger.info("Logging to %s", path)
    return path
