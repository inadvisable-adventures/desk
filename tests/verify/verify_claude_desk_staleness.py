"""Verifies TODO `5ce8447`: staleness tracking, task grace window and the
connectivity probe. Times are passed in explicitly; the probe uses an
injected checker. No live network/API."""

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.window  # noqa: E402,F401

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

import claude_agent_sdk as sdk  # noqa: E402

from desk import claude_staleness as cs  # noqa: E402
from desk.claude_session import ClaudeSession  # noqa: E402
from desk.claude_staleness import StalenessTracker  # noqa: E402
from desk.connectivity_probe import ConnectivityProbe  # noqa: E402

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


def ev(kind, solicited=True, data=None, turn_id=1):
    return {"seq": 1, "ts": 1.0, "turn_id": turn_id, "solicited": solicited, "kind": kind, "data": data or {}}


def task(task_id, **patch):
    return ev("task_event", data={"task_id": task_id, "patch": patch})


# -- tracker --------------------------------------------------------------------


def test_idle_is_never_stale():
    t = StalenessTracker()
    check("nothing outstanding -> level 0, no note", t.level(1000) == 0 and t.describe(1000, None) == "")


def test_pending_turn_goes_stale_then_probe_worthy():
    t = StalenessTracker()
    t.feed(ev("turn_started"), 0)
    check("fresh", t.level(cs.STALE_AFTER - 1) == 0)
    check("stale after the first threshold", t.level(cs.STALE_AFTER) == 1)
    check("probe-worthy after the second", t.level(cs.PROBE_AFTER) == 2)
    check("note counts seconds", t.describe(20, None) == "no response for 20s")
    t.feed(ev("assistant_text"), 30)
    check("any event resets the clock", t.level(31) == 0)
    t.feed(ev("turn_complete"), 40)
    check("turn_complete ends outstanding", not t.outstanding(1000))


def test_probe_result_wording():
    t = StalenessTracker()
    t.feed(ev("turn_started"), 0)
    check("level 1 never claims anything about the network", "network" not in t.describe(20, True) and "network" not in t.describe(20, False))
    check("down", t.describe(50, False) == "no response for 50s -- your network looks down")
    check("fine", t.describe(50, True) == "no response for 50s -- network's fine, something else is stuck")
    check("not probed yet adds nothing", t.describe(50, None) == "no response for 50s")


def test_unsolicited_turn_counts_and_unsolicited_complete_does_not_end_a_solicited_one():
    t = StalenessTracker()
    t.feed(ev("unsolicited_turn_started", solicited=False), 0)
    check("an open unsolicited turn is outstanding", t.outstanding(1))
    t.feed(ev("turn_complete", solicited=False), 2)
    check("its result closes it", not t.outstanding(3))
    t.feed(ev("turn_started"), 5)
    t.feed(ev("turn_complete", solicited=False), 6)
    check("an unsolicited result leaves the real turn outstanding", t.outstanding(7))


def test_session_error_clears():
    t = StalenessTracker()
    t.feed(ev("turn_started"), 0)
    t.feed(ev("session_error"), 1)
    check("session_error clears outstanding", not t.outstanding(100))


def test_delegated_task_keeps_things_outstanding_and_grace_follows():
    t = StalenessTracker()
    t.feed(task("a", status="running", task_type="local_agent"), 0)
    check("a running delegated agent is outstanding", t.outstanding(5))
    t.feed(task("a", status="completed"), 10)
    check("right after it settles we're in the grace window", t.in_grace(11) and t.outstanding(11))
    check("grace is hedged in plain language", "probably wrapping up a background task" in t.describe(10 + cs.STALE_AFTER, None))
    check("the hedge uses no SDK jargon", "SDK" not in t.describe(40, None) and "DEFERRING" not in t.describe(40, None))
    check("after the window it goes idle", not t.outstanding(10 + cs.GRACE_SECONDS + 1))


def test_plain_shell_tasks_are_ignored():
    t = StalenessTracker()
    t.feed(task("sh", status="running", task_type="local_bash"), 0)
    check("a background shell never counts as outstanding", not t.outstanding(10_000))
    t.feed(task("sh", status="completed"), 5)
    check("nor does settling one start a grace window", not t.in_grace(6))
    t.feed(task("u", status="running"), 0)
    check("a task of unknown type is treated as a shell", not t.outstanding(10))


def test_grace_not_started_while_another_agent_still_runs():
    t = StalenessTracker()
    t.feed(task("a", status="running", task_type="local_agent"), 0)
    t.feed(task("b", status="running", task_type="local_workflow"), 0)
    t.feed(task("a", status="completed"), 5)
    check("still outstanding because b runs, and no grace yet", t.outstanding(6) and t._grace_until is None)
    t.feed(task("b", status="failed"), 8)
    check("grace starts when the last one settles", t.in_grace(9))


def test_waiting_on_user_suppresses_staleness():
    t = StalenessTracker()
    t.feed(ev("turn_started"), 0)
    t.set_waiting_on_user(True, 5)
    check("while waiting on the user nothing is outstanding", not t.outstanding(500) and t.level(500) == 0 and t.describe(500, None) == "")
    t.set_waiting_on_user(False, 500)
    check("the wait doesn't count as silence once answered", t.outstanding(501) and t.level(501) == 0)
    check("silence after the answer counts from the answer", t.level(500 + cs.STALE_AFTER) == 1)


