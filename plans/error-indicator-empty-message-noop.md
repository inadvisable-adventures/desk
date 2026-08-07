# Fix the [ERROR] titlebar button's empty-message noop (TODO `47aaf73`)

## Summary

Per
`../FEEDBACK/FEEDBACK-DESK-error-indicator-empty-message-noop-2026-08-04-1305.md`:
the `[ERROR]` titlebar button can light up and then do nothing when
clicked. Root cause, confirmed directly: `DeskWindow
._on_widget_error_clicked` (`src/desk/shell/window.py:1970`) does `if
not frame.last_error_message: return` -- inferring "was there an
error" from the captured message string's truthiness. But
`_LoggingWebEnginePage.javaScriptConsoleMessage`
(`src/desk/shell/chromium_widget.py:57-68`) already has a deliberate
`message or ""` fallback for exactly the case where Qt hands back a
falsy message for a real error (an uncaught exception/rejection/
`console.error()` call with no usable text) -- so the click handler's
own gate is wrong precisely for the case that fallback exists to
handle. The button's own visibility (`WidgetFrame.set_error`'s
`has_error` argument) and the click handler's gate
(`last_error_message` truthiness) are driven by two different signals
that can disagree.

## Affected files

- `src/desk/shell/widget_frame.py` -- `WidgetFrame` gains an explicit
  has-error flag.
- `src/desk/shell/window.py` -- `_on_widget_error_clicked` gates on
  that flag instead of message truthiness; falls back to a
  placeholder string when showing an empty-text error.
- `tests/verify/` -- new coverage.

## Design decisions

- **New `WidgetFrame._has_error: bool`**, set directly from
  `set_error`'s `has_error` argument, independent of
  `last_error_message`'s content -- not reusing `_TitleBar`'s own
  existing `_has_error` (`widget_frame.py:297`), which is a private
  implementation detail of that chrome widget (purely for button
  visibility) and not meant to be read from outside it. `WidgetFrame`
  already has an established pattern for this exact shape
  (`self.locked`, a plain public bool mirroring `_titlebar`'s own
  private state) -- following that, not inventing a new one.
- **`_on_widget_error_clicked` gates on `frame._has_error`**, not
  `frame.last_error_message`. `last_error_message` remains exactly
  what it already is (the text to display), just no longer doubling
  as the "was there an error" signal too.
- **Placeholder text, not silent cancellation**, when showing the
  dialog for an error with empty captured text: `"(no error message
  was captured)"`, matching the FEEDBACK item's own suggested
  wording -- shown via `_confirm_widget_error_dismissed`, not by
  mutating `last_error_message` itself (keeps the stored value
  honest about what was actually captured).
- **Only the `kind: "html"`/`ChromiumWidget` path is affected** --
  confirmed the `kind: "python"` path (`build_error_changed`) always
  carries `traceback.format_exc()`, which is never empty, so no
  change needed there; `_has_error` still gets set correctly for that
  path too (same `set_error` call), just never hits the empty-message
  case in practice.

## Step-by-step implementation

1. `widget_frame.py`: add `self._has_error: bool = False` to
   `WidgetFrame.__init__` near `self.last_error_message`. Update
   `set_error` to also set `self._has_error = has_error`
   (unconditionally, not just when `has_error` is `True` -- clearing
   the indicator must clear this flag too, unlike
   `last_error_message`, which is deliberately left alone on clear).
2. `window.py`: change `_on_widget_error_clicked`'s guard from `if not
   frame.last_error_message: return` to `if not frame._has_error:
   return`. When showing the dialog, pass `frame.last_error_message or
   "(no error message was captured)"` instead of
   `frame.last_error_message` directly.
3. New verify coverage (see below); run the full `tests/verify/`
   suite.

## Key tradeoffs

None of substance -- this is a straightforward bug fix restoring the
button's own documented behavior ("a later error on the same instance
re-lights it") for the one case it was silently broken for.

## Verification

New checks in `tests/verify/verify_widget_error_indicator.py`
(extending the existing file, matching its established `_FakeWindow`
-plus-real-`WidgetFrame` pattern), real (no mocking):
- `frame.set_error(True, "")` (an error with genuinely empty captured
  text) leaves `frame._has_error` true and the `[ERROR]` button
  visible, exactly like a non-empty message would.
- Clicking the button in that state (via
  `DeskWindow._on_widget_error_clicked`) now actually shows the
  confirmation dialog (previously silently did nothing) -- with the
  placeholder text, not an empty string.
- The indicator still clears correctly after being dismissed in the
  empty-message case, same as the existing non-empty-message
  coverage.
- `frame._has_error` is `False` after `set_error(False)`, confirming
  the flag itself (not just the visible button state) is reset.
- Full `tests/verify/` regression suite.
