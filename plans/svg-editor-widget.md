# Plan: TODO 7076af5 (COMPLETED) — new SVG Editor widget

## Summary

See `design-docs/svg-viewing-and-editing.md`'s "Supported element types"
and "SVG Editor widget" sections for the overall shape. This plan pins
down the implementation-level decisions the design doc deliberately left
open, and trims a couple of things to a first-pass-sized scope (called
out explicitly below, not silently).

New `widgets/svg_editor/` (`kind: "python"`), single `widget.py` file
(matching every other widget in this repo — none split across multiple
modules within their own directory).

## Document model

- Parse with `xml.etree.ElementTree`. `ET.register_namespace("",
  "http://www.w3.org/2000/svg")` up front so a written-out document
  doesn't grow an `ns0:` prefix on every element.
- The parsed tree (`self._root: ET.Element`, the `<svg>` element) is the
  single source of truth — recognized-type wrapper objects hold a
  reference to their own live `ET.Element` (a direct child of root) and
  sync their current geometry/style *into* it only at save time
  (`sync_to_element()`), not continuously. Any element that isn't one of
  the recognized tags (comments, `<defs>`, anything else) is simply never
  touched — it stays in the tree exactly as parsed, giving verbatim
  round-tripping for free with no separate "passthrough" bookkeeping
  needed.
- New document / Save As with no existing file: a default `<svg
  xmlns="..." viewBox="0 0 400 300" width="400" height="300">` with no
  children.
- Style (fill/stroke/stroke-width) is read/written as plain presentation
  attributes (`fill=`, `stroke=`, `stroke-width=`) — **not** a `style="..."`
  CSS attribute. If a loaded element already has a `style=` attribute,
  it round-trips untouched but the property panel doesn't parse or edit
  it; scope trimmed here deliberately (CSS `style=` parsing is real added
  complexity for a first pass, and presentation attributes are equally
  valid SVG).

## Wrapper classes (one per supported type)

`RectObject`/`CircleObject`/`EllipseObject`/`LineObject`/
`PolylineObject`/`PolygonObject`/`PathObject`/`TextObject`, each pairing
a plain Qt graphics item with the shared interface:

- `from_element(element) -> Self` (classmethod, parses attributes into a
  new item)
- `create_default(scene_pos) -> Self` (classmethod, used by a toolbox
  create-tool click — see "Creating objects" below)
- `.item` — the `QGraphicsItem` added to the scene
- `.element` — the live `ET.Element`
- `sync_to_element()` — writes current item state back into
  `.element.attrib`

Backing Qt items: `QGraphicsRectItem` (rect), `QGraphicsEllipseItem`
(circle/ellipse — circle is just an ellipse with rx==ry, tracked
separately only so it round-trips back out as `<circle>` not
`<ellipse>`), `QGraphicsLineItem` (line), `QGraphicsPolygonItem`
(polygon — natively closed) — polyline needs its own thin
`QGraphicsPathItem` subclass instead, since `QGraphicsPolygonItem`
always closes the shape and a polyline must not. `PathObject` also
wraps a `QGraphicsPathItem`. `TextObject` wraps `QGraphicsSimpleTextItem`.

### `<path>` scope (called out explicitly, per the design doc's own
"stretch goal, not required" framing)

A first pass supports only straight-line path data: `M x,y L x,y L x,y
... [Z]` — built the same way as polyline/polygon creation (click to add
vertices), just serialized as a `<path d="...">` instead of `<polyline
points="...">`/`<polygon points="...">`. Curve commands (`C`/`Q`/arc)
are **not** parsed by the create/points tools; a loaded `<path>` whose
`d` contains anything beyond `M`/`L`/`Z` is left as an unrecognized,
inert element (round-trips untouched, per the document model above) —
not attempted to force into an editable object it can't accurately
represent. This is the "full control-handle editing... reasonable
stretch goal, not a hard requirement" note in the design doc, trimmed
all the way down to "not attempted in the first pass" for path *parsing*
specifically, not just control-point granularity.

## Creating objects (toolbox)

