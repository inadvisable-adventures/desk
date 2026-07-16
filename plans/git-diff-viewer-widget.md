# Plan: TODO fd713a5 (COMPLETED) — Git Diff Viewer widget + a `git-diff` file-type-registry role

## Summary

A new `widgets/git_diff/` widget shows `git diff HEAD -- <path>` for a
single file, opened by clicking a file in the Git Status widget
(`widgets/git_status/widget.py`, currently a plain `QListWidget` with
no click handling at all). Also add `"git-diff"` to
`desk.file_type_registry.ROLES` (alongside `view`/`edit`), with its own
`find_git_diff_handler` mirroring `find_view_handler`/
`find_edit_handler`, and a shared `DeskWindow.open_git_diff(path)`
opener (mirroring `open_editor_or_scrap`) so the underlying
lookup-a-handler-and-open-it mechanism is reusable elsewhere, not
hardcoded into the Git Status widget's click handler alone.

## Design

### `desk.file_type_registry`

`git-diff` differs from `view`/`edit` in one important way: git diff
is meaningful for *any* file type, not specific extensions, so unlike
`BUILTIN_VIEW_WIDGET_BY_SUFFIX`/`BUILTIN_EDIT_WIDGET_BY_SUFFIX` (suffix
-keyed dicts), the built-in fallback is a single, unconditional
constant: `GIT_DIFF_WIDGET_ID = "git_diff"`.
`find_git_diff_handler(registry, path) -> str` (not `str | None` --
always resolves, unlike its two siblings) checks the dynamic registry
first (`_find_handler(registry, path, "git-diff")`), falling back to
`GIT_DIFF_WIDGET_ID` unconditionally.

### `widgets/git_diff/` (new)

`GitDiffWidget.set_file(path: Path) -> None` (same public shape as
Editor/Markdown/SVG Editor's own `set_file`). Runs `git diff HEAD --
<path>` **on a background thread**, reporting back via a `_Relay`
(`pyqtSignal`) — the same shape `git_status`/`todo` widgets already use
for their own `git`/subprocess calls, per `LEARNINGS.md`'s "a blocking
`subprocess.run()` on the Qt GUI thread freezes the whole app's UI
feedback, not just the caller" — `git diff` is no exception, even for a
single file (a slow pre-commit-adjacent hook, a `.git` lock, or a huge
file could all still block). `find_git_root` (`desk.git_utils`, itself
a blocking subprocess call) is resolved *inside* the same background
thread call, not on the GUI thread first — `git_status/widget.py`
calls it synchronously today, but that's an existing, separate wart,
not something to copy into a fresh widget.

Binary detection honors both signals the TODO calls out: git's own
diff output (`"Binary files "` appears in stdout when git itself
detects binary content) is authoritative and checked first; ADDITIONALLY,
if the file still exists locally, `desk.file_type_registry
.looks_like_text_file(path)` is checked as a second signal. Order
matters for one real correctness reason: a **deleted** file (a common,
legitimate git-status entry) no longer exists on disk, so
`looks_like_text_file` on a missing path returns `False` (its own
`OSError` -> "can't tell, don't guess yes" convention) — treating that
as "binary" would incorrectly hide a perfectly good, meaningful diff
for every deleted file. So: binary if `"Binary files "` in the diff
output, OR (`path.is_file()` and not `looks_like_text_file(path)`) --
the local-file check is skipped entirely when the path doesn't
currently exist, letting a deleted file's real diff render normally.
Empty diff output (clean/untracked file) shows a plain "(no differences
from the last commit)" message rather than a blank pane.

`get_widget_local_storage`/`set_widget_local_storage` persist
`{"path": str(self._path)}` via `desk.persisted_path
.resolve_persisted_path`, the same convention Editor/Markdown/SVG
Editor already use, so the last-viewed diff survives a Desk reload.

`widget.json`: `kind: "python"`, no special capabilities.

### Shared opener (`current_context`/`DeskWindow`)

`current_context.set_git_diff_opener`/`get_git_diff_opener` (paired
functions, same shape as `set_editor_or_scrap_opener`), bound at
`DeskWindow` startup to a new `DeskWindow.open_git_diff(path)` mirroring
`open_editor_or_scrap`: looks up `find_git_diff_handler`, opens that
widget centered, calls its `set_file(path)`. Simpler than
`open_editor_or_scrap` — no Scratch-note fallback branch, since
`find_git_diff_handler` always resolves to a real widget id.

### Git Status widget wiring

`_populate_list` stores each row's resolved absolute `Path` (parsed
from the porcelain line: skip the fixed 2-char status + 1 space
prefix; for a rename/copy line (`old -> new`), take the part after
`" -> "`) as `Qt.ItemDataRole.UserRole` item data at population time
(not re-parsed at click time) — the `CLEAN_PLACEHOLDER` row gets no
such data, so clicking it is naturally a no-op.
`self._list.itemClicked.connect(...)` (single click, matching the
TODO's own "when clicked" wording) reads that data and calls
`current_context.get_git_diff_opener()(path)`.

### Scope note: `ProjectFilesWidget`

The TODO names `ProjectFilesWidget` as a place that "can offer a Git
Diff action the same way" as Git Status's click handler — but
`ProjectFilesWidget` today has **no** context menu at all (only a
double-click -> view-handler lookup); there's no existing Edit/View
menu entry point to extend, and building a brand-new right-click menu
is a separate, larger UI surface not concretely asked for here (open
questions: right-click vs. some other gesture, which actions it should
list, contained scope for CLAUDE.md's "don't add features beyond what
the task requires"). This plan builds the reusable
`find_git_diff_handler`/`open_git_diff` infrastructure so that addition
stays cheap later, but does **not** add a new context menu to
`ProjectFilesWidget` in this pass — noted explicitly in the TODO
completion entry rather than silently dropped.

## Verification

- New `tests/verify/verify_git_diff_widget.py`: `find_git_diff_handler`
  (registry hit, builtin fallback, never returns `None`); the widget's
  binary detection (git-reported binary via a real repo + real binary
  file; a deleted file's real diff still renders despite
  `looks_like_text_file` returning `False` for it); empty-diff message;
  `get_widget_local_storage`/`set_widget_local_storage` round-trip;
  real end-to-end `set_file` against a real temporary git repo with an
  actual uncommitted change (not just mocked subprocess output).
- New checks (or a new test) confirming Git Status's click handler
  resolves the correct path from both a plain modified-file porcelain
  line and a rename line (`R  old -> new`), and that clicking the
  `CLEAN_PLACEHOLDER` row is a no-op.
- Full `tests/verify/` regression suite.
