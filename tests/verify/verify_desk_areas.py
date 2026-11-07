"""TODO 0460b4c: desk areas -- scene item, canvas wiring, persistence, DeskWindow API, MCP tools."""
import asyncio
import json
import os
import sys
import tempfile
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from PyQt6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel  # noqa: E402

from desk.desks import AREAS_CHANGED_EVENT, AreaState, Desk, load_desk, save_desk  # noqa: E402
from desk.shell import current_context  # noqa: E402
from desk.shell.area_item import AREA_Z, AreaItem  # noqa: E402
from desk.shell.canvas import WorkspaceView  # noqa: E402
from desk.shell import desk_mcp_server as mcp  # noqa: E402
from desk.shell.window import DeskWindow  # noqa: E402

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


def click(view, scene_x, scene_y, **kw):
    p = view.mapFromScene(QPointF(scene_x, scene_y))
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=p, **kw)


# ---- canvas + item ----
view = WorkspaceView()
view.resize(1000, 800)
view.show()
view.centerOn(QPointF(500, 400))
item = view.add_area("a1", "Alpha", 100, 100, 600, 400)
check("area registered on the view", view.area_item("a1") is item)
check("area sits far behind every frame", item.zValue() == AREA_Z)

frame_proxy = view.add_widget(QLabel("hello"), "w", pos=(200, 200), size=(200, 150))
view.send_to_back(frame_proxy.widget())
check("even a sent-to-back frame stays above the area", frame_proxy.zValue() > item.zValue())

interior = view.mapFromScene(QPointF(650, 450))
check("interior is not hit-testable (itemAt finds no area)", not isinstance(view.itemAt(interior), AreaItem))
title_pt = view.mapFromScene(QPointF(300, 105))
check("title strip is hit-testable", isinstance(view.itemAt(title_pt), AreaItem))
border_pt = view.mapFromScene(QPointF(101, 300))
check("border band is hit-testable", isinstance(view.itemAt(border_pt), AreaItem))
widget_pt = view.mapFromScene(QPointF(300, 300))
check("a widget inside the area still wins the hit test", view.itemAt(widget_pt) is frame_proxy)

views = []
item.view_requested.connect(views.append)
geom = []
item.geometry_changed.connect(lambda *a: geom.append(a))

# title drag moves the area
start = view.mapFromScene(QPointF(300, 115))
end = view.mapFromScene(QPointF(340, 145))
QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
QTest.mouseMove(view.viewport(), end)
QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=end)
r = item.scene_rect()
check("dragging the title moves the area by the drag delta", abs(r.x() - 140) < 2 and abs(r.y() - 130) < 2 and r.width() == 600)
check("a finished drag reports geometry once", len(geom) == 1 and geom[0][0] == "a1")

# resize from right border
item.set_geometry(100, 100, 600, 400)
geom.clear()
rs = view.mapFromScene(QPointF(699, 300))
re = view.mapFromScene(QPointF(799, 300))
QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=rs)
QTest.mouseMove(view.viewport(), re)
QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=re)
r = item.scene_rect()
check("dragging the right border resizes only width", abs(r.width() - 700) < 2 and abs(r.x() - 100) < 1 and r.height() == 400)

# eye click
item.set_geometry(100, 100, 600, 400)
eye = item._eye_rect()
click(view, 100 + eye.center().x() * 1.0, 100 + eye.center().y())
check("clicking the eye requests a view of the area", views == ["a1"])

# interior click does not start an area interaction
geom.clear()
before = item.scene_rect()
QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=view.mapFromScene(QPointF(650, 460)))
check("clicking the interior leaves the area alone", item.scene_rect() == before and geom == [])

# zoom_to_area
view.reset_zoom()
view.zoom_to_area("a1")
check("zoom_to_area fits the area", view._scale > 1.0)
center = view.mapToScene(view.viewport().rect().center())
check("view centered on the area", abs(center.x() - 400) < 5 and abs(center.y() - 300) < 5)
check("zoom_to_area on unknown id is False", view.zoom_to_area("nope") is False)

