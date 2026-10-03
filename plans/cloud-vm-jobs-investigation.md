# Investigate running Desk jobs on cloud VMs (TODO `f165b8c`)

## Summary
Desk runs `claude`, and many VM providers have blanket no-running-AI policies.
The item is to investigate what options exist for running Desk jobs on cloud VMs.

## Why this can't proceed yet
The item says "Not designed/scoped yet", and the useful answer depends on
decisions that are the user's, not derivable from the code: which providers
and which concrete policies count (this is a policy/legal reading, not a code
question -- findings would be web research that can be wrong or out of date),
what "Desk jobs" means here (installed jobs? hmsvc services? the Claude
widgets themselves?), and what outcome is wanted (a recommendation, a design
for a runner abstraction, or just a list of providers that permit it).

## Status
BLOCKED on questions in `QUESTIONS.md` (TODO `f165b8c`). Marked `PENDING` in
`TODO.md`; nothing implemented.
