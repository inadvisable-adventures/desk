# TODO 93364f9: the [CHAT] titlebar button. Builds a real claude_desk
# PythonWidgetHost (exercising the real placement/instructions-file
# path) but swaps desk.claude_session.ClaudeSession for a recording
# _FakeSession before that widget is ever constructed -- see
# verify_claude_desk_widget.py's own docstring for why constructing a
# real ClaudeSession is harmless (no I/O until .start() is called) but
# letting a real .start() run would spawn a real background
# thread/network call. No live Claude API touched anywhere here.
import os
import sys
import tempfile
import uuid as uuid_mod
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.widget_frame  # noqa: E402  (imported before QApplication -- WebEngine ordering)
import desk.shell.canvas as canvas_mod  # noqa: E402
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402,F401

from PyQt6.QtCore import QPointF  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

import desk.claude_session as claude_session_mod  # noqa: E402
from desk.desks import Desk  # noqa: E402
from desk.event_mediator import EventMediator  # noqa: E402
from desk.hotreload import HotReloadBroker  # noqa: E402
from desk.schema_registry import SchemaRegistry  # noqa: E402
from desk.shell import current_context  # noqa: E402
from desk.shell.canvas import WorkspaceView  # noqa: E402
from desk.shell.widget_frame import _TitleBar  # noqa: E402
from desk.shell.window import CLAUDE_DESK_WIDGET_ID, DeskWindow  # noqa: E402
from desk.widgets import WidgetInfo  # noqa: E402

passed = 0
failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


# ---------- chrome visibility ----------


def test_chat_button_visibility():
    bar = _TitleBar("Test")
    bar.show()
    check("[CHAT] visible by default (unlocked, not popup, chrome not degraded)", bar.chat_button.isVisible())

    bar.set_locked(True)
    check("[CHAT] hidden while locked", not bar.chat_button.isVisible())
    bar.set_locked(False)

    bar.set_buttons_hidden(True)
    check("[CHAT] hidden when chrome degrades to title_only", not bar.chat_button.isVisible())
    bar.set_buttons_hidden(False)
    check("[CHAT] visible again once lock/degrade state clears", bar.chat_button.isVisible())

    popup_bar = _TitleBar("Popup", is_popup=True)
    popup_bar.show()
    check("[CHAT] never shown on a popup titlebar", not popup_bar.chat_button.isVisible())


test_chat_button_visibility()


def test_button_kinds_include_chat_and_error():
    check('"chat" is a recognized button kind', "chat" in canvas_mod._BUTTON_KINDS)
    check(
        '"error" is a recognized button kind (pre-existing gap, fixed alongside this item)',
        "error" in canvas_mod._BUTTON_KINDS,
    )


test_button_kinds_include_chat_and_error()


# ---------- fake window scaffolding (mirrors verify_widget_error_indicator.py) ----------


class _FakeHandle:
    token = "tok"

    def widget_url(self, widget_id):
        return f"http://fake/{widget_id}"


class _FakeWindow:
    def __init__(self, directory):
        self.current_desk = Desk(path=directory / "test.desk")
        self._widgets = {}
        self._handle = _FakeHandle()
        self.view = WorkspaceView()
        self.view.resize(800, 600)
        self.view.show()
        self._broker = HotReloadBroker()
        self._event_mediator = EventMediator()
        self._custom_widget_sources = {}
        self._custom_widget_definitions = {}
        self._custom_widget_content_hash = {}
        self._schema_registry = SchemaRegistry()


_FakeWindow._place_widget = DeskWindow._place_widget
_FakeWindow._chromium_profile_dir = DeskWindow._chromium_profile_dir
_FakeWindow._bind_claude_widget = DeskWindow._bind_claude_widget
_FakeWindow._bind_claude_desk_widget = DeskWindow._bind_claude_desk_widget
_FakeWindow._bind_external_indicator = DeskWindow._bind_external_indicator
_FakeWindow._bind_event_mediator = DeskWindow._bind_event_mediator
_FakeWindow._bind_error_indicator = DeskWindow._bind_error_indicator
_FakeWindow._check_schema_conflict = DeskWindow._check_schema_conflict
_FakeWindow._is_instance_currently_placed = DeskWindow._is_instance_currently_placed
_FakeWindow._notify_schema_conflict = DeskWindow._notify_schema_conflict
_FakeWindow._show_schema_conflict_popup = DeskWindow._show_schema_conflict_popup
_FakeWindow.find_frame_by_instance_id = DeskWindow.find_frame_by_instance_id
_FakeWindow._on_chat_button_clicked = DeskWindow._on_chat_button_clicked
_FakeWindow._place_widget_chat_about = DeskWindow._place_widget_chat_about
_FakeWindow._build_widget_chat_instructions = DeskWindow._build_widget_chat_instructions
_FakeWindow._write_claude_instructions_file = DeskWindow._write_claude_instructions_file


def _python_widget_info(directory, widget_id="ordinary_python", name="Ordinary Widget"):
    return WidgetInfo(
        id=widget_id, path=directory, kind="python", name=name,
        entry="widget.py", capabilities=[], default_size=(400, 300),
    )


TRIVIAL_WIDGET_PY = "from PyQt6.QtWidgets import QLabel\n\ndef build():\n    return QLabel('hi')\n"


def _write_widget_py(directory, body=TRIVIAL_WIDGET_PY):
    (directory / "widget.py").write_text(body)


class _FakeSignal:
    """Mirrors verify_claude_desk_titlebar_session_id.py's own helper --
    a real pyqtSignal-alike (connect/emit) without needing a real
    QObject/ClaudeSession underneath."""

    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def emit(self, *args):
        for slot in list(self._slots):
            slot(*args)


