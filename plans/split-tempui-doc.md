# Split desk-temporary-ui.md into multiple files (COMPLETED)

TODO `e57ce5f`.

## Summary

`desk-temporary-ui.md` has grown a new section with almost every recent
tempui-related TODO (`DefineWidget`, its invocation/promotion
subsections, the Desk Bridge API) on top of the original five DSL
kinds. Split the less-general sections out into their own files
alongside it in `.desk_temp/`, referenced from the main file by
relative path. The main file keeps: the title, the shared version
note, an intro that now signposts the split files, the
`QUESTIONS.md`-redirect section, the base `Question` DSL section, the
closing note, and — unchanged, at the bottom — the dynamically
-generated "registered custom widgets" section.

One version number, in the main file only, stands for the whole set —
the split files carry no version note of their own.

Also: audited every existing DSL section's own prose for a reference to
Desk's own source/repo documentation (the request's explicit
requirement that the `.desk_temp` docs be self-sufficient) and found
two: the Bridge API section's pointer to `design-docs/architecture.md`,
and the `Markdown` section's pointer to `markdown-rendering.md`. Both
removed — the doc already says enough without them.

## File layout

- `desk-temporary-ui.md` (unchanged filename/location) — title,
  version note, intro (updated), `QUESTIONS.md` redirect, `Question`
  DSL section, closing note, dynamic custom-widgets section.
- `tempui-lightning-round.md` (new) — the `LightningRound` DSL section.
- `tempui-markdown.md` (new) — the `OpenMarkdown` and `Markdown` DSL
  sections (kept together: each section's own prose already
  cross-references the other).
- `tempui-scratch.md` (new) — the `Scratch` DSL section.
- `tempui-custom-widgets.md` (new) — the `DefineWidget` DSL section,
  its "Invoking a defined widget"/"Promoting a defined widget to the
  Desk" subsections, and the Desk Bridge API section (kept together:
  one cohesive feature area — an agent interested in one is
  overwhelmingly likely to need the others).

Each split file opens with a one-line note pointing back to
`desk-temporary-ui.md` for the overview and the shared version (not a
version note of its own — matching the request's "the version number
in the main file will stand for all of the files").

## Key decisions

- **Which sections stay in main vs. split out**: the `QUESTIONS.md`
  redirect and the base `Question` DSL section are the most
  general/cross-cutting content (every tempui user needs to know about
  the `QUESTIONS.md` distinction; `Question` is the DSL's own default,
  simplest case) — kept in main. `LightningRound`/`OpenMarkdown`+
  `Markdown`/`Scratch`/`DefineWidget`-and-friends are each a single,
  more specialized capability — split out.
- **Grouped by feature area, not strictly one-section-per-file**:
  `OpenMarkdown`+`Markdown` share one file (already directly
  cross-reference each other in their own prose); `DefineWidget`+
  invocation+promotion+Bridge-API share one file (one cohesive
  feature, not four unrelated ones).
- **One shared version, not per-file** — exactly as requested. This
  means `ensure_doc_version_current` (TODO `f7b1611`) can no longer
  operate on a single file path; it's renamed `ensure_docs_current`
  and now takes the whole `.desk_temp` directory, checking both the
  main file's version *and* whether every split file is still present.
  Either check failing (stale version, or any split file missing —
  e.g. a user deleted one) triggers a full refresh of the *entire* set
  — matching "one number stands for all of them," not a per-file
  staleness concept.
- **No Desk-repo references anywhere in `.desk_temp`** — audited every
  section; removed the two found (see Summary). Nothing was inlined to
  replace them — both sentences were pointing to *additional* detail
  beyond what the surrounding prose already states, not documenting
  something with no other explanation at all.
- **`sync_custom_widgets_doc_section` (TODO `91b3f42`) is untouched** —
  it already only ever operates on the main file's path, which is
  exactly where the request says the custom-widgets section stays.

## Code changes needed at every "the file is referenced" site

- `src/desk/temp_ui.py`: `DOC_TEMPLATE` trimmed to the main-file
  content; four new content constants + filename constants +
  `SPLIT_DOC_CONTENT: dict[str, str]`; new `write_tempui_docs(temp_dir)`
  (writes the main file via `render_static_doc()` plus every split
  file, fresh); `ensure_doc_version_current(doc_path)` →
  `ensure_docs_current(temp_dir)` (directory-wide staleness check +
  refresh, reusing `write_tempui_docs` and preserving the custom
  -widgets section exactly as before).
- `src/desk/shell/temp_ui_manager.py`: `provision`'s doc-handling block
  calls `write_tempui_docs`/`ensure_docs_current` instead of the old
  single-file functions.
- `widgets/claude/widget.py`: `CLAUDE_WIDGET_PROMPT` (tells a freshly
  -launched `claude` session where to read about running inside Desk)
  gets a small wording addition making explicit that the main doc
  links to further files worth following, not just implicitly relying
  on the agent to notice the relative links in the main file's own
  prose.
- `design-docs/architecture.md`/`design-docs/widget-ux.md`: existing
  mentions of `desk-temporary-ui.md`'s own "DefineWidget"/Bridge-API
  content updated to name `tempui-custom-widgets.md` instead, where
  that content now actually lives.

Checked and confirmed to need **no** change: `TempUiManager
._DirectoryHandler`'s UUID-filename filter (already generically ignores
any non-UUID filename, the new split files included, with no
per-filename special-casing to update) and `sync_custom_widgets_doc_
section` (already scoped to the main file only, which is where it's
supposed to stay).

