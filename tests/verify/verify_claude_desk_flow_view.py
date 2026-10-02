"""Verifies TODO `eb50b84`: the Claude (Desk) widget's live data-flow
view (desk.claude_flow_view). See plans/claude-desk-data-flow-view.md.
`advance(dt)` is driven directly, so no real timing is involved."""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.window  # noqa: E402,F401  (must precede QApplication)

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from desk import claude_flow_view as cfv  # noqa: E402
from desk.claude_flow_view import FlowView  # noqa: E402

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


def ev(kind, turn_id=1, solicited=True, data=None):
    return {"seq": 1, "ts": 1.0, "turn_id": turn_id, "solicited": solicited, "kind": kind, "data": data or {}}


def test_turn_started_travels_outbound():
    view = FlowView()
    view.feed(ev("turn_started", 3))
    (marker,) = view.markers()
    check("outbound path", marker.path == cfv.OUTBOUND_PATH)
    check("solicited color", marker.color == cfv.SOLICITED_COLOR)
    check("labelled with the turn id", marker.label == "t3")
    check("session node shows the in-flight turn", view.inflight_turn == 3 and view._annotation("session") == "turn 3")


def test_stream_events_travel_inbound_with_provenance_colors():
    view = FlowView()
    view.feed(ev("assistant_text", 2))
    view.feed(ev("assistant_text", 9, solicited=False))
    view.feed(ev("turn_complete", 2))
    a, b, c = view.markers()
    check("all inbound", all(m.path == cfv.INBOUND_PATH for m in (a, b, c)))
    check("solicited blue, unsolicited orange, complete green", (a.color, b.color, c.color) == (cfv.SOLICITED_COLOR, cfv.UNSOLICITED_COLOR, cfv.COMPLETE_COLOR))
    check("solicited turn_complete clears the in-flight turn", view.inflight_turn is None)


def test_unsolicited_complete_keeps_inflight_turn():
    view = FlowView()
    view.feed(ev("turn_started", 5))
    view.feed(ev("turn_complete", 4, solicited=False))
    check("in-flight turn unchanged by an unsolicited result", view.inflight_turn == 5)


def test_markers_advance_arrive_and_expire():
    view = FlowView()
    view.feed(ev("assistant_text"))
    view.advance(0.3)
    (marker,) = view.markers()
    check("progress advances with dt", 0 < marker.progress < 1)
    view.advance(5)
    check("finished markers are retired", view.markers() == [])
    check("each later node on the path counted the arrival once", view.seen("stream") == 1 and view.seen("reader") == 1 and view.seen("history") == 1 and view.seen("cli") == 0)


def test_errors_flash_the_reader_and_decay():
    view = FlowView()
    view.feed(ev("protocol_violation", None, solicited=False))
    check("reader flashes on a protocol violation", view.flashing("reader"))
    view.advance(cfv.FLASH_SECONDS + 0.1)
    check("flash decays", not view.flashing("reader"))
    view.feed(ev("session_error", 1))
    check("session_error flashes too", view.flashing("reader"))


def test_queue_depth_and_task_annotations():
    view = FlowView()
    view.set_queue_depth(2)
    check("queue node shows depth", view._annotation("queue") == "2 queued")
    view.feed(ev("task_event", data={"task_id": "a", "patch": {"status": "running"}}))
    view.feed(ev("task_event", data={"task_id": "b", "patch": {"description": "x"}}))
    check("running tasks counted (status-less patch counts as running)", view.active_tasks == 2)
    view.feed(ev("task_event", data={"task_id": "a", "patch": {"status": "completed"}}))
    check("terminal tasks drop out", view.active_tasks == 1 and view._annotation("cli") == "1 bg tasks")


def test_timer_runs_only_while_visible_and_animating():
    view = FlowView()
    view.feed(ev("assistant_text"))
    check("hidden view never starts the timer", not view._timer.isActive())
    view.show()
    check("showing with markers in flight starts it", view._timer.isActive())
    view.advance(10)
    check("it stops once nothing is animating", not view._timer.isActive())
    view.feed(ev("assistant_text"))
    check("a new event while visible restarts it", view._timer.isActive())
    view.hide()
    check("hiding stops it", not view._timer.isActive())


def test_painting_does_not_raise_and_draws():
    view = FlowView()
    view.resize(520, 170)
    view.show()
    view.feed(ev("turn_started", 1))
    view.feed(ev("assistant_text", 1, solicited=False))
    view.feed(ev("session_error", 1))
    view.advance(0.4)
    image = view.grab().toImage()
    check("grab renders a non-empty image", image.width() == 520 and image.height() == 170)


def _widget_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("flow_check", REPO_ROOT / "widgets" / "claude_desk" / "widget.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_widget_integration():
    module = _widget_module()
    widget = module.build()
    check("a Flow toggle exists and starts off", widget._flow_toggle_button.isCheckable() and not widget._flow_toggle_button.isChecked())
    check("the flow panel starts hidden", widget._flow_view.isHidden())
    widget._flow_toggle_button.setChecked(True)
    check("toggling shows the panel", not widget._flow_view.isHidden())
    check("the label reflects state", widget._flow_toggle_button.text() == "Flow ▾")
    widget._on_session_event(ev("turn_started", 1))
    check("session events reach the flow view", len(widget._flow_view.markers()) == 1)

    class _S:
        def send_prompt(self, t):
            pass

        def stop(self):
            pass

    widget._session = _S()
    widget._busy = True
    widget._prompt_input.setPlainText("queue me")
    widget._on_send_clicked()
    check("queueing a message updates the flow's queue depth", widget._flow_view.queue_depth == 1)

    calls = []
    from desk.shell import current_context

    widget._session_id = "abc"
    previous = current_context.get_widget_height_adjuster()
    current_context.set_widget_height_adjuster(lambda iid, delta: calls.append((iid, delta)))
    try:
        widget._flow_toggle_button.setChecked(False)
        widget._flow_toggle_button.setChecked(True)
    finally:
        current_context.set_widget_height_adjuster(previous)
    check("toggling resizes the frame symmetrically", calls == [("abc", -module.FLOW_PANEL_HEIGHT), ("abc", module.FLOW_PANEL_HEIGHT)])


test_turn_started_travels_outbound()
test_stream_events_travel_inbound_with_provenance_colors()
test_unsolicited_complete_keeps_inflight_turn()
test_markers_advance_arrive_and_expire()
test_errors_flash_the_reader_and_decay()
test_queue_depth_and_task_annotations()
test_timer_runs_only_while_visible_and_animating()
test_painting_does_not_raise_and_draws()
test_widget_integration()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
