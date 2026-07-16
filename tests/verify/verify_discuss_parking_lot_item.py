import importlib.util
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from desk.desks import Desk  # noqa: E402
from desk.event_mediator import EventMediator  # noqa: E402
from desk.hotreload import HotReloadBroker  # noqa: E402
from desk.shell import current_context  # noqa: E402
from desk.shell.canvas import WorkspaceView  # noqa: E402
from desk.shell.window import DeskWindow  # noqa: E402
from desk.temp_ui import (  # noqa: E402
    DISCUSS_PARKING_LOT_ITEM_KEYWORD,
    DISCUSS_PARKING_LOT_ITEM_DOC_FILENAME,
    SPLIT_DOC_CONTENT,
    TEMPUI_DOC_VERSION,
    TEMP_UI_DIRNAME,
    detect_temp_ui_kind,
    parse_discuss_parking_lot_item,
)
from desk.widgets import WidgetInfo

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


# ---------- pure parsing/doc-content checks ----------


def test_detect_and_parse():
    # TODO 624ff3a: the second line is now `Line <N>` (a reference into
    # PARKINGLOT.md), not the item's own embedded text -- parse returns
    # (label, line_number), not (label, full_body_text).
    text = "DiscussParkingLotItem A way to end a session\nLine 42"
    assert detect_temp_ui_kind(text) == "discuss_parking_lot_item"
    parsed = parse_discuss_parking_lot_item(text)
    assert parsed == ("A way to end a session", 42)
    assert parse_discuss_parking_lot_item("Scratch hi\nbody") is None
    assert parse_discuss_parking_lot_item("DiscussParkingLotItem A way to end a session\nnot a line ref") is None
    print("detect_temp_ui_kind/parse_discuss_parking_lot_item: PASS")


def test_doc_version_and_split_file():
    assert TEMPUI_DOC_VERSION >= 5
    content = SPLIT_DOC_CONTENT[DISCUSS_PARKING_LOT_ITEM_DOC_FILENAME]
    assert DISCUSS_PARKING_LOT_ITEM_KEYWORD in content
    assert "PARKINGLOT.md" in content
    print("TEMPUI_DOC_VERSION bumped + tempui-discuss-parking-lot-item.md content present: PASS")


# ---------- ClaudeWidget.start_session appends extra_instructions on fresh launch only ----------


def test_claude_widget_start_session_appends_extra_instructions():
    claude_mod = load_widget_module("discuss_claude_widget_verify_mod", "widgets/claude/widget.py")
    widget = claude_mod.build()
    try:
        marker = "PARKING_LOT_ITEM_MARKER_TEXT"
        widget.start_session(
            "11111111-1111-1111-1111-111111111111",
            resume=False,
            extra_instructions=f"\n\nLet's discuss an item from PARKINGLOT.md: {marker}",
        )
        found = poll_until(lambda: marker in widget.toPlainText())
        assert found, widget.toPlainText()
        text = widget.toPlainText()
        assert "You are running inside of Desk" in text
        # shlex.quote escapes the apostrophe in "Let's" as '"'"' when the
        # whole prompt is single-quoted for the shell -- check the
        # unambiguous, apostrophe-free part of the phrase instead.
        assert "discuss an item from PARKINGLOT.md" in text
    finally:
        widget._process.terminate()
    print("ClaudeWidget.start_session: extra_instructions appended to the fresh-launch prompt: PASS")


def test_claude_widget_start_session_resume_ignores_extra_instructions():
    claude_mod = load_widget_module("discuss_claude_widget_resume_verify_mod", "widgets/claude/widget.py")
    widget = claude_mod.build()
    try:
        marker = "SHOULD_NOT_APPEAR_ON_RESUME"
        widget.start_session(
            "22222222-2222-2222-2222-222222222222", resume=True, extra_instructions=f"discuss {marker}"
        )
        found = poll_until(lambda: "--resume" in widget.toPlainText())
        assert found, widget.toPlainText()
        assert marker not in widget.toPlainText()
    finally:
        widget._process.terminate()
    print("ClaudeWidget.start_session: resume=True ignores extra_instructions: PASS")


