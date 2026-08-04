# DISABLED (TODO 9bc522b): this test places a real ClaudeWidget and
# spawns a real `claude` CLI process (via DeskWindow.start_discussion
# -> ClaudeWidget.start_session -> a real bash PTY that execs claude)
# -- real network calls, real API cost/quota, and outcomes that depend
# on the live model's actual behavior/output rendering rather than
# fixed local logic. Split out of
# tests/verify/verify_questions_discuss_button.py (which keeps its
# other, API-free test -- the Discuss button's hover/click UI, driven
# through a patched discuss-starter hook -- running normally) so only
# the actual live-API-touching coverage is disabled. Left disabled
# until TODO 9bc522b decides how coverage like this should actually be
# integrated (run occasionally by hand, mock the claude CLI/Agent SDK
# layer, or some combination) rather than always running as part of
# the normal sweep. Still a real, working, non-mocked test -- run it
# directly (`.venv/bin/python3
# tests/verify/disabled_verify_questions_discuss_button_claude_api.py`)
# when you want this coverage (needs real Claude API access/auth, and
# the `claude` CLI on PATH).
import os
import sys
import tempfile
import time
from pathlib import Path

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
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)


def poll_until(predicate, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.05)
    return False


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
_FakeWindow._bind_error_indicator = DeskWindow._bind_error_indicator
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


test_start_discussion_places_claude_widget_with_source_and_text()
print("ALL PASS")
