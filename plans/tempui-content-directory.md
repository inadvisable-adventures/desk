# tempui changelog and doc text move out of `temp_ui.py` (TODO `de16076`) (COMPLETED)

User request (2026-11-19): the `src/desk/temp_ui.py` git merges are tedious (every change touched the same giant
file: a `CURRENT_TAGS` tuple, two changelog dicts and ~20 long text constants). Instead: a directory of json and md
files loaded early at startup, Desk not complete until all are loaded.

## Design

- **Directory** `src/desk/tempui_content/`, read by `desk.tempui_content.load()` when `desk.temp_ui` is imported
  (`_CONTENT = tempui_content.load()`), so nothing can use the doc set before every file is loaded and checked, and a
  malformed file stops startup with a `TempUiContentError` naming it. Synchronous: ~25 small files, no reason for async.
- **`*.json`** -- a JSON array of any number of entries; each has `tag`, `monthstamp` ("MM YYYY") and `description`
  (strict: missing/unknown fields, bad monthstamp, empty strings and a repeated tag of the same kind are errors).
  One addition to the three fields: an **optional** `"breaking": true` puts the entry in the breaking-changes doc
  instead of new-features (needed because a tag can have one of each; two legacy tags do). A new change normally adds
  one new file with one entry (`scripts/new_tempui_changelog_entry.py` mints the tag and writes it); files can be
  regrouped or merged freely later, e.g. for tag collapses.
- **Ordering** (the changelog's newest-first display and `CURRENT_TAGS`): by (monthstamp, file name, position in file).
  New files should be named `YYYY-MM-DD-<slug>.json` so same-month files sort sensibly.
- **Existing entries** split into `2026-09.json` (24 tags, includes the two breaking entries), `2026-10.json` (21),
  `2026-11.json` (26), by the month each tag was first added to `temp_ui.py` (git history). Monotonic in the old
  `CURRENT_TAGS` order, so the derived order is identical.
- **`*.md`** -- the 20 long `_*_DOC` constants, one file each, named exactly as written into a project (e.g.
  `tempui-markdown.md`), content byte-identical. `DOC_TEMPLATE` stays in code (as asked), as do the two build scripts
  (`_BUILD_WIDGET_SCRIPT`, `_BUILD_JOB_OR_DESK_PROC_SCRIPT`: they are `.py` text, not md) -- both possible follow-ups.
  Dotfiles are ignored; any other file type is an error. A `.md` named like a generated file is an error.
- `SPLIT_DOC_CONTENT` = `**_CONTENT.docs` + the two rendered changelog docs + the two scripts. The `*_DOC_FILENAME`
  constants stay (tests use them). `TAG_COLLAPSES` stays in code, empty.
- Tests that imported the `_X_DOC` constants now read `SPLIT_DOC_CONTENT["tempui-x.md"]`.

## Verification

Before editing, the old `CURRENT_TAGS`, both dicts and all 24 `SPLIT_DOC_CONTENT` entries were dumped; after, they
compare **identical** (same tag order, same text). `temp_ui.py` shrank 5973 -> 2104 lines.
`tests/verify/verify_tempui_content_loader.py` (40 checks): the real directory, ordering, every format error, md
byte-exactness, and the helper script. Full verify suite passes.
