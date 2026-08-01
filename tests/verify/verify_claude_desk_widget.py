import importlib.util
import json
import os
import sys
import tempfile
import time
import uuid
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

from desk.claude_session import ClaudeSession  # noqa: E402

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


def wait_until(predicate, timeout=60.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return False


def pump(seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)


def load_widget_module():
    spec = importlib.util.spec_from_file_location("claude_desk_widget", REPO_ROOT / "widgets" / "claude_desk" / "widget.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def synthesize_pcm(text):
    """Real macOS text-to-speech -> raw 16kHz mono 16-bit PCM samples,
    same fixture approach as tests/verify/verify_voice_input_widget
    .py's own synthesize_pcm (TODO fe7d8f2)."""
    import subprocess
    import wave

    with tempfile.TemporaryDirectory() as tmp:
        wav_path = Path(tmp) / "sample.wav"
        subprocess.run(
            ["say", "-o", str(wav_path), "--file-format=WAVE", "--data-format=LEI16@16000", text],
            check=True,
        )
        with wave.open(str(wav_path), "rb") as wf:
            return wf.readframes(wf.getnframes())


def test_mic_button_dictates_into_the_prompt_box_without_sending():
    """TODO fe7d8f2: a real mic-button click starts a real MicRecorder
    (desk.voice_capture, shared with widgets/voice_input/widget.py),
    then injected known synthesized speech (real audio pipeline, same
    technique tests/verify/verify_voice_input_widget.py already uses)
    is transcribed and lands in _prompt_input -- confirmed *not*
    auto-sent (no real Claude session involved in this check at all,
    so send_prompt firing would be directly observable, not just
    theoretically possible)."""
    module = load_widget_module()
    widget = module.build()
    sent = []
    widget._session.send_prompt = lambda text: sent.append(text)

    widget._on_mic_clicked()
    check("mic button switches to Stop", widget._mic_button.text() == "■")
    check("prompt input disabled while recording", not widget._prompt_input.isEnabled())
    check("a real MicRecorder actually started capturing", widget._mic_recorder.is_recording())

    pump(0.5)  # let the real microphone actually deliver some data

    # Override the *content* of what got captured with known,
    # real synthesized speech, then let stop() do its own real
    # teardown (stops the real QAudioSource, emits recording_stopped
    # for real) -- same technique
    # tests/verify/verify_voice_capture.py's own
    # _start_then_inject_known_audio uses. Calling
    # _process_captured_audio() directly instead would skip
    # recording_stopped entirely, silently leaving the mic button
    # stuck in its Stop state -- confirmed directly, a real bug this
    # test caught in its own first draft, not a hypothetical.
    widget._mic_recorder._captured_chunks = [synthesize_pcm("Testing dictation into Claude Desk")]
    widget._mic_recorder.stop()

    ok = wait_until(lambda: widget._prompt_input.isEnabled())
    check("controls re-enable once transcription finishes", ok)
    check("the dictated text landed in the prompt box", "dictation" in widget._prompt_input.text().lower())
    check("mic button reverts to Record", widget._mic_button.text() == "●")
    check("nothing was sent to the session -- the user still has to hit Send", sent == [])

    widget._session.stop()
    widget.deleteLater()


def test_widget_json_is_well_formed():
    manifest = json.loads((REPO_ROOT / "widgets" / "claude_desk" / "widget.json").read_text())
    check("widget.json declares kind: python", manifest["kind"] == "python")
    check("widget.json entry is widget.py", manifest["entry"] == "widget.py")
    check("widget.json name is Claude (Desk)", manifest["name"] == "Claude (Desk)")


def test_session_fresh_start_and_resume():
    """Real, non-mocked: a fresh ClaudeSession completes a turn end to
    end (prompt in, ResultMessage out), then a second ClaudeSession
    resuming the same session id recalls context from the first --
    confirming resume reconnects rather than starting fresh."""
    session_id = str(uuid.uuid4())
    with tempfile.TemporaryDirectory() as tmp:
        session = ClaudeSession()
        turns = []
        errors = []
        session.turn_complete.connect(lambda summary: turns.append(summary))
        session.session_error.connect(lambda msg: errors.append(msg))
        session.start(
            session_id,
            resume=False,
            model="claude-haiku-4-5-20251001",
            permission_mode="auto",
            cwd=Path(tmp),
            initial_prompt="Reply with exactly the single word: PONG",
        )
        ok = wait_until(lambda: turns or errors)
        check("fresh session completes a turn (or reports an error) within the timeout", ok)
        check("fresh session reported no error", not errors)
        check("fresh session's turn completed without error", turns and not turns[0]["is_error"])
        session.stop()

        resumed = ClaudeSession()
        resumed_turns = []
        resumed_errors = []
        resumed_connected = []
        resumed.turn_complete.connect(lambda summary: resumed_turns.append(summary))
        resumed.session_error.connect(lambda msg: resumed_errors.append(msg))
        resumed.connected.connect(lambda: resumed_connected.append(True))
        resumed.start(
            session_id,
            resume=True,
            model="claude-haiku-4-5-20251001",
            permission_mode="auto",
            cwd=Path(tmp),
            initial_prompt="",
        )
        # send_prompt() is a no-op until the client is actually connected
        # (ClaudeSession.send_prompt's own self._client is None guard) --
        # connect() runs on the background thread/loop asynchronously,
        # so this must wait for the real `connected` signal rather than
        # calling send_prompt() immediately after start() returns.
        ok = wait_until(lambda: resumed_connected or resumed_errors, timeout=30.0)
        check("resumed session actually connects within the timeout", ok)
        resumed.send_prompt("What single word did you just reply with? Answer with only that word.")
        ok = wait_until(lambda: resumed_turns or resumed_errors)
        check("resumed session completes a turn (or reports an error) within the timeout", ok)
        check("resumed session reported no error", not resumed_errors)
        check(
            "resumed session recalls context from the first session (proves it reconnected, not a fresh session)",
            resumed_turns and resumed_turns[0]["result"] and "pong" in resumed_turns[0]["result"].lower(),
        )
        resumed.stop()


def test_tool_permission_gate():
    """Real, non-mocked: a Write-tool call is denied via
    respond_to_permission(allow=False), confirmed by the file never
    being created; a second, separately-approved request lets the file
    be created. Mirrors the manual reproduction done while designing
    ClaudeSession (a plain Bash `echo` is not gated at all -- matches
    real `claude` CLI behavior -- so this uses the Write tool, which
    is)."""
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "permission-gate-probe.txt"

        session = ClaudeSession()
        requests = []
        turns = []
        session.permission_request.connect(lambda rid, name, inp: requests.append((rid, name, inp)))
        session.turn_complete.connect(lambda summary: turns.append(summary))

        def deny_on_request():
            if requests:
                rid, _name, _inp = requests[0]
                session.respond_to_permission(rid, allow=False, message="denied by verify script")
                return True
            return False

        session.start(
            str(uuid.uuid4()),
            resume=False,
            model="claude-haiku-4-5-20251001",
            permission_mode="default",  # not auto/bypassPermissions -- so can_use_tool is actually consulted
            cwd=Path(tmp),
            initial_prompt=f"Use the Write tool to create a file at {target} containing the text hello.",
        )
        ok = wait_until(deny_on_request)
        check("a Write tool call triggers a real permission_request", ok)
        if requests:
            check("the permission request names the Write tool", requests[0][1] == "Write")
        wait_until(lambda: turns)
        check("the file was NOT created after the request was denied", not target.exists())
        session.stop()

        target.unlink(missing_ok=True)
        requests.clear()
        turns.clear()
        session2 = ClaudeSession()
        session2.permission_request.connect(lambda rid, name, inp: requests.append((rid, name, inp)))
        session2.turn_complete.connect(lambda summary: turns.append(summary))

        def allow_on_request():
            if requests:
                rid, _name, _inp = requests[0]
                session2.respond_to_permission(rid, allow=True)
                return True
            return False

        session2.start(
            str(uuid.uuid4()),
            resume=False,
            model="claude-haiku-4-5-20251001",
            permission_mode="default",
            cwd=Path(tmp),
            initial_prompt=f"Use the Write tool to create a file at {target} containing the text hello.",
        )
        wait_until(allow_on_request)
        wait_until(lambda: turns)
        check("the file WAS created after the request was allowed", target.is_file())
        session2.stop()


def test_widget_history_and_permission_ui():
    """Real, non-mocked: builds the actual widget, starts a fresh
    session through it, and confirms the history view accumulates
    entries in order across a multi-turn conversation that includes a
    tool call requiring approval, resolved through the widget's own
    Allow button rather than calling ClaudeSession directly."""
    module = load_widget_module()
    with tempfile.TemporaryDirectory() as tmp:
        original_cwd_getter = module.current_context.get_current_desk_directory
        module.current_context.get_current_desk_directory = lambda: Path(tmp)
        try:
            widget = module.build()
            widget.start_session(str(uuid.uuid4()), resume=False, extra_instructions="")
            check("prompt input starts disabled while the session connects/first turn runs", not widget._prompt_input.isEnabled())

            ok = wait_until(lambda: widget._prompt_input.isEnabled(), timeout=90.0)
            check("prompt input re-enables once the first turn completes", ok)
            check("history contains the bootstrap prompt's own opening text", "running inside of Desk" in widget._history.toPlainText())

            widget._prompt_input.setText("Use the Write tool to create a file named widget-probe.txt containing hi.")
            widget._on_send_clicked()

            # isVisibleTo(widget), not isVisible(): confirmed directly
            # that QWidget.isVisible() is unconditionally False for any
            # descendant of a top-level widget that was never shown
            # (this test never calls widget.show(), matching every
            # other offscreen widget test in this directory) --
            # regardless of setVisible(True) having been called on it.
            # isVisibleTo(ancestor) reflects the actual explicit
            # visibility flag this test cares about.
            ok = wait_until(lambda: widget._permission_label.isVisibleTo(widget), timeout=90.0)
            check("the widget's own permission approval row becomes visible for a real tool call", ok)
            check("the permission label names the Write tool", "Write" in widget._permission_label.text())

            widget._allow_button.click()
            ok = wait_until(lambda: widget._prompt_input.isEnabled(), timeout=90.0)
            check("turn completes after approving through the widget's own Allow button", ok)
            check("the created file actually exists", (Path(tmp) / "widget-probe.txt").is_file())

            history_text = widget._history.toPlainText()
            first_prompt_index = history_text.find("running inside of Desk")
            tool_use_index = history_text.find("[tool] Write")
            permission_index = history_text.find("[permission] allowed Write")
            check(
                "history entries appear in chronological order (bootstrap prompt, tool use, permission decision)",
                -1 < first_prompt_index < tool_use_index < permission_index,
            )
        finally:
            module.current_context.get_current_desk_directory = original_cwd_getter
            widget._session.stop()
            widget.deleteLater()


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


test_widget_json_is_well_formed()
test_mic_button_dictates_into_the_prompt_box_without_sending()
test_session_fresh_start_and_resume()
test_tool_permission_gate()
test_widget_history_and_permission_ui()
test_window_wiring()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
