# Plan: TODO 69ebfb0 (COMPLETED) — investigate `disabled_verify_build_widget_doc_and_seed.py`

## Investigation

Every check in this script covers a design superseded twice over:

- The doc-content assertions (`custom_widget_src/<name>/`,
  `scripts/build_widget.py` mentions, stale `TEMPUI_DOC_VERSION == 11`)
  test the *pre*-TODO-`59c5a70` "Authoring from real source" doc text.
  Confirmed directly: the current `_CUSTOM_WIDGETS_DOC` content
  contains neither string at all anymore (it now describes
  `.desk_temp/widgets/<name>/` and `.desk_temp/build_widget.py`) — these
  aren't just an outdated version number, they assert content that is
  now actively wrong.
- The seeding tests (`_FakeWindow._seed_build_widget_script =
  DeskWindow._seed_build_widget_script`) test a method TODO `029047b`
  removed entirely, superseded by the ensure mechanism (TODO
  `e57ce5f`).

## Resolution

Delete outright — nothing here reflects current or even semi-current
behavior, and the ensure-mechanism's own coverage (already exercised by
`tests/verify/verify_ensure_build_widget_script.py`) is the correct
replacement, not a patch-forward of this file.

## Verification

Full `tests/verify/` suite: disabled count drops to 14, 0 new failures
among the enabled ones (this script contributes nothing further to run).
