# Vendor shared components for a deployed build (TODO `b04682e`) (COMPLETED)

## Summary

A real-source widget is rebuilt from source each time Desk opens the
project, and its desk-wide components come from the *opening Desk's*
`shared-components/` (TODO `d34f8ed`). So a project's repository alone does
not determine its build. "Deployed build" is not a term the codebase defines;
this implements it as **making the project self-contained**: a means to put
every component a widget needs into the project itself. (Still required where
the project is opened: Desk and `tsc`.)

## Design

- `vendor_component(project, name)`: copy the desk-wide component directory
  into `desk_widgets/_shared/components/<name>/`. Identical existing copy ->
  no-op; a differing one (probably customized) -> error unless `overwrite`.
- `vendor_widget_components(project, source_path)`: for each desk-wide
  component in the widget's `widget.json`, vendor it and rewrite the entry to
  `project:<name>` (other entries and keys untouched; idempotent). Pinning
  makes the build read only project files and fail loudly -- not silently
  fall back to Desk's copy -- if the copy goes missing.
- Surfaces: MCP tool `desk_vendor_widget_components(source_path, overwrite?)`
  and the Components widget's "Copy to project library" button (copy only;
  pinning is the widget-level call).
- **Resolution change** (`desk.custom_widgets` and the generated
  `build_widget.py`): a bare name now prefers the project copy, else
  desk-wide. TODO `d34f8ed` made "in both" an error, which a vendored copy
  would trip -- breaking other widgets using the bare name -- and which a
  component added by a later Desk could also trip. Project-wins is stable
  under both. `desk:`/`project:` still pin a side.

## Verification

`verify_widget_components_vendor.py` (27): copy/identical/customized/
overwrite; widget.json rewrite and idempotence; resolution succeeds against
an EMPTY desk-wide library after vendoring (and fails without it); a pinned
entry errors when its copy is removed; the MCP tools; and a real build whose
output changes when the *project* copy is edited. `verify_widget_components`
updated for the precedence rule (29).

## Not done

No automatic vendoring on promotion; no version/hash record of what was
vendored from which Desk revision; no "update from Desk" beyond `overwrite`.
