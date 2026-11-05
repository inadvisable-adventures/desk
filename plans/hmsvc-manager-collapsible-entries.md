# Microservices widget: individually collapsible entries (TODO 5c79c86) -- COMPLETED

## Summary
Each service entry in `widgets/hmsvc_manager/widget.py` can be collapsed on its own into a single
row: status, name, the same action buttons (Start/Stop/Restart/Logs/Source) and an uncollapse
button. Expanded entries look as they do today (details, URLs, description) plus a collapse button.

## Affected files
- `widgets/hmsvc_manager/widget.py`
- `tests/verify/verify_hmsvc_manager_collapse.py` (new)

## Approach
1. Keep `self._collapsed: set[str]` (service names). Session-only, not saved in the `.desk` file;
   it survives list repopulation (status events rebuild every row).
2. `_build_row` takes the collapsed flag. Collapsed: a label with `<b>name</b> status` only, then
   the buttons, then the toggle. Expanded: today's rich label, buttons, toggle.
3. The toggle is a fixed-width painted-text button ("Expand"/"Collapse") -- no native arrow
   control, per `python-widget-conventions.md`.
4. Toggle flips membership in the set and repopulates; names no longer present are pruned.

## Decisions
- Per-session, not persisted: avoids a new state key for a view preference.
- Rebuild-on-toggle rather than hiding label parts, matching the widget's existing rebuild model.

## Verification
Offscreen script: collapsed row has no URL/description text but keeps name, status and all
buttons; toggling round-trips; collapsed state survives a `desk.hmsvc.changed` repopulate.
