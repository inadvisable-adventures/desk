import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from desk.shell.canvas import WorkspaceView  # noqa: E402
from desk.desks import WidgetState  # noqa: E402
from PyQt6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PyQt6.QtGui import QMouseEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLineEdit  # noqa: E402

app = QApplication(sys.argv)


def make_frame(view, title="Test"):
    content = QLineEdit()
    proxy = view.add_widget(content, title=title)
    return proxy.widget(), content


def test_set_locked_toggles_button_visibility():
    view = WorkspaceView()
    frame, _ = make_frame(view)
    tb = frame._titlebar
    assert tb.lock_button.isVisible()
    assert tb.bring_to_front_button.isVisible()
    assert tb.send_to_back_button.isVisible()
    assert tb.close_button.isVisible()
    assert not tb.unlock_button.isVisible()

    frame.set_locked(True)
    assert frame.locked is True
    assert not tb.lock_button.isVisible()
    assert not tb.bring_to_front_button.isVisible()
    assert not tb.send_to_back_button.isVisible()
    assert not tb.close_button.isVisible()
    assert tb.unlock_button.isVisible()

    frame.set_locked(False)
    assert frame.locked is False
    assert tb.lock_button.isVisible()
    assert not tb.unlock_button.isVisible()
    print("set_locked toggles button visibility correctly: PASS")


def screen_pos_of(view, frame, widget):
    """Viewport-space position of `widget` (a descendant of `frame`,
    which is embedded via a QGraphicsProxyWidget) -- mapTo() alone
    doesn't work across the proxy boundary (confirmed directly:
    "QWidget::mapTo(): parent must be in parent hierarchy"), so this
    goes through the proxy/scene chain instead, same shape as
    widgets/todo/widget.py's own _screen_point."""
    proxy = frame.graphicsProxyWidget()
    local_point = widget.mapTo(frame, widget.rect().center())
    scene_point = proxy.mapToScene(QPointF(local_point))
    return view.mapFromScene(scene_point)


def test_hit_test_returns_lock_and_unlock():
    view = WorkspaceView()
    view.show()
    frame, _ = make_frame(view)

    pos = QPointF(screen_pos_of(view, frame, frame._titlebar.lock_button))
    hit = view._hit_test_chrome(pos)
    assert hit == (frame, "lock"), hit

    frame.set_locked(True)
    pos2 = QPointF(screen_pos_of(view, frame, frame._titlebar.unlock_button))
    hit2 = view._hit_test_chrome(pos2)
    assert hit2 == (frame, "unlock"), hit2
    print("_hit_test_chrome returns lock/unlock at the right positions: PASS")


def press_release(view, pos):
    press = QMouseEvent(
        QEvent.Type.MouseButtonPress, pos, Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    view.mousePressEvent(press)
    release = QMouseEvent(
        QEvent.Type.MouseButtonRelease, pos, Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
    )
    view.mouseReleaseEvent(release)


def test_click_lock_button_locks_frame():
    view = WorkspaceView()
    view.show()
    frame, _ = make_frame(view)
    pos = QPointF(screen_pos_of(view, frame, frame._titlebar.lock_button))
    press_release(view, pos)
    assert frame.locked is True
    print("clicking the lock button locks the frame: PASS")


def test_click_unlock_button_unlocks_frame():
    view = WorkspaceView()
    view.show()
    frame, _ = make_frame(view)
    frame.set_locked(True)
    pos = QPointF(screen_pos_of(view, frame, frame._titlebar.unlock_button))
    press_release(view, pos)
    assert frame.locked is False
    print("clicking the unlock button unlocks the frame: PASS")


def test_locked_frame_does_not_drag_but_still_focuses():
    view = WorkspaceView()
    view.show()
    frame, content = make_frame(view)
    frame.set_locked(True)
    other = QLineEdit()
    other.setParent(view)
    other.show()
    other.setFocus()
    app.processEvents()

    tb_pos = QPointF(screen_pos_of(view, frame, frame._titlebar))
    press = QMouseEvent(
        QEvent.Type.MouseButtonPress, tb_pos, Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    view.mousePressEvent(press)
    assert view._drag_frame is None, "locked widget must not start a drag"
    assert view._titlebar_click_frame is frame  # still tracked for click-to-focus

    release = QMouseEvent(
        QEvent.Type.MouseButtonRelease, tb_pos, Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
    )
    view.mouseReleaseEvent(release)
    app.processEvents()
    # No prior focus recorded -> falls back to content itself.
    assert content.hasFocus() or frame.content.hasFocus()
    print("locked widget's titlebar does not drag but still supports click-to-focus: PASS")


def test_locked_frame_resize_handle_swallowed():
    view = WorkspaceView()
    view.show()
    frame, _ = make_frame(view)
    frame.set_locked(True)
    pos = QPointF(screen_pos_of(view, frame, frame._right_handle))
    press = QMouseEvent(
        QEvent.Type.MouseButtonPress, pos, Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    view.mousePressEvent(press)
    assert view._drag_frame is None, "locked widget must not start a resize"
    print("locked widget's resize handle press is swallowed: PASS")


def test_widget_state_locked_roundtrip():
    state = WidgetState("editor", 0.0, 0.0, 100.0, 100.0, locked=True)
    assert state.locked is True
    # Old-shaped dict with no "locked" key still constructs fine.
    old_shape = {"widget_id": "editor", "x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}
    state2 = WidgetState(**old_shape)
    assert state2.locked is False
    print("WidgetState.locked defaults False for old-shaped data: PASS")


test_set_locked_toggles_button_visibility()
test_hit_test_returns_lock_and_unlock()
test_click_lock_button_locks_frame()
test_click_unlock_button_unlocks_frame()
test_locked_frame_does_not_drag_but_still_focuses()
test_locked_frame_resize_handle_swallowed()
test_widget_state_locked_roundtrip()
print("ALL PASS")
