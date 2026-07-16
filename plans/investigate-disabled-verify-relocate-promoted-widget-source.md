# Plan: TODO ba0bd9a (COMPLETED) — investigate `disabled_verify_relocate_promoted_widget_source.py`

## Investigation

Only one of this script's 5 test functions is actually stale:
`test_build_widget_script_docstring_updated` reads `scripts/
build_widget.py` directly, deleted by TODO `029047b`. The other 4
(source-directory-moved-on-promotion, no-source-no-op, pre-existing
-destination-not-clobbered, doc-content) exercise
`_relocate_promoted_widget_source`/`CUSTOM_WIDGET_SRC_DIRNAME`
directly — unrelated to the build-widget-script relocation, still
fully current (confirmed `CUSTOM_WIDGET_SRC_DIRNAME = "widgets"` is
still the real current value).

## Resolution

Fix just the one stale function: check the in-memory generated content
(`SPLIT_DOC_CONTENT[BUILD_WIDGET_SCRIPT_FILENAME]`) instead of reading
`scripts/build_widget.py` from disk.

## Verification

Re-run standalone (passes, all checks); full `tests/verify/` suite:
disabled count drops to 4, 0 new failures.
