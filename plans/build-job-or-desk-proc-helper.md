# `build_job_or_desk_proc.py` authoring helper (TODO `49e3732`)

## Summary

A new generated script, `.desk_temp/build_job_or_desk_proc.py`, mirrors
`build_widget.py`'s convenience for `DefineWidget` but for `Job`/
`DeskProc`: given a summary, a script file, and (for `Job`) a `kind`
plus optional `Capability` names, it does the base64-encode-and-chunk
work and writes a ready-to-drop tempui file under `.desk_temp/`,
printing the path -- removing the hand-rolled `base64.b64encode(...)`
one-liner an author currently has to write from scratch every time.
One script, two subcommands (`desk-proc`, `job`), not two separate
scripts, since the two keywords' encoding is otherwise identical.
Generated and kept fresh via the exact same `SPLIT_DOC_CONTENT`/
`TEMPUI_DOC_VERSION` machinery `build_widget.py` itself already uses --
not a one-time seed.

## Affected files

- `src/desk/temp_ui.py` -- new `_BUILD_JOB_OR_DESK_PROC_SCRIPT` string
  constant (the script's full source, mirroring `_BUILD_WIDGET_SCRIPT`'s
  own triple-single-quote wrapping), `BUILD_JOB_OR_DESK_PROC_SCRIPT_FILENAME`,
  added to `SPLIT_DOC_CONTENT`; `TEMPUI_DOC_VERSION` bump +
  `_NEW_FEATURES_DOC` entry; `DOC_TEMPLATE`'s existing "There's also
  `build_widget.py`" paragraph extended to mention the new script;
  `_JOBS_DOC`/`_DESK_PROC_DOC` each gain a short cross-reference to it.
- `tests/verify/` -- new coverage.

## Design decisions

- **Self-contained, no `desk` package import** -- same hard constraint
  `_BUILD_WIDGET_SCRIPT` already has (this script runs inside whatever
  *other* project's `.desk_temp/` it's synced into, which has no
  `desk` package installed). Verify coverage compensates by importing
  the real `desk.temp_ui.parse_job`/`parse_desk_proc` separately (that
  part of the test runs with this repo's own `desk` on `sys.path`, the
  generated script itself never does) to confirm the generated text
  actually round-trips through the real parser -- not just "looks
  right by eye."
- **One script, two subcommands (`desk-proc`, `job`), not two
  scripts** -- per the TODO item's own explicit instruction, since the
  underlying base64/chunk/write logic is identical either way and a
  single discoverable file beats two near-duplicates.
- **Plain positional CLI arguments, not a `build_widget.py`-style
  source *directory* convention.** `DefineWidget` authoring is
  genuinely multi-file (a `.ts`, a `widget.html` template, a
  `tsconfig.json`, a `widget.json` manifest) and a real compile step
  (`tsc`) sits between source and output -- a directory convention
  earns its keep there. A `Job`/`DeskProc` script is just one file plus
  a short summary string (and, for `Job`, a kind and optional
  capability names) -- inventing a manifest-file convention for that
  would reintroduce exactly the authoring ceremony `Job`/`DeskProc`
  exist to avoid. Plain args mirror the DSL's own first-line shape
  almost exactly: `desk-proc SUMMARY SCRIPT` ~ `DeskProc<TAB>summary`;
  `job KIND SUMMARY SCRIPT [--capability NAME]...` ~
  `Job<TAB>kind<TAB>summary` + `Capability<TAB>name` lines.
- **A tab or newline inside `summary`/a capability name is a build
  -time error, not silently-corrupting output.** The tempui format's
  first line is TAB-delimited; an embedded tab would read as an extra
  field boundary and an embedded newline would end the line early --
  either way a **file that looks fine but parses wrong**, worse than
  refusing to build it. Checked once, in one small helper, applied to
  every free-text field this script accepts.
- **No dedup/cleanup pass** (unlike `build_widget.py`'s
  `_delete_other_builds_for_keyword`) -- that logic exists specifically
  because a `DefineWidget` *keyword* is a reusable registration that
  can accumulate stale re-builds; a `Job`/`DeskProc` file is a wholly
  independent one-shot instance every time, so there's no equivalent
  "same keyword, superseded" concept to clean up.

## Step-by-step implementation

1. Write the script's own source (`_BUILD_JOB_OR_DESK_PROC_SCRIPT` in
   `temp_ui.py`): `BuildError`, `_chunk`, `_check_single_line_safe`,
   `build_desk_proc(summary, script_path) -> str`,
   `build_job(kind, summary, script_path, capabilities) -> str`,
   `argparse`-based `desk-proc`/`job` subcommands, `main(argv) -> int`
   writing `.desk_temp/<uuid>` and printing the path -- same shape
   `build_widget.py`'s own `main` already establishes.
2. `temp_ui.py`: `BUILD_JOB_OR_DESK_PROC_SCRIPT_FILENAME =
   "build_job_or_desk_proc.py"`; add to `SPLIT_DOC_CONTENT`; bump
   `TEMPUI_DOC_VERSION` (with a matching comment-block entry); add a
   `_NEW_FEATURES_DOC` "## Version N" entry; extend `DOC_TEMPLATE`'s
   existing `build_widget.py` paragraph to also name this script;
   extend `_JOBS_DOC`/`_DESK_PROC_DOC` with a short "or build one with
   `build_job_or_desk_proc.py`" cross-reference each.
3. New verify coverage (see below); run the full `tests/verify/` suite.
4. Re-sync this repo's own `.desk_temp/` (`ensure_docs_current`) so the
   new script is actually present here too, matching what a real
   project would get on its next Desk open/switch.

## Key tradeoffs

- No validation that `script_path`'s own content is syntactically valid
  Python/HTML -- this script's job is packaging, not linting; a
  malformed script still base64-round-trips fine and fails, if it's
  going to fail, at Job/DeskProc *run* time (via View Code / a real
  traceback), the same as it would if hand-authored.
- Doesn't reach into an already-open Desk to place/preview the result
  -- prints the path, same as `build_widget.py`; opening/placing it is
  still the normal "drop a file, watch for the notification" flow.

## Verification

New checks, real (no mocking):
- `tests/verify/verify_build_job_or_desk_proc_script.py` (new): loads
  `_BUILD_JOB_OR_DESK_PROC_SCRIPT` from `desk.temp_ui` and execs it as a
  real module (same `importlib`-from-source-string pattern other
  generated-script verify coverage uses, if any precedent exists --
  otherwise write the string to a real temp file and run it as a real
  subprocess, matching how a project would actually invoke it); for
  each of `desk-proc` and `job` (both `python`- and `html`-kind):
  builds a real tempui file from a real script fixture, then imports
  this repo's own `desk.temp_ui.parse_desk_proc`/`parse_job` to confirm
  the generated file round-trips (summary, kind, capabilities, and the
  script's own decoded content all match); confirms a tab/newline in
  `summary` or a capability name is rejected with a clear error, not
  silently corrupted output; confirms a missing script file errors
  clearly rather than crashing with a raw traceback.
- `tests/verify/verify_tempui_build_job_or_desk_proc_doc.py` (new,
  mirrors `verify_tempui_desk_proc_doc.py`'s shape): `TEMPUI_DOC_VERSION`
  bumped; `build_job_or_desk_proc.py` registered in `SPLIT_DOC_CONTENT`;
  `DOC_TEMPLATE` mentions it; `_JOBS_DOC`/`_DESK_PROC_DOC` each
  cross-reference it; `_NEW_FEATURES_DOC` has a matching entry.
- Full `tests/verify/` regression suite.
