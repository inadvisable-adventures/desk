# Fix `_capture_desk_state`/friends dropping `Desk.state` (TODO `224fbc9`) (COMPLETED)

## Summary

From `../FEEDBACK/FEEDBACK-DESK-state-store-wiped-by-capture-desk-state-2026-09-12-2100.md`
(`draw-with-desk`): `DeskWindow._capture_desk_state()`
(`src/desk/shell/window.py`) rebuilds a fresh `Desk` from the live
canvas on every save but never carries over `Desk.state` -- the
shared, project-scoped `desk.state.*` store -- so it silently resets
to `{}`. Because `save_current_desk()` does `self.current_desk =
desk` right after, this isn't just a save-time/disk bug: it wipes the
*live*, in-memory store too, for every widget, immediately. Since
`save_current_desk()` runs on removing any widget (any kind), switching
Desks, quitting, installing/uninstalling a job, or editing the file
type registry, **closing any single widget deletes every key any
widget has ever written to `desk.state`, immediately, for the rest of
the running session** -- not just on the next explicit save.

The feedback also found two further, narrower instances of the same
bug class: `get_state_dict()` (Bridge API `workspace.getState`, reads
through `_capture_desk_state` too, so it always lies and reports
`"state": {}`) and `change_current_desk_directory()`, which hand-builds
a `Desk(...)` dropping `state` *and* `custom_widgets`/
`file_type_registry`/`installed_jobs` all at once. Auditing every other
`Desk(...)` construction site in `window.py` while fixing this turned
up a third, previously-unreported instance: `rename_current_desk()`
(`window.py:1999-2005`) has the exact same all-four-fields-dropped
shape as `change_current_desk_directory`.

The feedback's own root-cause section traces *why* this keeps
happening: every one of these functions hand-enumerates which fields
of the current `Desk` to carry over unchanged, so every new `Desk`
field (`file_type_registry`, `installed_jobs`, now `state`) requires
someone to remember to add it to every one of these call sites -- and
it's now failed at three of them. Per the feedback's own suggested
structural fix, this plan replaces the hand-enumeration at all three
sites with `dataclasses.replace(self.current_desk, ...)`, which
carries over every field not explicitly overridden automatically, by
construction -- closing the whole bug class rather than patching the
three currently-known instances of it.

Not in scope: `desk.state` never surviving an actual Desk *restart*
(the feedback's "structural finding" section) is a separate, deeper
claim the feedback itself doesn't fully explain (the round-trip test
`test_desk_persists_state` in `verify_state_store.py` already proves
`save_desk`/`load_desk` handle `state` correctly in isolation) -- once
this fix lands, `_capture_desk_state` will actually pass a real,
non-empty `state` through to `save_desk` on every save, which should
resolve that finding as a side effect (a `.desk` file's `state` was
never non-empty at save time in the first place, precisely because of
this bug). No separate restart-specific fix is needed or planned here;
verification below includes an explicit save-then-`load_desk` round
-trip check to confirm this.

## Affected files

- `src/desk/shell/window.py` -- `_capture_desk_state`,
  `change_current_desk_directory`, `rename_current_desk`, all
  rewritten to build their result via `dataclasses.replace` instead of
  hand-enumerating fields. `from dataclasses import dataclass` becomes
  `from dataclasses import dataclass, replace`.
- `tests/verify/verify_lock_persistence.py` -- `_FakeWindow`'s
  `current_desk` stand-in becomes a real `desk.desks.Desk(...)`
  instance (required for `dataclasses.replace` to work at all -- it
  raises on a non-dataclass argument), instead of the ad hoc
  `type("D", (), {...})()` object it uses today.
- `tests/verify/verify_state_store.py` -- new coverage for the actual
  bug (close-a-widget-then-check-state, `get_state_dict`, a real
  save/reload round-trip) added to the existing "data model round-trip"
  section.

## Implementation approach

1. **`src/desk/shell/window.py` import**: add `replace` to the
   existing `from dataclasses import dataclass` line.

2. **`_capture_desk_state`** (`window.py:1597-1638`): keep building
   `widget_states`/`pan_x`/`pan_y`/`scale` exactly as today, but
   construct the return value as:
   ```python
   return replace(
       self.current_desk,
       widgets=widget_states,
       pan_x=pan_x,
       pan_y=pan_y,
       scale=scale,
   )
   ```
   removing the `path=`/`custom_widgets=`/`file_type_registry=`/
   `installed_jobs=` lines and their carry-over comments entirely (the
   comments' own point -- "these aren't derived from placed widgets,
   carry them over unchanged" -- is now true of every field `replace`
   doesn't touch, by construction, so a per-field comment is no longer
   informative; a single comment above the call explains the pattern
   once).

