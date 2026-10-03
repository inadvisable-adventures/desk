# Investigate isolating Desk (TODO `e6ea1db`)

## Summary
Investigate ways to run Desk with better isolation -- e.g. not giving it full
access to absolute paths or system calls.

## Why this can't proceed yet
"Not designed/scoped yet." The code-side facts are readily gatherable (what
reads/writes absolute paths today: `desk.fs.*`, `desk.documents`, transforms and
`kind: "python"` widgets run in-process with full access, installed jobs and
hmsvc services are subprocesses, the Claude widgets run `claude` with the
user's permissions), but what to *do* with them depends on the threat model,
which is the user's call: protecting the host from a malicious/buggy widget or
job, protecting a project from another project, or constraining the Claude
agent. Those lead to different mechanisms (OS sandboxing of subprocesses,
container/VM, path allow-lists in the Bridge API, per-widget capability
tightening) with very different costs.

## Status
BLOCKED on questions in `QUESTIONS.md` (TODO `e6ea1db`). Marked `PENDING` in
`TODO.md`; nothing implemented.
