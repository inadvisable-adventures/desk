"""TODO 6413e58: docked sidebar -- dock/undock/close/list, persistence, spawn-menu group, MCP tools, docs."""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from PyQt6.QtCore import QObject, QPointF, pyqtSignal  # noqa: E402
from PyQt6.QtWidgets import QApplication, QDockWidget, QMainWindow, QToolButton  # noqa: E402

from desk import temp_ui  # noqa: E402
from desk.desks import Desk, DockedWidgetState, desk_state_dict, load_desk, save_desk  # noqa: E402
from desk.shell import current_context  # noqa: E402
from desk.shell import desk_mcp_server as mcp  # noqa: E402
from desk.shell.widget_spawn_menu import DOCK_ID_PREFIX, WidgetSpawnMenu  # noqa: E402
from desk.shell.window import DeskWindow  # noqa: E402
from desk.widgets import WidgetInfo  # noqa: E402

app = QApplication.instance() or QApplication([])
passed = failed = 0


def check(name, ok):
    global passed, failed
    if ok:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


def raises(fn):
    try:
        fn()
    except ValueError:
        return True
    return False


WIDGET_SRC = '''
from PyQt6.QtWidgets import QLabel


class W(QLabel):
    def __init__(self):
        super().__init__("w")
        self.data = {}
        self.bound = None

    def get_widget_local_storage(self):
        return dict(self.data)

    def set_widget_local_storage(self, data):
        self.data = dict(data)

    def bind_event_mediator(self, instance_id, mediator):
        self.bound = (instance_id, mediator)


def build():
    return W()
'''


class _Broker(QObject):
    widget_changed = pyqtSignal(str)


class _Mediator:
    def __init__(self):
        self.unsubscribed = []

    def unsubscribe_all(self, instance_id):
        self.unsubscribed.append(instance_id)


class _Frame:
    def __init__(self, instance_id):
        self.instance_id = instance_id


class _Win(QMainWindow):
    def __init__(self, widgets):
        super().__init__()
        self._widgets = widgets
        self._broker = _Broker()
        self._event_mediator = _Mediator()
        self._docked = {}
        self.placed = []
        self.bound = []
        self.infos = []
        self.view = type("V", (), {
            "mapToScene": lambda s, p: QPointF(1000.0, 500.0),
            "viewport": lambda s: type("VP", (), {"rect": lambda s: type("R", (), {"center": lambda s: None})()})(),
        })()

    def _place_widget(self, widget_id, info, pos, size, instance_id=None, local_storage_data=None, **k):
        self.placed.append((widget_id, pos, size, instance_id, local_storage_data))
        return _Frame(instance_id)

    def _bind_widget_local_storage(self, frame, data):
        self.bound.append(data)

    def _info(self, title, message):
        self.infos.append((title, message))


for name in ("_docked_title_bar", "dock_widget_by_id", "_remove_dock", "undock_widget", "close_docked_widget",
             "list_docked_widgets", "_capture_docked", "_load_desk_docked", "_clear_docked",
             "_on_widget_dock_requested"):
    setattr(_Win, name, DeskWindow.__dict__[name])