One toolbar button per type (`QButtonGroup`, checkable, mutually
exclusive with each other and with the Points/Shapes tools — "Select"
i.e. Shapes is the default active tool). **Click-to-place with a fixed
default size**, not click-drag-to-size — a simpler interaction for a
first pass (the design doc mentions drag-to-size as the usual vector
-editor gesture; this trims that to the simpler gesture, still lets you
immediately resize afterward via the Shapes tool once placed). Defaults:
rect 80×60, circle radius 30, ellipse rx/ry 40/25, line length 80
(horizontal), polyline/polygon/path built by successive clicks (Enter or
double-click to finish; polygon/path close automatically on finish,
polyline doesn't), text via `QInputDialog.getText` for its content
immediately on placement (font size defaults to 16).

## Points tool

Only meaningful for polyline/polygon/path objects (their own vertices)
and line (its two endpoints, reusing the same handle mechanism). A small
square `QGraphicsItem` handle per vertex/endpoint, shown only while the
Points tool is active *and* that object is selected; dragging a handle
updates that one coordinate in the backing point list and refreshes the
item's geometry live. Selecting a rect/circle/ellipse/text object while
Points is active shows no handles (nothing point-level to edit) — this
is expected, not an error state.

## Shapes tool

Selecting any object shows:

- **Move** — plain Qt drag (`ItemIsMovable`), works for every type.
- **Resize** — four corner handles (a small, reusable `_CornerHandle`
  class, positioned at the item's current `boundingRect()` corners).
  Dragging one:
  - rect/ellipse/circle: adjusts width/height (and circle constrains
    rx==ry from whichever corner delta is larger, so it stays a true
    circle rather than becoming an ellipse — if that's not wanted,
    switch it to an Ellipse object first, not a Circle).
  - line: the two "corners" collapse to its two endpoints — same handles
    the Points tool would show for it, functionally the endpoint-drag
    already covers "resize" for a line.
  - polyline/polygon/path/text: uniform scale of the whole bounding box
    from whichever corner is dragged (scales every point proportionally
    for the point-based types; scales font size proportionally to the
    bounding-box's own height change for text) — simpler than per-type
    custom resize semantics, and Points tool already covers precise
    per-vertex editing for the point-based types.
- **Property panel** — a small fixed side panel (not per-selection
  popup): two color-swatch buttons (fill, stroke — click opens
  `QColorDialog`) and a stroke-width spin box, all disabled until
  something is selected, applying immediately on change (no separate
  Apply button — matches this app's general "live" editing feel
  elsewhere, e.g. Markdown/Editor auto-reload).

## Toolbar / layout

- Top toolbar: Open / Save / Save As (same `SingleFileWatcher`
  -driven auto-reload-on-external-change shape as every other
  file-backed widget here — `_load_file`/`_reload` re-parses the whole
  document and rebuilds every wrapper+item from scratch, same as
  Markdown/Editor's own reload does for their own content).
- Left side: the toolbox (create-tool buttons, then a separator, then
  Points/Shapes tool buttons).
- Right side: the property panel (fill/stroke/stroke-width), visible
  regardless of tool but only enabled with a Shapes-tool selection.
- Center: a `QGraphicsView`/`QGraphicsScene` filling the remaining
  space.

## `src/desk/file_type_registry.py`

Add `BUILTIN_EDIT_WIDGET_BY_SUFFIX = {".svg": "svg_editor"}` and have
`find_edit_handler` fall back to it the same way `find_view_handler`
already falls back to `BUILTIN_VIEW_WIDGET_BY_SUFFIX` (registry match
first, then this builtin table). No other caller-side change needed —
Image Viewer's Edit button already goes through
`current_context.get_editor_or_scrap_opener()` →
`DeskWindow.open_editor_or_scrap` → `find_edit_handler`.

## Docs

`design-docs/architecture.md`: add a new numbered widget-list entry for
SVG Editor (there wasn't one for the retired SVG Viewer's *editing*
capability, since it never had one — this is genuinely new, not a
repurposed entry).

## Verification

- Real `SvgEditorWidget` (headless `QApplication`): create one of each
  supported type via its toolbox button, confirm the resulting
  `ET.Element` (after `sync_to_element()`) has the right tag and
  attributes; save and re-load a document, confirming every object
  round-trips (including an object that was moved/resized before save);
  an unrecognized element (e.g. a `<defs>` block or a curved `<path>`)
  present in a loaded file is still present, byte-for-byte in its own
  subtree, after a save with no edits.
- Points tool: dragging a polygon vertex handle updates that vertex only,
  confirmed via the object's own point list.
- Shapes tool: dragging a corner handle resizes correctly for a rect and
  an ellipse; the property panel's fill/stroke/stroke-width controls
  update the selected item's pen/brush and (after `sync_to_element()`)
  the element's attributes.
- `file_type_registry.find_edit_handler` resolves a bare `.svg` to
  `"svg_editor"` with an empty dynamic registry.
- Full scratchpad regression suite (`git stash` before/after).
