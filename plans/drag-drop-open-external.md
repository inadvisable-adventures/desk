# Drag-and-drop files onto the canvas open as external

TODO `5915ac2`.

## Summary

Dragging a real file from outside Desk (Finder, another app) onto the
Workspace Canvas should open it directly, in whatever widget kind
suits its extension, by *reference* to wherever it already lives on
disk -- never copied into the project first. "Opened as external" is
describing that mechanism (open-by-reference, exactly like
`OpenMarkdown`/a manually-opened external file), not a separate step:
the existing "[EXTERNAL]" titlebar indicator (TODO a053e3a) already
fires automatically for any file-backed widget whose source lives
outside the current Desk directory, so nothing new is needed there --
a dropped file (almost always outside the project) gets it for free
the moment it's opened via `set_file`.

## Key decisions

- **New `WorkspaceView.files_dropped` signal** (`list[Path]`,
  `QPointF` scene position), following the exact same shape as the
  existing `widget_add_requested` signal (right-click add-widget menu)
  -- `WorkspaceView` only knows "the user dropped these files here";
  `DeskWindow` decides what that means, same division of
  responsibility as every other view/window signal pair in this file.
- **`dragEnterEvent`/`dragMoveEvent`/`dropEvent` overridden on
  `WorkspaceView`** (a native `QGraphicsView`), accepting only when
  `event.mimeData().hasUrls()` and at least one URL `isLocalFile()` --
  rejects e.g. a browser-tab drag or an in-app text drag, neither of
  which this feature is for.
- **Extension -> widget-kind mapping, small and literal, not a new
  shared module.** Only three widget kinds currently expose `set_file`
  (Markdown, SVG Viewer, Editor) -- `.md` -> Markdown, `.svg` -> SVG
  Viewer, everything else -> Editor (Editor already handles arbitrary
  text by extension-based lexer choice, and is the sensible default
  for "some file, unknown type," matching File Explorer's own existing
  always-Editor behavior for its own "open" action). Kept as a plain
  dict in `window.py` next to the other widget-id constants -- pulling
  this out into `desk.file_kinds` or similar isn't justified for three
  entries and one call site; if TODO `f74945e` (clipboard-paste
  routing) later needs the same table, that's the point to extract it,
  not now.
- **Multiple dropped files fan out with the existing `WIDGET_SPACING`
  offset**, mirroring `_load_desk_widgets`'s own "no saved state"
  placement fallback, starting from the drop's scene position instead
  of `(0, 0)`.
- **Opened via `open_widget_content` + `set_file`**, the same two-step
  pattern already used for the TODO widget's "open plan" button and
  the paste-target-resolution code elsewhere in `window.py` -- no new
  opening mechanism needed.

## Affected files

- `src/desk/shell/canvas.py` -- `WorkspaceView.files_dropped` signal;
  `setAcceptDrops(True)`; `dragEnterEvent`/`dragMoveEvent`/`dropEvent`.
- `src/desk/shell/window.py` -- `_EXTERNAL_DROP_WIDGET_BY_SUFFIX` dict,
  `_EXTERNAL_DROP_DEFAULT_WIDGET_ID`; `_on_files_dropped`; wired in
  `__init__` alongside `widget_add_requested`.

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication`):

- `WorkspaceView`: a synthetic `QDropEvent` carrying file URLs is
  accepted and emits `files_dropped` with the right paths/scene
  position; one carrying no URLs (or a non-local URL) is not accepted
  and emits nothing.
- `DeskWindow._on_files_dropped` (unbound method on a fake double,
  matching this session's established `DeskWindow`-can't-construct
  -headlessly pattern): a `.md` path opens via the markdown widget id
  and calls `set_file` with that exact path; a `.svg` path opens via
  svg_viewer; an unrecognized extension falls back to editor; multiple
  paths in one drop each get a distinct, `WIDGET_SPACING`-offset
  position.

## Status

Not yet implemented.
