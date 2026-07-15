# Plan: TODO da4f9c0 (COMPLETED) — Edit titlebar button on viewer widgets

## Summary

Give every file-content viewer widget (`svg_viewer`, `image_viewer`,
`markdown`) an "Edit" button in its own top toolbar row (each already
has one -- `Open` button + stretch + filename label, an identical
pattern across all three). Clicking it reuses the exact editor-or-scrap
fallback logic Project Files' own double-click chain (TODO efdad99)
already has for its own edit-or-scrap step -- extracted into one shared
`DeskWindow` method both call into, reached via a new `current_context`
hook (these are all `kind: "python"` widgets; see TODO 2da314f for
exposing the same service over the real Bridge API for `kind: "html"`
widgets separately).

## Shared service: `DeskWindow.open_editor_or_scrap`

New method, extracted from what TODO efdad99 built inline in
`ProjectFilesWidget._open_file`:

```python
def open_editor_or_scrap(self, path: Path) -> None:
    registry = [entry_from_dict(d) for d in self.get_file_type_registry_dicts()]
    widget_id = find_edit_handler(registry, path)
    if widget_id is None and looks_like_text_file(path):
        widget_id = "editor"
    if widget_id is not None:
        widget = self.open_widget_content_centered(widget_id)
        if widget is not None and hasattr(widget, "set_file"):
            try:  # TODO 810a5d6
                widget.set_file(path)
            except Exception:
                logger.error(...)
        return
    scratch = self.open_widget_content_centered("scratch")
    if scratch is None or not hasattr(scratch, "set_label") or not hasattr(scratch, "body"):
        return
    scratch.set_label(f"Can't open {path.name}")
    scratch.body.setPlainText(
        f"No editor is registered for this file type "
        f"({path.suffix or 'no extension'}), and it doesn't look like plain text."
    )
```

`current_context.py`: new `set_editor_or_scrap_opener`/
`get_editor_or_scrap_opener` pair, same shape as every other hook.
`DeskWindow.__init__`: `current_context.set_editor_or_scrap_opener
(self.open_editor_or_scrap)`.

## Refactor `ProjectFilesWidget._open_file` (`widgets/project_files/widget.py`)

Replace the inline edit-handler-lookup/text-sniff/scratch-fallback
logic with a call to the new shared hook, keeping only the "view"
lookup as this widget's own first step:

```python
def _open_file(self, path: Path) -> None:
    opener = current_context.get_centered_widget_opener()
    if opener is None:
        return
    registry = [entry_from_dict(d) for d in self._file_type_registry]
    widget_id = find_view_handler(registry, path)
    if widget_id is not None:
        self._open_in_widget(opener, widget_id, path)
        return
    editor_or_scrap = current_context.get_editor_or_scrap_opener()
    if editor_or_scrap is not None:
        editor_or_scrap(path)
```

`_open_in_widget` stays (still used for the "view" case);
`_open_as_unopenable_scrap` is removed -- it's now
`open_editor_or_scrap`'s own job, not duplicated here.

## Viewer widgets: `svg_viewer`, `image_viewer`, `markdown`

Each already has an identical toolbar shape (`Open` button, stretch,
filename label) and a `self._current_path: Path | None`. Add an `Edit`
`QPushButton` to each toolbar (right after `Open`), enabled only when
`self._current_path is not None` (toggled everywhere `_current_path` is
set or cleared, mirroring how each widget's own label already updates
at those points). Clicking it:

```python
def _edit_current_file(self) -> None:
    if self._current_path is None:
        return
    opener = current_context.get_editor_or_scrap_opener()
    if opener is not None:
        opener(self._current_path)
```

`markdown/widget.py` has an extra wrinkle: it can be tempui-bound (no
real `_current_path`, see its own `has_unsaved_local_edits`-style
duck-typed state) -- the `Edit` button should simply stay disabled in
that state too, same as when `_current_path` is `None` generally (no
special-case needed beyond the existing enabled-state toggle).

## Verification

- `DeskWindow.open_editor_or_scrap`: a registered edit handler is
  used; no registered handler but a real text file opens the built-in
  `"editor"`; no handler and a binary file opens a `"scratch"`
  fallback with the explanatory label/body -- on a real `WorkspaceView`
  double, mirroring TODO efdad99's own verification shape.
- `ProjectFilesWidget._open_file` still finds a view handler correctly,
  and now delegates the edit-or-scrap case to the shared hook
  (confirm it's actually called, e.g. via a fake
  `get_editor_or_scrap_opener` recording its calls).
- Each of the three viewer widgets: the Edit button is disabled with
  no file loaded, enabled once one is, and clicking it calls the
  shared opener with the currently-loaded path.
- Full scratchpad regression suite (`git stash` before/after).
