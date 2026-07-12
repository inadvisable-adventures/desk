# MRU file-existence checking

TODO `8f5568f`.

## Summary

Two gaps, both already scoped out precisely in the TODO's own text
(written when the item was added):

1. `desk.recent_desks.load_mru()` already filters missing files out of
   what it *returns*, but never persists that removal back to
   `~/.desk/recent_desks.json` -- a stale entry just gets silently
   re-filtered forever instead of actually being cleaned up.
2. Clicking an MRU entry whose file has since vanished currently falls
   through to `DeskWindow.switch_desk`'s existing "path doesn't exist"
   handling (`Desk(path=path)`), which silently creates a brand-new,
   *empty* Desk at that now-nonexistent path -- no warning at all, and
   the user has no way to tell their real Desk just got clobbered by
   an empty stand-in until they notice its widgets are all gone.

## Key decisions

- **New `desk.recent_desks.prune_missing_mru_entries()`**, alongside
  (not replacing) the existing `load_mru()`: both share a new private
  `_load_raw_mru()` helper for the actual JSON read, but only the
  pruning variant re-`_save_mru()`s when something was actually
  removed. `load_mru()` itself stays a plain, side-effect-free read
  (still used internally by `add_to_mru`, which already re-saves the
  *entire* updated list unconditionally right after -- no reason for
  it to also independently persist a prune). `_refresh_picker` (the
  "MRU is shown" moment) switches to the pruning variant.
- **The click-time check happens in `DeskWindow._on_desk_chosen`**,
  before `switch_desk` is ever called -- `switch_desk` itself is used
  by more than just the MRU click path (the desk-picker "browse"
  dialog also ends up there, deliberately still using its own already
  -existing-file assumption, since `QFileDialog.getOpenFileName` can't
  itself return a path that stopped existing between the dialog
  closing and this line running in any realistic window), so the new
  guard sits at the MRU-specific entry point, not inside `switch_desk`
  itself.
- **Warning dialog with selectable path text**: a new
  `_warn_with_selectable_text` (distinct from the existing `_warn`,
  which uses `QMessageBox.warning`'s static convenience method --
  its text isn't selectable, and changing that helper's behavior for
  every other caller isn't wanted) constructs a `QMessageBox` directly
  and sets `Qt.TextInteractionFlag.TextSelectableByMouse` -- the
  explicit, TODO-specified exception to `CLAUDE.md`'s general
  "labels shouldn't be user-selectable" rule ("unless specifically
  requested").
- **Also prunes the now-confirmed-stale entry immediately** on a
  missing-file click (via `self._refresh_picker()` right after the
  warning) rather than waiting for the *next* time the picker happens
  to be shown -- a small, natural consequence of already knowing the
  entry is stale at that exact moment, not a separate feature.

## Affected files

- `src/desk/recent_desks.py` -- `_load_raw_mru()`,
  `prune_missing_mru_entries()`.
- `src/desk/shell/window.py` -- `_refresh_picker` uses
  `prune_missing_mru_entries()` instead of `load_mru()`;
  `_on_desk_chosen` gains the existence check + warning + re-prune;
  new `_warn_with_selectable_text`.

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication`, real JSON
files in a temp `~/.desk`-equivalent directory):

- `prune_missing_mru_entries()`: a persisted list with one missing
  path returns only the still-existing ones *and* rewrites the JSON
  file to match; a list with nothing missing doesn't rewrite the file
  at all (mtime unchanged) -- confirms it isn't a blind always-write.
- `load_mru()` is unaffected (still a pure read, no side effects) --
  regression-checked directly.
- `DeskWindow._on_desk_chosen` (unbound method on a fake double, the
  established pattern for `DeskWindow`-dependent logic): a path that
  still exists calls `switch_desk`; a path that no longer exists calls
  the selectable-text warning instead, never calls `switch_desk`, and
  triggers a picker refresh.

## Status

Not yet implemented.
