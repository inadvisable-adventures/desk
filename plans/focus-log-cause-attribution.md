# Focus log cause attribution (TODO 48fd3e0) -- COMPLETED

Follows from the third session of `investigations/text-focus-stability.md` (feedback file
`../FEEDBACK/FEEDBACK-DESK-text-focus-stability-repro-data-2026-10-16-1709.md`): the first real
repro showed scene focus being reassigned with no mouse press and a `py=` stack that is only
`app.py:62:main<__main__.py:6:<module>`. That value cannot tell "Qt did this on its own" from "Qt's
C++ handling of an input event did this", and nothing records which widget repainted just before
the change.

## Summary

Two additions to `desk.focus_logger`, both only active while logging is enabled:

1. **`py=native` becomes real.** The Python frames beneath the Qt event loop (`main`, `<module>`) are
   on every callback's stack, so they are noise. Strip them, so `py=` is `native` when no Desk or
   widget Python code is involved.
2. **Event context on each focus change.** `focus_item` and `focus_in` entries gain:
   - `ev=` -- the last few distinct events the application dispatched before this entry, most recent
     first, as `Type:ReceiverClass:age_ms` joined by `<` (e.g. `Timer:QTimer^_PromptInput:3<KeyPress:WorkspaceView:120`;
     a QTimer also names its parent). Only events that can *drive* the loop are listed (an allowlist:
     input, timers, queued calls, window activation, show/hide/resize, user events), not paint, palette,
     hover or layout noise.
   - `painted=` -- frames (by instance id, `canvas` for the view itself) whose widgets received a
     paint event within the last 100 ms, as `id:age_ms` joined by `,`. Tests the "a neighbour's
     background repaint triggers the flip" half of the refined hypothesis directly. Omitted when
     empty.

## Affected files

- `src/desk/focus_logger.py`
- `tests/verify/verify_focus_logger.py` (new checks)
- `design-docs/widget-ux.md` ("Focus logging" section), `investigations/text-focus-stability.md`

## Approach

- **Entry-frame stripping.** In `enable()` schedule `QTimer.singleShot(0, self._capture_loop_base)`.
  That slot runs from the event loop, so its caller frames (`sys._getframe(1)` outward) are exactly
  the Python frames beneath Qt dispatch. Store them as `(code object, current line)` pairs,
  outermost first. `_python_stack()` drops a matching outermost run from the stack it collects.
  Comparing the *line* as well as the code means a `setFocus()` made directly by a caller that
  merely sits in the same function at a different line (a test's module level, startup code) is
  not stripped. Until the base has been captured (the first loop turn after `enable()`), nothing is
  stripped. Cleared in `disable()`.
- **Event ring.** The app-level filter already runs for every event while enabled. Append
  `(monotonic, type, obj)` for non-noise types to a `deque(maxlen=EVENT_RING)`; format lazily when a
  focus entry is written (a deleted receiver raises `RuntimeError`, shown as `deleted`). Holding the
  PyQt wrapper does not keep the C++ object alive.
- **Paint tracking.** For `Paint` events on a `QWidget`, resolve its frame (`_frame_of_widget`; `canvas`
  for the view/viewport) and store `frame id -> monotonic` in a dict. Entries older than the window
  are pruned when formatting.
- Neither field changes the meaning of any existing field; consumers parsing `key=value` pairs are
  unaffected.

## Decisions and tradeoffs

- Strip by captured base, not by hard-coding `main`/`<module>`: those names are generic, and a
  hard-coded rule would also hide a genuine direct call.
- `ev` lists receivers by class name only (no characters, no text), consistent with the log being
  agent-readable.
- Overhead is paid only while enabled; the filter was already installed process-wide. A paint
  frame lookup walks a short parent chain per paint event.
- Not a fix for the underlying bug and not a base-rate measurement: `painted=` shows what repainted
  before a flip, not how often the same repaint happens without one. Comparing against ordinary
  entries needs a longer capture; noted in the investigation.

## Not in scope

Agent-facing docs for the log (TODO `9e74c40`), changing what focus does, a fix for the flips.

## Verification

Extend `verify_focus_logger.py` (headless, real `WorkspaceView`): a stack made only of loop-entry
frames reports `native`; a programmatic `setFocus` from a different line still shows its caller;
`ev=` names the event that preceded a focus change (a posted/timer-driven one vs a key press);
`painted=` names a frame that was repainted, and is omitted when none was; the old fields are
unchanged; disabling clears the state and detaches nothing new. Run the existing `verify_focus_logger*.py`
scripts. A real-app check against the actual bug needs the user's setup and is not possible here.

## Status: COMPLETED 2026-10-16

Implemented as planned. Deviations/notes:
- `ev=` uses an allowlist of driver events instead of a noise denylist: the first probe showed
  palette/font changes from widget creation filling the list.
- The loop base is compared by `(code, line)`; `tests/verify/verify_focus_logger_cause.py` therefore
  pumps every step through one `processEvents()` line. A direct `setFocus()` in `main` before the
  loop starts, or from the exact line that enters the loop, would read `native` (documented in
  LEARNINGS).
- Fixed a latent `ValueError` from `sys._getframe(2)` when a slot runs with no Python frame beneath it.
- Verified headlessly: `verify_focus_logger_cause.py` (14 checks) plus the existing
  `verify_focus_logger.py`, `verify_focus_logger_widget.py`, `verify_widget_focus.py` and
  `verify_trap_widget_tab_focus.py`. Not exercised against the real bug (needs the user's setup),
  and the added overhead of the per-event ring append in the app-level filter is unmeasured.
