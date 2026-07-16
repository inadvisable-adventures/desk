import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from PyQt6.QtCore import QPointF, QPoint, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication, QLabel

from desk.shell.canvas import WorkspaceView

app = QApplication(sys.argv)


def pump(seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)


def make_view_with_frames(n):
    view = WorkspaceView()
    view.resize(1400, 1000)
    view.show()
    proxies = []
    for i in range(n):
        content = QLabel(f"content {i}")
        proxy = view.add_widget(content, title=f"W{i}", pos=(i * 400, 0), size=(300, 200))
        proxies.append(proxy)
    pump(0.2)
    return view, proxies


def click_button(view, frame, button_widget):
    center_local = button_widget.rect().center()
    center_in_frame = button_widget.mapTo(frame, center_local)
    scene_pt = frame.graphicsProxyWidget().mapToScene(QPointF(center_in_frame))
    view_pt = view.mapFromScene(scene_pt)
    press = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress, QPointF(view_pt), Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    view.mousePressEvent(press)
    release = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease, QPointF(view_pt), Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
    )
    view.mouseReleaseEvent(release)
    pump(0.1)


def test_bring_to_front():
    view, proxies = make_view_with_frames(3)
    frame1 = proxies[1].widget()
    view.bring_to_front(frame1)
    z_values = [p.zValue() for p in proxies]
    assert z_values[1] == max(z_values), z_values
    print("bring_to_front sets highest zValue: PASS")


def test_send_to_back():
    view, proxies = make_view_with_frames(3)
    frame1 = proxies[1].widget()
    view.send_to_back(frame1)
    z_values = [p.zValue() for p in proxies]
    assert z_values[1] == min(z_values), z_values
    print("send_to_back sets lowest zValue: PASS")


def test_repeated_bring_to_front_stacks_correctly():
    view, proxies = make_view_with_frames(3)
    frame0 = proxies[0].widget()
    frame2 = proxies[2].widget()
    view.bring_to_front(frame0)
    view.bring_to_front(frame2)
    assert proxies[2].zValue() > proxies[0].zValue(), (proxies[2].zValue(), proxies[0].zValue())
    print("repeated bring_to_front on different widgets stacks correctly: PASS")


def test_real_button_click():
    view, proxies = make_view_with_frames(2)
    frame0 = proxies[0].widget()
    frame1 = proxies[1].widget()
    click_button(view, frame0, frame0._titlebar.bring_to_front_button)
    assert proxies[0].zValue() > proxies[1].zValue(), (proxies[0].zValue(), proxies[1].zValue())
    click_button(view, frame0, frame0._titlebar.send_to_back_button)
    assert proxies[0].zValue() < proxies[1].zValue()
    print("real button click (press+release via WorkspaceView) works end-to-end: PASS")


def test_close_button_still_works():
    view, proxies = make_view_with_frames(2)
    frame0 = proxies[0].widget()
    closed = []
    view.widget_close_requested.connect(lambda f: closed.append(f))
    click_button(view, frame0, frame0._titlebar.close_button)
    assert closed == [frame0]
    print("existing close button still fires widget_close_requested: PASS")


def test_press_then_release_elsewhere_is_cancelled():
    view, proxies = make_view_with_frames(2)
    frame0 = proxies[0].widget()
    frame1 = proxies[1].widget()
    button = frame0._titlebar.bring_to_front_button
    center_local = button.rect().center()
    center_in_frame = button.mapTo(frame0, center_local)
    scene_pt = frame0.graphicsProxyWidget().mapToScene(QPointF(center_in_frame))
    view_pt = view.mapFromScene(scene_pt)
    press = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress, QPointF(view_pt), Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    view.mousePressEvent(press)

    # Release far away (over frame1's title area, not the button).
    other_scene_pt = frame1.graphicsProxyWidget().mapToScene(QPointF(10, 10))
    other_view_pt = view.mapFromScene(other_scene_pt)
    release = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease, QPointF(other_view_pt), Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
    )
    view.mouseReleaseEvent(release)
    pump(0.1)
    z_values = [p.zValue() for p in proxies]
    assert z_values[0] == z_values[1] == 0.0, z_values
    print("press-then-release-elsewhere cancels the click: PASS")


test_bring_to_front()
test_send_to_back()
test_repeated_bring_to_front_stacks_correctly()
test_real_button_click()
test_close_button_still_works()
test_press_then_release_elsewhere_is_cancelled()
print("ALL PASS")
