# Plan: TODO efdad99 (COMPLETED) — File Explorer viewer/editor/scrap fallback chain

## Summary

Replace `FileExplorerWidget._open_index`'s unconditional "always open
the Editor widget" with a three-step fallback, using TODO b5d52c0's file
type registry: (1) a registered viewer, (2) a registered editor or (for
a file with no registry match at all) the built-in Editor widget *only*
if the file is genuinely text, (3) a Scratch note explaining that
nothing can open it. Whichever actually gets used is placed **centered
in the current view** — a real behavior change from today's `(0, 0)`
placement, needed for all three outcomes, not just the new ones.

## New lookup helpers (`src/desk/file_type_registry.py`)

```python
import mimetypes

# Generalizes desk.shell.window.EXTERNAL_DROP_WIDGET_BY_SUFFIX (kept as
# a code-level floor, not replaced by it) plus raster image suffixes
# (desk.shell.window.IMAGE_DROP_SUFFIXES) -- so existing double-click
# behavior for these known types doesn't regress just because the
# dynamic registry starts out empty for a fresh Desk.
BUILTIN_VIEW_WIDGET_BY_SUFFIX = {
    ".md": "markdown",
    ".svg": "svg_viewer",
    ".png": "image_viewer", ".jpg": "image_viewer", ".jpeg": "image_viewer",
    ".gif": "image_viewer", ".bmp": "image_viewer", ".webp": "image_viewer",
    ".tif": "image_viewer", ".tiff": "image_viewer", ".ico": "image_viewer",
}

def find_view_handler(registry, path) -> str | None:
    return _find_handler(registry, path, "view") or BUILTIN_VIEW_WIDGET_BY_SUFFIX.get(path.suffix.lower())

def find_edit_handler(registry, path) -> str | None:
    return _find_handler(registry, path, "edit")

def _find_handler(registry, path, role) -> str | None:
    """Extension match first (case-insensitive), then MIME type
    (mimetypes.guess_type) -- "keyed by both," per the original ask."""
    ...

def looks_like_text_file(path, sniff_bytes=8192) -> bool:
    """Null-byte + UTF-8-decodability sniff on the first sniff_bytes --
    a self-contained heuristic (no new dependency, per CLAUDE.md) that
    correctly treats an unknown-extension text file (a Dockerfile, a
    dotfile) as text and a real binary as not, unlike a fixed extension
    allowlist."""
    ...
```

## Centered placement hook (new, since today's `get_widget_opener()`
always places at `(0, 0)`)

- `current_context.py`: new `set_centered_widget_opener`/
  `get_centered_widget_opener` pair, same shape as every other hook
  here.
- `DeskWindow.open_widget_content_centered(self, widget_id, size=None,
  instance_id=None) -> QWidget | None`: looks up `self._widgets.get
  (widget_id)`, computes `self.view.mapToScene(self.view.viewport()
  .rect().center())` (the same centering math
  `_place_discuss_claude_widget`/`_auto_place_new_custom_widget` already
  use), calls `self.open_widget_content(widget_id, pos=(center.x(),
  center.y()), size=size or widget.default_size, instance_id=
  instance_id)`.
- `DeskWindow.__init__`: `current_context.set_centered_widget_opener
  (self.open_widget_content_centered)`.

## File Explorer (`widgets/file_explorer/widget.py`)

`_open_index` becomes a thin wrapper calling a new `_open_file(path)`:

```python
def _open_file(self, path: Path) -> None:
    opener = current_context.get_centered_widget_opener()
    if opener is None:
        return
    registry = [entry_from_dict(d) for d in self._file_type_registry]
    widget_id = find_view_handler(registry, path)
    if widget_id is None:
        widget_id = find_edit_handler(registry, path)
    if widget_id is None and looks_like_text_file(path):
        widget_id = "editor"  # the built-in text Editor, only for genuine text
    if widget_id is not None:
        self._open_in_widget(opener, widget_id, path)
        return
    self._open_as_unopenable_scrap(opener, path)

def _open_in_widget(self, opener, widget_id, path) -> None:
    widget = opener(widget_id)
    if widget is not None and hasattr(widget, "set_file"):
        try:  # TODO 810a5d6: must never propagate out of this Qt slot
            widget.set_file(path)
        except Exception:
            logger.error(...)

def _open_as_unopenable_scrap(self, opener, path) -> None:
    widget = opener("scratch")
    if widget is None:
        return
    widget.set_label(f"Can't open {path.name}")
    widget.body.setPlainText(
        f"No viewer or editor is registered for this file type "
        f"({path.suffix or 'no extension'}), and it doesn't look like "
        f"plain text."
    )
```

`_open_index` itself keeps its existing `index.isValid()`/directory
guard, resolves `path`, and calls `_open_file(path)`.

## Verification

- `find_view_handler`/`find_edit_handler`: registry match by
  extension, by MIME type, the built-in-suffix floor when the registry
  has nothing, and `None` when nothing matches at all.
- `looks_like_text_file`: a real plain-text file -> `True`; a file
  containing a null byte / invalid UTF-8 -> `False`.
- File Explorer, on a real `QApplication`/fake centered-opener double:
  a registry `view` match opens that widget; no `view` but an `edit`
  match opens that; no registry match but a real text file opens
  `"editor"`; no registry match and a binary file places a `"scratch"`
  widget with an explanatory label/body instead; the opener is always
  called for a *centered* placement (verified by checking the fake
  opener recorded the widget_id, not position -- position centering
  itself is `DeskWindow.open_widget_content_centered`'s own job,
  covered by a direct test of that method on a real `WorkspaceView`).
- Full scratchpad regression suite (`git stash` before/after).
