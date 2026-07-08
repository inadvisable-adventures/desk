# Claude widget: persist the session and resume it on reload (COMPLETED)

TODO `1d7331b`.

## Summary

"Update the claude widget to monitor the name/id of the claude session
and store that as part of the widget state so that it can be resumed on
reload; if there is no better way to do that, write instructions in the
initial Desk prompt that claude should write a temp file … that Desk can
monitor; if resuming a session on reload, don't pass the initial Desk
prompt."

There **is** a better way than monitoring/scraping the session id: the
`claude` CLI accepts `--session-id <uuid>` ("Use a specific session ID
for the conversation (must be a valid UUID)") and `--resume <uuid>`. So
Desk can *assign* the session id up front instead of discovering it
after the fact, which sidesteps the whole "monitor a temp file" fallback
the TODO offers.

And Desk already has a persisted, per-widget-instance identifier that
survives save/reload: the widget's Desk `instance_id` (stored in
`WidgetState`, restored by `_load_desk_widgets`). Making a claude
widget's `instance_id` double as its claude session UUID is the exact
same "instance_id-as-durable-identity" pattern the Temporary UI widgets
already use (TODO a02b001) — so **no new `WidgetState` payload field is
needed**. On first placement the widget launches `claude --session-id
<instance_id> "<prompt>"`; on reload the restored widget (same
`instance_id`) launches `claude --resume <instance_id>` with no prompt.

## Design

### `widgets/claude/widget.py`

- Introduce a small `ClaudeWidget(TerminalWidget)` subclass (spawns
  `bash`, like today) with a `start_session(session_id: str, resume:
  bool)` method:
  - `resume=False`: `claude --session-id <session_id> "<prompt>"` (the
    existing Desk prompt).
  - `resume=True`: `claude --resume <session_id>` (no prompt, per the
    TODO).
  - Both typed via the existing `type_into_shell`, same as today.
- `build()` now returns a bare `ClaudeWidget()` and **does not** type
  any `claude` command itself — the command is issued by the post-build
  binding below, which is the only place that knows the session id and
  whether this is a fresh launch or a resume. (Mirrors how Temporary UI
  widgets are inert until `set_source_file` is called on them post-build
  by `_bind_temp_ui_widget`.)

### `src/desk/shell/window.py`

- New `CLAUDE_WIDGET_ID = "claude"` constant.
- `_place_widget` gains a `restore: bool = False` param:
  - At the top: if this is a claude widget and no explicit
    `instance_id` was given (a fresh placement), generate a full
    `str(uuid.uuid4())` as the instance_id — claude's `--session-id`
    needs a valid UUID, and the default `instance_id` factory only makes
    an 8-hex-char id. A restore passes the saved (already-full-uuid)
    instance_id through unchanged.
  - After the frame is built: if this is a claude widget, call
    `_bind_claude_widget(frame, resume=restore)`.
- New `_bind_claude_widget(frame, resume)`: if `frame.content` is a
  `PythonWidgetHost` whose `.current` has a `start_session` method,
  call `content.start_session(frame.instance_id, resume=resume)`
  (duck-typed, so window.py needn't import the widget class — same
  style as `_bind_temp_ui_widget`).
- `_load_desk_widgets` calls `_place_widget(..., restore=True)` for the
  saved widgets it re-creates, so a restored claude widget resumes
  rather than starting fresh. All other placement paths
  (`_on_widget_add_requested` right-click add, Bridge `open_widget`)
  default to `restore=False` → a fresh session.

## Scope / limitations

- **Hot reload of `widgets/claude/widget.py` mid-session**: as with the
  Temporary UI widgets, a hot-reload rebuild re-runs `build()` but not
  the post-build binding, so it yields a fresh blank shell with no
  `claude` relaunch (the previous PTY/session is gone either way, since
  a rebuild makes a brand-new `TerminalWidget`). A developer-only edge
  case; noted in `PARKINGLOT.md`, consistent with the existing temp-UI
  limitation.
- **Resuming a session that was never actually created** (claude never
  ran, or the session file is gone): `claude --resume <uuid>` just
  prints its own error into the terminal; the user can recover
  manually. Best-effort resume, matching the TODO's intent.
- The "have claude write a temp file with its session id" fallback in
  the TODO is deliberately **not** implemented — `--session-id`/
  `--resume` make it unnecessary.

## Affected files

- `widgets/claude/widget.py` — `ClaudeWidget`, `start_session`,
  `build()`.
- `src/desk/shell/window.py` — `CLAUDE_WIDGET_ID`, `_place_widget`
  (`restore` param + uuid generation + binding call),
  `_bind_claude_widget`, `_load_desk_widgets`.
- `design-docs/architecture.md` — update the Claude Widget component
  entry to describe session assignment + resume-on-reload.

## Verification

All headless, against real PTYs, with a fake `claude` script on `PATH`
(mirroring `plans/claude-widget.md`'s approach), and spying on
`ClaudeWidget.start_session`/`type_into_shell` to capture the exact
command issued:

- Fresh `start_session(uuid, resume=False)` types `claude --session-id
  <uuid> "<prompt>"` (prompt present, correct doc path).
- `start_session(uuid, resume=True)` types `claude --resume <uuid>`
  with **no** prompt.
- Full-app: placing a claude widget in a real `DeskWindow` (fresh) gives
  it a full-uuid `instance_id` and issues a `--session-id <that uuid>`
  launch; saving the desk and constructing a **new** `DeskWindow` over
  the same `.desk` file restores the widget with the same `instance_id`
  and issues `--resume <that same uuid>` with no prompt.
- Regression: the console widget (which shares `TerminalWidget`) still
  spawns a plain bash shell and is unaffected; a fresh claude widget's
  instance_id is a valid UUID string.

## Status

**Completed.** Implemented and verified headlessly as described above:
`ClaudeWidget.start_session` issuing the right fresh (`--session-id` +
prompt) vs. resume (`--resume`, no prompt) command and `build()` alone
issuing nothing; and a full-app `DeskWindow` flow where the demo-seeded
claude widget gets a valid-UUID `instance_id` and launches
`--session-id <that uuid>`, then after save + a brand-new `DeskWindow`
over the same `.desk` file the restored widget keeps the same
`instance_id` and launches `--resume <that same uuid>` with no prompt,
with the console widget confirmed unaffected. `design-docs
/architecture.md`'s Claude Widget entry updated; the hot-reload
post-build-binding limitation logged in `PARKINGLOT.md`.
