# Desk areas (desk_*_area MCP tools)

See `desk-temporary-ui.md` (in this same directory) for this directory's
own overview and its current set of tags. This is not a tempui-DSL file
type: it is five MCP tools on the `desk` server, plus a desk event.

A **desk area** is a named rectangle drawn on the Workspace Canvas
background, behind every widget. It marks out a region ("Inbox", "Reading
list", "Experiments") that a human or agent can jump to. Its title strip
holds an editable title and an **eye button**; clicking the title edits it
in place (Enter saves, Escape cancels) and clicking the eye pans and
zooms the canvas to fit the area (what `desk_view_area` does).

- The **interior is click-through**: only the title strip and a thin band
  along the border are part of the area. Clicks, drags and scrolls inside
  it reach the canvas background and any widget on top, so an area never
  blocks interaction with what it contains.
- Areas always sit **behind every widget**, including ones created later.
- Moving or resizing an area **does not move widgets**. An area is a label
  on the canvas, not a container.
- Areas are saved in the project's `.desk` file.

## MCP tools

- `desk_list_areas()` -- every area as `{area_id, title, x, y, width,
  height}`. `x`/`y` are the top-left in canvas coordinates, the same ones
  `desk_list_widget_instances` reports, so you can tell which widgets
  fall inside an area by comparing rectangles.
- `desk_create_area(title?, x?, y?, width?, height?)` -- give both `x` and
  `y`, or neither; both `width` and `height`, or neither. Omitted geometry
  defaults to the middle 70% of what is on screen right now. Returns the
  new area, including its `area_id`.
- `desk_update_area(area_id, title?, x?, y?, width?, height?)` -- rename,
  move and/or resize; omitted fields are unchanged.
- `desk_delete_area(area_id)` -- removes the area only; returns whether it
  existed.
- `desk_view_area(area_id)` -- pans and zooms to fit the area; pair it with
  `desk_screenshot_desk` to see what is inside.

## The Areas widget

A built-in `Areas` widget (widget id `areas`) lists the areas for a human:
click a row to view it; Add, Rename and Delete act on the selected row. It is
meant to be docked in the sidebar (`desk_dock_widget("areas")`, or the canvas
right-click menu's "Dock in sidebar" group) but also works placed on the
canvas.

## Event

Every create, edit, move, resize and delete -- by a human or by a tool --
publishes the desk event `desk.areas.changed` with the payload
`{"areas": [<same dicts as desk_list_areas>]}`. A `kind: "html"` widget can
subscribe with `desk.events.subscribe("desk.areas.changed", ...)`.
`desk.workspace.getState()` also carries the list as `areas`.
