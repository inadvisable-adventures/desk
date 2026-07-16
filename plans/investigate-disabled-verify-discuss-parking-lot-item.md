# Plan: TODO 3c613af (COMPLETED) — investigate `disabled_verify_discuss_parking_lot_item.py`

## Investigation

`parse_discuss_parking_lot_item`'s contract changed twice since this
script was written:

- TODO `624ff3a`: a `DiscussParkingLotItem` temp-ui file's second line
  is now `Line <N>` (a 1-indexed line number into `PARKINGLOT.md`), and
  the function returns `(label, line_number)` — not `(label,
  full_item_text)`.
- TODO `51be2bc`: the actual discussion instructions handed to the new
  claude session are no longer spliced into the launch prompt at all —
  `_write_discuss_instructions_file` writes them to a standalone
  `.desk_temp/discuss-instructions-<hex>.md` file, and the prompt just
  says "Read the file at `<path>` now and follow its instructions."

No enabled script in `tests/verify/` currently covers
`_place_discuss_claude_widget`/`_write_discuss_instructions_file`/
`parse_discuss_parking_lot_item` at all — real coverage gap, worth
rewriting rather than deleting.

`test_claude_widget_start_session_appends_extra_instructions`/
`test_claude_widget_start_session_resume_ignores_extra_instructions`
exercise `ClaudeWidget.start_session`'s `extra_instructions` plumbing
directly, independent of the parking-lot-item format — unaffected by
either contract change, kept as-is.

## Resolution

Rewrite `test_detect_and_parse` against `(label, line_number)`;
loosen `test_doc_version_and_split_file`'s hardcoded
`TEMPUI_DOC_VERSION == 5`; rewrite
`test_activate_temp_ui_places_claude_widget_with_item_text` against the
current `Line <N>` file format and the file-based instructions
delivery — no more embedding a "marker" string directly in the item
text (the whole point of TODO `624ff3a` was to stop doing that);
instead confirm a `.desk_temp/discuss-instructions-*.md` file was
written with the expected line-number reference, and that the claude
widget's prompt references reading that file.

## Verification

Re-run the rewritten script standalone (a real, slow integration test —
spawns real `claude` subprocesses, same as before); full `tests/verify/`
suite: disabled count drops to 11, 0 new failures.
