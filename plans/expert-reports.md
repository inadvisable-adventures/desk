# "Notify an expert": findings agents report to listening experts (TODOs `0f506f7`, `7ebb24f`, `a63e115`)

User request (2026-11-09): "Sometimes, even non-experts can learn interesting things about domains. Let's extend the
'ask an expert' system to include a 'notify an expert' subsystem, with infra for agents to report on interesting
findings about domains to listening experts and for experts to receive, evaluate, and integrate those reports."
Builds on `plans/expert-registry.md` (same Postgres cluster, same `psql` access, same experts).

## Decisions (made without asking; each is easy to change)

- **Listening is opt-in.** `experts.listens_for` (text): empty = does not receive reports; non-empty = a sentence saying
  what findings it wants. Shown by `desk_list_experts`. The built-in `desk` expert listens for findings about Desk
  itself; `user` does not by default (it can still review reports sent to `desk` through the Experts widget).
  Reporting to a non-listener is refused, and the error lists who is listening.
- **A report is not a question.** Table `expert_reports(report_id, expert_id, reporter, title, finding, evidence,
  status, reviewed_by, review_note, integration_note, integrated_by, reported_at, reviewed_at, integrated_at, origin,
  expert_notified_at, outcome_notified_at)`. Status: `new` -> `accepted` | `rejected` | `duplicate` -> `integrated`
  (`new`/`accepted` may go straight to `integrated`; a rejected/duplicate/integrated report is final).
- **Evaluate = review; integrate = record.** The registry cannot know what "integrating" means for an arbitrary
  expert (edit a doc, open a TODO, update a service's data), so the expert does the work and then records an
  `integration_note` saying where. The reporter reads `review_note` / `integration_note` with `desk_get_expert_report`.
  Rejecting or calling a report a duplicate requires a note, so the reporter learns why.
- **Never waits**, like asking: `desk_report_to_expert` returns a `report_id`.
- **Reports are leads, not facts**: the docs tell the receiving expert to verify before integrating.

## Split into three TODOs, each committed on its own

1. **`0f506f7` -- registry + MCP tools.** `listens_for`, the table, `report/get_report/list_reports/review_report/
   integrate_report`, MCP tools `desk_report_to_expert`, `desk_get_expert_report`, `desk_list_expert_reports`,
   `desk_review_expert_report`, `desk_integrate_expert_report`, `desk_register_expert(listens_for)`; docs + changelog tag.
2. **`7ebb24f` -- Bridge** so an hmsvc expert can register with `listens_for`, poll its reports, review and integrate.
3. **`a63e115` -- notifications + the Experts widget + agent handoff.** Banners for new reports to `user`/`desk`
   (asking-Desk routing like answers) and for the outcome of a report to its reporter's Desk; a Reports mode in the
   Experts widget to accept/reject/duplicate and **Send to agent** (a Claude (Desk) session told to verify, integrate,
   and record the result).

## Verification

Throwaway Postgres like the rest of the experts tests (`tests/verify/verify_expert_registry.py` etc.).
