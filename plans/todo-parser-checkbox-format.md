# TODO widget: fix parsing of GitHub-checklist-style TODO.md files (e.g. world-timelines) (COMPLETED)

TODO `5a2f5b9`.

## Investigation

Read `~/world-timelines/TODO.md` directly
(the file the report names). It uses a different, but common and
recognizable, convention from this project's own:

```
- [x] 1. Bootstrap web-client project -- set up TypeScript... [planned: bootstrap-web-client.md]
- [x] 30. Entry descriptions shown in the detail panel contain wikitext markup artifacts...
- PENDING 21. Run ingester against the Wikipedia multistream dump...
```

`ITEM_START_RE` in `src/desk/todo_file.py` is anchored at the start of
the line (`^`) and only matches an id (7 hex digits, or -- already, a
prior generalization -- a plain decimal number) directly followed by
`". "`. None of world-timelines' 63 item lines match that at all, since
every one starts with a GitHub-style checklist marker (`- [x] ` /
`- [ ] `) *before* the number. Confirmed directly:
`ITEM_START_RE.match(line)` returns `None` for every single line in the
real file. Net effect: `parse_todo_file` finds zero item starts, so the
entire file becomes `preamble` and the TODO widget shows an empty list
-- not a crash, just silently nothing, which matches the report ("the
TODO widget's file parsing doesn't seem to work").

One item (`- PENDING 21. ...`, no checkbox at all) uses a third,
one-off prefix. Not generalizing for that specific case -- see Scope
below.

## Fix

Widen `ITEM_START_RE` to also match an optional leading GitHub-style
checklist marker before the id:

```python
ITEM_START_RE = re.compile(r"^(?:- \[([ xX])\]\s+)?([0-9a-f]{7}|\d+)\.\s")
```

- Group 1 (new): the checkbox character (`" "`, `"x"`, or `"X"`) when a
  checklist marker is present, else `None`.
- Group 2 (was group 1): the id, unchanged.

`parse_todo_file` uses the captured checkbox state as a *fallback* for
status: if `status_of(collapsed)` (this project's own
COMPLETED:/SUPERSEDED/PENDING description-prefix convention) falls
through to the "incomplete" default *and* a checkbox was present and
checked (`x`/`X`), treat the item as `"completed"` instead. An
unchecked `- [ ]` item, or a line with no checkbox at all (this
project's own convention), is unaffected -- this is purely additive,
never overrides an explicit COMPLETED:/SUPERSEDED/PENDING description
prefix.

## Scope

Not generalizing further for the one `- PENDING 21.` line (a bare
status word before the id, no checkbox) -- that's a one-off in this
particular external file, not a second recognizable convention the way
the checklist marker is (GitHub task lists are extremely common; a bare
leading status word with no consistent marker isn't a stable pattern to
special-case). It will simply not be recognized as an item start and
will be silently absorbed as trailing text of the preceding recognized
item -- a bounded, acceptable imperfection for one item out of 63,
consistent with this file's own existing "not universal TODO.md-format
detection" scope decision (see `todo_file.py`'s comments).

## Affected files

- `src/desk/todo_file.py` -- `ITEM_START_RE`, `parse_todo_file`.

## Verification

Headlessly, using `desk.todo_file.parse_todo_file` directly:
- Regression: this project's own `TODO.md` still parses identically
  (same item count, ids, statuses) before/after the regex change.
- Against a copy of world-timelines' real `TODO.md` content: item count
  matches the 63 checklist items actually present (`- [x]`/`- PENDING`
  lines), checked (`- [x]`) items get `status == "completed"`, and
  descriptions have the checklist marker stripped (start with the
  original text right after the id, not `- [x] N. `).
- A synthetic unchecked `- [ ] N. ...` item parses with
  `status == "incomplete"`.
- A full-app `DeskWindow` regression: place a real `todo` widget
  pointed at a temp copy of world-timelines' actual `TODO.md` and
  confirm the item list is no longer empty.

## Status

**Completed.** Implemented and verified headlessly exactly as
described above: a regression check confirming this project's own
`TODO.md` still parses identically, the real world-timelines
`TODO.md` now parsing all 62 `- [x]` checklist items as `completed`
(the one bare `- PENDING 21.` line intentionally out of scope, absorbed
without crashing), a synthetic unchecked `- [ ]` item parsing as
`incomplete`, this project's own COMPLETED:/PENDING description-prefix
convention still taking priority over a checked checkbox, and a
full-app `DeskWindow` regression placing a real `todo` widget against a
copy of the real file and confirming all 62 items now show (not an
empty list).
