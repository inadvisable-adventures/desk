# Markdown widget: link clicks (TODO `99ed232`) (COMPLETED)

## Summary

From `../FEEDBACK/FEEDBACK-DESK-markdown-widget-silently-inlines-a-linked-file-s-content-in-2026-11-05-1915.md`:
a section's text appeared to be silently replaced by the content of a file it linked to (`[LICENSE](./LICENSE)`
showed Desk's own MIT license instead of the project's text).

## Root cause (reproduced headlessly)

Not a render-time feature. `_AutoHeightTextBrowser` is a `QTextBrowser`, whose default `openLinks=True` makes a
*click* on a link navigate in place: it calls `setSource()` with the raw `./LICENSE`, replaces the block's whole
document with that file, and resolves it against the **process working directory** (Desk's own checkout), not the
document `baseUrl` set for images. So the wrong file's text (Desk's `LICENSE`) was displayed instead of the project's,
and the author's paragraph vanished until the next re-render. The companion `OpenMarkdown` path ticket is a
different code path; this one has no shared resolver.

## Fix (`widgets/markdown/widget.py`)

`setOpenLinks(False)`, `setOpenExternalLinks(False)`, and an `anchorClicked` handler:

- `#fragment` -> `scrollToAnchor` within the block;
- any scheme other than `file` (http, https, mailto...) -> `QDesktopServices.openUrl`;
- otherwise (relative path or `file:` URL) -> resolve against the markdown file's own directory (the project's
  directory for tempui-bound content), and if it exists open it through the shared editor-or-scrap service
  (`current_context.get_editor_or_scrap_opener`, as the widget's Edit button does); a missing target is logged and
  ignored. The block's text is never replaced.

## Out of scope

- `widgets/markdown_old_basic` (the retired plain widget) keeps the same default QTextBrowser behavior; it is not
  the widget in use.
- Opening a linked `.md` in a Markdown widget specifically (rather than the editor-or-scrap chain) is left for a
  later TODO if wanted.

## Verification

`tests/verify/verify_markdown_link_clicks.py` clicks a real rendered link with `QTest.mouseClick` (offscreen) and
checks the text is untouched and the right path is opened. Headless only.

## Follow-up

`widgets/markdown_old_basic` was subsequently removed outright (TODO `5a1b231`), so the "out of scope" note above
about it no longer applies.
