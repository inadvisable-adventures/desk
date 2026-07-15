# Plan: TODO 1a96c9f — fork development-process.md into a shared/not-shared hierarchy

## Summary

Split `development-process.md`'s current, entirely-generic content into
its own file, `shared_development_process.md`, and rewrite the
top-level doc into a thin wrapper with a (for-now-empty) Desk-specific
section plus a pointer to the shared file. Add an empty peer file for
guidance specific to working on some *other* project, not Desk itself.
Explain the resulting hierarchy, and instruct agents working on Desk to
keep TODO `7462cdb`'s two new changelog docs updated.

## New file: `shared_development_process.md` (repo root)

An exact fork of `development-process.md`'s current full content
(Design Docs, Learnings, Item IDs, Planning, Working on TODO Items,
Prioritizing TODO Items) -- nothing in that content is Desk-specific,
so it moves verbatim.

## New (empty) file: `specifically-not-working-on-desk-itself-development-process.md` (repo root)

Empty for now, per the request -- a placeholder peer to
`shared_development_process.md` for guidance specific to working on a
project *other than* Desk itself (as opposed to the shared conventions,
which apply either way).

## Rewritten `development-process.md`

```markdown
# Development Process

This file describes the development process for this project.

## When working on Desk itself

(empty for now -- Desk-specific guidance goes here)

## Shared development process

The actual day-to-day process this project follows -- design docs,
`LEARNINGS.md`, item ids, planning, working through TODO items,
prioritizing -- lives in [shared_development_process.md]
(./shared_development_process.md), not in this file directly. Treat
everything in that file with the exact same authority as if it were
written directly here.

There's also [specifically-not-working-on-desk-itself-development
-process.md](./specifically-not-working-on-desk-itself-development
-process.md) -- guidance specific to working on some *other* project
that adopted these conventions, as opposed to Desk itself.
```

## "When working on Desk itself" section content

Two things, per the request (still under the otherwise-empty section --
this is Desk-specific meta-guidance about the docs themselves, not a
generic process rule, so it belongs here rather than in the shared
file):

1. **The doc hierarchy.** Explain there are now three development
   -process documents (this top-level one, `shared_development_process
   .md`, and `specifically-not-working-on-desk-itself-development
   -process.md`), what each is for, and instruct an agent to ask the
   user for clarification whenever it's ambiguous which one's guidance
   actually applies to the current task -- rather than guessing.
2. **Keep the changelog docs current.** Whenever a change made to Desk
   itself is a breaking change or a new feature from the perspective of
   an agent running *inside* Desk (in some other project), update
   `tempui-breaking-changes.md`/`tempui-new-features.md` (TODO
   `7462cdb`) accordingly, in the same commit as the change -- so
   populating those two docs is a standing part of the Desk-development
   workflow, not a one-off backfill.

## Seeding (`src/desk/shell/window.py`)

`DeskWindow._seed_development_process` currently copies only
`development-process.md` itself into a newly-created project. Left
unchanged, a new project would get the *rewritten* top-level file (with
a dead relative link to `shared_development_process.md`, and none of the
actual process content it used to carry) -- a real regression this
change would otherwise introduce, not something explicitly called out
in the request but a necessary consequence of it. Extend the same
copy-if-missing/never-overwrite seeding, under the same existing
`copy_development_process` flag, to also seed `shared_development
_process.md` and the empty `specifically-not-working-on-desk-itself
-development-process.md` peer -- all three travel together as one unit,
no new dialog checkbox needed.

## Verification

- All three files exist at the repo root with the expected content
  (fork matches the old full content; top-level file has the two new
  sections and links to the other two; the peer file is empty).
- `_seed_development_process` (or a renamed/generalized version)
  copies all three into a fresh project directory, respects
  never-overwrite for each independently, and is a no-op if the source
  Desk has none of them.
- Full scratchpad regression suite (`git stash` before/after).
