# Plan: TODO 029047b — move build_widget.py into the ensured `.desk_temp` set

## Summary

`scripts/build_widget.py` (TODO b324217) is currently copied once into
a new project (`DeskWindow._seed_build_widget_script`, never
-overwrite) the same way `scripts/todo_item_ids.py` is -- but unlike a
hand-written id-generation script that basically never changes,
`build_widget.py`'s own content changes exactly as often as the rest of
the tempui doc set does. A one-time seed means an older project's copy
silently goes stale forever. Move its content into the same generated
-and-refreshed `.desk_temp` mechanism (`SPLIT_DOC_CONTENT`,
`write_tempui_docs`/`ensure_docs_current`, TODO e57ce5f) the docs
themselves already use, instead of a static file copied once.

## `src/desk/temp_ui.py`

- `BUILD_WIDGET_SCRIPT_FILENAME = "build_widget.py"`.
- `_BUILD_WIDGET_SCRIPT` -- the script's current content, moved here
  verbatim except: its own module docstring's "seeded into new
  projects... the same way scripts/todo_item_ids.py already is" claim
  no longer applies (nothing seeds it anymore) -- update it to
  describe living in `.desk_temp`, refreshed the same way the tempui
  docs are, and its usage examples updated from `scripts/
  build_widget.py` to `.desk_temp/build_widget.py`.
- Add `BUILD_WIDGET_SCRIPT_FILENAME: _BUILD_WIDGET_SCRIPT` to
  `SPLIT_DOC_CONTENT` -- `write_tempui_docs`/`ensure_docs_current`
  already treat every entry generically (`.write_text(content)`, no
  markdown-specific handling), so this needs no special-casing.
- `_CUSTOM_WIDGETS_DOC`'s "Authoring from real source" section: update
  every `scripts/build_widget.py` invocation example to
  `.desk_temp/build_widget.py`.
- Bump `TEMPUI_DOC_VERSION`, with a `tempui-breaking-changes.md` entry
  (the invocation path changes for anyone with an existing seeded
  copy) per TODO 1a96c9f's now-standing instruction.

## `src/desk/shell/window.py`

Remove `_seed_build_widget_script` and its call site in
`_create_new_desk` (alongside `_seed_todo_item_ids_script`) --
superseded entirely by the ensure mechanism, which already runs on
every Desk open/switch via `TempUiManager.provision`/
`ensure_docs_current`.

## `scripts/build_widget.py`

Delete the file (`git rm`) -- its content now lives in
`src/desk/temp_ui.py`, not a standalone script copied around.

## `design-docs/custom-widget-authoring.md`

Section 1 ("A repeatable authoring pattern") is stale in two ways
predating this TODO -- it still describes the *original*
`custom_widget_src/<name>/` convention (superseded by TODO 59c5a70's
`.desk_temp/widgets/<name>/`) and the scripts/-seeding approach this
TODO removes. Rewrite it to describe the current state end-to-end:
source lives at `.desk_temp/widgets/<name>/` pre-promotion and
`desk_widgets/<name>/` post-promotion (TODO 59c5a70), and the build
script lives at `.desk_temp/build_widget.py`, refreshed automatically
alongside the tempui doc set rather than seeded once (this TODO).

## Verification

- `SPLIT_DOC_CONTENT` includes the script; `write_tempui_docs` writes
  it into a fresh `.desk_temp` with the exact expected content, and
  the written script actually runs correctly end-to-end (real `tsc`
  invocation against a fixture, same check TODO b324217's own
  verification used) from its new `.desk_temp/build_widget.py`
  location.
- `ensure_docs_current` refreshes a stale/missing copy the same way it
  already does for the `.md` docs.
- `scripts/build_widget.py` no longer exists;
  `_seed_build_widget_script` no longer exists.
- Doc content: the "Authoring from real source" section's invocation
  examples point at the new location; version bump; breaking-changes
  entry present.
- Full scratchpad regression suite (`git stash` before/after) -- the
  TODO b324217 seeding-behavior test (`verify_build_widget_doc_and
  _seed.py`) will need updating/retiring, since the seeding mechanism
  it tests no longer exists.
