# `desk_ask_desk_expert` MCP tool (TODO `c4ef727`) (COMPLETED)

## Summary

A new `desk` MCP tool taking a single string `question`. It places a fresh Claude (Desk) widget
(`claude_desk`) whose initial prompt is the usual widget prompt (running inside Desk, tempui docs,
MCP tool list) plus:

- the question, tagged as coming from another agent running in the same Desk session;
- the location of Desk's own source checkout (derived from the `desk` package path) and its docs
  (`design-docs/`, `LEARNINGS.md`, `plans/`, `*.md`), so it can answer questions *about* Desk and
  the current session;
- encouragement to write diagnostic `kind: "python"` widgets as needed;
- an instruction to answer the question, written into its own widget window.

The usual "reading these documents is orientation only ... do not start working" wording is
omitted (also from the dev-process instruction), replaced by "answer the other agent's question".
Fire-and-forget: the tool returns the new widget's instance_id immediately; no results are routed
back to the caller.

## Affected files

- `widgets/claude_desk/widget.py` -- split `CLAUDE_WIDGET_PROMPT` into prefix / orientation-only /
  tools pieces (concatenation unchanged, existing tests keep passing); `start_session` gains
  `answer_question: bool = False`, which drops the orientation-only sentence and the dev-process
  orientation caveat.
- `src/desk/shell/window.py` -- plumb `claude_answer_question` through `_place_widget` and
  `_bind_claude_desk_widget`; new `DeskWindow.ask_desk_expert(question) -> str` building the
  instructions file (`_write_claude_instructions_file`, prefix "expert") and placing the widget
  at viewport center.
- `src/desk/shell/desk_mcp_server.py` -- the tool, via `_call_on_gui_thread`.
- `src/desk/temp_ui.py` -- changelog entry (new tag), dedicated doc `tempui-ask-desk-expert.md`
  in `SPLIT_DOC_CONTENT`, link from the overview doc.
- `tests/verify/verify_ask_desk_expert.py`.

## Decisions

- Uses `claude_desk` (SDK-based) since only it has the in-process desk MCP server.
- The session's cwd stays the current project; the source checkout is read by absolute path, so
  the user may see permission prompts in the widget -- acceptable, the user is in the loop.
- Tool call is bounded by GuiBridge's 5s timeout; placement is fast and does no modal UI.
