# Drag-and-drop image → saved into `.desk_temp`, displayed via tempui (COMPLETED)

TODO `6e731c1`.

## Summary

Today, dropping a file onto the Workspace Canvas (TODO `5915ac2`)
opens it *by reference* in whichever widget its extension maps to
(`EXTERNAL_DROP_WIDGET_BY_SUFFIX`), falling back to the Editor — which
means a dropped raster image (`.png`, `.jpg`, ...) currently falls
through to the Editor and renders as garbage text (there's no image
-aware entry in that map, and no image-viewing widget exists at all
yet). Per this item, a dropped image should instead be **copied into
`.desk_temp`** and displayed through a new tempui pointer keyword,
`OpenImage` — mirroring `OpenMarkdown`'s existing shape, and giving
this new capability to any tempui author (agent or script), not just
the drag-and-drop path.

Four pieces: a new `Image Viewer` widget (`kind: "python"`), a new
`OpenImage` DSL keyword (`desk.temp_ui`), drag-and-drop wiring
(`DeskWindow._on_files_dropped`) that special-cases image suffixes,
and a small `desk.geometry.fit_rect` extraction so the new widget
shares its aspect-preserving scaling math with the existing SVG
viewer instead of duplicating it.

## Design

### `desk.geometry.fit_rect`

`widgets/svg_viewer/widget.py`'s private `_fit_rect(content_size,
container_size) -> QRectF` (centered, aspect-preserving, letterboxed)
is exactly what an image viewer also needs — extracted verbatim into a
new `src/desk/geometry.py` module, imported by both. Not a speculative
abstraction: it's the same real math needed twice, not once.

### New DSL keyword: `OpenImage`

Same shape as `OpenMarkdown` — a pure fire-and-forget pointer, no
inline-content sibling (unlike `Markdown`, this item doesn't ask for
one, and raster image bytes don't belong inline in a text DSL file the
way markdown text does):

- `desk.temp_ui.OPEN_IMAGE_KEYWORD = "OpenImage"`, added to
  `RESERVED_TEMPUI_KEYWORDS`.
- `detect_temp_ui_kind` recognizes it, returning `"open_image"`.
- `parse_open_image(text) -> str | None` — identical shape to
  `parse_open_markdown`.
- A new split doc, `tempui-image.md` (own file, not folded into
  `tempui-markdown.md`: unlike `OpenMarkdown`/`Markdown`, there's no
  second, content-form keyword to cross-reference — same "single
  -keyword, own file" precedent as `tempui-discuss-parking-lot
  -item.md`), linked from `desk-temporary-ui.md`'s intro list ("seven"
  → "eight built-in file types"). `TEMPUI_DOC_VERSION` bumped
  `9 -> 10`.

### New widget: `widgets/image_viewer/`

`kind: "python"`, structurally a near-twin of `widgets/svg_viewer/
widget.py` (open button + `QFileDialog`, `set_file`/`SingleFileWatcher`
-driven auto-reload, `external_path_changed` for the `[EXTERNAL]`
marker) — the only real difference is rendering a `QPixmap` (loaded via
`QPixmap.loadFromData`) instead of a `QSvgRenderer`, through the shared
`fit_rect` helper in a custom `paintEvent` (not `QLabel.setScaledContents
(True)`, which stretches non-uniformly — the exact pitfall the SVG
viewer's own comment already calls out for `QSvgWidget`).

### Drag-and-drop wiring

`DeskWindow._on_files_dropped` currently does one thing for every
dropped path: look up `EXTERNAL_DROP_WIDGET_BY_SUFFIX` (or fall back
to Editor) and `set_file` it *by reference*. A new
`IMAGE_DROP_SUFFIXES` set (`.png .jpg .jpeg .gif .bmp .webp .tif .tiff
.ico` — deliberately excludes `.svg`, which already has correct,
existing by-reference handling via `EXTERNAL_DROP_WIDGET_BY_SUFFIX`
and isn't raster data needing a copy) is checked first; a match routes
to a new `_drop_image_as_temp_ui(path, pos)` instead of the generic
by-reference path — everything else is unchanged.

`_drop_image_as_temp_ui`:

1. Reads the dropped file's bytes and writes them to
   `.desk_temp/<8-hex>-<original filename>` (a short random prefix
   avoids collisions across repeated drops of same-named files, while
   keeping the original name readable for a human browsing the
   directory — original bytes/format preserved as-is, no re-encoding,
   unlike the existing clipboard-image paste path which re-encodes to
   PNG since a `QImage` from the clipboard has no "original file
   bytes" to preserve).
2. Writes a new UUID-named tempui file, `OpenImage <saved filename>`,
   into the same `.desk_temp` directory — suppressed via
   `TempUiManager.record_own_write` (same mechanism `_paste_text_as_
   temp_ui` already uses) so the directory watcher doesn't also fire a
   redundant top-right notification for a file about to be opened
   immediately anyway.
3. Immediately places and binds an Image Viewer instance at the drop
   position (`open_widget_content` + `_bind_temp_ui_content`, the same
   two-step every other tempui-file-driven placement uses) — matches
   how every *other* dropped file type already places immediately, no
   notification-then-click detour, and matches `_paste_text_as_temp_
   ui`'s own "write the tempui file for real, but don't make the user
   click a notification for their own just-performed action" shape.

Generic tempui plumbing gains matching entries for `"open_image"`,
mirroring every existing `"open_markdown"` case exactly:
`IMAGE_VIEWER_WIDGET_ID` (added to `TEMP_UI_WIDGET_IDS`, for the
usual instance_id-equals-source-file-uuid reload reconnection),
`_temp_ui_widget_id_for`, `_bind_temp_ui_content` (a new
`_resolve_open_image_target` static method, identical shape to
`_resolve_open_markdown_target`), and `_notify_temp_ui`'s notification
-text branch (relevant for an `OpenImage` file an agent writes
directly, not just the drag-and-drop path — same "general DSL
capability, not only reachable one way" spirit as every other
keyword).

## Affected files

- `src/desk/geometry.py` — new, `fit_rect`.
- `widgets/svg_viewer/widget.py` — import `fit_rect` from
  `desk.geometry` instead of its own private copy.
- `src/desk/temp_ui.py` — `OpenImage` keyword, `detect_temp_ui_kind`,
  `parse_open_image`, `_IMAGE_DOC`/`IMAGE_DOC_FILENAME` +
  `SPLIT_DOC_CONTENT` entry, `TEMPUI_DOC_VERSION` bump, `DOC_TEMPLATE`
  intro-list update.
- `widgets/image_viewer/widget.json` / `widget.py` — new widget.
- `src/desk/shell/window.py` — `IMAGE_VIEWER_WIDGET_ID`,
  `TEMP_UI_WIDGET_IDS`, `IMAGE_DROP_SUFFIXES`, `_on_files_dropped`'s
  branch, `_drop_image_as_temp_ui`, `_temp_ui_widget_id_for`,
  `_bind_temp_ui_content`/`_resolve_open_image_target`,
  `_notify_temp_ui`.

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`):

