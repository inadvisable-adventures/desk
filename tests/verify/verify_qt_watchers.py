import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from PyQt6.QtCore import QCoreApplication, QTimer

from desk.file_watch import SingleFileWatcher
from desk.widgets import WidgetWatcher
from desk.hotreload import HotReloadBroker
from desk.shell.temp_ui_manager import TempUiManager
from desk_services.file_watcher import get_service

app = QCoreApplication(sys.argv)


def pump(seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)


def test_single_file_watcher():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        f = d / "file.txt"
        f.write_text("v1")

        w = SingleFileWatcher()
        events = []
        w.changed.connect(lambda: events.append(1))
        w.watch(f)

        # idempotent re-watch of same path
        w.watch(f)

        f.write_text("v2")
        pump(1.0)
        assert events, "SingleFileWatcher should fire on external change"

        events.clear()
        w.record_own_write("v3")
        f.write_text("v3")
        pump(0.8)
        assert not events, f"record_own_write should suppress matching echo, got {events}"

        events.clear()
        f.write_text("v4")
        pump(1.0)
        assert events, "after v3, a real subsequent external change (v4) should still fire"

        w.stop()
        events.clear()
        f.write_text("v5")
        pump(0.8)
        assert not events, "no events after stop()"
        print("test_single_file_watcher: PASS")


def test_widget_watcher():
    with tempfile.TemporaryDirectory() as d:
        widgets_dir = Path(d)
        wid_dir = widgets_dir / "mywidget"
        wid_dir.mkdir()
        (wid_dir / "widget.py").write_text("def build():\n    pass\n")

        broker = HotReloadBroker()
        changed = []
        broker.widget_changed.connect(lambda wid: changed.append(wid))

        watcher = WidgetWatcher(widgets_dir, broker)
        watcher.start()

        (wid_dir / "widget.py").write_text("def build():\n    return None\n")
        pump(1.0)
        assert changed == ["mywidget"], f"expected hot-reload for mywidget, got {changed}"

        watcher.stop()
        changed.clear()
        (wid_dir / "widget.py").write_text("def build():\n    return 1\n")
        pump(0.8)
        assert not changed, "no reload events after stop()"
        print("test_widget_watcher: PASS")


def test_temp_ui_manager():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        mgr = TempUiManager()
        added = []
        edited = []
        mgr.file_added.connect(lambda p: added.append(p))
        mgr.file_edited.connect(lambda p: edited.append(p))

        temp_dir = mgr.provision(directory, lambda: True, lambda: True)
        assert temp_dir is not None

        import uuid

        fname = str(uuid.uuid4())
        target = temp_dir / fname
        target.write_text("hello")
        pump(1.0)
        assert added and added[0].name == fname, f"expected file_added for new uuid file, got {added}"

        edited.clear()
        target.write_text("hello edited")
        pump(1.0)
        assert edited and edited[0].name == fname, f"expected file_edited for modified uuid file, got {edited}"

        # self-write suppression
        added.clear()
        edited.clear()
        mgr.record_own_write(target, "self-write")
        target.write_text("self-write")
        pump(0.8)
        assert not edited and not added, f"record_own_write should suppress echo, got added={added} edited={edited}"

        mgr.stop()
        print("test_temp_ui_manager: PASS")


test_single_file_watcher()
test_widget_watcher()
test_temp_ui_manager()
get_service().stop()
print("ALL PASS")
