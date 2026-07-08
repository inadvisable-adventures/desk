# TODO widget (COMPLETED)

## Summary

A new `kind: "python"` widget (`widgets/todo/`) that reads the "nearest"
`TODO.md` relative to the current Desk's associated directory (searching
upward through parent directories, same idea as how tools locate a
`.git`/`pyproject.toml`), displays its items as a filterable
(complete/incomplete/pending/superseded) list, supports drag-and-drop
reprioritization and adding new items via a hovering dialog, and commits
both kinds of change back to the target repository — reprioritization
debounced (1 minute of inactivity, or an add happening) before
committing.

## New shared modules (not widget-specific — reusable)

- `src/desk/todo_ids.py` — the id-generation logic currently duplicated
  only in `scripts/todo_item_ids.py`, extracted so both the script and
  this widget import one implementation. Also generalizes the item-start
  pattern to match either the hash-id style (`^[0-9a-f]{7}\.\s`) or a
  plain numbered style (`^\d+\.\s`) — this widget will be pointed at
  *arbitrary* project TODO.md files via a Desk's associated directory,
  which may not have adopted the hash-id scheme yet.
- `src/desk/todo_file.py` — parsing/rendering for a TODO.md-shaped file:
  - `find_nearest_todo_file(start_dir) -> Path | None`: walks `start_dir`
    and its parents looking for `TODO.md`.
  - `TodoItem` (dataclass): `item_id: str`, `status: str`, `description:
    str` (whitespace-collapsed, for display/truncation), `raw_text: str`
    (the item's exact original text, preserved verbatim for
    reassembly).
  - `parse_todo_file(path) -> (preamble_text, list[TodoItem])`.
  - `render_todo_file(preamble, items) -> str`: reassembles file text
    from a preamble plus items *in their current list order* — only
    order changes for a reprioritize; an add appends one new raw block.
    Existing items' text is never reformatted, only reordered.
  - `status_of(description) -> str`: `"superseded"` if the description
    starts with that word, else `"completed"`, else `"pending"`, else
    `"incomplete"` — matching this project's own established
    `development-process.md` conventions (`COMPLETED:`, `SUPERSEDED by`,
    `PENDING`), which is what "nearest TODO.md" means in practice for any
    directory that follows the same process.
