# Sidebar tab labels/hit targets and inline area rename (TODO `615bd79`) (COMPLETED)

Four follow-ups from the user to TODOs `4ff712c` / `0460b4c`:

1. **Area titles rename inline** on the canvas: a click (press + release without moving) on the title text opens a
   `QLineEdit` (a scaled child `QGraphicsProxyWidget` of the `AreaItem`); Enter / focus loss commits, Escape cancels, an
   empty title is not committed. Replaces the double-click prompt dialog; the item's context-menu "Rename..." opens the
   same editor. The `AreaItem.rename_requested` / `area_rename_requested` / `_on_area_rename_requested` path became
   `title_edited` / `area_title_edited` / `_on_area_title_edited`. (The Areas list widget already renames in place.)
2. **The whole collapsed bar opens the sidebar**, and 4. **the whole bar collapses it** when open: `SidebarTab` now
   holds one full-height `_TabBody` widget (the click target) instead of a small button; the arrow is painted
   **vertically centred** in both states.
3. **Collapsed, the tab paints a rotated label per docked widget** above the arrow (title cut to 16 characters with
   "..."; labels that would run into the arrow are omitted; the tooltip lists every full title). The strip is 26px wide.

Verification: `verify_docked_sidebar.py` (real mouse clicks on the strip at top/middle/bottom, pixel checks that labels sit
above and the arrow is centred), `verify_desk_areas.py` (click-to-edit, Enter, Escape, empty), plus an offscreen real
`DeskWindow` run with screenshots. No real-mouse live check.