3. **`change_current_desk_directory`** (`window.py:1912-1927`): replace
   the hand-built `Desk(path=new_path, widgets=..., pan_x=..., pan_y=...,
   scale=...)` with `replace(self.current_desk, path=new_path)` --
   `widgets`/`pan_x`/`pan_y`/`scale` don't actually change here (moving
   directory doesn't move widgets on the canvas), so they don't need
   restating either; only `path` is actually changing.

4. **`rename_current_desk`** (`window.py:1984-2005`): same shape,
   `replace(self.current_desk, path=new_path)`.

5. **`get_state_dict`** (`window.py:1640-1643`): no code change needed
   -- it already reads through `_capture_desk_state()`, so fixing that
   one function fixes this lying-report symptom for free. Verified,
   not assumed (see verification below).

6. **`tests/verify/verify_lock_persistence.py`**: `_FakeWindow
   .__init__`'s `self.current_desk` changes from
   `type("D", (), {"path": ..., "custom_widgets": [], ...})()` to a
   real `Desk(path=Path("/tmp/x.desk"))` (import `desk.desks.Desk`) --
   a real dataclass instance is required for `dataclasses.replace` to
   accept it; this also means the fake no longer needs to hand-list
   every carried-over field itself, matching the same simplification
   the production code just got.

## Verification

`tests/verify/verify_state_store.py`, new tests alongside the existing
`test_desk_persists_state`:

- **`test_capture_desk_state_carries_over_state`**: a `_FakeWindow`
  (same shape as `verify_lock_persistence.py`'s, updated per above)
  whose `current_desk` is a real `Desk(state={"k": StateEntry(value=1,
  edit=None)})`. Call `_capture_desk_state()` and assert the returned
  `Desk.state` still has `"k"` with the same value -- this is the
  exact check the feedback's own reproduction ran by hand; making it
  permanent.
- **`test_close_widget_does_not_wipe_state`**: closer to the real
  end-to-end failure mode than the unit check above -- construct a
  minimal real `DeskWindow`-shaped scenario (or reuse the
  `_FakeWindow` plus a direct call to `save_current_desk`-equivalent
  logic: `win.current_desk = win._capture_desk_state()`) starting from
  a `current_desk` with non-empty `state`, simulate a widget being
  removed (drop one frame from `_FakeView`'s frame list, matching how
  `close_widget`/`close_widget_by_instance_id` call
  `save_current_desk()` after mutating `self.view._frames`), call
  `_capture_desk_state()` again, and assert `state` is still intact
  afterward -- directly closes the "test gap" the feedback calls out.
- **`test_get_state_dict_reflects_live_state`**: same `_FakeWindow`
  with non-empty `state`; call the real `DeskWindow.get_state_dict`
  (unbound, against the fake, same technique
  `verify_state_store.py` already uses for `get_state`/`set_state`)
  and assert the returned dict's `"state"` key is non-empty --
  regression coverage for the `workspace.getState`-always-lies
  symptom.
- **`test_change_directory_and_rename_carry_over_state`**: exercises
  `change_current_desk_directory`/`rename_current_desk` directly
  against a minimal fake/real `DeskWindow`-shaped object with
  non-empty `state` (and non-empty `custom_widgets`/
  `file_type_registry`/`installed_jobs`, to cover the "four fields at
  once" report too) and asserts all four survive.
- **`test_capture_then_save_then_reload_round_trips_state`**: the
  actual end-to-end path the feedback's "structural finding" section
  raises -- build a `_FakeWindow` with non-empty `state`, call
  `_capture_desk_state()`, `save_desk()` the result to a temp path,
  `load_desk()` it back, and assert `state` is non-empty and correct --
  proving a `.desk` file's `state` section is no longer *always* `{}`
  by construction.

Run the full `tests/verify/` suite afterward and confirm no
regressions beyond the pre-existing, unrelated
`verify_eye_button_persists_title_only.py` failure (confirmed already
present on `main` before TODO `b9d3de5`, still expected to be present
here since this change doesn't touch that code path).

## Key decisions

- Structural fix (`dataclasses.replace`) over the feedback's
  "immediate one-line fix" alternative, applied to all three
  `Desk(...)` construction sites in `window.py` (including the
  previously-unreported third one, `rename_current_desk`) -- per the
  feedback's own framing, patching just the reported `state` field
  would leave the identical bug waiting for the next new `Desk` field,
  which has already happened twice.
- No change to `desks.py`/`save_desk`/`load_desk` -- the feedback
  itself confirms that half is already correct
  (`test_desk_persists_state` already covers it).
- The "state has never survived a restart" structural finding is
  treated as a consequence of this same bug (every save previously
  passed a wiped `state` to `save_desk`), not a separate defect to
  design around -- confirmed via the new round-trip verify test rather
  than assumed.