- `src/desk/shell/current_context.py` — the minimal live-context
  mechanism `python` widgets have needed since item 18 explicitly
  deferred it ("no `python` widget has a way to learn the current Desk's
  directory yet"). A single module-level `get_current_desk_directory()`/
  `set_current_desk_directory()` pair; `DeskWindow` calls the setter
  whenever the current desk's directory is established or changes
  (construction, `switch_desk`, `change_current_desk_directory`). No
  signal/notification — see Scope below for why.

## Affected files

- `src/desk/todo_ids.py` (new, see above).
- `src/desk/todo_file.py` (new, see above).
- `src/desk/shell/current_context.py` (new, see above).
- `scripts/todo_item_ids.py` (edit) — import id-generation from
  `desk.todo_ids` instead of duplicating it.
- `src/desk/shell/window.py` (edit) — call
  `current_context.set_current_desk_directory(...)`.
- `widgets/todo/widget.json`, `widgets/todo/widget.py` (new) — the widget
  itself.

## Design

### Reading: resolve directory once, manual reload afterward

The widget resolves `current_context.get_current_desk_directory()` and
loads the nearest `TODO.md` **once, at construction**. If the user
switches Desks while the widget is open, it does *not* auto-refresh (see
Scope) — a small "Reload" button re-resolves and re-reads on demand.

### Filtering

A row of checkable toggle buttons — "Incomplete", "Pending", "Completed",
"Superseded" — all checked by default (nothing hidden until the user
narrows it down). Toggling one shows/hides matching rows in the list
immediately (no need to reload from disk).

### The list + drag-and-drop reprioritization

A `QListWidget` with `setDragDropMode(InternalMove)` — Qt's built-in
mechanism for exactly this (reorder items by dragging within the same
list), rather than hand-rolling drag/drop plumbing. Each row's display
text: the item's `description` truncated to 100 characters (`text[:100] +
"..."` if longer), prefixed with a short status tag (`[completed]`,
`[pending]`, etc.) so the truncation limit itself isn't spent on
redundant status words baked into every description (e.g. `COMPLETED:`).
Each row's `Qt.ItemDataRole.UserRole` holds the underlying `TodoItem` so
reordering the visual list can be read back into the real item order.

`model().rowsMoved` signal → triggers the debounced-commit path (see
below) for a reprioritization.

### Adding an item: a hovering dialog, matching `WidgetSpawnMenu`'s pattern

An "Add Item" button opens a small `Qt.WindowType.Popup` widget (a text
field + submit button) anchored under the button — the same
`Popup`-flag/positioning approach `WidgetSpawnMenu` (item 14) already
established for exactly this "small hovering input, dismiss on
click-away" shape. On submit: generate a fresh id
(`desk.todo_ids.make_item_id`), build a new `TodoItem`, **append** it to
the end of the underlying item list (lowest priority by default — the
user re-prioritizes it via the same drag-and-drop the list already
supports, rather than the widget guessing where a new item "should"
rank), write it to disk, and commit immediately (see below).

### Committing: git, scoped to the target file's own repo, debounced for reprioritization

Both kinds of change call a shared `_write_and_maybe_commit(commit_now:
bool, message: str)`:

1. `render_todo_file(...)` and write the result to the resolved
   `TODO.md` path.
2. If `commit_now`: run `git -C <repo-root> add TODO.md && git -C
   <repo-root> commit -m "<message>"` (`git -C <dir> rev-parse
   --show-toplevel` first, to find the repo root; if that fails — the
   target directory isn't a git repo — skip the commit and show an
   inline status message instead of crashing; the file write itself
   still succeeds).
3. If not `commit_now` (a reprioritization): reset a `QTimer.singleShot`
   debounce (60s) that calls this same commit path when it fires. A new
   add arriving before the timer fires commits immediately and cancels
   the pending timer (folding the reorder and the add into one commit).
   The widget's `destroyed` cleanup also flushes a still-pending commit
   (via the same closure-captured-locals-plus-staticmethod pattern
   `TerminalWidget` already established — connecting `destroyed` to a
   bound method of the same object doesn't fire, see `LEARNINGS.md`),
   so closing the widget/app doesn't silently drop an unsaved
   reprioritization.

## Scope

- **No live Desk-change notification for `python` widgets.** Building a
  full "Desk changed" broker signal (mirroring `HotReloadBroker`) just
  for this one widget's benefit is more machinery than one caller
  justifies yet — a manual reload button is a reasonable, honest
  substitute. If a second `python` widget later needs live Desk-change
  awareness, that's the point to build the shared signal.
- **Status categories match this project's own conventions
  specifically** (`COMPLETED:`/`SUPERSEDED by`/`PENDING`), not an attempt
  at universal TODO.md-format detection — reasonable since "nearest
  TODO.md" only produces a well-formed filterable list for a directory
  that already follows the same `development-process.md`-style
  conventions this project uses.
- **New items are appended (lowest priority), not inserted at a guessed
  position.** The list's own drag-and-drop already provides
  reprioritization — no need for the add flow to guess where a new item
  belongs.

## Verification

Entirely headless:

1. `todo_file.find_nearest_todo_file`: confirm it finds a `TODO.md` in
   the starting directory, and separately confirm it walks up through
   parent directories to find one that isn't in the starting directory
   itself.
2. `todo_file.parse_todo_file`/`render_todo_file`: round-trip a small
   synthetic TODO.md (a few items, mixed statuses) and confirm
   re-rendering an *unmodified* parse produces byte-identical output;
   confirm reordering items and re-rendering preserves each item's exact
   original text, just in the new order.
3. `todo_file.status_of`: confirm each of the four categories is detected
   correctly from representative description text, including a
   `"COMPLETED (SUPERSEDED by ...)"` case (should classify as
   `"completed"`, matching this project's own such items) vs. a bare
   `"SUPERSEDED by ..."` case with no `"COMPLETED"` prefix (should
   classify as `"superseded"`).
4. Widget: construct it directly against a temp directory with a
   synthetic `TODO.md`, confirm the list shows the right rows, truncated
   correctly (a >100-char description gets cut to 100 chars + `"..."`; a
   short one doesn't).
5. Widget: confirm toggling a status filter hides/shows the right rows
   without re-reading the file.
6. Widget: simulate a drag-and-drop reorder (directly manipulating the
   `QListWidget`'s row order, then emitting/triggering the same handler
   `rowsMoved` would) and confirm the debounce timer starts, no commit
   happens immediately, and firing the timer causes the file to be
   rewritten in the new order and a real git commit to appear (using a
   real temp git repo, not a mock) with the expected message.
7. Widget: confirm an add both writes the new item to disk immediately
   *and* commits immediately, and cancels any pending reprioritization
   debounce (folding both changes into that one commit).
8. Widget: confirm the "not a git repo" path writes the file successfully
   without raising, and surfaces a status message instead of crashing.
9. Regression: confirm `scripts/todo_item_ids.py` still works correctly
   after being refactored to import from `desk.todo_ids`.

## Status

Implemented and verified, entirely headlessly:

1. `find_nearest_todo_file`: confirmed both direct-hit and parent-walk
   cases.
2. `parse_todo_file`/`render_todo_file`: confirmed byte-identical
   round-trip on an unmodified parse, and confirmed reordering preserves
   each item's exact original `raw_text`, just in the new order.
3. `status_of`: confirmed all four categories, including the
   `"COMPLETED (SUPERSEDED by ...)"` vs. bare `"SUPERSEDED by ..."`
   distinction.
4. Widget: confirmed it loads a synthetic TODO.md, shows the right item
   count, and truncates a long description to exactly 100 characters +
   `"..."` while leaving a short one untouched.
5. Widget: confirmed toggling a status filter button shows/hides rows
   immediately without re-reading the file.
6. Widget: confirmed a reorder (i) marks `pending` and does *not* commit
   immediately (real git repo, commit count checked directly), (ii) the
   debounce timer firing commits exactly once and the file on disk
   reflects the new order.
7. Widget: confirmed adding an item commits immediately, correctly folds
   in a still-pending reprioritization into that same commit, and cancels
   the pending debounce timer.
8. Widget: confirmed the new item's id/description/status land correctly
   in the re-rendered file, with the prior reorder preserved.
9. Widget: confirmed the not-a-git-repo path writes the file successfully
   without raising and reports it via the status label instead of
   crashing.
10. Widget: confirmed the `destroyed`-triggered flush (the same closure
    -captured-plain-dict pattern `TerminalWidget` established, since
    connecting `destroyed` to a bound method of the same object never
    fires — see `LEARNINGS.md`) commits a still-pending reprioritization
    that never got to fire its debounce timer, so closing the widget
    doesn't silently lose an unsaved reorder.
11. Full-app: placed the widget via a real `DeskWindow` pointed at this
    very repository's own directory and confirmed it correctly resolved
    and loaded this project's actual `TODO.md` (all 31 real items).
12. Regression: confirmed `scripts/todo_item_ids.py` still produces the
    identical id for the same input after being refactored to import
    `make_item_id` from `desk.todo_ids`.
