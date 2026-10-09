"""TODO 8925b2e: each hmsvc service's {status, url} is mirrored to desk.state key
desk.hmsvc.<name> (see plans/hmsvc-url-in-desk-state.md)."""
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

import desk.shell.widget_frame  # noqa: E402,F401
from desk.desks import Desk, save_desk, load_desk, StateEntry  # noqa: E402
from desk.event_mediator import EventMediator  # noqa: E402
from desk.schema_registry import SchemaRegistry  # noqa: E402
from desk.shell.window import DeskWindow  # noqa: E402
from desk.temp_ui import CURRENT_TAGS, SPLIT_DOC_CONTENT, _NEW_FEATURES  # noqa: E402
from PyQt6.QtCore import QObject, pyqtSignal  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)
passed = failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


class FakeHmsvc:
    def __init__(self):
        self.services = []

    def list_services(self):
        return list(self.services)


def svc(name, status="stopped", url=None):
    return {"name": name, "status": status, "url": url}


class Win(QObject):
    dirty = pyqtSignal()
    _sync_hmsvc_state = DeskWindow._sync_hmsvc_state
    set_state = DeskWindow.set_state

    def __init__(self, path):
        super().__init__()
        self.current_desk = Desk(path=path)
        self._hmsvc = FakeHmsvc()
        self._schema_registry = SchemaRegistry()
        self._event_mediator = EventMediator()
        self.main_thread = threading.get_ident()
        self.sync_threads = []


with tempfile.TemporaryDirectory() as t:
    win = Win(Path(t) / "p.desk")
    events = []
    orig_publish = win._event_mediator.publish
    win._event_mediator.publish = lambda name, payload, sender_instance_id=None: events.append((name, payload))

    win._hmsvc.services = [svc("tiles"), svc("api", "running", "http://127.0.0.1:5001/")]
    win._sync_hmsvc_state()
    st = win.current_desk.state
    check("a key per service", set(st) == {"desk.hmsvc.tiles", "desk.hmsvc.api"})
    check("value is {status, url}", st["desk.hmsvc.api"].value == {"status": "running", "url": "http://127.0.0.1:5001/"})
    check("stopped service has null url", st["desk.hmsvc.tiles"].value == {"status": "stopped", "url": None})
    check("one change event per key", [e[0] for e in events] == ["desk.state.changed"] * 2)

    events.clear()
    win._sync_hmsvc_state()
    check("no rewrite when nothing changed", events == [])

    win._hmsvc.services[1] = svc("api", "crashed", None)
    win._sync_hmsvc_state()
    check("crash keeps the key, status updated, url null", st["desk.hmsvc.api"].value == {"status": "crashed", "url": None})
    check("exactly one change event for it", len(events) == 1 and events[0][1]["key"] == "desk.hmsvc.api")

    win._hmsvc.services[1] = svc("api", "running", "http://127.0.0.1:6002/")
    events.clear()
    win._sync_hmsvc_state()
    check("a restart's new port is a normal change", st["desk.hmsvc.api"].value["url"] == "http://127.0.0.1:6002/" and len(events) == 1)

    win._hmsvc.services = [svc("api", "running", "http://127.0.0.1:6002/")]
    win._sync_hmsvc_state()
    check("a service gone from disk is marked removed", st["desk.hmsvc.tiles"].value == {"status": "removed", "url": None})

    win.current_desk.state["other"] = StateEntry(value=1, edit=None)
    win._sync_hmsvc_state()
    check("unrelated keys untouched", st["other"].value == 1)

    # runtime-only: never persisted
    save_desk(win.current_desk)
    on_disk = json.loads(win.current_desk.path.read_text())["state"]
    check("desk.hmsvc.* keys are not written to the .desk file", set(on_disk) == {"other"})
    check("other keys still persist", "other" in load_desk(win.current_desk.path).state)

# a change signalled from a non-GUI thread runs the sync on the GUI thread
with tempfile.TemporaryDirectory() as t:
    win = Win(Path(t) / "p.desk")
    win._hmsvc.services = [svc("a", "running", "http://127.0.0.1:1/")]
    ran = []

    def slot():
        ran.append(threading.get_ident())
        win._sync_hmsvc_state()

    win.dirty.connect(slot)
    th = threading.Thread(target=win.dirty.emit)
    th.start()
    th.join()
    deadline = time.time() + 3
    while not ran and time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)
    check("slot ran, on the GUI thread", ran == [threading.get_ident()])
    check("state written", "desk.hmsvc.a" in win.current_desk.state)

check("DeskWindow declares the signal", hasattr(DeskWindow, "hmsvc_state_dirty"))
tag = next(t for t in CURRENT_TAGS if "service url published" in t)
check("changelog entry", tag in _NEW_FEATURES)
check("doc mentions the state keys", "desk.hmsvc.<name>" in SPLIT_DOC_CONTENT["tempui-hmsvc.md"])

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
