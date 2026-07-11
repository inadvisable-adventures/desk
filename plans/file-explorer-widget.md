# File Explorer widget

TODO `b927389`.

## Summary

"Add a tree-view project directory/file explorer widget. Add a search/
filter textbox at the top which temporarily hides everything but the
tree-paths to the results and the results themselves... clearing the
search should restore the view but the current file should remain
selected. if a user double-clicks on a filename or hits enter while a
filename is selected, open the file in a new instance of the Editor
widget." A new `kind: "python"` widget (`widgets/file_explorer/`).

## Key decisions

- **`QTreeView` + `QFileSystemModel` for normal browsing** (both
  built into `PyQt6.QtGui`/`PyQt6.QtWidgets` — no new dependency),
  scoped to the current Desk directory via `setRootPath`/
  `setRootIndex`, lazy-loading each directory's children on expand
  (Qt's native behavior) so browsing a large tree stays cheap. Only
  the Name column is shown (header hidden, Size/Type/Date-Modified
  columns hidden) — this is a lean sidebar-style explorer, not a full
  file-manager view.
- **Search does *not* use `QSortFilterProxyModel.setRecursiveFilteringEnabled`,
  despite that looking like the obvious built-in fit.** Verified directly
  (a throwaway headless script against a real temp tree) that it doesn't
  work correctly on top of `QFileSystemModel`: `QFileSystemModel` only
  populates a directory's children lazily, when something (normally a
  view expanding it) asks for them, and the recursive-filter machinery
  only sees data the model has already materialized — a match several
  levels deep in a never-expanded branch is invisible to it, so a fresh
  widget's search would silently miss real matches. (Also hit a
  segfault from holding a `QModelIndex` across a filter-invalidation
  instead of re-mapping it fresh — a `QModelIndex` is only valid until
  the next model-invalidating change to the model it came from.)
  - **Fix: a bespoke, synchronous search-results builder.** When the
    filter box is non-empty (debounced ~200ms via `QTimer`, matching
    the TODO widget's own debounce pattern, so fast typing doesn't
    re-walk on every keystroke), walk the tree directly with
    `Path.iterdir()` (recursive, depth-first), skipping common heavy/
    irrelevant directories (`.git`, `__pycache__`, `node_modules`,
    `.venv`, `venv`, `build`, `dist` — the same set this repo's own
    `.gitignore` already treats as noise), and build a `QStandardItemModel`
    containing only: a match itself (case-insensitive substring on the
    name), or a directory that contains at least one match somewhere
    beneath it (kept purely as a path to the match, per the TODO's own
    worked example: searching "foo" under `(a (b ...) (c (foo) ...) (d
    ...))` shows only `a -> c -> foo`, not `b`/`d`). Swapped onto the
    tree view in place of the `QFileSystemModel` for the duration of
    the search, then `expandAll()` so results are immediately visible
    with no manual expanding. Each item's real path is stashed via
    `Qt.ItemDataRole.UserRole` (mirrors how the model exposes it
    normally, just without `QFileSystemModel.filePath()` to call).
    Verified this approach directly against the same test tree
    (`a -> c -> foo.txt` shown, `b`/`d` excluded) — the intended
    result, and correct regardless of prior expand state.
  - **Known tradeoff**: the walk is synchronous on the GUI thread (not
    backgrounded, unlike the TODO/Git Status widgets' background-thread
    git calls) — acceptable for a typical project tree with the skip
    -list above, but a large enough tree (large monorepo, deep
    generated-output that isn't in the skip list) could visibly stall
    typing. Not addressed here; worth revisiting if it's a problem in
    practice (background thread + a "searching…" state, same shape as
    the Git Status widget's own background poll).
- **Clearing the filter restores the `QFileSystemModel` and re-selects
  the previously-selected file** (tracked as a `Path | None` alongside
  the tree, updated on any `currentChanged` from either model —
  `QFileSystemModel.filePath(idx)` or the `UserRole` data depending on
  which model is live) via `fs_model.index(str(path))` +
  `tree.setCurrentIndex(...)`/`scrollTo(...)`. If the file no longer
  exists (deleted while the widget had it selected), the restore is a
  no-op (an invalid index -> nothing gets selected) rather than an
  error.
- **Opening a file: reuses the established "widget opener" hook**
  (`desk.shell.current_context.get_widget_opener()`, the same one the
  TODO widget's "open plan" button already uses to open the Markdown
  widget) — `opener("editor")` places a **new** Editor widget instance
  (matching the TODO's explicit "a new instance"; `open_widget_content`
  always places a fresh instance unless a saved `instance_id` is
  passed, which this call site never does) and calls `.set_file(path)`
  on the returned widget, guarded with `hasattr` per the established
  convention.
  - **Requires a small, in-scope addition to `EditorWidget`**: it
    currently only has a private `_load_file(path)`, invoked from its
    own Open-button flow — no public `set_file` like
    `MarkdownWidget`/`MarkdownExWidget` already have for exactly this
    "opened programmatically by another widget" purpose. Adding a thin
    `set_file(path) -> self._load_file(path)` closes that gap; a
    freshly-placed Editor instance has no unsaved-changes state to
    worry about, so no confirmation prompt is needed here (unlike the
    Editor's own internal Open button, which does check).
  - Only a **file** row triggers this (double-click or Enter with a
    file selected); double-clicking/Enter-ing a directory just
    expands/collapses it (or, in search mode, is a no-op — mid-search
    directories are shown purely as breadcrumbs to a match, expanding
    them does nothing new since `expandAll()` already expanded
    everything).
- **Directory seeding**: `current_context.get_current_desk_directory()`,
  falling back to `Path.home()` — same as the TODO/Git Status widgets'
  *primary* directory (not just a file-dialog default like the Editor/
  Markdown/Sheet widgets use it). A small "Open Folder" toolbar button
  (`QFileDialog.getExistingDirectory`) lets the root be changed
  manually too, for when `current_context` isn't set yet or the user
  wants to browse elsewhere — matches the Open-button convention every
  other file-touching widget already has.
  - Inherits a known, pre-existing staleness bug (not something to fix
    here): `current_context`'s directory is set by `DeskWindow
    ._refresh_picker`, which runs *after* `_load_desk_widgets` on a
    Desk switch (though not on initial launch, per TODO 1a051d1) — see
    `PARKINGLOT.md`'s existing note on this. A widget placed as part of
    switching Desks can see the *previous* Desk's directory.

## New/affected files

- `widgets/file_explorer/widget.json` (new) — `{name: "File Explorer",
  kind: "python", entry: "widget.py", capabilities: [], default_size:
  360x640}`.
- `widgets/file_explorer/widget.py` (new) — `FileExplorerWidget(QWidget)`:
  - Toolbar: "Open Folder" button + a `QLineEdit` search box.
  - `QTreeView` showing a plain `QFileSystemModel` rooted at the
    current directory (Name column only, header hidden) when the
    search box is empty.
  - `_search_debounce` (`QTimer`, single-shot) triggered on
    `textChanged`; on fire, if the box is non-empty, builds and swaps
    in a `_build_search_model(root, query)` result (walk + skip-list,
    as above) and `expandAll()`s; if empty, swaps back to the
    `QFileSystemModel` and restores the remembered selection.
  - `_current_path` tracking via `QTreeView.selectionModel()
    .currentChanged`.
  - `_open_selected()` (double-click / `Return`/`Enter` key press on a
    file row) resolving the real path from whichever model is live,
    then `current_context.get_widget_opener()("editor").set_file(path)`.
- `widgets/editor/widget.py` — add public `set_file(path: Path) ->
  None` (thin wrapper around the existing `_load_file`).
- `design-docs/architecture.md` — new File Explorer Widget component
  entry.

## Verification

Headless, against a real temp directory tree (mirroring the TODO's own
`(a (b ...) (c (foo) ...) (d ...))` example):

- Normal-mode browsing: `QFileSystemModel` rooted correctly, only the
  Name column visible, lazy child population works (confirmed via
  `processEvents()` + `rowCount()`).
- `_build_search_model`: searching "foo" shows exactly `a -> c ->
  foo.txt` and excludes `b`/`d` (already confirmed directly while
  planning this — see Key Decisions); a skip-listed directory
  (`.git`/`node_modules`/etc.) containing a match is still excluded
  entirely (documented tradeoff, not a bug); clearing the query swaps
  back to `QFileSystemModel` and re-selects the previously-current
  path (and degrades to no selection, not an error, if that path was
  deleted in the meantime).
- Open action: selecting a file row and pressing Return, and double-
  clicking a file row, both call the widget-opener with `"editor"` and
  `set_file` with the right path (a fake opener hook substituted for
  the test, matching the TODO widget's own verification style for
  its "open plan" button); doing the same on a directory row does
  *not* try to open anything.
- `EditorWidget.set_file`: a round-trip (build an Editor, `set_file` a
  real temp file, confirm the text/label/lexer match what `_load_file`
  already produces via the Editor's own Open-button path).
- Real widget-loading path: `desk.widgets.discover_widgets` picks up
  the new manifest; `desk.shell.python_widget.PythonWidgetHost` builds
  a real `FileExplorerWidget` (matching the `markdown_ex` verification
  precedent — a literal `DeskWindow` construction hit an unrelated,
  pre-existing offscreen-`QtWebEngine` stall in this environment during
  `canvas.py` import, orthogonal to `kind: "python"` widgets; skipped
  for the same reason noted in `plans/markdown-ex-widget.md`).

## Status

Not yet implemented.
