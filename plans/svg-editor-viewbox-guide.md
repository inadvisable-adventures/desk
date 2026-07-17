# Plan: TODO d1d176f — SVG Editor: viewBox guide, Reset View, bounded scene, hexagon preview mask

Source: `../FEEDBACK/FEEDBACK-DESK-svg-editor-viewbox-guide-2026-07-16-1156.md`
(a `widgets/feedback/` note left for a future Claude instance working on
Desk itself — see `design-docs/` for the Feedback widget). Concrete
problem it documents: the SVG Editor never renders its own document
bounds (`viewBox`/`width`/`height`) anywhere, so a view that drifts
during editing leaves shapes drawn far outside the exportable area with
zero visual indication — the editor shows them fine (it never clips
while editing), but any real SVG consumer (a browser, an `<img>`/
`<image>` tag) clips strictly to `viewBox` and renders nothing. Traced
to a real, concrete case: a `necro-4x` `terrain-types-editor` widget's
`grassy-hills.svg`, whose shapes ended up 250–950 units outside its own
`0 0 400 300` viewBox.

## Design

All new scene items here are plain `QGraphicsItem`s added directly to
`self._scene`, **never** touching `self._root`/`self._objects` — since
`_save_to_path` only ever serializes `self._objects` (each syncing back
into its own already-parsed `ET.Element`) via `ET.tostring(self._root,
...)`, anything added to the scene this way is automatically excluded
from the saved file with no separate bookkeeping needed (confirmed
directly: this is exactly how `_Handle` already works today).

- **`_document_bounds(root: ET.Element) -> QRectF`** (module-level
  helper): the document's real exportable bounds. Primary source is
  `viewBox` (`min-x min-y width height`, space-separated); falls back
  to a `0,0,width,height` rect from the `width`/`height` attributes
  (stripping a trailing unit suffix, e.g. `"400px"`) if `viewBox` is
  absent/unparseable; falls back to `_new_empty_root`'s own `0 0 400
  300` default if neither is usable. Needed because a hand-authored or
  externally-produced `.svg` opened via `_load_file` isn't guaranteed
  to have a clean, unitless `viewBox`.

- **Bounds guide rect** (feedback's fix 1): a `QGraphicsRectItem`
  matching `_document_bounds`, dashed pen, no fill, `setAcceptedMouseButtons
  (Qt.MouseButton.NoButton)` (click-through — Qt's own mechanism for
  "don't intercept mouse events, but still receive/paint," the correct
  way to make a `QGraphicsItem` non-hittable without also making the
  scene ignore it visually), `zValue` far below every real object's
  default (`-1000`) so it never visually competes with drawn content.
  Tracked as `self._bounds_guide_item`, rebuilt (remove old, add new)
  by a `_refresh_document_guides()` method whenever bounds might have
  changed: `__init__` and the end of `_rebuild_scene_from_root`
  (`_scene.clear()` wipes every scene item, guide included — must be
  re-added every time, not just once).

- **Bounded scene rect** (feedback's fix 3, "optional" but cheap and
  low-risk given fix 1/2 already need `_document_bounds`): the same
  `_refresh_document_guides()` also calls `self._scene.setSceneRect(...)`
  — the document bounds expanded by a margin proportional to the
  document's own size (`max(width, height)` on each side, so a small
  400×300 doc gets a modest margin and a much larger document gets a
  proportionally larger one) rather than a fixed pixel constant.
  Deliberately generous, not exactly equal to the document bounds —
  drawing slightly outside the canvas mid-edit, before trimming, is
  reasonable (per the feedback's own framing) — just no longer
  effectively unbounded.

- **Reset View / Zoom to Fit Document** (feedback's fix 2): a
  `QPushButton("Reset View")` in `top_toolbar`, calling
  `self._view.fitInView(_document_bounds(self._root),
  Qt.AspectRatioMode.KeepAspectRatio)`. Also called automatically at
  the end of `_load_file` (opening/reloading a document should show its
  actual bounds, not wherever the view transform happened to be left
  from a previous document) and once at startup for a brand-new empty
  document — deferred via `QTimer.singleShot(0, self._reset_view)`
  since `fitInView` needs the view's real viewport size, not available
  yet at `__init__` time before the widget has actually been laid
  out/shown (a well-known Qt gotcha, not specific to this codebase).

- **Hexagon preview overlay** (the feedback's "additional feature,
  specifically requested"): a checkable `QPushButton("Hex Preview")` in
  `top_toolbar`, toggling `self._hex_preview_enabled`. When on, a
  `QGraphicsPathItem` is added: `QPainterPath` for the full document
  rect, `.subtracted(hexagon_path)` (Qt's own boolean path algebra —
  simpler and more robust than hand-building an even-odd-fill path),
  where `hexagon_path` is a regular hexagon centered in the document
  bounds, radius `min(width, height) / 2` (the largest hexagon that
  fits inside the bounds without touching the shorter edge). Semi
  -transparent dark fill, no stroke, `setAcceptedMouseButtons
  (Qt.MouseButton.NoButton)` (click-through, same mechanism as the
  guide rect — editing must work identically whether the preview is
  toggled on or off), `zValue` above everything including handles
  (`2000`) so the mask is always genuinely on top, visually. Tracked as
  `self._hex_preview_item`; toggling and every scene rebuild both go
  through one `_refresh_hex_preview()` method (add-if-enabled,
  remove-if-present-and-now-disabled/rebuilding) so the toggle state
  persists correctly across a file reload.

## Verification

Extend the existing `tests/verify/verify_svg_editor_widget.py` (same
module-loading/`check()` pattern already established there), not a new
file:

- `_document_bounds`: a normal `viewBox`, a `viewBox` with a non-zero
  origin, `width`/`height` with a unit suffix and no `viewBox`, and a
  totally malformed root (falls back to the 400×300 default).
- The bounds guide item is present after `__init__` and after
  `_rebuild_scene_from_root` (i.e. survives a reload), and — the core
  regression this whole feedback is about — **never appears in a saved
  file's XML** (`_save_to_path` to a temp file, re-parse, confirm no
  extra top-level element beyond what was actually drawn).
- The guide item (and, when enabled, the hex-preview item) is
  click-through: a real `QGraphicsScene.itemAt`/mouse-press-style hit
  test at a point inside the document bounds but not over any real
  drawn object resolves to nothing selectable (or falls through to
  whatever's actually beneath), not the guide/mask.
- `setSceneRect` after `_refresh_document_guides()` is strictly larger
  than the raw document bounds on every side (contains the bounds with
  room to spare), scaling with document size.
- `_reset_view`: after panning/zooming the view away, calling it
  restores a transform that actually shows the document bounds
  (confirm via `self._view.mapToScene(self._view.viewport().rect())`
  containing the document bounds, not just "some transform changed").
- Hex preview toggle: off by default; toggling on adds exactly one
  `QGraphicsPathItem` to the scene with the expected path bounds
  matching the document; toggling off removes it; the toggle state is
  preserved (item re-added, not silently dropped) across
  `_rebuild_scene_from_root`; **never appears in a saved file** (same
  save/re-parse check as the guide rect).
- Full `tests/verify/` regression suite.
