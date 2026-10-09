"""TODO c40c5c5: live watcher on desk_hmsvc/ + "new microservice" notification
(see plans/hmsvc-dir-watcher.md)."""
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

import desk.shell.widget_frame  # noqa: E402,F401  (WebEngine must be imported before QApplication exists)
from desk.shell.window import DeskWindow  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk.hmsvc import HmsvcManager  # noqa: E402
from desk.shell.hmsvc_dir_watcher import HmsvcDirWatcher  # noqa: E402

passed = failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


def pump(predicate, timeout=6.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        app.processEvents()
        time.sleep(0.02)
    return predicate()


def settle(seconds=0.8):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def make_service(root, name, description=""):
    d = root / "desk_hmsvc" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "service.py").write_text("app = None\n")
    if description:
        (d / "service.json").write_text('{"description": "%s"}' % description)


# -- manager.refresh() reports names new to this project ----------------------------------
with tempfile.TemporaryDirectory() as t:
    root = Path(t).resolve()
    make_service(root, "a")
    m = HmsvcManager()
    m.set_directory(root)
    check("initial scan finds the service", [s["name"] for s in m.list_services()] == ["a"])
    check("nothing is new right after open", m.refresh() == [])
    make_service(root, "b")
    check("a later-added service is reported new once", m.refresh() == ["b"])
    check("...and not again", m.refresh() == [])
    import shutil
    shutil.rmtree(root / "desk_hmsvc" / "b")
    m.refresh()
    check("a removed service leaves the list", [s["name"] for s in m.list_services()] == ["a"])
    make_service(root, "b")
    check("a removed-then-restored service is not announced again", m.refresh() == [])

# -- watcher: directory exists already ---------------------------------------------------
with tempfile.TemporaryDirectory() as t:
    root = Path(t).resolve()
    make_service(root, "a")
    w = HmsvcDirWatcher()
    hits = []
    w.changed.connect(lambda: hits.append(1))
    w.provision(root)
    settle(0.5)
    base = len(hits)
    make_service(root, "b")
    check("adding a service directory fires changed", pump(lambda: len(hits) > base))
    settle(0.6)
    base = len(hits)
    (root / "desk_hmsvc" / "b" / "service.json").write_text('{"description": "x"}')
    check("editing service.json fires changed", pump(lambda: len(hits) > base))
    settle(0.6)
    base = len(hits)
    (root / "desk_hmsvc" / "b" / "__pycache__").mkdir()
    (root / "desk_hmsvc" / "b" / "__pycache__" / "service.cpython-312.pyc").write_text("x")
    settle(1.0)
    check("__pycache__ churn does not fire changed", len(hits) == base)
    w._stop()

# -- watcher: desk_hmsvc/ doesn't exist yet ----------------------------------------------
with tempfile.TemporaryDirectory() as t:
    root = Path(t).resolve()
    w = HmsvcDirWatcher()
    hits = []
    w.changed.connect(lambda: hits.append(1))
    w.provision(root)
    settle(0.3)
    check("nothing fires while the directory is absent", not hits)
    make_service(root, "late")
    check("creating desk_hmsvc/ later is noticed (poll)", pump(lambda: len(hits) >= 1, timeout=8.0))
    settle(0.5)
    base = len(hits)
    make_service(root, "later")
    check("and then watched live", pump(lambda: len(hits) > base))
    w._stop()


# -- window handlers ---------------------------------------------------------------------
class FakeView:
    def __init__(self):
        self.notes = []
        self._frames = []
        self.fronted = []

    def notify_temp_ui(self, path, text, cb):
        self.notes.append((path, text, cb))

    def bring_to_front(self, frame):
        self.fronted.append(frame)

    def zoom_to_widget(self, frame):
        pass


class FakeWin:
    pass


for name in ("_on_hmsvc_dir_changed", "_notify_new_hmsvc_service", "_reveal_hmsvc_manager"):
    setattr(FakeWin, name, getattr(DeskWindow, name))

with tempfile.TemporaryDirectory() as t:
    root = Path(t).resolve()
    m = HmsvcManager()
    m.set_directory(root)
    win = FakeWin()
    win._hmsvc = m
    win.view = FakeView()
    opened = []
    win.open_widget_content_centered = lambda wid: opened.append(wid)
    make_service(root, "tiles", "Map tiles")
    win._on_hmsvc_dir_changed()
    check("one notification for the new service", len(win.view.notes) == 1)
    path, text, cb = win.view.notes[0]
    check("text names the service and description", text == "New microservice available: tiles — Map tiles")
    check("keyed per service", str(path) == "hmsvc-new:tiles")
    win._on_hmsvc_dir_changed()
    check("no second notification when nothing new", len(win.view.notes) == 1)
    cb()
    check("click places the Microservices widget when none exists", opened == ["hmsvc_manager"])
    frame = SimpleNamespace(content=SimpleNamespace(widget_id="hmsvc_manager"))
    win.view._frames.append(frame)
    cb()
    check("click focuses an existing Microservices widget instead", opened == ["hmsvc_manager"] and win.view.fronted == [frame])
    check("click never starts the service", m.get("tiles")["status"] == "stopped")

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
