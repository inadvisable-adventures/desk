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
