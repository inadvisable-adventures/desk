# QTextBrowser: images, SVGs, and hosting other Qt controls

**Q: Can QTextBrowser show images and svgs? can it host other QT controls?**

Both, with caveats.

**Images (raster):** Yes. `QTextBrowser`/`QTextDocument` renders `<img>` tags
and Markdown image syntax (`![alt](path)`) out of the box for
PNG/JPEG/GIF/etc. For local files it resolves relative paths against
`document().baseUrl()` (or you can override `loadResource()` on a subclass to
intercept and supply your own `QVariant`/`QImage`).

**SVG:** Works, but indirectly. `QTextDocument` doesn't have native vector
SVG support — it loads images through `QImageReader`, and SVG only becomes
readable that way if the Qt SVG *image format plugin* is present, which
rasterizes the SVG once at load time (not vector-scaled, so it can look
blocky if the doc scales it up). In this project's deps
(`pyproject.toml:9-16`), you have `PyQt6` (which bundles `PyQt6-Qt6`, the
actual Qt binaries including the imageformats plugins) but no explicit
`QtSvg`/`QtSvgWidgets` import anywhere in the codebase currently — nothing
references svg yet. The plugin likely ships with the Qt6 binary distribution
PyQt6-Qt6 installs, so `<img src="foo.svg">` in `setMarkdown()`/`setHtml()`
content would probably just work, but it's worth verifying at runtime rather
than assuming.

**Hosting other Qt controls (live widgets):** No. `QTextBrowser` is a
text/richtext document view, not a container — you cannot embed a real,
interactive `QPushButton`, `QComboBox`, etc. inline in the flowed text the
way an `<iframe>` works in HTML. The only embedding mechanism it exposes is
`QAbstractTextDocumentLayout::registerHandler()` with a custom
`QTextObjectInterface`, which lets you custom-*paint* an inline object (and
manually hit-test mouse events yourself) — it's not a hosted live widget
with its own event loop, focus handling, or signals. If you need real
interactive controls inside rendered content, you'd need `QGraphicsScene` +
`QGraphicsProxyWidget`, or drop down to the `QWebEngineView` you already
depend on (`PyQt6-WebEngine`) and use HTML/JS controls there instead.
