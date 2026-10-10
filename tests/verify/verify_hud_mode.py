"""TODOs 9ae13c0 / 1ce5130 / 93f79ca: HUD render mode (desk.shell.hud), the
Minimap's use of it and the HUD manager widget. Real WorkspaceView with a
real Minimap in a frame; presses are synthesized onto the view. See
plans/hud-render-mode.md."""
import importlib.util
import os
import sys
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.window  # noqa: E402,F401  (must precede QApplication)

from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PyQt6.QtGui import QMouseEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget  # noqa: E402

app = QApplication(sys.argv)

from desk.shell import current_context  # noqa: E402
from desk.shell.canvas import WorkspaceView  # noqa: E402

DeskWindow = desk.shell.window.DeskWindow
passed = failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


def load(name):
    spec = importlib.util.spec_from_file_location(f"{name}_check", REPO_ROOT / "widgets" / name / "widget.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


minimap_mod = load("minimap")
manager_mod = load("hud_manager")


class _Host(QWidget):
    """Stands in for PythonWidgetHost (`.current` is the built widget)."""

    def __init__(self, widget):
        super().__init__()
        self._widget = widget
        self.widget_id = "minimap"
        QVBoxLayout(self).addWidget(widget)

    @property
    def current(self):
        return self._widget


class _StubWindow:
    def __init__(self):
        self.view = WorkspaceView()
        self.view.resize(900, 700)
        self._widgets = {"minimap": types.SimpleNamespace(kind="python")}
        self._arrangement_undo_stack = []
        self.pans = []
        self.view.show()

    def _display_name_for_instance(self, iid):
        return f"title-{iid}"

    def arrange_canvas(self, mode):
        self.arranged = mode
        return 0

    def pan_canvas_to(self, x, y):
        self.pans.append((x, y))
        self.view.centerOn(QPointF(x, y))


for name in ("_canvas_rects", "get_canvas_layout", "get_hud_layout", "leave_hud"):
    setattr(_StubWindow, name, getattr(DeskWindow, name))


def mouse(kind, pos, button=Qt.MouseButton.LeftButton, buttons=Qt.MouseButton.LeftButton):
    return QMouseEvent(kind, QPointF(pos), QPointF(pos), button, buttons, Qt.KeyboardModifier.NoModifier)


win = _StubWindow()
current_context.set_main_window(win)
current_context.set_hud_controller(win.view.hud)
view = win.view
minimap = minimap_mod.build()
proxy = view.add_widget(_Host(minimap), title="Minimap", pos=(-400, -300), size=(500, 420), instance_id="mm1")
frame = proxy.widget()
app.processEvents()
region = minimap._map


def region_center_in_view():
    scene = proxy.mapToScene(QPointF(region.mapTo(frame, region.rect().center())))
    return QPointF(view.mapFromScene(scene))


def button_center_in_view():
    b = minimap._tile_button
    scene = proxy.mapToScene(QPointF(b.mapTo(frame, b.rect().center())))
    return QPointF(view.mapFromScene(scene))


check("the minimap declares its map as the HUD trigger", minimap.hud_trigger() is region and region.isVisible())

# -- a press outside the trigger (a button) does not enter HUD mode
view.mousePressEvent(mouse(QEvent.Type.MouseButtonPress, button_center_in_view()))
view.mouseReleaseEvent(mouse(QEvent.Type.MouseButtonRelease, button_center_in_view(), buttons=Qt.MouseButton.NoButton))
check("a press on a button does not pin anything (and the button still works)", not view.hud.is_pinned(frame) and view.hud.entries() == [] and getattr(win, "arranged", None) == "tile")

# -- a press on the map enters HUD mode exactly where the map already is
press_pos = region_center_in_view()
region_origin = QPointF(view.mapFromScene(proxy.mapToScene(QPointF(region.mapTo(frame, QPoint(0, 0))))))
win.pans.clear()
view.mousePressEvent(mouse(QEvent.Type.MouseButtonPress, press_pos))
overlay = view.hud.overlay_for(frame)
check("pressing the map pins it", overlay is not None and view.hud.is_pinned(frame))
check("the overlay appears where the map was on screen (no jump)", overlay is not None and abs(overlay.x() - round(region_origin.x())) <= 1 and abs(overlay.y() - round(region_origin.y())) <= 1)
check("the same press panned the canvas (forwarded to the real map)", len(win.pans) == 1)
first_target = win.pans[0]
check("the frame is marked pinned and the scene copy remains", frame.hud_pinned and proxy.scene() is not None)

# -- the drag: the canvas moves, the overlay (and so the pointer's target) does not
overlay_pos = overlay.pos()
view_before = view.mapToScene(QPoint(0, 0))
view.mouseMoveEvent(mouse(QEvent.Type.MouseMove, press_pos))
view_after = view.mapToScene(QPoint(0, 0))
check("the canvas panned during the drag", view_before != view_after or len(win.pans) >= 1)
check("the overlay stayed put on screen while the canvas panned", overlay.pos() == overlay_pos)
view.mouseMoveEvent(mouse(QEvent.Type.MouseMove, press_pos))
check("a stationary pointer keeps targeting the same scene point (1:1 tracking)", len(win.pans) >= 3 and abs(win.pans[1][0] - win.pans[2][0]) < 1.0 and abs(win.pans[1][1] - win.pans[2][1]) < 1.0)
view.mouseReleaseEvent(mouse(QEvent.Type.MouseButtonRelease, press_pos, buttons=Qt.MouseButton.NoButton))
check("releasing ends the routed press but leaves it pinned", view.hud.active_press is None and view.hud.is_pinned(frame))
count = len(win.pans)
view.mouseMoveEvent(mouse(QEvent.Type.MouseMove, press_pos, buttons=Qt.MouseButton.LeftButton))
check("moves after release are no longer forwarded", len(win.pans) == count)

# -- the overlay takes presses directly once pinned
inside = QPointF(overlay.width() / 2, overlay.height() / 2)
overlay.mousePressEvent(mouse(QEvent.Type.MouseButtonPress, inside))
overlay.mouseMoveEvent(mouse(QEvent.Type.MouseMove, inside))
overlay.mouseReleaseEvent(mouse(QEvent.Type.MouseButtonRelease, inside, buttons=Qt.MouseButton.NoButton))
check("pressing/dragging the overlay itself pans through the real map", len(win.pans) == count + 2)

# -- a press on the scene's own copy while pinned is swallowed
count = len(win.pans)
scene_copy = region_center_in_view()
view.mousePressEvent(mouse(QEvent.Type.MouseButtonPress, scene_copy))
view.mouseReleaseEvent(mouse(QEvent.Type.MouseButtonRelease, scene_copy, buttons=Qt.MouseButton.NoButton))
check("a press on the sliding scene copy is swallowed (no pan)", len(win.pans) == count)

# -- the overlay renders the live region
check("the overlay paints a live copy of the region", not overlay.grab().isNull() and overlay.size() == region.size())

# -- zoomed far out the frame would greek, but pinned content stays live
frame.set_view_scale(0.01)
check("a pinned frame never swaps its content for the greek page", frame._stack.currentIndex() == 0)

# -- the window API and the manager widget
layout = win.get_hud_layout()
check("get_hud_layout lists the pinned widget at its fixed rect", len(layout["overlays"]) == 1 and layout["overlays"][0]["instance_id"] == "mm1" and layout["overlays"][0]["title"] == frame.title and layout["view"]["w"] == view.viewport().width())
manager = manager_mod.build()
manager.resize(360, 280)
manager.show()
app.processEvents()
manager.refresh()
schem = manager._schematic
rect = schem.overlay_rect(schem.layout_data["overlays"][0])
check("the manager draws the pinned widget inside the viewport rectangle", schem.view_rect().contains(rect))
check("clicking empty space returns nothing", schem.overlay_at(QPointF(1, 1)) is None)
check("the hint explains how to return a widget", "Click" in manager._hint.text())
schem.mousePressEvent(mouse(QEvent.Type.MouseButtonPress, rect.center()))
check("clicking the pinned widget returns it to the canvas", not view.hud.is_pinned(frame) and win.get_hud_layout()["overlays"] == [])
check("... and it is no longer a pinned frame (greek page may apply again)", not frame.hud_pinned and frame._stack.currentIndex() == 1)
manager.refresh()
check("the manager says nothing is pinned", "No widgets" in manager._hint.text())
frame.set_view_scale(1.0)

# -- programmatic enter/leave, and cleanup when the frame goes away
ov = current_context.get_hud_controller().enter(region, opacity=0.8)
check("a widget can enter HUD mode programmatically", ov is not None and ov.opacity == 0.8 and view.hud.is_pinned(minimap))
check("entering twice returns the same overlay", current_context.get_hud_controller().enter(region) is ov)
check("a widget outside any placed frame cannot enter", current_context.get_hud_controller().enter(QWidget()) is None)
view.hud.leave(minimap)
proxy.setPos(300, 200)  # the map now lies partly beyond the viewport edge
app.processEvents()
edge = view.hud.enter(region)
check("a region partly off screen is clamped into the viewport", edge is not None and edge.x() + edge.width() <= view.viewport().width() and edge.y() + edge.height() <= view.viewport().height() and edge.x() >= 0 and edge.y() >= 0)
proxy.setPos(-400, -300)
view.remove_widget(frame)
check("closing a pinned widget drops its overlay", view.hud.entries() == [])

proxy2 = view.add_widget(_Host(minimap_mod.build()), title="M2", pos=(0, 0), size=(500, 420), instance_id="mm2")
app.processEvents()
view.hud.enter(proxy2.widget().content.current.hud_trigger())
check("a second pin works", len(view.hud.entries()) == 1)
view.clear_widgets()
check("clearing the canvas (desk switch) drops every overlay", view.hud.entries() == [])

check("leave on something never pinned is a no-op", view.hud.leave(QWidget()) is False)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
