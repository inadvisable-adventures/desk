# Recently Removed widget (TODO `454d718`) (COMPLETED)

## Summary
Removing a widget used to permanently destroy its widget-local-storage state
(`close_widget`/`close_widget_by_instance_id` drop the frame and re-save;
`save_desk` overwrites the `.desk` file, re-verified 2026-10-03 against the
current `window.py`). Tombstone removed widgets in the `.desk` file and add a
widget listing them with **Revive**.

## Affected files
- `src/desk/desks.py`: `RemovedWidget` dataclass, `Desk.recently_removed`,
  load/save.
- `src/desk/shell/window.py`: tombstoning in both close paths, `get_recently_
  removed`, `revive_removed_widget`, `clear_recently_removed`, change event.
- `src/desk/recently_removed.py` (new): the event name + the cap.
- `widgets/recently_removed/{widget.json,widget.py}` (new).
- `tests/verify/verify_recently_removed.py` (new), `TODO.md`,
  `design-docs/architecture.md`.

## Design
- **Tombstone** `RemovedWidget{widget_id, kind, label, instance_id, state,
  width, height, removed_at}` (epoch seconds), newest first, stored in a new
  `recently_removed` list in the `.desk` file. Cap: **20 entries** (count, not
  age -- simpler, and a stale-by-age entry is still worth reviving); the oldest
  fall off. The file format has no version field, so the key is simply optional
  on load (`data.get("recently_removed", [])`): old files load unchanged and
  an old Desk reading a new file ignores the extra key.
- **Capture point**: both close paths snapshot the tombstone (label via
  `_display_name_for_instance`, state via `_get_widget_local_storage`) *before*
  the frame is removed and the desk re-saved. Not tombstoned: tempui-backed
  widgets and crash-log widgets, whose instance id *is* their source file's
  identity -- a revived copy with a new id could not reconnect, so offering it
  would mislead. `_capture_desk_state` carries the field over automatically
  (`dataclasses.replace`, TODO `224fbc9`).
- **Revive** places a brand-new instance through the normal path
  (`_place_widget`, centered, at the saved size) and seeds *its own* local
  storage with the saved state synchronously right after placement (the same
  call `_load_desk_widgets` makes -- an html page's JS runs later, so it sees
  the restored data on its first `getLocalStorage()`; a Claude (Desk) widget
  gets it through `_place_widget`'s `local_storage_data`, which applies before
  `start_session`). A widget kind that no longer exists can't be revived (the
  tombstone stays). A successful revive drops the tombstone and saves.
- **Clear all** follows Event Log's confirm-then-clear (a patchable
  `_confirm_clear` using the popups service).
- **Live updates**: `desk.recently_removed.changed` carries the entries
  (without state, to stay light) on every add/revive/clear; the widget loads
  once from `get_main_window().get_recently_removed()`, then replaces its list
  from events. Row text: label, kind, relative time ("5 min ago").

## Verification
Desk round-trip (new field, old files), tombstone contents and cap, both close
paths, revive (new instance id, state seeded, tombstone removed, missing kind),
clear, event payloads, widget rows/buttons. Real `DeskWindow` not constructed
(none of the existing tests do); window methods are exercised on a stub with the
real `WorkspaceView`.
