# Fix QUESTIONS.md format doc gap and silent parse failure (TODO `1b7e500`)

## Summary

Per
`../FEEDBACK/FEEDBACK-DESK-questions-md-format-undocumented-and-brittle-2026-08-04-1347.md`:
`desk-temporary-ui.md`'s "Questions for the user" section
(`src/desk/temp_ui.py:236`) says each `QUESTIONS.md` entry is a `##
<short summary>` heading. The real parser
(`src/desk/questions_file.py`'s `ENTRY_START_RE`/`TODO_ID_RE`)
requires `## TODO \`<id>\`[/\`<id2>\`...]: <summary>` -- a literal
leading `TODO`, backtick-wrapped id(s) -- matching the deliberate
original design (`plans/questions-widget.md`: entries are
TODO-blocking questions, not general free-standing ones). An entry
whose heading doesn't match doesn't partially parse -- it's silently
absorbed into `preamble`, so `parse_questions_file` returns zero
entries, `_on_questions_file_changed` never shows the "new question"
notification, and the Questions widget shows nothing -- indistinguishable
from a file with no questions at all, at every layer.

## Affected files

- `src/desk/temp_ui.py` -- the doc text, plus a `TEMPUI_DOC_VERSION`
  bump and `_NEW_FEATURES_DOC` entry.
- `src/desk/questions_file.py` -- new helper to detect unparsed `## `
  headings.
- `src/desk/shell/window.py` -- `_on_questions_file_changed` logs a
  warning when unparsed content is detected.
- `tests/verify/` -- new coverage.

## Design decisions

- **Fix the doc to match the parser; don't change the parser to add
  free-standing-question support.** The FEEDBACK item presents these
  as alternatives. Given `plans/questions-widget.md`'s own original,
  deliberate design (TODO-blocking questions only), loosening the
  parser to also accept id-less headings would be a real feature
  addition, not a doc-accuracy fix -- out of scope for "keep the doc
  in sync with the code."
- **Doc wording**: state the real required heading shape verbatim
  (`## TODO \`<id>\`[/\`<id2>\`...]: <summary>`) and say explicitly
  that an entry must reference at least one TODO id -- not just show
  a corrected example, since the earlier framing's own prose ("if you
  have an open-ended question... instead of creating a file here")
  reads as if any question qualifies, which is exactly what misled the
  original report.
- **New `unparsed_heading_count(path) -> int` in `questions_file.py`**,
  not a change to `parse_questions_file`'s own return signature --
  that function has 4 real call sites across `window.py`/
  `widgets/questions/widget.py`, all doing 2-tuple unpacking; adding a
  third return value would force touching all of them for a
  diagnostic-only feature. A small, separate, opt-in helper is less
  invasive and keeps the existing call sites completely unchanged.
  Implementation: count real `## ` heading lines
  (`^## .*$`, multiline) that don't also match `ENTRY_START_RE`.
- **Low-severity log line, not a new UI surface.** Matches this
  project's own established precedent for exactly this shape of gap
  (`_relocate_promoted_widget_source`'s no-source-directory case,
  TODO `a820354`): "free for the common case to ignore, a concrete
  breadcrumb for the uncommon one." A `QUESTIONS.md` with unparsed
  content isn't common enough (or urgent enough) to warrant a new
  notification/Scratch-note mechanism the way the tempui-doc-drift
  case did -- a `logger.warning` in `_on_questions_file_changed` is
  the proportionate fix.

## Step-by-step implementation

1. `temp_ui.py`: rewrite the "Questions for the user" section's format
   description to the real required shape, and add a sentence stating
   the TODO-id requirement explicitly.
2. `temp_ui.py`: bump `TEMPUI_DOC_VERSION`, add the matching bump
   comment and a `## Version <N>` entry to `_NEW_FEATURES_DOC`
   (following this file's own established convention).
3. `questions_file.py`: add `_ANY_HEADING_RE = re.compile(r"^## .*$",
   re.MULTILINE)` and `unparsed_heading_count(path: Path) -> int`.
4. `window.py`: `_on_questions_file_changed` calls
   `unparsed_heading_count(questions_path)` and logs a `logger.warning`
   (naming the path and count) when it's nonzero -- alongside the
   existing entry-parsing logic, not gating it.
5. New verify coverage (see below); run the full `tests/verify/`
   suite.

## Key tradeoffs

- Not adding a UI-visible signal for unparsed content (just a log
  line) means an agent that isn't watching logs still won't notice --
  accepted as proportionate to how rare this should be once the doc
  itself is fixed to describe the real format correctly.

## Verification

New checks in a new `tests/verify/verify_questions_md_format_fix.py`
(a fresh file -- no existing verify script currently covers
`temp_ui.py`'s Questions section content or
`_on_questions_file_changed`'s logging), real (no mocking):
- `TEMPUI_DOC_VERSION` is bumped.
- The doc's "Questions for the user" section states the real required
  heading shape (contains `` `## TODO ` `` and mentions backtick
  -wrapped ids) and no longer shows the old, wrong `## <short
  summary>` example as *the* format.
- `_NEW_FEATURES_DOC` has a matching new-version entry.
- `unparsed_heading_count` returns 0 for a real, correctly-formatted
  `QUESTIONS.md`.
- `unparsed_heading_count` returns the real count (not just nonzero)
  for a file with one or more `## `-headed entries that don't match
  the required TODO-id format.
- A real `_on_questions_file_changed` call (via the established
  `_FakeWindow` pattern) against a malformed `QUESTIONS.md` logs a
  warning naming the file and the unparsed count (captured via a real
  `logging.Handler`, matching this project's own established
  `_WindowLogCapture` pattern from
  `verify_relocate_promoted_widget_source.py`) -- and does *not* log
  anything for a well-formed file.
- Full `tests/verify/` regression suite.
