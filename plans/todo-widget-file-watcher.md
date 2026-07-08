# TODO widget file watcher & edit-conflict handling (COMPLETED)

## Summary

TODO d25e557: the TODO widget currently only ever reads `TODO.md` at
construction (or on a manual "Reload" click) — an external edit (hand
-editing the file, another `claude` process, `git pull`, etc.) isn't
picked up until the user remembers to click Reload. Add a real file
watcher so external edits show up automatically, remove the Reload
button (redundant once this works), and handle the one real hazard a
live-reloading list introduces: if a TODO item is being edited (its
`_ItemDialog` open) when the file changes externally in a way that
touches that same item, reloading over it would silently discard the
in-progress edit. Instead, preserve the in-progress text by dropping it
into a new Scratch widget (TODO 43845be) labeled
`TODO Item ({item_id}) Edit Conflict`, and close the stale dialog.

## Design

### Watching the file

`watchdog` (already a project dependency, used by `desk.widgets.
WidgetWatcher` for widget hot-reload) can only watch directories, not a
single file directly. A small dedicated watcher (not a reuse of
`WidgetWatcher`, which is specifically about widget *source*
hot-reload via the shared `HotReloadBroker` — a different signal/
semantic than "this TODO.md's content changed") watches the resolved
`todo_path`'s parent directory non-recursively, filters events down to
the exact `todo_path`, and debounces bursts (e.g. an editor's
save-via-temp-file-then-rename dance) with a short `threading.Timer`
before reporting a change — same debounce-then-emit shape as
`desk.widgets._DebouncedHandler`. A small `QObject` (`_FileChangeRelay`,
mirroring `_CommitResultRelay`) owns the `pyqtSignal` so the watcher
-thread callback can report back onto the GUI thread safely (Qt queues
a cross-thread signal emission onto the receiving object's own thread —
same mechanism already relied on for background commit results).

The watcher is (re)started only when the resolved `todo_path` actually
changes (not on every `reload()` call, which would otherwise restart —
and briefly stop watching during — every single external-change
-triggered reload) and stopped via the same `destroyed`-triggered
teardown pattern already used for the debounced-commit flush (a plain
closure over `self._state`, not a bound method of `self` — see
`LEARNINGS.md`'s "Connecting an object's own `destroyed` signal to one
of its own bound methods never fires").

### Distinguishing our own writes from real external edits

`_write_and_commit` (already the sole write path for add/edit/
reprioritize) writes `TODO.md` itself, which the watcher above will
also see — without filtering, every one of our own saves would
immediately "detect" itself as an external change. Fixed by having
`_write_and_commit` record the exact text it wrote into
`state["last_written_text"]`; the watcher's change handler reads the
file fresh and skips entirely if its content matches
`last_written_text` verbatim.

### Edit-conflict detection

`TodoWidget` tracks currently-open edit dialogs: `self._open_edits:
dict[item_id, (dialog, original_description)]`, populated in
`_show_edit_dialog` (the `original_description` snapshot is the
description as loaded, i.e. what the dialog was prefilled with) and
popped automatically when the dialog is destroyed (`dialog.destroyed
.connect(...)` — connecting a *different* object's, `TodoWidget`'s, own
bound method to *another* object's, the dialog's, `destroyed` signal is
the case `LEARNINGS.md` confirms works fine; the never-fires gotcha is
specifically same-object).

On a confirmed real external change, before reloading: for every open
edit, look up that item's id in the freshly-parsed file. If the item is
gone, or its description no longer matches the snapshot taken when
editing began, that's a conflict: read the dialog's current (possibly
unsaved) text (a new `_ItemDialog.current_text()` accessor), spawn a
Scratch widget with that text and the label
`TODO Item ({item_id}) Edit Conflict`, and close the now-stale dialog
(no discard-confirmation — the text isn't being lost, just relocated).
*Then* apply the reload as normal.

If a local reprioritization is pending (uncommitted, mid-debounce) when
an external change is detected, flush it synchronously first (reusing
the existing debounced-commit machinery, `.join()`-ed) before reading
the file for the reload — so a local, not-yet-committed reorder and an
external edit landing at nearly the same moment don't race with the
local change silently lost. This can't fully eliminate every possible
race in a plain-file-based sync scheme (two processes editing at
literally the same instant), which is out of scope to solve further
here.

### Spawning a Scratch widget from inside the TODO widget

No `python` widget has ever had a way to place another widget instance
on the canvas before. Following the exact precedent
`desk.shell.current_context` already set for "the current Desk's
directory" (a minimal module-level get/set pair, set once by
`DeskWindow`, no live-update signal since only one caller needs it so
far): add `set_widget_opener`/`get_widget_opener` to
`current_context`, holding a callable `(widget_id: str) -> QWidget |
None`. `DeskWindow` sets it once at construction to a new
`open_widget_content` method — like the existing `open_widget` (used by
the Bridge API), but returning the actual built content widget (e.g.
the real `ScratchWidget` instance) instead of just an instance id, so
the caller can immediately configure it. Only meaningful for `kind:
"python"` widgets (returns `None` for `kind: "html"`, or if the build
failed and only the error placeholder exists) — needs a new `.current`
property on `PythonWidgetHost` to expose the widget its
`PythonWidgetHost` is currently hosting.

`ScratchWidget` gains a small `set_label(text)` (delegating to its
internal `_TitleRow`) so a caller can set the label without reaching
into private attributes — the natural, minimal extension needed to
actually satisfy this item's "label it with..." requirement; no
file-backing/content-parameter hook is added to `build()` itself (still
no caller needs that generically).

### Removing the Reload button

Deleted from the toolbar entirely (`reload()` remains as a plain method
— still called at construction and by the watcher's change handler,
just no longer manually triggerable).

## Affected files

- `widgets/todo/widget.py` — file watcher, self-write-echo filtering,
  edit-conflict tracking/resolution, Reload button removal.
- `widgets/scratch/widget.py` — `ScratchWidget.set_label` /
  `_TitleRow.set_label`.
- `src/desk/shell/current_context.py` — `set_widget_opener`/
  `get_widget_opener`.
- `src/desk/shell/python_widget.py` — `PythonWidgetHost.current`
  property.
- `src/desk/shell/window.py` — `DeskWindow.open_widget_content`, wiring
  the opener into `current_context` at construction.

## Verification

Entirely headless:

1. Construct a `TodoWidget` against a real temp-dir `TODO.md` (as
   existing TODO-widget tests already do), confirm the Reload button no
   longer exists in the toolbar.
2. Externally modify the file's content (a plain `Path.write_text`,
   simulating another process) and directly invoke the watcher's change
   handler (rather than waiting on a real filesystem-event round trip
   in a test), confirming the list picks up the new content.
