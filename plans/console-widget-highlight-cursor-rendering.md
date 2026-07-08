# Fix console widget selection highlighting and cursor visibility (COMPLETED)

## Summary

Confirmed via direct investigation (feeding known SGR sequences into a
real `pyte.Screen`/`Stream` and inspecting the resulting `Char` attributes)
two concrete, distinct rendering bugs in the console widget's
`_char_format`/`_resolve_color`, both plausibly explaining the reported
symptoms (no highlight for selected menu options; cursor not visible):

1. **Reverse video with default colors renders nothing.** `char.reverse`
   swaps `fg_name`/`bg_name` before resolving colors — but when neither is
   explicitly set (both are the string `"default"`), swapping "default"
   with "default" is a no-op, and `_resolve_color("default")` returns
   `None` either way, so *no* foreground/background override is ever
   applied. Reverse video (`ESC[7m`) is the standard, most common
   mechanism terminal programs use to render a selected/highlighted item
   (and many full-screen TUIs — very plausibly including `claude`'s own
   interface — hide the native terminal cursor entirely and instead draw
   their *own* cursor indicator as a single reverse-video character), so
   this one bug plausibly explains *both* reported symptoms at once.
2. **"Bright" SGR colors (`ESC[90-97m`/`ESC[100-107m`) aren't resolved at
   all.** Confirmed directly: `pyte` reports these as names like
   `"brightred"`, `"brightblack"`, etc. — not in `ANSI_COLOR_MAP`, and not
   6-character hex strings either, so `_resolve_color` falls through to
   `None` and the color is silently dropped. Bright colors are commonly
   used for emphasis/highlighting in modern CLI output.

Also confirmed directly, and *not* pursued further here: `pyte` 0.8.2 has
its own typo bug — background bright magenta (`ESC[105m`) reports as
`"bfightmagenta"` (missing the `r`), not `"brightmagenta"`. Recorded in
`LEARNINGS.md`; handled defensively (see Design).

## Investigation note: a focus-transfer red herring

While investigating, a synthetic test (a `QApplication.sendEvent`-based
click on the embedded console widget's content area, routed through
`WorkspaceView`) showed the embedded `TerminalWidget` never actually
gaining Qt focus (`hasFocus()` stayed `False`, `QApplication.focusWidget()`
stayed the `WorkspaceView` itself) — which would, if real, *also* explain
"no visible cursor" (a `QPlainTextEdit`'s blinking caret only paints when
focused, confirmed separately: a standalone, explicitly-focused
`TerminalWidget` *does* paint a visible cursor rectangle).

Not treated as a real bug here: the user has already demonstrably typed
commands into the console widget successfully in real usage (running
`claude` itself, reported via earlier screenshots/output) — which would be
impossible if clicking-then-typing didn't work at all. The synthetic
test's `QApplication.sendEvent` on a `WorkspaceView` that was `.show()`n
but never a real, OS-activated, frontmost window is a much more likely
explanation (this project's `LEARNINGS.md` already documents `.show()`n
test windows behaving differently around focus in this environment). Not
chased further — noted here rather than silently dropped, per this
project's practice of not letting an investigative dead end vanish
without a trace.

## Affected files

- `widgets/console/widget.py` (edit) — real default colors (not `None`)
  so reverse-video actually swaps something; add bright-color resolution.
- `LEARNINGS.md` (edit) — record `pyte`'s `"bfightmagenta"` typo.

## Design

### Real default colors, not `None`

```python
DEFAULT_FOREGROUND = "#e8e8e8"
DEFAULT_BACKGROUND = "#1e1e1e"
```

`_resolve_color(name, default_hex)` now always returns a concrete
`QColor` — falling back to `default_hex` (not `None`) for `"default"`,
unresolvable, or malformed values — so `_char_format` always sets an
explicit foreground *and* background. Critically, `char.fg`/`char.bg` are
each resolved to a concrete color *first* (against their own correct
default — foreground's default isn't the same color as background's),
and *then* the two resolved `QColor`s are swapped for `char.reverse` —
swapping the pre-resolution name strings instead is a no-op whenever both
are literally the string `"default"`, since neither carries information
about which slot it came from once extracted as a bare string (see
Status/`LEARNINGS.md` — this was the actual bug in the first attempt at
this fix). `TerminalWidget.__init__` also sets its own stylesheet to the
same two colors, so the "default" case is visually consistent with the
widget's own background outside any text.

This doesn't defeat the run-coalescing in `_redraw` — two adjacent
default-colored characters still produce equal `QTextCharFormat`s (now
both carrying the same concrete default colors instead of both being
under-specified), so they still coalesce into one run exactly as before.

### Bright colors

```python
BRIGHT_COLOR_MAP = {
    "brightblack": "#555753", "brightred": "#ef2929", "brightgreen": "#8ae234",
    "brightbrown": "#fce94f", "brightyellow": "#fce94f", "brightblue": "#729fcf",
    "brightmagenta": "#ad7fa8", "bfightmagenta": "#ad7fa8",  # pyte's own typo
    "brightcyan": "#34e2e2", "brightwhite": "#eeeeec",
}
```

Checked in `_resolve_color` alongside the existing `ANSI_COLOR_MAP`.

## Verification

Entirely headless, but pixel-level, not just property-level — the exact
gap that let the original bug through undetected (item 16/17's
verification checked `QTextCharFormat`/`cursorWidth()`/`textCursor()`
*properties* were set correctly, never that they actually produced a
*visible* difference). `QWidget.grab()` → `QImage` → `pixelColor()`
inspection is fully offscreen (no `.show()`n real-window visual
inspection needed, confirmed working in this environment already for
`ChromiumWidget`/`QWebEngineView` testing):

1. Feed a reverse-video sequence with no explicit colors set
   (`ESC[7m SELECTED ESC[0m`), `grab()` the widget, and confirm the
   "SELECTED" text's pixels are visibly different from the surrounding
   default-colored text's pixels (not just that a `QTextCharFormat`
   property was set).
