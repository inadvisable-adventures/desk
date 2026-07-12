# Seed development-process.md on new-Desk creation + mention it to claude

TODO `fbd0554`.

## Summary

Two parts:

1. "Add an option during new desk creation to initialize a new desk
   with a development-process.md; the content should be sourced
   initially from Desk's current development-process.md." — a confirm
   prompt in the (TODO 4c3fe4b-just-extended) new-Desk flow, offered
   only when there's actually something to source from and somewhere
   sensible to put it.
2. "if there is a development-process.md for a Desk's project when a
   claude widget is open, add an instruction to read that file to the
   initial instructions given to claude." — `CLAUDE_WIDGET_PROMPT`
   (`widgets/claude/widget.py`) conditionally gains a second sentence.

## Key decisions

- **Seeding is a plain file copy, not a template/generator** — "sourced
  initially from Desk's current development-process.md" means exactly
  that file's current content, copied verbatim, not derived or
  rewritten.
- **Only offered (confirm dialog) when there's something real to copy
  and somewhere real to put it**: the *current* Desk's directory must
  actually have a `development-process.md` (nothing to source from
  otherwise — silently skipped, no dialog, rather than asking a
  pointless question), and the *new* directory must not already have
  one (never silently overwritten — also silently skipped, matching
  this codebase's general "don't clobber existing files" posture, e.g.
  `TempUiManager.provision`'s own `if not doc_path.is_file(): ...
  write_text`). Also correctly a no-op if the chosen new directory
  happens to be the *same* as the current Desk's directory (nothing
  since 4c3fe4b prevents picking it) — source and destination would be
  the same file.
- **New, independently-testable `_seed_development_process(directory)`**
  (plain file I/O + `self.current_desk.directory`, no Qt/dialog
  dependency) separate from the confirm-dialog-driving code in
  `_on_new_desk_requested` — same split this codebase already uses
  elsewhere between a testable core method and its dialog-driving
  `_on_*_requested` wrapper.
- **Claude widget instruction is additive, appended only when the file
  actually exists** — `CLAUDE_WIDGET_PROMPT`'s existing sentence is
  unchanged; a second sentence is appended only if `current_context
  .get_current_desk_directory() / "development-process.md"` exists,
  mirroring `_doc_path()`'s own existing "no current Desk directory
  known yet" fallback shape (in that case, or if the file just doesn't
  exist, nothing is appended at all — not a placeholder/negative
  statement).
- **`"development-process.md"` as a plain per-file literal, not a new
  shared constant** — used in exactly two places, is a fixed, stable
  project-convention filename (not a piece of shared *behavior* the way
  `desk.temp_ui`'s constants are), so a shared constant module would be
  more machinery than the two-line duplication it'd save.

## Affected files

- `src/desk/shell/window.py` -- `_on_new_desk_requested` gains the
  confirm-and-seed step; new `_seed_development_process(directory)`.
- `widgets/claude/widget.py` -- new `_development_process_instruction()`,
  appended to the constructed prompt when non-empty.

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication`, no mocks):

- `_seed_development_process`: copies real content when the current
  Desk's directory has the file and the destination doesn't; no-ops
  (destination left untouched) when the current Desk has none, when
  the destination already has one (confirms it's *not* overwritten,
  content unchanged), and when source/destination resolve to the same
  path.
- `_development_process_instruction`: real file present -> a non-empty
  instruction sentence mentioning its path; absent, or no current Desk
  directory known yet -> empty string, and the overall prompt
  construction is therefore unchanged from before this TODO in that
  case (regression check against the exact pre-existing prompt text).

## Status

Not yet implemented.
