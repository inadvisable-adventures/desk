# deprecated-docs/ — history of replaced APIs

> # ⚠ NOT FOR NORMAL USE
>
> Everything in this directory documents an API Desk has **removed or replaced**.
> It is of interest **only to deep-dive investigations where history matters**
> (why did this change, what did the old behavior do). It must **never** be loaded
> into an agent's context as a consequence of normal operation, and **no current
> documentation links here** -- by design, so outdated docs cannot leak into
> agents doing anything else.
>
> If you are implementing, debugging, documenting or using Desk, you do not need
> anything in this directory. Use the current docs.

## Why this directory exists

Desk handles a replaced widget-facing API (Bridge JS, python-widget hooks, tempui
keywords, manifest fields) by leaving the old name as a **tombstone**: nothing
behind it except a report to Desk and an error that says what to use instead,
with an offer to rewrite the caller or hand the fix to an agent. The old
*documentation* therefore has no place in the current docs. It is kept here,
verbatim, one file per deprecation (`DEPR-NNN-<slug>.md`), for the rare person who
needs the history. The plan for the whole process is TODO `df8138a`.

## Rules (also enforced by `tests/verify/verify_deprecated_docs_isolation.py`)

- Current docs (`design-docs/`, the `.desk_temp/tempui-*.md` set, `README.md`,
  the process docs) **never** link to or quote this directory. The one exception
  is the guard line in `CLAUDE.md` telling agents not to read it.
- Runtime messages (errors, warnings, notifications) refer to a deprecation by its
  **id** (`DEPR-NNN`) and say what to do now -- they never point at these files.
- The tempui docs Desk writes into projects describe only the current API.
- Each entry file starts with the banner above; keep it.

## Index

- `DEPR-001-shared-launch-token.md` -- the shared per-launch Bridge token with
  header-asserted caller identity (replaced by per-instance Bridge credentials,
  TODO `929e730`).
