import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from desk.shell.widget_spawn_menu import WidgetSpawnMenu  # noqa: E402
from desk.shell.window import DeskWindow, MARKDOWN_WIDGET_ID, SCRATCH_WIDGET_ID  # noqa: E402
from desk.temp_ui import TEMP_UI_DIRNAME  # noqa: E402

from PyQt6.QtCore import QMimeData, QPointF  # noqa: E402
from PyQt6.QtGui import QImage  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
clipboard = QApplication.clipboard()


def test_menu_shows_paste_item_when_clipboard_has_text():
    clipboard.setText("hello from clipboard")
    menu = WidgetSpawnMenu({})
    assert menu._paste_item is not None
    assert menu._visible_entries()[0] is menu._paste_item
    received = []
    menu.paste_requested.connect(lambda: received.append(True))
    menu._activate_item(menu._paste_item)
    assert received == [True]
    print("menu shows Paste item with clipboard text, activates it: PASS")


def test_menu_hides_paste_item_when_clipboard_empty():
    clipboard.clear()
    menu = WidgetSpawnMenu({})
    assert menu._paste_item is None
    print("menu has no Paste item with empty clipboard: PASS")


class _FakeWidgetInfo:
    def __init__(self, default_size=(100, 100)):
        self.default_size = default_size


class _FakeContent:
    def __init__(self):
        self.set_file_calls = []


class _FakeWindow:
    def __init__(self, directory):
        self.current_desk = type("D", (), {"directory": directory})()
        self._widgets = {
            MARKDOWN_WIDGET_ID: _FakeWidgetInfo(),
            SCRATCH_WIDGET_ID: _FakeWidgetInfo(),
        }
        self.opened = []
        self.bound = []
        self.recorded_writes = []
        self._custom_widget_definitions = {}  # TODO 91b3f42

        class _FakeTempUiManager:
            def __init__(self, outer):
                self._outer = outer

            def record_own_write(self, path, text):
                self._outer.recorded_writes.append((path, text))

        self._temp_ui_manager = _FakeTempUiManager(self)

    def open_widget_content(self, widget_id, pos=None, size=None, instance_id=None):
        self.opened.append((widget_id, pos, size, instance_id))
        return _FakeContent()

    def _bind_temp_ui_content(self, content, path, directory):
        self.bound.append((content, path, directory))


_FakeWindow._on_paste_requested = DeskWindow._on_paste_requested
_FakeWindow._paste_text_as_temp_ui = DeskWindow._paste_text_as_temp_ui
_FakeWindow._paste_image_as_project_file = DeskWindow._paste_image_as_project_file
_FakeWindow._temp_ui_widget_id_for = DeskWindow._temp_ui_widget_id_for


def test_paste_markdown_text():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        (directory / TEMP_UI_DIRNAME).mkdir()
        win = _FakeWindow(directory)

        mime = QMimeData()
        mime.setText("# My Notes\nSome content")
        mime.setData("text/markdown", b"# My Notes\nSome content")
        clipboard.setMimeData(mime)

        win._on_paste_requested(QPointF(10.0, 20.0))

        assert len(win.opened) == 1
        widget_id, pos, size, instance_id = win.opened[0]
        assert widget_id == MARKDOWN_WIDGET_ID
        assert pos == (10.0, 20.0)

        written_path = directory / TEMP_UI_DIRNAME / instance_id
        text = written_path.read_text()
        assert text.startswith("Markdown My Notes\n"), text
        assert "Some content" in text
        assert win.recorded_writes == [(written_path, text)]
        assert len(win.bound) == 1
    print("paste with text/markdown flavor writes Markdown DSL file and opens it: PASS")


def test_paste_plain_text():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        (directory / TEMP_UI_DIRNAME).mkdir()
        win = _FakeWindow(directory)

        clipboard.setText("just some plain text, not markdown")

        win._on_paste_requested(QPointF(0.0, 0.0))

        assert len(win.opened) == 1
        widget_id, pos, size, instance_id = win.opened[0]
        assert widget_id == SCRATCH_WIDGET_ID
        written_path = directory / TEMP_UI_DIRNAME / instance_id
        text = written_path.read_text()
        assert text.startswith("Scratch just some plain text, not markdown\n"), text
    print("plain clipboard text (no text/markdown flavor) writes Scratch DSL file: PASS")


def test_paste_image_saves_file_no_widget_opened():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        win = _FakeWindow(directory)

        image = QImage(4, 4, QImage.Format.Format_RGB32)
        image.fill(0xFF0000)
        clipboard.setImage(image)

        win._on_paste_requested(QPointF(0.0, 0.0))

        assert win.opened == []
        pasted_files = list(directory.glob("PASTED-ITEM-*.png"))
        assert len(pasted_files) == 1, pasted_files
    print("paste with clipboard image saves a project file, opens no widget: PASS")


def test_empty_clipboard_is_noop():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        clipboard.clear()
        win._on_paste_requested(QPointF(0.0, 0.0))
        assert win.opened == []
        assert list(directory.glob("PASTED-ITEM-*")) == []
    print("empty clipboard is a no-op: PASS")


test_menu_shows_paste_item_when_clipboard_has_text()
test_menu_hides_paste_item_when_clipboard_empty()
test_paste_markdown_text()
test_paste_plain_text()
test_paste_image_saves_file_no_widget_opened()
test_empty_clipboard_is_noop()
print("ALL PASS")
