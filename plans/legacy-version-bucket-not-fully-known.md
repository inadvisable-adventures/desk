# TODO `ee1a474`: a legacy project's own version bucket must not be assumed fully known

## Bug

`desk.temp_ui._legacy_version_tags(version)` (TODO `6839365`) migrates a
pre-tags project's single old `TEMPUI_DOC_VERSION`-era integer into the
new tag scheme. As shipped, it treated a project at version `N` as
already having *every* decade bucket up through and including its own
bucket (`(N // 10) * 10`) -- e.g. version 44 -> `{version-00, version-10,
version-20, version-30, version-40}`.

That's wrong for the project's own (highest) bucket specifically: a
bucket covers ten version numbers (`version-40` covers 40-49, though only
40-46 actually exist), and a project at version 42 has *not* necessarily
seen whatever changed at versions 43-46 -- being "in" `version-40`'s
range doesn't mean being at its *top*. This is worse than an ordinary
off-by-one because the old version numbers weren't even reliably unique:
this is exactly the TODO `6839365` root cause (two branches independently
bumped to the same number, `43 -> 44`, on different content) -- so two
real projects both reporting "version 44" may not have seen the same
changes at all. A project's own bucket can never be trusted as fully
known, regardless of which specific number inside it the project reports.

Reported directly: many real projects are on old version numbers in the
40s; opening the latest Desk only surfaced the new "tagged changelog..."
tag as missing, not `version-40` itself, even though those projects have
no reliable claim to everything bucketed into `version-40`.

## Fix

`_legacy_version_tags(version)` returns every bucket *strictly below* the
project's own bucket only (`range(0, bucket, 10)`, not `range(0, bucket +
1, 10)`) -- the project's own bucket is always reported missing, so
`ensure_docs_current` always surfaces it (and its real
`_BREAKING_CHANGES`/`_NEW_FEATURES` content) as part of the doc-upgrade
notification the first time such a project is opened under a tag-aware
Desk. No new tag is needed -- this is a pure bucket-membership fix, not a
new fact `CURRENT_TAGS` needs to represent (nothing in
`plans/tempui-doc-tags.md` or `design-docs/architecture.md` promised
that a legacy project's own bucket would ever be treated as already
known; that was purely an implementation bug in `_legacy_version_tags`).

Once a project is opened under the new scheme, its doc is rewritten with
the real, full tag-comment set (every entry in `CURRENT_TAGS`), so this
migration path only ever runs once per project -- from then on staleness
is checked against its own real, granular tag comments, not re-derived
from a stale integer.

## Affected files

- `src/desk/temp_ui.py`: `_legacy_version_tags`'s own range bound, and its
  docstring (currently claims the opposite of the fixed behavior).
- `tests/verify/verify_tempui_doc_versioning.py`:
  `test_legacy_version_tags_cumulative_buckets` asserted the old (buggy)
  values -- rewritten for the corrected ones, retitled.
- `tests/verify/verify_tempui_storage_claim_fix.py`: its
  `test_ensure_docs_current_still_works_with_new_version` simulation
  computed its expected `missing_tags` from the old (buggy) bucket
  -inclusive semantics.
- `design-docs/architecture.md`: the tag-scheme paragraph's one-line
  mention of the legacy migration is still accurate as written ("a doc
  that predates tag-tracking entirely migrates via a one-time bulk
  mapping") and needs no change, but double-check the surrounding prose
  doesn't otherwise imply bucket-inclusive semantics.

## Verification

Full `tests/verify/` regression suite (non-`disabled_`) still passes
after the fix.
