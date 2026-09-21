# TODO aa0ce76: rotating file log for Desk's own logging.
import logging
import os
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


def temp_dir_in(base):
    directory = Path(base) / ".desk_temp"
    directory.mkdir()
    return directory


logging_setup.configure_logging()
logging_setup.configure_logging()
check("configure_logging is idempotent (one stderr handler)", len(stderr_handlers()) == 1)
check("path is <.desk_temp>/logs/desk.log", logging_setup.log_path(Path("/p/.desk_temp")) == Path("/p/.desk_temp/logs/desk.log"))

with tempfile.TemporaryDirectory() as d:
    reset_root()
    logging_setup.configure_logging()
    temp = temp_dir_in(d)
    path = logging_setup.set_log_directory(temp)
    logging.getLogger("desk.test").info("hello file log")
    for h in file_handlers():
        h.flush()
    text = path.read_text()
    check("creates logs/ inside the existing .desk_temp", path == temp / "logs" / "desk.log" and path.is_file())
    check("record written with timestamp, level and logger name",
          "INFO desk.test: hello file log" in text and text[:4].isdigit())
    check("the log path itself is logged into the file", "Logging to" in text)
    check("same directory again: idempotent, one file handler", logging_setup.set_log_directory(temp) == path and len(file_handlers()) == 1)
    reset_root()

with tempfile.TemporaryDirectory() as d:
    reset_root()
    logging_setup.configure_logging()
    first, second = Path(d) / "one", Path(d) / "two"
    first.mkdir()
    second.mkdir()
    first_temp, second_temp = temp_dir_in(first), temp_dir_in(second)
    logging_setup.set_log_directory(first_temp)
    logging.getLogger("desk.test").info("only in first")
    logging_setup.set_log_directory(second_temp)
    logging.getLogger("desk.test").info("only in second")
    for h in file_handlers():
        h.flush()
    first_text = logging_setup.log_path(first_temp).read_text()
    second_text = logging_setup.log_path(second_temp).read_text()
    check("switching directories: each instance keeps its own log",
          "only in first" in first_text and "only in second" not in first_text
          and "only in second" in second_text and "only in first" not in second_text)
    check("switching directories: exactly one file handler afterward", len(file_handlers()) == 1)
    check("None detaches the file log", logging_setup.set_log_directory(None) is None and not file_handlers())
    reset_root()

with tempfile.TemporaryDirectory() as d:
    reset_root()
    logging_setup.configure_logging()
    missing = Path(d) / ".desk_temp"
    check("a .desk_temp that doesn't exist is never created (consent)",
          logging_setup.set_log_directory(missing) is None and not missing.exists() and not file_handlers())
    reset_root()

with tempfile.TemporaryDirectory() as d:
    reset_root()
    logging_setup.configure_logging()
    temp = temp_dir_in(d)
    logging_setup.set_log_directory(temp, max_bytes=200, backup_count=2)
    for i in range(100):
        logging.getLogger("desk.test").info("rotation filler line %d", i)
    names = sorted(p.name for p in (temp / "logs").iterdir())
    check("rotates into backups", "desk.log.1" in names)
    check("never exceeds backup count", names == ["desk.log", "desk.log.1", "desk.log.2"])
    reset_root()

with tempfile.TemporaryDirectory() as d:
    reset_root()
    logging_setup.configure_logging()
    temp = temp_dir_in(d)
    (temp / "logs").write_text("a file, not a directory")
    result = logging_setup.set_log_directory(temp)
    check("unwritable location falls back without raising", result is None and not file_handlers() and len(stderr_handlers()) == 1)
    reset_root()

with tempfile.TemporaryDirectory() as d:
    reset_root()
    logging_setup.configure_logging()
    temp = temp_dir_in(d)
    path = logging_setup.set_log_directory(temp)
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

# Wiring: DeskWindow._provision_temp_ui points the log at whatever
# TempUiManager.provision returned (None when the user declined).
with tempfile.TemporaryDirectory() as d:
    import os
    from unittest.mock import MagicMock

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import desk.shell.widget_frame  # noqa: F401  (WebEngine import ordering)
    import desk.shell.canvas  # noqa: F401
    from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    from desk.shell.window import DeskWindow

    reset_root()
    logging_setup.configure_logging()
    temp = temp_dir_in(d)
    fake = MagicMock()
    fake.current_desk.directory = Path(d)
    fake._temp_ui_manager.provision.return_value = temp
    DeskWindow._provision_temp_ui(fake)
    check("_provision_temp_ui attaches the log under the provisioned .desk_temp",
          [Path(h.baseFilename) for h in file_handlers()] == [temp / "logs" / "desk.log"])
    fake._temp_ui_manager.provision.return_value = None
    DeskWindow._provision_temp_ui(fake)
    check("_provision_temp_ui detaches it when .desk_temp was declined", not file_handlers())
    reset_root()

print(f"\n{passed} passed, {failed} failed")
sys.stdout.flush()
os._exit(1 if failed else 0)