# ---------- DeskWindow._activate_temp_ui dispatches a DiscussParkingLotItem file to a claude widget ----------


class _FakeHandle:
    def widget_url(self, widget_id):
        return f"http://fake/{widget_id}"

    token = "tok"


class _FakeWindow:
    def __init__(self, directory, widgets):
        self.current_desk = Desk(path=directory / "test.desk")
        self._widgets = widgets
        self._handle = _FakeHandle()
        self._custom_widget_definitions = {}
        self._custom_widget_sources = {}
        self._custom_widget_content_hash = {}
        self.view = WorkspaceView()
        self.view.resize(800, 600)
        self.view.show()
        self._broker = HotReloadBroker()
        self._event_mediator = EventMediator()


_FakeWindow._place_widget = DeskWindow._place_widget
_FakeWindow._bind_event_mediator = DeskWindow._bind_event_mediator
_FakeWindow._bind_claude_widget = DeskWindow._bind_claude_widget
_FakeWindow._bind_external_indicator = DeskWindow._bind_external_indicator
_FakeWindow._temp_ui_widget_id_for = DeskWindow._temp_ui_widget_id_for
_FakeWindow._activate_temp_ui = DeskWindow._activate_temp_ui
_FakeWindow._place_discuss_claude_widget = DeskWindow._place_discuss_claude_widget
_FakeWindow._write_discuss_instructions_file = DeskWindow._write_discuss_instructions_file
_FakeWindow.find_frame_by_instance_id = DeskWindow.find_frame_by_instance_id


def test_activate_temp_ui_places_claude_widget_with_item_text():
    # TODO 624ff3a/TODO 51be2bc: the tempui file references a line
    # number (not embedded item text), and the actual discussion
    # instructions are written to a standalone .desk_temp/
    # discuss-instructions-*.md file rather than spliced into the
    # prompt -- the prompt just points at that file.
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        current_context.set_current_desk_directory(directory)
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

        uuid_str = "550e8400-e29b-41d4-a716-446655440000"
        tempui_path = directory / uuid_str
        tempui_path.write_text("DiscussParkingLotItem A way to end a session\nLine 42\n")

        win._activate_temp_ui(tempui_path)

        frame = win.find_frame_by_instance_id(uuid_str)
        assert frame is not None, "expected a claude widget frame placed with the tempui file's own uuid"

        found = poll_until(lambda: "Read the file at" in frame.content.current.toPlainText())
        assert found, frame.content.current.toPlainText()
        text = frame.content.current.toPlainText()
        assert "Read the file at" in text
        assert "discuss-instructions-" in text

        instructions_files = list((directory / TEMP_UI_DIRNAME).glob("discuss-instructions-*.md"))
        assert len(instructions_files) == 1, instructions_files
        instructions_text = instructions_files[0].read_text()
        assert "line 42 of PARKINGLOT.md" in instructions_text
        assert "Have this discussion here" in instructions_text

        # Clicking the (now-existing) notification again just centers the
        # view -- doesn't re-place or re-send anything.
        win._activate_temp_ui(tempui_path)
        assert win.find_frame_by_instance_id(uuid_str) is frame

        frame.content.current._process.terminate()
    current_context.set_current_desk_directory(None)
    print(
        "DeskWindow._activate_temp_ui: DiscussParkingLotItem places a new claude widget "
        "(instance_id == tempui uuid) whose session is pointed at a line-number reference "
        "via a standalone discuss-instructions file: PASS"
    )


test_detect_and_parse()
test_doc_version_and_split_file()
test_claude_widget_start_session_appends_extra_instructions()
test_claude_widget_start_session_resume_ignores_extra_instructions()
test_activate_temp_ui_places_claude_widget_with_item_text()
print("ALL PASS")
