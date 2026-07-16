# Development Process

This file describes the development process for this project.

## When working on Desk itself

This section is for guidance that applies specifically to working on
Desk's own codebase (this repository), as opposed to the shared
process content below, which applies to any project following these
conventions.

### The development-process doc hierarchy

There are three development-process documents:

- **`development-process.md`** (this file) — the top-level entry
  point. Desk-specific guidance lives directly in this file, under
  "When working on Desk itself."
- **[shared_development_process.md](./shared_development_process.md)**
  — the actual day-to-day process (design docs, `LEARNINGS.md`, item
  ids, planning, working through TODO items, prioritizing). Treat
  everything in that file with the exact same authority as if it were
  written directly in this one.
- **[specifically-not-working-on-desk-itself-development-process.md](./specifically-not-working-on-desk-itself-development-process.md)**
  — guidance specific to working on some *other* project that has
  adopted these conventions, as opposed to Desk itself.

If it's ever ambiguous which of these actually applies to the current
task, ask the user for clarification rather than guessing.

### Verification scripts (`tests/verify/`)

Desk has no formal, checked-in test suite (no `pytest`, no `tests/`
runner) — the "Verify the changes" step of the shared development
process below is instead backed by ad-hoc, hand-written scripts under
`tests/verify/`, one or more per TODO item, each run directly (`.venv/
bin/python3 tests/verify/<script>.py`) and printing its own `PASS`/
`FAIL` lines. See `tests/verify/README.md` for how they're organized.

- Keep them up to date as is practical: when a change makes an
  existing script's assertion stale (a hardcoded version number, a
  renamed path/attribute, a superseded contract), fix it in the same
  commit as the change that caused it — the same "fix what your own
  change made stale" expectation this file's "Working on TODO Items"
  step 5 already applies to the regression suite generally.
- If a script is failing and there's reasonable suspicion it isn't
  failing for a good reason (a stale fixture, a superseded design, an
  outdated assertion — not a real product bug) but fixing it properly
  isn't practical right now, rename it with a `disabled_` prefix, add
  a comment at the top of the file explaining the current failure and
  why it's suspected not to reflect a real bug, and add a TODO item to
  come back to it later: investigate, then either fix it, rewrite it
  for equivalent coverage, or delete it outright if the functionality
  it covered no longer exists.
- Don't disable a script just because it's inconvenient to fix right
  now — only when the failure itself looks like drift (fixture/
  assertion staleness), not a real regression worth chasing down
  immediately.

### Keep the tempui changelog docs current

Whenever a change made to Desk itself is a breaking change or a new
feature from the perspective of an agent running *inside* Desk (in
some other project) — i.e. anything that would change what such an
agent needs to know about `.desk_temp`'s tempui DSL or Bridge API —
update `tempui-breaking-changes.md`/`tempui-new-features.md` (see
`src/desk/temp_ui.py`'s `_BREAKING_CHANGES_DOC`/`_NEW_FEATURES_DOC`)
accordingly, in the same commit as the change. This is a standing part
of the Desk-development workflow, not a one-off backfill.

## Shared development process

See [shared_development_process.md](./shared_development_process.md)
for the actual process this project follows.
