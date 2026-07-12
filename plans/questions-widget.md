# Questions widget

TODO `7a086ba`.

## Summary

A new widget, `widgets/questions/`, that reads and manages QUESTIONS.md
similarly to how the TODO widget (`widgets/todo/`) manages TODO.md: a
filterable list backed by the real file, git-commit-backed writes, and
live file-watching reload. `a801180` (routing tempui notifications to
this widget) is a separate, later TODO and explicitly out of scope
here.

## QUESTIONS.md's actual shape

Confirmed directly by reading the file as it stands today:

- Starts with a `# Questions with optional answers` title line
  (preamble).
- Each entry is a `## TODO \`<id>\`[/\`<id2>\`...]: <summary>` heading --
  unlike TODO.md's items, an entry can reference **more than one** TODO
  id (e.g. `## TODO \`96013cf\`/\`858752b\`: ...`), so entries need a
  `todo_ids: list[str]` field rather than TodoItem's single `item_id`.
- Then free-form body prose (context + often a bulleted list of
  specific sub-questions).
- Then a `(Answer: ...)` block. Always present, even when unanswered
  (as `(Answer: )`).
- **Confirmed by reading TODO `9743419`'s own answer entry**: an
  answer's text can itself contain nested parentheses (e.g. "option
  (a)", "(which points at an external target file)") before its real
  closing `)`. A naive "first `)` after `(Answer:`" parse truncates
  answers like this one badly -- verified this directly against the
  real file before designing the parser (see below).

## Key decisions

- **New `src/desk/questions_file.py`, mirroring `desk/todo_file.py`'s
  shape** (`QuestionEntry` dataclass, `parse_questions_file`,
  `render_questions_file`), rather than trying to reuse TODO.md's
  parser -- the two formats are structurally different enough (multi
  -id headings, a required trailing answer block) that forcing one
  parser to handle both would be more convoluted than two small,
  purpose-fit ones.
- **Answer extraction uses paren-depth tracking, not a first-`)`
  scan.** `_find_matching_close_paren` walks forward from the `(Answer:`
  block's own opening paren, incrementing on `(` and decrementing on
  `)`, stopping when depth returns to zero -- this is the actual fix
  for the nested-parens case confirmed above. Verified directly against
  this project's real QUESTIONS.md, including a full round-trip
  (parse -> render -> byte-identical to the original file) and a
  splice-and-reparse check (`with_answer` on the `9743419` entry,
  written to a fresh temp file, reparsed, new answer text recovered
  exactly, other entries untouched).
- **`with_answer(entry, new_answer)` returns a new `QuestionEntry`**
  with just the matched `(Answer: ...)` span replaced in `raw_text`,
  leaving the heading/body/surrounding blank lines untouched --
  mirrors TODO.md's items being immutable dataclasses reconstructed on
  edit, not mutated in place.
- **No drag-to-reorder, no debounced-commit machinery.** TODO.md's
  reorder-then-debounce exists because item *position* is itself the
  priority signal -- QUESTIONS.md entries have no equivalent ordering
  -is-priority semantic, so adding drag-reorder would just be
  unused surface area. Each answer submit writes and commits
  immediately (matching TODO widget's `_add_item`/`_edit_item`
  immediate-write path, not its `_on_rows_moved` debounced path).
- **No "Add Question" capability.** Per `development-process.md`'s
  workflow, new questions are raised by the agent while working
  through TODO items (recorded directly in QUESTIONS.md), not
  hand-typed by the user through a widget UI -- the widget's job is to
  surface and let the user answer existing entries, not author new
  ones. If this turns out to be wanted later, it's a small additive
  change to make, not a redesign.
- **Filter: unanswered / answered / all** (`entry.answer.strip()`
  truthiness), not TODO.md's four-way incomplete/pending/completed
  /superseded scheme -- QUESTIONS.md entries only have that one binary
  state.
- **List shows each entry's title (truncated) plus an answered/
  unanswered marker**; double-clicking opens a dialog with the full
  body text (read-only -- the question itself isn't user-editable) and
  an editable answer field (pre-filled with the current answer, so
  re-answering/refining an existing answer works the same as answering
  a fresh one), mirroring `_ItemDialog`'s shape but split into a
  read-only question pane and an editable answer pane instead of one
  freeform field.
- **File watching, external-path indicator, edit-conflict handling on
  external change**: all mirrored directly from the TODO widget
  (`SingleFileWatcher`, `external_path_changed`/
  `refresh_external_path_status()`, and closing/flagging an open answer
  dialog if the underlying entry changed out from under it via
  `_resolve_edit_conflict`'s pattern) -- these are all generic,
  file-backed-widget concerns this widget shares with TODO, not
  QUESTIONS.md-specific design choices.
- **Git-commit-backed writes** via the same `_write_and_commit`
  -shaped helper (write synchronously on the GUI thread, commit in a
  background thread, `record_own_write` for self-write-echo
  suppression) -- copied into this widget rather than importing TODO's
  private module-level helper (it's parametrized over the render
  function and commit message, not otherwise TODO-specific, but small
  enough that a shared extraction isn't worth it yet for two callers).

## Affected files

- `src/desk/questions_file.py` (new) -- done and verified in isolation
  (see above) before starting the widget.
- `widgets/questions/widget.py` (new) -- `QuestionsWidget`.
- `widgets/questions/widget.json` (new) -- manifest, mirroring
  `widgets/todo/widget.json`'s shape.
- `design-docs/architecture.md` -- new widget entry.

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication`, no mocks
except `QMessageBox`/edit-conflict-adjacent paths where the TODO
widget's own tests already established the pattern):

- `questions_file.py`: parse the real QUESTIONS.md, confirm entry
  count/todo_ids/answers, confirm a full parse->render round-trip is
  byte-identical, confirm the nested-paren `9743419` answer is
  extracted in full (not truncated at its first inner paren), confirm
  `with_answer` splices correctly and the result reparses to the same
  answer with other entries untouched.
- Widget: load a temp QUESTIONS.md, confirm list population and
  filtering (unanswered/answered/all).
- Answering an unanswered entry via the dialog writes the expected
  `(Answer: ...)` text to disk and leaves every other entry's raw text
  untouched.
- Re-answering an already-answered entry (dialog pre-filled with the
  existing answer) updates just that entry's answer.
- External edit while the widget is open updates the list live (same
  `SingleFileWatcher` self-write-suppression as TODO).
- No QUESTIONS.md found near the current Desk directory: status label
  reflects that, list stays empty, no crash.

## Status

Not yet implemented -- `questions_file.py` is written and verified;
next is the widget itself.