## Affected files

- `src/desk/temp_ui.py`
- `src/desk/shell/temp_ui_manager.py`
- `widgets/claude/widget.py`
- `design-docs/architecture.md`
- `design-docs/widget-ux.md`

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication` where
`TempUiManager` is involved; plain function tests otherwise):

- `write_tempui_docs`: writes the main file (current version, no
  custom-widgets section) and every split file, into a real temp
  directory; none of the split files contain a version note; none of
  the rendered content (main or split) mentions `design-docs`,
  `plans/`, or `markdown-rendering.md`.
- `ensure_docs_current`: no-op on a missing main file; no-op when the
  version matches *and* every split file is present; refreshes the
  whole set (preserving a real custom-widgets section) when the
  version is stale; refreshes the whole set even with a *current*
  version if a split file is missing (deleted by a user, say).
- `TempUiManager.provision`: first creation writes the whole set, main
  file at the current version; a later `provision()` call on a
  directory with a stale/pre-split-era main file (and a real
  custom-widgets section) refreshes everything, preserving that
  section.
- Full scratchpad regression suite re-run, including fixing/renaming
  every existing reference to `ensure_doc_version_current` in this
  session's own prior verification scripts (TODO `f7b1611`/`5734529`'s
  suites) to the new `ensure_docs_current(temp_dir)` shape.

## Status

Implemented exactly as planned. `TEMPUI_DOC_VERSION` bumped 2 → 3 (a
real, meaningful content change -- the whole restructure, plus
removing the two Desk-repo references). Final file layout: main
`desk-temporary-ui.md` (title, version note, intro with relative links
to every split file, `QUESTIONS.md` redirect, `Question` DSL section,
closing note, dynamic custom-widgets section) plus
`tempui-lightning-round.md`, `tempui-markdown.md` (`OpenMarkdown` +
`Markdown` together), and `tempui-custom-widgets.md` (`DefineWidget` +
invocation + promotion + the Bridge API together).

Found and removed both Desk-repo references while auditing every
section's own prose, as required: the Bridge API section's pointer to
`design-docs/architecture.md`, and (a second one not originally
anticipated in the plan's Summary, caught by the same audit) the
version note's own mention of `src/desk/temp_ui.py` -- the HTML
-comment note itself named the exact source file that defines
`TEMPUI_DOC_VERSION`, which is exactly the kind of Desk-repo reference
the request said none of the documents should contain. Also removed
the `Markdown` section's pointer to `markdown-rendering.md`.

Updated every code site referencing the old single-file assumption:
`src/desk/shell/temp_ui_manager.py`'s `provision()` (now calls
`write_tempui_docs`/`ensure_docs_current`, directory-based);
`widgets/claude/widget.py`'s `CLAUDE_WIDGET_PROMPT` (now explicitly
tells the launched agent to follow the main doc's own links to further
files, not just rely on it noticing them); `design-docs/architecture.md`
and `design-docs/widget-ux.md` (both updated to name
`tempui-custom-widgets.md` where that content now actually lives).
Confirmed via a full audit (`grep`) that no other code site references
`DOC_FILENAME`/`desk-temporary-ui.md`/the renamed functions without
having been updated; three older, purely historical changelog entries
in `architecture.md` (describing what was built at the time, still
accurate as written) were deliberately left untouched rather than
over-edited.

Verified headlessly (`QT_QPA_PLATFORM=offscreen`, real `QApplication`
where `TempUiManager` is involved): 16 tests in a rewritten
`verify_tempui_doc_versioning.py` covering `write_tempui_docs`/
`ensure_docs_current`'s directory-wide behavior (including the new
"any split file missing, even at a current version, triggers a full
refresh" case explicitly requested by "don't each need their own
version" not meaning "don't check they exist"), a real end-to-end
`TempUiManager.provision` first-creation and stale-refresh case, and a
direct audit asserting none of `design-docs`/`markdown-rendering.md`/
`plans/`/`src/desk` appear anywhere in the rendered doc set. Manually
generated the full doc set into a scratch directory and read every
file to confirm it reads correctly end to end (relative links,
per-file headers, no broken cross-references).

Two other prior-TODO verification scripts needed small updates for the
renamed API/bumped version (not left broken):
`verify_html_widget_local_storage.py`'s hardcoded `TEMPUI_DOC_VERSION
== 2` loosened to `>= 2` (that assertion's real intent -- confirming
TODO `5734529`'s own content is present -- doesn't depend on the exact
current version number, which is expected to keep changing).

Full scratchpad regression suite re-run -- same three pre-existing,
unrelated failures as every recent prior TODO, none touching any file
edited here.

No `LEARNINGS.md` entry -- nothing here violated a reasonable
assumption or took real investigation; it's a straightforward content
-reorganization plus a mechanical generalization of the existing
version-check pattern from one file to a set.
