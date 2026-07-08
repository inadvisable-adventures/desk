# Fix: Temporary UI notification missed for an atomically-written file (TODO bb65aab) (COMPLETED)

## Summary

TODO bb65aab: a real temp-UI file (a bare-UUID file under `.desk_temp/`,
proper `Question`/`Option` DSL content) appeared in this project's own
`.desk_temp/` directory while a real Desk session had this directory as
its current Desk, but no notification ever showed up in the app.

## Investigation

Reproduced directly against this project's real, already-provisioned
`.desk_temp/` directory (a real `DeskWindow`, headless):

1. **Ruled out**: the watcher not running/attached to the right
   directory, and the notification-stack display itself silently
   failing. Writing a temp-UI file with a plain `Path.write_text()` call
   after boot **is** detected — `TempUiManager.file_added` fires and a
   real banner is added to `TempUiNotificationStack._banners`, with a
   valid `sizeHint()`/position once the event loop gets a couple of
   turns to settle layout (an artifact of a *test script* not waiting
   long enough, not a product bug — a real running app's own event loop
   already does this naturally).
2. **Ruled out (weaker theory, timing doesn't support it)**: TODO
   c8f6fb3's Desk-switch crash killing the app before the notification
   could render. `test.desk`'s own mtime shows the crash-triggering
   switch attempt happened roughly 3 minutes *after* the temp-UI file
   appeared — plenty of time for a working notification (debounced only
   0.3s) to have shown and been seen, if the pipeline worked for however
   the file was actually written.
3. **Confirmed root cause**: writing the file via a common "atomic
   write" idiom — write to a scratch name, then rename into place (the
   same pattern this codebase's own `LEARNINGS.md`/`_SingleFileHandler`
   docstring in `widgets/todo/widget.py` already call out as something
   editors/safe-write tools do routinely) — is **not** detected at all.
   `watchdog` reports a rename/move as a `FileMovedEvent`, not a
   `FileCreatedEvent`/`FileModifiedEvent`. `_DirectoryHandler.on_any_event`
   (`src/desk/shell/temp_ui_manager.py`) only handles those two event
   types:

   ```python
   def on_any_event(self, event: FileSystemEvent) -> None:
       if event.is_directory:
           return
       path = Path(event.src_path).resolve()
       if path.parent != self._directory or not is_temp_ui_filename(path.name):
           return
       if not isinstance(event, (FileCreatedEvent, FileModifiedEvent)):
           return
       ...
   ```

   Worse: even if the `isinstance` check were widened, a
   `FileMovedEvent`'s `src_path` is the *scratch* name (e.g.
   `<uuid>.tmp`), which fails `is_temp_ui_filename` on its own — the
   early-return above happens before the type check is even reached, for
   an unrelated reason. The path that actually matters for a move is
   `event.dest_path` (where the file landed), not `src_path`. Confirmed
   directly: a real `DeskWindow`, writing to a scratch file then
   `os.rename()`-ing it into `.desk_temp/` under a proper UUID name,
   produces **zero** `file_added` events and no banner — silently, no
   error, exactly matching the reported symptom.

## Affected files

- `src/desk/shell/temp_ui_manager.py` (edit) — `_DirectoryHandler
  .on_any_event`.

## Design

Handle `FileMovedEvent` explicitly, using its `dest_path` (the file's
final location) instead of `src_path`:

```python
def on_any_event(self, event: FileSystemEvent) -> None:
    if event.is_directory:
        return
    if isinstance(event, FileMovedEvent):
        raw_path = event.dest_path
    elif isinstance(event, (FileCreatedEvent, FileModifiedEvent)):
        raw_path = event.src_path
    else:
        return
    path = Path(raw_path).resolve()
    if path.parent != self._directory or not is_temp_ui_filename(path.name):
        return
    ... (debounce/timer logic unchanged)
```

`TempUiManager._handle_change`'s existing "seen before → edited,
otherwise → added" classification (`_known_files`) needs no change: it's
keyed purely by filename, independent of which raw event type triggered
the call.

### Related, deferred: the TODO widget's single-file watcher has the same gap

`widgets/todo/widget.py`'s `_SingleFileHandler.on_any_event` compares
`event.src_path` against the exact watched `TODO.md` path — an editor
that saves via write-scratch-then-rename-over-`TODO.md` would report a
`FileMovedEvent` whose `dest_path` (not `src_path`) matches, missing the
external change for the identical underlying reason. Its own docstring
already anticipates "an editor's save-via-temp-file-then-rename dance"
for *debouncing* purposes, but not this destination-path gap. Not fixed
here (a different file, and not what TODO bb65aab reported) — noted in
`PARKINGLOT.md` instead.

## Verification

Entirely headless (`QT_QPA_PLATFORM=offscreen`), against this project's
own real, already-provisioned `.desk_temp/` directory:

1. Regression repro (unfixed code): a real `DeskWindow`, write a file to
   `.desk_temp/` via a scratch-name-then-`os.rename()` atomic write —
   confirm zero `file_added` events and no banner.
2. Confirm the fix: identical repro against the fixed handler — confirm
   `file_added` fires with the correct final path and a banner appears.
3. Regression: a plain (non-atomic) `Path.write_text()` new-file write
   still fires `file_added` as `add` (unchanged path, already verified
   working pre-fix).
4. Regression: editing an already-known file (a second write, or a
   rename-based rewrite, to a filename already seen) still classifies as
   `edited`, not `added`.

## Status

Implemented and verified headlessly, against this project's own real,
already-provisioned `.desk_temp/` directory:

1. Reproduced the exact bug against the unfixed handler: a real
   `DeskWindow`, writing a temp-UI file via scratch-name-then-
   `os.rename()`, produced zero `file_added` events and no banner.
2. Confirmed the fix: identical repro against the fixed handler —
   `file_added` fires with the correct final path, and a banner appears.
3. Regression: a plain (non-atomic) new-file write still classifies as
   `added` (unchanged).
4. Regression: editing an already-known file classifies as `edited`
   both via a plain rewrite and via an atomic write-then-rename over the
   same name — the fix doesn't only handle the "added" case.

All test artifacts (scratch/temp-UI files) were cleaned up afterward;
the pre-existing real temp-UI file this bug was originally observed with
(`.desk_temp/d22c6226-...`) was left untouched throughout.
