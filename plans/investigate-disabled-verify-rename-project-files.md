# Plan: TODO f3120bb (COMPLETED) — investigate `disabled_verify_rename_project_files.py`

## Investigation

Confirmed: the "no remaining file_explorer/File Explorer content
anywhere" check scoped its grep across `design-docs`, `TODO.md`,
`PARKINGLOT.md`, `LEARNINGS.md`, and `plans` — all places this
project's own established convention deliberately preserves historical
mentions of the old name (TODO.md's own line describing TODO `8385dcc`
necessarily still says "File Explorer"; a rename plan's own prose
narrates the rename by name; forward-looking docs like
`design-docs/svg-viewing-and-editing.md` legitimately say "formerly
File Explorer" when explaining Image Viewer's own history). This
assertion was checking something the project's own conventions don't
actually promise — it was likely unsatisfiable from very early on, not
a regression from any later change.

## Resolution

Fix: scope the "no remaining content" check to `src`/`widgets` only —
actual code, where the old name genuinely shouldn't appear at all
anymore. Drop `design-docs`/`TODO.md`/`PARKINGLOT.md`/`LEARNINGS.md`/
`plans` from that specific grep (the plan-filenames-preserved check
below it already covers the one legitimate exception in `plans/` at
the filename level).

## Verification

Re-run standalone (passes); full `tests/verify/` suite: disabled count
drops to 3, 0 new failures.
