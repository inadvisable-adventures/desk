# Fix hardcoded sibling-checkout paths in `tests/verify/` scripts (COMPLETED)

TODO `c393520`.

## Summary

`LEARNINGS.md` (added while working TODO `551014c`/`f4a7872`/`1ceb701`)
already documents the core gotcha: a `tests/verify/` script that
hardcodes `REPO_ROOT = Path("/Users/mphair/inadvisable-adventures/desk")`
(a literal absolute path to one specific checkout) instead of the
portable `REPO_ROOT = Path(__file__).resolve().parents[2]` form doesn't
fail or error when run from a *different* checkout (e.g. this
`desk-dev-2` one) -- it silently imports and tests the *other*
checkout's code, so it can report `PASS` while validating code this
session never touched. `PARKINGLOT.md` has a stale entry estimating
"~28 scripts" affected and recording that only
`verify_claude_desk_widget.py` was ever actually fixed.

Re-auditing for this TODO found the real scope is bigger than that
estimate: 72 scripts under `tests/verify/` reference the literal
`/Users/mphair/inadvisable-adventures/desk` path somewhere in their
code (not just in the specific `REPO_ROOT = Path("...")` shape the
`LEARNINGS.md` entry called out) -- `sys.path.insert(0, "/Users/.../
desk/src")` and `sys.path.insert(0, "/Users/.../desk/widgets/
<name>")` calls with no `REPO_ROOT` variable involved at all, a bare
`REPO_ROOT = "/Users/.../desk"` string (not wrapped in `Path(...)`),
`WIDGETS_DIR = Path("/Users/.../desk/widgets")`,
`discover_widgets(Path("/Users/.../desk/widgets"))`,
`importlib.util.spec_from_file_location(name, "/Users/.../desk/
widgets/<x>/widget.py")` (including one f-string variant), and a
hardcoded doc path (`Path("/Users/.../desk/shared_development_process.md")`).
Currently only 5 of these 72 actually fail outright in this checkout
(the sibling checkout's `window.py` has drifted enough to raise
`AttributeError` for `_FakeWindow`); the rest still silently pass
while exercising the *other* checkout's code, which is the more
insidious half of the bug.

Scope: every script in `tests/verify/` (`disabled_`-prefixed ones
included, since they still run when un-disabled later) that contains
the literal substring `/Users/mphair/inadvisable-adventures/desk`.
Confirmed via `grep -rl '/Users/mphair/inadvisable-adventures/desk'
--include='*.py' .` that no file outside `tests/verify/` has this
problem.

## Affected files

The 72 files (from `grep -rl '/Users/mphair/inadvisable-adventures/
desk' tests/verify/`), grouped by the shape of their hardcoded
reference(s):

- **`REPO_ROOT = Path("/Users/.../desk")`** (most common; ~27 files,
  including 4 `disabled_` ones) -- e.g. `verify_svg_editor_widget.py`,
  `verify_voice_input_widget.py`, `verify_app_dsl_codegen.py`.
- **`REPO_ROOT = "/Users/.../desk"`** (bare string, not `Path(...)`)
  -- `verify_app_dsl_parse.py`, `verify_event_recorder_widget.py`.
- **A standalone `sys.path.insert(0, "/Users/.../desk/src")` and/or
  `sys.path.insert(0, "/Users/.../desk/widgets/<name>")` with no
  `REPO_ROOT` variable at all** -- e.g. `verify_build_widget.py`,
  `verify_state_manager_widget_ui.py`, `verify_widget_titlebar_subtitle.py`,
  and ~30 others.
- **A hardcoded `Path("/Users/.../desk/widgets")` assigned to some
  other name** (`WIDGETS_DIR`, `REAL_WIDGETS = discover_widgets(...)`,
  etc.) -- `verify_widgets_use_popup_service.py`,
  `verify_new_desk_existing_project_gaps.py`,
  `verify_viewer_widgets_edit_button.py`.
- **A hardcoded widget-source path passed straight to
  `importlib.util.spec_from_file_location`** -- `verify_event_viewer_widget.py`,
  `verify_file_explorer_fallback_chain.py`,
  `verify_viewer_widgets_edit_button.py` (one uses an f-string with a
  variable widget name spliced in).
