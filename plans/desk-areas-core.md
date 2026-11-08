# Desk areas core (TODO `0460b4c`) (COMPLETED)

## Summary

From `../FEEDBACK/FEEDBACK-DESK-desk-areas-background-frames-with-area-view-switching-2026-11-04-0000.md`: a **desk
area** is a named rectangle on the canvas background, behind every widget, with an editable title and an eye button,
whose interior does not take part in hit-testing, that can be created/read/updated/deleted/listed/viewed -- from the
frame chrome and from the Desk MCP. This TODO is the core; the docked sidebar is TODO `6413e58` (the region) and
`747806b` (the Areas list widget docked in it).

## Decisions (made with the user)

- **Native scene item**, not a special `WidgetFrame`: a `QGraphicsObject` at a fixed far-back z. Only the title strip
  and a thin border band are in `shape()`, so the interior is click-through by construction and nothing that
  iterates placed widgets (`_frames`) sees an area.
- **Viewing an area = fit view only** (no dimming/hiding). **Moving/resizing an area does not carry widgets.**
- The sidebar list is a **real docked sidebar** -- split into its own TODOs (`6413e58`, `747806b`), not part of this one.

## Design

- `desk.desks.AreaState(area_id, title, x, y, width, height)` and `Desk.areas`; saved/loaded in the `.desk` file
  (`areas` key; absent in older files -> none) and included in `desk_state_dict`, hence `workspace.getState()`.
  `_capture_desk_state` already carries unrecognised Desk fields over via `dataclasses.replace`.
- `desk/shell/area_item.py::AreaItem`: paint (faint fill, border, title strip, eye glyph), `shape()` (winding fill
  rule -- the strip overlaps the border bands, odd-even would punch holes), chrome sized in screen pixels
  (`px / view_scale`) so it stays readable when zoomed out, hover cursors, press/move/release for move (title strip) and
  edge/corner resize (7px band, min size 80), eye click -> `view_requested`, double-click title -> `rename_requested`,
  own context menu (View / Rename / Delete). Signals only; it holds no persistent state.
- `WorkspaceView`: `add_area` (also replaces), `remove_area`, `clear_areas` (called from `clear_widgets`, so a Desk
  switch clears them), `zoom_to_area` (`_fit_rect`, 3% margin), `visible_scene_rect`; areas get `set_view_scale` in
  `_on_scale_changed`; the right-click spawn menu gets a pseudo catalog entry **"Desk Area"** (so typing/filtering/keyboard
  work for free) that emits `area_add_requested(scene_pos)`; right-click on area chrome is delegated to the item.
- `DeskWindow`: `list_areas`, `create_area`, `update_area`, `delete_area`, `view_area`, plus the signal handlers
  (geometry write-back, rename prompt, delete, add at click: 800x600 top-left at the click). Omitted geometry on create
  defaults to the middle 70% of the visible scene rect. Every change publishes `desk.areas.changed`
  (`{"areas": [...]}`, sender `desk`). `_load_desk_areas` runs after `_load_desk_widgets` in `__init__` and `switch_desk`.
- MCP: `desk_list_areas`, `desk_create_area`, `desk_update_area`, `desk_delete_area`, `desk_view_area`.
- Agent docs: dedicated `tempui-areas.md`, changelog tag `desk areas: background regions + MCP tools #377360`, links from
  the overview doc and the tempui doc index. `design-docs/architecture.md` item 35.

## Not in this TODO

- The docked sidebar and the Areas list widget (`6413e58`, `747806b`).
- Dim/hide-outside "focus mode", carrying widgets with an area, areas in the Minimap, an undo for delete.
- A Bridge-API (`window.desk`) surface for `kind: "html"` widgets beyond the `desk.areas.changed` event and
  `workspace.getState().areas`.

## Verification

`tests/verify/verify_desk_areas.py` (offscreen): real `WorkspaceView`/`AreaItem` driven with `QTest` mouse events
(hit-testing of interior vs strip vs border, widget-above-area wins, move, resize, eye click, interior click inert,
zoom-to-area, chrome counter-scaling, Desk-switch clear, spawn-menu entry), `.desk` round trip and old-file load,
`DeskWindow`'s real area methods on a stand-in, the MCP handlers, and the docs/tag. Headless only: the area's own
right-click `QMenu` (it blocks in `exec`) and a live visual check were not exercised.

Also fixed in passing: `_NEW_FEATURES` was out of newest-first order after a merge (the `desk_place_widget` entry sat
above the two Mermaid entries), failing `verify_tempui_changelog_docs.py`.
