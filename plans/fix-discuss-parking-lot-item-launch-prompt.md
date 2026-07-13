# Fix DiscussParkingLotItem launch prompt: reference by line number, and stop nested discussions (COMPLETED)

TODO `624ff3a`.

## Summary

Reported: clicking the notification for a `DiscussParkingLotItem` tempui
file (TODO `c0875bc`) for the "Packaging & distribution" parking-lot item
produced something wrong with the launch message that kept `claude` from
starting. Two changes requested:

1. Instead of embedding the *entire* `PARKINGLOT.md` item's text
   (heading, body, everything) into the tempui file and from there into
   the new claude session's initial launch prompt, the tempui file
   should just reference the item by its starting line number in
   `PARKINGLOT.md`, and the launch prompt should tell the new session to
   go read that line itself rather than being handed the full text.
2. The launch prompt should explicitly tell the new session to have the
   discussion right there, in the current session -- not immediately
   start another new Desk discussion (e.g. by writing its own
   `DiscussParkingLotItem` file).

## Investigation

Traced the full path: `ClaudeWidget.start_session` (`widgets/claude/widget.py`)
already runs the *entire* assembled prompt (base "embedded in Desk" text +
the dev-process sentence + `extra_instructions`) through a single
`shlex.quote(...)` call before splicing it into the `exec claude
--session-id ... '<prompt>'` command line typed into the shell -- so this
isn't a case of literally-unescaped shell metacharacters. The full
parking-lot item text is still real markdown prose (backticks, quotes,
em-dashes, blank lines) of unbounded length, though, and a couple of
still-plausible failure modes exist independent of the quoting itself:
bash's default interactive `histexpand` performs `!`-history-expansion
even *inside* a single-quoted argument, and the whole multi-hundred-byte
quoted blob is written to the PTY in one `os.write` immediately after
spawning `bash` -- before it's certain `bash`'s own readline has taken
over the terminal in raw mode, so an unlucky race could still hit the
kernel tty layer's canonical-mode line-length limit. Neither was
independently reproduced here. Regardless of which (if either) is the
exact mechanism, shortening the message to a short, fixed-shape sentence
referencing a line number -- instead of splicing in arbitrary,
unbounded, hand-written prose -- avoids all of the above at once, which
is the fix directed by the user.

## Design

### 1. `DiscussParkingLotItem` DSL shape changes

Old shape (first line label, everything after verbatim item text):

```
DiscussParkingLotItem <label>
- **A way to end a claude widget's session...**
  ...full item text...
```

New shape (first line label, second line a line-number reference):

```
DiscussParkingLotItem <label>
Line <N>
```

`<N>` is the 1-indexed line number, in the *current* `PARKINGLOT.md`,
where the item's own text starts (its leading `- **Title**` bullet) --
written by whoever creates the file (an agent that just read the file),
not computed by Desk itself. `label` keeps its existing job (the
notification's text only, `"Discuss: <label>"`).

`src/desk/temp_ui.py` changes:

- `parse_discuss_parking_lot_item(text) -> tuple[str, int] | None` --
  same overall shape as before (first-line label check), but now scans
  for a `Line <N>` line and returns `(label, line_number)`. Returns
  `None` if the keyword doesn't match or no valid `Line <N>` is found.
- `_DISCUSS_PARKING_LOT_ITEM_DOC` rewritten: explains the new two-line
  format, updates the example, and is explicit that the creating agent
  should write the item's *starting line number*, not copy its text.
- `TEMPUI_DOC_VERSION` bumped `5 -> 6` (content actually changed).

### 2. `src/desk/shell/window.py`: short reference instead of full text, plus a "don't start a new discussion" instruction

`_place_discuss_claude_widget` is shared by two callers:

- the tempui `DiscussParkingLotItem` path (`_activate_temp_ui`), which
  after this change has only a line number, not the item's text;
- the Questions widget's "Discuss" button (`DeskWindow.start_discussion`,
  TODO `46e1b42`), which passes a `QUESTIONS.md` entry's own full
  `raw_text` -- shorter, structurally different content, not reported as
  broken, and out of scope here.

Generalized rather than duplicated: `_place_discuss_claude_widget` gains
an optional `parking_lot_line: int | None = None` parameter alongside
the existing `item_text` (now defaulted to `""`, only meaningful when
`parking_lot_line` is `None`). When a line number is given, the built
instruction references it ("read that file yourself...") instead of
splicing in `item_text`. Both branches get a new, shared trailing
sentence telling the new session to discuss it in-place rather than
kicking off another new Desk discussion -- this applies equally well to
the Questions-widget path (same risk: a fresh session could otherwise
try to "helpfully" spin up yet another discussion of its own), so it's
added once in the shared helper rather than duplicated per call site.

`_activate_temp_ui`'s `CLAUDE_WIDGET_ID` branch now reads the parsed
line number and passes `parking_lot_line=` instead of the old
`item_text=`.

### 3. Refresh this project's own already-provisioned docs

`.desk_temp/desk-temporary-ui.md` and
`.desk_temp/tempui-discuss-parking-lot-item.md` in *this* project were
already written by an earlier provisioning pass, which only runs once
-- not on every boot (same situation TODO `11aeb43`/TODO `e57ce5f` noted
for their own doc changes). Refreshed by hand to match, including the
bumped version note.

### 4. Re-author the existing demo tempui file

The `.desk_temp/<uuid>` file created earlier this session for discussing
"Packaging & distribution" (the one whose launch reportedly broke) is
rewritten in the new `Line <N>` format so a real end-to-end try can be
made from Desk's own UI after this fix lands.

## Affected files

- `src/desk/temp_ui.py`
- `src/desk/shell/window.py`
- `.desk_temp/desk-temporary-ui.md` (this project's own copy)
- `.desk_temp/tempui-discuss-parking-lot-item.md` (this project's own copy)
- the existing demo `.desk_temp/<uuid>` file (rewritten to the new format)

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`):

- `parse_discuss_parking_lot_item` round-trips the new `Line <N>` format
  correctly; rejects a file missing the `Line` line or with a
  non-integer value; `detect_temp_ui_kind` is unaffected (still keys off
  the first line's keyword only).
- `_place_discuss_claude_widget`, driven directly against a real
  `DeskWindow` (unbound-method-on-a-double pattern used throughout this
  project's own tests): with `parking_lot_line=N` the exact text sent to
  `type_into_shell` contains a short "line N of PARKINGLOT.md" reference
  (not the old full item text) and the new "discuss it here, don't start
  a new Desk discussion" sentence; with a plain `item_text=` call (the
  Questions-widget path) the full text is still included verbatim, and
  the new trailing sentence is present there too (regression check that
  the shared addition didn't silently drop this path's own content).
- A full end-to-end `_activate_temp_ui` run against a synthetic
  `DiscussParkingLotItem` file in the new format places a claude widget
  and sends the expected short prompt.
- `TEMPUI_DOC_VERSION == 6` and the rendered main/split doc content
  reflect the new format.

Real `claude` binary launch itself can't be exercised in this
environment (no interactive terminal), so this stops at confirming the
exact command string built and typed into the PTY is well-formed and
short -- consistent with how every prior claude-widget TODO in this
project has verified `start_session`.

## Status

Implemented as designed above.
