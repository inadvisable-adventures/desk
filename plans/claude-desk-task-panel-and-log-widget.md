# Claude (Desk) background-tasks panel: framed items, log widget, sub-agent routing (TODO `90efef6`) (COMPLETED)

## Summary
(a) Replace the `_tasks_list` `QListWidget` with a scroll area of framed,
tail-previewed per-task items. (b) Hover "View Log" / double-click opens a
separate `claude_desk_task_log` widget instance (zooming to an existing one)
holding a read-only `HistoryView` of that task's log, kept live through the
event mediator. (c) Route a sub-agent's own tool activity into its task's log
instead of the main history.

## Affected files
- `src/desk/claude_task_panel.py` (new): `TaskPanel`, `TaskEntry`,
  `tail_preview`.
- `widgets/claude_desk_task_log/{widget.json,widget.py}` (new).
- `src/desk/claude_session.py`: forward `tool_use_id` in task patches; sub-agent
  (`parent_tool_use_id`) messages -> `session_event` only; new `UserMessage`
  branch for sub-agent traffic; `CLAUDE_DESK_TASK_LOG_EVENT`.
- `src/desk/shell/current_context.py`, `src/desk/shell/window.py`: new
  `background_task_log_opener` hook + `DeskWindow.open_background_task_log`.
- `widgets/claude_desk/widget.py`: panel, per-task logs, opener, routing.
- `tests/verify/verify_claude_desk_task_panel.py` (new), `TODO.md`,
  `design-docs/architecture.md`.

## Design
- **Per-task log** (`_task_logs[task_id]`, entries `{kind, text, ts, turn_id}`):
  fed by task events (start description, progress `last_tool_name`, terminal
  status + summary) and by routed sub-agent messages.
- **Panel entry**: header "[status] description", body = *tail* preview (last
  `PREVIEW_LINES` log lines; `tail_preview` helper, since `collapse_preview`
  shows the head, which is backwards for a task). No inline expansion by
  design. Hover reveals "View Log" (mirrors `HistoryEntry`'s reload-button
  mechanics); `mouseDoubleClickEvent` fires the same action. Fixed
  `TASKS_PANEL_HEIGHT` and symmetric frame resize are unchanged.
- **Opening the log**: `current_context.get_background_task_log_opener()` ->
  `DeskWindow.open_background_task_log(source_instance_id, task_id, title,
  entries)`, which places the new widget to the right of the source frame
  (like `_place_widget_chat_about`) and seeds it. The main widget keeps
  `task_id -> instance_id` and zooms to an existing instance (zoomer returns
  False if it was closed, then a new one is opened).
- **Live updates**: `CLAUDE_DESK_TASK_LOG_EVENT = "desk.claude_desk.task_log_appended"`,
  payload `{"task_id", "entry"}`, published per new log entry; the log widget
  subscribes and filters by both its task id and the sender (source) instance
  id. Same broadcast-and-filter shape as the status event (TODO `a7d7c0a`).
- **Persistence**: a task-log widget is ephemeral display of a live session's
  task; if restored from a saved desk it shows "no log available". Not
  persisted further in this pass.
- **(c) Routing**: `AssistantMessage`/`UserMessage` both carry
  `parent_tool_use_id` (the spawning `Task` call's `tool_use_id`, also on
  `TaskStartedMessage.tool_use_id`). `ClaudeSession` now handles
  `UserMessage` blocks that carry a `parent_tool_use_id` (previously the whole
  type was ignored) and, for any message with a parent id, emits only
  `session_event` (with `data["parent_tool_use_id"]`) and not the legacy
  signals. The widget routes by matching the id to a known task's
  `tool_use_id`; **no match -> falls back to the main history** (tagged as
  sub-agent output) so nothing is lost. Not confirmed against a live Task-tool
  run (no live API here): both message types are handled so whichever fires
  works. Nesting: a nested `Task` produces its own `TaskStartedMessage`, so it
  gets its own task entry/log and its tool traffic routes there; nothing is
  rolled up into the parent. UserMessage handling without a parent id is
  unchanged (still ignored) -- see the note to the user about that.

## Verification
Pure-Qt tests for `tail_preview`/panel, session routing with synthetic SDK
messages, log widget filtering/seeding, opener hook and dedup/zoom in the
main widget, window placement via a fake. Whole suite. No live GUI/API.
