"""Verifies TODO `669b690`: the Minimap widget and DeskWindow's canvas
layout API (real WorkspaceView frames, stub window object)."""

import os
import sys
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.window  # noqa: E402,F401  (must precede QApplication)

from PyQt6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PyQt6.QtGui import QMouseEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel  # noqa: E402

app = QApplication(sys.argv)

from desk.event_mediator import EventMediator  # noqa: E402
from desk.shell import current_context  # noqa: E402
from desk.shell.canvas import WorkspaceView  # noqa: E402
from desk.widget_overview import WIDGET_OVERVIEW_CHANGED_EVENT  # noqa: E402

DeskWindow = desk.shell.window.DeskWindow
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


def _module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("mm_check", REPO_ROOT / "widgets" / "minimap" / "widget.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


module = _module()


class _StubWindow:
    """DeskWindow's canvas-layout methods over a real WorkspaceView."""

    def __init__(self, count=3):
        self.view = WorkspaceView()
        self.view.resize(800, 600)
        self._widgets = {"w": types.SimpleNamespace(kind="python")}
        self._arrangement_undo_stack = []
        for i in range(count):
            self.add(f"inst{i}", 30 * i, 20 * i)

    def add(self, instance_id, x, y, size=(300, 200)):
        proxy = self.view.add_widget(QLabel(instance_id), title=instance_id, pos=(x, y), size=size, instance_id=instance_id)
        proxy.widget().content = types.SimpleNamespace(widget_id="w")
        return proxy.widget()

    def _display_name_for_instance(self, iid):
        return f"title-{iid}"

    def frame(self, iid):
        return next(f for f in self.view._frames if f.instance_id == iid)

    def pos(self, iid):
        p = self.frame(iid).graphicsProxyWidget().pos()
        return (p.x(), p.y())


for name in ("_canvas_rects", "get_canvas_layout", "pan_canvas_to", "_move_frames", "arrange_canvas", "undo_canvas_arrangement"):
    setattr(_StubWindow, name, getattr(DeskWindow, name))


def overlaps(win):
    rects = win._canvas_rects()
    return any(
        min(a["x"] + a["w"], b["x"] + b["w"]) > max(a["x"], b["x"]) and min(a["y"] + a["h"], b["y"] + b["h"]) > max(a["y"], b["y"])
        for i, a in enumerate(rects)
        for b in rects[i + 1 :]
    )


# -- window API ------------------------------------------------------------------------


def test_layout_dict():
    win = _StubWindow()
    layout = win.get_canvas_layout()
    check("a rect per frame, in placement order, with id/kind/title/geometry", [f["id"] for f in layout["frames"]] == ["inst0", "inst1", "inst2"] and layout["frames"][1]["x"] == 30 and layout["frames"][0]["w"] == 300 and layout["frames"][0]["title"] == "title-inst0" and layout["frames"][0]["kind"] == "python")
    check("the viewport rect is included", set(layout["view"]) == {"x", "y", "w", "h"} and layout["view"]["w"] > 0)
    check("nothing to undo yet", layout["can_undo"] is False)


def test_pan():
    win = _StubWindow()
    win.pan_canvas_to(5000, -3000)
    v = win.get_canvas_layout()["view"]
    check("panning centers the viewport on the point", abs(v["x"] + v["w"] / 2 - 5000) < 2 and abs(v["y"] + v["h"] / 2 + 3000) < 2)


def test_arrange_and_undo_with_changed_widget_set():
    win = _StubWindow(count=4)
    before = {i: win.pos(i) for i in ("inst0", "inst1", "inst2", "inst3")}
    check("sanity: overlapping to start", overlaps(win))
    moved = win.arrange_canvas("nudge")
    check("nudge moved something and cleared every overlap", moved > 0 and not overlaps(win))
    check("an undo is now available", win.get_canvas_layout()["can_undo"] is True)
    win.view.remove_widget(win.frame("inst1"))
    fresh = win.add("fresh", 7000, 7000)
    fresh_pos = win.pos("fresh")
    restored = win.undo_canvas_arrangement()
    check("undo restores widgets still present to where they were", all(win.pos(i) == before[i] for i in ("inst0", "inst2", "inst3")))
    check("a widget closed since is skipped without error", all(f.instance_id != "inst1" for f in win.view._frames) and restored <= 3)
    check("a widget opened since stays exactly where it landed", win.pos("fresh") == fresh_pos)
    check("the stack is empty again", win.get_canvas_layout()["can_undo"] is False and win.undo_canvas_arrangement() == 0)


def test_locked_widgets_and_noop_arrangements():
    win = _StubWindow(count=3)
    win.frame("inst0").locked = True
    pinned = win.pos("inst0")
    win.arrange_canvas("tile")
    check("tile never moves a locked widget", win.pos("inst0") == pinned)
    win.undo_canvas_arrangement()
    ok = _StubWindow(count=2)
    ok.frame("inst1").graphicsProxyWidget().setPos(5000, 0)
    check("nudging an already-clear layout moves nothing", ok.arrange_canvas("nudge") == 0)
    check("and pushes no undo snapshot", ok.get_canvas_layout()["can_undo"] is False)


def test_organize_groups_by_kind():
    win = _StubWindow(count=4)
    win._widgets["h"] = types.SimpleNamespace(kind="html")
    win.frame("inst1").content = types.SimpleNamespace(widget_id="h")
    win.frame("inst3").content = types.SimpleNamespace(widget_id="h")
    win.arrange_canvas("organize")
    rects = {f["id"]: f for f in win._canvas_rects()}
    check("same-kind widgets end up in the same row, kinds in different rows", rects["inst0"]["y"] == rects["inst2"]["y"] and rects["inst1"]["y"] == rects["inst3"]["y"] and rects["inst0"]["y"] != rects["inst1"]["y"] and not overlaps(win))


# -- widget -------------------------------------------------------------------------------


class _WindowFor:
    def __init__(self, layout):
        self.layout = layout
        self.calls = []

    def get_canvas_layout(self):
        return self.layout

    def pan_canvas_to(self, x, y):
        self.calls.append(("pan", x, y))

    def arrange_canvas(self, mode):
        self.calls.append(("arrange", mode))
        return 1

    def undo_canvas_arrangement(self):
        self.calls.append(("undo",))
        return 1


LAYOUT = {
    "frames": [
        {"id": "a", "kind": "python", "title": "A", "x": 0, "y": 0, "w": 400, "h": 300, "locked": False, "stale": False},
        {"id": "b", "kind": "html", "title": "B", "x": 1000, "y": 500, "w": 400, "h": 300, "locked": False, "stale": True},
    ],
    "view": {"x": 200, "y": 100, "w": 800, "h": 600},
    "can_undo": False,
}


def with_window(window):
    previous = current_context.get_main_window()
    current_context.set_main_window(window)
    return previous


def test_transform_round_trip_and_fit():
    window = _WindowFor(dict(LAYOUT))
    previous = with_window(window)
    try:
        widget = module.build()
        widget.resize(420, 360)
        mp = widget._map
        scale, ox, oy = mp.transform()
        corners = [mp.to_map(0, 0), mp.to_map(1400, 800)]
        check("everything (incl. the far corner) fits inside the widget", all(0 <= c.x() <= mp.width() and 0 <= c.y() <= mp.height() for c in corners))
        x, y = mp.to_scene(mp.to_map(777, 333))
        check("to_scene inverts to_map", abs(x - 777) < 1e-6 and abs(y - 333) < 1e-6)
        r = mp.map_rect(0, 0, 400, 300)
        check("map rects scale uniformly", abs(r.width() / r.height() - 400 / 300) < 1e-6)
        mp.layout_data = {"frames": [], "view": {"x": 0, "y": 0, "w": 10, "h": 10}, "can_undo": False}
        check("an empty canvas still has sane bounds (just the viewport)", mp.bounds().width() == 10 and mp.transform()[0] > 0)
    finally:
        current_context.set_main_window(previous) if previous is not None else None


def test_click_and_drag_pan_and_buttons():
    window = _WindowFor(dict(LAYOUT))
    previous = with_window(window)
    try:
        widget = module.build()
        widget.resize(420, 360)
        mp = widget._map
        target = mp.to_map(500, 400)
        press = QMouseEvent(QEvent.Type.MouseButtonPress, target, target, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        mp.mousePressEvent(press)
        pan = window.calls[-1]
        check("clicking the map pans the canvas to that scene point", pan[0] == "pan" and abs(pan[1] - 500) < 1e-6 and abs(pan[2] - 400) < 1e-6)
        other = QPointF(target.x() + 20, target.y() + 10)
        move = QMouseEvent(QEvent.Type.MouseMove, other, other, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        mp.mouseMoveEvent(move)
        check("dragging keeps panning", len([c for c in window.calls if c[0] == "pan"]) == 2)
        hover = QMouseEvent(QEvent.Type.MouseMove, other, other, Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
        mp.mouseMoveEvent(hover)
        check("moving with no button down does not pan", len([c for c in window.calls if c[0] == "pan"]) == 2)
        window.calls.clear()
        widget._organize_button.click()
        widget._nudge_button.click()
        widget._tile_button.click()
        check("the three buttons request their arrangements", window.calls == [("arrange", "organize"), ("arrange", "nudge"), ("arrange", "tile")])
        check("Undo is disabled with nothing to undo", not widget._undo_button.isEnabled())
        window.layout = dict(LAYOUT, can_undo=True)
        widget.refresh()
        check("Undo enables once the window reports something to undo", widget._undo_button.isEnabled())
        widget._undo_button.click()
        check("Undo calls the window", window.calls[-1] == ("undo",))
    finally:
        current_context.set_main_window(previous) if previous is not None else None


def test_refresh_only_repaints_on_change_and_events_refresh():
    window = _WindowFor(dict(LAYOUT))
    previous = with_window(window)
    try:
        widget = module.build()
        mediator = EventMediator()
        widget.bind_event_mediator("mm-1", mediator)
        widget.refresh()
        first = widget._map.layout_data
        window.layout = dict(LAYOUT, frames=LAYOUT["frames"][:1])
        mediator.publish(WIDGET_OVERVIEW_CHANGED_EVENT, {"widgets": []}, "desk")
        widget._subscription._poll()
        check("an overview event refreshes immediately", len(widget._map.layout_data["frames"]) == 1 and widget._map.layout_data is not first)
        check("the timer runs only while visible", not widget._timer.isActive())
        widget.show()
        check("showing starts it", widget._timer.isActive())
        widget.hide()
        check("hiding stops it", not widget._timer.isActive())
        widget.resize(420, 360)
        widget.show()
        check("painting does not raise", widget.grab().width() == 420)
    finally:
        current_context.set_main_window(previous) if previous is not None else None


def test_no_window_is_safe():
    previous = current_context.get_main_window()
    try:
        current_context._main_window = None
        widget = module.build()
        widget.refresh()
        widget._organize_button.click()
        widget._undo_button.click()
        widget._map._on_pan(1, 2)
        check("with no main window nothing raises", True)
    finally:
        current_context._main_window = previous


test_layout_dict()
test_pan()
test_arrange_and_undo_with_changed_widget_set()
test_locked_widgets_and_noop_arrangements()
test_organize_groups_by_kind()
test_transform_round_trip_and_fit()
test_click_and_drag_pan_and_buttons()
test_refresh_only_repaints_on_change_and_events_refresh()
test_no_window_is_safe()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
