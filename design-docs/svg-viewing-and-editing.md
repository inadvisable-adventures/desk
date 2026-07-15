# Desk — SVG Viewing and Editing

Pulled out of `PARKINGLOT.md` ("SVG Viewer widget: further work" and "SVG
editor"). Two related widget changes:

- The **Image Viewer** widget (`widgets/image_viewer/`) becomes the one
  widget for viewing both raster and vector images, absorbing the
  standalone SVG Viewer widget's rendering path.
- A new **SVG Editor** widget (`widgets/svg_editor/`) for actually editing
  `.svg` files, distinct from viewing.

## Goals

- Opening a `.svg`/`.svgz` file in Image Viewer renders it via the same
  aspect-fit, letterboxed approach already used for raster images (see
  `desk.geometry.fit_rect`), using the existing `QSvgRenderer`-based
  rendering path currently living in the standalone SVG Viewer widget.
- The standalone SVG Viewer widget (`widgets/svg_viewer/`, TODO `c7d6e4d`)
  is retired — its rendering logic moves into, and is owned by, Image
  Viewer; it isn't kept around as a separate, now-redundant widget.
- A new SVG Editor widget provides:
  - A **toolbox** with a create tool for each supported SVG visual-object
    type (see [Supported Element Types](#supported-element-types) below).
  - An editing tool for **points** — selecting and dragging a path/
    polyline/polygon's individual vertices.
  - An editing tool for **shapes** — selecting a whole object (any
    supported type) to move/resize/transform it and edit its visual
    attributes (fill, stroke, stroke width) as a unit, rather than vertex
    by vertex.
  - Open/Save (and Save As for a new/untitled document), matching every
    other file-backed widget's shape (`Open` button + file watcher +
    auto-reload — see e.g. `widgets/markdown/widget.py`).

## Non-Goals

- Gradients, filters, animation (`<animate>`/SMIL), masking/clipping,
  `<use>`/`<symbol>`/`<defs>` reuse, or any other advanced SVG feature —
  see [Supported Element Types](#supported-element-types) for the closed
  set this editor actually treats as editable objects. A loaded file's
  unrecognized top-level elements round-trip untouched on save (preserved
  verbatim) rather than being silently dropped, but they're inert, not
  editable, in the first pass.
- Embedding an `.svg`'s own nested raster `<image>` references, or editing
  an embedded raster image from within the SVG Editor.
- In-widget zoom/pan for Image Viewer's SVG rendering — this was already
  parked separately before this doc and remains parked; unrelated to the
  viewing/editing merge itself.
- Undo/redo history in the SVG Editor. Worth adding later if editing
  without it proves painful in practice; not attempted in the first pass.
- Multi-select, alignment/distribution tools, a layers panel, or grouping
  (`<g>`) as an editable concept — the first version only needs
  single-object create/select/point-edit/shape-edit.
- Embedding a `kind: "html"` widget's rendering approach for SVG (e.g. an
  embedded `<img>`/inline-SVG-in-a-page) — both Image Viewer and SVG
  Editor stay `kind: "python"`, matching the widget they're extending or
  replacing.

## Design

### Image Viewer: raster + vector

`ImageViewerWidget` and the (retiring) `SvgViewerWidget` are already
near-identical in shape — same toolbar (Open/Edit/status label), same
`SingleFileWatcher`-driven auto-reload, same `desk.geometry.fit_rect`
-based aspect-preserving paint. The only real difference is the rendering
backend: `_AspectImageView` (`QPixmap`) vs. `_AspectSvgView`
(`QSvgRenderer`). Image Viewer keeps both view implementations internally
and picks one per loaded file — by extension (`.svg`/`.svgz`, case
-insensitive, matching how `BUILTIN_VIEW_WIDGET_BY_SUFFIX` already keys
off suffix) rather than by sniffing content, since SVG's XML preamble
isn't reliably distinguishable from other XML-ish text formats cheaply,
and extension-based dispatch is exactly what the file type registry
already does elsewhere (`src/desk/file_type_registry.py`). Only one of
the two view implementations is visible/active at a time, swapped via
the same kind of page-swap shape already established for greeked widgets
(`design-docs/widget-ux.md`'s "Titlebar Degrade + Greeking" section) —
not a separate widget instance or dialog, just an internal view swap
behind the one common toolbar/label/watcher/edit-button plumbing that
`set_file`/`_reload` already drive.

- `IMAGE_FILTER` gains `*.svg *.svgz` in its file-picker filter string.
- `src/desk/file_type_registry.py`'s `BUILTIN_VIEW_WIDGET_BY_SUFFIX[".svg"]`
  changes from `"svg_viewer"` to `"image_viewer"` (the built-in
  view-fallback table `find_view_handler` already uses — see TODO
  `efdad99`) so Project Files' double-click, drag-drop, and any other
  `find_view_handler` caller pick up the new location automatically, no
  caller-side change needed.
- `widgets/svg_viewer/` is deleted entirely (not deprecated/kept around) —
  matching the precedent set by the File Explorer → Project Files rename
  (TODO `8385dcc`): no attempt is made to migrate a `.desk` file with a
  previously-placed "SVG Viewer" instance; such an instance simply becomes
  unresolvable, the same kind of break that rename already accepted.

### Supported element types

The SVG Editor's closed set of editable object types — the ones the
toolbox offers a create-tool for, and the only elements the points/shapes
tools understand — is SVG's basic shape primitives plus text:

`<rect>`, `<circle>`, `<ellipse>`, `<line>`, `<polyline>`, `<polygon>`,
`<path>`, `<text>`

This is a deliberate, closed scope decision (see Non-Goals) rather than
"everything SVG can express" — these are the elements every "basic
toolbox" vector editor starts with, and each maps cleanly onto a `QGraphicsItem`
subclass with well-defined "points" (vertices) vs. "shape" (whole-object)
editing semantics. `<path>`'s points are its segment endpoints/control
coordinates (the `M`/`L`/`C`/`Q`/`Z`/etc. coordinate pairs in its `d`
attribute) — full separate-handle editing of cubic/quadratic control
points specifically (as opposed to just segment endpoints) is a
reasonable stretch goal within the points tool, not a hard requirement
for a first pass.

### SVG Editor widget

New `widgets/svg_editor/` (`kind: "python"`), same Open/file-watcher/
auto-reload/Save shape as every other file-backed widget here. Internals:

- **Document model**: parse with the standard library's
  `xml.etree.ElementTree` (no new dependency, per `CLAUDE.md`) into a
  list of recognized objects (see above) plus a verbatim-preserved
  remainder for anything unrecognized; serialize the same way on save.
- **Canvas**: a `QGraphicsView`/`QGraphicsScene`, one custom
  `QGraphicsItem` subclass per supported element type, each knowing how
  to paint itself and how to read/write its own SVG attributes — the
  editable analogue of `QSvgRenderer`'s read-only rendering.
- **Toolbox**: one button per creatable type (Rectangle, Circle, Ellipse,
  Line, Polyline, Polygon, Path, Text) plus the Points and Shapes editing
  tools, all mutually exclusive (a `QButtonGroup` of checkable buttons —
  "Select"/Shapes tool active by default). Choosing a create tool arms
  "place a new object of this type on the next click/drag" the same way
  most vector editors' click-drag-to-size gesture works; choosing Points
  or Shapes changes what selecting an existing object shows (vertex
  handles vs. whole-object transform handles + a small fill/stroke/
  stroke-width property panel).
- Registered as the built-in `.svg` **edit** handler (see below), rather
  than needing the user/an agent to configure that via the file type
  registry editor themselves for this to work out of the box.

### Wiring SVG Editor into the existing Edit button / edit-handler chain

`DeskWindow.open_editor_or_scrap` (TODO `da4f9c0`) already checks
`find_edit_handler` (a *registered*, dynamic-registry-only lookup — no
built-in fallback, per `find_edit_handler`'s own docstring) before
falling back to the built-in text editor for a text file, or a scrap
otherwise. Today there's no built-in-by-suffix edit fallback at all,
because until now there was no dedicated non-text editor for any type
`find_view_handler`'s builtin table already covers. Introduce
`BUILTIN_EDIT_WIDGET_BY_SUFFIX = {".svg": "svg_editor"}` in
`src/desk/file_type_registry.py`, and have `find_edit_handler` fall back
to it the same way `find_view_handler` already falls back to
`BUILTIN_VIEW_WIDGET_BY_SUFFIX` — otherwise clicking Edit on a `.svg`
loaded in Image Viewer would silently open it in the plain text Editor
widget by default (a `.svg` file is valid UTF-8 text, so
`looks_like_text_file` would say yes) even after a dedicated SVG Editor
widget exists, which would be a regression in usefulness the same way
skipping a built-in view fallback would have been in TODO `efdad99`.
With this in place, Image Viewer needs **no changes at all** to its own
`_edit_current_file`/Edit button — it already just calls
`current_context.get_editor_or_scrap_opener()`, which now resolves to
SVG Editor for a `.svg` automatically.

## Open Questions

- Whether `<path>`'s control-point editing (as opposed to just segment
  endpoints) makes the first pass or is deferred — see [Supported
  Element Types](#supported-element-types).
- Exact property panel contents for the Shapes tool beyond fill/stroke/
  stroke-width (opacity? stroke-dasharray?) — start minimal, expand if
  it proves too limiting in practice.

## Future Work

- In-widget zoom/pan for Image Viewer (already parked separately).
- Multi-select, layers, grouping, gradients/filters.
- Undo/redo.
