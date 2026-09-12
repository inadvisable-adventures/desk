# TODO 551014c: the Claude (Desk) widget's own session id shown in its
# titlebar via the widget-subtitle current_context hook. Follows
# verify_claude_desk_widget.py's own established shape (a real widget
# built via module.build(), a _FakeSession standing in for a live
# ClaudeSDKClient, no network calls).
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.window  # noqa: E402,F401

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

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


def _load_widget_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "claude_desk_widget", REPO_ROOT / "widgets" / "claude_desk" / "widget.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeSignal:
    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def emit(self, *args):
        for slot in list(self._slots):
            slot(*args)


class _FakeSession:
    def __init__(self):
        self.start_calls = []
        self.connected = _FakeSignal()

    def start(self, session_id, resume, model, permission_mode, cwd, initial_prompt):
        self.start_calls.append((session_id, resume, model, permission_mode, cwd, initial_prompt))

    def set_permission_mode(self, mode):
        pass

    def stop(self):
        pass


def test_hook_is_none_until_set():
    from desk.shell import current_context

    current_context.set_widget_subtitle_setter(None)
    check("get_widget_subtitle_setter is None before anything sets it", current_context.get_widget_subtitle_setter() is None)
    fake = lambda instance_id, text: None  # noqa: E731
    current_context.set_widget_subtitle_setter(fake)
    check("get_widget_subtitle_setter returns exactly what was set", current_context.get_widget_subtitle_setter() is fake)
    current_context.set_widget_subtitle_setter(None)


def test_window_init_wires_the_hook_to_the_real_set_widget_subtitle():
    import desk.shell.window as window_mod
    from desk.shell import current_context

    # DeskWindow.__new__(DeskWindow), not a real constructed window --
    # same trick verify_claude_desk_widget.py's own test_window_wiring
    # already uses (a real DeskWindow needs a live Desk/QMainWindow
    # setup this check doesn't need just to confirm the wiring line
    # exists and does the right thing).
    fake_window = window_mod.DeskWindow.__new__(window_mod.DeskWindow)
    recorded = []
    fake_window.set_widget_subtitle = lambda instance_id, text: recorded.append((instance_id, text))

    current_context.set_widget_subtitle_setter(fake_window.set_widget_subtitle)
    setter = current_context.get_widget_subtitle_setter()
    setter("some-instance-id", "abcd1234")
    check(
        "the wired hook calls through to DeskWindow.set_widget_subtitle",
        recorded == [("some-instance-id", "abcd1234")],
    )
    current_context.set_widget_subtitle_setter(None)

    import inspect

    init_source = inspect.getsource(window_mod.DeskWindow.__init__)
    check(
        "DeskWindow.__init__ wires set_widget_subtitle_setter to self.set_widget_subtitle",
        "current_context.set_widget_subtitle_setter(self.set_widget_subtitle)" in init_source,
    )


def test_subtitle_set_once_session_connects_not_before():
    from desk.shell import current_context

    module = _load_widget_module()
    widget = module.build()
    fake_session = _FakeSession()
    widget._session = fake_session
    # __init__ already connected the *real* session's `connected`
    # signal to _on_session_connected -- reconnect the fake one's here
    # too, mirroring exactly what a real ClaudeSession.start() would do
    # once its own SDK client actually connects.
    fake_session.connected.connect(widget._on_session_connected)

    recorded = []
    current_context.set_widget_subtitle_setter(lambda instance_id, text: recorded.append((instance_id, text)))
    try:
        import uuid

        session_id = str(uuid.uuid4())
        widget.start_session(session_id, resume=False)
        check("nothing is set before the session actually connects", recorded == [])

        fake_session.connected.emit()
        check(
            "the subtitle is set to the session id truncated to 8 hex characters, once connected",
            recorded == [(session_id, session_id[:8])],
        )
    finally:
        current_context.set_widget_subtitle_setter(None)


def test_subtitle_setter_missing_is_a_safe_no_op():
    from desk.shell import current_context

    current_context.set_widget_subtitle_setter(None)
    module = _load_widget_module()
    widget = module.build()
    fake_session = _FakeSession()
    widget._session = fake_session
    fake_session.connected.connect(widget._on_session_connected)

    import uuid

    widget.start_session(str(uuid.uuid4()), resume=False)
    fake_session.connected.emit()  # must not raise
    check("connecting with no subtitle-setter hook registered doesn't raise", True)


test_hook_is_none_until_set()
test_window_init_wires_the_hook_to_the_real_set_widget_subtitle()
test_subtitle_set_once_session_connects_not_before()
test_subtitle_setter_missing_is_a_safe_no_op()

print(f"\n{passed} passed, {failed} failed")
