# Seed a self-contained scripts/todo_item_ids.py (+ broaden .gitignore) on new-Desk creation (COMPLETED)

TODO `c458012`.

## Summary

`development-process.md`'s "Item IDs" section documents running
`python3 scripts/todo_item_ids.py new "<description>"` to generate a
new TODO item's permanent id. That script currently only works when
the current working directory both (a) actually has `scripts/
todo_item_ids.py` at that exact relative path, and (b) can import
`desk.todo_ids` -- which means having this specific app's own `desk`
package installed/importable, since that's where `make_item_id`
actually lives (`src/desk/todo_ids.py`). Neither holds for a brand-new
project Desk created via "New Desk…": TODO `fbd0554` already added an
option to copy `development-process.md` itself into a new Desk's
directory, but never the tool that document tells you to run --
copying just the `.md` file leaves its own documented workflow broken
in the very place it just got seeded into.

## Fix

Two parts, tied to the same "copy development process" decision TODO
`fbd0554` already added to the New Desk dialog:

**1. Make `scripts/todo_item_ids.py` itself self-contained.** It's
meant to be copied verbatim into arbitrary other projects (mirroring
`development-process.md`'s own "plain file copy, not a template
/generator" precedent) -- so it can no longer depend on importing the
`desk` package, which won't exist in an arbitrary destination project.
Inlines `make_item_id`'s ~6-line body (just `hashlib`/`secrets`,
already stdlib-only) directly into the script instead of `from
desk.todo_ids import make_item_id`, with a comment explaining the
duplication is deliberate. `src/desk/todo_ids.py` (still used directly
by `widgets/todo/widget.py`, which always runs with the `desk` package
available) gets its own docstring updated to stop claiming the script
imports it.

**2. Seed it into a new Desk's directory, alongside development
-process.md**, via a new `DeskWindow._seed_todo_item_ids_script
(directory)`, mirroring `_seed_development_process`'s exact shape:
source = `self.current_desk.directory / "scripts" / "todo_item_ids.py"`,
destination = `directory / "scripts" / "todo_item_ids.py"` -- a no-op
if the current Desk has no script of its own to source from, or if the
destination already has one (never silently overwritten, same posture
as the `.md` file). Unlike the `.md` copy, this one also needs to
`mkdir(parents=True)` the destination's `scripts/` directory (which
won't exist yet in a brand-new project) and set the copied file's mode
to executable (`0o755`) -- explicit, not copied from the source file's
own mode bits, since umask/source-filesystem quirks shouldn't leak into
the destination.

Called from `new_desk()` right after the existing `_seed_development_
process(directory)` call, under the same `if copy_development_process:`
guard -- one "bring my dev-process tooling along" decision, not two
near-identical checkbox questions. `NewDeskDialog`'s checkbox label
gets a short parenthetical mentioning the script, so the user knows
what "copy development-process.md" actually brings along; the checkbox
itself stays gated on `development-process.md`'s own presence (same as
today) since the script only makes sense alongside the process doc
that references it -- there's no case where you'd want the script but
not the doc it implements a section of.

**3. Broaden `.gitignore` provisioning to also cover `**/__pycache__/`**,
not just `.desk_temp/`. Directly relevant here: running the just-seeded
`scripts/todo_item_ids.py` (`python3 scripts/todo_item_ids.py new
"..."`) produces `scripts/__pycache__/` the first time it's run, and a
brand-new project's `.gitignore` (freshly created by this same
provisioning step, or not yet covering this) wouldn't otherwise catch
it. `src/desk/temp_ui.py`'s `ensure_gitignore_entry`/`GITIGNORE_ENTRY`
generalize to `GITIGNORE_ENTRIES = (".desk_temp/", "**/__pycache__/")`,
adding whichever of the two aren't already present (independently --
an existing project that already has `.desk_temp/` ignored but not
`__pycache__/` gets just the missing one appended next time
`provision()` runs, not a duplicate). Same re-check-immediately-before
-write behavior as today (TODO `4716585`) is preserved for the combined
check.

## Key decisions

- **Root-caused, not special-cased**: rather than writing a "generate
  a portable copy of the script for seeding" step that diverges from
  the actual `scripts/todo_item_ids.py` used in this repo, the *real*
  script is made portable directly -- so the file that gets copied
  verbatim into a new project is byte-identical to (and never drifts
  from) the one this repo itself uses and tests.
- **Tied to the existing checkbox, not a new one**: the script only has
  meaning in the context of the process doc it implements a section
  of -- no realistic case wants one without the other, so a second
  checkbox would just be another question with an always-the-same
  answer.
- **`.gitignore` broadening scoped to what this change actually
  produces** (`__pycache__/`, from running the seeded script) rather
  than also importing this repo's entire top-level `.gitignore` (
  `.venv/`, `build/`, `node_modules/`, etc.) into every new project --
  those aren't things *this* change causes, and copying them
  unconditionally would be well past what was asked.

## Affected files

- `scripts/todo_item_ids.py` -- inline `make_item_id`, drop the
  `desk.todo_ids` import.
- `src/desk/todo_ids.py` -- docstring update (no longer claims the
  script imports it).
- `src/desk/shell/window.py` -- new `_seed_todo_item_ids_script`,
  called from `new_desk()` alongside `_seed_development_process`.
- `src/desk/shell/new_desk_dialog.py` -- checkbox label mentions the
  script.
