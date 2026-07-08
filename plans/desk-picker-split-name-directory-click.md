# Desk picker: split name/directory, stable name picker, direct directory click (TODO 8beab6e) (COMPLETED)

## Summary

TODO 8beab6e: the top-left Desk picker (`DeskPicker`) always shows the
current Desk's name and directory, which is good, but its hover
interaction is "finicky and strange" — hovering pops a `QComboBox` (MRU
list) and a `QPushButton` ("Directory…") out to the side of the always
-visible label. Requested instead:

1. The name and directory should read as visually distinct, independently
   -interactive elements (not just one plain label), including on hover.
2. Clicking the **name** opens a more stable picker than the current
   combo-box (which needs a hover to reveal, then a further click to
   actually open its own native popup, and is easy to lose by moving the
   mouse off it before finishing).
3. Clicking the **directory** immediately opens the directory picker —
   no separate "Directory…" button.

## Affected files

- `src/desk/shell/desk_picker.py` (edit) — the whole rework.
- `design-docs/widget-ux.md` (edit) — Desk Picker section no longer
  matches once this changes.

## Design

### Two independently clickable label "chips" instead of one label + hover controls

Replace the single `QLabel` with two small `_ClickableLabel(QLabel)`
instances — `_name_label` and `_directory_label` — separated by a plain,
non-interactive `"—"` `QLabel`. Each keeps its own half-alpha rounded
-pill background (the same visual language the old single label used),
but styled distinctly:

- Name: bold, brighter text (`#e8e8e8`) — the primary identifier.
- Directory: regular weight, dimmer text (`#b8bcc2`) — secondary detail.

`_ClickableLabel` (new, private) owns:

- A `clicked` signal, emitted from `mousePressEvent` on a left click
  (plain `QWidget` children of the viewport get real mouse events
  directly — no `QGraphicsProxyWidget`-embedding involved here, unlike
  widget content on the canvas, so this needs none of
  `design-docs/widget-ux.md`'s Zoom-Correct-Dragging workarounds).
- `enterEvent`/`leaveEvent` swapping its own stylesheet between a base
  style and a hover style (brighter accent-colored background matching
  the app's existing `#3daee9` accent — see `widgets/todo/widget.py`'s
  `FILTER_BUTTON_STYLE` — plus an underline), independent of the other
  label's hover state. This is what makes them read as genuinely
  distinct, separately-clickable regions instead of one ambiguous label.
- `Qt.CursorShape.PointingHandCursor` and
  `Qt.TextInteractionFlag.NoTextInteraction` (per `CLAUDE.md`'s
  "labels shouldn't be user-selectable" convention — still a label, just
  a clickable one).

`DeskPicker.enterEvent`/`leaveEvent`/`_set_expanded` are removed entirely
— there's no more whole-widget hover state, only each chip's own.

### Name click: a stable list popup instead of a `QComboBox`

A new private `_DeskListPopup(QWidget)`, shown on `_name_label.clicked`,
mirrors `WidgetSpawnMenu`'s established "Popup" pattern
(`Qt.WindowType.Popup`, `WA_DeleteOnClose`) but only needs a plain
`QListWidget` (no live filter box — MRU lists are short): every MRU entry
as an item (current one pre-selected via `setCurrentItem`), plus a
trailing `"…"` item (the existing `BROWSE_LABEL`). A single click/Enter
on an item (`itemClicked`/`itemActivated`) immediately fires and closes
— no separate confirm step needed, since picking *is* the action, same
as the old combo box's `activated` signal.

This is "more stable" than the combo box for the reasons in the Summary:
it's fully visible immediately (no second click to open a nested native
popup), and closes via the same click-away/Escape convention as every
other popup in this app, rather than a hover-reveal disappearing early.

`_DeskListPopup` exposes the same `desk_chosen(Path)`/`browse_requested()`
signals `DeskPicker` already does, connected straight through
(`popup.desk_chosen.connect(self.desk_chosen)` — signal-to-signal
forwarding) so `DeskPicker`'s own external API, and therefore
`DeskWindow`'s wiring, is unchanged.

### Directory click: emit `directory_change_requested` directly

`_directory_label.clicked` connects straight to
`self.directory_change_requested` (again, signal-to-signal). No more
`QPushButton`, no more "Directory…" text — the directory *is* the
button now.

### State DeskPicker needs to keep

`set_mru(entries, current)` no longer populates a `QComboBox`; it just
remembers `self._mru_entries`/`self._current_path` (still inserting
`current` at the front if the MRU list hasn't caught up yet — see
`plans/fix-desk-picker-label.md`, unaffected by this rework) so a later
name-click can build the popup with current data. `set_current(name,
directory)` sets both labels' text and calls `self.adjustSize()` (both
methods already call this today — kept, not introduced, per
`plans/fix-desk-picker-label.md`'s fix).

### `DeskWindow` changes

None. `desk_chosen`, `browse_requested`, and `directory_change_requested`
keep their exact signatures and meaning; `src/desk/shell/window.py`'s
three `.connect()` calls in `DeskWindow.__init__` are untouched.

## Verification

Entirely headless (`QT_QPA_PLATFORM=offscreen`):

1. `set_current`/`set_mru` populate both labels' text and internal MRU
   state correctly (including the "current not yet in MRU" insert-at
   -front case).
2. Clicking `_name_label` opens a `_DeskListPopup` listing the right
   entries with the right one pre-selected; activating an MRU item emits
   `desk_chosen(path)` on `DeskPicker` itself; activating the trailing
   `"…"` item emits `browse_requested()`.
3. Clicking `_directory_label` emits `directory_change_requested()`
   directly, with no dialog of its own.
4. Each label's hover style differs from the other's and reverts on
   leave, confirming they're independently stateful (not one shared
   toggle).
5. Regression: `DeskWindow`'s three existing `.connect()` wirings still
   receive the right signals end-to-end.

## Status

Implemented and verified headlessly:

1. `set_current`/`set_mru` populate both labels' text and the internal
   MRU/current state correctly, including the "current not yet in MRU"
   insert-at-front case.
2. Confirmed each `_ClickableLabel`'s hover style is independent: hovering
   the name label leaves the directory label's stylesheet untouched, and
   vice versa; both revert correctly on leave.
3. Clicking `_directory_label` emits `directory_change_requested()`
   directly, with no dialog of its own.
4. Clicking `_name_label` opens a `_DeskListPopup` with the exact expected
   entries (MRU + current, deduplicated, in order, plus the trailing
   `"…"`) and the current desk pre-selected; activating an MRU item emits
   `desk_chosen(path)` with the right path and closes the popup;
   activating the trailing entry emits `browse_requested()`.
5. Regression, full-app: constructed a real `DeskWindow` (unrelated to
   this change, but exercises the same picker wiring `DeskWindow.__init__`
   sets up) and confirmed it still boots correctly with the reworked
   `DeskPicker` in place — no changes were needed in `window.py`, since
   `DeskPicker`'s external signal API is unchanged.

This is a native Qt app, not a browser one, so all of the above was
driven directly against the real widget classes under
`QT_QPA_PLATFORM=offscreen` — no browser launch applicable or skipped.
