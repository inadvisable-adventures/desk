"""Verifies TODO `90efef6`: framed tail-previewed task items, the
background-task log widget (opened via a current_context hook, live via the
event mediator), and routing of sub-agent output into task logs. No live
API/GUI session."""

import os
import sys
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.window  # noqa: E402,F401

from PyQt6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PyQt6.QtGui import QMouseEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

import claude_agent_sdk as sdk  # noqa: E402

from desk.claude_session import CLAUDE_DESK_TASK_LOG_EVENT, ClaudeSession  # noqa: E402
from desk.claude_task_panel import NO_LOG_TEXT, TaskPanel, tail_preview  # noqa: E402
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


desk_mod = _load("widgets/claude_desk/widget.py", "tp_desk")
log_mod = _load("widgets/claude_desk_task_log/widget.py", "tp_log")


class _FakeSession:
    def send_prompt(self, t):
        pass

    def stop(self):
        pass


def ev(kind, data, turn_id=1, solicited=True):
    return {"seq": 1, "ts": 1.0, "turn_id": turn_id, "solicited": solicited, "kind": kind, "data": data}


# -- tail preview + panel ------------------------------------------------------------


def test_tail_preview():
    check("empty log reads as no activity", tail_preview([]) == NO_LOG_TEXT)
    check("a short log shows everything", tail_preview(["a", "b"]) == "a\nb")
    check("a long log shows the LAST lines with a leading ellipsis", tail_preview(["1", "2", "3", "4", "5"]) == "…\n3\n4\n5")
    check("a very long line is capped", tail_preview(["x" * 1000]).endswith("…") and len(tail_preview(["x" * 1000])) < 400)


