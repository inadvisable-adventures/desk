# Feedback items (desk_*_feedback)

See `desk-temporary-ui.md` (in this same directory) for this
directory's own overview and its current set of tags. This is not a
tempui-DSL file type: it is three MCP tools on the `desk` server, for
reporting friction with Desk itself (not with your own project).

- `desk_list_feedback(status?, keyword?, directory?)` lists items, newest
  first, each with its triage `status`: `open` (not yet acted on),
  `parkinglot`, `implemented` or `external`. **Search with a keyword
  before filing**, so you do not write a near-duplicate.
- `desk_get_feedback(id, directory?)` returns one item's full text and
  status.
- `desk_create_feedback(title, body, directory?)` files a new `open` item.
  Desk derives the filename (`FEEDBACK-DESK-<slug>-<date>-<time>.md`) and
  heading; `body` is markdown: what happened, why it matters, a suggested
  fix. Only the problem and fix belong there, not secrets.

Triage is done by Desk's maintainers; you can create and read, not move
or edit. `directory` is relative to the current project (default
`../FEEDBACK`); absolute paths are refused.
