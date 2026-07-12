# New-Desk creation: pick both title and directory (COMPLETED)

TODO `4c3fe4b`.

## Summary

"When creating a new .desk, the user should pick both the title and
the initial associated directory, although the picker for the
directory should default to the current desk's associated directory."

Checked: today `_on_new_desk_requested` only prompts for a name
(`_prompt_fn`), and `new_desk(name)` always creates the new file inside
`self.current_desk.directory` — no directory picker at all. Add a
second step, a `QFileDialog.getExistingDirectory` prompt (same call
this window already makes for `_on_directory_change_requested`,
defaulting the same way), and thread the chosen directory through
`new_desk` instead of it assuming "same as current."

## Key decisions

- **`new_desk(name, directory)` takes the directory explicitly now**
  (was `new_desk(name)`, implicitly `self.current_desk.directory`) --
  its only call site, `_on_new_desk_requested`, is updated to match.
  `Desk.directory` is already just `self.path.parent`
  (`desk.desks.Desk`), so passing a different directory through to the
  constructed `path` is the entire fix -- no other code assumes "same
  directory as the current Desk."
- **Directory prompt after the name prompt, both cancellable
  independently** -- cancelling either step (empty/cancelled name,
  cancelled directory dialog) aborts the whole flow with no Desk
  created, matching the existing behavior for a cancelled name prompt
  today.
- **Plain, direct `QFileDialog.getExistingDirectory` call, not routed
  through an injectable `_prompt_fn`-style wrapper** -- matches
  `_on_directory_change_requested`'s own existing, already-precedented
  style (a real file-picker dialog isn't meaningfully fakeable/testable
  headlessly the way a canned text-prompt answer is, and this codebase
  doesn't currently pretend otherwise for the other existing directory
  -picker call site either). `new_desk()` itself stays a plain method
  taking an explicit `Path`, so it's fully testable without touching
  any dialog at all -- same shape as every other headlessly-verified
  `DeskWindow` method in this codebase.
- **Default directory is the *current* Desk's directory**, per the
  TODO's own explicit wording -- not the new Desk's *name* location or
  any other guess.
- **Out of scope, left for their own separate TODO items**: seeding a
  `development-process.md` into the new directory (TODO fbd0554) and
  not placing every discovered widget by default (TODO cb2790d) --both
  touch this same flow but are independently scoped asks; this item is
  specifically the directory-picker gap.

## Affected files

- `src/desk/shell/window.py` -- `new_desk`'s signature and body;
  `_on_new_desk_requested` gains the directory-picker step.

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication`, no mocks) --
`new_desk(name, directory)` exercised directly against a real,
constructed `DeskWindow`-equivalent (or its own unbound logic, matching
this codebase's existing verification style for `DeskWindow` methods
that don't need a full window):

- Creating a new Desk in a directory *different* from the current
  Desk's directory: confirm the resulting `.desk` file actually lands
  in the chosen directory, not the current Desk's.
  `current_context.get_current_desk_directory()` reflects the new
  directory afterward (via the existing `_refresh_picker` call inside
  `switch_desk`).
- A name that already exists as a `.desk` file *in the chosen
  directory* is rejected (existing warn-and-abort behavior), even if no
  file of that name exists in the *current* Desk's directory -- confirms
  the existence check moved to the right directory, not left checking
  the old one.
- An empty/whitespace-only name still aborts with no Desk created
  (existing behavior, unchanged).

## Status

Implemented as planned: `new_desk` now takes `directory: Path`
explicitly; `_on_new_desk_requested` adds the `QFileDialog
.getExistingDirectory` step, defaulting to `self.current_desk.directory`.

Verification note: constructing a real `DeskWindow` is a known,
pre-existing stall in this headless environment (already noted and
skipped in several earlier plans this session -- 578cb6b, cee6f74,
a053e3a). Rather than skip verification of this method entirely,
exercised the real, unmodified `DeskWindow.new_desk` bound onto a
lightweight double for the surrounding window (faking only
`switch_desk`/`save_current_desk` with the minimal *real* behavior
`new_desk` depends on, via the actual standalone `desk.desks`
functions, not reimplemented logic). All steps passed: a new Desk
lands in the chosen directory, not the current one; an existing-name
collision check applies to the *chosen* directory, not the current
one; an empty name still aborts.

No `LEARNINGS.md` entry needed for the offscreen-`DeskWindow`-stall
workaround itself -- it's already an established, previously-noted
limitation, not a new finding.
