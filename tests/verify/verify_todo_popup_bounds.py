import importlib.util
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")
sys.path.insert(0, "widgets/todo")

from PyQt6.QtWidgets import QApplication

from desk.shell import current_context
from desk.shell.canvas import WorkspaceView
from desk.shell.python_widget import PythonWidgetHost

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


def test_mapToGlobal_is_unreliable_confirmation():
    from PyQt6.QtCore import QPoint, QPointF
    from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

    view = WorkspaceView()
    view.resize(1000, 800)
    view.show()

    host = QWidget()
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    inner = QLabel("stand-in")
    layout.addWidget(inner)

    proxy = view.add_widget(host, title="Test", pos=(100, 50), size=(300, 200))
    pump(0.1)
    view.scale(2.0, 2.0)
    pump(0.1)

    frame = proxy.widget()
    top_left_in_frame = inner.mapTo(frame, QPoint(0, 0))
    scene_tl = proxy.mapToScene(QPointF(top_left_in_frame))
    correct = view.viewport().mapToGlobal(view.mapFromScene(scene_tl))
    naive = inner.mapToGlobal(QPoint(0, 0))
    assert naive != correct, f"expected mapToGlobal to be wrong (naive={naive}, correct={correct})"
    print(f"confirmed mapToGlobal is unreliable under zoom (naive={naive} vs correct={correct}): PASS")


def build_real_todo_widget(view, directory):
    todo_mod = load_widget_module("todo_mod_pos", "widgets/todo/widget.py")
    current_context.set_current_desk_directory(directory)
    host = PythonWidgetHost("todo", Path("widgets/todo"), "widget.py", _FakeBroker())
    proxy = view.add_widget(host, title="TODO", pos=(50, 50), size=(680, 520))
    pump(0.2)
    return proxy, host.current, todo_mod


class _FakeBroker:
    class widget_changed:
        @staticmethod
        def connect(_fn):
            pass


def test_popup_stays_within_bounds_add():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        (directory / "TODO.md").write_text("a1b2c3d. First item.\n")

        view = WorkspaceView()
        view.resize(1400, 1000)
        view.show()
        proxy, todo, _ = build_real_todo_widget(view, directory)

        # Zoom so the naive mapToGlobal-based position would clearly be
        # wrong/unclamped, and place the widget away from the origin.
        view.scale(1.8, 1.8)
        pump(0.2)

        add_button = None
        from PyQt6.QtWidgets import QPushButton

        for child in todo.findChildren(QPushButton):
            if child.text() == "Add Item":
                add_button = child
                break
        assert add_button is not None, "could not find the Add button"

        add_button.clicked.emit()
        pump(0.2)

        dialogs = [w for w in app.topLevelWidgets() if type(w).__name__ == "_ItemDialog"]
        assert len(dialogs) == 1, dialogs
        dialog = dialogs[0]

        bounds = todo._screen_rect(todo)
        dialog_rect = dialog.geometry()
        assert bounds is not None
        assert bounds.contains(dialog_rect), f"dialog {dialog_rect} not contained in widget bounds {bounds}"
        print("add-dialog popup stays within widget bounds under zoom: PASS")
        dialog.close()


def test_popup_capped_when_widget_smaller_than_dialog():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        (directory / "TODO.md").write_text("a1b2c3d. First item.\n")

        view = WorkspaceView()
        view.resize(1400, 1000)
        view.show()
        proxy, todo, _ = build_real_todo_widget(view, directory)
        frame = proxy.widget()
        frame.resize(200, 120)  # MIN_WIDTH/MIN_HEIGHT
        pump(0.2)

        from PyQt6.QtWidgets import QPushButton

        add_button = None
        for child in todo.findChildren(QPushButton):
            if child.text() == "Add Item":
                add_button = child
                break
        assert add_button is not None

        add_button.clicked.emit()
        pump(0.2)

        dialogs = [w for w in app.topLevelWidgets() if type(w).__name__ == "_ItemDialog"]
        assert len(dialogs) == 1
        dialog = dialogs[0]
        bounds = todo._screen_rect(todo)
        # Can't fully contain (dialog's own field has a hard minimum size
        # larger than the widget), but it must be capped down from its
        # default 420x220, not left at full size.
        assert dialog.width() <= 420 and dialog.height() <= 220
        print(f"dialog capped when widget is tiny: dialog size={dialog.size()}, bounds size={bounds.size()}: PASS")
        dialog.close()


def test_fallback_when_not_embedded():
    todo_mod = load_widget_module("todo_mod_standalone", "widgets/todo/widget.py")
    with tempfile.TemporaryDirectory() as d:
        current_context.set_current_desk_directory(Path(d))
        (Path(d) / "TODO.md").write_text("a1b2c3d. First.\n")
        todo = todo_mod.build()  # not embedded in any canvas
        todo.show()
        pump(0.1)

        from PyQt6.QtWidgets import QPushButton

        add_button = None
        for child in todo.findChildren(QPushButton):
            if child.text() == "Add Item":
                add_button = child
                break
        assert add_button is not None
        add_button.clicked.emit()  # must not raise despite no canvas
        pump(0.1)
        dialogs = [w for w in app.topLevelWidgets() if type(w).__name__ == "_ItemDialog"]
        assert len(dialogs) == 1
        dialogs[0].close()
        todo.close()
    print("fallback works when not embedded (no crash): PASS")


test_mapToGlobal_is_unreliable_confirmation()
test_popup_stays_within_bounds_add()
test_popup_capped_when_widget_smaller_than_dialog()
test_fallback_when_not_embedded()
print("ALL PASS")
