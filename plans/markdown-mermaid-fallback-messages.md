# Markdown widget: distinguish Mermaid fallback reasons (TODO 9fe03a1) (COMPLETED)

## Summary

`_build_mermaid_widget`/`_mermaid_fallback_widget` (`widgets/markdown/
widget.py`) collapsed every failure -- no transform registered for this
project, a genuinely malformed diagram, or the transform itself
failing/producing bad output -- into one generic
"(unsupported or unparseable Mermaid diagram)" note (TODO `a9e2ba7`'s
original, deliberate decision). There was no way, from the widget's own
UI, to tell "your Mermaid syntax is wrong" from "this project just
doesn't have the transform that would have rendered it," and the
`MermaidParseError`/`TransformError` message that already existed for
either case was discarded. Cites
`../FEEDBACK/FEEDBACK-DESK-mermaid-parser-rejects-standard-syntax-2026-09-18-2220.md`
and
`../FEEDBACK/FEEDBACK-DESK-mermaid-rendering-fails-silently-without-project-transforms-2026-09-18-2000.md`.

## Approach

`_build_mermaid_widget` now distinguishes:

1. **Unsupported diagram type** (`detect_diagram_kind` doesn't
   recognize the header at all) -- can only ever be this one thing.
2. **`MermaidParseError`** -- detected by calling `desk.mermaid.parse`
   directly, ourselves, in-process, *before* invoking the transform.
   Both Mermaid transforms are thin, synchronous, same-process Python
   wrappers around this exact function; by the time an exception
   reaches here through `TransformsService._invoke`'s own generic
   `except Exception as e: on_result(None, str(e))`, the type is
   already gone -- there's nothing left to `except MermaidParseError`
   against. Parsing here first, while the real exception object still
   exists, is what actually recovers it. The transform then parses the
   same (unmutated) content again -- a cheap, harmless redundant parse.
3. **No transform found in this project** -- `TransformsService`
   flattens this to a `TransformError` whose message always starts
   with the literal `"Unknown transform: "` (`_require`'s own wording);
   matched the same way this codebase's own
   `tests/verify/verify_transforms_service.py` already does, since
   there's no exception subclass or structured code to check instead
   (the whole service only ever surfaces plain strings by design).
4. **Any other transform failure** (a genuine bug, or valid-looking
   output that turns out not to be valid SVG) -- shown with its own
   detail, in a generic "rendering failed" bucket.

`_mermaid_fallback_widget` takes the note as a parameter instead of a
hardcoded string.

## Affected files

- `widgets/markdown/widget.py`
- `tests/verify/verify_markdown_mermaid_transforms.py` -- updated
  existing tests for the new message text, two new tests (syntax error
  vs. missing transform, with a sanity check on the exact string this
  whole distinction hinges on).
- `src/desk/temp_ui.py` -- `_MARKDOWN_DOC`'s "Supported Mermaid subset"
  section (added by TODO 90dd6e6) gains a paragraph naming each
  fallback note and stating plainly that rendering depends on the
  current project having the right transform (the second feedback
  file's suggestion 2) -- new tag + `_NEW_FEATURES` entry.

## Verification

`_build_mermaid_widget` called directly (no real widget tree needed) for
each case: unsupported diagram type, a genuinely malformed diagram
(confirms it never even reaches the transform runner), an empty/real
`TransformsService` with no `desk_transforms/` copied in (the actual
root cause from the second feedback report, plus a sanity check that
`TransformsService` really does raise the exact `"Unknown transform: "`
string this depends on), a transform that raises for an unrelated
reason, invalid SVG output, and no runner registered at all -- each
checked against its own distinct message text, and cross-checked that
different cases don't share the same wording. Real end-to-end case
(existing test) unaffected. Re-ran `verify_markdown_mermaid_transforms.py`
in full, `verify_tempui_doc_versioning.py` (guards against Desk-internal
paths leaking into the tempui doc set). Full `tests/verify/` sweep (159
scripts) passes. Browser launch not needed.

## Status

Implemented as planned, no deviations. The first cited feedback file's
own items (90dd6e6, this one) are both complete -- moved
`../FEEDBACK/FEEDBACK-DESK-mermaid-parser-rejects-standard-syntax-2026-09-18-2220.md`
to `../FEEDBACK/implemented/`. The second stays in place:
`../FEEDBACK/FEEDBACK-DESK-mermaid-rendering-fails-silently-without-project-transforms-2026-09-18-2000.md`
is also cited by TODO `05f2222` (suggestions 2 and 3 -- discovering
Desk's own bundled `desk_transforms/`), still open and next in the
queue.
