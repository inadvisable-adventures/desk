# TODO.md bullet-prefixed items (TODO `80de4d4`) (COMPLETED)

## Summary

`ITEM_START_RE` only accepted `id. ` or `- [ ] id. ` at column 0, so a
file writing items as plain markdown bullets (`- 4f9f415. ...`) parsed as
zero items (7 real ones in `inadvisable-archive/TODO.md`), and the MCP
tools / TODO widget silently showed an empty list. Source feedback:
`FEEDBACK-DESK-todo-md-items-with-a-leading-markdown-bullet-4f9f415-parse-a-2026-11-08-1138.md`.
All three of its suggested fixes are done.

## Changes

1. **`src/desk/todo_file.py`**: `ITEM_START_RE` also accepts `- `, `* `,
   `+ ` bullets (with or without a checkbox). Group numbers unchanged. The
   bullet stays in `raw_text` (reordering never reformats) but is stripped
   from `description`. This repo's own TODO.md parses to the same 410 items
   before and after. Not covered on purpose: ordered markers (`1. id.`)
   and indented starts, which are ambiguous with prose/sub-lists.
2. **Fail loud**: `unrecognized_items_message(path)` returns a message when
   no item is recognized but lines look item-shaped (looser regex:
   indentation, `1.`/`1)` markers). `desk_list_todo_items` /
   `desk_get_next_todo_item` return it as an error instead of `[]`/"nothing
   actionable"; the TODO widget shows it in its status line. A genuinely
   item-free file still gives `[]`.
3. **`scripts/todo_item_ids.py canonicalize FILE [--dry-run]`**: strips
   column-0 bullet/ordered markers before an id, skips fenced code and HTML
   comments, leaves checklist items alone, lists remaining item-shaped
   lines for manual review; idempotent. Self-contained, as the script must
   be.
4. `shared_development_process.md`: "Item format Desk's tooling reads".

## Known limit

The parser has never been fence/comment-aware; a bulleted example item
inside a code fence now counts as an item just as a bare `id. ` line
already did.

## Verification

`tests/verify/verify_todo_bullet_items.py` (18) and a new case in
`verify_desk_mcp_server.py`; `verify_todo_widget`,
`verify_seed_todo_item_ids_script`, `verify_todo_item_ids_script_regex_fixes`
still pass.
