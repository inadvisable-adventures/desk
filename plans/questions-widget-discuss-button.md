# Questions widget: a "Discuss" button per entry (COMPLETED)

TODO `46e1b42`.

## Summary

Adds a "Discuss" button to each entry shown in the Questions widget
(`widgets/questions/`, the `QUESTIONS.md`-backed list of open-ended
questions -- not to be confused with the singular tempui `Question`
widget). Clicking it does exactly what the tempui
`DiscussParkingLotItem` keyword does (TODO `c0875bc`): places a new
claude widget with a fresh session, prompted to discuss that entry's
full text.

## Design

`DeskWindow._place_widget`/`_bind_claude_widget`'s
`claude_extra_instructions` plumbing (built for
`DiscussParkingLotItem`) is generalized into a small shared helper
rather than being PARKINGLOT.md-specific:

- `DeskWindow._place_discuss_claude_widget(source_label, item_text,
  instance_id=None)` -- places a new claude widget whose fresh-launch
  prompt is appended with `"\n\nLet's discuss an item from
  {source_label}: {item_text}"`. `_activate_temp_ui`'s
  `DiscussParkingLotItem` branch now calls this with
  `source_label="PARKINGLOT.md"` and `instance_id=uuid_str` (unchanged
  behavior, just refactored to share the helper).
- `DeskWindow.start_discussion(source_label, item_text)` -- registered
  as a new `current_context` hook (`set_discuss_starter`/
  `get_discuss_starter`, mirroring the existing widget-opener/temp-UI
  -write-recorder/main-window/widget-path-resolver hooks), so a
  `python` widget can trigger the same flow without importing
  `desk.shell.window` directly. No `instance_id` in the hook's own
  signature -- each button click is an independent, fresh session
  (there's no natural per-question-entry identity to dedup against,
  unlike a tempui file's own UUID).

`widgets/questions/widget.py`'s `QuestionsWidget` gains a "Discuss"
button using the exact same floating-button-that-follows-the-hovered
-row pattern as the TODO widget's own "📄 Plan" button (`_plan_button`/
`_on_item_entered`/`_hide_plan_button` in `widgets/todo/widget.py`) --
not a per-row `setItemWidget`, to match the sibling widget's own
established convention (even though this list doesn't drag-reorder,
consistency with the widget it already mirrors is worth more than a
different approach here). Clicking it calls
`current_context.get_discuss_starter()` with `("QUESTIONS.md",
entry.raw_text)` -- `raw_text` is the entry's exact original text
(heading, body, and `(Answer: ...)` block), the same "full verbatim
item text" shape `DiscussParkingLotItem`'s own body already uses for a
`PARKINGLOT.md` item.

## Affected files

- `src/desk/shell/current_context.py` -- new `set_discuss_starter`/
  `get_discuss_starter` hook pair.
- `src/desk/shell/window.py` -- `_place_discuss_claude_widget` (shared
  helper, extracted from `_activate_temp_ui`'s `DiscussParkingLotItem`
  branch), `start_discussion` (the registered hook), hook registration
  in `__init__`.
- `widgets/questions/widget.py` -- `QuestionsWidget` gains the
  floating "Discuss" button (`_discuss_button`/`_on_item_entered`/
  `_hide_discuss_button`/`_discuss_hovered_entry`), an `eventFilter`
  override to hide it on mouse-leave, and a scrollbar-triggered hide,
  mirroring `widgets/todo/widget.py`'s plan-button wiring.

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication`): a real
`QuestionsWidget` built against a temp `QUESTIONS.md` with one entry,
with `current_context.set_discuss_starter` replaced by a recording
stub -- confirms hovering the entry shows the Discuss button positioned
over that row, clicking it calls the stub exactly once with
`("QUESTIONS.md", entry.raw_text)`, and the button hides again when the
mouse leaves the list. Separately, a `_place_discuss_claude_widget`
-level test (the same real-claude-widget-process harness used for TODO
`c0875bc`) confirms `start_discussion`/`_place_discuss_claude_widget`
places a real claude widget whose session prompt contains the given
`source_label`/`item_text`. Confirmed via `git stash` that both new
tests fail pre-fix. Full scratchpad regression suite re-run.

## Status

Implemented as designed above.
