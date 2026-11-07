"""TODO 6413e58 + 4ff712c: docked sidebar -- dock/undock/close/list, persistence, spawn-menu group, MCP tools, docs;
left side, collapsed-by-default tab, drag-and-drop docking with a drop indicator."""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from PyQt6.QtCore import QEvent, QObject, QPoint, QPointF, Qt, pyqtSignal  # noqa: E402
from PyQt6.QtGui import QMouseEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication, QDockWidget, QLineEdit, QMainWindow, QToolButton, QWidget  # noqa: E402

from desk import temp_ui  # noqa: E402
from desk.desks import Desk, DockedWidgetState, desk_state_dict, load_desk, save_desk  # noqa: E402
from desk.shell import current_context  # noqa: E402
from desk.shell import desk_mcp_server as mcp  # noqa: E402
from desk.shell.canvas import WorkspaceView  # noqa: E402
from desk.shell.python_widget import PythonWidgetHost  # noqa: E402
from desk.shell.sidebar import DockDropIndicator, SidebarTab  # noqa: E402
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


class _View(QWidget):
    def __init__(self):
        super().__init__()
        self.removed = []

    def mapToScene(self, p):
        return QPointF(1000.0, 500.0)

    def viewport(self):
        return type("VP", (), {"rect": lambda s: type("R", (), {"center": lambda s: None})()})()

    def remove_widget(self, frame):
        self.removed.append(frame)


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
        self.saves = 0
        self.frames = {}
        self.view = _View()
        self.setCentralWidget(self.view)
        self._sidebar_expanded = False
        self._sidebar_tab = SidebarTab(self)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, self._sidebar_tab)
        self._sidebar_tab.button.clicked.connect(lambda: self.set_sidebar_expanded(not self._sidebar_expanded))
        self._dock_drop_indicator = DockDropIndicator(self)
        self._update_sidebar_tab()

    def save_current_desk(self):
        self.saves += 1

    def find_frame_by_instance_id(self, instance_id):
        return self.frames.get(instance_id)

    def _place_widget(self, widget_id, info, pos, size, instance_id=None, local_storage_data=None, **k):
        self.placed.append((widget_id, pos, size, instance_id, local_storage_data))
        return _Frame(instance_id)

    def _bind_widget_local_storage(self, frame, data):
        self.bound.append(data)

    def _info(self, title, message):
        self.infos.append((title, message))


