# Drafted upstream `claude_agent_sdk` feature requests

Drafts only -- nothing has been filed anywhere. Raised by Desk's Claude
(Desk) widget (TODO `5ce8447`).

## 1. A run-boundary signal from the CLI

`ClaudeSDKClient`'s message stream gives a `ResultMessage` per turn, but
nothing says "the run is over" (no more turns will arrive on their own).
A background task can settle and still wake the agent for an unsolicited
follow-up turn, so "no tasks in flight" is not "done". The SDK's own
`Query._track_task_lifecycle` documents exactly this gap (issue #1088) and
notes it needs "a run-boundary signal from the CLI rather than an inference
from task bookkeeping". Request: such a signal, or a public indicator that
a continuation turn is pending.

## 2. A public classification of task types that wake the parent

`claude_agent_sdk/_internal/query.py` has `DEFERRING_TASK_TYPES =
frozenset({"local_agent", "local_workflow"})`, unexported. Desk needs the
same distinction (delegated agent work vs. a plain background shell) to word
"still working?" status honestly, and currently keeps a commented copy
(`desk.claude_staleness.DEFERRING_TASK_TYPES`) that can silently drift.
Request: export it, or expose it as a field on `TaskStartedMessage`.

## 3. (From TODO `db1cd65`) a programmatic compaction method -- not needed

Checked against a real session (2026-10-03): sending the literal `/compact`
through `ClaudeSDKClient.query()` works (summary `UserMessage`s, then a
`ResultMessage` with empty `result`), so Desk's Compact now button uses that.
A first-class method would still be nicer than relying on slash-command text,
but nothing is blocked.
