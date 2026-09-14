# Plan: TODO 1c67fe5 (COMPLETED) — gitignore `desk_widgets/**/.build` in managed projects

## Summary

TODO 13f4ad5 introduced a rebuilt-on-demand `.build/` cache under any
promoted, source-backed custom widget's own `desk_widgets/<name>/`
directory (`desk.custom_widgets.build_from_source`). That cache is
gitignored in Desk's own repo (`**/.build/`, added the same TODO), but
nothing ensured the same for a *project* Desk is managing. This adds
that: a narrower, project-specific `desk_widgets/**/.build/` pattern
(not the more general `**/.build/`, which could plausibly collide with
something unrelated to Desk in someone else's project), ensured (1) at
startup/Desk-switch and (2) right after a widget is promoted — the two
moments `desk_widgets/` can first come to exist.

## Design

Mirrors the existing `ensure_gitignore_entry`/`GITIGNORE_ENTRIES`
mechanism (`src/desk/temp_ui.py`) already used for `.desk_temp/`/
`**/__pycache__/`, but as a separate, conditional function rather than
a third `GITIGNORE_ENTRIES` member: those two are unconditional
(ensured alongside `.desk_temp` provisioning regardless of whether any
custom widget has ever been promoted), while this one only matters --
and only ever prompts -- once `desk_widgets/` actually exists.

- `SOURCE_BUILD_CACHE_DIRNAME` moved from `custom_widgets.py` to
  `temp_ui.py` (which `custom_widgets.py` already imports from) so the
  new gitignore constant/function can reference it without an import
  cycle; re-exported from `custom_widgets.py` unchanged for its own
  existing importers.
- `DESK_WIDGETS_BUILD_GITIGNORE_ENTRY = f"{PROMOTED_WIDGET_SRC_DIRNAME}/**/{SOURCE_BUILD_CACHE_DIRNAME}/"`
  (`"desk_widgets/**/.build/"`).
- `ensure_desk_widgets_gitignore_entry(directory, ask)`: no-ops if
  `directory/desk_widgets` doesn't exist; otherwise resolves
  `find_git_root(directory)` (no-op if not in a git repo) and writes
  the entry to that root's `.gitignore`, with the same
  ask-then-re-check-before-write dance `ensure_gitignore_entry` uses
  (a modal confirm can pump its own nested event loop for an arbitrary
  time; re-verify against a fresh read before writing).
- `desk.shell.window.DeskWindow._provision_temp_ui` calls it
  unconditionally (independent of the `.desk_temp`/`.gitignore`
  confirms already there) after its existing provisioning steps.
- `_on_tempui_promote_requested` calls it right after
  `_relocate_promoted_widget_source`, the step that can create
  `desk_widgets/<name>/` for the first time.

## Verification

New `tests/verify/verify_desk_widgets_build_gitignore.py`: the
constant's exact value; `ensure_desk_widgets_gitignore_entry`'s own
behavior (no `desk_widgets/` -> no-op without asking; not in a git repo
-> no-op; fresh/append/already-present/decline/re-check-before-write
cases, mirroring `verify_new_desk_flow.py`'s existing
`ensure_gitignore_entry` coverage); and `_provision_temp_ui`'s wiring
via a minimal fake window.

Extended `tests/verify/verify_relocate_promoted_widget_source.py` with
a promotion-triggers-the-entry test (needs a real `git init`'d tempdir,
since `find_git_root` shells out for real).

Full `tests/verify/` regression suite: 137 scripts (new
`verify_desk_widgets_build_gitignore.py` plus the pre-existing 136), 0
failures. (A pre-existing, unrelated stale-fixture failure in
`verify_eye_button_persists_title_only.py`, found while first running
the full suite during TODO 13f4ad5, was fixed in the same session --
see that TODO's own plan file.)
