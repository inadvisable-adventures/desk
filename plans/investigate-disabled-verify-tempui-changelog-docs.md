# Plan: TODO 28119c6 (COMPLETED) — investigate `disabled_verify_tempui_changelog_docs.py`

## Investigation

Confirmed: `TEMPUI_DOC_VERSION == 15` and the two exact-list-equality
version-range checks (`features_versions == [14..7]`,
`breaking_versions == [14]`) are all stale — the doc set has grown
through version 17 since TODO `7462cdb` wrote these assertions.

Checked the *actual* current content before choosing a fix: `breaking_
versions == [17, 14]`, `features_versions == [16, 14, 13, 12, 11, 10,
9, 8, 7]` — notably **not** a contiguous 7-through-current range (15
has no features-doc entry at all, since TODO `1a96c9f`'s change wasn't
agent-in-Desk-visible behavior). A "no gaps, contiguous through
current" rewrite would therefore be *wrong*, not just looser — confirms
the plan's own tentative idea needed checking against real data before
assuming it was the right fix.

## Resolution

- Loosen `TEMPUI_DOC_VERSION == 15` to `>= 15`.
- Replace the two exact-list-equality checks with ones that only
  confirm the *original* backfilled content is still present
  (`all(v in features_versions for v in range(7, 15))`, `14 in
  breaking_versions`) — robust to further versions being added later
  without needing hand-updates each time, and correct against the
  real (non-contiguous) shape of this content.

## Verification

Re-run standalone (passes); full `tests/verify/` suite: disabled count
drops to 1, 0 new failures.
