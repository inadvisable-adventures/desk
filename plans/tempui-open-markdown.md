# TempUI: `OpenMarkdown` capability (COMPLETED)

TODO `42dd260`.

## Summary

"Add new tempui capabilities to allow claude to open markdown files in
the GUI." A third TempUI file type, `OpenMarkdown`, alongside the
existing `Question` and `LightningRound` (`.desk_temp/desk-temporary
-ui.md`): a fire-and-forget instruction (no `Answer`, Desk never
writes back to the file) that opens a target Markdown file in a new
Markdown (Extended) (`markdown_ex`) widget instance — reusing that
widget's existing public `set_file(path)` rather than adding a new
widget kind.

## Key decisions

- **DSL: `OpenMarkdown <path>`, a single line**, matching `Question`'s
  existing one-liner shape (`keyword rest-of-line...`, everything
  after the first space is one opaque value — handles a path
  containing spaces with no escaping needed, unlike `LightningRound`'s
  tab-separated fields, which exist specifically to disambiguate
  multiple values on one line; `OpenMarkdown` only ever has one).
  `path` may be absolute or relative to the current Desk's directory.
  No `Answer`-equivalent — this type is detected purely from its
  keyword and never mutated by Desk.
- **Reuses `markdown_ex`, not a new widget.** `MarkdownExWidget`
  already has exactly the needed `set_file(path: Path)`. Registering
  its widget id (`"markdown_ex"`) in the existing `TEMP_UI_WIDGET_IDS`
  set gets it the same `instance_id`-equals-tempui-file-uuid
  reconnect-on-restore handling `question`/`lightning_round` already
  have (`design-docs/architecture.md`'s Claude Widget entry describes
  the general pattern) — for free, this also means a `markdown_ex`
  instance opened via `OpenMarkdown` now survives a Desk save/reload
  with its file restored, which no *manually*-placed `markdown_ex`
  instance does today (no per-instance state payload yet — see
  `PARKINGLOT.md`). A manually-placed `markdown_ex` instance's restore
  path becomes a safe no-op under this change (its random instance_id
  won't match any real `.desk_temp/` filename, so the file read fails,
  kind falls back to `"question"`, and the `hasattr(content,
  "set_source_file")` guard skips it) — identical to its current
  "starts blank on reload" behavior, no regression.
