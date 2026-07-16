import importlib.util
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from desk.event_mediator import EventMediator, LOG_FILENAME  # noqa: E402
from desk.temp_ui import TEMP_UI_DIRNAME  # noqa: E402
from desk.shell import current_context  # noqa: E402

app = QApplication.instance() or QApplication([])

REPO_ROOT = Path("/Users/mphair/inadvisable-adventures/desk")

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


# ---------- window.py source-level check ----------

window_src = (REPO_ROOT / "src/desk/shell/window.py").read_text()
check(
    "window.py sets log directory under TEMP_UI_DIRNAME",
    "self._event_mediator.set_log_directory(self.current_desk.directory / TEMP_UI_DIRNAME)" in window_src,
)
check(
    "window.py no longer sets log directory to the bare project directory",
    "self._event_mediator.set_log_directory(self.current_desk.directory)\n" not in window_src,
)

# ---------- EventMediator writes under .desk_temp ----------

with tempfile.TemporaryDirectory() as d:
    project_dir = Path(d)
    mediator = EventMediator()
    mediator.set_log_directory(project_dir / TEMP_UI_DIRNAME)
    check("log_path resolves under .desk_temp", mediator.log_path == project_dir / TEMP_UI_DIRNAME / LOG_FILENAME)
    check(".desk_temp doesn't exist yet", not (project_dir / TEMP_UI_DIRNAME).exists())

    event = mediator.publish("test.event", {"x": 1}, "sender-1")
    check("publish returned an event", event.name == "test.event")
    check(".desk_temp got created as a side effect of the first publish", (project_dir / TEMP_UI_DIRNAME).is_dir())
    check("log written under .desk_temp, not the project dir directly", (project_dir / TEMP_UI_DIRNAME / LOG_FILENAME).is_file())
    check("no stray log file in the project directory itself", not (project_dir / LOG_FILENAME).is_file())

    content = (project_dir / TEMP_UI_DIRNAME / LOG_FILENAME).read_text()
    check("row contains the published event name", "test.event" in content)


# ---------- Event Log widget computes the same new location ----------

spec = importlib.util.spec_from_file_location(
    "event_log_widget_relocate_check", REPO_ROOT / "widgets/event_log/widget.py"
)
event_log_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(event_log_module)

with tempfile.TemporaryDirectory() as d:
    project_dir = Path(d)
    current_context.set_current_desk_directory(project_dir)
    widget = event_log_module.EventLogWidget()
    check(
        "Event Log widget watches the relocated path",
        widget._log_path == project_dir / TEMP_UI_DIRNAME / LOG_FILENAME,
    )
    check(
        "Event Log widget's status label shows the new path",
        str(project_dir / TEMP_UI_DIRNAME / LOG_FILENAME) in widget._status_label.text(),
    )
    widget.deleteLater()

current_context.set_current_desk_directory(None)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
