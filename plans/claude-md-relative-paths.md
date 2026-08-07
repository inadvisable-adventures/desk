# Add a relative-paths instruction to Desk's own CLAUDE.md (TODO `a8e4115`)

## Summary

Per
`../FEEDBACK/FEEDBACK-DESK-claude-md-relative-paths-2026-08-03-1604.md`:
another project's `CLAUDE.md` was recently given the instruction "use
paths relative to the current project directory rather than absolute
ones." Desk's own `CLAUDE.md` has no equivalent, so an agent working on
Desk itself has no standing guidance against defaulting to absolute
paths (commit messages, doc references, generated code, etc.).

## Affected files

- `CLAUDE.md`

## Design decisions

- One line, matching this file's existing terse, imperative bullet
  style (`avoid adding dependencies, prefer bespoke solutions.`, etc.)
  -- no elaboration needed beyond the instruction itself.

## Step-by-step implementation

1. Add a bullet to `CLAUDE.md`.

## Key tradeoffs

None -- trivial, single-line addition.

## Verification

Read `CLAUDE.md` back to confirm the line is present and matches the
file's existing style. No automated verify script -- this is a plain
text instruction with no behavior to exercise (matching precedent:
`tests/verify/` has no scripts asserting on `CLAUDE.md`'s own prose
content elsewhere in this repo).