# chrome counter-scales
big = item._strip_height()
view._rescale(0.25)
check("title strip grows in scene units when zoomed out", item._strip_height() > big * 3)

# right-click menu: the "Desk Area" pseudo entry requests an area at the click
from PyQt6.QtGui import QContextMenuEvent  # noqa: E402
from desk.shell.widget_spawn_menu import WidgetSpawnMenu  # noqa: E402

requested = []
view.area_add_requested.connect(requested.append)
click_pos = view.mapFromScene(QPointF(900, 700))
view.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Reason.Mouse, click_pos, view.viewport().mapToGlobal(click_pos)))
menus = view.findChildren(WidgetSpawnMenu)
check("right-click on empty canvas opens the spawn menu", len(menus) == 1)
names = {menus[0]._catalog[k].name for k in menus[0]._catalog} if menus else set()
check("spawn menu offers 'Desk Area'", "Desk Area" in names)
menus[0].widget_chosen.emit("desk.area")
app.processEvents()
QTest.qWait(50)
check("choosing it requests an area at the click's scene position",
      len(requested) == 1 and abs(requested[0].x() - 900) < 2 and abs(requested[0].y() - 700) < 2)
menus[0].close()

# right-click on area chrome does not open the spawn menu (it has its own)
view.findChildren(WidgetSpawnMenu)

view.clear_widgets()
check("clear_widgets also clears areas", view.area_item("a1") is None)

# ---- persistence ----
with tempfile.TemporaryDirectory() as d:
    desk = Desk(path=Path(d) / "x.desk", areas=[AreaState("q1", "Q", 1.0, 2.0, 30.0, 40.0)])
    save_desk(desk)
    back = load_desk(desk.path)
    check("areas round-trip through the .desk file", back.areas == desk.areas)
    old = Path(d) / "old.desk"
    old.write_text(json.dumps({"widgets": []}))
    check("a .desk saved before areas loads with none", load_desk(old).areas == [])

# ---- DeskWindow API (real methods on a stand-in) ----
published = []


class _Mediator:
    def publish(self, name, payload, sender):
        published.append((name, payload, sender))


class _View:
    def __init__(self):
        self.items = {}
        self.viewed = []

    def visible_scene_rect(self):
        from PyQt6.QtCore import QRectF
        return QRectF(0, 0, 1000, 800)

    def add_area(self, area_id, title, x, y, w, h):
        self.items[area_id] = (title, x, y, w, h)

    def remove_area(self, area_id):
        return self.items.pop(area_id, None) is not None

    def zoom_to_area(self, area_id):
        self.viewed.append(area_id)
        return area_id in self.items


class _Win:
    pass


win = _Win()
win.current_desk = Desk(path=Path("/tmp/none.desk"))
win.view = _View()
win._event_mediator = _Mediator()
win._prompt_fn = lambda *a: (lambda: "Renamed")
for name in ("_area_dict", "_find_area", "_publish_areas_changed", "list_areas", "create_area", "update_area",
             "delete_area", "view_area", "_on_area_add_requested", "_on_area_geometry_changed",
             "_on_area_rename_requested", "_on_area_delete_requested", "_load_desk_areas"):
    setattr(_Win, name, getattr(DeskWindow, name))

a = win.create_area()
check("default geometry is the middle 70% of the visible rect", (a["x"], a["y"], a["width"], a["height"]) == (150.0, 120.0, 700.0, 560.0))
check("default title is numbered", a["title"] == "Area 1")
check("create publishes the change event",
      published[-1][0] == AREAS_CHANGED_EVENT == "desk.areas.changed" and published[-1][2] == "desk"
      and published[-1][1]["areas"][0]["area_id"] == a["area_id"])
