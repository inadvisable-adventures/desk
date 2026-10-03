"""Verifies TODO `a7d7c0a`: Claude (Desk) status events and the Claude
(Desk) Status widget. Real EventMediator, stub main window; no live GUI."""

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.window  # noqa: E402,F401

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from desk.claude_session import CLAUDE_DESK_STATUS_EVENT  # noqa: E402
from desk.event_mediator import EventMediator  # noqa: E402
from desk.shell import current_context  # noqa: E402

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


def _load(path, name):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


desk_mod = _load("widgets/claude_desk/widget.py", "cd_status_check")
status_mod = _load("widgets/claude_desk_status/widget.py", "cds_check")


class _FakeSession:
    def send_prompt(self, t):
        pass

    def stop(self):
        pass

    def respond_to_permission(self, *a):
        pass

    def respond_to_question(self, *a):
        pass


def make_publisher():
    mediator = EventMediator()
    mediator.subscribe("listener", CLAUDE_DESK_STATUS_EVENT)
    widget = desk_mod.build()
    widget._session = _FakeSession()
    return widget, mediator


def published(mediator):
    return [e.payload for e in mediator.drain("listener")]


def test_widget_json_and_event_name():
    manifest = json.loads((REPO_ROOT / "widgets/claude_desk_status/widget.json").read_text())
    check("status widget manifest is a python widget", manifest["kind"] == "python" and manifest["entry"] == "widget.py")
    check("event name is the documented one", CLAUDE_DESK_STATUS_EVENT == "desk.claude_desk.status_changed")


def test_no_publish_before_binding_and_bind_announces():
    widget, mediator = make_publisher()
    widget._set_busy(True)  # must not raise with no mediator
    check("unbound: nothing published, nothing raised", published(mediator) == [])
    widget._set_busy(False)
    widget.bind_event_mediator("inst-1", mediator)
    check("binding announces the current status once", published(mediator) == [{"busy": False, "waiting_on_user": False, "detail": None}])


def test_busy_transitions_publish_once_each():
    widget, mediator = make_publisher()
    widget.bind_event_mediator("inst-1", mediator)
    published(mediator)
    widget._set_busy(True)
    widget._set_busy(True)
    widget._set_busy(False)
    check("one publish per idle<->busy transition (duplicates deduped)", published(mediator) == [
        {"busy": True, "waiting_on_user": False, "detail": None},
        {"busy": False, "waiting_on_user": False, "detail": None},
    ])
    widget._set_busy(True)
    events = list(mediator.drain("listener"))
    check("sender id is the bound instance id", all(e.sender_instance_id == "inst-1" for e in events) and len(events) == 1)


def test_permission_edges():
    widget, mediator = make_publisher()
    widget.bind_event_mediator("inst-1", mediator)
    published(mediator)
    widget._on_permission_request("r1", "Bash", {"command": "ls"})
    widget._on_permission_request("r2", "Write", {})
    got = published(mediator)
    check("first pending permission publishes waiting_on_user with the tool name", got == [{"busy": False, "waiting_on_user": True, "detail": "Bash"}])
    widget._resolve_current_permission(True)
    check("resolving the first leaves another pending: detail moves on", published(mediator) == [{"busy": False, "waiting_on_user": True, "detail": "Write"}])
    widget._resolve_current_permission(False)
    check("last one resolved: waiting clears", published(mediator) == [{"busy": False, "waiting_on_user": False, "detail": None}])


def test_question_edges():
    widget, mediator = make_publisher()
    widget.bind_event_mediator("inst-1", mediator)
    published(mediator)
    widget._on_question_request("q1", {"questions": [{"question": "Which one?", "options": [{"label": "A"}, {"label": "B"}]}]})
    check("a pending question publishes waiting with its text", published(mediator) == [{"busy": False, "waiting_on_user": True, "detail": "Which one?"}])
    widget._skip_question()
    check("skipping clears waiting", published(mediator) == [{"busy": False, "waiting_on_user": False, "detail": None}])
    widget._on_question_request("q2", {"questions": [{"question": "Again?", "options": [{"label": "A"}]}]})
    published(mediator)
    widget._question_controls[0][2][0].setChecked(True)
    widget._submit_question()
    check("answering clears waiting", published(mediator) == [{"busy": False, "waiting_on_user": False, "detail": None}])


