# Live `desk_hmsvc/` watcher + new-microservice notification (TODO `c40c5c5`) (COMPLETED)

Cites `../FEEDBACK/FEEDBACK-DESK-hmsvc-discovery-friction-and-promoted-widget-capabilities-2026-10-09-1351.md`
(finding 1).

## Summary

`HmsvcManager.refresh()` only ran at project open/switch or on a Rescan
click, so a service directory added while Desk ran was invisible. A watcher
now calls `refresh()`; a service not seen before in the project raises a
notification whose click places/focuses the Microservices widget.

## Affected files

- `src/desk/shell/hmsvc_dir_watcher.py` (new) -- mirrors `SchemaFileWatcher`:
  recursive watch, one debounced `changed` signal, polls until
  `desk_hmsvc/` exists; ignores `__pycache__`, `.pyc/.log` and
  existing-directory mtime events.
- `src/desk/hmsvc.py` -- `refresh()` returns names new since the project
  was opened (`_ever_seen`, reset by `set_directory`).
- `src/desk/shell/window.py` -- provision on every desk open/switch next to
  `set_directory`; `_on_hmsvc_dir_changed`, `_notify_new_hmsvc_service`,
  `_reveal_hmsvc_manager`.
- `src/desk/temp_ui.py` -- `tempui-hmsvc.md` discovery section, changelog
  tag `#008485`.
- `tests/verify/verify_hmsvc_dir_watcher.py`.

## Decisions

- The scan at project open, and a widget Rescan, never notify by
  themselves (the user is looking); only the watcher path does.
- A removed-then-restored service is not announced twice.
- Clicking opens the Microservices widget only; it never starts a service
  (decided with the user).
