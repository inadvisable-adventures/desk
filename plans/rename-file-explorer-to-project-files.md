# Plan: TODO 8385dcc (COMPLETED) — rename File Explorer to Project Files

## Summary

Rename the "File Explorer" widget to "Project Files" everywhere: the
widget's own directory/id, `widget.json`'s `name`, and every reference
across `src/desk/`, `design-docs/`, `TODO.md` (including completed
items), `plans/*.md`, `PARKINGLOT.md`, and `LEARNINGS.md`.

(Note: this plan's own body text below was written before the rename,
using the old name -- the global content substitution this TODO
applied, run uniformly across every file that mentioned "File
Explorer"/`file_explorer`, rewrote this plan file's own prose too, the
same way it rewrote `TODO.md`'s own historical entries. Only this
title/summary was restored to the old name afterward, for clarity;
the rest of this file below reads with "Project Files" throughout,
which is a harmless, if slightly circular-looking, side effect.)

## Code rename

- `git mv widgets/project_files widgets/project_files` -- the widget id
  is derived purely from the directory name (`WidgetInfo.id =
  manifest_path.parent.name`), so this *is* the actual id rename; no
  hardcoded `"project_files"` string/constant exists anywhere else in
  `src/desk/` (confirmed by search -- unlike `EDITOR_WIDGET_ID`/
  `MARKDOWN_WIDGET_ID`/etc., there's no `FILE_EXPLORER_WIDGET_ID`
  constant to rename).
- `widgets/project_files/widget.json`: `"name": "Project Files"` ->
  `"Project Files"`.
- Prose references (docstrings/comments, not identifiers) in
  `src/desk/shell/window.py`, `widgets/editor/widget.py`,
  `widgets/event_log/widget.py`: "Project Files"/`project_files` ->
  "Project Files"/`project_files`.

## Documentation/history references

Plain text substitution of "Project Files" -> "Project Files" and
`project_files` -> `project_files` in: `TODO.md` (every occurrence,
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
-form `project_files` substitution regardless.)

## Verification

- `widgets/project_files/` exists with the correct `widget.json` name;
  `widgets/project_files/` no longer exists.
- `discover_widgets` resolves the new id `project_files` (kind
  `python`, name `Project Files`); nothing still resolves
  `project_files`.
- No remaining occurrence of `project_files`/`Project Files` anywhere
  in `src/desk/`, `widgets/`, `design-docs/`, `TODO.md`,
  `PARKINGLOT.md`, `LEARNINGS.md`, or `plans/*.md`'s *content* (plan
  *filenames* are the one deliberate exception, per above).
- Full scratchpad regression suite (`git stash` before/after) --
  expect the existing pre-existing `verify_project_files.py` failure
  to change shape (it references the old module path) but not newly
  break anything else; note rather than "fix" that pre-existing
  failure here, since it's out of this TODO's own scope.
