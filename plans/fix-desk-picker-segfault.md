# Investigate: segfault while interacting with the Desk picker

TODO `b44e8ba`.

## Summary

Reported crash: `python -m desk` started normally, discovered the usual
widget catalog, opened a real `.desk` file — then `Segmentation fault:
11` with no Python traceback at all. No specific interaction (name
click vs. directory click vs. hover) was captured in the report beyond
"interacting with the Desk picker" generally.

## Investigation so far

- **`LEARNINGS.md`'s `QNativeGestureEvent(dev=None)` segfault note**:
  ruled out as the direct cause. That entry is specifically about
  *synthesizing* a native gesture event by hand (a test-authoring
  mistake); Desk's own code (`canvas.py`) only *reads*
  `QEvent.Type.NativeGesture`/`gestureType()` from events the OS itself
  delivers (real trackpad input), and never constructs one. Still
  possible a *different*, real hardware-driven gesture event happening
  to arrive while the Desk picker has focus/hover state interacts badly
  with something else, but there's no evidence tying the two together
  yet, and no repro to test it against.
- **`desk_picker.py`/`canvas.py` code review**: nothing else obviously
  fragile found. `_ClickableLabel` (`enterEvent`/`leaveEvent`/
  `mousePressEvent`) is a plain, ordinary `QLabel` subclass with no
  native/C-extension interaction. `_DeskListPopup._activate_item`
  already has the "close before emit" fix from TODO `c8f6fb3` for a
  *different*, previously-confirmed crash in this exact class
  (`RuntimeError: wrapped C/C++ object ... has been deleted`, a Python
  -level exception with a full traceback) — not a plausible match for
  *this* report, since a segfault has no Python-level exception at all;
  whatever's happening here is either a genuinely separate bug, or
  a variant severe enough to crash below the Python/Qt exception layer
  before any handler runs.
- **Background-thread GUI access**: checked whether any of this
  codebase's `watchdog`-based watchers (`WidgetWatcher`, the TODO
  widget's file watcher, `TempUiManager`) could be calling into GUI
  code directly from their background observer threads (a classic real
  segfault cause in PyQt) rather than only emitting a Qt signal across
  threads (safe). All three only ever call `.emit()` on a dedicated
  relay `QObject` from the watcher thread; nothing else. No sign these
  are involved, but they weren't specifically active in whatever
  sequence produced the reported crash either, so this isn't a
  conclusive rule-out.

## Why this is blocked

A segfault with no Python traceback is, by nature, not something code
review alone can pin down, and there isn't a captured, specific
sequence of interactions to reproduce it against (the report notes
this explicitly: "reproduce the exact picker interaction that
triggered it"). Guessing at a fix without a reproduction would be
just as likely to paper over a coincidence as to fix the real cause.

## Status

**Blocked** on getting a specific reproduction. Question added to
`QUESTIONS.md`. Marked `PENDING` in `TODO.md` until that's answered (or
until the bug recurs with more specific circumstances captured, e.g. a
`crashreporter`/`Console.app` crash log, which would let this be
investigated from an actual stack trace instead of guesswork).
