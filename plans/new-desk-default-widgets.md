# New-Desk default widget seeding

TODO `cb2790d`.

## Summary

A brand-new Desk currently gets *every* discovered widget placed side
by side (`_load_desk_widgets`'s "no saved widgets" fallback) -- a
leftover bootstrapping default, not a meaningful onboarding experience.
Instead: open a Markdown viewer on the project's `README.md` if one
exists, else seed a Scratch widget with a minimal starter template.

## Key decisions

- **Same fallback branch, new behavior** -- `_load_desk_widgets`'s
  `else` (no saved `desk.widgets`) is reached both by a genuinely new
  Desk (`new_desk` -> `switch_desk` -> a fresh in-memory `Desk` with no
  widgets) and, in principle, by loading an existing `.desk` file that
  happens to have an empty widget list. There's no meaningful
  distinction to preserve for the latter -- "no saved widgets" *is* "a
  blank Desk" either way, and placing the entire catalog was never a
  deliberate feature worth keeping for that case. So this changes the
  one shared branch rather than threading a new "is this fresh"
  parameter through `switch_desk`/`_load_desk_widgets`.
- **README.md check is a plain `is_file()`, case-sensitive, exact
  name** -- matches how every other well-known-filename convention in
  this codebase already works (`TODO_FILENAME`, `QUESTIONS_FILENAME`,
  `DEVELOPMENT_PROCESS_FILENAME`): a fixed, exact name, not a
  case-insensitive or `README`/`README.txt`-tolerant search. If that
  turns out to be too narrow later, broadening it is a small, separate
  change.
- **Markdown path**: opened via the existing `open_widget_content` +
  `set_file` two-step (same as the drag-and-drop feature, TODO
  `5915ac2`, and the TODO widget's "open plan" button) -- no new
  opening mechanism.
- **Scratch fallback content**: exactly the template text the TODO
  itself specifies -- `# <desk name> README` then a blank line then
  `## What this project is about or exploring...` -- with the Scratch
  widget's own label set to `<desk name> README` too, via the existing
  `set_label`/`body.setPlainText` API (the same one the TODO widget's
  edit-conflict handling already uses to spawn a labeled Scratch
  instance).
- **Placed at `(0, 0)`**, matching where a single ad hoc widget is
  placed elsewhere in this file (e.g. `_focus_questions_widget`'s
  "open new" fallback uses the current view center instead, but there
  is no "current view" yet for a Desk that's still being constructed
  for the first time here -- `_load_desk_widgets` runs before
  `set_view_state`, so the origin is the only meaningful default).

## Affected files

- `src/desk/shell/window.py` -- `_load_desk_widgets`'s `else` branch
  replaced with a call to a new `_seed_new_desk_widgets(desk)`.

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication`), against
`_seed_new_desk_widgets` run unbound on a fake double (the established
pattern for `DeskWindow`-dependent logic):

- A directory with a real `README.md`: opens the markdown widget id
  and calls `set_file` with that exact path; the Scratch widget id is
  never opened.
- A directory with no `README.md`: opens the scratch widget id, sets
  its label to `"<name> README"`, and its body text to the exact
  two-line/blank-line template with the Desk's own name substituted.
- A directory with neither widget kind available in the catalog (an
  unusual/stripped-down widget set): a no-op, no crash.

## Status

Not yet implemented.
