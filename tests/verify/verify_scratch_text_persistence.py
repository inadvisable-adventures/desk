"""TODO a7618c8: a Scratch not attached to a tempui file persists its label and
text in .desk_temp/scratch-text/<instance_id>.json across a restore."""
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from desk.desks import Desk  # noqa: E402
from desk.event_mediator import EventMediator  # noqa: E402
from desk.hotreload import HotReloadBroker  # noqa: E402
from desk.shell.canvas import WorkspaceView  # noqa: E402
from desk.shell.window import DeskWindow, SCRATCH_WIDGET_ID  # noqa: E402
from desk.shell.promoted_widget_source_watcher import PromotedWidgetSourceWatcher  # noqa: E402
from desk.temp_ui import TEMP_UI_DIRNAME, is_temp_ui_filename  # noqa: E402
from desk.widgets import WidgetInfo  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
passed = failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


class _FakeHandle:
    token = "tok"

    def widget_url(self, widget_id):
        return f"http://fake/{widget_id}"


class _FakeWindow:
    def __init__(self, directory):
        self.current_desk = Desk(path=directory / "test.desk")
        self._widgets = {
            SCRATCH_WIDGET_ID: WidgetInfo(
                id=SCRATCH_WIDGET_ID, path=Path("widgets") / SCRATCH_WIDGET_ID, kind="python",
                name="Scratch", entry="widget.py", capabilities=[], default_size=(400, 300),
            )
        }
        self._handle = _FakeHandle()
        self._custom_widget_definitions = {}
        self._custom_widget_sources = {}
        self._custom_widget_content_hash = {}
        self._promoted_widget_source_watcher = PromotedWidgetSourceWatcher()
        self._promoted_widget_source_dirty = set()
        self.view = WorkspaceView()
        self._broker = HotReloadBroker()
        self._event_mediator = EventMediator()


for name in (
    "_place_widget _bind_event_mediator _bind_external_indicator _bind_error_indicator "
    "find_frame_by_instance_id open_widget open_widget_content _scratch_backing_file "
    "_bind_scratch_backing_file _flush_scratch_backing_files _delete_scratch_backing_file"
).split():
    setattr(_FakeWindow, name, getattr(DeskWindow, name))


def backing(win, iid):
    return win.current_desk.directory / TEMP_UI_DIRNAME / "scratch-text" / f"{iid}.json"


with tempfile.TemporaryDirectory() as tmp:
    directory = Path(tmp)
    win = _FakeWindow(directory)
    check("test desk directory is the tmp dir", win.current_desk.directory == directory)
    content = win.open_widget_content(SCRATCH_WIDGET_ID, pos=(0, 0))
    iid = win.view._frames[0].instance_id
    content.body.setPlainText("hello restart")
    content.set_label("my note")
    win._flush_scratch_backing_files()
    data = json.loads(backing(win, iid).read_text())
    check("flush writes text", data["text"] == "hello restart")
    check("flush writes label", data["label"] == "my note")

    # debounce timer path
    content.body.setPlainText("edited")
    check("edit schedules a save", content._save_timer.isActive())
    content._save_timer.timeout.emit()
    check("timer save writes new text", json.loads(backing(win, iid).read_text())["text"] == "edited")
    check("no .tmp left behind", not list(backing(win, iid).parent.glob("*.tmp")))
    check("file is not mistaken for a tempui file", not is_temp_ui_filename(backing(win, iid).name))

    # restore into a "new session"
    win2 = _FakeWindow(directory)
    restored = win2.open_widget_content(SCRATCH_WIDGET_ID, pos=(0, 0), instance_id=iid)
    check("restored text", restored.body.toPlainText() == "edited")
    check("restored label", restored.label_text == "my note")
    check("restore isn't flagged as unsaved local edits", not restored.has_unsaved_local_edits())

    # tempui-backed scratch: instance id names a .desk_temp file -> no backing file
    temp = directory / TEMP_UI_DIRNAME
    (temp / "abc-uuid").write_text("Scratch lbl\nbody")
    tcontent = win2.open_widget_content(SCRATCH_WIDGET_ID, pos=(0, 0), instance_id="abc-uuid")
    tcontent.body.setPlainText("changed")
    tcontent.flush_pending_save()
    check("tempui-backed Scratch gets no backing file", not backing(win2, "abc-uuid").exists())

    # close deletes
    frame = win2.find_frame_by_instance_id(iid)
    win2._delete_scratch_backing_file(frame)
    check("closing deletes the backing file", not backing(win2, iid).exists())
    restored.body.setPlainText("late")
    restored.flush_pending_save()
    check("late flush doesn't resurrect it", not backing(win2, iid).exists())

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
