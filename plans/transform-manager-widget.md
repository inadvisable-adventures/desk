# Plan: TODO b5e15cf — Transform Manager widget

See `design-docs/transforms.md`'s "Transform Manager widget" section
for the design rationale.

## New files

- **`widgets/transform_manager/widget.json`**: `kind: "python"`,
  `entry: "widget.py"`, no capabilities.
- **`widgets/transform_manager/widget.py`**: `TransformManagerWidget`
  (`QWidget`), modeled on `EventLogWidget`'s plain `QTableWidget` shape
  (no existing "list/introspect other widgets or definitions" widget
  precedent to mirror instead).
  - Columns: **Name / Input Type / Output Type / Language / Config? /
    Identity? / Location**, plus a trailing **Promote** button column.
  - A **Refresh** button (toolbar row, same placement convention as
    Event Log's Live Tail/Clear Log row) re-runs discovery: resolves
    `.desk_temp/transforms/`/`desk_transforms/` from
    `current_context.get_current_desk_directory()`, calls
    `desk_services.transforms.get_service().discover(desk_temp_dir,
    project_dir)` **directly** (no `current_context` indirection
    needed here -- this widget IS the dedicated UI for this exact
    service, the same relationship `GitStatusWidget` has to
    `find_git_root`), and repopulates the table from the returned
    `(transforms, errors)`.
  - Also populates one row per entry in `errors` (a transform that
    failed to discover, e.g. a Python transform under `.desk_temp/`) --
    a distinct visual treatment (e.g. the row's Name column shows the
    directory name + a `[!]`-prefixed error message in place of the
    other columns) rather than silently omitting it, so an author gets
    real feedback on why their transform didn't show up as usable.
  - The Promote button is only shown/enabled for a row whose
    `TransformInfo.location == "desk_temp"`. Clicking it calls
    `current_context.get_popup_opener()` (TODO `359684f`) for a
    confirmation: title `"Promote Transform"`, message
    `f"Promote '{name}' to desk_transforms/? This moves its source "
    "into the project, to be committed to version control going "
    "forward."`, buttons `["Promote", "Cancel"]`, default `"Cancel"`.
    On `"Promote"`, calls `get_service().promote(transform_id,
    desk_temp_dir, project_dir)` and refreshes the table; a
    `TransformError` shows a second popup (`["OK"]`) with the failure
    reason instead of silently doing nothing.
  - Auto-refreshes once at construction (`initial=True`-style, matching
    `GitStatusWidget._poll`'s own "don't leave a freshly-placed widget
    blank until a manual click" convention) -- no file-watching beyond
    that (per the design doc: transforms aren't edited anywhere near
    as often as `TODO.md`; a manager/introspection widget, not a
    live-edited document).

## Verification

- New `tests/verify/verify_transform_manager_widget.py`:
  - Populates the table correctly from a mix of `.desk_temp`- and
    project-level real transform directories (real `transform.json`
    files on disk, not mocked `TransformInfo` objects) -- correct
    Name/Input/Output/Language/Config?/Identity?/Location per row.
  - A discovery error (a real Python transform under a real
    `.desk_temp/transforms/` directory) shows as a distinct error row,
    not silently dropped.
  - The Promote button is present only on `.desk_temp`-sourced rows,
    absent on project-level ones.
  - Clicking Promote shows a confirmation popup (patch
    `current_context.get_popup_opener` to a fake returning `"Promote"`/
    `"Cancel"` in separate test runs) and only actually calls
    `TransformsService.promote` (confirmed via a real `shutil.move` --
    the file really moves on disk) when confirmed; declining leaves
    the `.desk_temp/` source untouched.
  - Refresh re-discovers and repopulates (add a transform on disk
    between two calls, confirm the second Refresh sees it).
- Full `tests/verify/` regression suite.
