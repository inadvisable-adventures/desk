# DISABLED (TODO 9bc522b): every test in this file starts a real
# ClaudeSession (the Claude Agent SDK wrapper, desk.claude_session) and
# runs one or more real turns against the live Claude API -- real
# network calls, real API cost/quota, real (if usually short) latency,
# and outcomes that depend on a live model's actual behavior rather
# than fixed local logic. Same reasoning/convention as
# disabled_verify_claude_desk_widget_claude_api.py, split out on its
# own here (TODO 0529501) rather than folded into that file, since this
# covers a different feature (ClaudeSession.start()'s allowed_paths
# scoping) with its own setup. Left disabled until TODO 9bc522b decides
# how coverage like this should actually be integrated. Still real,
# working, non-mocked tests -- run directly (`.venv/bin/python3
# tests/verify/disabled_verify_scoped_claude_session.py`) when you want
# this coverage (needs real Claude API access/auth).
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

# desk.shell.window (imported indirectly) must be importable before
# QApplication is constructed -- see
# tests/verify/verify_claude_desk_widget.py's own comment on this same
# gotcha.
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


def wait_until(predicate, timeout=90.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_scoped_session_denies_out_of_scope_read():
    """Real, non-mocked: a session scoped to one allowed file, asked to
    Read both it and an unrelated file by absolute path in the same
    turn -- the in-scope read succeeds, the out-of-scope read is denied
    with no permission_request ever firing for it (the PreToolUse hook
    denies before it would reach one -- the thing a cwd/add_dirs-only
    design would not have done, per plans/scoped-claude-session-api.md's
    investigation)."""
    with tempfile.TemporaryDirectory() as allowed, tempfile.TemporaryDirectory() as forbidden:
        allowed_file = Path(allowed) / "allowed.txt"
        forbidden_file = Path(forbidden) / "forbidden.txt"
        allowed_file.write_text("ALLOWED-CONTENT-42")
        forbidden_file.write_text("FORBIDDEN-CONTENT-99")

        session = ClaudeSession()
        perm_requests = []
        turns = []
        errors = []
        session.permission_request.connect(lambda rid, name, inp: perm_requests.append((rid, name, inp)))
        session.turn_complete.connect(lambda summary: turns.append(summary))
        session.session_error.connect(lambda msg: errors.append(msg))

        session.start(
            str(uuid.uuid4()),
            resume=False,
            model="claude-haiku-4-5-20251001",
            permission_mode="default",
            cwd=Path(allowed),
            allowed_paths=[allowed_file],
            initial_prompt=(
                f"Use the Read tool to read exactly these two absolute paths, one at "
                f"a time: first {allowed_file}, then {forbidden_file}. After "
                f"attempting both, report in plain text: for each path, either its "
                f"exact file contents, or the exact error message you got trying to "
                f"read it. Attempt both even if the first fails."
            ),
        )
        ok = wait_until(lambda: turns or errors)
        check("scoped session completes a turn (or reports an error) within the timeout", ok)
        check("scoped session reported no error", not errors)
        check(
            "no permission_request ever fired for the out-of-scope read (hook denied it first)",
            not perm_requests,
        )
        result = turns[0]["result"] if turns else ""
        check("the in-scope file's real content came back", "ALLOWED-CONTENT-42" in result)
        check("the out-of-scope file's real content did NOT come back", "FORBIDDEN-CONTENT-99" not in result)
        session.stop()


def test_scoped_session_denies_even_under_bypass_permissions():
    """Real, non-mocked: same as above but permission_mode="bypassPermissions"
    -- the one mode can_use_tool is never consulted for at all (confirmed
    directly against the SDK's own can_use_tool docstring). The
    PreToolUse hook must still deny the out-of-scope read here, or the
    whole scoping mechanism would be bypassable by simply picking that
    mode."""
    with tempfile.TemporaryDirectory() as allowed, tempfile.TemporaryDirectory() as forbidden:
        allowed_file = Path(allowed) / "allowed.txt"
        forbidden_file = Path(forbidden) / "forbidden.txt"
        allowed_file.write_text("ALLOWED-CONTENT-42")
        forbidden_file.write_text("FORBIDDEN-CONTENT-99")

        session = ClaudeSession()
        turns = []
        errors = []
        session.turn_complete.connect(lambda summary: turns.append(summary))
        session.session_error.connect(lambda msg: errors.append(msg))

        session.start(
            str(uuid.uuid4()),
            resume=False,
            model="claude-haiku-4-5-20251001",
            permission_mode="bypassPermissions",
            cwd=Path(allowed),
            allowed_paths=[allowed_file],
            initial_prompt=(
                f"Use the Read tool to read exactly these two absolute paths, one at "
                f"a time: first {allowed_file}, then {forbidden_file}. After "
                f"attempting both, report in plain text: for each path, either its "
                f"exact file contents, or the exact error message you got trying to "
                f"read it. Attempt both even if the first fails."
            ),
        )
        ok = wait_until(lambda: turns or errors)
        check("bypassPermissions scoped session completes a turn within the timeout", ok)
        result = turns[0]["result"] if turns else ""
        check(
            "the out-of-scope file's real content did NOT come back, even under bypassPermissions",
            "FORBIDDEN-CONTENT-99" not in result,
        )
        session.stop()


def test_scoped_session_denies_out_of_scope_write():
    """Real, non-mocked: a scoped session asked to Write to a path
    outside allowed_paths is denied without ever prompting; the file is
    never created."""
    with tempfile.TemporaryDirectory() as allowed, tempfile.TemporaryDirectory() as forbidden:
        allowed_file = Path(allowed) / "allowed.txt"
        allowed_file.write_text("ALLOWED-CONTENT-42")
        target = Path(forbidden) / "should-not-exist.txt"

        session = ClaudeSession()
        perm_requests = []
        turns = []
        session.permission_request.connect(lambda rid, name, inp: perm_requests.append((rid, name, inp)))
        session.turn_complete.connect(lambda summary: turns.append(summary))

        session.start(
            str(uuid.uuid4()),
            resume=False,
            model="claude-haiku-4-5-20251001",
            permission_mode="default",
            cwd=Path(allowed),
            allowed_paths=[allowed_file],
            initial_prompt=f"Use the Write tool to create a file at {target} containing the text hello.",
        )
        wait_until(lambda: turns)
        check("no permission_request fired for the out-of-scope write", not perm_requests)
        check("the out-of-scope file was never created", not target.exists())
        session.stop()


test_scoped_session_denies_out_of_scope_read()
test_scoped_session_denies_even_under_bypass_permissions()
test_scoped_session_denies_out_of_scope_write()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
