# Components catalog widget (TODO `5ee7493`) (COMPLETED)

## Summary

A built-in `kind: "python"` widget (`widgets/components/`) that shows the
catalog of shared web components (TODO `d34f8ed`): both libraries -- the
project's mutable `desk_widgets/_shared/components/` and Desk's static
`shared-components/` -- so an author can discover what exists without
reading directories.

## Design

- Data in `desk.widget_components` (`list_catalog`, `catalog_signature`),
  shared with an agent-facing read-only MCP tool,
  `desk_list_shared_components`. Per entry: name, scope, README summary (its
  first prose paragraph), template yes/no, files, `used_by` (source widgets --
  promoted `desk_widgets/*` and not-yet-promoted `.desk_temp/widgets/*` --
  whose `widget.json` resolves to that exact entry), `vendored`.
- Widget: grouped list (project, then desk-wide) beside a details pane
  (Markdown); buttons Open README / Open source (the shared editor opener),
  Copy entry (clipboard), Copy to project library (desk-wide only; see TODO
  `b04682e`). A 2 s poll on `catalog_signature` picks up edits/new
  components while open; selection is kept across refreshes. Labels are not
  user-selectable; no native combo box.

## Files

`widgets/components/{widget.json,widget.py}`, `src/desk/widget_components.py`,
`src/desk/shell/desk_mcp_server.py`, `src/desk/temp_ui.py` (docs, tag
`#5ee7493`), `tests/verify/verify_components_widget.py` (17 checks),
`tests/verify/verify_widget_components_vendor.py` (catalog part).

## Verification

Headless (offscreen Qt): the widget against a temp project plus Desk's real
library, including vendoring through the button, a live add picked up by the
poll, and no Desk directory. A bug found and fixed on the way: the refresh
after "Copy to project library" overwrote its own status message. Not looked
at in the live app.
