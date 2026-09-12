# Background-tasks monitoring panel for the Claude (Desk) widget (TODO `f4a7872`) (COMPLETED)

## Summary

The Claude Agent SDK reports a running session's background tasks (a
backgrounded Bash command, a subagent/Task run, ...) as a stream of
`system` messages -- `TaskStartedMessage` / `TaskProgressMessage` /
`TaskNotificationMessage` / `TaskUpdatedMessage` (all subclasses of
`SystemMessage`). `ClaudeSession._handle_message`
(`src/desk/claude_session.py`) currently only branches on
`AssistantMessage`/`ResultMessage` -- every one of these is silently
dropped, so the Claude (Desk) widget (`widgets/claude_desk/widget.py`)
today has no visibility at all into a session's own background work.

Adds a dedicated, collapsible panel at the bottom of the widget listing
each known background task and its current status, toggled open/closed
by a header button. Expanding it grows the *widget's own placed frame*
by the panel's height (rather than squeezing the existing history/
prompt area down to make room), and collapsing it shrinks the frame
back by the same amount.

## Affected files

- `src/desk/claude_session.py` -- new `task_event` signal, `_handle_message`
  gains branches for the four `Task*Message` subclasses, and a
  re-exported `TERMINAL_TASK_STATUSES` constant (so `widget.py` never
  needs to import `claude_agent_sdk` directly, matching this module's
  existing role as the one place that import lives).
- `src/desk/shell/current_context.py` -- new `widget_height_adjuster`
  hook (get/set pair, same minimal shape as every other hook here).
- `src/desk/shell/window.py` -- `DeskWindow.adjust_widget_instance_height`
  (the hook's real implementation) and its wiring into
  `current_context.set_widget_height_adjuster` in `__init__`.
- `widgets/claude_desk/widget.py` -- the panel itself (a `QListWidget`
  plus a toggle `QPushButton`), `_on_task_event`, `_refresh_tasks_list`.
- `tests/verify/verify_claude_desk_background_tasks_panel.py` -- new.

## Design decisions

- **One combined `task_event(task_id: str, patch: dict)` signal**,
  not four separate ones -- every `Task*Message` subtype ultimately
  just updates *some* fields of *one* tracked task, so the widget-side
  handling is a single `dict.update`-shaped merge regardless of which
  underlying message produced it. `patch` values are `None`-filtered
  before merging (a message that doesn't carry a given field, e.g.
  `TaskStartedMessage` has no `summary`, must never blank out a value
  set earlier by another message for the same task).
- **The panel is rebuilt from scratch on every event**
  (`_refresh_tasks_list` clears and repopulates the `QListWidget`),
  not incrementally patched -- the number of concurrent background
  tasks in real usage is small, and this avoids a second, easy-to-drift
  bookkeeping structure (task_id -> `QListWidgetItem`) for no real
  benefit at this scale.
- **Fixed panel height (`TASKS_PANEL_HEIGHT`), not a dynamic
  `sizeHint()`** -- the panel's own list can scroll internally past
  that height. This keeps the expand/collapse frame-resize delta
  perfectly symmetric (the same constant both ways) regardless of how
  many tasks have accumulated, which a content-driven height would not
  guarantee.
- **A new `current_context` hook for frame-height adjustment**, mirroring
  every other "let a `python` widget reach `DeskWindow` state without
  importing `desk.shell.window` directly" hook already documented in
  that module's own docstring -- `adjust_widget_instance_height(instance_id,
  delta)` finds the frame via the existing `find_frame_by_instance_id`,
  then resizes its `graphicsProxyWidget()` (the same object
  `canvas.py`'s own manual-resize-drag handling already resizes),
  clamped to `widget_frame.MIN_HEIGHT` the same way manual dragging is.
  Delta-based (not "resize to absolute height") since the widget itself
  is the one that knows the panel's own fixed height and doesn't need
  to know its frame's current size.
- **Completed/failed background tasks stay listed, not cleared** -- a
  first pass; useful as a short recent-activity log, and nothing in
  the request asks for pruning. A follow-up (cap the list / clear on
  demand) is a small addition if this proves noisy in practice, not
  designed here.
- **Not folded into the existing `_history` transcript** -- the whole
  point of a separate panel is a place to look that isn't the same
  scrolling tool-call/assistant-text log; background task events are
  never also appended to `_history`.

## Step-by-step implementation

1. `claude_session.py`: add `TERMINAL_TASK_STATUSES = sdk.TERMINAL_TASK_STATUSES`
   at module level; add `task_event = pyqtSignal(str, dict)`; in
   `_handle_message`, add `elif isinstance(message, sdk.TaskStartedMessage)`
   / `TaskProgressMessage` / `TaskNotificationMessage` / `TaskUpdatedMessage`
   branches, each emitting `task_event(message.task_id, {...})` with the
   fields relevant to that subtype (`description`/`status` for started;
   `description`/`status`/`last_tool_name` for progress; `status`/`summary`
   for notification; `patch` merged with an explicit `status` key for
   updated).
2. `current_context.py`: `_widget_height_adjuster` module global,
   `set_widget_height_adjuster`/`get_widget_height_adjuster`, plus a
   docstring paragraph matching the existing ones.
3. `window.py`: import `MIN_HEIGHT` alongside the existing `WidgetFrame`
   import; `adjust_widget_instance_height(self, instance_id, delta)`
   next to `set_widget_subtitle`; wire
   `current_context.set_widget_height_adjuster(self.adjust_widget_instance_height)`
   into `__init__`'s existing hook-wiring block.
4. `widget.py`: `TASKS_PANEL_HEIGHT = 140` constant;
   `self._background_tasks: dict[str, dict] = {}`; a toggle
   `QPushButton` in `top_row`; a `QListWidget` (`setFixedHeight`,
   initially hidden) appended after `prompt_row` in the main layout;
   `_on_task_event`/`_refresh_tasks_list`/`_on_tasks_toggled` (the last
   calls `current_context.get_widget_height_adjuster()`, a no-op if
   unset or if `self._session_id` isn't known yet).
5. New verify script (below); run the full `tests/verify/` suite.

## Key tradeoffs

- The panel's toggle state and accumulated task list are not persisted
  across a Desk reload (unlike TODO `1ceb701`'s combo-box persistence)
  -- background tasks are inherently tied to the live process of a
  running session, so nothing meaningful survives a reload to restore
  anyway; the panel simply starts empty and closed on every fresh
  connect, same as `_history` already does.

## Verification

New `tests/verify/verify_claude_desk_background_tasks_panel.py`,
following `verify_claude_desk_widget.py`'s own established shape (a
real widget built via `module.build()`, a `_FakeSession`/direct signal
emission standing in for a live `ClaudeSDKClient`, no network calls):
- `ClaudeSession.task_event` fires with the right merged fields for a
  real instance of each of the four `Task*Message` subclasses fed
  through `_handle_message` directly.
- The widget's tasks panel is hidden by default; the toggle button
  shows/hides it and updates its own running-count label; toggling
  calls the `current_context` height-adjuster hook with `+`/`-
  TASKS_PANEL_HEIGHT` symmetrically.
- A patch missing a field (e.g. a bare `TaskNotificationMessage` with
  no prior `TaskStartedMessage` for that `task_id`) never raises and
  never overwrites an already-set field with `None`.
- Full `tests/verify/` regression suite passes.
