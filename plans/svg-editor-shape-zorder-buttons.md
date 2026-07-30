# Plan: TODO 217f3ce — SVG Editor shape actions menu: Move Forward / Move Backward (z-order)

Adds two more buttons to `self._shape_actions_menu` (TODO `70789ee`):
"Move Forward" (▲, tooltip "Move Forward") and "Move Backward" (▼,
tooltip "Move Backward") — one-step z-order swaps with the adjacent
sibling in `self._objects`' own order, placed between the existing
Duplicate and Delete buttons.

## Design

Today a shape's paint order is implicit and singular: document order
in `self._root`'s children == `self._objects` list order == the order
each item was added to `self._scene` (`_add_object`) — nothing sets an
explicit `QGraphicsItem.zValue()` on a real drawn shape (only the
non-exported guide rect/hex-preview mask do, at fixed `-1000`/`2000`).
Confirmed directly (a real `QGraphicsScene`, three real items, real
`.items()` calls): items with equal z-value paint in *insertion* order,
last-added on top, and `QGraphicsItem.stackBefore(sibling)` reorders
within that same insertion-order list — `sibling.stackBefore(item)`
moves `sibling` to just before `item` in that list, i.e. `item` ends up
stacked *above* `sibling` afterward.

`_move_selected_object(direction: int)` (`direction` is `+1` forward,
`-1` backward):

1. `index = self._objects.index(obj)`; `new_index = index + direction`;
   no-op (silently) if out of range — already at the front/back.
2. `other = self._objects[new_index]`.
3. Swap `obj.element`/`other.element` in `self._root`'s children —
   confirmed directly that `ET.Element` supports list-style item swap
   (`root[i], root[j] = root[j], root[i]`) — found each element's own
   *actual* index within `self._root`'s children first (not assumed
   adjacent there — an untouched/unrecognized element, e.g. a comment
   or unsupported `<path>`, could sit between them in the raw XML even
   though they're adjacent in `self._objects`), so this is a targeted
   two-slot swap, not a naive adjacent-swap.
4. Swap `self._objects[index]`/`self._objects[new_index]`.
5. Reflect the same swap in the scene's own stacking order:
   `other.item.stackBefore(obj.item)` for forward (`obj` ends up above
   `other`), `obj.item.stackBefore(other.item)` for backward (`obj`
   ends up below `other`).

No handle/menu refresh needed afterward — selection and geometry are
unchanged, only paint order.

## Verification

Extend `tests/verify/verify_svg_editor_widget.py`:

- Two new buttons in `_shape_actions_menu`, correct glyph/tooltip
  each, positioned between Duplicate and Delete.
- Three real objects: moving the middle one forward swaps it with the
  one currently in front of it in `self._objects`, and swaps their
  respective elements' actual positions in `self._root`'s children
  (checked via each element's real index there, not assumed adjacency)
  — same for backward. A real `QGraphicsScene.items()` call (topmost
  first, per Qt's own documented behavior) confirms the *actual paint
  order* changed correctly, not just the two Python-side lists.
  Attempting to move the frontmost object forward (or the backmost
  one backward) is a no-op on all three (objects list, root children,
  scene stacking order all unchanged).
- Full `tests/verify/` regression suite.
