# Collapsible active/deprecated groups in the widget-add popup menu

TODO `ed483e2`.

## Summary

"split the widget-adding popup menu list of popups into collapsible
groups, with the current groups being 'active' and 'deprecated', and
default to showing active as shown and deprecated as collapsed."

`WidgetSpawnMenu` (the typeable-filter popup shown on canvas right
-click) is today a single flat `QListWidget` over `catalog: dict[str,
str]` (widget_id -> display name) -- no concept of "deprecated"
anywhere in the widget system at all. Two things are needed: a new
`deprecated` field on the widget manifest (`widget.json` ->
`WidgetInfo`, checked -- doesn't exist today), and a UI rework from
`QListWidget` to a two-group `QTreeWidget` ("Active" expanded,
"Deprecated" collapsed by default), since Qt has no lighter-weight
built-in "collapsible list section" widget.

## Key decisions

- **New optional `"deprecated": bool` field on `widget.json`**, parsed
  into a new `WidgetInfo.deprecated: bool = False` field
  (`_parse_manifest`'s `manifest.get("deprecated", False)`) -- every
  existing widget's manifest is silently `false` by omission, no
  migration needed.
- **`QTreeWidget`, not two `QListWidget`s side by side or a custom
  collapsible-section widget.** A `QTreeWidget` gives native expand/
  collapse arrows and (crucially) a stable visual/traversal order for
  free via two non-selectable top-level "group" items ("Active",
  "Deprecated"), each holding the actual widget entries as children --
  matches the existing precedent of using `QTreeWidget` for a similar
  grouped-list job (`markdown_ex`'s own TOC panel), rather than
  introducing a new pattern.
- **Group header items are created once and kept across filter changes,
  not recreated.** Only recreating `_populate`s the *children* under
  each group's already-existing header -- so a group's expand/collapse
  state (whether the user just toggled it) survives every keystroke in
  the filter box, instead of resetting to the hardcoded default on
  every filter update.
- **Keyboard navigation (`Up`/`Down`/`Enter`) walks only *visible*
  leaf entries** -- skips group headers themselves (never selectable),
  and skips any entry sitting under a currently-*collapsed* group
  (`QTreeWidgetItemIterator`'s built-in flags don't account for
  collapsed-ancestor invisibility, so this is a small manual walk over
  each group's children, only for expanded/not-hidden groups). Focus
  stays on the filter `QLineEdit` throughout, exactly as today --
  `eventFilter` keeps forwarding these keys rather than handing focus
  to the tree.
- **Filtering doesn't auto-expand a collapsed group just because it
  contains a match.** A collapsed "Deprecated" group stays collapsed
  while typing, even if the filter text matches something inside it --
  matches the TODO's literal "default to... deprecated as collapsed"
  wording without adding unrequested auto-expand behavior. A group with
  zero matching entries (after filtering) is hidden entirely rather than
  shown empty.
- **`WorkspaceView.contextMenuEvent` now passes the full `dict[str,
  WidgetInfo]` catalog straight through** instead of first flattening it
  to `dict[str, str]` (name only) -- `WidgetSpawnMenu` needs `.name`
  *and* `.deprecated` per entry, and `desk.widgets.WidgetInfo` is
  already a plain dataclass with no dependency on `desk.shell`, so
  importing it into `widget_spawn_menu.py` doesn't risk a cycle.

## Affected files

- `src/desk/widgets.py` -- `WidgetInfo.deprecated: bool = False`;
  `_parse_manifest` reads it.
- `src/desk/shell/widget_spawn_menu.py` -- `QListWidget` -> `QTreeWidget`
  with two persistent group header items; `_populate`/`_apply_filter`
  rebuild only the children under each group; keyboard nav walks visible
  leaf entries only.
- `src/desk/shell/canvas.py` -- `contextMenuEvent` passes the full
  `WidgetInfo` catalog through unchanged instead of pre-flattening it.
- `design-docs/widget-ux.md` -- wherever `WidgetSpawnMenu` is currently
  described, updated for the two-group shape.

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication`, no mocks):

- A catalog with a mix of active and deprecated entries: "Active" group
  is expanded and "Deprecated" is collapsed by default; each entry lands
  under the correct group.
- Typing a filter that matches only a deprecated entry: it appears
  (correctly) under the still-collapsed "Deprecated" group -- not
  auto-expanded, matching the documented scope decision; the "Active"
  group is hidden if it now has zero matches.
- Manually expanding "Deprecated", then typing a filter character:
  confirm it's *still* expanded afterward (state survives re-populate).
- `Down`/`Up`/`Enter` from the filter box: only reach actual widget
  entries, in visual order, skipping both group headers and any entries
  hidden inside a collapsed group; `Enter` on a reached entry emits
  `widget_chosen` with the right widget_id and closes the popup.
- `WidgetInfo.deprecated` defaults to `False` for a manifest with no
  `"deprecated"` key (every real widget today), and is `True` only when
  the manifest explicitly sets it.

## Status

Not yet implemented.
