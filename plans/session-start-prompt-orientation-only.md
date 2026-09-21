# Session-start prompt: reading the docs is orientation only (TODO b78e7b8) (COMPLETED)

## Summary

The prompt sent to a freshly started Claude session (both the PTY-based
`widgets/claude/` widget and the SDK-based `widgets/claude_desk/` widget)
tells the agent to read `desk-temporary-ui.md` and, when the project has
one, `development-process.md`. An agent can take that as a work request
and go pick up a `TODO.md` item, especially because `development-process.md`
describes a "Working on TODO Items" workflow and the `claude_desk` prompt
ends by telling the agent to check `desk_get_next_todo_item`. See
`../FEEDBACK/FEEDBACK-DESK-onboarding-read-mistaken-for-work-request-2026-09-18-2110.md`.

## Affected files

- `widgets/claude/widget.py` -- `CLAUDE_WIDGET_PROMPT` and
  `_development_process_instruction`.
- `widgets/claude_desk/widget.py` -- `CLAUDE_WIDGET_PROMPT` (including its
  trailing `desk_get_next_todo_item` sentence) and
  `_development_process_instruction`.
- `tests/verify/verify_claude_prompt_tempui_wording.py`,
  `tests/verify/verify_dev_process_seeding.py` -- assert the new text.

## Approach

1. Both `CLAUDE_WIDGET_PROMPT`s: add a sentence after the doc-reading
   instruction: reading these documents is for orientation only, is not
   itself a task, and does not mean you should start working (for example
   by picking up a `TODO.md` item or calling `desk_get_next_todo_item`)
   unless the user's own message separately asks for it.
2. `claude_desk` prompt: reword the trailing sentence from an unqualified
   "check desk_get_next_todo_item before assuming an earlier read of
   TODO.md is still current" to "if and when you are working on TODO
   items, check ... before assuming ..." so it is conditional on the user
   having asked for that work.
3. Both `_development_process_instruction`s: append the same
   orientation-only statement to the "please read that too" text, since
   that is the document whose contents most invite starting work.
4. Keep the text plain ASCII with no newlines or single quotes -- the PTY
   widget passes the prompt through a shell command line (see the earlier
   embedded-newline fix, `fix-embedded-newline-breaks-claude-launch-prompt.md`).
5. Not a tempui DSL/Bridge API change (no `temp_ui.py` edit), so no
   tempui changelog entry.

## Verification

- Update `verify_claude_prompt_tempui_wording.py` to assert the
  orientation-only wording in the `claude` widget prompt, and add the
  same assertions for the `claude_desk` prompt (including that the
  trailing `desk_get_next_todo_item` sentence is now conditional).
- Update `verify_dev_process_seeding.py` to assert the instruction text
  contains the orientation-only statement, for both widgets, while the
  file-absent regression check still holds unchanged.
- Run the two scripts, then the other `tests/verify/` scripts touching
  these modules (`verify_claude_desk_*`), and confirm no new failures.
- No browser launch needed.

## Status

Implemented as planned. Wording avoids apostrophes/newlines ("the message
from the user" rather than "the user's message") so the PTY widget's shell
launch line stays safe. Both verify scripts updated and passing; all
`verify_claude_desk_*` scripts still pass. Browser launch not needed.
