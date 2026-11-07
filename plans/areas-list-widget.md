# Areas list widget (TODO `747806b`) (COMPLETED)

## Summary

A built-in `kind: "python"` widget, **"Areas"** (`widgets/areas/`), that lists the desk's areas (TODO `0460b4c`) and is
meant to be docked in the left sidebar (TODOs `6413e58`, `4ff712c`) via the canvas right-click menu's "Dock in
sidebar" group. It also works as an ordinary canvas widget.

## Decisions

- Modelled on `widgets/recently_removed`: reads `current_context.get_main_window().list_areas()` once at construction,
  then replaces its rows from each `desk.areas.changed` event (`bind_event_mediator`); no polling. A desk switch
  re-creates a docked widget after the new Desk's areas are loaded, so the construction-time read is right.
- Plain `QListWidget` (one row per area, title only, geometry in the tooltip) rather than per-row widgets: it must fit a
  300px sidebar. **Clicking a row views that area** (`view_area`, fit-view).
- Buttons under the list act on the selected row: **Add** (`create_area` with the default "middle 70% of the view"
  geometry and a numbered title, then edits the new row's title in place), **Rename** (in-place edit; an empty title is
  reverted), **Delete** (confirmed through the Desk popup service, mirroring Recently Removed's Clear; widgets under
  an area are never touched).
- No widget-local storage (everything is the Desk's own state), no capabilities.
- Agent docs: one paragraph in `tempui-areas.md` + a changelog tag.

## Verification

Offscreen with a fake main window and a real `EventMediator`: initial load, live replace from the event, click -> view,
add (default title, edit begins on the new row), rename commit + empty revert, delete with confirm yes/no, not-connected
state, selection kept across a refresh, manifest/docs/tag.
