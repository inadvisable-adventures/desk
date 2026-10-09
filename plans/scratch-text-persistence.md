# Scratch text persists across restarts (TODO `a7618c8`) (COMPLETED)

## Summary

A Scratch widget that isn't backed by a tempui file loses its label and
text when Desk restarts. Give each such instance a backing file under
`.desk_temp/scratch-text/<instance_id>.json` (`{"label", "text"}`), written
(debounced) on every edit and read back when the instance is restored.

## Affected files

- `widgets/scratch/widget.py` -- `set_backing_file(path)`, `label_changed`
  signal, debounced atomic save, `flush_pending_save()`.
- `src/desk/shell/window.py` -- bind the backing file in `_place_widget`
  (fresh and restore) for Scratch instances with no tempui file; flush in
  `_capture_desk_state`; delete the file when the widget is closed.
- `design-docs/widget-ux.md` or `architecture.md` -- one note.
- `tests/verify/verify_scratch_text_persistence.py` -- new.

## Design decisions

- **Subdirectory, not a top-level file.** The tempui watcher only looks at
  direct children of `.desk_temp` (`path.parent != self._directory`), so a
  file in `scratch-text/` can never be mistaken for a tempui file or raise a
  notification (a plain `.desk_temp/<id>` file could).
- **"Not attached to a file"** = `.desk_temp/<instance_id>` doesn't exist.
  A tempui-backed Scratch's instance id *is* that file's name, and it keeps
  its existing tempui restore path.
- **JSON with label and text**, so a renamed Scratch restores under its name.
- **Debounced (300 ms) atomic write** (temp file + `os.replace`); the desk
  save (`_capture_desk_state`) flushes any pending write so a quit never
  loses the last keystrokes.
- **Closing the widget deletes the file**, but first tombstones it into
  Recently Removed with `{label, text}` inlined in the tombstone state
  (`_tombstone_state`; Scratch is exempted from the tempui skip in
  `_tombstone_widget`). Revive applies it via `set_widget_local_storage`,
  which Scratch implements with no `get_` counterpart so ordinary desk
  saves don't copy text into the `.desk` file (a stale copy would clobber
  the fresher backing file on restore). A desk switch
  or quit leaves it alone.
- Restore order: the backing file loads first; `_bind_temp_ui_widget` is a
  no-op for a non-tempui id, so nothing overwrites it.

## Verification

New verify script: round-trip text+label through a fresh `DeskWindow`
restore, tempui-backed Scratch gets no backing file, close deletes it,
flush writes pending edits, file ignored by tempui filename detection.
Run the neighbouring scratch verify scripts too.

Browser launch was skipped (headless offscreen Qt verification only).
