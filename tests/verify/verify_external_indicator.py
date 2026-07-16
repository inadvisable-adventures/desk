import importlib.util
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from PyQt6.QtWidgets import QApplication, QWidget

from desk.shell import current_context
from desk.shell.widget_frame import WidgetFrame

app = QApplication(sys.argv)


def pump(seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)


def load_widget_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_path_is_external():
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as other:
        directory = Path(d)
        (directory / "sub").mkdir()
        current_context.set_current_desk_directory(directory)

        assert current_context.path_is_external(directory / "TODO.md") is False
        assert current_context.path_is_external(directory / "sub" / "file.txt") is False
        assert current_context.path_is_external(Path(other) / "file.txt") is True

        current_context.set_current_desk_directory(None)
        assert current_context.path_is_external(directory / "TODO.md") is False
        current_context.set_current_desk_directory(directory)
    print("path_is_external: PASS")


def test_widget_frame_set_external():
    content = QWidget()
    frame = WidgetFrame("Markdown", content)
    assert frame._titlebar._label.text() == "Markdown"
    frame.set_external(True)
    assert frame._titlebar._label.text() == "Markdown [EXTERNAL]"
    frame.set_external(False)
    assert frame._titlebar._label.text() == "Markdown"
    print("WidgetFrame.set_external: PASS")


def test_markdown_widget():
    md = load_widget_module("md_mod", "widgets/markdown/widget.py")
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as other:
        directory = Path(d)
        current_context.set_current_desk_directory(directory)
        inside = directory / "notes.md"
        inside.write_text("hi")
        outside = Path(other) / "notes.md"
        outside.write_text("hi")

        w = md.build()
        events = []
        w.external_path_changed.connect(events.append)

        w.set_file(inside)
        assert events == [False], events
        events.clear()

        w.set_file(outside)
        assert events == [True], events
        events.clear()

        w.set_file(inside)
        assert events == [False], events
        w.deleteLater()
    print("MarkdownWidget external_path_changed: PASS")


def test_todo_widget_and_place_widget_binding():
    sys.path.insert(0, "widgets/editor")
    todo_mod = load_widget_module("todo_mod", "widgets/todo/widget.py")
    editor_mod = load_widget_module("editor_mod", "widgets/editor/widget.py")

    with tempfile.TemporaryDirectory() as parent:
        parent_path = Path(parent)
        (parent_path / "TODO.md").write_text("a1b2c3d. Parent item.\n")
        desk_dir = parent_path / "child"
        desk_dir.mkdir()
        current_context.set_current_desk_directory(desk_dir)

        todo = todo_mod.build()  # reload() already ran in __init__
        events = []
        todo.external_path_changed.connect(events.append)
        # Simulate DeskWindow._bind_external_indicator's post-connect sync.
        todo.refresh_external_path_status()
        assert events == [True], f"TODO.md resolved above the Desk dir should be external: {events}"
        print("TodoWidget external_path_changed (nearest-parent lookup): PASS")

        inside_file = desk_dir / "notes.md"
        inside_file.write_text("hi")
        ed = editor_mod.build()
        ed_events = []
        ed.external_path_changed.connect(ed_events.append)
        ed.set_file(inside_file)
        assert ed_events == [False], ed_events
        print("EditorWidget external_path_changed: PASS")

        todo.deleteLater()
        ed.deleteLater()


test_path_is_external()
test_widget_frame_set_external()
test_markdown_widget()
test_todo_widget_and_place_widget_binding()
print("ALL PASS")
