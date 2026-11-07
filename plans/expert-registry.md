# Desk-wide "ask an expert" (TODOs `c2555b5`, `b2e031d`, `d15791d`)

From `../FEEDBACK/FEEDBACK-DESK-request-a-desk-wide-ask-an-expert-mechanism-...-2026-11-05-2336.md`. Decided with the
user: **use Postgres**; **hmsvcs can register themselves as experts and answer questions**; **humans use a built-in
python widget** that shows open questions and lets the user answer them or send them to an agent. Postgres access
follows the user's existing projects (`../world-timelines`, `../inadvisable-archive`): **no driver dependency, shell out
to the `psql` CLI** against a self-contained local cluster on a unix socket.

## Split into three TODOs, each committed on its own

1. **`c2555b5` -- registry + MCP tools.** `desk.expert_registry.ExpertRegistry` (Qt-free, thread-safe).
2. **`b2e031d` -- Bridge `experts` capability** so an hmsvc can register, poll its questions, accept and answer
   (`desk.hmsvc_client`).
3. **`d15791d` -- notifications + the Experts widget + agent handoff.**

## Storage

- A **Desk-wide** cluster (not per project -- the request is "this Desk instance/machine"): `~/.desk/experts/pgdata`,
  database `desk_experts`, listening on a unix socket in that directory only (no TCP port claimed), created and started
  lazily on first use (`initdb` / `pg_ctl start` / `createdb` / apply schema) and, like the existing projects' clusters,
  **left running** afterwards. Binaries come from `$DESK_PG_BIN`, Homebrew's `postgresql@18` (then `@17`, `@16`), then
  `$PATH`. No Postgres installed -> every expert tool and the widget return one clear error; nothing else in Desk is
  affected.
- Queries go through `psql -X -q -A -t -v ON_ERROR_STOP=1 -v name=value -f -` with the SQL on stdin and **`:'name'`
  variable interpolation** (psql's own literal quoting) -- never string-built SQL. Every statement returns one JSON value
  (`json_agg`), parsed in Python.
- Tables: `experts(expert_id, name, description, kind human|hmsvc|agent, registered_by, registered_at)` and
  `expert_questions(question_id, expert_id, asker, question, note_to_self, status open|accepted|answered|withdrawn,
  accepted_by, answer, answered_by, asked_at, answered_at, answer_notified_at, expert_notified_at, handed_off_at)`.
  A built-in human expert **`user`** is always registered.
- **The asker's private note is never shown to an expert**: every expert-side read (`list_questions` for an answerer, the
  Bridge, the widget's detail view) omits `note_to_self`; only the asker's own `get_question` and the agent handoff
  include it.

## MCP tools (TODO `c2555b5`)

`desk_list_experts`, `desk_register_expert(expert_id, name, description, kind?)`, `desk_ask_expert(expert_id, question,
note_to_self?)` -> `question_id` (does **not** wait), `desk_get_expert_question(question_id)` (the asker's view: status,
answer, own note), `desk_list_expert_questions(expert_id, status?)` (the answerer's view, no note),
`desk_accept_expert_question(question_id, accepted_by?)`, `desk_answer_expert_question(question_id, answer,
answered_by?)`. Every change publishes the desk event `desk.experts.changed`. `desk_ask_desk_expert` is unchanged
(folding it in as an always-registered "Desk maintainer" expert is left for later).

## Bridge (TODO `b2e031d`)

New capability `experts` (not a default one): `POST /api/bridge/experts/register` (kind forced to `hmsvc`,
`registered_by` = the caller), `GET .../experts/pending` (open questions for experts that caller registered),
`POST .../experts/accept`, `POST .../experts/answer` (only for questions addressed to its own experts); client methods
`experts_register/pending/accept/answer`.

## Notification + widget (TODO `d15791d`)

- A background poller (every 10s, only once the cluster exists) finds **answers the asker has not been told about** and
  **new open questions for the built-in `user` expert**, posts the top-right banner for each (click opens the Experts
  widget), and stamps `answer_notified_at` / `expert_notified_at`. It also publishes `desk.experts.changed`.
- Built-in python widget **Experts** (`widgets/experts/`): filter Open / Answered / All, a list, the question text, an
  answer box + **Answer**, **Send to agent**. For an open question the new Claude (Desk) session is told to answer it
  with `desk_answer_expert_question` (it gets the question, never the note); for an answered one it is seeded with the
  question, the answer and the asker's private note, and `handed_off_at` is stamped. New
  `DeskWindow.start_expert_session(text)`.

## Verification

A real throwaway Postgres cluster in a temp dir (initdb/pg_ctl from the Homebrew keg; the script skips with a clear message
if none is installed) for the registry, MCP handlers against it, the Bridge routes via the app test client, widget +
poller with fakes. No live check of the banner click-through.
