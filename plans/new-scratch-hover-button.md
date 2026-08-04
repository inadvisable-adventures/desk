# Always-visible lower-left "new Scratch" hover button (TODO `945b086`)

## Summary

Add a fourth pinned-HUD widget to the Workspace Canvas (alongside the
existing `DeskPicker` top-left, `ZoomControl` bottom-right, and
`TempUiNotificationStack` top-right — see `src/desk/shell/canvas.py`):
an always-visible button in the lower-left corner that, when clicked,
places a new Scratch widget (`SCRATCH_WIDGET_ID`) centered in the
current viewport and focuses its body, so typed characters go straight
into it with no extra click needed.

## Affected files

- `src/desk/shell/new_scratch_button.py` (new) — the button widget
  itself, matching the existing pinned-HUD widgets' shape
  (`desk_picker.py`, `zoom_control.py`).
- `src/desk/shell/canvas.py` — construct/position it in `WorkspaceView`,
  new `new_scratch_requested` signal.
- `src/desk/shell/window.py` — connect the signal, new
  `_open_focused_scratch(pos=None)` helper (shared with TODO `496d685`,
  which reuses it with a non-`None` pos).
- `tests/verify/` — new coverage.

## Design decisions

- **Plain `QLabel` child of `self.viewport()`**, not a scene item —
  identical shape to `DeskPicker`'s `_ClickableLabel`
  (`Qt.TextInteractionFlag.NoTextInteraction` per `CLAUDE.md`'s
  "labels shouldn't be user-selectable" convention,
  `PointingHandCursor`, hover restyle, `clicked` signal emitted from an
  overridden `mousePressEvent`). Copied as a small standalone class
  rather than importing `desk_picker._ClickableLabel` (a private,
  underscore-prefixed name not meant for cross-module reuse).
- **Never hidden** — built from the start the same way `DeskPicker` is
  (see TODO `e4662a5`'s conclusion that this is the right default for
  HUD chrome unless there's a specific reason to hide it, which there
  isn't here).
- **No arguments on the click signal** — `new_scratch_requested =
  pyqtSignal()`. Unlike `widget_add_requested`/`paste_requested` (which
  need a scene position from the click that triggered them), this
  button's placement is always "centered in the current viewport",
  independent of where the button itself sits.
- **Shared `_open_focused_scratch(pos: tuple[float, float] | None =
  None)` helper on `DeskWindow`**: `pos=None` → centered
  (`open_widget_content_centered`), otherwise → `open_widget_content(...,
  pos=pos)`. Either way, if a content widget was actually built, call
  `content.body.setFocus(Qt.FocusReason.MouseFocusReason)` — the same
  `.setFocus()`-on-embedded-content pattern already confirmed to work
  for `QGraphicsProxyWidget`-hosted content in
  `tests/verify/verify_widget_focus.py`. Written now so TODO `496d685`
  (double-click-to-scratch) can call it directly with a real pos
  instead of duplicating the "place + focus" logic.
- **Positioned via the same deferred (`QTimer.singleShot(0, ...)`)
  `move()`-off-viewport-size-and-margin pattern** every other pinned
  HUD widget uses, called from both `resizeEvent` and
  `scrollContentsBy` (the latter guarded by `hasattr`, matching the
  existing three) — `scrollContentsBy`'s docstring already explains why
  fast-scroll drift needs this for *any* plain-`QWidget`-child-of-
  the-viewport HUD element, not just the three that predate this one.
- **Icon/label text**: a short, unambiguous "+ Scratch" label (plain
  text, not an icon font — nothing in this codebase currently pulls in
  an icon font, and `CLAUDE.md` says avoid new dependencies).

## Step-by-step implementation

1. `src/desk/shell/new_scratch_button.py`: `NewScratchButton(QLabel)`
   with a `clicked = pyqtSignal()`, hover restyle, matching the visual
   language (`rgba(40, 42, 46, ...)` panel, `61, 174, 233` accent on
   hover) already used by `DeskPicker`/`ZoomControl`.
2. `canvas.py`: import it, add `NEW_SCRATCH_BUTTON_MARGIN = 12`,
   construct `self.new_scratch_button = NewScratchButton(self.viewport())`
   in `WorkspaceView.__init__` right after the other three HUD widgets,
   connect its `clicked` to `self.new_scratch_requested.emit`, add
   `_position_new_scratch_button()` (bottom-left: `x = MARGIN`, `y =
   viewport height - hint.height() - MARGIN`), call it from `__init__`,
   `resizeEvent`, and `scrollContentsBy`.
3. New `WorkspaceView.new_scratch_requested = pyqtSignal()` class
   attribute (alongside the other signals near the top of the class).
4. `window.py`: connect `self.view.new_scratch_requested.connect(self._on_new_scratch_requested)`
   near the other `self.view.*.connect(...)` calls in `__init__`. Add
   `_open_focused_scratch(pos=None)` and `_on_new_scratch_requested`
   (calls `self._open_focused_scratch()`).
5. New verify coverage (see below); run the full `tests/verify/` suite.

## Key tradeoffs

- A fourth always-on HUD element in the corner is more visual chrome
  permanently on screen — accepted as the direct ask (an
  always-visible button), same tradeoff already made for `DeskPicker`.
- No keyboard shortcut equivalent added — out of scope, this item is
  specifically about the hovering button.

## Verification

New script `tests/verify/verify_new_scratch_button.py`, real
`WorkspaceView`/`DeskWindow`-shaped `_FakeWindow` (matching the
`_FakeWindow` recipe from `verify_discuss_parking_lot_item.py`/
`verify_tempui_doc_upgrade_notification.py`: real `_place_widget`,
`open_widget`, `open_widget_content`, `open_widget_content_centered`
bound from the real `DeskWindow` class), no mocking:
- The button is visible immediately after construction (no `.show()`
  needed first, matching the other always-visible HUD widgets).
- Clicking it places a real Scratch widget frame on the canvas,
  centered in the viewport.
- The new Scratch's `body` (`QPlainTextEdit`) has real Qt focus
  immediately after the click (`body.hasFocus()` / the proxy's
  embedded focus chain), confirmed via
  `QGraphicsScene.focusItem()`/`view.scene().focusItem()` reflecting
  the new frame, not just calling `.setFocus()` and trusting it.
- Full `tests/verify/` regression suite.
