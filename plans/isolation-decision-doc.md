# Isolation decision doc (TODO `2924940`) (COMPLETED)

## Summary
Write down the trust tiers and threat model Desk's isolation work is built on, in
`design-docs/isolation.md`.

## Affected files
`design-docs/isolation.md` (new), `design-docs/architecture.md` (pointer), `TODO.md`.

## Approach
Before writing, verify every "today" claim against the source (what runs
in-process vs subprocess, how the Bridge authenticates and identifies callers,
whether the Chromium sandbox is disabled). Two TODO assumptions turned out to
be wrong and are corrected in place: python installed jobs and tempui python
`Job`s run in-process, and the Bridge trusts client-supplied identity headers
behind a single shared token (new TODO `929e730`).

## Verification
Not testable; each statement in the doc's tables was read from code (files named
in the doc and in `TODO.md`).
