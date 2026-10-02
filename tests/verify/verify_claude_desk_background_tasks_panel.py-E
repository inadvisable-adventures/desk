# TODO f4a7872: the Claude (Desk) widget's background-tasks panel.
# Follows verify_claude_desk_widget.py's own established shape -- a
# real widget built via module.build(), real claude_agent_sdk Task*
# message instances fed through a real ClaudeSession._handle_message,
# no network calls.
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

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


def _load_widget_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "claude_desk_widget", REPO_ROOT / "widgets" / "claude_desk" / "widget.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_claude_session_emits_task_event_for_each_message_type():
    import claude_agent_sdk as sdk

    from desk.claude_session import ClaudeSession

    session = ClaudeSession()
    seen = []
    session.task_event.connect(lambda task_id, patch: seen.append((task_id, patch)))

    started = sdk.TaskStartedMessage(
        subtype="task_started",
        data={},
        task_id="t1",
        description="run the build",
        uuid="u1",
        session_id="s1",
    )
    session._handle_message(started)
    check(
        "TaskStartedMessage emits description+running status",
        seen[-1] == ("t1", {"description": "run the build", "status": "running"}),
    )

    progress = sdk.TaskProgressMessage(
        subtype="task_progress",
        data={},
        task_id="t1",
        description="still building",
        usage={"total_tokens": 10, "tool_uses": 1, "duration_ms": 100},
        uuid="u2",
        session_id="s1",
        last_tool_name="Bash",
    )
    session._handle_message(progress)
    check(
        "TaskProgressMessage emits description+running status+last_tool_name",
        seen[-1] == ("t1", {"description": "still building", "status": "running", "last_tool_name": "Bash"}),
    )

    notification = sdk.TaskNotificationMessage(
        subtype="task_notification",
        data={},
        task_id="t1",
        status="completed",
        output_file="/tmp/out.txt",
        summary="build succeeded",
        uuid="u3",
        session_id="s1",
    )
    session._handle_message(notification)
    check(
        "TaskNotificationMessage emits status+summary",
        seen[-1] == ("t1", {"status": "completed", "summary": "build succeeded"}),
    )

    updated = sdk.TaskUpdatedMessage(
        subtype="task_updated",
        data={},
        task_id="t2",
        patch={"end_time": "now"},
        status="killed",
        session_id="s1",
        uuid="u4",
    )
    session._handle_message(updated)
    check(
        "TaskUpdatedMessage folds patch.status into the emitted patch",
        seen[-1] == ("t2", {"end_time": "now", "status": "killed"}),
    )

    updated_no_status = sdk.TaskUpdatedMessage(
        subtype="task_updated",
        data={},
        task_id="t2",
        patch={"end_time": "later"},
        status=None,
        session_id="s1",
        uuid="u5",
    )
    session._handle_message(updated_no_status)
    check(
        "TaskUpdatedMessage with status=None leaves it out of the emitted patch",
        seen[-1] == ("t2", {"end_time": "later"}),
    )


def test_panel_hidden_by_default_and_toggle_updates_label():
    # isHidden(), not isVisible(): this standalone widget is never
    # actually .show()n in this headless/offscreen test, so isVisible()
    # would report False regardless of setVisible calls (it also
    # depends on every ancestor being shown) -- isHidden() reflects
    # only this specific widget's own explicit visibility flag, which
    # is exactly what _on_tasks_toggled's setVisible calls above
    # toggle.
    module = _load_widget_module()
    widget = module.build()
    check("tasks list starts hidden", widget._tasks_list.isHidden() is True)
    check("toggle button starts unchecked", widget._tasks_toggle_button.isChecked() is False)
    check(
        "toggle label starts as bare 'Background Tasks' plus a collapsed arrow",
        widget._tasks_toggle_button.text() == "Background Tasks ▸",
    )

    widget._tasks_toggle_button.setChecked(True)
    check("checking the toggle shows the list", widget._tasks_list.isHidden() is False)
    check(
        "toggle label switches to the expanded arrow",
        widget._tasks_toggle_button.text() == "Background Tasks ▾",
    )


def test_task_event_merge_never_overwrites_with_none_and_updates_running_count():
    module = _load_widget_module()
    widget = module.build()

    widget._on_task_event("t1", {"description": "build", "status": "running"})
    check(
        "running count reflects one non-terminal task",
        widget._tasks_toggle_button.text().startswith("Background Tasks (1 running)"),
    )
    check("list shows the running task", widget._tasks_list.count() == 1)
    check(
        "list item text includes status and description",
        widget._tasks_list.item(0).text() == "[running] build",
    )

    # A notification-only patch (no description re-sent) must not blank
    # out the description already recorded above.
    widget._on_task_event("t1", {"status": "completed", "summary": "done", "last_tool_name": None})
    check(
        "description survives a later patch that omits it",
        widget._background_tasks["t1"]["description"] == "build",
    )
    check(
        "a None-valued field in the patch is not written into the task dict",
        "last_tool_name" not in widget._background_tasks["t1"],
    )
    check(
        "running count drops to zero once the task reaches a terminal status",
        widget._tasks_toggle_button.text() == "Background Tasks ▸",
    )
    check(
        "list item reflects the merged summary",
        widget._tasks_list.item(0).text() == "[completed] build — done",
    )


def test_tasks_toggle_calls_height_adjuster_symmetrically():
    from desk.shell import current_context

    module = _load_widget_module()
    widget = module.build()
    widget._session_id = "fake-session-id"

    calls = []
    current_context.set_widget_height_adjuster(lambda instance_id, delta: calls.append((instance_id, delta)))
    try:
        widget._tasks_toggle_button.setChecked(True)
        check(
            "expanding calls the height adjuster with +TASKS_PANEL_HEIGHT",
            calls == [("fake-session-id", module.TASKS_PANEL_HEIGHT)],
        )
        widget._tasks_toggle_button.setChecked(False)
        check(
            "collapsing calls it again with the exact same magnitude, negated",
            calls == [("fake-session-id", module.TASKS_PANEL_HEIGHT), ("fake-session-id", -module.TASKS_PANEL_HEIGHT)],
        )
    finally:
        current_context.set_widget_height_adjuster(None)


def test_tasks_toggle_is_a_no_op_without_a_session_id_or_hook():
    from desk.shell import current_context

    current_context.set_widget_height_adjuster(None)
    module = _load_widget_module()
    widget = module.build()
    check("session id is None before start_session runs", widget._session_id is None)
    widget._tasks_toggle_button.setChecked(True)  # must not raise
    check("toggling without a session id/hook doesn't raise", True)


test_claude_session_emits_task_event_for_each_message_type()
test_panel_hidden_by_default_and_toggle_updates_label()
test_task_event_merge_never_overwrites_with_none_and_updates_running_count()
test_tasks_toggle_calls_height_adjuster_symmetrically()
test_tasks_toggle_is_a_no_op_without_a_session_id_or_hook()

print(f"\n{passed} passed, {failed} failed")
