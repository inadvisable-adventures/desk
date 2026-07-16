# Plan: TODO f7469bc (COMPLETED) — investigate `disabled_verify_questions_discuss_button.py`

## Investigation

Same underlying cause as TODO `3c613af`: `_place_discuss_claude_widget`
now delivers its instructions via a standalone `.desk_temp/discuss
-instructions-*.md` file (TODO `51be2bc`), not spliced into the launch
prompt — regardless of which branch built the instructions body (this
script uses the `item_text` branch, i.e. `parking_lot_line=None`,
unaffected by TODO `624ff3a`'s line-number change specifically, but
still affected by the file-based-delivery change). The fake
`DeskWindow` double is also missing `_write_discuss_instructions_file`
plus the same `_bind_event_mediator`/`_event_mediator`/
`_custom_widget_content_hash` gaps found in the sibling scripts above.

## Resolution

Add the missing fake-double attributes/methods; rewrite the assertion
that checks the widget's terminal output for the marker/item text
directly — instead confirm the prompt references reading a
`discuss-instructions-*.md` file, and that the file itself contains
the expected "an item from QUESTIONS.md: <marker>" text.

## Verification

Re-run standalone (passes); full `tests/verify/` suite: disabled count
drops to 5, 0 new failures.
