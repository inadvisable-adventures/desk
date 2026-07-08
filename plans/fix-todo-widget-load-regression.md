# Fix TODO widget regression: TODO.md not found at boot (TODO 1a051d1) (COMPLETED)

## Summary

TODO 1a051d1: the TODO widget shows "No TODO.md found near the current
Desk's directory" at boot, even when a real `TODO.md` sits right next to
the current Desk's `.desk` file.

## Root cause

`DeskWindow.__init__` (`src/desk/shell/window.py`) does, in this order:

```python
self.current_desk = load_desk(desk_path) if desk_path.is_file() else Desk(path=desk_path)
self._load_desk_widgets(self.current_desk)   # constructs saved widgets, incl. TodoWidget
...
self._refresh_picker()                        # <- only place that calls
                                                #    current_context.set_current_desk_directory
```

`TodoWidget.__init__` (`widgets/todo/widget.py`) calls `self.reload()`
once, synchronously, at construction time. `reload()` reads the current
directory via `desk.shell.current_context.get_current_desk_directory()`
— a plain module-level variable (see its docstring: "resolves the
directory once at construction ... no signal/notification of later
changes"). Since `_load_desk_widgets` runs *before* `_refresh_picker`,
that variable is still `None` (its module-level default) the moment a
saved `TodoWidget` instance is rebuilt from a `.desk` file at boot —
`reload()` then takes the `directory is None` branch and shows the
"No TODO.md found" error, even though `self.current_desk.directory` is
already correctly known at that point (`self.current_desk` is assigned
on the line right before).

This ordering bug has existed since the TODO widget's very first commit
(`ef75ca1`), but was silently masked by a "Reload" button in the
widget's toolbar: since both `_load_desk_widgets` and `_refresh_picker`
run synchronously inside the same `__init__` call, by the time the user
could actually see and click that button, `current_context` was already
correctly populated, so a manual reload always fixed the display. TODO
d25e557 (`ba0b03e`) removed that button in favor of automatic
file-watching — which only fires on a subsequent *external change* to
the file, never on initial load — turning a cosmetic first-paint glitch
into a permanent, unrecoverable-without-restarting-into-a-different-
-directory regression. This matches the reported symptom exactly.

## Affected files

- `src/desk/shell/window.py` (edit) — reorder `DeskWindow.__init__`.

## Design

Move the `self._refresh_picker()` call (which sets
`current_context.set_current_desk_directory` as a side effect, among
other things) to right after `self.current_desk` is assigned, before
`_load_desk_widgets` constructs any saved widgets. `_refresh_picker`
only reads `self.current_desk` and `self.view.desk_picker`/`.view` —
both already available at that point — so this reordering is safe and
has no other effect on boot behavior.

```python
self.current_desk = load_desk(desk_path) if desk_path.is_file() else Desk(path=desk_path)
self._refresh_picker()
self._load_desk_widgets(self.current_desk)
self.view.set_view_state(...)
current_context.set_widget_opener(self.open_widget_content)
current_context.set_temp_ui_write_recorder(self._temp_ui_manager.record_own_write)
self._provision_temp_ui()
```

Not touching `desk.shell.current_context`'s design itself (no signal/
notification mechanism) — that's an intentional, still-valid scope
limit per its own docstring; the bug is purely in *when* the one-time
set happens relative to widget construction, not in the module's
fundamentally synchronous, no-live-update shape.

## Verification

Entirely headless (`QT_QPA_PLATFORM=offscreen`):

1. Regression repro: construct a `DeskWindow` (unfixed) around a
   `.desk` file that already has a saved `TodoWidget` instance, in a
   directory containing a real `TODO.md` — confirm the widget's status
   label shows the "No TODO.md found" error despite the file existing.
2. Confirm the fix: same setup, after reordering — the widget's status
   label shows the real `TODO.md` path and its parsed items, immediately
   at construction, no manual reload needed.
3. Regression check: `_refresh_picker`'s other effects (desk picker
   label reflecting name/directory, MRU dropdown) still correct after
   being moved earlier in `__init__`.

## Status

Implemented and verified. Reproduced the exact bug directly by
temporarily reverting to the unfixed ordering and constructing a real
`DeskWindow` (catalog trimmed to just the `todo` widget, and the target
directory's `.desk_temp` pre-provisioned, to avoid unrelated hangs from
this sandbox's QtWebEngine GPU process and the temp-UI first-run
confirmation dialog respectively — both orthogonal to what's being
tested here) pointed at a directory with a real `TODO.md`: the widget's
status label showed "No TODO.md found near the current Desk's
directory." Restored the fix and re-ran the identical repro: the status
label immediately showed the real `TODO.md` path. `_refresh_picker`'s
other effects (desk picker label/MRU dropdown) are unaffected by the
reordering — nothing else in `DeskWindow.__init__` depends on it running
after `_load_desk_widgets` instead of before.
