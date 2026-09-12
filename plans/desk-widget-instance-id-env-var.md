# Widget instance id via `DESK_WIDGET_INSTANCE_ID` env var (TODO `b9d3de5`)

## Summary

Give an in-Desk agent (hosted by either the `claude` PTY-based widget
or the `Claude (Desk)` SDK-based widget) a documented way to learn its
own placed widget's instance id, as a static, launch-time environment
variable (`DESK_WIDGET_INSTANCE_ID`) rather than a sentence folded into
the initial prompt -- per the 2026-09-01 discussion recorded on the
TODO item, an env var costs nothing per turn, survives context
compaction, and is trivially extensible to more static self-facts
later without further prompt bloat.

Both widget kinds already thread `frame.instance_id` down to their
`start_session(session_id, ...)` call as `session_id`
(`DeskWindow._bind_claude_widget`/`_bind_claude_desk_widget`,
`src/desk/shell/window.py:648-692`, per the existing comment that "a
claude/claude_desk widget's instance_id doubles as its session_id") --
so `session_id` is exactly the value to expose, at both existing call
sites, with no new plumbing needed to derive it.

Only the *mechanism* needs documenting, not the value itself (the
value is already conveyed for free, by being a real env var) -- one
new section in `desk-temporary-ui.md` (the doc every Claude-hosted
widget's initial prompt already unconditionally points at) covers it,
so it's future-proof against more such env vars being added later
without needing a new prompt sentence each time.

## Affected files

- `src/desk/claude_session.py` -- `ClaudeSession._connect_and_maybe_prompt`
  gains `env={"DESK_WIDGET_INSTANCE_ID": session_id}` on the
  `sdk.ClaudeAgentOptions(...)` it builds.
- `widgets/claude/widget.py` -- `ClaudeWidget.start_session` prefixes
  both the `--resume` and fresh-launch shell commands with
  `DESK_WIDGET_INSTANCE_ID=<session_id> ` before `exec claude`.
- `src/desk/temp_ui.py` -- new "Environment variables" section in
  `DOC_TEMPLATE`, `TEMPUI_DOC_VERSION` bumped 41 -> 42 with a matching
  comment-block entry, and a new `## Version 42` entry in
  `_NEW_FEATURES_DOC`.
- `tests/verify/verify_desk_widget_instance_id_env_var.py` (new).

## Implementation approach

1. **`src/desk/claude_session.py`**: in `_connect_and_maybe_prompt`,
   add `env={"DESK_WIDGET_INSTANCE_ID": session_id}` as a new keyword
   argument to the existing `sdk.ClaudeAgentOptions(...)` call (right
   after `mcp_servers`). `session_id` here is always the widget's own
   instance id regardless of `resume` (it's the function parameter
   itself, not the `resume`-conditional `options.session_id`/
   `options.resume` split a few lines above) -- one line, same value in
   both the fresh and resume cases, correctly covering both.

2. **`widgets/claude/widget.py`**: in `start_session`, prepend
   `f"DESK_WIDGET_INSTANCE_ID={shlex.quote(session_id)} "` to both
   branches' `command` string, immediately before `exec claude`:
   - Resume: `f"DESK_WIDGET_INSTANCE_ID={shlex.quote(session_id)} exec claude --resume {shlex.quote(session_id)} {PERMISSION_MODE_ARGS}\n"`
   - Fresh launch: same prefix before the existing
     `f"exec claude --session-id {shlex.quote(session_id)} {PERMISSION_MODE_ARGS} {shlex.quote(prompt)}\n"`.
   A plain `VAR=value` prefix on a simple command exports `VAR` into
   that command's own environment only (bash semantics for a temporary
   assignment before a simple command) -- since `exec` replaces the
   shell process image with `claude`, `claude` inherits it as a normal
   environment variable, with no effect on the rest of the shell's
   environment (matches the "no new plumbing" framing on the TODO item
   -- `session_id` is already in scope at this exact call site).

3. **`src/desk/temp_ui.py` docs**: add a new section to `DOC_TEMPLATE`,
   placed after the "Every file named above lives in this same
   directory." paragraph and its `tempui-breaking-changes.md`/
   `tempui-new-features.md`/Installed Jobs paragraph, and before the
   "## Questions for the user" section:

   ```
   ## Environment variables

   If you're running as the agent behind a `claude`/`Claude (Desk)`
   widget (as opposed to a script invoked via `Job`/`DeskProc`/an
   Installed Job), a few static, launch-time facts about your own
   placed widget instance are available as environment variables
   rather than folded into your prompt -- check for these directly
   (e.g. `echo $DESK_WIDGET_INSTANCE_ID`) rather than assuming one is
   absent just because this document doesn't call it out by name at
   launch:

   - `DESK_WIDGET_INSTANCE_ID` -- this widget instance's own instance
     id (the same id used internally as your session id for
     `--resume`/reconnection across a Desk reload).
   ```

   Bump `TEMPUI_DOC_VERSION` 41 -> 42, with a new comment-block entry
   above the constant matching the existing "TODO `<id>`: bumped N ->
   N+1 for ..." convention, and a new `## Version 42` entry in
   `_NEW_FEATURES_DOC` (newest-first, above `## Version 41`)
   summarizing the new section. This isn't a Bridge API/DSL change
   (the two things `development-process.md`'s "Keep the tempui
   changelog docs current" section calls out by name), but it is new,
   agent-visible static content in `DOC_TEMPLATE` itself -- which is
   exactly what `TEMPUI_DOC_VERSION`'s own doc comment in
   `temp_ui.py` says to bump for, and every prior addition to this
   file has followed that broader rule -- so bump it for consistency
   with that established pattern rather than carve out a narrower
   exception here.

4. **Verification** (`tests/verify/verify_desk_widget_instance_id_env_var.py`,
   new):
   - Monkeypatch `claude_agent_sdk.ClaudeSDKClient` (module-level, via
     `desk.claude_session.sdk.ClaudeSDKClient`) with a fake class whose
     `__init__` captures the `ClaudeAgentOptions` it's given and whose
     `connect()` is a no-op coroutine (same "no real network" shape as
     `tests/verify/verify_installed_job_permission_bypass.py`, which
     already drives `ClaudeSession` methods directly via `asyncio.run`
     without a real SDK connection). Call
     `asyncio.run(session._connect_and_maybe_prompt(session_id, resume, None, "default", None, ""))`
     for both `resume=False` and `resume=True`, and check the captured
     options' `.env == {"DESK_WIDGET_INSTANCE_ID": session_id}` in
     both cases.
   - Load `widgets/claude/widget.py` directly (the
     `verify_terminal_cwd.py`/`verify_claude_prompt_tempui_wording.py`
     pattern: headless `QApplication`, `importlib.util` module load,
     real `ClaudeWidget()` -- a real local `bash` PTY spawn, no live
     `claude`/network dependency, same as those existing scripts).
     `unittest.mock.patch.object(widget, "type_into_shell")` to capture
     the exact command string without ever writing it into the PTY,
     call `start_session("abc-123", resume=False)` and again with
     `resume=True`, and check the captured command starts with
     `"DESK_WIDGET_INSTANCE_ID=abc-123 "` in both cases. Terminate the
     real spawned `bash` process (`widget._process.terminate()`) in a
     `finally`, matching `verify_terminal_cwd.py`'s own cleanup.
   - `TEMPUI_DOC_VERSION >= 42` and the new section's presence
     (`"DESK_WIDGET_INSTANCE_ID" in render_static_doc()`, `"## Version 42"`
     in `_NEW_FEATURES_DOC`/`SPLIT_DOC_CONTENT`'s equivalent, following
     `verify_tempui_changelog_docs.py`'s own check shape).
   - Run the full `tests/verify/` suite afterward and confirm no
     regressions beyond the pre-existing baseline (the already
     -`disabled_`-prefixed scripts).

## Key decisions

- Env var over prompt sentence, and no plumbing changes beyond the
  literal `env=`/shell-prefix addition: both already decided on the
  TODO item itself (2026-09-01 discussion) -- this plan only works out
  the mechanical rest (exact call sites, doc placement, verification).
- Document the *mechanism* once, generically, in `desk-temporary-ui.md`
  rather than adding a per-fact prompt sentence -- matches the TODO
  item's own stated reason for choosing env vars in the first place
  ("trivially extensible to more static self-facts ... without prompt
  bloat").
- Live/dynamic widget facts remain explicitly out of scope here (moved
  to TODO `a762501`, already `COMPLETED`, per the TODO item's own
  text) -- this item only concerns the one static fact, instance id.
