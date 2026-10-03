"""Verifies TODO `d0a4c7b`: new widgets land on top, and the eye/greeked
chrome click raises the widget it zooms to. A real WorkspaceView."""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

import desk.shell.window  # noqa: E402,F401  (must precede QApplication)

from PyQt6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PyQt6.QtGui import QMouseEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel  # noqa: E402

app = QApplication(sys.argv)

from desk.shell.canvas import WorkspaceView  # noqa: E402

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


def frame_of(view, proxy):
    return next(f for f in view._frames if f.graphicsProxyWidget() is proxy)


def z(proxy):
    return proxy.zValue()


def test_new_widget_lands_on_top():
    view = WorkspaceView()
    first = view.add_widget(QLabel("a"), title="a")
    second = view.add_widget(QLabel("b"), title="b")
    third = view.add_widget(QLabel("c"), title="c")
    check("each newly added widget is above everything before it", z(first) < z(second) < z(third))
    view.send_to_back(frame_of(view, third))
    fourth = view.add_widget(QLabel("d"), title="d")
    check("even after a send-to-back, a new widget outranks all existing ones", all(z(fourth) > z(p) for p in (first, second, third)))


def release_chrome(view, frame, kind):
    """Simulates a press-then-release on a chrome button of `kind`."""
    view._button_press = (frame, kind)
    original = view._hit_test_chrome
    view._hit_test_chrome = lambda pos: (frame, kind)
    try:
        event = QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(5, 5), QPointF(5, 5), Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
        view.mouseReleaseEvent(event)
    finally:
        view._hit_test_chrome = original


def test_eye_and_greeked_raise_the_widget():
    for kind in ("eye", "greeked"):
        view = WorkspaceView()
        buried = view.add_widget(QLabel("buried"), title="buried")
        others = [view.add_widget(QLabel(str(i)), title=str(i)) for i in range(3)]
        view.send_to_back(frame_of(view, buried))
        check(f"{kind}: sanity: the widget starts buried", all(z(buried) < z(p) for p in others))
        zoomed = []
        view.zoom_to_widget = lambda frame, **kw: zoomed.append(frame)
        release_chrome(view, frame_of(view, buried), kind)
        check(f"{kind}: it is brought to the front", all(z(buried) > z(p) for p in others))
        check(f"{kind}: and still zoomed to", len(zoomed) == 1 and zoomed[0] is frame_of(view, buried))


def test_other_chrome_kinds_do_not_raise():
    view = WorkspaceView()
    first = view.add_widget(QLabel("a"), title="a")
    view.add_widget(QLabel("b"), title="b")
    before = z(first)
    release_chrome(view, frame_of(view, first), "lock")
    check("a lock click leaves stacking alone", z(first) == before)


test_new_widget_lands_on_top()
test_eye_and_greeked_raise_the_widget()
test_other_chrome_kinds_do_not_raise()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
