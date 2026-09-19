# Claude (Desk): real UI for AskUserQuestion (TODO 6ab9e85)

## Summary

`ClaudeSession._can_use_tool` sends every gated tool call, including
`AskUserQuestion`, through the widget's Allow/Deny row and always
returns `updated_input=None`. A question call therefore shows a repr
dump, and "Allow" cannot deliver an answer, so the turn can hang.
Source: `../FEEDBACK/FEEDBACK-DESK-claude-desk-question-vs-permission-hang-2026-09-18-2356.md`.

## Confirmed from the bundled CLI (`claude_agent_sdk/_bundled/claude`)

- Input: `{questions: [{question, header, options: [{label,
  description, preview?}], multiSelect}], answers?, annotations?,
  metadata?}` (1-4 questions, 2-4 options each; question texts unique).
- Output: the same object with `answers` filled in -- "question text ->
  answer string; multi-select answers are comma-separated". A free-text
  reply is an answer string too. The CLI always offers "Other"/free text.
- So the answer channel is `PermissionResultAllow.updated_input`, as the
  feedback suspected. Not yet confirmed: behavior of a real live call
  (verify manually if the app can be launched, else note it as skipped).

## Affected files

- `src/desk/claude_session.py` -- `_can_use_tool`, `respond_to_permission`,
  new `question_request` signal, new `respond_to_question`.
- `widgets/claude_desk/widget.py` -- question panel UI; history line.
- `tests/verify/verify_claude_desk_ask_user_question.py` (new).
- `design-docs/` -- update the Claude (Desk) widget section if it
  describes the permission flow.

## Steps

1. Session: in `_can_use_tool`, if `tool_name == "AskUserQuestion"`,
   emit `question_request(request_id, tool_input)` instead of
   `permission_request`, await a future resolved with an answers dict
   (or `None` = skipped), and return `PermissionResultAllow(
   updated_input={**tool_input, "answers": answers})`; on skip return
   `PermissionResultDeny` with a message saying the user declined.
   Share the pending-future map with permissions.
2. Session: `respond_to_question(request_id, answers | None)`.
3. Widget: a question panel (hidden by default, like the permission
   row) rendering each question's text and its options as buttons
   (toggle buttons when `multiSelect`), plus a free-text line and a
   Submit / Skip pair. Labels not user-selectable (CLAUDE.md). Questions
   queue like permissions do; only one panel at a time.
4. Widget: on submit build `answers` (question text -> label, multi
   joined with ", ", free text used verbatim), call
   `respond_to_question`, append `[question] answered: ...` to history.
5. Tests: session-level (fake loop) that a question call emits
   `question_request` not `permission_request` and that the resolved
   answers land in `updated_input`; widget-level for single, multi,
   free text, skip, and queued questions.
6. Run the full `tests/verify/` suite; update design doc; consider a
   tempui changelog entry only if agent-visible behavior changed (it
   does not appear to -- decide when implementing).

## Tradeoffs

- Match on the tool name `AskUserQuestion` (confirmed present in the CLI)
  rather than inferring from `ToolPermissionContext`; simpler and exact.
  A second, unknown question-shaped tool would still get Allow/Deny.
- `annotations`/`preview` are ignored in v1.