- **Binding logic branches on file content, not a hardcoded method
  name.** `_bind_temp_ui_widget` (restore-on-load) and
  `_activate_temp_ui` (notification click) both currently hardcode
  `content.set_source_file(path)`. Both now go through one new shared
  `_bind_temp_ui_content(content, tempui_path, directory)`: detect the
  file's kind; for `open_markdown`, parse out its target path
  (resolved against `directory` if relative) and call
  `content.set_file(target)`; otherwise, the existing
  `content.set_source_file(tempui_path)` call, unchanged. This is the
  single source of truth for "which widget method gets which path,"
  shared by both the click path and the restore path, rather than
  duplicating the branch.
  - `PARKINGLOT.md`'s existing note on TempUI widgets needing a way to
    persist an "arbitrary user-chosen path" (not just their own
    uuid-named source file) is exactly what this type resolves, in the
    narrow way that note itself suggests as sufficient for now: the
    *tempui file* stays the uuid-controlled, restore-anchoring artifact
    (like `Question`/`LightningRound`'s own source file); it just
    carries an arbitrary path as payload instead of being the content
    itself. No `WidgetState.state` payload generalization needed.
- **No write-back, no self-write-suppression concern.** Unlike
  `Question`/`LightningRound` (which call `current_context
  .get_temp_ui_write_recorder()` before rewriting their own source
  file, so `TempUiManager`'s watcher doesn't mistake that write for an
  external edit), `OpenMarkdown` never touches the tempui file at all
  — Desk only reads it. Nothing new needed in `TempUiManager` itself.
- **Notification preview text**: `f"Open {target_path}"` (parsed from
  the file), matching how `Question`/`LightningRound` preview their
  own question/prompt text rather than a generic "New question:
  `<uuid>`" fallback.
- **Doc updates in two places**: `desk/temp_ui.py`'s `DOC_TEMPLATE`
  (the canonical, version-controlled source — written into a fresh
  `.desk_temp/` only if that directory doesn't already have the doc
  file, per `TempUiManager.provision`) *and* this repo's own
  already-provisioned `.desk_temp/desk-temporary-ui.md` copy (gitignored,
  not auto-refreshed by `provision()` since it already exists — same
  "hand-refresh the local copy" step the `LightningRound` addition
  needed).

## New/affected files

- `src/desk/temp_ui.py`:
  - `OPEN_MARKDOWN_KEYWORD = "OpenMarkdown"`.
  - `detect_temp_ui_kind` — third return value `"open_markdown"`.
  - `parse_open_markdown(text: str) -> str | None` — extracts the
    path string from the first non-blank line if it's an
    `OpenMarkdown` line, else `None`.
  - `DOC_TEMPLATE` — new `## The TempUI DSL: OpenMarkdown` section;
    intro paragraph updated from "two file types" to "three."
- `src/desk/shell/window.py`:
  - `MARKDOWN_EX_WIDGET_ID = "markdown_ex"`, added to
    `TEMP_UI_WIDGET_IDS`.
  - Import `parse_open_markdown`.
  - New `_bind_temp_ui_content(content, tempui_path, directory)` and
    `_resolve_open_markdown_target(tempui_path, directory)` helpers.
  - `_bind_temp_ui_widget`/`_activate_temp_ui` — call the new shared
    helper instead of `content.set_source_file(...)` directly.
  - `_temp_ui_widget_id_for` — route `"open_markdown"` →
    `MARKDOWN_EX_WIDGET_ID`.
  - `_notify_temp_ui` — preview text branch for `"open_markdown"`.
- `.desk_temp/desk-temporary-ui.md` (gitignored, not committed) —
  hand-refreshed to match the new `DOC_TEMPLATE`, so this repo's
  already-running Desk instance (and the `claude` widget it launches,
  which is told to read exactly this file) picks up the new capability
  without needing a fresh `.desk_temp/` provision.
- `design-docs/architecture.md` — a short addendum on the Markdown
  (Extended) Widget entry noting it's also TempUI-backed via
  `OpenMarkdown`.

## Verification

Headless:

- `detect_temp_ui_kind`/`parse_open_markdown`: an `OpenMarkdown ./x.md`
  file detects as `"open_markdown"` and parses to `"./x.md"`; a path
  containing spaces round-trips correctly; existing `Question`/
  `LightningRound` detection is unchanged (regression check).
- `_resolve_open_markdown_target`: a relative path resolves against
  the passed `directory`; an absolute path passes through unchanged.
- Real production path: a temp Desk directory, a real `DeskWindow`
  substitute via the same `PythonWidgetHost`-level approach used for
  `markdown_ex`/`project_files`/`svg_viewer`'s own verification
  (literal `DeskWindow` construction hits the pre-existing, unrelated
  offscreen stall noted in those plans) — instead, directly exercise
  `_bind_temp_ui_content` logic against a real `MarkdownExWidget`
  instance and a real temp `OpenMarkdown` tempui file, confirming
  `set_file` gets called with the correctly-resolved target and the
  file actually renders. Also confirm a `Question`/`LightningRound`
  file through the same helper still calls `set_source_file` as
  before (no regression).
- `_temp_ui_widget_id_for`/`_notify_temp_ui` preview text: an
  `OpenMarkdown` file routes to `"markdown_ex"` and previews as
  `"Open <path>"`.
- Manually-placed-`markdown_ex`-survives-restore-as-before check: a
  non-tempui instance_id passed through `_bind_temp_ui_content` is a
  safe no-op (no exception, `set_file` never called).

## Status

**Completed.** Implemented and verified headlessly as described above:

- `detect_temp_ui_kind`/`parse_open_markdown`: correct detection and
  parsing for `OpenMarkdown`, including a path containing spaces;
  `Question`/`LightningRound` detection unchanged (regression check).
- `_resolve_open_markdown_target`: a relative path resolves against
  the passed directory; an absolute path passes through unchanged
  (verified without the misleading `.resolve()` comparison a macOS
  `tempfile.mkdtemp()` symlink would otherwise cause — compared
  against the literal expected `Path`, not a resolved one).
- `_bind_temp_ui_content` against real widget instances (not mocks):
  a real `MarkdownExWidget` gets `set_file`'d with the correctly
  -resolved target and renders it; a real `Question` widget still gets
  `set_source_file` and genuinely re-renders its question text
  (checked before/after, not just "didn't raise") — confirms the
  shared-helper refactor didn't regress the existing types; a real
  `LightningRound` widget binds without exception; a non-tempui
  `markdown_ex` instance (a `.desk_temp/` path that doesn't exist) is
  a safe no-op, matching its pre-existing "starts blank on reload"
  behavior.
- `_temp_ui_widget_id_for` routes an `OpenMarkdown` file to
  `"markdown_ex"`; `_notify_temp_ui`'s preview text is `"Open
  <path>"`.
- `design-docs/architecture.md`'s Markdown (Extended) Widget entry
  updated; the local, gitignored `.desk_temp/desk-temporary-ui.md`
  copy hand-refreshed from the updated `DOC_TEMPLATE` so this repo's
  already-provisioned `.desk_temp/` (and the `claude` widget reading
  it) picks up the new capability immediately.
- **Skipped**: a literal end-to-end `DeskWindow` + real notification
  -click flow, for the same pre-existing, unrelated offscreen-canvas
  stall noted in `plans/markdown-ex-widget.md`/`plans/file-explorer
  -widget.md`/`plans/svg-viewer-widget.md`. Every piece of the chain
  (`detect_temp_ui_kind` → `_temp_ui_widget_id_for` →
  `_notify_temp_ui` → `_bind_temp_ui_content` → `MarkdownExWidget
  .set_file`) was instead verified directly against real objects.
