# Plan: TODO 4d21e7c (COMPLETED) — Image Viewer gains SVG (vector) rendering; retire SVG Viewer

## Summary

See `design-docs/svg-viewing-and-editing.md`'s "Image Viewer: raster +
vector" section. `ImageViewerWidget` (`widgets/image_viewer/widget.py`)
and `SvgViewerWidget` (`widgets/svg_viewer/widget.py`) are already
near-identical in shape (Open/Edit toolbar, `SingleFileWatcher`-driven
auto-reload, `desk.geometry.fit_rect`-based aspect-preserving paint) —
the only real difference is the rendering backend (`QPixmap` vs.
`QSvgRenderer`). Fold `_AspectSvgView` into Image Viewer as a second
internal view, dispatched on file extension, and delete the standalone
widget entirely.

## `widgets/image_viewer/widget.py`

- Import `QSvgRenderer` (`PyQt6.QtSvg`) and bring in `_AspectSvgView`
  verbatim from `widgets/svg_viewer/widget.py` (unchanged — it's already
  self-contained: load/is_valid/clear/paintEvent against its own
  `QSvgRenderer`).
- `IMAGE_FILTER` gains `*.svg *.svgz` in its filter string.
- Add `VECTOR_SUFFIXES = {".svg", ".svgz"}` and a small
  `_is_vector(path) -> bool` (`path.suffix.lower() in VECTOR_SUFFIXES`)
  — extension-based, not content-sniffed (see design doc's reasoning:
  SVG's XML preamble isn't cheaply distinguishable from other XML-ish
  text, and every other dispatch in `file_type_registry.py` is already
  extension-first).
- `ImageViewerWidget.__init__`: construct both `self._raster_view =
  _AspectImageView()` and `self._vector_view = _AspectSvgView()`, add
  both as pages of a `QStackedLayout` (or a plain container `QWidget`
  with a `QStackedLayout` set as its layout), added to the toolbar/
  layout in place of the single `self._view` that exists today.
- `set_file(path)`: after resolving which page is active
  (`self._is_vector(path)`), route `_reload()`'s `data = path.read_bytes()`
  /load call to whichever view is current, and call
  `self._stack.setCurrentWidget(...)` before loading so the correct page
  is visible even before the load result is known (matches existing
  `_show_placeholder`/`_reload` structure — both views already handle
  their own invalid/empty state independently, no shared state needed
  beyond "which one is on top").
- `_reload()`: dispatch to `self._raster_view.load(data)` or
  `self._vector_view.load(data)` based on the same `_is_vector` check;
  keep the existing "no file" / `FileNotFoundError` / `OSError` /
  invalid-content label branches, just parameterized by which view's
  `is_valid()`/error message applies.
- `IMAGE_FILTER` error text ("is not a valid image file") stays generic
  enough to cover both cases; no separate vector-specific message needed
  unless testing surfaces a reason to.
- No changes needed to `_edit_current_file`/the Edit button — see
  "Edit button wiring" below, this widget's own code doesn't need to
  know anything changed there.
- Update the class docstring's "same shape as `widgets/svg_viewer/
  widget.py`" comment (that widget won't exist anymore).

## `src/desk/file_type_registry.py`

`BUILTIN_VIEW_WIDGET_BY_SUFFIX[".svg"]`: `"svg_viewer"` → `"image_viewer"`.

(`BUILTIN_EDIT_WIDGET_BY_SUFFIX` is TODO `7076af5`'s concern, not this
one — no edit-handler change here.)

## Delete `widgets/svg_viewer/`

`git rm -r widgets/svg_viewer/` — its rendering logic now lives in Image
Viewer; no back-compat shim, matching the TODO `8385dcc` File Explorer →
Project Files precedent (a previously-placed "SVG Viewer" instance in an
existing `.desk` file simply becomes unresolvable, same kind of break
already accepted there).

## Docs

- `design-docs/architecture.md`: update its widget list/component entry
  that currently describes a standalone SVG Viewer widget (grep first to
  find the exact entry) to instead describe Image Viewer's raster+vector
  support.
- Leave historical `plans/svg-viewer-widget.md`, `TODO.md`'s completed
  `c7d6e4d` entry, and `LEARNINGS.md` mentions untouched — those are
  history, not current-state docs (same distinction already applied
  during the Project Files rename).
- Check `plans/image-drop-tempui.md`/other *forward-looking* docs found
  via grep for `svg_viewer`/`SvgViewerWidget`/`SVG Viewer` — anything
  that describes *current* behavior (not a historical "what we did and
  why" narrative) gets updated; anything narrating past work stays as-is.

## Verification

- Real `ImageViewerWidget` (headless, `QApplication`): loading a `.png`
  fixture shows the raster page and renders correctly; loading a real
  `.svg` fixture shows the vector page and renders correctly (both via
  `set_file`, and via the Open-dialog code path if easily exercisable
  headlessly); loading an invalid/corrupt file of each kind shows the
  right error label without crashing.
- `file_type_registry.find_view_handler` resolves `.svg` to
  `"image_viewer"` (both via the builtin fallback with an empty dynamic
  registry, and confirming no `svg_viewer` string remains anywhere in
  `file_type_registry.py`).
- `widgets/svg_viewer/` no longer exists; nothing under `widgets/`,
  `src/desk/`, or current (non-historical) docs still imports/references
  `SvgViewerWidget`/the `svg_viewer` widget id.
- Full scratchpad regression suite (`git stash` before/after), checking
  for any script that hardcodes `widgets/svg_viewer` or the `svg_viewer`
  widget id (expected to need the same kind of path/id fixup already
  seen for the Project Files rename and the `build_widget.py` move).
