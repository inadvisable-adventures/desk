# Plan: TODO 8385dcc — rename File Explorer to Project Files

## Summary

Rename the "File Explorer" widget to "Project Files" everywhere: the
widget's own directory/id, `widget.json`'s `name`, and every reference
across `src/desk/`, `design-docs/`, `TODO.md` (including completed
items), `plans/*.md`, `PARKINGLOT.md`, and `LEARNINGS.md`.

## Code rename

- `git mv widgets/file_explorer widgets/project_files` -- the widget id
  is derived purely from the directory name (`WidgetInfo.id =
  manifest_path.parent.name`), so this *is* the actual id rename; no
  hardcoded `"file_explorer"` string/constant exists anywhere else in
  `src/desk/` (confirmed by search -- unlike `EDITOR_WIDGET_ID`/
  `MARKDOWN_WIDGET_ID`/etc., there's no `FILE_EXPLORER_WIDGET_ID`
  constant to rename).
- `widgets/project_files/widget.json`: `"name": "File Explorer"` ->
  `"Project Files"`.
- Prose references (docstrings/comments, not identifiers) in
  `src/desk/shell/window.py`, `widgets/editor/widget.py`,
  `widgets/event_log/widget.py`: "File Explorer"/`file_explorer` ->
  "Project Files"/`project_files`.

## Documentation/history references

Plain text substitution of "File Explorer" -> "Project Files" and
`file_explorer` -> `project_files` in: `TODO.md` (every occurrence,
completed or open, per the request), `PARKINGLOT.md`, `LEARNINGS.md`,
`design-docs/architecture.md`, and every `plans/*.md` file that
mentions it.

**Plan filenames themselves are not renamed** (e.g.
`plans/file-explorer-widget.md` stays exactly where it is) -- this
project's own convention treats a plan's filename as a stable,
permanent handle once created (the same "generated once, never
recomputed" spirit as a TODO item's own id), and `TODO.md`'s
`[planned: file-explorer-widget.md]`-style references point at that
exact filename. Renaming the files would break those references for no
real benefit; only the *content* inside them changes. (These
hyphenated filenames are also naturally unaffected by the underscore
-form `file_explorer` substitution regardless.)

## Verification

- `widgets/project_files/` exists with the correct `widget.json` name;
  `widgets/file_explorer/` no longer exists.
- `discover_widgets` resolves the new id `project_files` (kind
  `python`, name `Project Files`); nothing still resolves
  `file_explorer`.
- No remaining occurrence of `file_explorer`/`File Explorer` anywhere
  in `src/desk/`, `widgets/`, `design-docs/`, `TODO.md`,
  `PARKINGLOT.md`, `LEARNINGS.md`, or `plans/*.md`'s *content* (plan
  *filenames* are the one deliberate exception, per above).
- Full scratchpad regression suite (`git stash` before/after) --
  expect the existing pre-existing `verify_file_explorer.py` failure
  to change shape (it references the old module path) but not newly
  break anything else; note rather than "fix" that pre-existing
  failure here, since it's out of this TODO's own scope.