2. Feed each bright-color SGR code (90–97 foreground, 100–107 background,
   including the `"bfightmagenta"` case) and confirm `_resolve_color`
   returns the expected concrete color (not `None`) for each.
3. Regression: re-run item 16/17's existing headless checks (cursor
   -overwrite, plain SGR color/bold formatting, cursor position/
   visibility) to confirm the default-color change didn't break them.
4. Regression: launch `claude --help` in the widget (as done for item
   16's verification) and confirm output still renders correctly.

## Key design decisions / tradeoffs

- **Always resolve to a concrete color, never `None`.** The `None`
  ("don't override, let the widget's own default show through") approach
  was the direct cause of reverse-video-with-defaults doing nothing —
  there's no way to "swap" an absence of a color. Making the default
  itself a real, known color is the only way reverse video can work
  correctly in the default case.
- **A small, fixed 8-color bright palette, not a fuller xterm 256-color
  table.** Matches the level of fidelity `ANSI_COLOR_MAP` already commits
  to for the base 8; true 256-color/truecolor values already come through
  correctly as raw hex strings via the existing fallback path.
- **Defensively handling `pyte`'s own `"bfightmagenta"` typo rather than
  filing it upstream and waiting.** `pyte` is a slow-moving dependency
  (0.8.2 has been the latest release for a while, per earlier
  investigation) — a one-line defensive alias costs nothing and doesn't
  block on someone else's release cadence.
- **Not chasing the focus-transfer finding.** See the Investigation note
  above — real-world evidence (the user successfully typing `claude`
  commands into this exact widget) contradicts treating it as a genuine
  bug; recorded rather than silently dropped, but not acted on.

## Status

Implemented and verified, entirely headlessly — including genuine
pixel-level rendering checks (`QWidget.grab()` → `QImage` →
`pixelColor()`), not just property checks, per this item's own root
cause (item 16/17's verification checked properties only, which is
exactly how a "sets the right value, renders nothing visible" bug slipped
through originally):

1. Caught a real bug in the *first* attempt at this very fix: swapping
   `char.fg`/`char.bg` (the pre-resolution name strings) for reverse video
   is a no-op when both are the literal string `"default"` — confirmed via
   a direct property-level test that showed no swap occurred at all.
   Corrected to resolve each color to its own proper default first, then
   swap the resolved `QColor`s — verified the corrected version actually
   swaps two distinct colors.
2. Pixel-level: fed a reverse-video sequence with no explicit colors into
   a real `TerminalWidget`, `grab()`'d it, and confirmed (via a dense,
   whole-widget color-frequency scan — a single guessed sample coordinate
   unreliably missed the actual text, see `LEARNINGS.md`) that the
   expected highlight color appears as a large, unambiguous block of
   pixels, not just set as an unrendered property.
3. Pixel-level: same technique for a bright-red SGR sequence — confirmed
   `#ef2929` appears as a real block of rendered pixels.
4. Confirmed `_resolve_color` correctly resolves every bright SGR color
   (90–97 foreground, 100–107 background), including `pyte`'s own
   `"bfightmagenta"` typo.
5. Regression: re-ran all of item 16/17's existing headless checks
   (cursor-overwrite, plain SGR color/bold formatting, cursor position/
   visibility) and the original `plans/console-widget.md` checks (echo
   round-trip, process spawn, cleanup-on-destroy) — all still pass.
6. Regression: `claude --help` still renders correctly in the widget.

Not resolved (deliberately, per the Investigation note above): whether
"cursor not rendered" was *entirely* explained by the reverse-video bug,
or partly by the separate focus-transfer finding that was set aside as a
likely test-environment artifact. If a real user still reports no visible
cursor after this fix, that finding should be revisited rather than
treated as fully closed.
