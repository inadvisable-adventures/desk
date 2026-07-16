import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from desk import crash_handler
from desk.shell import current_context


def reset():
    crash_handler._previous_excepthook = None
    sys.excepthook = sys.__excepthook__


def make_exc():
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        return sys.exc_info()


def test_idempotent_install():
    reset()
    crash_handler.install()
    hook1 = sys.excepthook
    crash_handler.install()
    hook2 = sys.excepthook
    assert hook1 is hook2, "second install() should be a no-op"
    print("idempotent install: PASS")


def test_writes_log_in_current_desk_dir():
    reset()
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        current_context.set_current_desk_directory(directory)
        crash_handler.install()
        exc_type, exc_value, tb = make_exc()
        sys.excepthook(exc_type, exc_value, tb)

        logs = list((directory / ".desk_temp").glob("DESK-CRASH-*.log"))
        assert len(logs) == 1, logs
        content = logs[0].read_text()
        assert "RuntimeError: boom" in content, content
        assert "Traceback" in content
    print("writes log in current Desk dir: PASS")


def test_falls_back_to_cwd():
    reset()
    current_context.set_current_desk_directory(None)
    with tempfile.TemporaryDirectory() as d:
        old_cwd = Path.cwd()
        os.chdir(d)
        try:
            crash_handler.install()
            exc_type, exc_value, tb = make_exc()
            sys.excepthook(exc_type, exc_value, tb)
            logs = list((Path(d) / ".desk_temp").glob("DESK-CRASH-*.log"))
            assert len(logs) == 1, logs
        finally:
            os.chdir(old_cwd)
    print("falls back to cwd: PASS")


def test_chains_to_previous_hook():
    reset()
    calls = []
    sys.excepthook = lambda *a: calls.append(a)
    crash_handler.install()
    with tempfile.TemporaryDirectory() as d:
        current_context.set_current_desk_directory(Path(d))
        exc_type, exc_value, tb = make_exc()
        sys.excepthook(exc_type, exc_value, tb)
        assert len(calls) == 1
        assert calls[0][0] is exc_type
    print("chains to previous hook: PASS")


def test_survives_log_write_failure():
    reset()
    calls = []
    sys.excepthook = lambda *a: calls.append(a)
    crash_handler.install()
    with patch.object(crash_handler, "_log_path", side_effect=RuntimeError("path boom")):
        exc_type, exc_value, tb = make_exc()
        sys.excepthook(exc_type, exc_value, tb)  # must not raise
    assert len(calls) == 1, "previous hook should still fire even if logging fails"
    print("survives log-write failure: PASS")


test_idempotent_install()
test_writes_log_in_current_desk_dir()
test_falls_back_to_cwd()
test_chains_to_previous_hook()
test_survives_log_write_failure()
print("ALL PASS")