- **A hardcoded doc path** -- `verify_fork_development_process_doc.py`
  (`Path(".../desk/shared_development_process.md")`).

(Full, exact list captured at plan-authoring time via
`grep -rl '/Users/mphair/inadvisable-adventures/desk' tests/verify/`
-- re-run that command to get the authoritative list at
implementation time, since new scripts may have been added since.)

## Approach

Standardize every one of these files on the same portable idiom
already used correctly elsewhere in `tests/verify/`:

```python
from pathlib import Path
...
REPO_ROOT = Path(__file__).resolve().parents[2]
```

(`tests/verify/<script>.py` -> `tests/verify/` -> repo root, i.e.
`parents[2]`, matching the already-correct scripts.)

Then rewrite every hardcoded reference in the file in terms of that
`REPO_ROOT`, keeping each call site's existing type expectations
(`str` vs. `Path`) so behavior doesn't change beyond no-longer-being-
hardcoded:

- `Path("/Users/.../desk")` -> `REPO_ROOT`
- `"/Users/.../desk"` (bare string) -> `str(REPO_ROOT)`
- `"/Users/.../desk/src"` -> `str(REPO_ROOT / "src")`
- `"/Users/.../desk/widgets/<name>"` -> `str(REPO_ROOT / "widgets" / "<name>")`
- `Path("/Users/.../desk/widgets")` -> `REPO_ROOT / "widgets"`
- `importlib.util.spec_from_file_location("x", "/Users/.../desk/widgets/<w>/widget.py")`
  -> `str(REPO_ROOT / "widgets" / "<w>" / "widget.py")` (an f-string
  with an interpolated widget-name variable becomes
  `str(REPO_ROOT / "widgets" / widget_name / "widget.py")`)
- `Path("/Users/.../desk/shared_development_process.md")` -> `REPO_ROOT / "shared_development_process.md"`

Where a file currently has `REPO_ROOT` (or an equivalent hardcoded
`sys.path.insert`) defined *after* another line that already needs a
hardcoded path (e.g. a `sys.path.insert(0, ".../desk/src")` that must
run before `import desk.something`, followed later by a redundant
hardcoded `REPO_ROOT = Path(".../desk")`), move the `REPO_ROOT`
definition up to the earliest point it's needed (right after the
`os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")` line and any
existing `from pathlib import Path` import, adding that import if a
file doesn't already have it) and delete the now-redundant later
definition.

This is mechanical enough to script: a small one-off Python script
(scratch, not checked in) does the substitution per the shapes above
across all affected files, followed by:

1. `python3 -m py_compile` on every touched file (catches syntax
   errors from the rewrite).
2. `grep -rl '/Users/mphair/inadvisable-adventures/desk' tests/verify/`
   returns empty (no literal sibling-checkout path remains anywhere
   in `tests/verify/`).
3. Run every non-`disabled_` script in `tests/verify/` (`QT_QPA_
   PLATFORM=offscreen`) and confirm the failing set is unchanged from
   the pre-existing baseline captured via `git stash` (should shrink
   by the same amount the `_FakeWindow` `AttributeError` currently
   causes once these scripts are validating *this* checkout's
   `window.py` instead of the sibling one's -- if the sibling's
   `window.py` genuinely predates this checkout's own fixes, running
   against the right code should actually make some of today's 5
   failures disappear, not persist).
4. Spot-run 2-3 of the previously-un-runnable `disabled_` scripts
   directly (they won't be re-enabled by this TODO, just no longer
   hardcoded) to confirm the substitution didn't break their imports.

## Also update

- `PARKINGLOT.md`'s stale "~28 scripts hardcode..." entry: remove it
  once this TODO ships (superseded -- the cleanup it was flagging is
  now done, and the real count it undercounted is captured in this
  plan/TODO instead).
- `LEARNINGS.md`'s existing entry about this gotcha stays (it's still
  a valid, non-obvious pitfall for any *new* script written in the
  future) but doesn't need the count corrected in place -- this plan
  is the historical record of the actual scope.