- `fit_rect` (moved, not rewritten) — a quick regression against its
  existing behavior, plus the SVG viewer's own existing behavior
  unaffected by the import change.
- `detect_temp_ui_kind`/`parse_open_image`/`RESERVED_TEMPUI_KEYWORDS`
  for the new keyword; `ensure_docs_current` refreshing a
  version-9-stuck doc directory to 10 with `tempui-image.md` present
  and linked from the main doc.
- The Image Viewer widget: placeholder state, `set_file` loading a
  real image (correct scaled/letterboxed render, non-empty pixmap),
  live-reload via a real `SingleFileWatcher` change, missing
  -file/invalid-image error messages, `[EXTERNAL]` marker wiring, and
  the "Open" button's `QFileDialog` path (`set_file` called with the
  chosen path — not driving the real native dialog).
- `discover_widgets` picks up the new manifest; a real
  `PythonWidgetHost` builds a working instance.
- A full real `DeskWindow` regression (pointed at this project's own
  already-provisioned directory, same reasoning as TODO `dc557b2`'s
  plan) simulating a real drop of a real temp PNG file: confirms the
  file is genuinely copied into `.desk_temp` (byte-for-byte), exactly
  one new UUID-named `OpenImage` tempui file is written pointing at
  it, no spurious notification fires for that self-authored write, an
  Image Viewer instance is placed immediately at the drop position
  showing the real image, and a simulated app restart (a fresh
  `DeskWindow` over the same saved Desk) reconnects to the same
  `.desk_temp` file via the standard instance_id-equals-uuid
  mechanism. Also confirms non-image drops (e.g. `.md`) are entirely
  unaffected (regression of TODO `5915ac2`'s existing behavior).

## Status

Implemented as planned, plus one unplanned but necessary fix: the
`OpenImage` pointer path is written relative to the *Desk* directory
(`.desk_temp/<name>`), not just the bare saved filename -- matching
`OpenMarkdown`'s own documented convention, which
`_resolve_open_image_target` resolves against (an early version wrote
the bare filename, which resolved against the wrong base directory and
was caught by the DeskWindow regression check below).

Also found and fixed a real, pre-existing bug in
`desk.file_watch.SingleFileWatcher` (not introduced by this change,
but directly blocking this item's own live-reload requirement):
watching a binary file crashed its internal `read_text()` call with an
uncaught `UnicodeDecodeError`, silently killing the `changed`
notification. Fixed by also catching that alongside the existing
`OSError` handling. See the new `LEARNINGS.md`-style note in the
fix's own comment and TODO `6e731c1`'s `TODO.md` entry for the full
summary.

The DeskWindow-level regression test used an isolated,
pre-provisioned temp project directory rather than this project's own
directory (unlike TODO `dc557b2`/TODO `7505703`'s plans) -- this test
performs real file writes and a real `save_current_desk()`, so
touching the real repo wasn't an acceptable risk; pre-creating
`.desk_temp` and calling `write_tempui_docs` directly avoids both the
`_provision_temp_ui` confirmation-dialog hang and any risk to real
files (a plain tempdir is also never inside a git repo, so the
`.gitignore` prompt is skipped too).
