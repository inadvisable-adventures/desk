# Claude widget: start claude in auto mode (COMPLETED)

TODO `2dca4c8`.

## Answer to the question

Yes — the `claude` CLI has `--permission-mode <mode>` whose choices
include `"auto"` (alongside `acceptEdits`, `bypassPermissions`, `manual`,
`dontAsk`, `plan`). So claude can be launched directly in auto mode by
passing `--permission-mode auto`.

## Fix

Add `--permission-mode auto` to the `claude` invocation the claude widget
types into its shell, in `ClaudeWidget.start_session` — on both the fresh
launch and the resume path, so a widget's session stays in auto mode
whether it's newly started or reconnected on reload:

- Fresh: `claude --session-id <uuid> --permission-mode auto "<prompt>"`
- Resume: `claude --resume <uuid> --permission-mode auto`

Implemented as a `PERMISSION_MODE_ARGS = "--permission-mode auto"`
constant spliced into both command strings, so the mode is stated once.

## Affected files

- `widgets/claude/widget.py` — `ClaudeWidget.start_session`.

## Verification

Headless (spying on `type_into_shell`, as in TODO 1d7331b's tests):
- Fresh `start_session(uuid, resume=False)` types a command containing
  `--session-id <uuid>`, `--permission-mode auto`, and the prompt.
- `start_session(uuid, resume=True)` types `claude --resume <uuid>
  --permission-mode auto` with no prompt.
- The session-id / resume / no-prompt-on-resume behavior from TODO
  1d7331b still holds.

## Status

**Completed.** `--permission-mode auto` added to both the fresh and
resume commands (via a `PERMISSION_MODE_ARGS` constant). Verified
headlessly (fresh includes `--session-id` + `--permission-mode auto` +
prompt; resume is `claude --resume <uuid> --permission-mode auto` with no
prompt) and re-ran TODO 1d7331b's full-app session/resume flow with the
updated commands.