for name in ("_docked_title_bar", "dock_widget_by_id", "_remove_dock", "undock_widget", "close_docked_widget",
             "list_docked_widgets", "_capture_docked", "_load_desk_docked", "_clear_docked",
             "_on_widget_dock_requested", "set_sidebar_expanded", "_update_sidebar_tab", "sidebar_drop_zone",
             "_on_frame_drag_moved", "_on_frame_drag_ended", "dock_placed_widget", "_get_widget_local_storage"):
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
    check("docked in the LEFT area", win.dockWidgetArea(dock).name == "LeftDockWidgetArea")
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

    # ---- TODO 4ff712c: collapsible left sidebar, drop zone, drag-and-drop docking ----
    from PyQt6.QtTest import QTest  # noqa: E402

    w3 = _Win({"dummy": py, "webby": html})
    check("the sidebar tab sits in the left toolbar area",
          isinstance(w3._sidebar_tab, SidebarTab) and w3.toolBarArea(w3._sidebar_tab) == Qt.ToolBarArea.LeftToolBarArea)
    check("collapsed by default, with the expand arrow", w3._sidebar_expanded is False and w3._sidebar_tab.button.text() == "▸")
    w3._load_desk_docked(Desk(path=Path(d) / "r.desk", docked=[DockedWidgetState("dummy", "r1")]))
    check("restoring a saved Desk leaves the sidebar collapsed", w3._docked["r1"].isHidden() and not w3._sidebar_expanded)
    new_id = w3.dock_widget_by_id("dummy")
    check("docking on purpose expands the sidebar and shows every dock",
          w3._sidebar_expanded and not w3._docked[new_id].isHidden() and not w3._docked["r1"].isHidden()
          and w3._sidebar_tab.button.text() == "◂")
    w3._sidebar_tab.button.click()
    check("the tab collapses it again: all docks hidden, arrow flips, count in the tooltip",
          not w3._sidebar_expanded and all(dk.isHidden() for dk in w3._docked.values())
          and w3._sidebar_tab.button.text() == "▸" and "(2 widgets)" in w3._sidebar_tab.button.toolTip())
    w3._load_desk_docked(Desk(path=Path(d) / "r2.desk", docked=[DockedWidgetState("dummy", "r2")]))
    check("a restore while collapsed stays hidden; its count is updated", w3._docked["r2"].isHidden()
          and "(3 widgets)" in w3._sidebar_tab.button.toolTip())
    w3._sidebar_tab.button.click()
    check("the tab expands it", w3._sidebar_expanded and not w3._docked["r2"].isHidden())
    w3._sidebar_tab.button.click()
    w3.resize(900, 600)
    w3.show()
    QTest.qWait(30)

    zone = w3.sidebar_drop_zone()
    tab_global = w3._sidebar_tab.mapToGlobal(QPoint(w3._sidebar_tab.width() // 2, 100))
    canvas_mid = w3.view.mapToGlobal(QPoint(w3.view.width() // 2, w3.view.height() // 2))
    check("collapsed drop zone covers the tab plus a margin of canvas, not the canvas middle",
          zone.contains(tab_global) and not zone.contains(canvas_mid) and zone.width() >= w3._sidebar_tab.width() + 40)
    check("drop zone spans the canvas height", zone.top() == w3.view.mapToGlobal(QPoint(0, 0)).y() and zone.height() == w3.view.height())

    inside, outside = QPointF(tab_global), QPointF(canvas_mid)
    pf = type("PF", (), {"instance_id": "x"})()
    w3._on_frame_drag_moved(pf, inside)
    ind = w3._dock_drop_indicator
    check("the indicator shows over the zone while the cursor is in it",
          not ind.isHidden() and ind.geometry().size() == zone.size()
          and w3.mapToGlobal(ind.geometry().topLeft()) == zone.topLeft())
    w3._on_frame_drag_moved(pf, outside)
    check("the indicator hides when the cursor leaves the zone", ind.isHidden())

    w3.set_sidebar_expanded(True)
    QTest.qWait(30)
    zone2 = w3.sidebar_drop_zone()
    dock_right = max(dk.mapToGlobal(QPoint(dk.width(), 0)).x() for dk in w3._docked.values())
    check("expanded drop zone extends across the open docks", zone2.right() + 1 >= dock_right and zone2.width() > zone.width())
    w3.set_sidebar_expanded(False)

    # dock_placed_widget: a move that keeps id + state, no tombstone
    class _PFrame:
        def __init__(self, instance_id, content):
            self.instance_id, self.content = instance_id, content

    host = PythonWidgetHost("dummy", wdir, "widget.py", w3._broker)
    host.current.data = {"q": 9}
    w3.frames["pf1"] = _PFrame("pf1", host)
    got = w3.dock_placed_widget("pf1")
    check("dock_placed_widget keeps the instance id and state, removes the frame, saves, and reveals",
          got == "pf1" and w3._docked["pf1"].widget().current.data == {"q": 9} and w3.view.removed == [w3.frames["pf1"]]
          and "pf1" in w3._event_mediator.unsubscribed and w3.saves == 1 and w3._sidebar_expanded)
    check("dock_placed_widget of an unknown id raises", raises(lambda: w3.dock_placed_widget("nope")))
    w3.frames["le"] = _PFrame("le", QLineEdit())
    check("dock_placed_widget refuses non-python content", raises(lambda: w3.dock_placed_widget("le")))
    check("a refused move leaves the frame in place", w3.view.removed == [w3.frames["pf1"]])

    # drop handling: only a release inside the zone docks (deferred one tick)
    w3.set_sidebar_expanded(False)
    QTest.qWait(30)
    zone3 = w3.sidebar_drop_zone()
    host2 = PythonWidgetHost("dummy", wdir, "widget.py", w3._broker)
    w3.frames["pf2"] = _PFrame("pf2", host2)
    w3._on_frame_drag_moved(w3.frames["pf2"], QPointF(zone3.center()))
    w3._on_frame_drag_ended(w3.frames["pf2"], QPointF(canvas_mid))
    QTest.qWait(30)
    check("a release outside the zone hides the indicator and docks nothing", ind.isHidden() and "pf2" not in w3._docked)
    w3._on_frame_drag_ended(w3.frames["pf2"], QPointF(zone3.center()))
    check("the dock is deferred past the release handler", "pf2" not in w3._docked)
    QTest.qWait(30)
    check("a release inside the zone docks the widget", "pf2" in w3._docked and ind.isHidden())
    w3.close()

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

# ---- TODO 4ff712c: WorkspaceView drag signals (real view, real titlebar press/move/release) ----
class _PyContent(QLineEdit):
    widget_id = "dummy"


class _HtmlContent(QLineEdit):
    widget_id = "webby"


def _mouse(kind, pos, gpos, buttons=Qt.MouseButton.LeftButton):
    return QMouseEvent(kind, pos, gpos, Qt.MouseButton.LeftButton, buttons, Qt.KeyboardModifier.NoModifier)


def _screen_pos(view, frame, widget):
    proxy = frame.graphicsProxyWidget()
    local = widget.mapTo(frame, widget.rect().center())
    return QPointF(view.mapFromScene(proxy.mapToScene(QPointF(local))))


def drag(content_cls, locked=False, via="titlebar"):
    view = WorkspaceView()
    view.set_widget_catalog({
        "dummy": WidgetInfo("dummy", Path("."), "python", "D", "w.py", [], None),
        "webby": WidgetInfo("webby", Path("."), "html", "W", "i.html", [], None),
    })
    view.show()
    frame = view.add_widget(content_cls(), title="T").widget()
    frame.set_locked(locked)
    QApplication.processEvents()
    moved, ended = [], []
    view.frame_drag_moved.connect(lambda f, p: moved.append((f, p)))
    view.frame_drag_ended.connect(lambda f, p: ended.append((f, p)))
    start = _screen_pos(view, frame, frame._titlebar if via == "titlebar" else frame._right_handle)
    view.mousePressEvent(_mouse(QEvent.Type.MouseButtonPress, start, QPointF(500, 500)))
    view.mouseMoveEvent(_mouse(QEvent.Type.MouseMove, QPointF(-200, start.y()), QPointF(12, 34)))
    view.mouseReleaseEvent(_mouse(QEvent.Type.MouseButtonRelease, QPointF(-200, start.y()), QPointF(12, 34), Qt.MouseButton.NoButton))
    return frame, moved, ended


frame, moved, ended = drag(_PyContent)
check("a python titlebar drag outside the viewport reports the global cursor position",
      len(moved) == 1 and moved[0][0] is frame and moved[0][1] == QPointF(12, 34))
check("its release reports an end", len(ended) == 1 and ended[0][1] == QPointF(12, 34))
_, moved, ended = drag(_HtmlContent)
check("an html widget's drag never reports", moved == [] and ended == [])
_, moved, ended = drag(_PyContent, locked=True)
check("a locked widget's titlebar does not report", moved == [] and ended == [])
_, moved, ended = drag(_PyContent, via="resize")
check("a resize-handle drag does not report", moved == [] and ended == [])

import inspect  # noqa: E402

_init_src = inspect.getsource(DeskWindow.__init__)
check("DeskWindow wires the tab toggle and the two drag signals (a real one is not constructed here)",
      "self._sidebar_tab.button.clicked.connect(lambda: self.set_sidebar_expanded(not self._sidebar_expanded))" in _init_src
      and "self.view.frame_drag_moved.connect(self._on_frame_drag_moved)" in _init_src
      and "self.view.frame_drag_ended.connect(self._on_frame_drag_ended)" in _init_src
      and "LeftToolBarArea" in _init_src)

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
new_tag = "sidebar: left, collapsible, drag-and-drop dock #046076"
check("left/collapsible/dnd changelog tag current, with an entry", new_tag in temp_ui.CURRENT_TAGS and new_tag in temp_ui._NEW_FEATURES)
check("doc describes the left side, default-collapsed and dragging",
      all(t in temp_ui.SPLIT_DOC_CONTENT["tempui-docked-widgets.md"] for t in ("left edge", "collapsed by", "drag a")))
tag = "docked sidebar widgets + MCP tools #797468"
check("changelog tag current, with an entry", tag in temp_ui.CURRENT_TAGS and tag in temp_ui._NEW_FEATURES)
check("dedicated doc names every tool", all(t in temp_ui.SPLIT_DOC_CONTENT["tempui-docked-widgets.md"] for t in
      ("desk_dock_widget", "desk_undock_widget", "desk_list_docked_widgets")))

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
