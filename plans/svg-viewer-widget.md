# SVG Viewer widget

TODO `c7d6e4d`.

## Summary

"Implement an SVG-rendering widget." A new `kind: "python"` widget
(`widgets/svg_viewer/`) that opens and displays a single `.svg` file,
scaled to fit the widget while preserving aspect ratio, auto-reloading
on changes — the same shape as the plain Markdown widget (TODO
`6bf83a9`), but for SVG instead of Markdown.

## Key decisions

- **`QtSvg`/`QtSvgWidgets` (bundled with `PyQt6-Qt6`, already a
  dependency — no new package)**, not a vendored SVG library — matches
  `CLAUDE.md`'s dependency aversion and this repo's existing
  `qtextbrowser-images-svg-controls.md` research note, which already
  identified `QtSvg` as present but unused.
- **A custom `QSvgRenderer` + `paintEvent`, not the stock
  `QSvgWidget`.** Confirmed directly, headlessly: `QSvgWidget` renders
  into its full widget rect without preserving aspect ratio — a
  100×100 SVG circle drawn into a 400×100 widget came out as a
  300px-wide ellipse (should stay a ~100px circle). Fix: render via a
  bare `QSvgRenderer` into a manually computed, letterboxed target
  `QRectF` (scaled to fit within the widget, centered on the shorter
  axis) — confirmed this keeps the same circle circular (~75px wide,
  correctly centered, with visible letterbox background on both
  sides). The content size for that fit computation prefers
  `QSvgRenderer.defaultSize()` (the SVG's own intrinsic
  width/height), falling back to `viewBoxF().size()` if the SVG
  declares no explicit size (only a `viewBox`), and finally to "just
  fill the widget" (1:1, no aspect info available at all) if neither
  is present.
- **Live reload via `desk.file_watch.SingleFileWatcher`** and an
  editor-style Open button seeded from
  `current_context.get_current_desk_directory()` (falling back to
  home) — identical shape to the Markdown widget (this widget shows
  one file, like Markdown/Editor/Sheet, not a primary-directory role
  like the TODO/Git Status/File Explorer widgets).
- **Invalid/unparseable SVG degrades to a message, not a crash or
  blank widget** — `QSvgRenderer.isValid()` checked after every
  load/reload; `paintEvent` no-ops (nothing to draw) and a label above
  the canvas reports the problem, mirroring the Markdown widget's own
  `FileNotFoundError`/`OSError` handling.
- **No in-widget zoom/pan** — out of scope for this item (matches the
  Markdown/Editor/Sheet widgets' own scope level; the Workspace
  Canvas's existing zoom already covers "make it bigger" for the whole
  widget frame). Worth a `PARKINGLOT.md` note as a future enhancement,
  not implemented here.
- **No integration with other widgets** (e.g. having the File Explorer
  or Markdown (Extended) widget's `.svg` results open here instead of
  the Editor/QTextBrowser) — the TODO text is just "Implement an
  SVG-rendering widget," and neither of those widgets' own completed
  TODOs mentioned this widget, so wiring them together isn't in scope
  here; flagged as a `PARKINGLOT.md` idea instead.

## New/affected files

- `widgets/svg_viewer/widget.json` (new) — `{name: "SVG Viewer", kind:
  "python", entry: "widget.py", capabilities: [], default_size:
  480x480}`.
- `widgets/svg_viewer/widget.py` (new):
  - `_fit_rect(content_size: QSizeF, container_size: QSizeF) ->
    QRectF` — pure geometry helper (letterboxed, centered fit),
    independently testable without a live `QApplication`.
  - `_AspectSvgView(QWidget)` — owns the `QSvgRenderer`, `load(data:
    bytes) -> bool`, `paintEvent` using `_fit_rect`, `isValid()`
    passthrough.
  - `SvgViewerWidget(QWidget)` — toolbar (Open button + filename
    label) + `_AspectSvgView`, `SingleFileWatcher`-driven `_reload`,
    `set_file(path)` (public, matching `MarkdownWidget`'s own
    programmatic-open convention even though nothing calls it yet —
    consistent with every other single-file widget in this codebase).
- `design-docs/architecture.md` — new SVG Viewer Widget component
  entry.
- `PARKINGLOT.md` — two small notes: in-widget zoom/pan for the SVG
  Viewer, and wiring `.svg` results in the File Explorer/Markdown
  (Extended) widgets to open here.

## Verification

Headless (no browser needed):

- `_fit_rect`: a wide container/square content (letterboxed
  left/right), a tall container/square content (letterboxed top/
  bottom), a matching-aspect container (fills exactly, no letterbox),
  and a zero-size content/container edge case (falls back to filling
  the container rather than dividing by zero).
- `_AspectSvgView`: real headless (offscreen `QApplication`) render of
  a small test SVG (a circle, same shape used while planning this)
  into a deliberately non-matching-aspect widget size, sampling
  `grab()`'d pixels to confirm the circle stays circular (not
  stretched into an ellipse) — the same check already done directly
  while investigating the `QSvgWidget` behavior above, now as part of
  the widget itself. Also: an invalid SVG (`isValid()` False) paints
  nothing and doesn't raise.
- `SvgViewerWidget`: `set_file` on a real temp `.svg` renders it and
  updates the label; the file watcher picks up an on-disk edit
  (replace the file's content, confirm the rendered circle's
  radius/color changes accordingly); a deleted/unreadable file shows a
  message instead of crashing.
- Real widget-loading path: `desk.widgets.discover_widgets` picks up
  the manifest; `desk.shell.python_widget.PythonWidgetHost` builds a
  real `SvgViewerWidget` (a literal `DeskWindow` construction skipped
  for the same pre-existing, unrelated offscreen-`QtWebEngine` stall
  noted in `plans/markdown-ex-widget.md`/`plans/file-explorer-widget.md`).

## Status

Not yet implemented.
