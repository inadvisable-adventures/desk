"""Verifies TODO `9585a5a`: a placed widget keeps its size at every zoom
level (the frame must not regrow because chrome or content minimums balloon),
and the Claude (Desk) widget's content fits its default size. Real
WorkspaceView and frames, headless."""

import importlib.util
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.window  # noqa: E402,F401  (must precede QApplication)

from PyQt6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget  # noqa: E402

app = QApplication(sys.argv)

from desk.shell.canvas import WorkspaceView  # noqa: E402

passed = 0
failed = 0
SCALES = [1.0, 0.5, 0.25, 0.12, 0.06, 0.03]


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


def pump(n=10):
    for _ in range(n):
        app.processEvents()


def _claude_desk_module():
    spec = importlib.util.spec_from_file_location("lz_cd", REPO_ROOT / "widgets" / "claude_desk" / "widget.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


claude_desk = _claude_desk_module()


def many_buttons():
    widget = QWidget()
    layout = QVBoxLayout(widget)
    for i in range(8):
        layout.addWidget(QPushButton(f"button {i}"))
    return widget


CASES = {"claude_desk": claude_desk.build, "many_buttons": many_buttons, "label": lambda: QLabel("hi")}
SIZES = [(480, 560), (300, 200)]


def test_size_is_stable_at_every_zoom():
    for name, make in CASES.items():
        for size in SIZES:
            view = WorkspaceView()
            view.resize(1200, 900)
            view.show()
            pump()
            content = make()
            content.widget_id = "x"
            proxy = view.add_widget(content, title=name, pos=(0, 0), size=size)
            pump()
            unstable = []
            for scale in SCALES:
                view._rescale(scale)
                pump()
                got = (round(proxy.size().width()), round(proxy.size().height()))
                if abs(got[0] - size[0]) > 2 or abs(got[1] - size[1]) > 2:
                    unstable.append((scale, got))
            check(f"{name} {size}: placed size holds at every zoom level (unstable: {unstable[:2]})", not unstable)


def test_frame_minimum_is_explicit():
    view = WorkspaceView()
    frame = view.add_widget(QLabel("x"), title="x").widget()
    check("the frame's own minimum size is explicitly tiny, not derived from its pages", frame.minimumSize().width() == 1 and frame.minimumSize().height() == 1)


def test_claude_desk_content_fits_its_default_width():
    widget = claude_desk.build()
    import json

    default_width = json.loads((REPO_ROOT / "widgets" / "claude_desk" / "widget.json").read_text())["default_size"]["width"]
    check(f"the widget's minimum width ({widget.minimumSizeHint().width()}px) fits its default {default_width}px frame", widget.minimumSizeHint().width() <= default_width)


def test_resize_still_works_after_zooming():
    view = WorkspaceView()
    view.resize(1200, 900)
    view.show()
    proxy = view.add_widget(QLabel("x"), title="x", pos=(0, 0), size=(300, 200))
    pump()
    view._rescale(0.1)
    pump()
    proxy.widget().resize(400, 260)
    pump()
    check("an explicit resize sticks (the fix doesn't pin the size)", (round(proxy.size().width()), round(proxy.size().height())) == (400, 260))


test_size_is_stable_at_every_zoom()
test_frame_minimum_is_explicit()
test_claude_desk_content_fits_its_default_width()
test_resize_still_works_after_zooming()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
