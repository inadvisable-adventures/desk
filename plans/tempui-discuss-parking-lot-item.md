# tempui DSL addition: DiscussParkingLotItem (COMPLETED)

TODO `c0875bc`.

## Summary

A new tempui DSL keyword, `DiscussParkingLotItem`, that lets Desk (or
an agent working inside a Desk) kick off a fresh `claude` session
specifically to discuss one `PARKINGLOT.md` item. Placing/clicking the
notification for such a file spawns a brand-new claude widget whose
initial prompt is the usual `CLAUDE_WIDGET_PROMPT` (the standard
"you're embedded in Desk" instructions) with the full parking-lot item
text appended as a final instruction to discuss it.

## Design

Follows the existing `Scratch`/`Markdown` shape — first line
`DiscussParkingLotItem <label>`, everything after it verbatim as the
body (the full item text, copied in by whoever creates the file):

```
DiscussParkingLotItem A way to end a claude widget's session
- **A way to end a claude widget's session so it can get new
  instructions -- maybe an "end session" button?**
  ...full item text...
```

`label` is only for the notification text (`Discuss: <label>`);
`item_text` (everything after the first line) is what gets appended to
the new session's prompt as `"\n\nLet's discuss an item from
PARKINGLOT.md: {item_text}"`.

This is a **one-shot trigger**, not a live-synced document like
Scratch: once the claude session starts, there's nothing more to sync
back to the tempui file, and there's no `Answer` line. A tempui
filename is already a valid UUID (`is_temp_ui_filename`), which
composes for free with `claude --session-id`'s own UUID requirement
(`_place_widget`'s existing `CLAUDE_WIDGET_ID`/`instance_id` special
case only generates a fresh uuid4 when `instance_id is None` — passing
the tempui file's own UUID through satisfies this without any new
special-casing there).

The tricky part: `_place_widget` already calls `_bind_claude_widget`
(which calls `start_session`, which sends the initial prompt)
*unconditionally* and *immediately* whenever it places a `claude`
-kind widget — before `_activate_temp_ui`'s generic
`open_widget_content` → `_bind_temp_ui_content` two-step (used by
every other kind) gets a chance to run. Binding the extra instructions
*after* placement (the generic pattern) would be too late — the
session already started with the plain prompt. So the extra
instructions have to be threaded into `_place_widget` itself, not
bound afterward:

- `_place_widget` gains a `claude_extra_instructions: str = ""` param,
  passed to `_bind_claude_widget`, passed to
  `ClaudeWidget.start_session`'s new `extra_instructions: str = ""`
  param, appended after `_development_process_instruction()` only on a
  fresh (non-resume) launch.
- `_activate_temp_ui` special-cases the `discuss_parking_lot_item`
  kind: parses the item text and calls `_place_widget` directly
  (bypassing `open_widget_content`/`_bind_temp_ui_content`, which has
  no claude-specific branch and nothing to wire back anyway) with the
  built extra-instructions string.

A Desk reload restoring this widget later goes through the ordinary
saved-widget-instance path (`_load_desk_widgets` → `_place_widget(...,
restore=True)`), which calls `_bind_claude_widget(frame, resume=True)`
— `--resume`, no prompt resent — exactly like any other placed claude
widget; no special handling needed there.

## Affected files

- `src/desk/temp_ui.py` — `DISCUSS_PARKING_LOT_ITEM_KEYWORD`, added to
  `RESERVED_TEMPUI_KEYWORDS`; `detect_temp_ui_kind` new branch;
  `parse_discuss_parking_lot_item`; new split doc
  `tempui-discuss-parking-lot-item.md`
  (`DISCUSS_PARKING_LOT_ITEM_DOC_FILENAME`,
  `_DISCUSS_PARKING_LOT_ITEM_DOC`, added to `SPLIT_DOC_CONTENT`);
  `DOC_TEMPLATE`'s intro bullet list gains the new keyword/link (six
  built-in types -> seven); `TEMPUI_DOC_VERSION` bumped (4 -> 5).
- `src/desk/shell/window.py` — `_temp_ui_widget_id_for` new branch (->
  `CLAUDE_WIDGET_ID`); `_notify_temp_ui` new branch (`Discuss:
  <label>`); `_place_widget`/`_bind_claude_widget` gain
  `claude_extra_instructions`/`extra_instructions` params;
  `_activate_temp_ui` special-cases this kind.
- `widgets/claude/widget.py` — `ClaudeWidget.start_session` gains
  `extra_instructions: str = ""`, appended on a fresh launch.

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication`): a new
scratchpad script constructs a fake `.desk_temp/<uuid>` file with
`DiscussParkingLotItem <label>\n<item text>`, drives
`DeskWindow._activate_temp_ui` (via the unbound-method-on-a-double
pattern used throughout this session) or a real minimal `DeskWindow`,
and asserts: (a) a new claude-widget frame is placed with
`instance_id == uuid_str`; (b) the exact text sent to the PTY (via a
`TerminalWidget`/`ClaudeWidget` double capturing what
`type_into_shell` was called with) contains both the standard
`CLAUDE_WIDGET_PROMPT` content and the "Let's discuss an item from
PARKINGLOT.md: <item text>" suffix; (c) `detect_temp_ui_kind`/
`parse_discuss_parking_lot_item` round-trip correctly; (d) resuming an
already-restored instance (`resume=True`) does *not* include the extra
instructions (matches existing `fbd0554`-style resume behavior). Also
confirmed `TEMPUI_DOC_VERSION == 5` and the rendered
`tempui-discuss-parking-lot-item.md`/main doc content. Full scratchpad
regression suite re-run.

## Status

Implemented as designed above.
