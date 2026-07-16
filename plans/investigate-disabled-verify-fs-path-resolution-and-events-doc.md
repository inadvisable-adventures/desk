# Plan: TODO 9b89129 (COMPLETED) — investigate `disabled_verify_fs_path_resolution_and_events_doc.py`

## Investigation

Same category as TODO `06fa070`/`fea158d`: the only failure is a
hardcoded `TEMPUI_DOC_VERSION == 13` assertion; every other check
passes.

## Resolution

Loosen to `>= 13` and re-enable.

## Verification

Re-run standalone (passes); full `tests/verify/` suite: disabled count
drops to 9, 0 new failures.
