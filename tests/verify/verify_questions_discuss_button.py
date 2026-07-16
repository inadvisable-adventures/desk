import importlib.util
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from desk.shell import current_context  # noqa: E402
from desk.shell.window import DeskWindow  # noqa: E402
from desk.desks import Desk  # noqa: E402
from desk.event_mediator import EventMediator  # noqa: E402
from desk.hotreload import HotReloadBroker  # noqa: E402
from desk.shell.canvas import WorkspaceView  # noqa: E402
from desk.temp_ui import TEMP_UI_DIRNAME  # noqa: E402
from desk.widgets import WidgetInfo  # noqa: E402
from PyQt6.QtCore import QEvent, QPoint  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)


def load_widget_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def poll_until(predicate, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.05)
    return False


# ---------- QuestionsWidget's Discuss button ----------


def test_discuss_button_shows_on_hover_and_calls_starter():
    questions_mod = load_widget_module("questions_discuss_verify_mod", "widgets/questions/widget.py")
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        (directory / "QUESTIONS.md").write_text(
            "# Questions with optional answers\n\n"
            "## TODO `9743419`: First question\n"
            "Should we use approach A or B?\n"
            "(Answer: )\n"
        )
        with patch.object(questions_mod.current_context, "get_current_desk_directory", return_value=directory):
            widget = questions_mod.build()
            widget.resize(500, 400)
            widget.show()
            app.processEvents()

            assert widget._list.count() == 1
            list_item = widget._list.item(0)
            entry = list_item.data(questions_mod.ENTRY_ROLE)
            assert "First question" in entry.raw_text
            assert "TODO" in entry.raw_text
            assert "(Answer: )" in entry.raw_text

            assert widget._discuss_button.isHidden()
            widget._on_item_entered(list_item)
            assert widget._discuss_button.isVisible()
            assert widget._discuss_item is list_item

            calls = []
            recorded_starter = lambda source_label, item_text: calls.append((source_label, item_text))
            with patch.object(current_context, "get_discuss_starter", return_value=recorded_starter):
                widget._discuss_hovered_entry()
            assert calls == [("QUESTIONS.md", entry.raw_text)]
            # Clicking hides the button again (mirrors the Plan button's
            # own hide-after-open behavior).
            assert widget._discuss_button.isHidden()

            # Leaving the list view hides the button too.
            widget._on_item_entered(list_item)
            assert widget._discuss_button.isVisible()
            widget.eventFilter(widget._list.viewport(), QEvent(QEvent.Type.Leave))
            assert widget._discuss_button.isHidden()
    print("QuestionsWidget: Discuss button shows on hover, calls the discuss-starter hook with "
          "(QUESTIONS.md, entry.raw_text), hides on click/mouse-leave: PASS")


# ---------- DeskWindow._place_discuss_claude_widget / start_discussion ----------


class _FakeHandle:
    def widget_url(self, widget_id):
        return f"http://fake/{widget_id}"

    token = "tok"


class _FakeWindow:
    def __init__(self, directory, widgets):
        self.current_desk = Desk(path=directory / "test.desk")
        self._widgets = widgets
        self._handle = _FakeHandle()
        self.view = WorkspaceView()
        self.view.resize(800, 600)
        self.view.show()
        self._broker = HotReloadBroker()
        self._custom_widget_sources = {}
        self._custom_widget_content_hash = {}
        self._event_mediator = EventMediator()


_FakeWindow._place_widget = DeskWindow._place_widget
_FakeWindow._bind_event_mediator = DeskWindow._bind_event_mediator
_FakeWindow._bind_claude_widget = DeskWindow._bind_claude_widget
_FakeWindow._bind_external_indicator = DeskWindow._bind_external_indicator
_FakeWindow._place_discuss_claude_widget = DeskWindow._place_discuss_claude_widget
_FakeWindow._write_discuss_instructions_file = DeskWindow._write_discuss_instructions_file
_FakeWindow.start_discussion = DeskWindow.start_discussion
_FakeWindow.find_frame_by_instance_id = DeskWindow.find_frame_by_instance_id


def test_start_discussion_places_claude_widget_with_source_and_text():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        widget_info = WidgetInfo(
            id="claude",
            path=Path("widgets/claude"),
            kind="python",
            name="Claude",
            entry="widget.py",
            capabilities=[],
            default_size=(700, 500),
        )
        win = _FakeWindow(directory, widgets={"claude": widget_info})
        current_context.set_current_desk_directory(directory)

        # TODO 51be2bc: the actual instructions (including item_text)
        # are written to a standalone .desk_temp/discuss-instructions
        # -*.md file, not spliced into the launch prompt -- the prompt
        # just points at that file.
        marker = "QUESTIONS_WIDGET_DISCUSS_MARKER"
        win.start_discussion("QUESTIONS.md", marker)

        found = poll_until(lambda: len(win.view._frames) == 1)
        assert found
        frame = win.view._frames[0]
        found = poll_until(lambda: "Read the file at" in frame.content.current.toPlainText())
        assert found, frame.content.current.toPlainText()
        text = frame.content.current.toPlainText()
        assert "Read the file at" in text
        assert "discuss-instructions-" in text

        instructions_files = list((directory / TEMP_UI_DIRNAME).glob("discuss-instructions-*.md"))
        assert len(instructions_files) == 1, instructions_files
        instructions_text = instructions_files[0].read_text()
        assert "an item from QUESTIONS.md" in instructions_text
        assert marker in instructions_text

        frame.content.current._process.terminate()
    current_context.set_current_desk_directory(None)
    print("DeskWindow.start_discussion: places a new claude widget pointed at a "
          "discuss-instructions file containing the given source_label/item_text: PASS")


test_discuss_button_shows_on_hover_and_calls_starter()
test_start_discussion_places_claude_widget_with_source_and_text()
print("ALL PASS")