def test_permission_mid_turn_is_busy_and_waiting():
    widget, mediator = make_publisher()
    widget.bind_event_mediator("inst-1", mediator)
    widget._set_busy(True)
    published(mediator)
    widget._on_permission_request("r1", "Edit", {})
    check("the two booleans co-occur", published(mediator) == [{"busy": True, "waiting_on_user": True, "detail": "Edit"}])


# -- status widget ---------------------------------------------------------------


class _StubWindow:
    def __init__(self, widgets):
        self.widgets = widgets

    def get_state_dict(self):
        return {"widgets": self.widgets}


def test_describe_status():
    d = status_mod.describe_status
    check("None -> no status yet, not attention", d(None) == ("no status yet", False))
    check("idle", d({"busy": False, "waiting_on_user": False, "detail": None}) == ("Idle", False))
    check("working", d({"busy": True, "waiting_on_user": False, "detail": None}) == ("Working", False))
    check("waiting with detail wins over busy", d({"busy": True, "waiting_on_user": True, "detail": "Bash"}) == ("Waiting on you: Bash", True))
    check("waiting without detail", d({"busy": False, "waiting_on_user": True, "detail": None}) == ("Waiting on you", True))


def test_status_widget_end_to_end():
    previous_window = current_context.get_main_window()
    previous_zoomer = current_context.get_widget_zoomer()
    zooms = []
    windows = _StubWindow(
        [
            {"widget_id": "claude_desk", "instance_id": "a"},
            {"widget_id": "claude_desk", "instance_id": "b"},
            {"widget_id": "editor", "instance_id": "c"},
        ]
    )
    current_context.set_main_window(windows)
    current_context.set_widget_zoomer(lambda iid: zooms.append(iid) or True)
    try:
        mediator = EventMediator()
        widget = status_mod.build()
        widget.bind_event_mediator("status-1", mediator)
        check("only claude_desk instances listed", widget._list.count() == 2)
        check("an instance with no event yet shows 'no status yet'", all(status_mod.NO_STATUS_TEXT in widget._list.itemWidget(widget._list.item(i)).label.text() for i in range(2)))

        mediator.publish(CLAUDE_DESK_STATUS_EVENT, {"busy": True, "waiting_on_user": True, "detail": "Bash"}, "b")
        widget._subscription._poll()
        first = widget._list.itemWidget(widget._list.item(0)).label.text()
        check("a waiting instance sorts first and says so", "Waiting on you: Bash" in first)
        check("its row is emphasized", "font-weight" in widget._list.itemWidget(widget._list.item(0)).label.styleSheet())
        check("the summary counts waiting instances", "1 waiting on you" in widget._status_label.text())

        widget._list.itemWidget(widget._list.item(0)).findChild(status_mod.QPushButton).click()
        check("the eye button zooms to that instance", zooms == ["b"])

        windows.widgets = [w for w in windows.widgets if w["instance_id"] != "b"]
        widget._refresh(initial=True)
        check("a removed instance's row and stored status disappear", widget._list.count() == 1 and "b" not in widget._statuses)

        windows.widgets = []
        widget._refresh(initial=True)
        check("with none open the empty message shows", widget._status_label.text() == status_mod.NO_INSTANCES_STATUS and widget._list.count() == 0)
    finally:
        if previous_window is not None:
            current_context.set_main_window(previous_window)
        if previous_zoomer is not None:
            current_context.set_widget_zoomer(previous_zoomer)


test_widget_json_and_event_name()
test_no_publish_before_binding_and_bind_announces()
test_busy_transitions_publish_once_each()
test_permission_edges()
test_question_edges()
test_permission_mid_turn_is_busy_and_waiting()
test_describe_status()
test_status_widget_end_to_end()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
