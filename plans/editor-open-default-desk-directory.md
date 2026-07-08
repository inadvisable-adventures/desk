# Code editor: "Open" defaults to the Desk's associated directory (TODO 14d14e7) (COMPLETED)

## Summary

TODO 14d14e7: the Editor widget's "Open" button (`EditorWidget._open_file`,
`widgets/editor/widget.py`) should default to the current Desk's
associated directory instead of the user's home directory.

## Background

`plans/code-editor-widget.md`'s Key Design Decisions explicitly deferred
this: at the time, no `python` widget had any way to learn the current
Desk's directory at all — building one-off plumbing for just this widget
would've preempted the Desk Bridge API's general solution. That gap no
longer exists: TODO d1205ef (the TODO widget) introduced
`desk.shell.current_context`, a minimal module-level get/set the TODO
widget already uses the same way this item wants — `EditorWidget` can use
the exact same mechanism, no new plumbing needed.

## Affected files

- `widgets/editor/widget.py` (edit).

## Design

`EditorWidget.__init__` currently seeds `self._last_dir = Path.home()`
unconditionally. Change it to prefer the current Desk's directory when
one is known:

```python
from desk.shell import current_context
...
self._last_dir = current_context.get_current_desk_directory() or Path.home()
```

This is the *initial* default only — exactly like the TODO widget's own
use of `current_context`, it's resolved once at construction, not
live-updated (see that module's docstring: no signal/notification
mechanism exists yet, and still isn't needed for a second caller with the
same "read once at construction" shape). `_last_dir` already gets
overwritten to the actually-opened/saved file's own directory after any
real `_load_file`/`_save_file`/`_save_file_as` call, same as today — this
change only affects what a *freshly-constructed* editor with nothing
open yet defaults to.

Update the class docstring (currently: "Deliberately has no automatic
awareness of the current Desk's associated directory") to reflect that
it now has this one piece of awareness, and drop the now-stale "Key
Design Decisions" cross-reference for that specific point (the rest of
`plans/code-editor-widget.md` is otherwise unaffected and stays as-is —
historical plans aren't rewritten after the fact).

### Known caveat (not fixed here)

Found while implementing this: `DeskWindow.switch_desk` has the same
`_load_desk_widgets`-before-`_refresh_picker` ordering bug TODO 1a051d1
fixed in `__init__` (`_refresh_picker` is the only place that updates
`current_context`, and it runs *after* `_load_desk_widgets` rebuilds any
saved widgets in `switch_desk` too) — so an `EditorWidget` that's part of
a Desk's *saved* state, reloaded via a Desk switch rather than freshly
placed, would still see the *previous* Desk's directory at that moment.
A freshly-placed `EditorWidget` (the right-click spawn menu, or the
common case of just opening the app) is unaffected, since
`current_context` is already correct by the time that path runs. Noted
in `PARKINGLOT.md` — the fix is the identical one-line reorder TODO
1a051d1 already did, just not this item's reported scope.

## Verification

Entirely headless (`QT_QPA_PLATFORM=offscreen`):

1. With `current_context.set_current_desk_directory(some_dir)` set before
   construction, confirm a fresh `EditorWidget._last_dir` equals
   `some_dir`.
2. With no current Desk directory set (`current_context`'s default,
   `None`), confirm a fresh `EditorWidget._last_dir` falls back to
   `Path.home()` — unchanged from today's behavior.
3. Regression: after `_load_file`/`_save_file_as` on a real temp file,
   `_last_dir` still updates to that file's own parent directory
   (existing behavior, unaffected by the constructor change).

## Status

Implemented and verified headlessly:

1. With `current_context.set_current_desk_directory(some_dir)` set
   beforehand, a freshly-constructed `EditorWidget._last_dir` equals
   `some_dir`.
2. With no current Desk directory known (`None`), a fresh
   `EditorWidget._last_dir` falls back to `Path.home()`.
3. Regression: after `_load_file` on a real temp file, `_last_dir` still
   updates to that file's own parent directory, unaffected by the
   constructor change.
