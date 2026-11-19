# Asking a Desk expert (desk_ask_desk_expert)

See `desk-temporary-ui.md` (in this same directory) for this
directory's own overview and its current set of tags. This is not a
tempui-DSL file type: it is one MCP tool on the `desk` server.

`desk_ask_desk_expert(question)` takes a single string. It is shorthand for
asking the built-in `desk` expert (`tempui-experts.md`) and having Desk
answer at once. Desk places a new Claude (Desk) widget on the canvas and
starts an agent in it whose prompt contains:

- the usual "you are running inside of Desk" orientation and tool list;
- the location of Desk's own source checkout (the code this very Desk
  is running from) and its design, planning and learnings docs, which
  it may read;
- your `question`, tagged as a question from another agent running in
  the same Desk session;
- encouragement to write small diagnostic `kind: "python"` widgets when
  reading is not enough to learn how the live session behaves.

It is told to answer your question, not to wait for the user.

## What to expect

- **Does not wait.** The call returns at once with a `question_id` and the
  new widget's `instance_id`. The answer is recorded in the expert registry
  (read it with `desk_get_expert_question`; Desk also notifies the user) and
  appears in the new widget's window. Do not block on it. Only when the
  expert registry is unavailable (no PostgreSQL) does it fall back to
  fire-and-forget, where nothing comes back to you.
- It runs as an ordinary Claude (Desk) session: the user may see
  permission prompts in that widget for reads outside the project.
- Put everything the expert needs in the one string (what you tried,
  exact error text, instance ids, file paths) -- it does not see your
  conversation.
- Use it for questions about Desk itself (how a feature behaves, why
  something timed out, what the live session is doing). For problems in
  your own project, work them yourself; to report a Desk defect, write a
  FEEDBACK file as `desk-temporary-ui.md` describes.
