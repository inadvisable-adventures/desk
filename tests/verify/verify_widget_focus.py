import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from desk.shell.canvas import WorkspaceView, TITLEBAR_CLICK_THRESHOLD  # noqa: E402
from desk.shell.widget_frame import FOCUSED_TITLEBAR_COLOR, UNFOCUSED_TITLEBAR_COLOR  # noqa: E402
from PyQt6.QtCore import QPointF  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLineEdit, QWidget  # noqa: E402

app = QApplication(sys.argv)


def make_frame(view, title="Test"):
    content = QLineEdit()
    proxy = view.add_widget(content, title=title)
    return proxy.widget(), content


def test_focus_marks_enclosing_frame():
    view = WorkspaceView()
    view.show()
    frame1, content1 = make_frame(view, "One")
    frame2, content2 = make_frame(view, "Two")

    content1.setFocus()
    app.processEvents()
    assert FOCUSED_TITLEBAR_COLOR in frame1._titlebar.styleSheet()
    assert UNFOCUSED_TITLEBAR_COLOR in frame2._titlebar.styleSheet()
    assert frame1._last_focused_widget is content1

    content2.setFocus()
    app.processEvents()
    assert UNFOCUSED_TITLEBAR_COLOR in frame1._titlebar.styleSheet()
    assert FOCUSED_TITLEBAR_COLOR in frame2._titlebar.styleSheet()
    assert frame2._last_focused_widget is content2
    print("focus tracking marks the enclosing frame focused/unfocused correctly: PASS")


def test_focus_outside_any_frame_unfocuses():
    view = WorkspaceView()
    view.show()
    frame1, content1 = make_frame(view, "One")
    content1.setFocus()
    app.processEvents()
    assert FOCUSED_TITLEBAR_COLOR in frame1._titlebar.styleSheet()

    outside = QLineEdit()
    view.layout() if False else None  # not added to any WidgetFrame
    outside.setParent(view)  # inside the view, but not inside a WidgetFrame
    outside.show()
    outside.setFocus()
    app.processEvents()
    assert UNFOCUSED_TITLEBAR_COLOR in frame1._titlebar.styleSheet()
    print("focus moving outside any frame unfocuses the previous frame: PASS")


def test_frame_for_item_helper():
    view = WorkspaceView()
    frame, content = make_frame(view)
    proxy = frame.graphicsProxyWidget()
    assert view._frame_for_item(proxy) is frame
    assert view._frame_for_item(None) is None
    print("_frame_for_item resolves a WidgetFrame's proxy correctly: PASS")


def test_titlebar_click_focuses_last_widget():
    view = WorkspaceView()
    view.show()
    frame, content = make_frame(view)
    content.setFocus()
    app.processEvents()
    # Someone else steals focus in between (e.g. the user clicked
    # elsewhere) -- titlebar click should restore it.
    other = QLineEdit()
    other.setParent(view)
    other.show()
    other.setFocus()
    app.processEvents()
    assert not content.hasFocus()

    view._titlebar_click_frame = frame
    view._titlebar_click_pos = QPointF(10, 10)
    from PyQt6.QtCore import QEvent
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import Qt as QtNS

    release = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(10 + TITLEBAR_CLICK_THRESHOLD, 10),
        QtNS.MouseButton.LeftButton,
        QtNS.MouseButton.NoButton,
        QtNS.KeyboardModifier.NoModifier,
    )
    view.mouseReleaseEvent(release)
    app.processEvents()
    assert content.hasFocus()
    assert view._titlebar_click_frame is None
    print("titlebar click (small displacement) re-focuses the remembered widget: PASS")


def test_titlebar_drag_does_not_focus():
    view = WorkspaceView()
    view.show()
    frame, content = make_frame(view)
    other = QLineEdit()
    other.setParent(view)
    other.show()
    other.setFocus()
    app.processEvents()
    assert not content.hasFocus()

    view._titlebar_click_frame = frame
    view._titlebar_click_pos = QPointF(10, 10)
    from PyQt6.QtCore import QEvent
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import Qt as QtNS

    release = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(10 + TITLEBAR_CLICK_THRESHOLD + 50, 10),
        QtNS.MouseButton.LeftButton,
        QtNS.MouseButton.NoButton,
        QtNS.KeyboardModifier.NoModifier,
    )
    view.mouseReleaseEvent(release)
    app.processEvents()
    assert not content.hasFocus()
    print("large displacement (a drag) does not trigger focus restore: PASS")


def test_fallback_to_content_when_nothing_focused_yet():
    view = WorkspaceView()
    view.show()
    frame, content = make_frame(view)
    assert frame._last_focused_widget is None
    frame.focus_last_widget()
    app.processEvents()
    # content itself (a QLineEdit) is what gets focus when nothing was
    # ever remembered.
    assert content.hasFocus() or frame.content.hasFocus()
    print("no prior focus: falls back to focusing content itself: PASS")


test_focus_marks_enclosing_frame()
test_focus_outside_any_frame_unfocuses()
test_frame_for_item_helper()
test_titlebar_click_focuses_last_widget()
test_titlebar_drag_does_not_focus()
test_fallback_to_content_when_nothing_focused_yet()
print("ALL PASS")
