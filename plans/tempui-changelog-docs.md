# Plan: TODO 7462cdb (COMPLETED) — tempui-breaking-changes.md / tempui-new-features.md

See `../../FEEDBACK/FEEDBACK-DESK-tempui-doc-changelog-2026-07-15-1315.md`
for the full source feedback and rationale.

## Summary

`TEMPUI_DOC_VERSION` already tells a reading agent *that* the tempui doc
set changed since whatever version its project was built against, but
not *what* -- forcing a full re-read and a manual diff against memory
(impossible for a fresh agent with no memory of an earlier read) to
answer "what do I need to fix." Add two more files to the same
generated/versioned `.desk_temp` set, each a reverse-chronological
changelog tagged by the version it was introduced in.

## New constants/content (`src/desk/temp_ui.py`)

- `BREAKING_CHANGES_DOC_FILENAME = "tempui-breaking-changes.md"`
- `NEW_FEATURES_DOC_FILENAME = "tempui-new-features.md"`
- `_BREAKING_CHANGES_DOC`/`_NEW_FEATURES_DOC` string constants, added to
  `SPLIT_DOC_CONTENT` (no separate version of their own -- refreshed for
  free by the existing `ensure_docs_current` staleness check, per TODO
  `e57ce5f`'s "one shared version number for the whole set").

## Backfilling real history

Reconstruct entries from this project's own actual `TEMPUI_DOC_VERSION`
bump comments in `temp_ui.py` (every bump already has a "TODO xxx:
bumped N -> N+1 for ..." comment) -- more reliable than the feedback
doc's own illustrative reconstruction, which was written against this
project's version 13 and predates the version 14 change made earlier in
this same work session. Only bumps 7 through 14 have per-bump comments
recorded (versions 1-6 predate this practice) -- the changelog starts at
7, with a one-line note that earlier versions aren't individually
recorded.

Classification (breaking vs. new, by bump):
- v7: new "Sending and receiving named messages" section (events
  capability) -- **New**.
- v8: new `Capability` DefineWidget DSL line -- **New**.
- v9: new "Inspecting another widget" section (introspect capability)
  -- **New**.
- v10: new `OpenImage` keyword -- **New**.
- v11: new "Authoring from real source" section (`custom_widget_src/
  <name>/` + `scripts/build_widget.py`) -- **New** (additive, nothing
  existing broke).
- v12: `DefineWidget` no-instance-placed callout + auto-place-first
  -instance behavior -- **New**.
- v13: `getManifest`'s new `content_hash`/`directory` fields, `fs`'s
  relative-path resolution fix (previously effectively broken for a
  relative path; absolute paths unaffected) -- **New**.
- v14: authoring source location moved `custom_widget_src/<name>/` ->
  `.desk_temp/widgets/<name>/`, promotion now also moves the source
  directory to `desk_widgets/<name>/` -- **Breaking** (an existing
  `custom_widget_src/<name>/` needs to move).

## Doc intro

`DOC_TEMPLATE`'s "eight built-in file types" list is specifically the
DSL-keyword-triggered file types -- these two new files aren't one (no
keyword triggers them, they're reference docs) -- so add a short
paragraph *after* that list (not as a ninth bullet in it) pointing to
both and explaining their purpose: check them after being relaunched
under an updated Desk to see exactly what changed since the version you
last read.

## Going-forward convention

Add a short instruction alongside `TEMPUI_DOC_VERSION`'s existing bump
-log comments: whenever a future bump reflects a breaking change or a
new capability, add a corresponding entry to whichever of these two docs
applies, in the same commit as the bump. (TODO `1a96c9f` formalizes this
same instruction in `development-process.md` itself, for anyone working
on Desk who might not otherwise think to look at this code comment.)

## Verification

- Both filenames present in `SPLIT_DOC_CONTENT`; `write_tempui_docs`
  writes both into a fresh `.desk_temp`.
- Content: entries appear newest-first, cover versions 7-14 (the
  documented range) with the classifications above, and the doc states
  plainly that versions 1-6 predate individual tracking.
- `TEMPUI_DOC_VERSION` bumped, with the bump comment referencing this
  TODO the same way every other bump comment does.
- `DOC_TEMPLATE` links both new docs after (not inside) the built-in
  -file-types list.
- Full scratchpad regression suite (`git stash` before/after).