def test_widget_permission_wait_is_not_stale():
    module = _module()
    widget = module.build()
    widget._staleness_timer.stop()
    widget._staleness.feed(ev("turn_started"), 0)
    widget._tick_staleness(100)
    check("sanity: stale before any permission request", not widget._stale_label.isHidden())
    widget._pending_permissions.append(("r1", "Bash", {}))
    widget._publish_status()
    check("a pending permission clears the stale label immediately", widget._stale_label.isHidden() and widget._flow_view.stale_seconds is None)
    widget._tick_staleness(10_000)
    check("and it stays quiet however long the user takes", widget._stale_label.isHidden())
    widget._pending_permissions.clear()
    widget._publish_status()
    check("answering ends the suppression: the turn is outstanding again, with a fresh clock", widget._staleness.outstanding(time.monotonic()) and widget._stale_label.isHidden())


# -- session forwards task_type ------------------------------------------------


def test_session_forwards_task_type():
    session = ClaudeSession()
    seen = []
    session.task_event.connect(lambda tid, patch: seen.append((tid, patch)))
    msg = sdk.TaskStartedMessage(subtype="task_started", data={}, task_id="t1", description="d", uuid="u", session_id="s", task_type="local_agent")
    session._handle_message(msg, 1, True)
    check("task_type is in the patch", seen[0][1]["task_type"] == "local_agent")


# -- probe -------------------------------------------------------------------------


def test_probe_reports_and_stops():
    results = []
    probe = ConnectivityProbe(interval=0.05, check=lambda: False)
    probe.result.connect(results.append)
    probe.start()
    deadline = time.time() + 2
    while len(results) < 2 and time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)
    probe.stop()
    check("repeats while started, reporting the checker's answer", len(results) >= 2 and results[0] is False)
    check("stop() halts it", not probe.is_running())
    n = len(results)
    for _ in range(20):
        app.processEvents()
        time.sleep(0.01)
    check("no further results after stop", len(results) == n)


def test_probe_checker_exception_means_unreachable():
    def boom():
        raise RuntimeError("x")

    results = []
    probe = ConnectivityProbe(interval=10, check=boom)
    probe.result.connect(results.append)
    probe.probe_now()
    deadline = time.time() + 2
    while not results and time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)
    check("an exception is reported as unreachable", results == [False])


def test_tcp_reachable_uses_a_bare_connect():
    import socket
    import threading

    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    accepted = []
    threading.Thread(target=lambda: accepted.append(server.accept()), daemon=True).start()
    from desk.connectivity_probe import tcp_reachable

    check("reachable listener -> True", tcp_reachable("127.0.0.1", port, 2) is True)
    server.close()
    check("closed port -> False", tcp_reachable("127.0.0.1", port, 1) is False)


# -- widget ---------------------------------------------------------------------------


def _module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("stale_check", REPO_ROOT / "widgets" / "claude_desk" / "widget.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_widget_label_flow_and_probe_lifecycle():
    module = _module()
    widget = module.build()
    widget._staleness_timer.stop()
    starts = []
    widget._probe.start = lambda: starts.append(1) or setattr(widget._probe, "_fake_running", True)
    widget._probe.is_running = lambda: getattr(widget._probe, "_fake_running", False)
    widget._probe.stop = lambda: setattr(widget._probe, "_fake_running", False)

    widget._staleness.feed(ev("turn_started"), 0)
    widget._tick_staleness(5)
    check("fresh: label hidden, flow not stale, no probe", widget._stale_label.isHidden() and widget._flow_view.stale_seconds is None and not starts)
    widget._tick_staleness(20)
    check("stale: amber label with the note", not widget._stale_label.isHidden() and widget._stale_label.text() == "no response for 20s")
    check("stale: flow Session node goes amber", widget._flow_view.stale_seconds == 20 and widget._flow_view._annotation("session") == "stale 20s")
    check("stale but not yet probe-worthy: no probe", not starts)
    widget._tick_staleness(50)
    check("probe starts once, at the second threshold", starts == [1])
    widget._on_probe_result(False)
    check("a failed probe says the network looks down", widget._stale_label.text().endswith("your network looks down"))
    widget._on_probe_result(True)
    check("a successful probe says something else is stuck", "network's fine" in widget._stale_label.text())
    widget._staleness.feed(ev("assistant_text"), 51)
    widget._tick_staleness(52)
    check("recovery hides the label, clears flow, stops probe, forgets the verdict", widget._stale_label.isHidden() and widget._flow_view.stale_seconds is None and not widget._probe.is_running() and widget._network_ok is None)


test_idle_is_never_stale()
test_waiting_on_user_suppresses_staleness()
test_widget_permission_wait_is_not_stale()
test_pending_turn_goes_stale_then_probe_worthy()
test_probe_result_wording()
test_unsolicited_turn_counts_and_unsolicited_complete_does_not_end_a_solicited_one()
test_session_error_clears()
test_delegated_task_keeps_things_outstanding_and_grace_follows()
test_plain_shell_tasks_are_ignored()
test_grace_not_started_while_another_agent_still_runs()
test_session_forwards_task_type()
test_probe_reports_and_stops()
test_probe_checker_exception_means_unreachable()
test_tcp_reachable_uses_a_bare_connect()
test_widget_label_flow_and_probe_lifecycle()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
