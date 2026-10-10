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

- A hook in `src/desk/shell/current_context.py` (the `set_X`/`get_X`
  pairs a `python` widget uses to reach `DeskWindow`) has its shape
  written in several places that Python never compares: the
  `Callable[...]` alias, the real `DeskWindow` method, and any fake a
  test registers. Change them together, and exercise the hook
  positionally through the REAL method at least once; a test that
  registers a hand-written fake only shows the caller matches the
  documentation, not the code (TODO `66aa766`,
  `investigations/hook-signature-drift.md`).
  `tests/verify/verify_current_context_hook_signatures.py` mechanically
  compares every binding to its alias; a new hook with optional or
  keyword parameters gets a `Protocol` like `CenteredWidgetOpener`
  instead of a bare `Callable`.

### Keep the tempui changelog docs current

Whenever a change made to Desk itself is a breaking change or a new
feature from the perspective of an agent running *inside* Desk (in
some other project) — i.e. anything that would change what such an
agent needs to know about `.desk_temp`'s tempui DSL or Bridge API —
mint a fresh tag (`desk.temp_ui.generate_tag`), add it to
`CURRENT_TAGS`, and add a matching entry to the `_BREAKING_CHANGES`/
`_NEW_FEATURES` dicts in `src/desk/temp_ui.py`, which render to
`tempui-breaking-changes.md`/`tempui-new-features.md` in `.desk_temp/`
at runtime (not checked-in files), all in the same commit as the
change. This is a standing part of the Desk-development workflow, not
a one-off backfill.

### Give agent-visible features a real doc, not a one-line mention

The changelog (`tempui-new-features.md`) *announces* a feature once; it
is not meant to be the only place an agent can learn how to use it. Any
new agent-visible feature that needs more than a one-line mention gets
its own dedicated doc file in `.desk_temp/` (the `tempui-installed-jobs.md`/
`tempui-hmsvc.md`/`tempui-lightning-round.md` pattern: register it in
`SPLIT_DOC_CONTENT`), written in the same commit as the feature and linked
from **both** its changelog entry **and** whichever higher-level doc
(`tempui-custom-widgets.md`'s Bridge API list,
`tempui-porting-existing-apps.md`'s "What Desk gives you", the overview in
`desk-temporary-ui.md`) would otherwise summarize it in passing. A
higher-level doc points to the dedicated file rather than trying to fit
the whole story in one line.

As the safety net for when upkeep lapses, `desk-temporary-ui.md` tells an
agent that finds a doc too thin to check the changelog section first, and
to say so (and offer a FEEDBACK file) if it had to read Desk's source or
another project's code. See TODO `601dae5`.

## Shared development process

See [shared_development_process.md](./shared_development_process.md)
for the actual process this project follows.
