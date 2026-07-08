# Isolate hot reload failures to the one widget, not the whole app (COMPLETED)

## Summary

`PythonWidgetHost._rebuild()` has no exception handling around
re-importing a widget's module or calling `build()`. Confirmed via a real
crash: any error there propagates out of `_on_widget_changed` (a Qt slot
connected to the Hot Reload Broker's signal) and is fatal to the whole
process in this PyQt6 setup — not just a failure to reload that one
widget. Since this app's own core purpose is running `claude` to edit
Desk's own widget code live, a transient broken intermediate save is
routine, not a rare edge case, and it currently costs the entire session
every time.

## Affected files

- `src/desk/shell/python_widget.py` (edit).

## Design

### Catch, log, and keep the previous widget in place

`_rebuild()` wraps the re-import + `build()` call in `try/except
Exception`. On failure: log an `ERROR` with the full traceback (unlike
the `pyte` private-CSI case — TODO fa288ce — this is a genuinely
unpredictable, per-bug failure each time, so full diagnostic depth is
worth it here, not noise) and return without touching `self._current` or
the layout at all — the previously-working widget (if any) stays exactly
where it was, visually and functionally untouched. A broken intermediate
save now means "hasn't picked up your latest edit yet" (check the log),
not "the whole app just died."

### First-build failure: a visible placeholder, not a silently blank widget

If the *first* build (during `__init__`, before there's ever been a
working `self._current`) fails, there's no previous widget to fall back
to — leaving `self._current` as `None` and adding nothing to the layout
would show a totally blank widget instance with no indication anything's
wrong. Falls back to a small inline error-message `QLabel` instead
(non-selectable, per `CLAUDE.md`'s labels convention), which a later
successful rebuild replaces normally (the existing swap logic already
handles "replace whatever `self._current` currently is").

## Verification

Entirely headless:

1. Construct a `PythonWidgetHost` pointed at a widget whose `widget.py`
   raises on import (a syntax/attribute error, matching the real
   originally-reported case) — confirm construction doesn't raise, and
   the host shows the error placeholder instead of being blank.
2. Construct a working widget, confirm normal operation; then simulate a
   hot-reload where the *rebuilt* module is broken (patch the file
   in-place to introduce an error, fire the broker signal) — confirm the
   *previous* widget instance is still present and functional (not
   replaced, not removed), and the failure was logged.
3. Confirm a subsequent *successful* rebuild after fixing the file
   correctly replaces whatever's currently shown (whether that's the
   error placeholder from a first-build failure, or the still-good
   previous widget from a later-rebuild failure) with the new one — the
   existing swap path needs no changes for this to work correctly.
4. Regression: confirm a normal, always-successful widget (e.g. `demo`)
   still builds and hot-reloads exactly as before.

## Key design decisions / tradeoffs

- **Keep the previous widget in place on a later rebuild failure, rather
  than replacing it with an error placeholder too.** The old widget is
  still fully functional — discarding working state because a *later*
  edit introduced a bug would be strictly worse for the person actively
  iterating on that file. The error placeholder is only for the case
  where there's truly nothing else to show.
- **Full traceback in the error log, unlike the `pyte` private-CSI
  case.** That case is one specific, already-fully-diagnosed, always
  -identical failure; this one is "whatever bug the currently-being
  -edited widget happens to have," different every time and worth full
  diagnostic depth.

## Status

Implemented and verified, entirely headlessly:

1. Confirmed a first-build failure (a widget whose `build()` raises)
   shows the error placeholder instead of raising or leaving a blank
   widget, and logs an `ERROR`.
2. Confirmed a working widget survives a later broken rebuild (a
   `SyntaxError` on re-import) with the *original* widget instance still
   in place and functional, logged as an `ERROR`.
3. Confirmed a subsequent successful rebuild correctly replaces whatever
   was being shown — both the later-rebuild-failure case (still-good
   previous widget) and the first-build-failure case (error placeholder)
   — with no changes needed to the existing swap logic.
4. Regression: confirmed the real `demo` widget still builds and
   hot-reloads normally.
5. Directly reproduced the exact originally-reported crash: copied the
   real `widgets/todo/widget.py`, introduced the exact reported bug
   (`itemDoubleClicked.connect(self._show_edit_dialog)` with that method
   undefined), and fired a hot-reload against it — confirmed the app
   survives (logs the error, keeps the previous working `todo` widget in
   place) instead of taking down the whole process.
