# Markdown rendering in Desk

TODO `9743419`. Reference for what Desk's Markdown-rendering widgets
actually support — see `diagrams.md` for a runnable set of examples
exercising the Mermaid/SVG pieces of this.

## Widgets

- **Markdown Widget** (`widgets/markdown/`) — the plain viewer. Renders
  one chosen file via Qt's native `QTextBrowser.setMarkdown()`, nothing
  more: no table of contents, no foldable sections, no diagrams. Auto
  -reloads when the file changes on disk. See
  `plans/markdown-renderer-widget.md`.
- **Markdown (Extended) Widget** (`widgets/markdown_ex/`) — everything
  the plain widget does, plus:
  - A left-hand table-of-contents tree, generated from the document's
    own headings.
  - Foldable sections: each heading's content collapses/expands via a
    disclosure triangle, nested by heading level.
  - Inline Mermaid diagram rendering (see below) for fenced
    ` ```mermaid ` code blocks — the one piece of syntax the plain
    Markdown widget doesn't understand at all (it renders a Mermaid
    fence as a plain, unrendered code block, same as any other
    language).

  See `plans/markdown-ex-widget.md`.

Both widgets can be pointed at a file either via their own "Open"
button, or programmatically by another widget (`set_file(path)`) — e.g.
the TODO widget's "open plan" button, or a tempui `OpenMarkdown <path>`
notification (see "Tempui integration" below).

## Markdown syntax support

Both widgets render through the same underlying engine,
`QTextDocument.setMarkdown()` (via `QTextBrowser`), with no custom
`MarkdownFeature` flags set — so both get Qt's *default* dialect,
`MarkdownDialectGitHub`. In practice that covers:

- Headings (`#` through `######`), paragraphs, line breaks.
- Emphasis: `*italic*`/`_italic_`, `**bold**`, and GitHub's
  `~~strikethrough~~`.
- Links (`[text](url)`) and autolinks (a bare `https://...` URL).
- Ordered and unordered lists, including nesting.
- Blockquotes (`>`).
- Tables (GitHub's `| a | b |` pipe syntax).
- Fenced and indented code blocks (rendered as plain monospace text —
  no syntax highlighting; that's what the separate Code Editor widget
  is for).
- Images (`![alt](path)`) — see "Images and SVGs" below.

Not supported (Qt's Markdown parser doesn't implement these, regardless
of dialect): footnotes, task-list checkboxes (`- [ ] ...` renders as a
literal list item, not an interactive checkbox), definition lists, or
custom HTML blocks beyond what `QTextDocument`'s own limited inline-HTML
handling covers.

## Images and SVGs

Raster images (PNG/JPEG/GIF/etc.) work natively — `QTextDocument`
resolves relative paths against the source file's own directory.

SVG images work too, but indirectly and with a caveat: `QTextDocument`
has no native vector renderer, so it loads an SVG through Qt's image
-format-plugin machinery, which **rasterizes it once at the size it's
displayed**, not vector-scaled — it can look blocky if the surrounding
layout later scales it up. For a crisp, properly-scaled single SVG, use
the dedicated **SVG Viewer** widget instead (`widgets/svg_viewer/`,
`QSvgRenderer`-based, true vector scaling). See
`qtextbrowser-images-svg-controls.md` for the full investigation.

## Mermaid diagrams (Markdown (Extended) only)

A fenced ` ```mermaid ` block is pulled out and rendered by
`desk.mermaid` — a small, **intentionally partial** Mermaid
implementation, not the real Mermaid.js grammar:

- **Flowchart**: `flowchart <direction>` (`TD`/`TB`/`LR`/`BT`/`RL`).
  Four node shapes only — rect `[Label]`, rounded `(Label)`, diamond
  `{Label}`, circle `((Label))`. Edges: solid `-->`, open/no-arrowhead
  `---`, dotted `-.->`, and piped edge labels `-->|label|`. Multi-node
  chains on one line, self-loops, and cycles are supported.
- **State diagrams**: flat only (no nested/composite states).

No other Mermaid diagram types (sequence, class, ER, Gantt, etc.) are
supported — a fence using one renders as an error/placeholder, not a
silent fallback to plain text. See `src/desk/mermaid.py`'s own
docstring for the exact grammar, and `diagrams.md` for a full set of
runnable examples of everything above.

## What isn't possible

`QTextBrowser`/`QTextDocument` is a text/richtext document view, not a
container: there is no way to embed a real, interactive Qt control
(a button, a text field, a live sub-widget) inline in rendered Markdown
content. If a widget needs that, it needs `QGraphicsScene` +
`QGraphicsProxyWidget` (how Desk's own Workspace Canvas places widget
chrome) or a Chromium/`QWebEngineView`-based widget instead — not
Markdown rendering.

## Tempui integration

The plain Markdown widget has no tempui integration. Markdown
(Extended) does, via the `OpenMarkdown` tempui capability
(`desk-temporary-ui.md`'s own DSL docs, `desk.temp_ui.parse_open_markdown`):
an agent drops a `.desk_temp/<uuid>` file whose first line is
`OpenMarkdown <path>`, and clicking the resulting notification opens
`path` in a new Markdown (Extended) instance. This is a **pointer** to
an existing file elsewhere on disk — the tempui file's own content
isn't itself rendered as Markdown. See `plans/tempui-open-markdown.md`.
