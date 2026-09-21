# tempui-custom-widgets.md: subjective-visual-judgment callout (TODO e501d8a) (COMPLETED)

## Summary

Add a callout to `tempui-custom-widgets.md` (the `_CUSTOM_WIDGETS_DOC`
string in `src/desk/temp_ui.py`) naming a task whose correct answer
depends on a human's subjective visual judgment -- cropping/selecting a
region in an image, confirming a placement/composite/layout looks right,
disambiguating what a fixed heuristic cannot isolate -- as a signal to
propose a small, disposable `DefineWidget` for the user to *show* the
answer, even when the request did not ask for one. It composes with
automation: a cheap heuristic can seed a default, the widget only
*selects* (e.g. writes confirmed rects to a JSON file), and an ordinary
script does the actual work. Cites
`../FEEDBACK/FEEDBACK-DESK-tempui-widget-for-subjective-visual-tasks-2026-08-27-1220.md`.

## Affected files

- `src/desk/temp_ui.py` -- the callout in `_CUSTOM_WIDGETS_DOC`; a new tag
  in `CURRENT_TAGS`; a matching `_NEW_FEATURES` entry (guidance changes
  count as features, per the user).
- `tests/verify/verify_tempui_subjective_visual_callout.py` -- new.

## Approach

1. Place the callout in the doc's intro, right after the paragraph saying
   a `DefineWidget` file only registers the kind, before the line-format
   list.
2. Mint a tag with `desk.temp_ui.generate_tag`, append it to
   `CURRENT_TAGS`, add the `_NEW_FEATURES` entry in the same commit.
3. Doc text only; no DSL/Bridge behavior change.

## Verification

New verify script: the rendered custom-widgets doc contains the callout's
key phrases (subjective visual judgment, proposing a widget unprompted,
heuristic default, widget only selects); the new tag is in
`CURRENT_TAGS` and has a `_NEW_FEATURES` entry that renders into
`tempui-new-features.md`. Re-run the existing tempui changelog verify
scripts. No browser launch needed.

## Status

Implemented as planned. Tag `widget for subjective visual tasks guidance
#588265` added to `CURRENT_TAGS` with a `_NEW_FEATURES` entry. The callout
also says to propose the widget first rather than silently building it.
New verify script passes, as do all existing `verify_tempui_*` scripts,
`verify_hmsvc.py` and `verify_pipeline_dsl_split_channels.py`. Browser
launch not needed.
