# Image Viewer: drag the loaded image out of the widget (TODO `8b88ec2`) (COMPLETED)

## Summary

The Image Viewer widget (`widgets/image_viewer/widget.py`) can already
receive an image *into* itself (the "Open" file dialog, `set_file`
called programmatically, or a file dropped onto the canvas — TODO
`6e731c1` — and, as of TODO `9d52dc4`, a pipeline's own `open_image`
verb output). Nothing lets it act as a drag *source*. This adds that:
a click-and-drag starting on the displayed image (raster or vector)
begins a native OS drag carrying the loaded file's own local-file URL,
so dropping it anywhere that already accepts a local-file drop — the
OS (Finder/another app), another spot on the Desk canvas, or another
placed widget's own drop target (e.g. the Pipeline widget's "Input"
box, TODO `9d52dc4`) — just works via the drop side's *existing*
handling. Nothing on any receiving side needs to change.

## Affected files

- **Modified: `widgets/image_viewer/widget.py`** — the drag-source
  behavior, scoped entirely to this widget.
- **New: `tests/verify/verify_image_viewer_drag_out.py`**.

Deliberately **not** modifying `src/desk/svg_view.py` — `SvgView` is
shared with the Markdown widget's own Mermaid-diagram rendering (TODO
`a9e2ba7`), which has no backing file to drag out at all (it's
rendered SVG *bytes*, not a path on disk). Making `SvgView` itself
draggable would either be meaningless there or require it to grow
file-awareness it has no business having. The drag gesture is
implemented once, at the `ImageViewerWidget` level (via an event
filter installed on `self._view_container`, the `QStackedLayout` host
for both `_raster_view` and `_vector_view`), which already knows
`self._current_path` — not duplicated per view type.

## Design

### Detecting the drag gesture

`ImageViewerWidget` installs itself as an event filter on
`self._view_container` and watches for `QEvent.Type.MouseButtonPress`
(left button — records the press position), `MouseMove` (once the
displacement from that position exceeds
`QApplication.startDragDistance()`, starts the drag and clears the
tracked press position so a second drag isn't started mid-drag), and
`MouseButtonRelease`/any other event (clears the tracked press
position). No existing mouse interaction lives on either view widget
today (confirmed: neither `_AspectImageView` nor `desk.svg_view
.SvgView` overrides any mouse event) — there is nothing to conflict
with.

### Building the drag

`_drag_mime_data(self) -> QMimeData | None`: `None` if
`self._current_path` is `None` or no longer an existing file (the
placeholder state, or a file that's since been deleted/moved out from
under the widget); otherwise a `QMimeData` with
`setUrls([QUrl.fromLocalFile(str(self._current_path))])` — exactly the
shape every existing local-file drop handler (`WorkspaceView`'s
`_local_file_urls`, the Pipeline widget's `_DropTarget
._local_image_url`) already reads. Split out as its own method,
separate from the actual `QDrag`/`.exec()` call, specifically so a
test can exercise the MIME-building logic without invoking a real,
blocking native drag loop (see "Verification").

`_start_drag(self) -> None`: gets the mime data from
`_drag_mime_data()` (no-ops if `None`); builds a `QDrag(self)`, sets
its mime data, sets a thumbnail pixmap for the drag cursor via
`self._active_view().grab()` (a real screenshot of whichever view is
currently showing — works identically for the raster and vector
cases, no separate rendering path needed) scaled down to a reasonable
cursor size; calls `drag.exec(Qt.DropAction.CopyAction)`.

## Key design decisions

- **File-URL drag, not image-data drag.** Considered also setting
  `mime.setImageData(...)` so an app with no interest in "a file" (only
  raw image bytes) could still accept the drop. Rejected for this pass
  — every drop target that currently exists in Desk itself (canvas,
  Pipeline widget) reads a local-file URL, not image data, and the OS
  file-manager/most apps' own image-drop handling already accepts a
  file URL directly. Easy to add later if a real need for the
  image-data form actually surfaces.
- **One event filter at the `ImageViewerWidget` level, not per-view
  subclassing.** Keeps `desk.svg_view.SvgView` (shared with the
  Markdown widget) and `_AspectImageView` untouched; the drag gesture
  only needs `self._current_path`, which only `ImageViewerWidget`
  itself tracks.
- **No modifier key required.** Matches ordinary OS image-viewer/
  browser drag-out conventions, and there's no existing content-area
  mouse interaction on this widget to collide with (confirmed
  directly, not assumed).

## Verification

`tests/verify/verify_image_viewer_drag_out.py`:

- `_drag_mime_data()` returns `None` with no file loaded (placeholder
  state).
- `_drag_mime_data()` returns `None` if `self._current_path` no longer
  exists on disk (deleted after loading).
- `_drag_mime_data()` returns a `QMimeData` whose `urls()` is exactly
  `[QUrl.fromLocalFile(str(path))]` for both a loaded raster file and a
  loaded `.svg` file (both dispatch through the same
  `ImageViewerWidget`-level method, regardless of `_active_view()`).
- The event-filter gesture: simulate a `MouseButtonPress` then a
  `MouseMove` *below* `QApplication.startDragDistance()` on
  `self._view_container` — `_start_drag` (patched) is **not** called;
  a further `MouseMove` that crosses the threshold — `_start_drag`
  *is* called exactly once, even with additional move events past that
  point (already in the middle of a drag, doesn't restart it);
  patching `_start_drag` rather than letting a real `QDrag.exec()` run
  avoids a blocking native drag loop in an automated test.
- A `MouseButtonRelease` before crossing the threshold cleans up the
  tracked press state (a fresh press afterward starts its own
  independent threshold check, not carrying over stale position data).

Full `tests/verify/` regression suite run after, to confirm nothing
else regressed (in particular `verify_image_viewer_svg_integration.py`
and anything exercising `_AspectImageView`/`SvgView` directly).
