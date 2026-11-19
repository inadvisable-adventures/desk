# Asking experts (desk_*_expert MCP tools)

See `desk-temporary-ui.md` (in this same directory) for this directory's
own overview and its current set of tags. This is not a tempui-DSL file
type: it is MCP tools on the `desk` server, backed by a registry shared by
every project on this machine.

`desk_ask_desk_expert` (`tempui-ask-desk-expert.md`) only answers questions
about Desk itself, once, in a new window. The **expert registry** is the
general mechanism: a list of experts (the person using Desk, agents, and
Desk-hosted services) that any agent on any project can ask, where the
answer may take minutes to days and **your session will usually be gone by
then**. Asking never waits.

- The registry lives in a local PostgreSQL database (`~/.desk/experts`),
  created and started the first time it is used. If PostgreSQL is not
  installed the tools return one clear error and nothing else in Desk is
  affected.
- The built-in expert **`user`** is the person using Desk; they answer in the
  **Experts** widget.
- When an answer arrives Desk shows the user a top-right notification, and the
  Experts widget can start a new Claude session seeded with the
  question, the answer and your private note.

## MCP tools

- `desk_list_experts()` -- `[{expert_id, name, description, kind,
  registered_by, listens_for}]`; `kind` is `human`, `agent` or `hmsvc`.
- `desk_register_expert(expert_id, name, description?, kind?, registered_by?, listens_for?)`
  -- offer yourself (or a person) as an answerer. `expert_id` is lowercase
  letters, digits, `.`, `_`, `-`. An expert can only be updated by whoever
  registered it (pass the same `registered_by`).
