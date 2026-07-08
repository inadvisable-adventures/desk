# TODO widget: hover button to open a plan document (COMPLETED)

TODO `b25412e`.

## Summary

"If there is a plan listed in a todo item, detect that and provide a
button on hover to open the plan document in Desk." Items in `TODO.md`
carry a `[planned: <file>.md]` marker; when an item has one, hovering its
row should reveal a button that opens that plan file as a widget on the
canvas.

## Key decisions

- **Detect the plan in `desk.todo_file`**: add a `plan: str | None` field
  to `TodoItem`, parsed from the item's `raw_text` with a
  `[planned: <name>]` regex. One place, reusable, and keeps the widget
  from re-parsing.
- **Hover affordance = a single floating button that follows the mouse
  to the hovered row**, *not* per-row `setItemWidget`. The TODO list is a
  `QListWidget` with `InternalMove` drag-to-reorder (`rowsMoved`), and
  putting a real widget in each row via `setItemWidget` is a well-known
  fragile combination with `InternalMove` (the row widget doesn't
  reliably move with its item). Instead: one `QPushButton` child of the
  list's `viewport()`, hidden by default; enable mouse tracking and use
  `QListWidget.itemEntered` to, when the hovered item has a plan,
  position the button over that row's right edge and show it (hide it
  for plan-less rows, on list leave, on scroll, and on repopulate). This
  gives a genuine hover button while leaving the item model — and thus
  drag-reorder — completely untouched.
- **Open the plan in the Markdown renderer** (TODO 6bf83a9) — best for
  *reading* a plan. Add a small public `set_file(path)` to
  `MarkdownWidget` (refactored out of its `_open_file`) so the opener can
  point a freshly-placed markdown widget at the plan. Placement uses the
  existing widget-opener hook (`current_context.get_widget_opener()`,
  the same mechanism the TODO widget already uses to spawn a Scratch
  widget for edit conflicts).
- **Plan file location**: `todo_path.parent / "plans" / <plan name>` —
  plans live in a `plans/` directory beside `TODO.md` (this project's
  convention). If the file doesn't exist, the markdown widget shows its
  own "no longer exists" note (no special-casing needed).

## Affected files

- `src/desk/todo_file.py` — `TodoItem.plan`, parsed in `parse_todo_file`.
- `widgets/markdown/widget.py` — public `set_file(path)`.
- `widgets/todo/widget.py` — mouse-tracking + `itemEntered` wiring, the
  floating `_plan_button`, positioning/visibility, and the open-plan
  action via the widget opener.

## Verification

Headless:
- `parse_todo_file`: an item with `[planned: foo.md]` yields
  `item.plan == "foo.md"`; an item without yields `None`; this project's
  own `TODO.md` parses (many items with plans) unchanged otherwise.
- `MarkdownWidget.set_file(path)` renders the file and starts watching it
  (reuses the existing markdown verification shape).
- TODO widget: `itemEntered` over a planned row shows the button
  positioned within that row's rect; over a plan-less row (and on list
  leave) hides it; clicking the button calls the widget opener with
  `"markdown"` and `set_file` with `plans/<name>` resolved against the
  TODO.md directory (driven with a fake opener via
  `current_context.set_widget_opener` that returns a real
  `MarkdownWidget`).
- Regression: drag-reorder (`rowsMoved` → reprioritize) and the existing
  add/edit/double-click flows still work (the item model is unchanged).

## Status

**Completed.** Implemented and verified headlessly: `TodoItem.plan`
parsing (and this project's own `TODO.md` still parses, with plans
detected); `MarkdownWidget.set_file`; the TODO widget's hover button
(shown positioned on a planned row's right side, hidden over plan-less
rows / on list leave / on repopulate; clicking calls the `"markdown"`
opener with the plan path); and a full-app `DeskWindow` flow where
clicking the button places a markdown widget rendering the plan file
(frame count +1). Drag-reorder is untouched (the item model is
unchanged). The `MarkdownWidget.set_file` API also cleanly supersedes
its old open-file-dialog-only path.

## Note on autonomous choices

The two open UX choices here (hover affordance style; which widget to open
the plan in) were put to the user via `AskUserQuestion` but not answered
(away). Proceeding with the floating-hover-button (to honor the literal
"button on hover" while protecting drag-reorder) and the Markdown renderer
(for reading), both easily changed later if the user prefers the toolbar/
context-menu affordance or the editor.
