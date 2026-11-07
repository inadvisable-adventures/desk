# `desk_place_widget` MCP tool (TODO `1746166`) (COMPLETED)

## Summary

From `../FEEDBACK/FEEDBACK-DESK-no-mcp-tool-to-place-a-new-widget-instance-on-the-canvas-2026-11-06-1245.md`:
after building/registering a widget (`DefineWidget`), an agent had no way to put an instance on the canvas;
the `desk_*` widget tools only list, reveal or screenshot already-placed instances. A human had to place it,
blocking the build -> place -> screenshot -> iterate loop.

New `desk` MCP tool `desk_place_widget(widget_id, x?, y?, width?, height?)` returning the new `instance_id`.

## Affected files

- `src/desk/shell/window.py` -- `DeskWindow.place_widget_by_id`, wrapping `_place_widget` (the same path
  every human-driven placement uses, so stale-hash stamping, schema-conflict checks etc. all apply).
- `src/desk/shell/desk_mcp_server.py` -- the tool, via `_call_on_gui_thread`.
- `src/desk/temp_ui.py` -- changelog tag + `_NEW_FEATURES` entry; mention in the overview doc and under
  "Invoking a defined widget" in `tempui-custom-widgets.md` (the entry is small enough not to need its own doc file).
- `tests/verify/verify_place_widget_tool.py`.

## Decisions

- Works for any id in the widget catalog, including `tempui_only` custom widgets (that restriction only hides
  them from the human "Add widget" menu); unknown id -> error listing registered ids.
- `x`/`y` are the **top-left** in scene coordinates (matching `desk_list_widget_instances`); omitted, the widget
  is centered in the current viewport. Both-or-neither for x/y and width/height.
- The feedback's optional `state` argument is deliberately left out of this first pass: there is no generic
  "initial state" contract across widget kinds, and an agent can adjust a placed widget through its own means.
- No modal UI is involved, so the call stays inside `GuiBridge`'s 5 s window.

## Verification

`verify_place_widget_tool.py` (fake window driven through the real `DeskWindow.place_widget_by_id`, plus the real
handler). Headless only; not run against a live Desk session.
