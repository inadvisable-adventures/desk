# `qt_controls/` package and a clean `PaintedComboBox` (COMPLETED)

TODO 5303de6, from `../FEEDBACK/FEEDBACK-DESK-painted-combo-popup-coordinate-origin-bug-2026-10-16-1730.md`
and `...-painted-combo-crash-and-enforcement-gap-2026-10-16-1836.md`. The investigation (TODOs 0f2c458,
7bc07a8, ff0628a) lives on branch `investigations/combo-box-misplacement`, kept intact as the record.

## Summary
Create `src/desk/shell/qt_controls/` as the home for Qt controls that replace native widgets that misbehave
embedded in the Workspace Canvas, move `painted_branches.py` into it, and land a minimal `PaintedComboBox`
(the branch's end state minus its guesses), used by the Claude (Desk) widget.

## Affected files
`src/desk/shell/qt_controls/{__init__,painted_branches,painted_combo}.py`, `widgets/claude_desk/widget.py`,
`widgets/project_files/widget.py`, `widgets/markdown/widget.py`, `tests/verify/verify_painted_combo.py`,
`tests/verify/verify_markdown_painted_arrows.py`, `LEARNINGS.md`, `TODO.md`.

## Approach
1. `git mv` painted_branches into the package, update importers; package docstring states the house rule.
   `zoom_control.py` stays put.
2. `painted_combo.py`: painted frame/text/arrow; popup via proxy -> scene -> view rect; keep `parent=None`
   (never parent a `Qt.Popup` to the alien `WidgetFrame`), synchronous emit in the popup plus
   `deferred(...)` on the control's connection, wheel ignored, close-on-drift. Dropped
   `_settle_initial_position` and all diagnostics.
3. Fresh verify script (API, placement at three zooms, no parent, real click, drift close, no false
   positive, item pick).
4. One concise LEARNINGS entry instead of the branch's chronology.

## Key decisions
- `_settle_initial_position` dropped as an offscreen-only artifact, per the feedback. The branch's live
  confirmation had been with it present; confirmed live by the user on 2026-10-16 that it works without it.
- Headless can't verify OS window placement (offscreen adds a 2px offset; tolerance 3px).

## Verification
- Headless: `verify_painted_combo.py`, Markdown arrows, Claude (Desk) scripts.
- Real (non-offscreen, cocoa) one-off script from the agent's shell, scratchpad only, not checked in
  (parked: "real-GUI verify script"): clicked each combo through a `QGraphicsView`-embedded `WidgetFrame`
  at zoom 1.0/0.6/0.35, painted the popup magenta, `QScreen.grabWindow(0)`, measured: delta (0,0) every time
  without the settle code. Caveat: the same harness with the popup parented to the frame (the old bug) did
  NOT show an offset, so it does not reproduce the original bug; the user's live check in Desk is still the
  decisive one.

## Status
Confirmed live in Desk by the user, 2026-10-16.
