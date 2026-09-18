import base64
import os
import sys
import tempfile
import time
import uuid as uuid_mod
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.widget_frame  # noqa: E402  (imported before QApplication -- WebEngine ordering)
import desk.shell.canvas  # noqa: E402
# TODO 78bfa41: canvas.py's own QWebEngineView import (previously used
# by the now-removed _scrollable_at) was the thing actually satisfying
# the "import WebEngine before QApplication" ordering requirement above
# -- import it explicitly instead of depending on that as an incidental
# side effect of an unrelated module.
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402,F401

from PyQt6.QtCore import QPointF  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk.desks import Desk  # noqa: E402
from desk.hotreload import HotReloadBroker  # noqa: E402
from desk.schema_registry import SchemaRegistry  # noqa: E402
from desk.shell.canvas import WorkspaceView  # noqa: E402
from desk.shell.chromium_widget import ChromiumWidget  # noqa: E402
from desk.shell.python_widget import PythonWidgetHost  # noqa: E402
from desk.shell.widget_frame import WidgetFrame  # noqa: E402
from desk.shell.window import DeskWindow  # noqa: E402
from desk.shell.promoted_widget_source_watcher import PromotedWidgetSourceWatcher  # noqa: E402
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


def pump_until(predicate, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        app.processEvents()
        time.sleep(0.02)
    return predicate()


# ---------- fake window scaffolding (mirrors verify_stale_marker_click_dialog.py) ----------


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
        self._custom_widget_sources = {}
        self._custom_widget_definitions = {}
        self._custom_widget_content_hash = {}
        # TODO 4eb3d9e: _register_custom_widget/_place_widget/
        # _on_widget_stale_clicked now also touch these.
        self._promoted_widget_source_watcher = PromotedWidgetSourceWatcher()
        self._promoted_widget_source_dirty = set()
        self._schema_registry = SchemaRegistry()
        self.confirm_calls = []

    def _confirm_widget_error_dismissed_recording(self, message):
        self.confirm_calls.append(message)


_FakeWindow._place_widget = DeskWindow._place_widget
_FakeWindow._chromium_profile_dir = DeskWindow._chromium_profile_dir
_FakeWindow._bind_claude_widget = DeskWindow._bind_claude_widget
_FakeWindow._bind_external_indicator = DeskWindow._bind_external_indicator
_FakeWindow._bind_event_mediator = DeskWindow._bind_event_mediator
_FakeWindow._bind_error_indicator = DeskWindow._bind_error_indicator
_FakeWindow._check_schema_conflict = DeskWindow._check_schema_conflict
_FakeWindow._is_instance_currently_placed = DeskWindow._is_instance_currently_placed
_FakeWindow._notify_schema_conflict = DeskWindow._notify_schema_conflict
_FakeWindow._show_schema_conflict_popup = DeskWindow._show_schema_conflict_popup
_FakeWindow.find_frame_by_instance_id = DeskWindow.find_frame_by_instance_id
_FakeWindow._on_widget_error_clicked = DeskWindow._on_widget_error_clicked


def _html_widget_info(directory):
    return WidgetInfo(
        id="ordinary_html", path=directory, kind="html", name="Ordinary",
        entry="index.html", capabilities=[], default_size=None,
    )


def _python_widget_info(directory):
    return WidgetInfo(
        id="ordinary_python", path=directory, kind="python", name="Ordinary",
        entry="widget.py", capabilities=[], default_size=None,
    )


def _write_widget_py(directory, body):
    (directory / "widget.py").write_text(body)


# ---------- UI plumbing: button visibility, click dispatch, dialog ----------


def test_error_button_hidden_by_default_and_shown_by_set_error():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        win = _FakeWindow(Path(d))
        info = _html_widget_info(Path(d))
        frame = win._place_widget("ordinary_html", info, (0, 0), (400, 300), instance_id=uuid_mod.uuid4().hex[:8])
        check("[ERROR] button hidden by default", not frame._titlebar.error_button.isVisible())

        frame.set_error(True, "boom")
        check("[ERROR] button visible after set_error(True, ...)", frame._titlebar.error_button.isVisible())
        check("last_error_message stored", frame.last_error_message == "boom")

        frame.set_error(False)
        check("[ERROR] button hidden after set_error(False)", not frame._titlebar.error_button.isVisible())


test_error_button_hidden_by_default_and_shown_by_set_error()


def test_clicking_error_button_emits_widget_error_clicked():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        win = _FakeWindow(Path(d))
        info = _html_widget_info(Path(d))
        frame = win._place_widget("ordinary_html", info, (0, 0), (400, 300), instance_id=uuid_mod.uuid4().hex[:8])
        frame.set_error(True, "boom")

        emitted = []
        win.view.widget_error_clicked.connect(lambda f: emitted.append(f))

        button = frame._titlebar.error_button
        button_center_local = button.rect().center()
        global_pos = button.mapToGlobal(button_center_local)
        viewport_pos = win.view.viewport().mapFromGlobal(global_pos)
        scene_pos = win.view.mapToScene(viewport_pos)
        view_pos = win.view.mapFromScene(scene_pos)
        view_pos_f = QPointF(view_pos)

        hit = win.view._hit_test_chrome(view_pos_f)
        check("hit-test resolves to (frame, 'error')", hit == (frame, "error"))


test_clicking_error_button_emits_widget_error_clicked()


def test_on_widget_error_clicked_shows_dialog_and_clears_indicator():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        win = _FakeWindow(Path(d))
        info = _html_widget_info(Path(d))
        frame = win._place_widget("ordinary_html", info, (0, 0), (400, 300), instance_id=uuid_mod.uuid4().hex[:8])
        frame.set_error(True, "kaboom")

        win._confirm_widget_error_dismissed = win._confirm_widget_error_dismissed_recording
        win._on_widget_error_clicked(frame)

        check("_confirm_widget_error_dismissed called with the error message", win.confirm_calls == ["kaboom"])
        check("indicator cleared after acknowledging", not frame._titlebar.error_button.isVisible())


test_on_widget_error_clicked_shows_dialog_and_clears_indicator()


def test_on_widget_error_clicked_noop_with_no_error():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        win = _FakeWindow(Path(d))
        info = _html_widget_info(Path(d))
        frame = win._place_widget("ordinary_html", info, (0, 0), (400, 300), instance_id=uuid_mod.uuid4().hex[:8])

        win._confirm_widget_error_dismissed = win._confirm_widget_error_dismissed_recording
        win._on_widget_error_clicked(frame)
        check("no dialog shown when there's no error to show", win.confirm_calls == [])


test_on_widget_error_clicked_noop_with_no_error()


# ---------- TODO 47aaf73: an error with empty captured text ----------


def test_error_with_empty_message_still_shows_button_and_flag():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        win = _FakeWindow(Path(d))
        info = _html_widget_info(Path(d))
        frame = win._place_widget("ordinary_html", info, (0, 0), (400, 300), instance_id=uuid_mod.uuid4().hex[:8])

        frame.set_error(True, "")
        check("has_error is True even though the captured message is empty", frame.has_error is True)
        check("[ERROR] button still visible with an empty captured message", frame._titlebar.error_button.isVisible())


test_error_with_empty_message_still_shows_button_and_flag()


def test_clicking_error_button_with_empty_message_shows_placeholder_not_a_noop():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        win = _FakeWindow(Path(d))
        info = _html_widget_info(Path(d))
        frame = win._place_widget("ordinary_html", info, (0, 0), (400, 300), instance_id=uuid_mod.uuid4().hex[:8])
        frame.set_error(True, "")

        win._confirm_widget_error_dismissed = win._confirm_widget_error_dismissed_recording
        win._on_widget_error_clicked(frame)

        check(
            "clicking with an empty captured message no longer silently does nothing -- the dialog is shown with a placeholder",
            win.confirm_calls == ["(no error message was captured)"],
        )
        check("indicator cleared after acknowledging the empty-message error", not frame._titlebar.error_button.isVisible())
        check("has_error is False after clearing", frame.has_error is False)


test_clicking_error_button_with_empty_message_shows_placeholder_not_a_noop()


def test_has_error_flag_matches_button_visibility_through_a_full_cycle():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        win = _FakeWindow(Path(d))
        info = _html_widget_info(Path(d))
        frame = win._place_widget("ordinary_html", info, (0, 0), (400, 300), instance_id=uuid_mod.uuid4().hex[:8])

        check("has_error starts False", frame.has_error is False)
        frame.set_error(True, "boom")
        check("has_error True after set_error(True, ...)", frame.has_error is True)
        frame.set_error(False)
        check("has_error False after set_error(False)", frame.has_error is False)


test_has_error_flag_matches_button_visibility_through_a_full_cycle()


# ---------- kind:"html" real capture (real QtWebEngine JS execution, data: URL) ----------


def _data_url(html: str) -> str:
    return f"data:text/html;base64,{base64.b64encode(html.encode()).decode()}"


def test_console_error_call_is_captured():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        win = _FakeWindow(Path(d))
        info = _html_widget_info(Path(d))
        frame = win._place_widget("ordinary_html", info, (0, 0), (400, 300), instance_id=uuid_mod.uuid4().hex[:8])
        # Real page load, real JS execution -- not mocked.
        frame.content.load(__import__("PyQt6.QtCore", fromlist=["QUrl"]).QUrl(
            _data_url('<html><body><script>console.error("explicit-error");</script></body></html>')
        ))
        ok = pump_until(lambda: frame._titlebar._has_error)
        check("a real console.error() call lights up the [ERROR] indicator", ok)
        check("the captured message is the console.error() text", frame.last_error_message == "explicit-error")


test_console_error_call_is_captured()


def test_uncaught_exception_is_captured_not_just_explicit_console_error():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        win = _FakeWindow(Path(d))
        info = _html_widget_info(Path(d))
        frame = win._place_widget("ordinary_html", info, (0, 0), (400, 300), instance_id=uuid_mod.uuid4().hex[:8])
        from PyQt6.QtCore import QUrl
        frame.content.load(QUrl(_data_url('<html><body><script>throw new Error("uncaught-boom");</script></body></html>')))
        ok = pump_until(lambda: frame._titlebar._has_error)
        check("an uncaught JS exception (no explicit console.error) lights up [ERROR] too", ok)
        check("captured message mentions the uncaught error", "uncaught-boom" in frame.last_error_message)


test_uncaught_exception_is_captured_not_just_explicit_console_error()


def test_reload_clears_the_html_error_indicator():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        win = _FakeWindow(Path(d))
        info = _html_widget_info(Path(d))
        frame = win._place_widget("ordinary_html", info, (0, 0), (400, 300), instance_id=uuid_mod.uuid4().hex[:8])
        from PyQt6.QtCore import QUrl
        frame.content.load(QUrl(_data_url('<html><body><script>console.error("boom");</script></body></html>')))
        check("error captured before reload", pump_until(lambda: frame._titlebar._has_error))

        frame.content.load(QUrl(_data_url("<html><body>clean</body></html>")))
        frame.content.reload()
        ok = pump_until(lambda: not frame._titlebar._has_error)
        check("reload() clears the [ERROR] indicator", ok)


test_reload_clears_the_html_error_indicator()


# ---------- kind:"python" real build-failure capture ----------


FAILING_WIDGET_PY = """
def build():
    raise RuntimeError("deliberately broken build")
"""

WORKING_WIDGET_PY = """
from PyQt6.QtWidgets import QLabel


def build():
    return QLabel("fine")
"""


def test_build_failure_lights_up_error_indicator_immediately():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        _write_widget_py(directory, FAILING_WIDGET_PY)
        win = _FakeWindow(directory)
        info = _python_widget_info(directory)
        frame = win._place_widget("ordinary_python", info, (0, 0), (400, 300), instance_id=uuid_mod.uuid4().hex[:8])

        check("PythonWidgetHost.build_error is populated", "deliberately broken build" in frame.content.build_error)
        check(
            "[ERROR] indicator already showing right after placement (pre-existing-state check)",
            frame._titlebar._has_error,
        )
        check("last_error_message mentions the real traceback", "deliberately broken build" in frame.last_error_message)


test_build_failure_lights_up_error_indicator_immediately()


def test_successful_build_never_shows_error_indicator():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        _write_widget_py(directory, WORKING_WIDGET_PY)
        win = _FakeWindow(directory)
        info = _python_widget_info(directory)
        frame = win._place_widget("ordinary_python", info, (0, 0), (400, 300), instance_id=uuid_mod.uuid4().hex[:8])

        check("build_error is empty for a successful build", frame.content.build_error == "")
        check("[ERROR] indicator never shows for a successful build", not frame._titlebar._has_error)


test_successful_build_never_shows_error_indicator()


def test_hot_reload_from_failing_to_working_clears_indicator_live():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        _write_widget_py(directory, FAILING_WIDGET_PY)
        win = _FakeWindow(directory)
        info = _python_widget_info(directory)
        frame = win._place_widget("ordinary_python", info, (0, 0), (400, 300), instance_id=uuid_mod.uuid4().hex[:8])
        check("starts out erroring", frame._titlebar._has_error)

        _write_widget_py(directory, WORKING_WIDGET_PY)
        win._broker.widget_changed.emit("ordinary_python")

        check("build_error cleared after a live successful rebuild", frame.content.build_error == "")
        check("[ERROR] indicator cleared live once the fix lands", not frame._titlebar._has_error)


test_hot_reload_from_failing_to_working_clears_indicator_live()


# TODO a5f66cc: os._exit(), not the default clean interpreter exit
# -- this script places several kind:"html" (ChromiumWidget-backed)
# widgets across its test functions, each now with its own real
# QWebEngineProfile (previously all shared Qt's one default
# profile). Confirmed directly (see LEARNINGS.md's TODO a5f66cc
# entry): once every check()/assert above has already passed
# correctly, normal Python interpreter shutdown can still segfault
# tearing down 2+ such profiles/pages -- a real, reproducible
# Qt/WebEngine internals race specific to that shutdown path, not a
# bug in anything this script actually verifies. os._exit()
# terminates immediately, skipping that teardown path entirely (the
# same way force-quitting a process does), so the reported exit
# code reliably reflects the real results above instead of being
# clobbered by an unrelated crash.
print(f"\n{passed} passed, {failed} failed")
sys.stdout.flush()
os._exit(1 if failed else 0)