- `desk_ask_expert(expert_id, question, note_to_self?, asker?)` -- returns the
  new `question_id` at once. `question` is shown to the expert verbatim, so
  make it self-contained. **`note_to_self` is never shown to the expert**: put
  there what a future agent needs to act on the answer ("if yes, update
  section 3 of the familiars design doc and reopen TODO `a1b2c3d`").
- `desk_get_expert_question(question_id)` -- your view: `status` (`open`,
  `accepted`, `answered`, `withdrawn`), the `answer` once there is one, and your
  `note_to_self`.
- `desk_list_expert_questions(expert_id, status?)` -- the answerer's view
  (default `open`; `all` for every status), without any note.
- `desk_accept_expert_question(question_id, accepted_by?)` -- claim an `open`
  question so nobody else starts it.
- `desk_answer_expert_question(question_id, answer, answered_by?)` -- answer a
  question that is `open` or `accepted`.

Every change publishes the desk event `desk.experts.changed`.

## Reporting findings to an expert

Experts can also be **told** things. Sometimes an agent learns something
about a domain it does not own (a library pitfall, a Desk quirk, a doc that
is wrong, a workaround that worked) and the expert who maintains that
knowledge would want to know. An expert opts in by registering with
`listens_for` (a sentence saying what it wants to hear); `desk_list_experts`
shows it. The built-in `desk` expert listens for findings about Desk itself.

- `desk_report_to_expert(expert_id, title, finding, evidence?, reporter?)`
  -- returns a `report_id` at once and never waits. Make it self-contained and
  report what you actually observed, with the evidence (commands, paths, exact
  output). Reporting to an expert that is not listening is refused, and the
  error lists the experts that are.
- `desk_get_expert_report(report_id)` -- your view: `status` (`new`,
  `accepted`, `rejected`, `duplicate`, `integrated`), the expert's
  `review_note`, and once folded in, the `integration_note` saying where.
- `desk_list_expert_reports(expert_id, status?)` -- the expert's view; by
  default the reports still to deal with (`new` and `accepted`).
- `desk_review_expert_report(report_id, decision, note?, reviewed_by?)` --
  `accepted` (worth keeping), `rejected` or `duplicate` (a note is required, so
  the reporter learns why).
- `desk_integrate_expert_report(report_id, integration_note, integrated_by?)`
  -- after you have actually folded the finding into what you maintain, record
  where. Do the integration first; this only records it.

An expert that is an agent should check `desk_list_expert_reports` when it
starts work in its domain. Treat a report as a lead, not a fact: verify it
before integrating, and reject it if it does not hold.

## The Experts widget and notifications

When an answer arrives for a question you asked, and when a new question is
put to the built-in `user` expert, Desk shows a top-right notification
(once per event); clicking it opens the built-in `Experts` widget (widget id
`experts`, also dockable in the sidebar). The widget lists questions (Open,
Answered or All), shows one, and lets the person **answer it** or use
**Send to agent**:

- for a question still waiting, Send to agent starts a new Claude session
  told to answer it with `desk_answer_expert_question` (it is given the
  question, never your private note) and marks the question `accepted`;
- for an answered question, it starts a new Claude session seeded with the
  question, the answer **and your private `note_to_self`**, so the agent that
  acts on the answer has the context to do so.

An answer written in the widget does not produce a notification.

Reports (see "Reporting findings to an expert") show up too: a new report
for `desk` or `user` produces a notification in the Desk that reported it,
and when a report you filed is rejected, called a duplicate or integrated,
the Desk you filed it from shows that outcome. In the widget, pick *Reports
to review* (or *Reports: all*) to see them, **Accept** / **Reject** /
**Duplicate** with a note, or **Send to agent** to have a new Claude session
verify the finding, fold it in and record where.

With several Desks running on one machine, each notification is shown by
exactly **one** Desk: the one whose session asked the question (the registry
records the asking Desk's directory). If that Desk has been closed for a
little while, or the question has no recorded Desk, whichever Desk is
running announces it instead.

## The built-in `desk` expert

`desk` answers questions about Desk itself or the running session (how a
feature behaves, why something timed out, what is on the canvas). A person
or a Desk-hosted service may answer for it like any expert. If a question to
`desk` is still `open` (nobody has accepted it) after about 20 seconds, the
Desk it was asked from starts a Claude (Desk) session that reads Desk's own
source and docs, answers, and records the answer as `desk-fallback`; you get
it the usual way (`desk_get_expert_question`, plus the notification). A
question someone has already accepted is left alone. `desk_ask_desk_expert`
is shorthand for asking `desk` and having that session start immediately.

## A Desk-hosted service as an expert

An hmsvc (`tempui-hmsvc.md`) can register itself as an expert and answer
questions. Give its `service.json` the `experts` capability, then, from
`service.py`, with `from desk.hmsvc_client import desk` (each call blocks;
wrap it in `asyncio.to_thread` from an `async def`):

- `desk.experts_register(expert_id, name, description="", listens_for="")` --
  registers or updates an expert (kind `hmsvc`) owned by this service.
  `listens_for` says what findings agents may report to it (empty: none).
- `desk.experts_pending(expert_id)` -- the open questions put to it:
  `[{question_id, question, asker, asked_at, ...}]`. The asker's private
  note is never included.
- `desk.experts_accept(question_id)` -- claim one so nothing else starts it.
- `desk.experts_answer(question_id, answer)` -- answer it; the asker is
  notified.

To receive reports (findings agents send with `desk_report_to_expert`):

- `desk.experts_reports(expert_id)` -- the reports still to deal with (status
  `new` or `accepted`): `[{report_id, title, finding, evidence, reporter,
  ...}]`. They are leads, not facts: verify before folding one in.
- `desk.experts_report_review(report_id, decision, note="")` -- `"accepted"`,
  `"rejected"` or `"duplicate"`; a note is required for the last two.
- `desk.experts_report_integrate(report_id, integration_note)` -- after you
  have folded the finding in, record where; the reporter can read it.

A service can only act on experts it registered itself. Poll
`experts_pending` (or subscribe to the `desk.experts.changed` desk event and
call it when one arrives).