b = win.create_area("Beta", 10, 20, 300, 200)
check("explicit geometry honored", (b["title"], b["x"], b["y"], b["width"], b["height"]) == ("Beta", 10.0, 20.0, 300.0, 200.0))
check("list returns both in creation order", [x["title"] for x in win.list_areas()] == ["Area 1", "Beta"])

def raises(fn):
    try:
        fn()
    except ValueError:
        return True
    return False

check("x without y raises", raises(lambda: win.create_area("t", 1, None)))
check("non-positive size raises", raises(lambda: win.create_area("t", 1, 2, 0, 5)))
u = win.update_area(b["area_id"], title="Gamma", width=500)
check("update changes only the given fields", (u["title"], u["x"], u["width"], u["height"]) == ("Gamma", 10.0, 500.0, 200.0))
check("update pushes to the scene item", win.view.items[b["area_id"]] == ("Gamma", 10.0, 20.0, 500.0, 200.0))
check("update of unknown area raises", raises(lambda: win.update_area("nope", title="x")))
win._on_area_geometry_changed(b["area_id"], 1.0, 2.0, 3.0, 4.0)
check("a user drag writes geometry back to the model", win.list_areas()[1]["x"] == 1.0 and win.list_areas()[1]["height"] == 4.0)
win._on_area_rename_requested(b["area_id"])
check("rename request prompts and applies the title", win.list_areas()[1]["title"] == "Renamed")
check("view_area delegates to the canvas", win.view_area(a["area_id"]) is True and win.view_area("nope") is False)
check("delete removes it from model and canvas", win.delete_area(a["area_id"]) is True and a["area_id"] not in win.view.items
      and len(win.list_areas()) == 1)
check("delete of unknown area is False", win.delete_area("nope") is False)
win.view.items.clear()
win._load_desk_areas(win.current_desk)
check("_load_desk_areas rebuilds scene items from the model", len(win.view.items) == 1)

# ---- agent docs ----
from desk import temp_ui  # noqa: E402

tag = "desk areas: background regions + MCP tools #377360"
check("changelog tag current, with an entry", tag in temp_ui.CURRENT_TAGS and tag in temp_ui._NEW_FEATURES)
check("dedicated areas doc registered and names every tool",
      all(t in temp_ui.SPLIT_DOC_CONTENT["tempui-areas.md"] for t in
          ("desk_list_areas", "desk_create_area", "desk_update_area", "desk_delete_area", "desk_view_area", "desk.areas.changed")))
check("overview doc links the areas doc", "tempui-areas.md" in temp_ui.DOC_TEMPLATE)

# ---- MCP tools ----
names = {"desk_list_areas", "desk_create_area", "desk_update_area", "desk_delete_area", "desk_view_area"}
check("all five area tools registered", names <= {t.name for t in mcp._TOOLS})
current_context.set_gui_thread_caller(lambda fn: fn())
current_context.set_main_window(win)


def call(tool, args):
    res = asyncio.run(tool.handler(args))
    return res, res["content"][0]["text"]


res, text = call(mcp._create_area, {"title": "MCP", "x": 0, "y": 0, "width": 100, "height": 100})
created = json.loads(text)
check("create tool returns the area JSON", not res.get("is_error") and created["title"] == "MCP")
res, text = call(mcp._list_areas, {})
check("list tool returns JSON list", any(x["area_id"] == created["area_id"] for x in json.loads(text)))
res, text = call(mcp._update_area, {"area_id": created["area_id"], "title": "MCP2"})
check("update tool renames", json.loads(text)["title"] == "MCP2")
res, text = call(mcp._update_area, {"area_id": "nope"})
check("update tool reports unknown area as error", res["is_error"] is True)
res, text = call(mcp._view_area, {"area_id": created["area_id"]})
check("view tool returns True for a real area", text == "True")
res, text = call(mcp._delete_area, {"area_id": created["area_id"]})
check("delete tool returns True then False", text == "True" and call(mcp._delete_area, {"area_id": created["area_id"]})[1] == "False")
current_context.set_main_window(None)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
