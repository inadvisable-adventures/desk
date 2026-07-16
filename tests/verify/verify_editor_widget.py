import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")
sys.path.insert(0, "widgets/editor")

from PyQt6.QtWidgets import QApplication

from desk_services.file_watcher import get_service

app = QApplication(sys.argv)


def pump(seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)


import widget as editor_module

with tempfile.TemporaryDirectory() as d:
    directory = Path(d)
    f = directory / "notes.txt"
    f.write_text("v1")

    w = editor_module.build()
    w.set_file(f)
    pump(0.2)
    assert w.editor.text() == "v1"

    # 1. External change, no local unsaved edits -> silent reload.
    f.write_text("v2 external")
    pump(1.0)
    assert w.editor.text() == "v2 external", w.editor.text()
    assert not w._external_change_pending
    print("silent reload when unmodified: PASS")

    # 2. Local unsaved edit, then external change -> buffer NOT clobbered,
    #    conflict flagged.
    w.editor.setText("my local edit")
    assert w.editor.isModified()
    f.write_text("v3 external while editing")
    pump(1.0)
    assert w.editor.text() == "my local edit", f"buffer was clobbered: {w.editor.text()}"
    assert w._external_change_pending
    assert "(changed on disk)" in w._label.text(), w._label.text()
    print("no clobber + conflict flagged: PASS")

    # 3. Saving resolves the conflict in favor of the local edit, and the
    #    echo of our own save doesn't re-trigger anything.
    ok = w._save_file()
    assert ok
    pump(1.0)
    assert not w._external_change_pending
    assert "(changed on disk)" not in w._label.text()
    assert f.read_text() == "my local edit"
    print("save resolves conflict + suppresses own echo: PASS")

    w.deleteLater()
    app.processEvents()


def test_cross_widget_scenario():
    import importlib.util

    from desk.shell import current_context

    spec = importlib.util.spec_from_file_location("todo_widget_module", "widgets/todo/widget.py")
    todo_widget_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(todo_widget_module)

    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        todo_path = directory / "TODO.md"
        todo_path.write_text("a1b2c3d. First item.\n")
        current_context.set_current_desk_directory(directory)

        todo = todo_widget_module.build()
        todo.reload()
        pump(0.2)

        ed = editor_module.build()
        ed.set_file(todo_path)
        pump(0.2)
        assert ed.editor.text() == "a1b2c3d. First item.\n"

        # TODO widget performs a real write-and-commit (add an item).
        todo._add_item("Second item added via TODO widget")
        pump(1.5)

        assert len(todo._state["items"]) == 2
        assert "Second item added via TODO widget" in ed.editor.text(), ed.editor.text()
        assert not ed._external_change_pending
        print("cross-widget: Editor widget picked up TODO widget's write: PASS")

        todo.deleteLater()
        ed.deleteLater()
        app.processEvents()


test_cross_widget_scenario()
get_service().stop()
print("ALL PASS")
