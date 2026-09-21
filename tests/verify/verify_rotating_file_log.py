# TODO aa0ce76: rotating file log for Desk's own logging.
import logging
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "src")

from desk import crash_handler, logging_setup  # noqa: E402

passed = 0
failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


def reset_root():
    root = logging.getLogger()
    for h in list(root.handlers):
        if getattr(h, "_desk_file", False) or getattr(h, "_desk_stderr", False):
            h.close()
            root.removeHandler(h)


def file_handlers():
    return [h for h in logging.getLogger().handlers if getattr(h, "_desk_file", False)]


def stderr_handlers():
    return [h for h in logging.getLogger().handlers if getattr(h, "_desk_stderr", False)]


check("default location is ~/.desk/logs/desk.log", logging_setup.log_path() == Path.home() / ".desk" / "logs" / "desk.log")

with tempfile.TemporaryDirectory() as d:
    reset_root()
    path = logging_setup.configure_logging(Path(d) / "nested" / "logs")
    logging.getLogger("desk.test").info("hello file log")
    for h in file_handlers():
        h.flush()
    text = path.read_text()
    check("creates missing directory and file, returns path", path.is_file())
    check("record written with timestamp, level and logger name",
          "INFO desk.test: hello file log" in text and text[:4].isdigit())
    logging_setup.configure_logging(Path(d) / "nested" / "logs")
    check("idempotent: one file handler, one stderr handler", len(file_handlers()) == 1 and len(stderr_handlers()) == 1)
    reset_root()

with tempfile.TemporaryDirectory() as d:
    reset_root()
    path = logging_setup.configure_logging(Path(d), max_bytes=200, backup_count=2)
    for i in range(100):
        logging.getLogger("desk.test").info("rotation filler line %d", i)
    names = sorted(p.name for p in Path(d).iterdir())
    check("rotates into backups", "desk.log.1" in names)
    check("never exceeds backup count", names == ["desk.log", "desk.log.1", "desk.log.2"])
    reset_root()

with tempfile.TemporaryDirectory() as d:
    reset_root()
    blocker = Path(d) / "blocker"
    blocker.write_text("a file, not a directory")
    result = logging_setup.configure_logging(blocker / "logs")
    check("unwritable location falls back without raising", result is None and not file_handlers() and len(stderr_handlers()) == 1)
    reset_root()

with tempfile.TemporaryDirectory() as d:
    reset_root()
    path = logging_setup.configure_logging(Path(d))
    try:
        raise RuntimeError("boom for crash log")
    except RuntimeError:
        exc_info = sys.exc_info()
    crash_handler._previous_excepthook = None
    original_log_path = crash_handler._log_path
    crash_handler._log_path = lambda: Path(d) / "DESK-CRASH-test.log"
    try:
        crash_handler._handle_exception(*exc_info)
    finally:
        crash_handler._log_path = original_log_path
    for h in file_handlers():
        h.flush()
    text = path.read_text()
    check("uncaught exception traceback lands in the rotating log",
          "CRITICAL desk: Uncaught exception" in text and "RuntimeError: boom for crash log" in text)
    check("per-project crash file still written", (Path(d) / "DESK-CRASH-test.log").is_file())
    reset_root()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
