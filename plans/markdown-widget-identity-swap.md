# Swap markdown widget identities: markdown -> markdown_old_basic, markdown_ex -> markdown

TODO `96013cf` and `858752b`.

## Summary

Two originally-conflicting rename requests (both said "rename to
`markdown_old_basic`" -- see `QUESTIONS.md`), resolved by the user:

> markdown should become markdown_old_basic and markdown_ex should
> become markdown. we're replacing the old markdown widget with the
> new one, but we're keeping the old one around as deprecated.

So: `widgets/markdown/` (the plain viewer, TODO 6bf83a9) is renamed to
`widgets/markdown_old_basic/` and marked deprecated (TODO ed483e2's
grouping); `widgets/markdown_ex/` (TOC/folding/Mermaid, TODO
`markdown-ex-widget.md`) is renamed to `widgets/markdown_ex/` ->
`widgets/markdown/`, becoming the new default "Markdown" widget.
**Order matters**: the plain widget must move out of `widgets/markdown/`
*before* Markdown (Extended) can move into it.

## Key decisions

- **`git mv`, not delete+recreate** -- preserves file history through
  the rename for both directories.
- **Existing saved `.desk` files referencing `widget_id: "markdown"`
  (confirmed one exists in this repo, `meta-desk.desk`) now resolve to
  the new (formerly markdown_ex) widget on next load, not the old one.**
  This is the *intended* effect of "replacing" — matches the user's own
  framing directly, and no per-instance persisted state is lost either
  way (neither widget currently remembers its open file across reload
  regardless -- see `PARKINGLOT.md`'s still-open widget-local-storage
  follow-on). Not treated as a migration to work around.
- **Display names, not just ids, updated to stay distinguishable in the
  UI** (both id *and* `"name"` change): the old widget becomes id
  `markdown_old_basic`, name **"Markdown (Old, Basic)"**,
  `"deprecated": true`. The renamed-from-markdown_ex widget becomes id
  `markdown`, name **"Markdown"** (dropping "(Extended)" now that it's
  simply *the* markdown widget, not an alternate one).
- **`window.py`'s `MARKDOWN_EX_WIDGET_ID` constant renamed to
  `MARKDOWN_WIDGET_ID`, value `"markdown_ex"` -> `"markdown"`** --
  keeping the old constant name pointing at the new id would be
  actively misleading. Its one real usage (`_temp_ui_widget_id_for`'s
  `open_markdown` -> widget_id mapping) is unaffected in behavior, just
  now correctly named.
- **Historical plan files get a short, timestamped rename note near
  the top, nothing else changed** -- per each TODO's own explicit
  instruction ("add a timestamped note... but don't change the rest of
  the plan"), `plans/markdown-renderer-widget.md` and
  `plans/markdown-ex-widget.md` keep their original content as a
  historical record of what was actually built and why, with a short
  note flagging the later rename.
- **`design-docs/architecture.md`, unlike the historical plans, *is*
  updated for real** (per `development-process.md`: design docs stay
  current, unlike plans, which are historical records) -- its Markdown
  Widget / Markdown (Extended) Widget component entries are rewritten
  to describe the new identities/names/deprecation status directly,
  not just noted.

## Affected files

- `widgets/markdown/` -> `widgets/markdown_old_basic/` (git mv),
  `widget.json` updated (`name`, `deprecated: true`).
- `widgets/markdown_ex/` -> `widgets/markdown/` (git mv), `widget.json`
  updated (`name`).
- `src/desk/shell/window.py` -- `MARKDOWN_EX_WIDGET_ID` ->
  `MARKDOWN_WIDGET_ID`, value updated.
- `plans/markdown-renderer-widget.md`, `plans/markdown-ex-widget.md` --
  timestamped rename notes.
- `design-docs/architecture.md` -- Markdown Widget / Markdown
  (Extended) Widget entries updated for the new identities.

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication`, no mocks):

- `discover_widgets(Path("widgets"))`: `"markdown_old_basic"` exists,
  `deprecated=True`, name `"Markdown (Old, Basic)"`; `"markdown"`
  exists, `deprecated=False`, name `"Markdown"`; `"markdown_ex"` no
  longer exists as an id.
- A real `WidgetSpawnMenu` built from that catalog: `"Markdown (Old,
  Basic)"` appears in the (collapsed-by-default) Deprecated group;
  `"Markdown"` appears in the Active group -- the actual TODO ed483e2
  -built mechanism, exercised end-to-end against a real deprecated
  widget for the first time.
- `_temp_ui_widget_id_for` for a real `OpenMarkdown` tempui file still
  resolves to `MARKDOWN_WIDGET_ID` ("markdown") -- unaffected in
  behavior by the rename.
- Both renamed widgets' `build()` still construct successfully
  (a basic smoke check that the rename didn't break either module's
  own internal imports/assumptions).

## Status

Not yet implemented.
