# TODO widget: double-click to edit an item (TODO d49f1cf) (COMPLETED)

## Summary

TODO d49f1cf: "double-clicking on a TODO item in the TODO widget should
pop up an editor."

Add an edit flow to `widgets/todo/widget.py`'s `TodoWidget`: double
-clicking a row in the list opens a hovering popup dialog (same shape as
the existing "Add Item" dialog) prefilled with that item's current
description; submitting updates the item's text in place (same
`item_id`, permanent per `development-process.md`'s "Item IDs" section —
never recomputed on edit) and commits immediately, the same way adding an
item does.

Note: TODO 8db7891 (later in `TODO.md`, "the add/edit textbox on the TODO
widget should be much larger, and multiline") already refers to this as
"the add/edit textbox," implying one shared dialog for both flows. To
avoid redoing this later, `_AddItemDialog` is generalized in place now
(renamed `_ItemDialog`) to take an optional initial description, rather
than adding a second near-duplicate dialog class.

## Affected files

- `widgets/todo/widget.py` (edit):
  - `_AddItemDialog` → `_ItemDialog`: constructor gains `initial_text:
    str = ""` (sets the field's initial text and selects it, so typing
    immediately replaces it, matching normal "edit text" affordances);
    behavior and signal (`item_submitted`) otherwise unchanged.
  - `TodoWidget.__init__`: connect `self._list.itemDoubleClicked` to a
    new `_show_edit_dialog(list_item)`.
  - `_show_add_dialog` renamed/kept, `_show_edit_dialog(list_item)`:
    reads the `TodoItem` off `ITEM_ROLE`, opens an `_ItemDialog`
    prefilled with its description, positioned under the double-clicked
    row (mirrors `_show_add_dialog`'s under-the-button positioning), and
    connects `item_submitted` to `self._edit_item(item, ...)`.
  - New `_edit_item(item: TodoItem, description: str) -> None`: finds
    `item` by identity (or `item_id`) in `self._state["items"]`, replaces
    it with a new `TodoItem` — same `item_id`, `status=status_of(new
    description)`, `raw_text=f"{item_id}. {description}\n"` — stops the
    debounce timer (folding in any pending reprioritization, same as
    `_add_item`), writes+commits immediately with message `f"Edit TODO
    item: {truncate_description(description, 60)}"`, then repopulates the
    list and reports commit status.
  - `status_of` imported from `desk.todo_file` alongside the existing
    imports.

No changes needed to `src/desk/todo_file.py` — `TodoItem`/`status_of`/
`render_todo_file` already support constructing a replacement item with
the same id and reassembling the file from the (edited) list.

## Design decisions

- **Same id, always.** Editing a description never regenerates
  `item_id` — ids are permanent per `development-process.md`. Only
  `status`, `description`, and `raw_text` change.
- **Immediate commit, not debounced.** Like adding an item, an edit is a
  distinct, deliberate user action (not a drag gesture that might still
  be mid-motion), so it commits right away and folds in any pending
  reprioritization — same rationale `_add_item` already uses.
- **Reuse the add dialog.** One `_ItemDialog` class serves both flows
  (empty for add, prefilled for edit) rather than a second dialog class,
  anticipating TODO 8db7891's "add/edit textbox" language.
- Double-click during an in-progress drag-reorder won't spuriously
  trigger: Qt's `itemDoubleClicked` only fires for an actual double
  -click on a row, not a drag gesture.

## Verification

Headless, via a real `TodoWidget` pointed at a temporary `TODO.md` in a
throwaway git repo (matching TODO d1205ef's original verification
style):

1. Construct a `TodoWidget` against a temp repo with a two-item
   `TODO.md`; simulate a double-click on a row (`itemDoubleClicked.emit`
   or a real `QTest.mouseDClick`); confirm a popup with the item's
   current description appears.
2. Submit an edited description; confirm: the item's `item_id` is
   unchanged, its `status`/`description` reflect the new text, the list
   row updates, the file on disk reflects the edit (via
   `render_todo_file`), and a real git commit was made with the "Edit
   TODO item: ..." message.
3. Regression: adding a new item and reprioritizing (drag) still work
   as before.

No step requires a visible window — popup presence/content and list
state are checked via Qt object state, not pixels.

## Status

This plan (and most of this change) was already in progress, uncommitted,
from an earlier session that crashed mid-edit — see TODO ef1b2e7's own
crash diagnosis. Picking it up found the working tree already had the
`_AddItemDialog` → `_ItemDialog` rename and the
`itemDoubleClicked.connect(self._show_edit_dialog)` wiring in place, but
two things left unfinished (exactly why it crashed): `_show_add_dialog`
still referenced the old, now-nonexistent `_AddItemDialog` name, and
`_show_edit_dialog`/`_edit_item` were never actually defined. Finished
both, then verified headlessly:

1. Confirmed double-clicking a row (both by calling `_show_edit_dialog`
   directly and by emitting the real `itemDoubleClicked` signal, to
   exercise the actual wiring, not just the handler in isolation) opens a
   dialog prefilled with that item's current description.
2. Confirmed submitting an edit preserves `item_id`, updates `status`
   (via `status_of`) and `description`, writes the file, and makes a real
   git commit with an "Edit TODO item: ..." message.
3. Regression: confirmed adding a new item and reprioritizing (drag) via
   a real reorder-then-debounce-then-flush cycle both still work
   correctly.
