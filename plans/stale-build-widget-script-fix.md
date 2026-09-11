# Warn on a stale build_widget.py sibling, clean up old build output, add err.status (TODO `e86a31b`) (COMPLETED)

## Summary

Per
`../FEEDBACK/FEEDBACK-DESK-stale-build-widget-script-defeats-capabilities-fix-2026-07-31-1445.md`:
a project's own stale, pre-fix copy of `scripts/build_widget.py` (from
before TODO `029047b` moved the mechanism to the auto-refreshed
`.desk_temp/build_widget.py`, bumped 16->17) can silently defeat
TODO `31db3f6`'s already-shipped capabilities-emission fix, since both
scripts compile/produce a valid `DefineWidget` file with the same exit
code either way -- the stale one just has zero mentions of
`Capability` and silently drops every capability a widget declares.
Confirmed Desk's own repo no longer seeds `scripts/build_widget.py` at
all (no such seeding function exists) -- this is purely legacy drift
in a project that adopted Desk before the move, with nothing today
warning it's stale/unused.

Two smaller, related gaps from the same FEEDBACK item, fixed in the
same pass:
1. `main()` never cleans up an earlier build's output for the same
   keyword -- a real (if narrow) risk given
   `_register_custom_widgets_from_desk_temp` re-scans `.desk_temp` in
   alphabetical order at startup.
2. The Bridge client's thrown `Error` bakes the HTTP status into the
   message string instead of exposing it as a structured property.

## Affected files

- `src/desk/temp_ui.py` -- `_BUILD_WIDGET_SCRIPT`'s generated
  `main()`, plus a `TEMPUI_DOC_VERSION` bump/changelog entry.
- `src/desk/server/bridge_client.py` -- the `call()` helper's thrown
  `Error`.
- `tests/verify/` -- new/extended coverage.

## Design decisions

- **Sibling-check, not "stop seeding a second copy"** -- the FEEDBACK
  item's own fallback ("if checking for a sibling copy feels like
  solving a self-inflicted problem... stop seeding it") is already
  moot: confirmed directly that Desk doesn't seed `scripts/build_widget.py`
  today at all. The only real gap left is warning an *already
  -affected* project (one that adopted Desk before the move) that it
  has a stale, unused copy sitting around.
- **Check at the very start of the generated script's `main()`**, not
  at import time or via a separate mechanism -- keeps the check
  self-contained inside the one file that's already regenerated fresh
  per-project (so it can safely carry a little more logic without
  going stale itself), matching the FEEDBACK item's own suggested
  location. No new capability needed: just `Path("scripts/build_widget.py").is_file()`,
  checked relative to the current working directory (the script is
  always invoked as `python3 .desk_temp/build_widget.py <dir>` from
  the project root, per its own documented usage).
- **A loud warning to stderr, not a hard failure.** The stale copy
  isn't necessarily what's running *right now* (the user could be
  correctly invoking `.desk_temp/build_widget.py`) -- the warning is
  about ambiguity/risk of running the wrong one *next time*, not a
  certainty that something just went wrong. Matches the FEEDBACK
  item's own suggested wording style.
- **Old-build cleanup**: `build_widget()` already returns the
  assembled tempui text with the keyword known
  (`manifest['keyword']`); `main()` already knows `temp_ui_dir`. After
  writing the fresh `.desk_temp/<uuid>` file, scan `temp_ui_dir` for
  other files whose first line matches `DefineWidget\t<keyword>\t`
  and delete them -- cheap (a handful of files at most, only ever
  called at build time, not on any hot path), and doesn't need to
  parse the file beyond its own first line.
- **`err.status`, set right before throwing, not restructuring the
  message.** Minimal, additive change -- the existing message string
  (with the status embedded in the text) stays exactly as-is for
  anything already reading it as free text; `err.status` is new,
  purely additive.

## Step-by-step implementation

1. `temp_ui.py`, `_BUILD_WIDGET_SCRIPT`'s `main()`: at the very start,
   check whether `Path("scripts/build_widget.py")` exists and, if so,
   print a warning to stderr naming both paths (own canonical location
   plus the stale one) -- does not abort the build, just warns.
2. `temp_ui.py`, same script's `main()`: after successfully writing
   the fresh `.desk_temp/<uuid>` file, scan `temp_ui_dir` for any
   *other* file whose content starts with `DefineWidget\t<keyword>\t`
   (the same keyword just built) and delete it.
3. `temp_ui.py`: bump `TEMPUI_DOC_VERSION`, add the matching comment
   block and `_NEW_FEATURES_DOC` entry describing both build-script
   behavior changes above.
4. `bridge_client.py`'s `call()` helper: add `err.status =
   response.status;` right before the existing `throw err;` (the
   error is already constructed as a variable before throwing, or
   needs to become one if it's currently `throw new Error(...)`
   inline -- check the real current shape first).
5. New/extended verify coverage (see below); run the full
   `tests/verify/` suite.

## Key tradeoffs

- The sibling-check only looks for `scripts/build_widget.py`
  specifically (the one historical location the FEEDBACK item found),
  not a general "any other build_widget.py anywhere in the project"
  scan -- matches the FEEDBACK item's own scoped suggestion, not
  over-engineered for locations that were never a real seeded
  convention.
- The old-build cleanup only fires on a *successful* build (after the
  fresh file is written) -- a failed build leaves prior output
  untouched, which is correct (nothing new to prefer over the old
  one).

## Verification

New checks, real (no mocking):
- `tests/verify/verify_ensure_build_widget_script.py` (extending the
  existing file) or a focused new script: running the generated
  `.desk_temp/build_widget.py`'s `main()` in a directory that also has
  a `scripts/build_widget.py` prints the warning to stderr; running it
  where no such sibling exists prints nothing extra.
- `tests/verify/verify_build_widget_concat_order.py` (extending the
  existing file, which already does real `tsc`/`node` builds) or a
  focused new script: building the same keyword twice in a row leaves
  exactly one `DefineWidget` file for that keyword in `.desk_temp/`
  (the older one deleted), and a *different* keyword's own file is
  left untouched.
- `TEMPUI_DOC_VERSION` bumped, with a matching changelog entry.
- A new script (or extending an existing Bridge-API-focused one) for
  `err.status`: a real HTTP request through the Bridge client that
  gets a 403 (capability rejection) throws an `Error` whose `.status
  === 403`, distinguishable from a 400.
- Full `tests/verify/` regression suite.
