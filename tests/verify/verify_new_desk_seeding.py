import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from desk.shell.window import DeskWindow, MARKDOWN_WIDGET_ID, SCRATCH_WIDGET_ID  # noqa: E402

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)


class _FakeWidgetInfo:
    def __init__(self, default_size=(100, 100)):
        self.default_size = default_size


class _FakeContent:
    def __init__(self):
        self.set_file_calls = []
        self.label = None
        self.body_text = None
        self.body = self

    def set_file(self, path):
        self.set_file_calls.append(path)

    def set_label(self, text):
        self.label = text

    def setPlainText(self, text):
        self.body_text = text


class _FakeWindow:
    def __init__(self, widgets=None):
        self._widgets = widgets if widgets is not None else {
            MARKDOWN_WIDGET_ID: _FakeWidgetInfo(),
            SCRATCH_WIDGET_ID: _FakeWidgetInfo(),
        }
        self.opened = []
        self._next_content = None

    def open_widget_content(self, widget_id, pos=None, size=None, instance_id=None):
        self.opened.append((widget_id, pos, size))
        self._next_content = _FakeContent()
        return self._next_content


_FakeWindow._seed_new_desk_widgets = DeskWindow._seed_new_desk_widgets


def make_desk(directory, name="MyProject"):
    return type("D", (), {"directory": directory, "name": name})()


def test_readme_present_opens_markdown():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        (directory / "README.md").write_text("# hi")
        win = _FakeWindow()
        win._seed_new_desk_widgets(make_desk(directory))
        assert [op[0] for op in win.opened] == [MARKDOWN_WIDGET_ID]
        assert win._next_content.set_file_calls == [directory / "README.md"]
    print("README.md present: opens markdown widget with set_file: PASS")


def test_no_readme_seeds_scratch():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        win = _FakeWindow()
        win._seed_new_desk_widgets(make_desk(directory, name="Widgets"))
        assert [op[0] for op in win.opened] == [SCRATCH_WIDGET_ID]
        content = win._next_content
        assert content.label == "Widgets README"
        assert content.body_text == "# Widgets README\n\n## What this project is about or exploring...\n"
    print("no README.md: seeds scratch widget with template: PASS")


def test_missing_widget_kinds_are_noop():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        win = _FakeWindow(widgets={})
        win._seed_new_desk_widgets(make_desk(directory))
        assert win.opened == []
    with tempfile.TemporaryDirectory() as d2:
        directory2 = Path(d2)
        (directory2 / "README.md").write_text("hi")
        win2 = _FakeWindow(widgets={})
        win2._seed_new_desk_widgets(make_desk(directory2))
        assert win2.opened == []
    print("missing widget kinds in catalog: no-op, no crash: PASS")


test_readme_present_opens_markdown()
test_no_readme_seeds_scratch()
test_missing_widget_kinds_are_noop()
print("ALL PASS")
