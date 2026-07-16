import os
import sys
import time
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")

from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QContextMenuEvent, QMouseEvent
from PyQt6.QtWidgets import QApplication, QLabel, QTextEdit

import desk.shell.canvas as canvas_mod
from desk.shell.canvas import WorkspaceView

app = QApplication(sys.argv)

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


def pump(seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)


def make_view():
    view = WorkspaceView()
    view.resize(1000, 800)
    view.show()
    return view


def send_mouse(viewport, evtype, pos, buttons, button=Qt.MouseButton.LeftButton):
    ev = QMouseEvent(
        evtype, QPointF(pos), QPointF(viewport.mapToGlobal(pos)), button, buttons, Qt.KeyboardModifier.NoModifier
    )
    QApplication.sendEvent(viewport, ev)


def drag(viewport, start, delta):
    end = start + delta
    send_mouse(viewport, QEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton)
    pump(0.05)
    send_mouse(viewport, QEvent.Type.MouseMove, start + delta / 2, Qt.MouseButton.LeftButton)
    pump(0.05)
    send_mouse(viewport, QEvent.Type.MouseMove, end, Qt.MouseButton.LeftButton)
    pump(0.05)
    send_mouse(viewport, QEvent.Type.MouseButtonRelease, end, Qt.MouseButton.NoButton)
    pump(0.1)


# ---------- TODO 3846190, part 3: click-and-drag inside widget content ----------
# no longer leaks into canvas ScrollHandDrag panning.


def test_drag_inside_widget_content_does_not_pan_canvas():
    view = make_view()
    content = QLabel("passive content, no mouse handling of its own")
    content.resize(400, 300)
    view.add_widget(content, title="W", pos=(0, 0), size=(400, 300))
    pump(0.3)

    viewport = view.viewport()
    proxy = view._frames[0].graphicsProxyWidget()
    start = view.mapFromScene(proxy.sceneBoundingRect().center())

    before = (view.horizontalScrollBar().value(), view.verticalScrollBar().value())
    drag(viewport, start, QPoint(150, 100))
    after = (view.horizontalScrollBar().value(), view.verticalScrollBar().value())

    check("drag inside widget content leaves canvas scroll position untouched", before == after)


def test_drag_on_empty_canvas_still_pans() -> None:
    view = make_view()
    content = QLabel("content")
    content.resize(200, 150)
    view.add_widget(content, title="W", pos=(0, 0), size=(200, 150))
    pump(0.3)

    viewport = view.viewport()
    start = QPoint(900, 700)  # well away from the placed widget

    before = (view.horizontalScrollBar().value(), view.verticalScrollBar().value())
    drag(viewport, start, QPoint(150, 100))
    after = (view.horizontalScrollBar().value(), view.verticalScrollBar().value())

    check("drag starting on truly empty canvas still pans it", before != after)


test_drag_inside_widget_content_does_not_pan_canvas()
test_drag_on_empty_canvas_still_pans()


# ---------- TODO 3846190, part 1: right-click over widget content ----------
# no longer always shows Desk's own add-widget spawn menu.


class _StubSignal:
    def connect(self, *a):
        pass


class _StubSpawnMenu:
    def __init__(self):
        self.widget_chosen = _StubSignal()
        self.paste_requested = _StubSignal()

    def move(self, *a):
        pass

    def show(self):
        pass


def check_context_menu(name, view, viewport_pos, expect_spawn_menu):
    ev = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, viewport_pos, view.viewport().mapToGlobal(viewport_pos))
    calls = []
    with patch.object(canvas_mod, "WidgetSpawnMenu", side_effect=lambda *a, **k: (calls.append(1), _StubSpawnMenu())[1]):
        view.contextMenuEvent(ev)
    check(name, bool(calls) == expect_spawn_menu)


def test_right_click_over_widget_content_does_not_show_spawn_menu():
    view = make_view()
    text_content = QTextEdit()
    text_content.resize(300, 200)
    proxy = view.add_widget(text_content, title="TE", pos=(0, 0), size=(300, 200))
    pump(0.3)
    pos = view.mapFromScene(proxy.sceneBoundingRect().center())
    check_context_menu("right-click over widget content: no spawn menu", view, pos, expect_spawn_menu=False)


def test_right_click_on_empty_canvas_still_shows_spawn_menu():
    view = make_view()
    pump(0.1)
    check_context_menu("right-click on empty canvas: spawn menu still shown", view, QPoint(900, 700), expect_spawn_menu=True)


test_right_click_over_widget_content_does_not_show_spawn_menu()
test_right_click_on_empty_canvas_still_shows_spawn_menu()


# ---------- TODO 3846190, part 2: pinch-zoom over widget content ----------
# (duck-typed fake event -- constructing/dispatching a real
# QNativeGestureEvent segfaulted in this offscreen environment,
# unrelated to the correctness of the logic under test.)


class _FakeNativeGestureEvent:
    def __init__(self, position, value):
        self._position = position
        self._value = value

    def type(self):
        return QEvent.Type.NativeGesture

    def gestureType(self):
        return Qt.NativeGestureType.ZoomNativeGesture

    def position(self):
        return self._position

    def value(self):
        return self._value


def test_pinch_over_scrollable_widget_does_not_zoom_canvas():
    view = make_view()
    text_content = QTextEdit()
    text_content.resize(300, 200)
    proxy = view.add_widget(text_content, title="TE", pos=(0, 0), size=(300, 200))
    pump(0.3)
    pos = view.mapFromScene(proxy.sceneBoundingRect().center())
    before = view.transform().m11()
    view.event(_FakeNativeGestureEvent(QPointF(pos), 0.2))
    after = view.transform().m11()
    check("pinch over a scrollable widget (QTextEdit) does not zoom the canvas", before == after)


def test_pinch_over_non_scrollable_widget_still_zooms_canvas():
    view = make_view()
    label_content = QLabel("plain")
    label_content.resize(300, 200)
    proxy = view.add_widget(label_content, title="L", pos=(0, 0), size=(300, 200))
    pump(0.3)
    pos = view.mapFromScene(proxy.sceneBoundingRect().center())
    before = view.transform().m11()
    view.event(_FakeNativeGestureEvent(QPointF(pos), 0.2))
    after = view.transform().m11()
    check(
        "pinch over non-scrollable widget content still zooms the canvas (consistent with wheel's own behavior)",
        before != after,
    )


def test_pinch_over_empty_canvas_still_zooms():
    view = make_view()
    pump(0.1)
    before = view.transform().m11()
    view.event(_FakeNativeGestureEvent(QPointF(900, 700), 0.2))
    after = view.transform().m11()
    check("pinch over empty canvas still zooms it", before != after)


test_pinch_over_scrollable_widget_does_not_zoom_canvas()
test_pinch_over_non_scrollable_widget_still_zooms_canvas()
test_pinch_over_empty_canvas_still_zooms()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
