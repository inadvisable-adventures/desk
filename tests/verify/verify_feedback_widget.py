import importlib.util
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from desk.shell.canvas import WorkspaceView  # noqa: E402
from desk.shell import current_context  # noqa: E402
from PyQt6.QtCore import QEvent, Qt  # noqa: E402
from PyQt6.QtGui import QMouseEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton  # noqa: E402

app = QApplication(sys.argv)


def load_widget_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


feedback_mod = load_widget_module("feedback_verify_mod", "widgets/feedback/widget.py")


# ---------- describe_widget_at_global_pos ----------


def screen_pos_of(view, frame, widget):
    from PyQt6.QtCore import QPointF

    proxy = frame.graphicsProxyWidget()
    local_point = widget.mapTo(frame, widget.rect().center())
    scene_point = proxy.mapToScene(QPointF(local_point))
    return view.mapFromScene(scene_point)


def test_describe_widget_at_global_pos_embedded():
    win = QMainWindow()
    view = WorkspaceView()
    win.setCentralWidget(view)
    win.resize(800, 600)
    win.show()
    app.processEvents()

    button = QPushButton("Save")
    proxy = view.add_widget(button, title="My Editor")
    frame = proxy.widget()
    app.processEvents()

    viewport_pos = screen_pos_of(view, frame, button)
    global_pos = view.viewport().mapToGlobal(viewport_pos)
    path = view.describe_widget_at_global_pos(global_pos)
    assert path is not None
    assert 'WidgetFrame["My Editor"]' in path
    assert 'QPushButton["Save"]' in path
    print("describe_widget_at_global_pos resolves an embedded button's path: PASS")


def test_describe_widget_at_global_pos_blank_canvas():
    win = QMainWindow()
    view = WorkspaceView()
    win.setCentralWidget(view)
    win.resize(800, 600)
    win.show()
    app.processEvents()
    # Far corner, no widgets placed -- blank canvas.
    global_pos = view.viewport().mapToGlobal(view.viewport().rect().center())
    path = view.describe_widget_at_global_pos(global_pos)
    assert path is None
    print("describe_widget_at_global_pos returns None over blank canvas: PASS")


def test_context_hooks_roundtrip():
    win = QMainWindow()
    current_context.set_main_window(win)
    assert current_context.get_main_window() is win

    def resolver(pos):
        return "SomePath"

    current_context.set_widget_path_resolver(resolver)
    assert current_context.get_widget_path_resolver() is resolver
    print("current_context main-window/widget-path-resolver hooks round-trip: PASS")


# ---------- FeedbackWidget ----------


def test_screenshot_inserts_reference_and_records_pixmap():
    win = QMainWindow()
    win.resize(200, 200)
    win.show()
    app.processEvents()
    with patch.object(current_context, "get_main_window", return_value=win):
        widget = feedback_mod.FeedbackWidget()
        widget._take_screenshot()
        assert len(widget._screenshots) == 1
        text = widget._body.toPlainText()
        assert "screenshot 1" in text
        base_name = widget._base_name
        assert base_name is not None
        assert f"{base_name}-screenshot-1.png" in text

        widget._take_screenshot()
        assert len(widget._screenshots) == 2
        assert f"{base_name}-screenshot-2.png" in widget._body.toPlainText()
        assert widget._base_name == base_name  # same base name reused
    print("Screenshot inserts a matching reference and records a pixmap; base name reused: PASS")


def test_pick_inserts_resolved_path():
    widget = feedback_mod.FeedbackWidget()
    widget._on_ui_path_picked("WidgetFrame[\"Console\"] > QPlainTextEdit")
    assert "WidgetFrame" in widget._body.toPlainText()
    print("picking a UI element inserts the resolved path: PASS")


def test_pick_with_no_result_inserts_nothing():
    widget = feedback_mod.FeedbackWidget()
    widget._on_ui_path_picked("")
    assert widget._body.toPlainText() == ""
    print("cancelled/empty pick inserts nothing: PASS")


def test_save_feedback_writes_md_and_screenshots():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        win = QMainWindow()
        win.resize(150, 150)
        win.show()
        app.processEvents()
        with patch.object(current_context, "get_main_window", return_value=win), patch.object(
            current_context, "get_current_desk_directory", return_value=directory
        ):
            widget = feedback_mod.FeedbackWidget()
            widget._body.setPlainText("Something looks off here.")
            widget._take_screenshot()
            base_name = widget._base_name

            widget._save_feedback()

            md_path = directory / f"{base_name}.md"
            assert md_path.is_file()
            assert "Something looks off here." in md_path.read_text()
            screenshot_path = directory / f"{base_name}-screenshot-1.png"
            assert screenshot_path.is_file()

            # After saving, state resets for the next round.
            assert widget._base_name is None
            assert widget._screenshots == []
    print("Save Feedback writes the .md and screenshot PNGs with matching names; resets after: PASS")


def test_save_feedback_does_not_overwrite_existing():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        with patch.object(current_context, "get_current_desk_directory", return_value=directory):
            widget = feedback_mod.FeedbackWidget()
            widget._body.setPlainText("Original text")
            base_name = widget._ensure_base_name()
            existing = directory / f"{base_name}.md"
            existing.write_text("pre-existing content")

            widget._save_feedback()
            # Must not have been overwritten.
            assert existing.read_text() == "pre-existing content"
    print("Save Feedback does not overwrite a pre-existing file at the target path: PASS")


def test_overlay_click_emits_and_closes():
    win = QMainWindow()
    win.resize(400, 300)
    win.show()
    app.processEvents()
    overlay = feedback_mod._PickOverlay(win)
    overlay.show()
    app.processEvents()

    received = []
    overlay.picked.connect(lambda p: received.append(p))

    with patch.object(current_context, "get_widget_path_resolver", return_value=lambda pos: "Picked!"):
        from PyQt6.QtCore import QPointF

        press = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(10, 10),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        overlay.mousePressEvent(press)
    app.processEvents()
    assert received == ["Picked!"]
    print("overlay click resolves via the path resolver and emits it: PASS")


def test_overlay_escape_cancels():
    win = QMainWindow()
    win.resize(400, 300)
    win.show()
    app.processEvents()
    overlay = feedback_mod._PickOverlay(win)
    overlay.show()
    app.processEvents()

    received = []
    overlay.picked.connect(lambda p: received.append(p))

    from PyQt6.QtGui import QKeyEvent

    escape = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    overlay.keyPressEvent(escape)
    app.processEvents()
    assert received == [""]
    print("overlay Escape cancels (emits empty string): PASS")


test_describe_widget_at_global_pos_embedded()
test_describe_widget_at_global_pos_blank_canvas()
test_context_hooks_roundtrip()
test_screenshot_inserts_reference_and_records_pixmap()
test_pick_inserts_resolved_path()
test_pick_with_no_result_inserts_nothing()
test_save_feedback_writes_md_and_screenshots()
test_save_feedback_does_not_overwrite_existing()
test_overlay_click_emits_and_closes()
test_overlay_escape_cancels()
print("ALL PASS")
