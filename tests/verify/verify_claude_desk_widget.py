# Note: the mic-button test (starts a real MicRecorder capture -- a
# real QAudioSource against the actual default microphone) was split
# out to tests/verify/disabled_verify_claude_desk_widget_mic.py and
# disabled there (TODO b2ab79f); the tests that run real Claude API
# turns (a real ClaudeSession, real network calls/API cost) were split
# out to tests/verify/disabled_verify_claude_desk_widget_claude_api.py
# and disabled there (TODO 9bc522b). Both were making calls this
# project doesn't want happening automatically during routine
# regression sweeps. Every test remaining here never touches the
# microphone or the live Claude API and keeps running normally.
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path("/Users/mphair/inadvisable-adventures/desk")
sys.path.insert(0, str(REPO_ROOT / "src"))

# desk.shell.window (imported by widget.py's DeskWindow-adjacent pieces
# indirectly) must be importable before QApplication is constructed --
# see LEARNINGS.md-worthy gotcha confirmed directly while writing this
# script: desk.shell.chromium_widget's QtWebEngineWidgets import fails
# with "must be imported... before a QCoreApplication instance is
# created" otherwise. Importing desk.shell.window first (even though
# this script doesn't exercise DeskWindow itself) sidesteps it, same
# as every other verify script here that touches window.py.
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


def test_widget_json_is_well_formed():
    manifest = json.loads((REPO_ROOT / "widgets" / "claude_desk" / "widget.json").read_text())
    check("widget.json declares kind: python", manifest["kind"] == "python")
    check("widget.json entry is widget.py", manifest["entry"] == "widget.py")
    check("widget.json name is Claude (Desk)", manifest["name"] == "Claude (Desk)")


def test_window_wiring():
    import desk.shell.window as window_mod
    from desk.shell.python_widget import PythonWidgetHost
    from PyQt6.QtWidgets import QWidget

    check(
        "CLAUDE_DESK_WIDGET_ID is a distinct id from CLAUDE_WIDGET_ID",
        window_mod.CLAUDE_DESK_WIDGET_ID == "claude_desk" and window_mod.CLAUDE_DESK_WIDGET_ID != window_mod.CLAUDE_WIDGET_ID,
    )
    check("DeskWindow._bind_claude_desk_widget exists", hasattr(window_mod.DeskWindow, "_bind_claude_desk_widget"))

    class _FakeContent:
        def __init__(self):
            self.calls = []

        def start_session(self, instance_id, resume, extra_instructions=""):
            self.calls.append((instance_id, resume, extra_instructions))

    class _FakeHost(PythonWidgetHost):
        def __init__(self, current):
            QWidget.__init__(self)
            self._current = current
            self.widget_id = window_mod.CLAUDE_DESK_WIDGET_ID

    class _FakeFrame:
        def __init__(self, content, instance_id):
            self.content = content
            self.instance_id = instance_id

    content = _FakeContent()
    frame = _FakeFrame(_FakeHost(content), "fake-instance-id")
    # DeskWindow.__new__(DeskWindow), not object.__new__(DeskWindow): the
    # latter raises TypeError ("not safe") since DeskWindow's effective
    # __new__ (inherited through QMainWindow) differs from object's --
    # confirmed directly. Skips __init__ (no real window construction
    # needed just to call one duck-typed method), matching this
    # project's own ChromiumWidget.__new__(ChromiumWidget) precedent
    # elsewhere in tests/verify/.
    fake_window = window_mod.DeskWindow.__new__(window_mod.DeskWindow)
    window_mod.DeskWindow._bind_claude_desk_widget(fake_window, frame, resume=True, extra_instructions="extra")
    check(
        "_bind_claude_desk_widget duck-types on start_session exactly like _bind_claude_widget",
        content.calls == [("fake-instance-id", True, "extra")],
    )


def _load_widget_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("claude_desk_widget", REPO_ROOT / "widgets" / "claude_desk" / "widget.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeSession:
    """A recording stand-in for desk.claude_session.ClaudeSession (TODO
    e9eddba) -- swapped in after the real widget is built (its own
    __init__ already constructed and wired a real ClaudeSession, but
    that object's own .start() is never called here, so nothing about
    swapping it out afterward leaves anything real running) so
    start_session/the permission-mode combo can be tested without a
    real ClaudeSDKClient/network call."""

    def __init__(self):
        self.start_calls = []
        self.permission_mode_calls = []

    def start(self, session_id, resume, model, permission_mode, cwd, initial_prompt):
        self.start_calls.append((session_id, resume, model, permission_mode, cwd, initial_prompt))

    def set_permission_mode(self, mode):
        self.permission_mode_calls.append(mode)

    def stop(self):
        # The widget's own __init__ connects self.destroyed to
        # self._session.stop() -- fires for any teardown, including at
        # interpreter exit for a widget this script never explicitly
        # closes, regardless of which session object is currently
        # installed.
        pass


def test_permission_mode_combo_present_and_defaults_to_default():
    module = _load_widget_module()
    widget = module.build()
    labels = [widget._permission_mode_combo.itemText(i) for i in range(widget._permission_mode_combo.count())]
    check(
        "the permission-mode combo offers all six real SDK modes",
        labels == ["Default", "Accept Edits", "Plan", "Bypass Permissions", "Don't Ask", "Auto"],
    )
    check("the permission-mode combo defaults to Default", widget._permission_mode_combo.currentIndex() == 0)


def test_start_session_passes_the_selected_permission_mode():
    import uuid

    module = _load_widget_module()
    for index, (label, value) in enumerate(module.PERMISSION_MODE_CHOICES):
        widget = module.build()
        fake_session = _FakeSession()
        widget._session = fake_session
        widget._permission_mode_combo.setCurrentIndex(index)
        widget.start_session(str(uuid.uuid4()), resume=False)
        check(
            f"start_session passes the real SDK value for {label!r}, not the label",
            fake_session.start_calls and fake_session.start_calls[0][3] == value,
        )


def test_changing_the_combo_calls_set_permission_mode_live():
    module = _load_widget_module()
    widget = module.build()
    fake_session = _FakeSession()
    widget._session = fake_session

    widget._permission_mode_combo.setCurrentIndex(1)
    check(
        "changing the combo calls set_permission_mode with the newly-selected value",
        fake_session.permission_mode_calls == ["acceptEdits"],
    )
    widget._permission_mode_combo.setCurrentIndex(4)
    check(
        "a second change calls it again with the new value",
        fake_session.permission_mode_calls == ["acceptEdits", "dontAsk"],
    )


def test_set_permission_mode_is_a_real_no_op_before_start():
    from desk.claude_session import ClaudeSession

    session = ClaudeSession()
    session.set_permission_mode("acceptEdits")  # must not raise
    check("ClaudeSession.set_permission_mode no-ops before any session has started", True)


test_widget_json_is_well_formed()
test_window_wiring()
test_permission_mode_combo_present_and_defaults_to_default()
test_start_session_passes_the_selected_permission_mode()
test_changing_the_combo_calls_set_permission_mode_live()
test_set_permission_mode_is_a_real_no_op_before_start()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
