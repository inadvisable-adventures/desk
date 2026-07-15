# Plan: TODO 59c5a70 — relocate DefineWidget authoring source

## Summary

TODO b324217 recommended authoring a `DefineWidget` widget's source at a
project-root `custom_widget_src/<name>/` directory. Change that
recommendation to `.desk_temp/widgets/<name>/` (already-established,
gitignored Desk-support territory, rather than a second project-root
convention), and make the `[TEMPUI]` promote button move a promoted
widget's source out of there into a permanent, non-gitignored
`desk_widgets/<name>/` project subdirectory -- promotion already means
"this is now a permanent part of my project," so its source shouldn't
keep living in the disposable `.desk_temp` tree either, not just its
definition in the `.desk` file.

## New constants (`src/desk/temp_ui.py`, alongside `TEMP_UI_DIRNAME`)

```python
CUSTOM_WIDGET_SRC_DIRNAME = "widgets"  # under .desk_temp/, pre-promotion
PROMOTED_WIDGET_SRC_DIRNAME = "desk_widgets"  # project root, post-promotion
```

## `scripts/build_widget.py`

No functional change needed -- it already takes an arbitrary directory
as its argument (never hardcodes `custom_widget_src`), so it already
works unchanged for a source directory at either
`.desk_temp/widgets/<name>/` or `desk_widgets/<name>/`. Just update its
own module docstring's usage example (currently cites
`custom_widget_src/<name>`) to the new recommended pre-promotion
location, and mention the post-promotion one.

## Docs (`_CUSTOM_WIDGETS_DOC`'s "Authoring from real source" section)

- Change the recommended directory from `custom_widget_src/<name>/` to
  `.desk_temp/widgets/<name>/`, with the same "not under `widgets/`"
  reasoning as before (still applies -- `discover_widgets` would still
  choke on this manifest shape).
- Add a paragraph: once promoted via the `[TEMPUI]` button, the source
  directory moves to `desk_widgets/<name>/` at the project root (a
  permanent, non-gitignored location, matching the promoted
  definition's own move into the `.desk` file) -- re-run
  `python3 scripts/build_widget.py desk_widgets/<name>` from there for
  any further edits; nothing else about the build process changes.
- Bump `TEMPUI_DOC_VERSION` by 1.

## Promote flow (`DeskWindow._on_tempui_promote_requested`)

After the existing removal of the `.desk_temp/<uuid>` invocation file:
check whether `self.current_desk.directory / TEMP_UI_DIRNAME /
CUSTOM_WIDGET_SRC_DIRNAME / keyword` exists as a directory. If so, move
it (`shutil.move`) to `self.current_desk.directory /
PROMOTED_WIDGET_SRC_DIRNAME / keyword` (creating the destination's
parent directory as needed). If a source directory doesn't exist at that
path (e.g. the widget was hand-authored inline, no separate source dir
ever existed), this is a silent no-op -- not every custom widget has an
authoring source directory to move. If the destination already exists
(an unexpected name collision), leave the source in place and log a
warning rather than clobbering or raising -- the `.desk` file promotion
above has already succeeded by this point, and a problem with this
secondary bookkeeping step shouldn't be allowed to look like the whole
promotion failed.

## Verification

- `build_widget.py`'s own build behavior is unaffected -- confirm with
  a quick end-to-end run against a fixture at
  `.desk_temp/widgets/<name>/` (real `tsc`) and again from
  `desk_widgets/<name>/`, same output either way.
- Doc: the new recommended directory, the promotion-time move
  explanation, and the version bump.
- Promote flow: a source directory at `.desk_temp/widgets/<keyword>/`
  moves to `desk_widgets/<keyword>/` on promotion (files present,
  original location gone); promoting a widget with no such source
  directory is an unchanged no-op-for-this-part; promoting into an
  already-existing `desk_widgets/<keyword>/` leaves the source where it
  was (logged, not raised) without affecting the rest of the promote
  flow (the `.desk` file save/button-hide/spawn-menu-catalog-refresh
  still happen).
- Full scratchpad regression suite (`git stash` before/after).