with tempfile.TemporaryDirectory() as d:
    wdir = Path(d) / "dummy"
    wdir.mkdir()
    (wdir / "widget.py").write_text(WIDGET_SRC)
    py = WidgetInfo("dummy", wdir, "python", "Dummy", "widget.py", [], (300, 200))
    html = WidgetInfo("webby", wdir, "html", "Webby", "index.html", [], None)
    win = _Win({"dummy": py, "webby": html})

    iid = win.dock_widget_by_id("dummy", {"k": 1})
    dock = win._docked[iid]
    check("dock returns an instance id and creates a QDockWidget", isinstance(dock, QDockWidget) and iid)
    check("docked in the right area", win.dockWidgetArea(dock).name == "RightDockWidgetArea")
    content = dock.widget().current
    check("state seeds the widget's local storage", content.data == {"k": 1})
    check("event mediator bound with the instance id", content.bound == (iid, win._event_mediator))
    check("custom title bar has a label and two tool buttons",
          dock.titleBarWidget() is not None and len(dock.titleBarWidget().findChildren(QToolButton)) == 2)
    check("listed", win.list_docked_widgets() == [{"instance_id": iid, "widget_id": "dummy", "name": "Dummy"}])

    check("unknown widget raises", raises(lambda: win.dock_widget_by_id("nope")))
    check("html widget refused", raises(lambda: win.dock_widget_by_id("webby")))
    check("non-dict state refused", raises(lambda: win.dock_widget_by_id("dummy", [1])))

    # capture reflects live state
    content.data = {"k": 2}
    cap = win._capture_docked()
    check("capture pulls the widget's current state", len(cap) == 1 and cap[0].state == {"k": 2}
          and cap[0].instance_id == iid and cap[0].widget_id == "dummy")

    # persistence
    desk = Desk(path=Path(d) / "x.desk", docked=cap)
    save_desk(desk)
    back = load_desk(desk.path)
    check("docked round-trips through the .desk file", back.docked == desk.docked)
    old = Path(d) / "old.desk"
    old.write_text(json.dumps({"widgets": []}))
    check("an older .desk loads with nothing docked", load_desk(old).docked == [])
    check("desk_state_dict carries docked", desk_state_dict(desk)["docked"][0]["widget_id"] == "dummy")

    # restore into a fresh window
    win2 = _Win({"dummy": py})
    win2._load_desk_docked(back)
    restored = win2._docked[iid].widget().current
    check("restore re-creates the dock with the same instance id and state", restored.data == {"k": 2})
    ghost = Desk(path=Path(d) / "g.desk", docked=[DockedWidgetState("gone")])
    win2._load_desk_docked(ghost)
    check("a docked widget whose kind is missing is skipped, not fatal", len(win2._docked) == 1)

    # undock
    result = win.undock_widget(iid)
    check("undock returns the same instance id and removes the dock", result == iid and iid not in win._docked)
    placed = win.placed[-1]
    check("undock places a canvas instance with the state and id, centered",
          placed[0] == "dummy" and placed[3] == iid and placed[4] == {"k": 2} and placed[1] == (850.0, 400.0))
    check("undock re-binds the local storage", win.bound[-1] == {"k": 2})
    check("undock unsubscribes the old mediator binding", iid in win._event_mediator.unsubscribed)
    check("undock of an unknown id raises", raises(lambda: win.undock_widget("nope")))

    # close + clear
    a = win.dock_widget_by_id("dummy")
    b = win.dock_widget_by_id("dummy")
    check("close removes just that one", win.close_docked_widget(a) is True and list(win._docked) == [b])
    check("close of unknown is False", win.close_docked_widget("nope") is False)
    win._clear_docked()
    check("clear removes every dock", win._docked == {})

    win._on_widget_dock_requested("webby")
    check("a refused dock from the menu is reported, not raised", len(win.infos) == 1)

    # ---- MCP tools ----
    names = {"desk_dock_widget", "desk_undock_widget", "desk_list_docked_widgets"}
    check("three docking tools registered", names <= {t.name for t in mcp._TOOLS})
    current_context.set_gui_thread_caller(lambda fn: fn())
    current_context.set_main_window(win)

    def call(tool, args):
        res = asyncio.run(tool.handler(args))
        return res, res["content"][0]["text"]

    res, iid2 = call(mcp._dock_widget, {"widget_id": "dummy", "state": {"z": 1}})
    check("dock tool returns the instance id", not res.get("is_error") and iid2 in win._docked)
    res, text = call(mcp._list_docked_widgets, {})
    check("list tool returns JSON", json.loads(text)[0]["instance_id"] == iid2)
    res, text = call(mcp._dock_widget, {"widget_id": "webby"})
    check("dock tool reports a refusal as an error", res["is_error"] is True)
    res, text = call(mcp._dock_widget, {"widget_id": " "})
    check("dock tool rejects an empty id", res["is_error"] is True)
    res, text = call(mcp._undock_widget, {"instance_id": iid2})
    check("undock tool returns the id", text == iid2 and iid2 not in win._docked)
    res, text = call(mcp._undock_widget, {"instance_id": "nope"})
    check("undock tool reports unknown id as error", res["is_error"] is True)
    current_context.set_main_window(None)

# ---- spawn menu group ----
cat = {
    "a": WidgetInfo("a", Path("."), "python", "Alpha", "w.py", [], None),
    "b": WidgetInfo("b", Path("."), "html", "Beta", "i.html", [], None),
}
menu = WidgetSpawnMenu(cat, None, frozenset({"a"}))
grp = menu._group_items["Dock in sidebar"]
check("dock group lists only the dockable widgets", grp.childCount() == 1 and grp.child(0).text(0) == "Alpha")
check("dock group is collapsed by default", grp.isExpanded() is False)
check("dock entries carry the dock: prefix", grp.child(0).data(0, 0x100) == DOCK_ID_PREFIX + "a")
chosen = []
menu.widget_chosen.connect(chosen.append)
menu._activate_item(grp.child(0))
check("activating a dock entry emits the prefixed id", chosen == ["dock:a"])
plain = WidgetSpawnMenu(cat)
check("with nothing dockable the group is hidden", plain._group_items["Dock in sidebar"].isHidden() is True)
plain.close()

# ---- docs ----
tag = "docked sidebar widgets + MCP tools #797468"
check("changelog tag current, with an entry", tag in temp_ui.CURRENT_TAGS and tag in temp_ui._NEW_FEATURES)
check("dedicated doc names every tool", all(t in temp_ui.SPLIT_DOC_CONTENT["tempui-docked-widgets.md"] for t in
      ("desk_dock_widget", "desk_undock_widget", "desk_list_docked_widgets")))

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
