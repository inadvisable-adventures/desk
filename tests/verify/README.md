# `tests/verify/`

Ad-hoc, hand-written verification scripts for Desk — see
`development-process.md`'s "Verification scripts" section for the
process these back. Desk has no formal test framework (no `pytest`, no
test runner, no CI wiring) — each script here is a self-contained
program, run directly:

```
.venv/bin/python3 tests/verify/verify_some_topic.py
```

from the repo root. Each one prints its own `PASS`/`FAIL` lines for the
things it checks and exits non-zero if anything failed.

## Where these came from

Every script here was originally written into a session's scratchpad
directory as the "Verify the changes" step of implementing some TODO
item (see `shared_development_process.md`'s "Working on TODO Items"),
then moved into this directory on 2026-07-15 so they persist across
sessions instead of being lost with the scratchpad they were written
in. The name usually reflects the TODO/feature it was written to check
(e.g. `verify_svg_editor_widget.py` for TODO `7076af5`), not a general
naming convention beyond that.

They're a real, growing regression suite in spirit — before completing
any TODO item, run every script in this directory and compare the
failing set against the last known baseline (`git stash` the change
being verified, rerun, and confirm which failures predate it) — but
they were never designed as one from the start, so expect real
inconsistency in style: some use a `check(name, condition)`/counter
pattern that keeps going and reports a final tally, others use bare
`assert` statements that abort at the first failure. Newer scripts
should prefer the `check()`/counter style so a single stale assertion
doesn't hide everything after it.

## The `disabled_` prefix

A script renamed with a `disabled_` prefix (e.g.
`disabled_verify_crash_handler.py`) is currently failing, with
reasonable suspicion that the failure reflects drift (a stale fixture,
a superseded design, an outdated hardcoded assertion) rather than a
real product bug — see the comment block at the top of the file for
the specific reason, and the TODO item it references for the plan to
resolve it (investigate, then fix, rewrite for equivalent coverage, or
delete outright if the functionality it covered no longer exists).

A script should **not** be disabled just because fixing it is
inconvenient — only when there's an actual, articulable reason to
suspect the failure isn't a real regression. When in doubt, leave it
failing and visible rather than disabling it.

## Adding a new script

Follow an existing script's shape (real headless Qt via
`QT_QPA_PLATFORM=offscreen`, a real `QApplication`, direct construction/
method calls rather than driving the full app) for whatever you're
verifying, name it `verify_<whatever-it-covers>.py`, and leave it in
this directory when you're done — it becomes part of the suite the
next TODO item's own verification step runs against.
