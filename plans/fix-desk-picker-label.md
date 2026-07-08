# Fix Desk picker's collapsed-state label (COMPLETED)

## Summary

Two confirmed, distinct bugs in `DeskPicker`:

1. **Stale outer geometry clips the label.** `DeskPicker.__init__` calls
   `_set_expanded(False)` — which calls `self.adjustSize()` — while
   `_label` still has no text (empty `QLabel`), locking the picker's
   outer bounds to a near-zero width. `set_current(name)` later sets the
   label's actual text but never re-triggers a resize of the *container*,
   so the label's real content (e.g. `"default"`, `sizeHint()` reporting
   65px wide) is clipped down to whatever the stale ~24px outer bounds
   still allow — confirmed directly (`picker.geometry()` stays `(0, 0,
   24, 30)` from construction all the way through `set_current`). This
   explains the reported "briefly shows [wrong/truncated content] instead
   of the current Desk's name" on startup.
2. **The dropdown falls back to the wrong entry when the current desk
   isn't in the MRU list yet.** `set_mru(entries, current)` only selects
   `current` in the dropdown if it finds a matching entry already in
   `entries` — but on a Desk's first open, nothing has called
   `add_to_mru()` for it yet (that only happens in `save_current_desk`/
   `switch_desk`), so no match is found and Qt's default combo-box
   selection (the first added item) is shown instead. Confirmed directly:
   feeding a `current` path not present in `entries` leaves
   `dropdown.currentText()` showing the *first* MRU entry instead.
   Explains "on hover it switches to showing ['default', the user's
   -observed first-MRU-entry] ... instead of the actual current Desk
   name."

Both bugs share the same underlying category (the picker's displayed
state not correctly reflecting its actual current-desk state at some
point in its lifecycle) but are separate, independently-fixable issues.

## Affected files

- `src/desk/shell/desk_picker.py` (edit) — both fixes.

## Design

### Fix 1: resize whenever displayed content changes, not just on expand/collapse

Call `self.adjustSize()` at the end of `set_current()` too (not just
inside `_set_expanded`), so the container's outer bounds are recomputed
immediately whenever the label's actual text changes. Also call it at the
end of `set_mru()`, for the same reason on the expanded (dropdown) side —
the container's ideal width can change once the dropdown's content is
populated, and nothing currently accounts for that either.

### Fix 2: the dropdown must always be able to select the current desk

`set_mru(entries, current)` ensures `current` is represented before
building the dropdown: if it's not already in `entries`, insert it at the
front. This makes "the dropdown's current selection matches the actually
-open desk" an invariant that holds regardless of whether the persisted
MRU list has caught up yet — semantically correct regardless of the
`recent_desks.json` file's own state, since the currently-open desk is
definitionally the most recently used one.

## Verification

Entirely headless:

1. Confirm `set_current("default")` (a name whose `sizeHint()` needs more
   width than the picker's just-constructed, empty-label bounds) results
   in the label's *actual displayed width* (via its geometry, not just
   its `.text()` property — the original bug was specifically about
   clipped rendering, not wrong data) being wide enough for its
   `sizeHint()`, not the stale construction-time size.
2. Confirm `set_mru(entries, current)` selects `current` correctly both
   when it's already present in `entries` (regression) and when it's not
   (the bug case) — `dropdown.currentData() == current` in both cases.
3. Regression: confirm the collapsed/expanded visibility toggle
   (`enterEvent`/`leaveEvent` → `_set_expanded`) still works correctly.

## Key design decisions / tradeoffs

- **Resize on every content change, not just on expand/collapse.** The
  root cause of bug 1 is specifically that a resize-worthy event
  (content changing) wasn't triggering a resize — the fix is to make
  every content-changing method respect that, rather than special
  -casing just the one call site that happened to be reported.
- **Insert the current desk into the MRU dropdown if missing, rather than
  falling back to "no selection is fine."** A dropdown with no visibly
  -correct selection at all would be worse than showing a slightly
  -unusual state (the current desk listed even though it's not yet
  "recently used" in the persisted sense) — the dropdown's whole purpose
  is to reflect what's currently open, which this guarantees.

## Status

Implemented and verified, entirely headlessly:

1. Confirmed `set_current("default")` now resizes the picker's outer
   bounds to fit the label's real `sizeHint()`, rather than staying
   clipped to the empty-label construction-time size.
2. Confirmed `set_mru` selects the current desk correctly both when
   already present in `entries` (regression) and when absent (the bug
   case) — `dropdown.currentData()`/`currentText()` both correct in
   either case.
3. Regression: confirmed `_set_expanded` (the enter/leave-driven collapse/
   expand toggle) still correctly shows/hides the label vs.
   dropdown+button.
4. Full-app: constructed a real `DeskWindow` around a fresh, never
   -before-saved desk named "default" (the exact originally-reported
   scenario) and confirmed both fixes hold there too — the label isn't
   clipped, and the dropdown correctly shows the actual current desk
   rather than falling back to a stale/different MRU entry.
