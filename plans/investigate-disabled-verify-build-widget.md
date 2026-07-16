# Plan: TODO 1082bd4 (COMPLETED) — investigate `disabled_verify_build_widget.py`

## Investigation

This script `import build_widget`s directly from `scripts/`, which TODO
`029047b` deleted (moved into `src/desk/temp_ui.py`'s
`_BUILD_WIDGET_SCRIPT`, generated into `.desk_temp/build_widget.py` at
runtime). Unlike `disabled_verify_build_widget_doc_and_seed.py`
(genuinely superseded design, deleted outright), this script's actual
*coverage* is still valuable and non-redundant: five distinct
`BuildError` scenarios (missing manifest keys, missing `.ts` file,
missing marker in `widget.html`, `tsc` absent from `PATH`) plus a "never
falls back to `npx`" source-content check — none of which
`verify_ensure_build_widget_script.py` (the still-enabled script
covering the *generated* script's happy path) exercises.

## Resolution

Rewrite, not delete: generate the real script into a fresh temp
`.desk_temp/` (`write_tempui_docs`, matching
`verify_ensure_build_widget_script.py`'s own pattern), dynamically
import it (`importlib.util.spec_from_file_location`, the same pattern
used throughout this project's own verification scripts) instead of a
static `scripts/` import, and build every fixture inline under
`tempfile.TemporaryDirectory()` instead of relying on the old
scratchpad fixture path (`FIXTURE = Path(".../scratchpad/
build_widget_test")`), which is session-specific and won't exist in a
future session. Every one of the 6 original checks carries over
unchanged in substance — only the module-loading and fixture-location
mechanics change.

## Verification

Re-run the rewritten script standalone (passes, all 6 original checks
represented); re-run the full `tests/verify/` suite and confirm the
disabled count drops to 15 with no new failures.
