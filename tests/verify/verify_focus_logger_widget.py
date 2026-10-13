"""Verifies TODO `00ea6b3`: the Focus Logger widget (plans/focus-logger-widget.md).
Real FocusLogger/WidgetLogStore/EventMediator and a real WorkspaceView; no full
DeskWindow. Headless."""

import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.window  # noqa: E402,F401  (must precede QApplication)

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from desk.event_mediator import EventMediator  # noqa: E402
from desk.focus_logger import FOCUS_LOG_NAME, FocusLogger  # noqa: E402
from desk.shell import current_context  # noqa: E402
from desk.shell.canvas import WorkspaceView  # noqa: E402
from desk.widget_logs import RECORDING_EVENT, STOPPED_RECORDING_EVENT, WidgetLogStore  # noqa: E402

_KEEP_ALIVE = []


def _keep(obj):
    """See verify_minimap.py / verify_claude_desk_status_events.py: an
    EventSubscription's destroyed-callback touches its mediator at GC
    time; interpreter shutdown order is arbitrary, so keep every test
    mediator/logger/store alive for the whole run."""
    _KEEP_ALIVE.append(obj)
    return obj


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
        "focus_logger_widget_check", REPO_ROOT / "widgets" / "focus_logger" / "widget.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


widget_mod = _load_widget_module()

store = _keep(WidgetLogStore())
view = WorkspaceView()
view.resize(400, 300)
view.show()
logger = _keep(FocusLogger(view, store))
app.processEvents()  # let initial window-activation focus settle, matching verify_focus_logger.py
current_context.set_focus_logger(logger)
current_context.set_widget_log_store(store)


# --- initial state, button start/stop -----------------------------------

w = widget_mod.FocusLoggerWidget()
check("starts off", not logger.is_enabled() and w._toggle_button.text() == "Start")
check("status label says logging off", w._status_label.text() == "Logging off")

w._on_toggle_clicked()
check("button start enables the logger", logger.is_enabled())
check("button records that this widget started it", w._state["started_by_button"] is True)
check("button text flips to Stop", w._toggle_button.text() == "Stop")

time.sleep(0.01)  # real wall-clock gap past the widget's "live starts now" baseline
store.append(FOCUS_LOG_NAME, [(None, "test_entry foo=1")])
w._poll()
check("a new store entry appears in the live view", "test_entry foo=1" in w._view.toPlainText())

w._on_toggle_clicked()
check("button stop disables the logger", not logger.is_enabled())
check("button stop clears started_by_button", w._state["started_by_button"] is False)
check("button text flips back to Start", w._toggle_button.text() == "Start")


# --- recording/stopped_recording bracket a fresh session -----------------

mediator = _keep(EventMediator())
w2 = widget_mod.FocusLoggerWidget()
w2.bind_event_mediator("w2", mediator)

mediator.publish(RECORDING_EVENT, {"recording_id": "rec-A", "started_at_ms": 1}, "sender")
w2._subscription._poll()
check("recording event turns the logger on, tagged", logger.is_enabled() and logger.tag == "rec-A")
check("this instance marks itself as the one that auto-started it", w2._auto_started is True)

mediator.publish(STOPPED_RECORDING_EVENT, {"recording_id": "rec-A", "started_at_ms": 1, "stopped_at_ms": 2}, "sender")
w2._subscription._poll()
check("stopped_recording turns an auto-started session back off", not logger.is_enabled())
check("_auto_started resets", w2._auto_started is False)


# --- a manual session survives a recording that starts/stops around it ---

w3 = widget_mod.FocusLoggerWidget()
w3.bind_event_mediator("w3", mediator)
w3._on_toggle_clicked()  # manual start, before any recording
check("manual session is on", logger.is_enabled() and w3._state["started_by_button"] is True)

mediator.publish(RECORDING_EVENT, {"recording_id": "rec-B", "started_at_ms": 3}, "sender")
w3._subscription._poll()
check("recording event re-tags an already-running manual session", logger.tag == "rec-B")
check("a manual session is not considered auto-started", w3._auto_started is False)

mediator.publish(STOPPED_RECORDING_EVENT, {"recording_id": "rec-B", "started_at_ms": 3, "stopped_at_ms": 4}, "sender")
w3._subscription._poll()
check("stopped_recording leaves a manual session running", logger.is_enabled())
check("stopped_recording clears the tag of a manual session", logger.tag is None)

w3._on_toggle_clicked()  # clean up
check("manual stop afterward still works", not logger.is_enabled())


# --- closing the widget: only a self-started session is stopped ----------

logger.enable()
widget_mod._stop_if_started_here(logger, {"started_by_button": True})
check("closing a self-started session disables it", not logger.is_enabled())

logger.enable()
widget_mod._stop_if_started_here(logger, {"started_by_button": False})
check("closing an externally-observed session leaves it running", logger.is_enabled())
logger.disable()


# --- multiple instances share one logger without double-stopping ---------

w4 = widget_mod.FocusLoggerWidget()
w5 = widget_mod.FocusLoggerWidget()
w4.bind_event_mediator("w4", mediator)
w5.bind_event_mediator("w5", mediator)

mediator.publish(RECORDING_EVENT, {"recording_id": "rec-C", "started_at_ms": 5}, "sender")
w4._subscription._poll()
w5._subscription._poll()
check("only the instance that actually flips it on marks auto_started", w4._auto_started is True and w5._auto_started is False)

mediator.publish(STOPPED_RECORDING_EVENT, {"recording_id": "rec-C", "started_at_ms": 5, "stopped_at_ms": 6}, "sender")
w4._subscription._poll()
check("the auto-starting instance turns it back off", not logger.is_enabled())
w5._subscription._poll()
check("a second instance's own stopped_recording handling is harmless once already off", not logger.is_enabled())


# --- widget.json manifest -------------------------------------------------

manifest = json.loads((REPO_ROOT / "widgets" / "focus_logger" / "widget.json").read_text())
check("manifest is a python widget with an entry point", manifest["kind"] == "python" and manifest["entry"] == "widget.py")


print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
