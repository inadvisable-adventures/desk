# Terminal widget: send special keys (arrows, Shift+Tab, etc.) to the PTY (COMPLETED)

TODO `3be392a`.

## Investigation

`TerminalWidget.keyPressEvent` (`src/desk/terminal_widget.py`, shared by
the Claude and Console widgets) only sends: the four `KEY_BYTES` entries
(Return/Enter/Backspace/Tab), Ctrl+C / Ctrl+D, and anything with a
non-empty `event.text()`. **Arrow keys, Shift+Tab, Home/End, Page
Up/Down, Delete, Insert, and Escape all produce an empty `event.text()`
and aren't in `KEY_BYTES`, so pressing them sends nothing at all** — the
exact symptom reported (arrow keys can't move a selection in claude's
TUI; Shift+Tab can't cycle modes). Terminal programs expect these as
ANSI escape sequences.

## Fix

Map the missing keys to their standard terminal byte sequences in
`keyPressEvent` (via a small `_key_to_bytes` helper):

- **Mode-independent** (added to `KEY_BYTES`): Shift+Tab
  (`Qt.Key.Key_Backtab`) → `ESC [ Z` (CSI Z / back-tab); Escape → `ESC`;
  Delete → `ESC [ 3 ~`; Insert → `ESC [ 2 ~`; Page Up → `ESC [ 5 ~`;
  Page Down → `ESC [ 6 ~`. (Existing Return/Enter/Backspace/Tab
  unchanged.)
- **Cursor keys + Home/End** (mode-dependent): Up/Down/Right/Left → final
  byte `A`/`B`/`C`/`D`; Home/End → `H`/`F`. These are prefixed with
  `ESC [` (CSI) normally, or `ESC O` (SS3) when the screen is in
  **application cursor keys mode** (DECCKM). Full-screen TUIs (claude
  included) commonly enable DECCKM and then only recognize the SS3 form,
  so honoring it is what makes claude's arrow navigation actually work.
  `pyte` tracks DECCKM in `screen.mode`; it encodes a private mode `N`
  as `N << 5`, and DECCKM is private mode 1, so the value to test for is
  `1 << 5` (defined as a named constant with that derivation commented,
  and covered by a test that enables DECCKM via `ESC [ ? 1 h` so a pyte
  encoding change would be caught).
- **Ctrl+letter**: generalize the current Ctrl+C/Ctrl+D special-case to
  Ctrl+A…Ctrl+Z → control bytes `0x01`…`0x1a` (`key - Key_A + 1`), which
  keeps Ctrl+C (`0x03`) / Ctrl+D (`0x04`) identical and adds the rest
  (Ctrl+Z, Ctrl+R, Ctrl+A/E for readline, etc.).

Order in `_key_to_bytes`: cursor/Home/End (mode-aware) first, then the
static `KEY_BYTES` table, then Ctrl+letter, then printable
`event.text()`. `keyPressEvent` still doesn't call `super()` (the widget
is read-only and fully owns input handling — unchanged).

## Scope

- Not handling modified cursor keys (e.g. Ctrl+Left word-jump →
  `ESC [ 1 ; 5 D`), function keys F1–F12, or the numeric keypad — none
  are in the report and they add a large, low-value mapping table. The
  common navigation/editing keys above cover the reported cases and the
  everyday ones.

## Affected files

- `src/desk/terminal_widget.py` — `KEY_BYTES` additions, a
  `_CURSOR_KEYS` map, a `_DECCKM` constant, and a `_key_to_bytes`
  helper refactored out of `keyPressEvent`.

## Verification

Headless, against a real `TerminalWidget` (real PTY), spying on
`os.write(self._master_fd, …)` (or reading the slave) to capture the
exact bytes each key produces — driving synthetic `QKeyEvent`s through
`keyPressEvent`:

- Arrow keys send `ESC [ A/B/C/D` in normal mode, and `ESC O A/B/C/D`
  after the screen is put into DECCKM (feed `ESC [ ? 1 h` through the
  stream first); Home/End likewise switch `ESC [ H/F` ↔ `ESC O H/F`.
- Shift+Tab (`Key_Backtab`) sends `ESC [ Z`; Escape sends `ESC`; Delete
  `ESC [ 3 ~`; Page Up/Down `ESC [ 5 ~` / `ESC [ 6 ~`.
- Ctrl+A → `0x01`, Ctrl+C → `0x03` (unchanged), Ctrl+Z → `0x1a`.
- Regression: a plain letter still sends its UTF-8 text; Return still
  sends `\r`; Tab still sends `0x09`.

## Status

**Completed.** Implemented and verified headlessly (spying on
`os.write` to the PTY master while driving synthetic `QKeyEvent`s):
arrows/Home/End send CSI in normal mode and switch to SS3 after DECCKM
is enabled via `ESC [ ? 1 h` (and back on reset); Shift+Tab/Escape/
Delete/Page Up/Page Down send their sequences; Ctrl+A/C/D/Z send
`0x01/0x03/0x04/0x1a`; and plain text / Return / Tab / Backspace are
unchanged.
