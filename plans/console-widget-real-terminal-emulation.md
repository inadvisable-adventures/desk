# Fix console widget rendering for full-screen TUI programs (COMPLETED)

## Summary

Replace the console widget's regex-stripped-ANSI, append-only rendering
(`plans/console-widget.md`) with real terminal emulation via `pyte`
(cursor-aware screen-buffer state), since the append-only approach breaks
exactly the thing the widget's whole purpose is stated to be: running
`claude`, whose interface redraws itself in place (cursor positioning,
box-drawing, colored status bar) rather than printing a linear scrolling
log. Confirmed via screenshot: overlapping, unreadable text, no visible
cursor.

## Reversing the "no third-party dependency" decision

`plans/console-widget.md`/`design-docs/architecture.md` originally chose
regex-stripped ANSI specifically to avoid a third-party terminal-emulation
dependency (`CLAUDE.md`'s "avoid adding dependencies, prefer bespoke
solutions"), accepting that full-screen TUI programs wouldn't render
correctly as a documented tradeoff. That tradeoff is no longer acceptable:
the concrete evidence is that the widget's own stated core purpose
("hosts bash so it can run claude") is what breaks, not some
secondary/rare use case. A correct VT100/ANSI interpreter is also
genuinely deep, well-trodden territory (cursor positioning, scroll
regions, character attributes, ...) where hand-rolling a partial
implementation risks worse bugs than a small, focused, pure-Python
library written for exactly this. **Reversing course**: add `pyte`
(pure Python, no C extensions, LGPLv3, actively used for exactly this
purpose) as a real dependency, replacing the regex-strip approach
entirely.

## Design

### `pyte.Screen` + `pyte.Stream` maintain real terminal state

```python
self._screen = pyte.Screen(PTY_COLS, PTY_ROWS)
self._stream = pyte.Stream(self._screen)
```

On each PTY read: `self._stream.feed(text)` (instead of stripping ANSI
and appending), then `self._redraw()`.

### `_redraw()`: render the *current screen*, not an appended log

`self._screen.buffer` is a `{row: {col: Char}}` grid (`Char` is a
namedtuple: `data`, `fg`, `bg`, `bold`, `italics`, `underscore`,
`strikethrough`, `reverse`, `blink`) reflecting the terminal's actual
current visual state — this is what must be displayed, replacing
whatever was there before, not appended to. `_redraw()`:

1. Rebuilds the widget's document from scratch: for each of the
   `PTY_ROWS` rows, walk across columns, coalescing consecutive
   same-attribute characters into runs, and `QTextCursor.insertText(run,
   format)` with a `QTextCharFormat` built from that `Char`'s attributes
   (foreground/background color via a small ANSI-name→hex map, falling
   back to using pyte's own hex string directly for 256-color/truecolor
   values which pyte already provides as raw hex; bold via
   `QFont.Weight.Bold`; underline/strikethrough via the format's
   corresponding properties).
2. Positions the *visible* cursor at `(screen.cursor.y, screen.cursor.x)`
   via `QTextCursor.setPosition`/`setTextCursor`, and sets
   `setCursorWidth(0 if screen.cursor.hidden else 2)` so a program that
   explicitly hides the cursor (many TUIs do while redrawing) doesn't
   leave a stray blinking caret visible.

### Scope: no scrollback (for now)

Only the current on-screen buffer is rendered — no scroll-up/history
view. `pyte.HistoryScreen` supports this and could be wired in later; not
needed to fix the reported bug (garbled rendering + missing cursor), so
left as explicit future work rather than folded into this fix.

### Everything else about the widget is unchanged

PTY spawn (`start_new_session=True`, not `preexec_fn` — see
`LEARNINGS.md`), key forwarding, and `destroyed`-triggered cleanup via a
closure-captured `@staticmethod` (also per `LEARNINGS.md`) all stay
exactly as they are; only the *rendering* path changes.

## Affected files

- `pyproject.toml` (edit) — add `pyte` to dependencies.
- `widgets/console/widget.py` (edit) — replace `ANSI_ESCAPE_RE`/
  `_strip_ansi`/append-based `_on_readable` with `pyte.Screen`/
  `pyte.Stream` and a real `_redraw()`.
- `design-docs/architecture.md` (edit) — revise the Key Design Decisions
  entry that justified regex-stripping/no-dependency, replacing it with
  the real rationale for using `pyte`; update the Console Widget component
  description.

## Verification

1. Headless: feed a known sequence with cursor repositioning (e.g. write
   text, move the cursor up and overwrite part of a previous line via
   `\x1b[<N>A`/`\x1b[<N>G`) directly into the widget's PTY and confirm the
   *displayed* text reflects the final, correctly-overwritten screen state
   — not both the original and overwritten text concatenated (which is
   exactly the bug being fixed).
2. Headless: confirm colored/bold output produces the expected
   `QTextCharFormat` (foreground color set, bold flag set) on the relevant
   run of characters, by feeding SGR sequences and inspecting the
   resulting document's formatting directly.
3. Headless: confirm the visible text cursor is positioned at the
   coordinates `pyte.Screen.cursor` reports after a redraw, and that
   `setCursorWidth(0)` is applied when the cursor is hidden
   (`\x1b[?25l`) and restored when shown again (`\x1b[?25h`).
4. Full-cycle: launch the real app; run a command that exercises cursor
   positioning (e.g. `printf` with cursor-movement escapes, or — closer to
   the real reported case — actually launching `claude` if available in
   this environment) and confirm the widget's text no longer shows the
   overlapping/concatenated garbling from the original screenshot.
5. Regression: re-run `plans/console-widget.md`'s original verification
   (basic `echo` round-trip, process spawn/cleanup) to confirm the
   rendering rewrite didn't break the parts that already worked.
6. Actually visually eyeballing a live `claude` session in the widget is
   the real-world confirmation this is chasing, and remains **skipped**
   for direct confirmation in this environment (no way to drive real
   mouse/keyboard interaction) — steps 1–4 exercise the same underlying
   render path a real session would.

## Key design decisions / tradeoffs

- **`pyte` instead of hand-rolled VT100 parsing.** Real terminal emulation
  is a deep, well-trodden problem; getting cursor positioning, scroll
  regions, and character-attribute tracking right by hand is a much
  larger and more error-prone undertaking than reusing a small, focused,
  pure-Python library built for exactly this — especially once the
  concrete cost of *not* doing so (the reported bug) is this visible and
  affects the widget's stated core purpose.
- **Full redraw per update, not incremental/diffed rendering.** Simpler
  and correct; at `80×24`, a full rebuild is cheap. Diffing changed rows
  only (matching how `pyte.DiffScreen` reports dirty lines) is a
  reasonable future optimization if redraw performance ever becomes a
  real problem, not a concern worth solving preemptively here.
- **No scrollback/history view yet.** Only fixing what's reported
  (garbled current-screen rendering, missing cursor) — scrollback is a
  distinct, separable feature or a later increment on `pyte.HistoryScreen`.

## Status

Implemented and verified:

1. Headless cursor-overwrite test: fed `"first line\r\n"` + `"second line"`
   then `\x1b[1A\x1b[1G` (cursor up one row, to column 1) + `"XXXX"`;
   confirmed the displayed row is exactly `"XXXXt line"` (final overwritten
   state only, not the original and overwritten text concatenated).
2. Headless SGR/format test: fed `\x1b[1;31mBOLD RED\x1b[0m plain`, confirmed
   the `BOLD RED` run's `QTextCharFormat` has `fontWeight() ==
   QFont.Weight.Bold` and foreground color `#cc0000`, and the trailing
   `plain` run has neither.
3. Headless cursor position/visibility test: confirmed the visible
   `QTextCursor` tracks `pyte.Screen.cursor.x/y` after each redraw, and that
   `setCursorWidth(0)` is applied on `\x1b[?25l` and restored to `2` on
   `\x1b[?25h`.
4. Regression (from `plans/console-widget.md`): `echo` round-trip still
   works: typed text reaches bash and its output appears in the widget.
   Process spawn (`bash` appears as a real child process via `ps`) and
   cleanup-on-destroy (process is no longer running after the widget is
   destroyed) both still pass.
5. Full-app smoke test: launched the real app widget, ran `clear; printf
   'AAAAAAAAAA\n'; sleep 0.2; tput cup 0 0; printf 'BBBBB'` — confirmed the
   final displayed row is `"BBBBBAAAAA"` (cursor-positioned overwrite
   applied in place), not the two strings concatenated.
6. Real-world check (stronger than originally planned — `claude` turned out
   to be available in this environment): ran `claude --help` in the widget.
   Its actual multi-column, wrapped, aligned help output rendered correctly
   with no garbling. Full interactive `claude` session still not driven
   directly (no real mouse/keyboard interaction available in this
   environment), consistent with the verification plan's original scope.