3. Confirm a write made via `_write_and_commit` itself does *not*
   trigger a spurious "external change" handling pass (content matches
   `last_written_text`).
4. Open an edit dialog for an item, then externally change that same
   item's description in the file and invoke the change handler:
   confirm a new Scratch widget instance is created (via a fake
   `current_context` opener installed for the test) with the dialog's
   in-progress text and the label `TODO Item ({item_id}) Edit
   Conflict`, and that the stale dialog is closed.
5. Regression: open an edit dialog, externally change a *different*
   item (or make an unrelated, non-conflicting change), confirm no
   Scratch widget is created and the dialog stays open.
6. Regression: full add/edit/reprioritize/commit flows (already
   covered by `plans/todo-widget.md` etc.) still work with the watcher
   active.
7. Real filesystem watcher regression: with a real `Observer` (not the
   directly-invoked handler used above), touch the actual file on disk
   and confirm the debounced signal does eventually fire (bounded
   `Monitor`-free wait via a short real sleep in the test, acceptable
   here since this one check is specifically about the real watchdog
   wiring, not the conflict-resolution logic already covered above).

## Status

Implemented and verified, entirely headlessly:

1. Confirmed the Reload button no longer exists in the toolbar (Add
   Item still does).
2. Confirmed `_on_external_change`, invoked directly against a real
   temp git repo whose `TODO.md` was modified out-of-band, correctly
   picks up the new content.
3. Confirmed a write made via `_write_and_commit`/`_add_item` does not
   trigger a spurious external-change reparse (content matches
   `last_written_text`).
4. Confirmed opening an edit dialog, then externally changing that
   same item's description and invoking the change handler, spawns a
   Scratch widget (via a fake installed `current_context` opener) with
   the dialog's in-progress text and the label
   `TODO Item ({item_id}) Edit Conflict`, and closes the stale dialog
   (its `_open_edits` entry is popped).
5. Regression: externally changing a *different*, non-conflicting item
   while an edit dialog is open spawns no Scratch widget and leaves the
   dialog open.
6. Regression: full add/edit/reprioritize/commit flows still work with
   the watcher active.
7. Confirmed a real `watchdog` `Observer`, pointed at an actual temp
   directory, picks up a genuine on-disk write end-to-end. This first
   hit exactly the macOS symlinked-`tempfile.mkdtemp()`-path gotcha
   `LEARNINGS.md` already documents for `WidgetWatcher` (the observer's
   reported `event.src_path` is the *resolved* path, while the
   unresolved directory was being compared against) -- fixed the same
   way, by `.resolve()`-ing both sides of the comparison in
   `_SingleFileHandler`.
8. Separately, confirmed a real `DeskWindow` correctly wires
   `current_context`'s widget opener at construction, and that calling
   it (or `DeskWindow.open_widget_content` directly) places and returns
   a genuine, configurable `ScratchWidget`/`BrowserWidget` instance
   (not just an instance id).
