# Expose per-instance staleness to agents (TODO f0da2e9) (COMPLETED)

## Summary

`desk_list_widget_instances` (MCP) and `desk.workspace.getState()`
(Bridge, same underlying `DeskWindow.get_state_dict()` call) return a
`placed_content_hash` with nothing anywhere in reach to compare it
against -- the other half of the comparison
(`DeskWindow._custom_widget_content_hash`) is never serialized. An
agent driving Desk has no way to tell a placed instance is showing the
titlebar `[STALE]` badge (still running pre-edit code) short of a human
looking at the canvas -- confirmed to have let an agent report an
entire multi-widget feature as complete and tested while three
instances silently ran stale code the whole time. Cites
`../FEEDBACK/FEEDBACK-DESK-agent-cannot-detect-stale-widget-instances-2026-09-17-2200.md`.

## Approach

Surface the exact live `[STALE]` bit each `WidgetFrame`'s titlebar
already reads, not an independently recomputed hash diff -- the report
itself calls this out: a hash diff alone would miss the force-`True`
set by `_on_promoted_widget_source_changed` when source changed on
disk and no fresh hash exists yet to diff against.

1. `_TitleBar.is_stale()` / `WidgetFrame.is_stale()`
   (`src/desk/shell/widget_frame.py`) -- getters alongside the existing
   `set_stale()`, returning the same `_stale` bit the `[STALE]` button's
   visibility is driven by.
2. `desk_state_dict()` (`src/desk/desks.py`) gains an optional
   `stale_by_instance_id: dict[str, bool] | None = None` parameter. A
   `"stale"` key is added to a widget's dict only when given -- this
   function is also `save_desk`'s own persistence path, and staleness
   is live, in-session UI state that must never be written to the
   `.desk` file (it would already be wrong the moment it's read back).
   `save_desk` keeps calling it with no `stale_by_instance_id`, so the
   persisted shape is byte-for-byte unchanged.
3. `DeskWindow.get_state_dict()` -- the one shared implementation
   behind both `desk_list_widget_instances` and
   `desk.workspace.getState()` (confirmed identical, per the report) --
   builds `{frame.instance_id: frame.is_stale() for frame in
   self.view._frames}` and passes it through. Both surfaces get `stale`
   automatically from this one change.
4. Docs: the `desk.workspace.getState()`/`deskproc.list_widget_instances()`
   bullets in `tempui-custom-widgets.md`/`tempui-desk-proc.md`
   (`src/desk/temp_ui.py`) name the new field and what it means; the
   `desk_list_widget_instances` MCP tool's own description does too.
   New tempui changelog tag + `_NEW_FEATURES` entry.

## Affected files

- `src/desk/shell/widget_frame.py`
- `src/desk/desks.py`
- `src/desk/shell/window.py`
- `src/desk/shell/desk_mcp_server.py`
- `src/desk/temp_ui.py`
- `tests/verify/verify_stale_marker_click_dialog.py` (existing
  staleness coverage) and/or a new dedicated verify script.

## Verification

Real `WidgetFrame`s, no mocks: `is_stale()` reflects exactly what
`set_stale()` last set, both directions, and defaults `False` for an
ordinary (never-marked-stale) instance. `desk_state_dict`: omitting
`stale_by_instance_id` reproduces today's exact dict shape (regression,
covers `save_desk`'s own call site); passing it adds `stale` per
instance, defaulting `False` for an instance missing from the map.
`DeskWindow.get_state_dict()`: a real placed instance marked stale via
`_refresh_stale_indicators_for` (a genuine hash mismatch) and one
force-marked via `_on_promoted_widget_source_changed` (no fresh hash
yet) both report `stale: true`; an unrelated ordinary widget reports
`stale: false`; the MCP tool (`desk_list_widget_instances`) and the
Bridge route reach the exact same values (both call `get_state_dict()`).
Full `tests/verify/` sweep. No browser launch needed.

## Status

Implemented as planned. One extra measure taken beyond the plan itself:
`desk_state_dict`'s optional `stale_by_instance_id` design (rather than
always adding the key) was necessary, not just tidy -- `save_desk` calls
this same function directly to persist to disk, and a `stale` key baked
into the `.desk` file would already be wrong the moment it's read back.
Verified this explicitly: `save_desk` writes and `load_desk` re-reads
the exact same file with no `stale` key present.

Verified: the new `verify_stale_exposed_to_agents.py` (20 checks --
`WidgetFrame.is_stale()` mirrors `set_stale()`; `desk_state_dict`'s
optional parameter behavior including the `save_desk` persistence
regression; `DeskWindow.get_state_dict()` reporting `true` for both
ways an instance can go stale -- a genuine hash mismatch via
`_refresh_stale_indicators_for`, and the force-`True`
`_on_promoted_widget_source_changed` path the report explicitly says a
hash diff alone would miss -- `false` for a fresh instance and for an
ordinary `kind: "python"` widget with no staleness concept at all; doc/
changelog checks), run 3x for flakiness. Needed the same `os._exit()`
ending `verify_relocate_promoted_widget_source.py` already established
(LEARNINGS.md, TODO a5f66cc) -- several real `ChromiumWidget` instances
placed for the custom-widget tests segfault tearing down at normal
interpreter shutdown, after every check has already passed and printed.
Re-ran `verify_custom_widget_content_hash.py`, `verify_stale_marker
_click_dialog.py`, `verify_desk_mcp_server.py`. Full `tests/verify/`
sweep (161 scripts) passes. Browser launch not needed.

This was the only TODO citing
`../FEEDBACK/FEEDBACK-DESK-agent-cannot-detect-stale-widget-instances-2026-09-17-2200.md`
-- moved to `../FEEDBACK/implemented/`.
