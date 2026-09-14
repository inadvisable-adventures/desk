# DISABLED (TODO 9bc522b): every test in this file starts a real
# ClaudeSession (the Claude Agent SDK wrapper, desk.claude_session) and
# runs one or more real turns against the live Claude API -- real
# network calls, real API cost/quota, real (if usually short) latency,
# and outcomes that depend on a live model's actual behavior rather
# than fixed local logic. Split out of
# tests/verify/verify_claude_desk_widget.py (which keeps its other,
# API-free tests -- widget.json shape, DeskWindow wiring -- running
# normally) so only the actual live-API-touching coverage is disabled.
# Left disabled until TODO 9bc522b decides how coverage like this
# should actually be integrated (run occasionally by hand, mock the
# Claude Agent SDK layer, or some combination) rather than always
# running as part of the normal sweep. Still real, working, non-mocked
# tests -- run directly (`.venv/bin/python3
# tests/verify/disabled_verify_claude_desk_widget_claude_api.py`) when
# you want this coverage (needs real Claude API access/auth).
import importlib.util
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
# see tests/verify/verify_claude_desk_widget.py's own comment on this
# same gotcha.
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


def load_widget_module():
    spec = importlib.util.spec_from_file_location("claude_desk_widget", REPO_ROOT / "widgets" / "claude_desk" / "widget.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
            # TODO e1f6391: _prompt_input/_send_button deliberately
            # stay enabled even while busy now (so a submission queues
            # instead of having nowhere to go) -- widget._busy is the
            # real busy signal to check, not Qt's own isEnabled().
            check("widget is busy while the session connects/first turn runs", widget._busy is True)

            ok = wait_until(lambda: not widget._busy, timeout=90.0)
            check("widget goes idle once the first turn completes", ok)
            check("history contains the bootstrap prompt's own opening text", "running inside of Desk" in widget._history.toPlainText())

            widget._prompt_input.setPlainText("Use the Write tool to create a file named widget-probe.txt containing hi.")
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
            ok = wait_until(lambda: not widget._busy, timeout=90.0)
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


def test_message_queue_sends_in_order_once_idle():
    """TODO e1f6391: real, non-mocked -- a message sent while a real
    turn is in flight queues instead of dispatching immediately, shows
    up in the UI (queue label, "[queued]" history line, Send button
    relabeled to "Queue"), and a second queued message stays behind the
    first. Once each turn actually completes for real, the next queued
    message is dispatched automatically, in order -- confirmed via two
    real, separate turns completing, not simulated."""
    module = load_widget_module()
    with tempfile.TemporaryDirectory() as tmp:
        original_cwd_getter = module.current_context.get_current_desk_directory
        module.current_context.get_current_desk_directory = lambda: Path(tmp)
        try:
            widget = module.build()
            sent_prompts = []
            original_send_prompt = widget._session.send_prompt
            widget._session.send_prompt = lambda text: (sent_prompts.append(text), original_send_prompt(text))[-1]

            widget.start_session(str(uuid.uuid4()), resume=False, extra_instructions="")
            check("widget starts busy (bootstrap turn in flight)", widget._busy is True)

            widget._prompt_input.setPlainText("Reply with exactly the word: first")
            widget._on_send_clicked()
            check("a message sent while busy does not dispatch immediately", sent_prompts == [])
            check("Send button relabels to Queue while busy", widget._send_button.text() == "Queue")
            check("the queue label becomes visible", widget._queue_label.isVisibleTo(widget))
            check("the queue label reports one queued message", widget._queue_label.text() == "Queued: 1")
            check("history records the queued submission", "[queued] Reply with exactly the word: first" in widget._history.toPlainText())

            widget._prompt_input.setPlainText("Reply with exactly the word: second")
            widget._on_send_clicked()
            check("a second message queues behind the first, not sent yet", sent_prompts == [])
            check("the queue label now reports two queued messages", widget._queue_label.text() == "Queued: 2")

            ok = wait_until(lambda: sent_prompts == ["Reply with exactly the word: first"], timeout=90.0)
            check("the first queued message is dispatched once the bootstrap turn completes", ok)
            check("the second message is still queued, not sent yet", widget._queue_label.text() == "Queued: 1")
            check("widget is busy again for the first queued message's own turn", widget._busy is True)

            ok = wait_until(lambda: sent_prompts == ["Reply with exactly the word: first", "Reply with exactly the word: second"], timeout=90.0)
            check("the second queued message is dispatched once its own turn completes, in order", ok)

            ok = wait_until(lambda: not widget._busy, timeout=90.0)
            check("widget returns to idle once the last queued message's turn completes", ok)
            check("the queue label hides once the queue is empty", not widget._queue_label.isVisibleTo(widget))
            check("Send button reverts to Send once idle", widget._send_button.text() == "Send")
        finally:
            module.current_context.get_current_desk_directory = original_cwd_getter
            widget._session.stop()
            widget.deleteLater()


test_session_fresh_start_and_resume()
test_tool_permission_gate()
test_widget_history_and_permission_ui()
test_message_queue_sends_in_order_once_idle()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
