# Desk picker: add "New Desk" and "Rename current Desk" actions (COMPLETED)

TODO `cbeda83`.

## Summary

"Make the Desk picker a little more substantial, including a way to make
a new desk and a way to rename the current desk." Today the name-chip
popup (`_DeskListPopup`) only lists MRU desks plus a trailing `"…"`
browse entry. Add two action rows to that same popup — **New Desk…**
and **Rename current Desk…** — wired through `DeskPicker`'s existing
"dumb component" signal pattern to `DeskWindow`, which owns the actual
state and does the work.

## Design

### `_DeskListPopup` / `DeskPicker` (`src/desk/shell/desk_picker.py`)

- Keep the existing MRU rows (each carrying its `Path` in `PATH_ROLE`).
- Introduce an `ACTION_ROLE` for non-navigation rows and route the
  trailing rows through it: `"browse"` (the existing `"…"` entry, now
  relabelled to read clearly alongside the new actions), `"new"`, and
  `"rename"`. MRU rows have `ACTION_ROLE == None`.
- Add two new signals on both `_DeskListPopup` and `DeskPicker`:
  `new_desk_requested()` and `rename_requested()`. `DeskPicker`
  re-emits the popup's signals exactly as it already does for
  `desk_chosen`/`browse_requested`.
- `_activate_item` keeps the TODO `c8f6fb3` "close before emit, never
  touch `self` after" ordering: read the row's role/path, `self.close()`,
  then emit the one matching signal (an MRU path → `desk_chosen`;
  `"browse"` → `browse_requested`; `"new"` → `new_desk_requested`;
  `"rename"` → `rename_requested`).
- The action rows get a faint visual distinction from MRU desk rows (a
  muted/italic style via a per-row foreground role or font) so the
  popup reads as "recent desks, then actions", not one flat list.

### `DeskWindow` (`src/desk/shell/window.py`)

- Connect the two new picker signals to `_on_new_desk_requested` /
  `_on_rename_requested`.
- New injectable `_prompt_fn(title, label, default="") -> Callable[[],
  str | None]`, mirroring the existing `_confirm_fn` pattern (returns a
  zero-arg callable so headless tests can substitute a canned answer
  instead of driving a real modal `QInputDialog`). Returns the entered
  text, or `None` if cancelled.
- New injectable `_warn(title, message)` method (a thin
  `QMessageBox.warning` wrapper, class-level-patchable in headless tests
  the same way `_confirm_fn` is) for the name-collision error path.
- New public, directly-testable methods (the dialogs live only in the
  `_on_*_requested` handlers, so tests call these with a ready name):
  - `new_desk(name)`: strip the name; build `path = current_desk
    .directory / (name + DESK_SUFFIX)`; if it already exists, `_warn`
    and abort; otherwise `switch_desk(path, confirm=lambda: True)` (which
    already handles a non-existent path by creating a fresh `Desk`,
    saves the outgoing desk, clears/loads widgets, updates MRU,
    refreshes the picker, and re-provisions temp-UI) followed by an
    explicit `save_current_desk()` so the new desk is persisted to disk
    immediately rather than only on the next transition. No "Switch to
    X?" confirm here — naming the new desk *is* the intent. Note: a
    brand-new desk is not blank — like any widget-less Desk it gets the
    documented fresh-desk demo layout (one instance of every discovered
    widget; see `architecture.md`). `new_desk` deliberately does *not*
    special-case this to an empty canvas, so it stays consistent with
    browsing to a not-yet-existing `.desk` path.
  - `rename_current_desk(new_name)`: strip; build `new_path` in the same
    directory; no-op if unchanged; if `new_path` exists, `_warn` and
    abort; else `save_current_desk()` (ensures the `.desk` file exists
    on disk), `old_path.rename(new_path)`, rebuild `self.current_desk`
    as the same state at `new_path`, `add_to_mru(new_path)` (whose own
    `load_mru()` drops the now-nonexistent old path automatically, since
    it filters `is_file()`), and `_refresh_picker()`. Directory is
    unchanged, so no temp-UI re-provisioning is needed.

Renaming a desk is renaming its `.desk` file, since a Desk's `name` is
just `path.stem` (see `desks.py`) — there's no separate stored name to
update.

## Affected files

- `src/desk/shell/desk_picker.py` — `_DeskListPopup`, `DeskPicker`.
- `src/desk/shell/window.py` — signal wiring, `_prompt_fn`, `_warn`,
  `new_desk`, `rename_current_desk`, `_on_new_desk_requested`,
  `_on_rename_requested`.
- `design-docs/widget-ux.md` — update the Desk Picker section to
  document the two new popup actions and signals.

## Verification

All headless (no browser involved):
- `_DeskListPopup`: constructing it and driving `_activate_item` on each
  row type emits exactly the right signal (MRU path → `desk_chosen`
  with that path; the three action rows → their respective signals) and
  closes first (per the c8f6fb3 ordering) — exercised by calling the
  method directly / emitting the list's signals, not via `.show()`
  +`processEvents()` (see LEARNINGS.md on Popup self-destruction under
  headless event pumping).
- `DeskWindow.new_desk` against a real temp directory: creates a new
  `.desk` file on disk, makes it current, gives it the standard
  fresh-desk demo layout (one of every widget, per the documented
  behavior — not a special empty case), adds it to the MRU, and saves
  the previously-open desk first. Collision case (`new_desk` with an
  existing name) calls `_warn` and does not switch.
- `DeskWindow.rename_current_desk`: renames the on-disk `.desk` file,
  updates `current_desk.path`/`name`, preserves widgets/pan/scale,
  updates the MRU (old path gone, new path present), and leaves the
  directory (and thus `.desk_temp`) untouched. No-op when the name is
  unchanged; collision case `_warn`s and does not rename.
- A full-app `DeskWindow` regression: place a widget, rename the desk,
  and confirm the widget/layout survive the rename (state preserved,
  file moved).

## Status

**Completed.** Implemented and verified headlessly as described above.
One correction surfaced during verification and is reflected in the
plan: a brand-new Desk is *not* an empty canvas — per
`architecture.md`'s documented behavior, any widget-less Desk gets the
fresh-desk demo layout (one of every widget), and `new_desk`
deliberately keeps that behavior for consistency with browsing to a
not-yet-existing `.desk` path (rather than special-casing an empty
canvas). `design-docs/widget-ux.md`'s Desk Picker section updated to
document the two new actions/signals.