class _FakeSession:
    """A recording stand-in for desk.claude_session.ClaudeSession -- see
    this file's own top-of-module docstring for why swapping it in
    (before the claude_desk widget is ever built) rather than after is
    required here, unlike verify_claude_desk_widget.py's own
    swap-in-afterward trick. Needs every signal ClaudeDeskWidget.__init__
    connects to, since that runs against this fake directly."""

    def __init__(self):
        self.start_calls = []
        self.assistant_text = _FakeSignal()
        self.tool_use = _FakeSignal()
        self.tool_result = _FakeSignal()
        self.permission_request = _FakeSignal()
        self.turn_complete = _FakeSignal()
        self.session_error = _FakeSignal()
        self.task_event = _FakeSignal()
        self.connected = _FakeSignal()

    def start(self, session_id, resume, model, permission_mode, cwd, initial_prompt):
        self.start_calls.append((session_id, resume, model, permission_mode, cwd, initial_prompt))

    def set_permission_mode(self, mode):
        pass

    def stop(self):
        pass


def test_clicking_chat_button_resolves_via_hit_test():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        info = _python_widget_info(directory)
        _write_widget_py(directory)
        frame = win._place_widget(info.id, info, (0, 0), (400, 300), instance_id=uuid_mod.uuid4().hex[:8])

        button = frame._titlebar.chat_button
        global_pos = button.mapToGlobal(button.rect().center())
        viewport_pos = win.view.viewport().mapFromGlobal(global_pos)
        scene_pos = win.view.mapToScene(viewport_pos)
        view_pos_f = QPointF(win.view.mapFromScene(scene_pos))

        hit = win.view._hit_test_chrome(view_pos_f)
        check("hit-test resolves a click on [CHAT] to (frame, 'chat')", hit == (frame, "chat"))


test_clicking_chat_button_resolves_via_hit_test()


def test_on_chat_button_clicked_places_scoped_claude_desk_session():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        current_context.set_current_desk_directory(directory)
        try:
            win = _FakeWindow(directory)
            source_info = _python_widget_info(directory)
            _write_widget_py(directory)
            win._widgets[source_info.id] = source_info
            win._widgets[CLAUDE_DESK_WIDGET_ID] = WidgetInfo(
                id=CLAUDE_DESK_WIDGET_ID,
                path=REPO_ROOT / "widgets" / "claude_desk",
                kind="python",
                name="Claude (Desk)",
                entry="widget.py",
                capabilities=[],
                default_size=(480, 560),
            )

            source_instance_id = "11111111-1111-1111-1111-111111111111"
            source_frame = win._place_widget(
                source_info.id, source_info, (0, 0), (400, 300), instance_id=source_instance_id
            )

            with patch.object(claude_session_mod, "ClaudeSession", _FakeSession):
                win._on_chat_button_clicked(source_frame)

            placed = [f for f in win.view._frames if f.content.widget_id == CLAUDE_DESK_WIDGET_ID]
            check("exactly one new claude_desk frame was placed", len(placed) == 1)
            new_frame = placed[0]
            check(
                "placed to the right of the source frame",
                new_frame.graphicsProxyWidget().pos().x() > source_frame.graphicsProxyWidget().pos().x(),
            )

            instructions_files = list((directory / ".desk_temp").glob("chat-instructions-*.md"))
            check("exactly one chat-instructions file was written", len(instructions_files) == 1)
            text = instructions_files[0].read_text() if instructions_files else ""
            check("mentions the source widget's kind", f"`{source_info.id}`" in text)
            check("mentions the source widget's instance_id", source_instance_id in text)
            check("mentions the source widget's title", source_info.name in text)
            check("mentions the manifest path", f"widgets/{source_info.id}/widget.json" in text)
            check("mentions the entry path", f"widgets/{source_info.id}/widget.py" in text)
            check("mentions desk_list_widget_instances", "desk_list_widget_instances" in text)
            check("mentions desk.state and where schemas live", "desk.state" in text and "desk-schemas" in text)
            check("mentions Installed Jobs infrastructure", "desk_run_installed_job" in text)

            content = new_frame.content.current
            check("a real ClaudeDeskWidget was built", content is not None and hasattr(content, "start_session"))
            started = getattr(content, "_session", None)
            check(
                "the fake session's start() ran with a pointer to the instructions file (no live API touched)",
                isinstance(started, _FakeSession)
                and len(started.start_calls) == 1
                and "chat-instructions-" in started.start_calls[0][5],
            )
        finally:
            current_context.set_current_desk_directory(None)


test_on_chat_button_clicked_places_scoped_claude_desk_session()


def test_on_chat_button_clicked_noop_if_widget_kind_unknown():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        info = _python_widget_info(directory)
        _write_widget_py(directory)
        win._widgets[info.id] = info
        frame = win._place_widget(info.id, info, (0, 0), (400, 300), instance_id=uuid_mod.uuid4().hex[:8])
        # Simulate the widget kind having gone missing from the catalog
        # between placement and click -- an already-broken state this
        # button can't usefully do anything about.
        del win._widgets[info.id]
        before = len(win.view._frames)
        win._on_chat_button_clicked(frame)
        check("no crash and nothing placed when the widget kind isn't in the catalog", len(win.view._frames) == before)


test_on_chat_button_clicked_noop_if_widget_kind_unknown()


print(f"\n{passed} passed, {failed} failed")
if failed:
    sys.exit(1)
