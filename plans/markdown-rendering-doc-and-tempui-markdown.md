# Markdown rendering capabilities doc + tempui-based Markdown (Extended) "save a copy" (COMPLETED)

TODO `9743419`.

## Summary

Three-part request:

1. "Add a md file to the source with a description of the markdown
   rendering capabilities of Desk." — **done**, see `markdown
   -rendering.md`.
2. "update the markdown_ex markdown viewer to be able to show a
   tempui-based markdown file" — **blocked**, see Open Question below.
3. "in that case, add a 'save a copy' button to replace 'open' and
   default to the root of the project directory with a default file
   name derived from the first line of the markdown file; once that
   file is saved, it should be opened in a new normal markdown_ex
   widget, and the original tempui one should remain open." — depends
   entirely on (2)'s mechanism, so also blocked.

## Part 1 (done): `markdown-rendering.md`

A project-root reference doc covering: which widgets render Markdown
(plain vs. Extended) and what each adds; the actual Markdown syntax
subset supported (`QTextDocument.setMarkdown()`'s default
`MarkdownDialectGitHub` dialect — confirmed directly: strikethrough and
tables both render; task-list checkboxes render as plain list items,
not interactive, confirmed by inspecting `MarkdownFeature`'s default
value and Qt's own parser behavior, not assumed); images/SVG handling
(cross-references the existing `qtextbrowser-images-svg-controls.md`
investigation); the Mermaid subset `desk.mermaid` actually implements
(cross-references `diagrams.md`'s runnable examples); what's
architecturally impossible (no live embedded Qt controls inside
rendered Markdown); and the existing `OpenMarkdown` tempui integration
(a pointer to an external file, not the tempui file's own content).

## Open Question (blocking parts 2 and 3)

"A tempui-based markdown file" is genuinely ambiguous between at least
two different mechanisms, and the choice materially changes the
design (and needs to be documented in `desk-temporary-ui.md`'s own DSL
instructions for claude either way, so getting the actual syntax right
matters):

- **(a) A new explicit tempui keyword** (e.g. `Markdown` as the tempui
  file's first line, matching `Scratch`'s TODO f8d9cec shape exactly:
  first line is the keyword, everything after it verbatim is the
  content) — Markdown (Extended) would render everything after that
  first line as live Markdown, watched for changes the same way
  Question/LightningRound already watch their own tempui file via
  `set_source_file`.
- **(b) Any tempui file with *no* recognized keyword at all** falls
  back to being rendered as raw Markdown by Markdown (Extended),
  instead of today's fallback to the Question widget. This changes
  `detect_temp_ui_kind`'s existing default-fallback behavior for
  *every* tempui file with a first line that doesn't happen to start
  with a known keyword — including a malformed/typo'd `Question` file,
  which today falls back to an (empty but still recognizable) Question
  widget and would instead silently become a Markdown widget showing
  garbled text. This is a real behavior change to an existing,
  already-relied-upon fallback, not just an additive one.

There's also a second, independent ambiguity in part 3's own wording:
**"a default file name derived from the first line of the markdown
file"** doesn't specify the derivation algorithm -- e.g. `# My
Investigation Notes` becoming literally `My Investigation Notes.md`,
or a slugified `my-investigation-notes.md`, or something else (leading
`#`/heading markers stripped how, spaces/punctuation handled how,
length-capped or not).

Recorded in `QUESTIONS.md` rather than guessing at either the DSL
mechanism (option a vs. b materially differs in *existing*-behavior
risk, not just a stylistic choice) or the filename-derivation format
(a save-dialog default the user will actually look at, worth getting
right the first time rather than picking arbitrarily).

## Status

Implemented in full, after the user resolved the open questions (see
`QUESTIONS.md`): a new `Markdown <label>` tempui DSL keyword
(`desk.temp_ui.MARKDOWN_KEYWORD`/`parse_markdown_tempui`,
`detect_temp_ui_kind` -> `"markdown_content"`) whose own content -- not
a pointer to an external file, unlike `OpenMarkdown` -- is rendered
directly by the Markdown widget via a new `set_tempui_content(label,
content)`. Wired through `DeskWindow._bind_temp_ui_content`/
`_temp_ui_widget_id_for`/`_notify_temp_ui` the same way the other
tempui kinds already are. A tempui-bound instance shows a **"Save As"**
button in place of "Open"; saving defaults to the project root with a
kebab-case-slugified filename derived from the rendered content's own
first line, and opens the saved file in a *new*, ordinary file-backed
Markdown instance while the original tempui-bound instance stays open,
unaffected.

The parked branch (`pending/9743419-markdown-rendering-doc`) was
merged in, and `markdown-rendering.md` itself updated for the
now-completed 96013cf/858752b rename (it was written before that
happened) plus a new "Tempui integration" description of this
capability.

All headless verification steps above passed, plus a full,
non-mocked-except-the-file-dialog "Save As" round trip: a real
tempui-bound widget instance saves real content to a real file at the
derived path, a real second widget instance opens pointed at it, and
the original instance is confirmed unaffected/still tempui-bound
afterward. Also ran a regression pass of the existing Scratch tempui
verification to confirm the shared dispatch code (`_bind_temp_ui_content`
/`_temp_ui_widget_id_for`/`_notify_temp_ui`) wasn't disturbed for the
other kinds.

One correction to my own earlier description to the user, noted here
for the record: I described this as "rendered live and watched for
changes," but checking `QuestionWidget`/`LightningRoundWidget`'s actual
existing behavior showed neither actually live-watches its tempui file
for *external* edits after being bound -- both just render once at
bind time (plus their own self-triggered updates). The Markdown tempui
capability matches that same, simpler, actual precedent (render once
at bind time via `set_tempui_content`), not continuous file-watching.

No `LEARNINGS.md` entry needed -- the correction above is a plan
-level clarification, not a surprising runtime discovery during
verification.