- `src/desk/temp_ui.py` -- `GITIGNORE_ENTRY` -> `GITIGNORE_ENTRIES`
  (tuple), `_has_entry`/`ensure_gitignore_entry` generalized to check
  /append multiple entries independently.
- `design-docs/widget-ux.md` -- New Desk section update.

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication`, no mocks
beyond the existing unbound-method-on-a-fake-double pattern already
used for `DeskWindow`-dependent logic in this session's other new
-Desk-flow tests):

- `scripts/todo_item_ids.py` runs standalone (subprocess, plain
  `python3`, no `PYTHONPATH`/venv activation) from a temp directory
  with only that one file present, confirming it truly has no `desk`
  package dependency left -- `new "<description>"` prints a 7-hex-digit
  id matching `desk.todo_ids.make_item_id`'s own output for the same
  input (the two copies must agree, not just both "work").
- `_seed_todo_item_ids_script`: copies real content + sets it
  executable when the current Desk's directory has the script and the
  destination doesn't (including creating the destination's `scripts/`
  directory from nothing); no-ops when the current Desk has none, when
  the destination already has its own (content untouched), and when
  source/destination resolve to the same path.
- `ensure_gitignore_entry`/`GITIGNORE_ENTRIES`: fresh `.gitignore` gets
  both entries; a file with only `.desk_temp/` already present gets
  just `**/__pycache__/` appended (not a duplicate `.desk_temp/`); a
  file with both already present is left untouched (`ask` never
  called); the existing concurrent-write re-check behavior still holds
  for the combined check.
- Full scratchpad regression suite re-run, including updating
  `verify_new_desk_flow.py`'s `GITIGNORE_ENTRY`-based assertions to the
  new `GITIGNORE_ENTRIES` shape (a real behavior change, not a stale
  reference -- updated to match, not left broken).

## Status

Implemented exactly as planned:

- `scripts/todo_item_ids.py`: `make_item_id` inlined (own `ID_LENGTH`
  /`SHORT_DESCRIPTION_THRESHOLD` constants, `hashlib`/`secrets`
  imports), `from desk.todo_ids import make_item_id` removed, module
  docstring updated. `src/desk/todo_ids.py`'s own docstring updated to
  match (no longer claims the script imports it).
- `DeskWindow._seed_todo_item_ids_script` added, called from
  `new_desk()` right after `_seed_development_process`, same
  `if copy_development_process:` guard.
- `NewDeskDialog`'s dev-process checkbox label mentions the script.
- `src/desk/temp_ui.py`: `GITIGNORE_ENTRY` -> `GITIGNORE_ENTRIES =
  (".desk_temp/", "**/__pycache__/")`; `_has_entry` ->
  `_missing_entries` (checks/appends each entry independently);
  `ensure_gitignore_entry` writes whichever are missing as one block
  under one comment, same re-check-immediately-before-write behavior
  as before.
- `design-docs/widget-ux.md`'s New Desk section updated.

Verified headlessly (`QT_QPA_PLATFORM=offscreen`, real `QApplication`,
unbound-method-on-a-fake-double pattern for `DeskWindow`-dependent
logic, matching this session's other new-Desk-flow tests):
`_seed_todo_item_ids_script` copies + sets 0o755 when source exists
and destination doesn't (creating `scripts/` from nothing); no-ops
when there's no source, when the destination already has its own
(content untouched), and when source/destination are the same
directory. `ensure_gitignore_entry`/`GITIGNORE_ENTRIES`: a fresh file
gets both entries under one comment block; a file with only
`.desk_temp/` already present gets just `**/__pycache__/` appended
(not a duplicate `.desk_temp/`); a file with both already present is
untouched and `ask()` is never called; the concurrent-write re-check
still holds for the combined check.

Most direct proof of the actual fix: the real `scripts/
todo_item_ids.py` has no `import desk`/`from desk` anywhere in it
(static check, not just "it happened to run" -- this project's own
venv has `desk` installed editable regardless of `PYTHONPATH`, so a
subprocess run alone wouldn't have proven independence), and, copied
into an empty temp directory and run with a bare `/usr/bin/env
python3` (not this repo's venv), `new "<description>"` prints an id
that matches `desk.todo_ids.make_item_id`'s own output for the same
input -- the two independent copies agree. Manually re-ran `scripts/
todo_item_ids.py convert TODO.md` against a scratch file with a bare
system `python3` (no venv, no `PYTHONPATH`) to confirm the `convert`
subcommand (unrelated to `make_item_id` inlining beyond sharing the
one function) still works standalone too.

Re-ran the full scratchpad regression suite, including updating
`verify_new_desk_flow.py`'s `GITIGNORE_ENTRY`-based exact-text
assertions to the new `GITIGNORE_ENTRIES` shape (its own gitignore
-block/provision tests, not a new script). Three pre-existing failures
found, all unrelated to this change (a crash-log-directory test, a
`switch_desk` fake test double missing a `provisioning` kwarg added by
later work, and a stale reference to the since-renamed `markdown_ex`
directory) -- same three flagged in TODO 02eda20's plan, left as-is
for the same reason (out of scope, pre-existing, not touching any file
edited here).

No `LEARNINGS.md` entry -- nothing here violated a reasonable
assumption or took real investigation to root-cause; it's a
straightforward "the tool this doc tells you to run wasn't actually
along for the ride" gap, closed the same way TODO fbd0554 already
established for the doc itself.
