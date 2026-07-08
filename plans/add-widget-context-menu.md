# Add widget instances to a Desk via a right-click typeable-filter menu (COMPLETED)

## Summary

Right-clicking anywhere on the Workspace Canvas opens a small popup
listing every registered widget type from the discovered catalog, with a
typeable filter box at the top that live-filters the list as the user
types. Choosing an entry adds a new instance of that widget type to the
current Desk at the right-click position.

Qt has no built-in "typeable-filter menu" widget, so this is a small
custom popup (`QLineEdit` filter box + `QListWidget` results, shown as a
`Qt.WindowType.Popup` so it auto-closes on click-away/focus-loss like a
normal menu) rather than a `QMenu`.

## Design

### `WidgetSpawnMenu` (`src/desk/shell/widget_spawn_menu.py`)

A `QWidget` with `Qt.WindowType.Popup` (auto-grabs the mouse and closes on
an outside click, same as `QMenu`) and `WA_DeleteOnClose`:

- A `QLineEdit` filter box (auto-focused on show, placeholder "Add
  widget…").
- A `QListWidget` below it, one row per matching widget (`item.setData`
  stores the `widget_id`; display text is the widget's `name`).
- Typing filters the list to entries whose `name` or `id` contains the
  (case-insensitive) query as a substring; the first match is
  auto-selected.
- An event filter on the line edit intercepts Up/Down (move the list
  selection without losing text-edit focus), Return/Enter (activate the
  current selection), and Escape (close without choosing) — everything
  else passes through to the line edit normally.
- Clicking or double-clicking a list row also activates it.
- Signal: `widget_chosen(str)` — the chosen `widget_id`. Emitted once,
  right before the popup closes itself.

### `WorkspaceView` (edit)

- `set_widget_catalog(catalog: dict[str, WidgetInfo])`: called once by
  `DeskWindow` at construction, so the view knows what's available to
  offer in the menu (the view otherwise has no reason to know about the
  wider widget catalog — this is its only piece of that knowledge, kept
  minimal).
- `contextMenuEvent(event)`: builds a `WidgetSpawnMenu` from the stored
  catalog (`{id: info.name for id, info in catalog.items()}`), positions
  it at `event.globalPos()`, connects `widget_chosen` to emit a new
  `widget_add_requested(str, QPointF)` signal with the chosen id and the
  right-click's *scene* position (`self.mapToScene(event.pos())`), and
  shows it.

### `DeskWindow` (edit)

- Connects `self.view.widget_add_requested` to a new
  `_on_widget_add_requested(widget_id, scene_pos)` handler that looks up
  the `WidgetInfo` in `self._widgets` and calls the existing
  `_place_widget(widget_id, widget, (scene_pos.x(), scene_pos.y()),
  widget.default_size)` — the same instantiation path already used for
  loading a Desk's saved widgets and for the fresh-desk fallback, so no
  new widget-construction logic is needed here at all.
- Calls `self.view.set_widget_catalog(widgets)` once, alongside the
  existing constructor wiring.

## Affected files

- `src/desk/shell/widget_spawn_menu.py` (new) — `WidgetSpawnMenu`.
- `src/desk/shell/canvas.py` (edit) — `set_widget_catalog`,
  `contextMenuEvent`, new `widget_add_requested` signal.
- `src/desk/shell/window.py` (edit) — wire the new signal to
  `_place_widget`, call `set_widget_catalog` once.

## Out of scope (for now)

- Any distinction between right-clicking empty canvas vs. right-clicking
  an existing widget's chrome/content — *any* right-click on the
  `WorkspaceView` opens this same menu. A widget-specific context menu
  (close/duplicate/etc.) would be a separate, later feature, not a
  reason to special-case this one.
- Keyboard-only invocation (a menu/context-menu key) — right-click only,
  matching the TODO item's literal ask.

## Verification

1. Headless: construct a `WidgetSpawnMenu` with a small fake catalog
   (`{"demo": "Demo", "other": "Other Widget"}`); confirm it starts with
   both rows listed and the first selected; type a filter string and
   confirm the list narrows to only matching rows; confirm Up/Down move
   the selection while the line edit keeps focus; confirm Return with a
   selection, and double-clicking a row, both emit `widget_chosen` with
   the right `widget_id` and then close the popup; confirm Escape closes
   without emitting anything.
2. Headless: `WorkspaceView.set_widget_catalog` + simulate a
   `contextMenuEvent` (constructing a real `QContextMenuEvent` and
   routing it through `sendEvent`, the same realistic-event-path
   technique used in earlier plans) — confirm a `WidgetSpawnMenu` becomes
   visible, populated from the catalog.
3. Headless: `DeskWindow._on_widget_add_requested` — confirm calling it
   adds exactly one new frame to `self.view._frames`, at the given
   position, of the right widget kind, without disturbing any
   already-placed widgets.
4. Full-cycle: launch the real app, confirm it still starts/quits
   cleanly with the new context-menu wiring in place (no crash
   constructing the menu infrastructure even though it's never actually
   opened by a real right-click in this headless check).
5. Actually right-clicking with a real mouse, typing into the filter, and
   confirming the popup visually is expected to be **skipped** for direct
   confirmation, per the precedent throughout this project (this
   environment can't drive real mouse/keyboard interaction) — the
   structural/logic pieces above are checked directly instead, including
   simulating the real `QContextMenuEvent` path rather than only calling
   `contextMenuEvent` as a plain method.

### Status (verification notes)

- Headless: `WidgetSpawnMenu` — confirmed it starts populated with all
  catalog entries (sorted by name) and the first row selected; typing a
  filter narrows the list to substring matches against name or id;
  Up/Down move the list selection via the line edit's event filter;
  Return with a selection, and emitting `itemActivated` directly
  (double-click's effect), both emit `widget_chosen` with the right
  `widget_id`; Escape closes without emitting anything.
- Headless: `WorkspaceView.set_widget_catalog` + a real
  `QContextMenuEvent` routed through `contextMenuEvent` — confirmed a
  `WidgetSpawnMenu` is created as a child of the view, populated from the
  catalog (`id -> name`), and that choosing an entry emits
  `widget_add_requested` with the right id and the right-click's scene
  position.
- Headless: `DeskWindow._on_widget_add_requested` — confirmed it adds
  exactly one new frame at the requested position/default size without
  disturbing existing widgets, and that an unknown `widget_id` is
  silently ignored (no crash) — a case that can't happen from the menu
  itself (which only ever offers known catalog ids) but is inexpensive to
  guard against.
- **Found a real environment/testing gotcha along the way**: a
  `Qt.WindowType.Popup` widget (used here to get `QMenu`-like
  click-away/focus-loss auto-close behavior) can get torn down (and, with
  `WA_DeleteOnClose`, have its underlying C++ object deleted) the moment
  `app.processEvents()` runs afterward in this headless/offscreen
  environment, since it never holds real window-manager focus here.
  Verified the widget's actual logic is correct by testing it directly
  (calling methods, feeding synthetic events) without an intervening
  event-loop turn between showing it and inspecting it — recorded in
  `LEARNINGS.md` for future headless testing of similar popups.
- Launched the real app (`python -m desk`); it starts and quits cleanly
  with the new context-menu wiring in place.
- Actually right-clicking with a real mouse and typing into the filter is,
  as anticipated, **skipped** for direct visual confirmation — this
  environment can't drive real mouse/keyboard interaction (same
  limitation noted throughout this project).

## Key design decisions / tradeoffs

- **Custom popup widget, not `QMenu`.** `QMenu`'s built-in keyboard
  handling does prefix/mnemonic jumping, not a persistent, editable
  filter query with live substring narrowing — there's no way to get a
  Spotlight/command-palette-style "typeable filter" out of a stock
  `QMenu`. A small dedicated widget is simpler than fighting `QMenu`'s
  event handling into behaving like something it isn't.
- **New widgets go through the existing `_place_widget` path, not a
  parallel one.** `DeskWindow` already has exactly the "given a
  `widget_id`/`WidgetInfo`/position/size, construct and place the right
  host type" logic (used for Desk loading and the fresh-desk fallback);
  reusing it here means the context-menu path can't drift out of sync
  with how widgets are placed anywhere else.
- **Any right-click opens the menu, with no special-casing for
  clicking-on-an-existing-widget.** Keeps this item's scope to exactly
  what was asked; differentiating "right-click empty canvas" from
  "right-click a widget" is a reasonable future feature (a
  widget-specific menu) but isn't needed to satisfy this TODO item.
