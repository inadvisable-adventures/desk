# Plan: TODO 70789ee — SVG Editor shape actions context menu (duplicate + delete)

From `../FEEDBACK/FEEDBACK-DESK-svg-editor-duplicate-shape-button-2026-07-22-1819.md`,
revised per direct user instruction: instead of a second floating corner
button (`_shape_duplicate_button`) alongside the existing corner-anchored
`_shape_delete_button` (TODO `1fb365e`), replace both with a single
context-menu-style panel shown near a selected shape (Shapes tool only —
the Points tool's single `_point_delete_button` is untouched, out of
scope here), containing Duplicate and Delete.

## Design

### Not a real `QMenu`/`Qt.WindowType.Popup` — a floating `QFrame`, like the affordance it replaces

This app already has exactly one precedent for "a menu-like popup near a
canvas location" — `WidgetSpawnMenu` (`Qt.WindowType.Popup`, positioned
via `.move(event.globalPos())` on a real right-click). That shape
doesn't fit here: a `Qt.WindowType.Popup` window auto-closes the instant
it loses focus or the user clicks anywhere else — exactly wrong for this
feature, which (like the button it replaces) must stay visible and
keep tracking the shape for as long as it's selected, refreshed on every
drag/resize step, tool switch, and reload, not dismissed by clicking the
shape's own resize handles or dragging it. It would also auto-clamp to
the *desktop screen*, not this widget's own view — the user's own
three-tier fallback is explicitly scoped to whether the menu stays
within *this view* (`self._view`), not the screen.

So: `self._shape_actions_menu`, a `QFrame(self._view)` (same
floating-child-widget-of-the-view shape as `_complete_button`/the
button it replaces), `QFrame.Shape.StyledPanel` so it visually reads as
a small contextual panel, holding a `QHBoxLayout` with the two action
buttons — refreshed from the exact same call sites `_refresh_handles()`
already drives everything else from (selection change, tool switch,
every drag step), plus `_reset_view`/`_EditorView.resizeEvent` like the
button it replaces.

### Buttons: icon + hover text each

- `self._shape_duplicate_button`: text `"⧉"` (the icon, following this
  file's own existing convention of a plain-text glyph *as* the icon —
  same shape as `widget_frame.py`'s `🔒`/`🔓`/`👁` chrome buttons, not a
  real `QIcon`/pixmap), `setToolTip("Duplicate")`.
- `self._shape_delete_button` (moved into the new frame, no longer its
  own standalone floating widget): text `"🗑"` (replacing `"✕"`, per
  instruction), `setToolTip("Delete")`, keeps its existing red-tinted
  style (still a destructive action, worth the visual signal alongside
  the trash-can glyph itself).

### Positioning: three-tier fallback, checked against this view's own bounds

`_refresh_shape_actions_menu()` (replaces `_refresh_shape_delete_button`
as the call-site name everywhere it was called from):

1. `menu.adjustSize()` for its current real size.
2. Three candidate top-left positions, computed from the selected
   shape's `sceneBoundingRect()` mapped through `self._view.mapFromScene`:
   - (a) menu's bottom-center at the shape's top-center.
   - (b) menu's top-center at the shape's bottom-center.
   - (c) menu's center at the shape's own center.
3. Try (a); if `QRect(candidate, menu.size())` isn't fully contained in
   `self._view.rect()` (this widget's own view bounds — matching how
   every other floating button here is already positioned relative to
   `self._view`, not `self._view.viewport()`), try (b); if that also
   doesn't fit, use (c) unconditionally (no further fallback beyond it,
   per the user's own three-tier spec).
4. `move()`/`raise_()`/`show()` at the chosen position; `hide()`
   entirely under the same guard the button it replaces already used
   (`current_tool != "shapes" or self._selected_object is None`).

### `_duplicate_selected_object`

A genuine improvement over the feedback's own sketch, not just a
relocation of it: the sketch manually re-implements `_add_object`'s own
body inline (set flags, add to scene, append to `self._root`/
`self._objects`, clear selection, select) — reuse `_add_object` directly
instead, since it already does exactly that:

```python
def _duplicate_selected_object(self) -> None:
    obj = self._selected_object
    if obj is None:
        return
    cloned_element = copy.deepcopy(obj.element)
    cls = TAG_TO_CLASS[_local_tag(cloned_element.tag)]
    new_obj = cls.from_element(cloned_element)
    new_obj.item.moveBy(12, 12)
    self._add_object(new_obj)
```

`_add_object` itself appends `obj.element` to `self._root` — `_duplicate
_selected_object` must *not* also append `cloned_element` there itself
(the one thing the sketch's manual inlining would double-do if reused
verbatim). New `import copy` at the top of the file.

## Verification

Extend `tests/verify/verify_svg_editor_widget.py`:

- Selecting a shape in the Shapes tool shows `_shape_actions_menu`
  (containing both buttons, both visible, both with the right text and
  tooltip); switching tools or clearing selection hides it (mirrors the
  existing delete-button tests, now against the menu frame).
- Clicking Duplicate creates a new object of the same tag with the same
  attributes (offset by the fixed nudge), selects it, and leaves the
  original untouched; clicking Delete still removes the selected object
  exactly as before.
- Positioning: construct scenarios (via a resized, shown widget) where
  (a) fits, where (a) doesn't but (b) does (shape near the view's top
  edge), and where neither (a) nor (b) fits (shape larger than the
  view, or the view too small) — confirm each resolves to the right
  tier, checked via `self._view.rect().contains(QRect(menu.pos(),
  menu.size()))` for the tiers expected to fit, and the specific
  expected anchor point otherwise.
- Full `tests/verify/` regression suite.
