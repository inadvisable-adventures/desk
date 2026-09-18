# TODO `6839365`: replace TEMPUI_DOC_VERSION with a tag-based changelog

## Summary

Replace the tempui doc set's single, manually-bumped `TEMPUI_DOC_VERSION`
integer with **tags**: a tag is a short (10-50 character) human-written
summary plus an appended 6-digit, non-semantic hash generated from its
creation timestamp (`desk.temp_ui.generate_tag`). A `.desk_temp` project
records which tags it has seen (not a single version number); Desk's own
`CURRENT_TAGS` is the full set a fully up-to-date project has. Tags can
later be collapsed (several old tags folded into one new tag, to keep the
changelog's footprint bounded) via `TAG_COLLAPSES`.

This fixes two real problems found while investigating the request:

1. The ~280-line manually-maintained bump-log comment above the old
   `TEMPUI_DOC_VERSION = 46` (`src/desk/temp_ui.py:64-340`) is redundant
   with `_BREAKING_CHANGES_DOC`/`_NEW_FEATURES_DOC` just below it, and had
   already gone stale: it stops documenting at version 44, two versions
   behind the real `46`. Root cause: two branches (TODO `63bfd42`, pipe
   -chained verb DSL, and TODO `4eb3d9e`, promoted-widget staleness) each
   independently bumped `43 -> 44` from the same base; the merge
   (`9caf3c6`) silently renumbered one side to 45/46 (the changelog docs'
   own content ended up correctly renumbered, but the hand-written comment
   log and `TODO.md`'s own "bumped to 44/45" prose did not, and never can
   be reconciled automatically). A single global counter can't survive two
   concurrent workstreams without this kind of collision; a hash-suffixed
   tag can, by construction.
2. `TempUiManager._notify_docs_upgraded` writes a static Scratch note
   ("refreshed from version X to Y, see tempui-breaking-changes.md
   yourself") -- clicking it just shows that fixed text, never the actual
   new content. (The user described this as "pops up multiple
   notifications, one per version, each showing the full range" -- that
   exact loop was not found in the current code; `provision` calls
   `_notify_docs_upgraded` at most once, per `verify_tempui_doc_upgrade_
   notification.py:127`'s own regression check. Building to the requested
   spec -- one-or-zero notifications, single call site, no loop -- anyway,
   plus the genuinely-missing feature: clicking now opens a widget that
   shows the real descriptions of exactly the tags that are new.)

## Design

### `src/desk/temp_ui.py`

- Delete the old bump-log comment block and `TEMPUI_DOC_VERSION`/
  `_DOC_VERSION_PLACEHOLDER`/`_DOC_VERSION_RE`. Replace with:
  - `Tag` (frozen dataclass: `summary: str`, `hash: str = ""`, `id`
    property -- `f"{summary} #{hash}"` if `hash` else bare `summary`).
  - `generate_tag(summary, *, now=None) -> Tag` -- validates 10-50 chars,
    derives the 6-digit hash from `now` (defaults to `time.time()`).
  - `_legacy_version_tags(version: int) -> frozenset[str]` -- migration
    helper, see below.
  - `TAG_COLLAPSES: dict[str, str]` (old id -> new id; empty for now) and
    `_canonicalize_tags(tags) -> frozenset[str]` (chained lookup through
    `TAG_COLLAPSES`, so a project that already has every tag that was
    later collapsed into a new one is recognized as already having the
    new one).
  - `CURRENT_TAGS: tuple[str, ...]` -- every tag a from-scratch project
    gets, replacing `TEMPUI_DOC_VERSION`'s role as "the current baseline."
- `DOC_TEMPLATE`: replace the single `<!-- desk-temporary-ui.md version: N
  -->` comment with one `<!-- desk-temporary-ui.md tag: <id> -->` comment
  per entry in `CURRENT_TAGS` (a `{{TEMPUI_DOC_TAGS}}` placeholder,
  substituted in `render_static_doc`). Update the nearby prose ("read from
  the top down until you reach a version you already know" etc.) to talk
  about tags. Update the ~9 identical `"...shared version number -- this
  file just covers the \`X\` keyword."` lines in the split docs' own
  intros to `"...shared set of tags..."`.
- `_BREAKING_CHANGES_DOC`/`_NEW_FEATURES_DOC` (the two files actually
  written to `.desk_temp/`) become **generated** from two new dicts,
  `_BREAKING_CHANGES: dict[str, str]` and `_NEW_FEATURES: dict[str, str]`
  (tag id -> markdown body, no leading heading), via a small
  `_render_changelog_doc(title, entries, intro) -> str` that emits one
  `## <tag id>` section per entry, newest-first (per `CURRENT_TAGS`
  order). This makes the "what changed for exactly these tags" excerpt
  used by the upgrade notification (below) reachable without re-parsing
  Markdown headings.
- One-time migration of the old changelog content into the two dicts:
  bucket every old integer version into a decade tag (`version-00` =
  versions 1-9, `version-10` = 10-19, ... `version-40` = 40-46 -- this is
  exactly the "duplicate/out-of-order 44" the user flagged: both
  concurrent 43->44 bumps, plus 45/46, all land in the same `version-40`
  bucket regardless), preserving every original bullet verbatim under a
  nested `### Version N` sub-heading (no rewriting/summarizing -- least
  risk of silently dropping something). Generated programmatically from
  the live `_BREAKING_CHANGES_DOC`/`_NEW_FEATURES_DOC` constants (not
  hand-retyped) to avoid transcription errors.
- New tag for this change itself: `generate_tag("tagged changelog, no
  version numbers")`, added to `CURRENT_TAGS`, with a `_NEW_FEATURES`
  entry describing the new mechanism (this plan's own summary, condensed).
- `parse_doc_version` -> `parse_doc_tags(text) -> set[str] | None`:
  - Real `<!-- ... tag: ... -->` comments present -> that set.
  - None of those, but the old `<!-- ... version: N -->` comment is
    present -> `_legacy_version_tags(N)` (migration path).
  - Neither -> `None` (predates tracking entirely; always stale, but see
    below -- matches old "no version note" behavior of not notifying).
- `ensure_docs_current(temp_dir) -> tuple[bool, frozenset[str]]` (was
  `tuple[bool, int | None]`): rewrite is triggered when the canonicalized
  known-tag set doesn't cover `CURRENT_TAGS`, or a split file is missing
  (unchanged reasoning). Second element is the *missing* tags (`CURRENT_TAGS
  - canonicalize(known)`), empty when nothing is missing, and also empty
  when `known_tags is None` (a file that predates tag-tracking entirely --
  preserves the old "silently top up, don't notify" behavior for that
  case; there's nothing meaningful to diff against).
- `write_tempui_docs` unchanged in shape (still writes the main doc +
  every `SPLIT_DOC_CONTENT` file); `render_static_doc` now fills in the
  tag-comment block instead of a version number.

### `src/desk/shell/temp_ui_manager.py`

- `provision`: `previous_version` -> `missing_tags: frozenset[str]`;
  notify iff `missing_tags` is non-empty (still exactly one call site, no
  loop -- satisfies "only one or zero notifications" directly).
- `_notify_docs_upgraded(temp_dir, missing_tags)`: build the notification
  body from `desk.temp_ui.render_new_tags_digest(missing_tags)` (new
  function: for each missing tag, newest-first, emit its
  `_BREAKING_CHANGES`/`_NEW_FEATURES` entries if present) and write it as
  a **Markdown** tempui note (`_write_markdown_note`, a new sibling of the
  existing `_write_scratch_note` sharing a `_write_note(keyword, ...)`
  helper) instead of a Scratch note -- clicking a Markdown note already
  renders real Markdown content in a Markdown widget (existing, generic
  path; `window.py`'s `_activate_temp_ui`/`detect_temp_ui_kind` need no
  changes), which is what makes this "a widget to actually read the
  descriptions of the new tags" rather than a pointer to a file.

### Migration semantics for an existing project

A project whose `.desk_temp` doc only has the old `version: N` comment
gets `_legacy_version_tags(N)` = every decade bucket up through `N`'s own
bucket (versions were always cumulative, so version 25 already implies
`version-00`/`version-10`/`version-20`, not just `version-20` alone).
`ensure_docs_current` then reports whatever's missing beyond that
(certainly the new "tagged changelog..." tag, plus any bucket above its
own) as a real, single notification -- this is the intended first-open
experience under the new scheme, not a bug.

### `design-docs/architecture.md`

The "`desk-temporary-ui.md` itself is version-stamped..." paragraph
(currently lines ~812-827) gets rewritten for the tag scheme, and its
existing stale reference to a function called `ensure_doc_version_current`
(real name: `ensure_docs_current`) gets fixed. Add a short note describing
the doc-upgrade notification (`_notify_docs_upgraded`) and its click
-through Markdown widget, since that feature currently isn't mentioned in
`design-docs/` at all (only in `plans/tempui-doc-upgrade-notification.md`).

### Tests

- `tests/verify/verify_tempui_doc_versioning.py` -> rewritten in place
  (kept filename, since it still covers `render_static_doc`/
  `write_tempui_docs`/`ensure_docs_current`, just against the tag API) to
  exercise `parse_doc_tags`, `generate_tag` validation, `_legacy_version_
  tags` bucketing, `_canonicalize_tags`/`TAG_COLLAPSES` chaining, and
  `ensure_docs_current`'s missing-tags return.
- `tests/verify/verify_tempui_doc_upgrade_notification.py` -> updated for
  `missing_tags`/`render_new_tags_digest`/the Markdown-note write path
  (was Scratch); keeps its existing "exactly one file_added" assertion.
- `tests/verify/verify_tempui_changelog_docs.py` -> updated for the dict
  -based `_BREAKING_CHANGES`/`_NEW_FEATURES` + generated doc strings.
- `tests/verify/verify_tempui_storage_claim_fix.py`,
  `verify_html_widget_local_storage.py` -> their incidental `parse_doc_
  version`/`TEMPUI_DOC_VERSION` sanity-checks swapped for the tag
  equivalents.
- `tests/verify/verify_ensure_build_widget_script.py` -- its stale-doc
  simulation (`.replace(f"version: {TEMPUI_DOC_VERSION}", "version: 1")`)
  rewritten to instead strip the tag-comment block entirely (simulating a
  doc that's missing tags), so it still actually exercises the rebuild
  -on-stale path.
- The ~20 other `tests/verify/*.py` files whose only connection to this is
  a per-feature `check("TEMPUI_DOC_VERSION bumped to at least N", ...)`
  regression tripwire: each becomes `check("<feature> is covered by its
  version-XX changelog tag", "version-XX" in CURRENT_TAGS)` where XX is
  that N's own decade bucket -- same "don't silently lose this feature's
  changelog entry" intent, expressed in terms that still exist.

### `development-process.md`

"Keep the tempui changelog docs current" already names
`_BREAKING_CHANGES_DOC`/`_NEW_FEATURES_DOC` by their rendered-file role,
which is unchanged; light wording pass only (mention minting a tag via
`generate_tag` instead of "bump the version").

## Explicitly out of scope

- Actually performing a *collapse* (`TAG_COLLAPSES` stays empty besides
  being exercised in tests) -- the mechanism is built and documented, but
  there's nothing to collapse yet the same day it ships.
- A dedicated new widget kind for the upgrade notification -- reusing the
  existing generic Markdown tempui kind is sufficient and matches how
  Scratch notes already work.
