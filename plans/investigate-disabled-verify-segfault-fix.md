# Plan: TODO f7c2f60 (COMPLETED) — investigate `disabled_verify_segfault_fix.py`

## Investigation

Four independent test functions, three different staleness issues:

- `test_refresh_external_path_status_hardened`'s widget list still
  includes both `widgets/markdown_ex/widget.py` (renamed to
  `widgets/markdown/widget.py` by TODO `858752b` — the list already
  separately has an entry for the *current* `markdown` path too, so
  this is now a duplicate of an already-covered widget under its old,
  nonexistent path) and `widgets/svg_viewer/widget.py` (retired,
  folded into `widgets/image_viewer/widget.py` by TODO `4d21e7c`, this
  same session).
- `test_open_index_hardened` imports `widgets/file_explorer/widget.py`
  (renamed to `widgets/project_files/widget.py` by TODO `8385dcc`) —
  but the method under test (`_open_index`) still exists unchanged
  there. The deeper issue: `_open_file` (TODO `efdad99`) now dispatches
  through a registered-view-handler → editor-or-scrap fallback chain
  using `current_context.get_centered_widget_opener()`, not the plain
  `current_context.get_widget_opener()` this test registers its broken
  fake opener through — for a bare `.txt` file with no file-type
  -registry entry, `_open_file` wouldn't even reach the fake opener at
  all with the registry empty (it'd fall through to the editor-or-scrap
  path instead), so simply fixing the import path alone would leave
  this test silently not exercising what it claims to (a downstream
  widget's broken `set_file()` not crashing `_open_in_widget`'s own
  `try`/`except`, the actual hardening this script is about).
- `test_editor_unreadable_file_no_crash`/
  `test_regression_normal_case_still_works` are unaffected by either
  rename — confirmed by reading `widgets/editor/widget.py` and
  `widgets/markdown/widget.py`'s current `_load_file`/`set_file`
  directly.

## Resolution

- Drop the duplicate `markdown_ex` entry; replace `svg_viewer` with
  `image_viewer` in the widget list.
- Rewrite `test_open_index_hardened` against the current dispatch
  chain: register a fake file-type-registry entry (`.txt` → a
  `"broken_widget"` view handler) via
  `current_context.set_file_type_registry_provider` *before*
  constructing the widget (`self._file_type_registry` is read once at
  `__init__`), and `current_context.set_centered_widget_opener(...)`
  (not `set_widget_opener`) returning a `Broken` object whose
  `set_file` raises — this actually reaches `_open_in_widget`'s
  `try`/`except` this time.
- Leave the other two test functions as-is.

## Verification

Re-run standalone (passes, all 4 functions); full `tests/verify/`
suite: disabled count drops to 2, 0 new failures.