def test_panel_entries_and_signals():
    panel = TaskPanel()
    entry = panel.set_task("t1", {"status": "running", "description": "build"}, ["one", "two", "three", "four"])
    check("one framed entry per task", panel.count() == 1 and panel.entry("t1") is entry)
    check("title is [status] description", entry.title_text() == "[running] build")
    check("body is the tail of the log, not the head", entry.preview_text() == "…\ntwo\nthree\nfour")
    panel.set_task("t1", {"status": "completed", "description": "build"}, ["one", "two"])
    check("updating reuses the same entry", panel.count() == 1 and entry.title_text() == "[completed] build")
    panel.set_task("t2", {}, [])
    check("a task with no description falls back to its id, status to pending", panel.entry("t2").title_text() == "[pending] t2")

    requests = []
    panel.view_log_requested.connect(requests.append)
    check("View Log is hidden until hover", entry._view_log_button.isHidden())
    entry.enterEvent(None)
    check("hover reveals it", not entry._view_log_button.isHidden())
    entry._view_log_button.click()
    check("clicking View Log requests this task's log", requests == ["t1"])
    entry.leaveEvent(None)
    check("leaving hides it again", entry._view_log_button.isHidden())
    press = QMouseEvent(QEvent.Type.MouseButtonDblClick, QPointF(5, 5), QPointF(5, 5), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    entry.mouseDoubleClickEvent(press)
    check("double-click requests the same thing", requests == ["t1", "t1"])
    check("the preview is selectable content, the title chrome is not", bool(entry._preview.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse) and not (entry._title.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse))


# -- session routing ---------------------------------------------------------------------


def test_session_routes_sub_agent_output_to_events_only():
    session = ClaudeSession()
    events, texts, tools, results = [], [], [], []
    session.session_event.connect(events.append)
    session.assistant_text.connect(texts.append)
    session.tool_use.connect(lambda *a: tools.append(a))
    session.tool_result.connect(lambda *a: results.append(a))
    session._handle_message(
        sdk.AssistantMessage(
            content=[sdk.TextBlock(text="sub says"), sdk.ToolUseBlock(id="u1", name="Read", input={"p": 1})],
            model="m",
            parent_tool_use_id="toolu_task",
        ),
        1,
        True,
    )
    session._handle_message(
        sdk.UserMessage(content=[sdk.ToolResultBlock(tool_use_id="u1", content="file body")], parent_tool_use_id="toolu_task"),
        1,
        True,
    )
    check("no legacy signals fire for sub-agent output", texts == [] and tools == [] and results == [])
    check("session_events carry the parent id", [(e["kind"], e["data"]["parent_tool_use_id"]) for e in events] == [("assistant_text", "toolu_task"), ("tool_use", "toolu_task"), ("tool_result", "toolu_task")])
    events.clear()
    session._handle_message(sdk.AssistantMessage(content=[sdk.TextBlock(text="main")], model="m"), 1, True)
    check("top-level output is unchanged: legacy signal and no parent key", texts == ["main"] and "parent_tool_use_id" not in events[0]["data"])
    events.clear()
    session._handle_message(sdk.UserMessage(content=[sdk.ToolResultBlock(tool_use_id="x", content="r")]), 1, True)
    check("a top-level UserMessage's tool result now surfaces (TODO 10b4d7d), without a parent key", [(e["kind"], "parent_tool_use_id" in e["data"]) for e in events] == [("tool_result", False)])
    events.clear()
    session._handle_message(sdk.UserMessage(content="plain text", parent_tool_use_id="toolu_task"), 1, True)
    check("a string-content sub-agent UserMessage is ignored without error", events == [])


def test_task_started_forwards_tool_use_id():
    session = ClaudeSession()
    seen = []
    session.task_event.connect(lambda tid, patch: seen.append(patch))
    session._handle_message(sdk.TaskStartedMessage(subtype="task_started", data={}, task_id="t", description="d", uuid="u", session_id="s", tool_use_id="toolu_task", task_type="local_agent"), 1, True)
    check("tool_use_id is in the patch", seen[0]["tool_use_id"] == "toolu_task")


# -- main widget ----------------------------------------------------------------------------


def make_widget():
    widget = desk_mod.build()
    widget._session = _FakeSession()
    return widget


def test_task_events_build_a_log_and_publish():
    widget = make_widget()
    mediator = EventMediator()
    mediator.subscribe("listener", CLAUDE_DESK_TASK_LOG_EVENT)
    widget.bind_event_mediator("src-1", mediator)
    mediator.drain("listener")
    widget._on_task_event("t1", {"description": "build", "status": "running", "tool_use_id": "toolu_task"})
    widget._on_task_event("t1", {"status": "running", "last_tool_name": "Bash"})
    widget._on_task_event("t1", {"status": "running", "last_tool_name": "Bash"})
    widget._on_task_event("t1", {"status": "completed", "summary": "all good"})
    texts = [e["text"] for e in widget._task_logs["t1"]]
    check("start, tool (deduped), terminal status+summary are logged", texts == ["started: build", "Bash", "completed: all good"])
    published = mediator.drain("listener")
    check("each new entry is published with the task id and sender", [(p.payload["task_id"], p.payload["entry"]["text"], p.sender_instance_id) for p in published] == [("t1", t, "src-1") for t in texts])
    check("the panel entry previews the log's tail", widget._tasks_panel.entry("t1").preview_text() == "started: build\nBash\ncompleted: all good")


def test_sub_agent_events_route_to_the_owning_task_or_fall_back():
    widget = make_widget()
    widget._on_task_event("t1", {"description": "research", "status": "running", "tool_use_id": "toolu_task"})
    widget._on_session_event(ev("tool_use", {"id": "u1", "name": "Read", "input": {"path": "x"}, "parent_tool_use_id": "toolu_task"}))
    widget._on_session_event(ev("tool_result", {"tool_use_id": "u1", "content": "body", "is_error": False, "parent_tool_use_id": "toolu_task"}))
    widget._on_session_event(ev("assistant_text", {"text": "found it", "parent_tool_use_id": "toolu_task"}))
    log = widget._task_logs["t1"]
    check("sub-agent traffic lands in the task's log", [(e["kind"], e["text"]) for e in log[1:]] == [("tool", "Read(path='x')"), ("tool_result", "body"), ("assistant", "found it")])
    check("and not in the main history", widget._history.entries() == [])

    widget._on_session_event(ev("assistant_text", {"text": "orphan", "parent_tool_use_id": "toolu_unknown"}))
    (orphan,) = widget._history.entries()
    check("an unmatched parent id falls back to the main history, tagged sub-agent", orphan.text == "orphan" and orphan.meta.source == "sub-agent")
    widget._on_session_event(ev("tool_result", {"tool_use_id": "z", "content": "bad", "is_error": True, "parent_tool_use_id": "toolu_task"}))
    check("sub-agent tool errors keep their kind", widget._task_logs["t1"][-1]["kind"] == "tool_error")


def test_open_task_log_hook_dedup_and_zoom():
    widget = make_widget()
    widget._session_id = "src-1"
    widget._on_task_event("t1", {"description": "build", "status": "running"})
    opened, zooms = [], []
    states = {"zoom_ok": True}
    previous_open = current_context.get_background_task_log_opener()
    previous_zoom = current_context.get_widget_zoomer()
    current_context.set_background_task_log_opener(lambda src, tid, title, entries: opened.append((src, tid, title, entries)) or f"log-{len(opened)}")
    current_context.set_widget_zoomer(lambda iid: zooms.append(iid) or states["zoom_ok"])
    try:
        widget._tasks_panel.view_log_requested.emit("t1")
        check("first request opens a log with the source id, task id, title and entries", opened[0][:3] == ("src-1", "t1", "build [running]") and opened[0][3][0]["text"] == "started: build")
        widget._tasks_panel.view_log_requested.emit("t1")
        check("a second request zooms to the existing instance instead", len(opened) == 1 and zooms == ["log-1"])
        states["zoom_ok"] = False
        widget._tasks_panel.view_log_requested.emit("t1")
        check("if that instance is gone (zoom fails), a new one is opened", len(opened) == 2 and widget._task_log_instances["t1"] == "log-2")
    finally:
        if previous_open is not None:
            current_context.set_background_task_log_opener(previous_open)
        if previous_zoom is not None:
            current_context.set_widget_zoomer(previous_zoom)


# -- log widget ----------------------------------------------------------------------------------


def test_log_widget_seeds_and_filters_live_updates():
    widget = log_mod.build()
    check("unseeded widget explains itself", "No log available" in widget._title.text())
    mediator = EventMediator()
    widget.bind_event_mediator("log-1", mediator)
    widget.seed("src-1", "t1", "build [running]", [{"kind": "notice", "text": "started: build", "ts": 5.0, "turn_id": 2}])
    (first,) = widget._history.entries()
    check("seeded entries render with kind, time and turn", first.text == "started: build" and first.meta.ts == 5.0 and first.meta.turn_id == 2)
    check("title shows the task", widget._title.text() == "build [running]")

    entry = {"kind": "tool", "text": "Bash", "ts": 6.0, "turn_id": 2}
    mediator.publish(CLAUDE_DESK_TASK_LOG_EVENT, {"task_id": "t1", "entry": entry}, "src-1")
    mediator.publish(CLAUDE_DESK_TASK_LOG_EVENT, {"task_id": "other", "entry": entry}, "src-1")
    mediator.publish(CLAUDE_DESK_TASK_LOG_EVENT, {"task_id": "t1", "entry": entry}, "src-2")
    widget._subscription._poll()
    check("only this task's entries from this source are appended", [e.text for e in widget._history.entries()] == ["started: build", "Bash"])
    widget._add({"kind": "bogus", "text": "x"})
    check("an unknown kind degrades to a plain notice", widget._history.entries()[-1].meta.kind == "notice")


# -- window placement --------------------------------------------------------------------------------


def test_window_open_background_task_log():
    DeskWindow = desk.shell.window.DeskWindow
    seeded, placed = [], []

    class _Content:
        def seed(self, *a):
            seeded.append(a)

    class _Host:
        pass

    host = _Host()
    host.current = _Content()
    frame = types.SimpleNamespace(instance_id="log-9", content=host)
    source_proxy = types.SimpleNamespace(sceneBoundingRect=lambda: types.SimpleNamespace(right=lambda: 500.0, top=lambda: 40.0))
    source = types.SimpleNamespace(graphicsProxyWidget=lambda: source_proxy)
    info = types.SimpleNamespace(default_size=(460, 360))
    fake = types.SimpleNamespace(
        _widgets={"claude_desk_task_log": info},
        find_frame_by_instance_id=lambda iid: source if iid == "src-1" else None,
        _place_widget=lambda wid, w, pos, size: placed.append((wid, pos, size)) or frame,
    )
    # isinstance(frame.content, PythonWidgetHost) -- stand in with the real class
    real_host_cls = desk.shell.window.PythonWidgetHost
    desk.shell.window.PythonWidgetHost = _Host
    try:
        result = DeskWindow.open_background_task_log(fake, "src-1", "t1", "title", [{"text": "x"}])
    finally:
        desk.shell.window.PythonWidgetHost = real_host_cls
    check("placed the task-log widget just right of the source frame", placed == [("claude_desk_task_log", (524.0, 40.0), (460, 360))])
    check("seeded it with source, task, title and entries", seeded == [("src-1", "t1", "title", [{"text": "x"}])])
    check("returned the new instance id", result == "log-9")
    check("an unknown widget id (not in the catalog) returns None", DeskWindow.open_background_task_log(types.SimpleNamespace(_widgets={}), "src-1", "t", "x", []) is None)


def test_manifest():
    import json

    manifest = json.loads((REPO_ROOT / "widgets/claude_desk_task_log/widget.json").read_text())
    check("task-log manifest is a python widget", manifest["kind"] == "python" and manifest["entry"] == "widget.py")


test_tail_preview()
test_panel_entries_and_signals()
test_session_routes_sub_agent_output_to_events_only()
test_task_started_forwards_tool_use_id()
test_task_events_build_a_log_and_publish()
test_sub_agent_events_route_to_the_owning_task_or_fall_back()
test_open_task_log_hook_dedup_and_zoom()
test_log_widget_seeds_and_filters_live_updates()
test_window_open_background_task_log()
test_manifest()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
