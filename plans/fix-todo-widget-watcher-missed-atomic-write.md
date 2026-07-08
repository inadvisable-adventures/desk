# Fix: TODO widget's file watcher misses TODO.md saved via atomic write-then-rename (TODO 54b0a9f) (COMPLETED)

## Summary

TODO 54b0a9f: the TODO widget's own file watcher (`_SingleFileHandler` in
`widgets/todo/widget.py`) has the identical gap TODO bb65aab found and
fixed in `TempUiManager`'s directory watcher — a `TODO.md` saved via a
common "atomic write" idiom (write to a scratch name, then rename over
the target file — what many editors/safe-write tools do) is never
detected as an external change.

## Root cause

```python
def on_any_event(self, event: FileSystemEvent) -> None:
    if Path(event.src_path).resolve() != self._target_path:
        return
    ...
```

`event.src_path` is the field that matters for a direct
`FileCreatedEvent`/`FileModifiedEvent` (the file's own path), but for a
`watchdog` `FileMovedEvent` (what a rename-into-place produces),
`src_path` is the *old* (scratch) name and `dest_path` is where the file
actually ended up — comparing `src_path` against `self._target_path`
here fails for the exact same reason TODO bb65aab's investigation found
in `TempUiManager._DirectoryHandler.on_any_event`. The docstring already
anticipates "an editor's save-via-temp-file-then-rename dance" for
*debouncing* purposes, but the comparison itself never accounted for it.

## Affected files

- `widgets/todo/widget.py` (edit) — `_SingleFileHandler.on_any_event`.

## Design

Mirror the `TempUiManager` fix: use `event.dest_path` for a
`FileMovedEvent`, `event.src_path` for everything else.

```python
from watchdog.events import FileMovedEvent  # new import

def on_any_event(self, event: FileSystemEvent) -> None:
    raw_path = event.dest_path if isinstance(event, FileMovedEvent) else event.src_path
    if Path(raw_path).resolve() != self._target_path:
        return
    ...
```

No other change needed: the debounce timer logic below is unaffected —
it only cares that *a* relevant change happened, not which raw event
type triggered it.

## Verification

Entirely headless (`QT_QPA_PLATFORM=offscreen`), a real `TodoWidget`
watching a real `TODO.md` in a temp directory:

1. Regression repro (unfixed code): edit `TODO.md` via a
   scratch-name-then-`os.rename()` atomic write — confirm the widget's
   `_on_external_change` never fires (no reload, stale display).
2. Confirm the fix: identical repro against the fixed handler — confirm
   `_on_external_change` fires and the widget reloads the new content.
3. Regression: a plain (non-atomic) direct write to `TODO.md` still
   triggers the watcher correctly (unchanged behavior).

## Status

Implemented and verified headlessly:

1. Isolated confirmation of the exact mechanism: a real `FileMovedEvent`
   (`src_path=".../TODO.md.tmp"`, `dest_path=".../TODO.md"`) fails the
   old `src_path`-only comparison against the target path, and passes
   the new `dest_path`-aware one.
2. End-to-end: a real `TodoWidget` watching a real `TODO.md`, edited via
   scratch-name-then-`os.rename()` — `_file_change_relay.changed` fires
   and the widget's in-memory items correctly reflect the new content.
3. Regression: a plain (non-atomic) direct write to `TODO.md` is still
   detected exactly as before.
