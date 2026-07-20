# Plan: TODO 9874bc3 (COMPLETED) — SVG Editor hex preview: visual grouping + flat-top sizing

Follow-up to TODO `1c7d5b9` (the flat-top/pointy-top button split). Two
independent refinements, direct from user feedback:

1. Separate the two hex-preview buttons from the rest of the toolbar
   with a frame + spacing, and visually distinguish the buttons
   themselves from the plain toolbar buttons (Open/Save/Save As/Reset
   View).
2. The flat-top hex should be sized so its top/bottom edges land
   exactly on the document's own bounds (`viewBox`), while staying a
   *regular* hexagon (constant radius, all six sides/angles equal) —
   not just inscribed the same way the pointy-top orientation already is.

## Design

### (1) Visual grouping

Established precedent already exists in this exact codebase for
"group of related checkable buttons, framed and distinctly styled" —
`widgets/todo/widget.py`'s `filter_frame`
(`QFrame.Shape.StyledPanel` + a `QHBoxLayout` with margins/spacing) and
its `FILTER_BUTTON_STYLE` constant (a `QPushButton`/`QPushButton:checked`
QSS rule, whose own comment explains exactly why: "a plain
`QPushButton(checkable=True)` looks nearly identical checked vs.
unchecked on some platform styles (macOS's native style included)").
Mirror that shape directly rather than inventing something new:

- A `_HEX_PREVIEW_BUTTON_STYLE` QSS constant (own module-level constant,
  not a re-import of `todo`'s — no cross-widget coupling for a shared
  style string), giving the two buttons a distinct look from the
  plain toolbar buttons in both their unchecked and `:checked` states.
- A `QFrame(QFrame.Shape.StyledPanel)` wrapping a `QHBoxLayout`
  (its own margins/spacing) holding the flat-top/pointy-top buttons;
  this frame is what gets added to `top_toolbar`, not the two buttons
  directly — giving the visible border/grouping the user asked for,
  plus the toolbar's own existing spacing separates the frame from its
  neighbors the same way `todo` widget's `toolbar.addWidget(filter_frame)`
  + surrounding widgets already does.

### (2) Flat-top sizing

For a regular hexagon with circumradius `R` (center-to-vertex):
- Pointy-top: vertex-to-vertex (top-to-bottom) = `2R`; flat-to-flat
  (left-right) = `R * sqrt(3)`.
- Flat-top: flat-to-flat (top-to-bottom, since the flat edges are on
  top/bottom for this orientation) = `R * sqrt(3)`; vertex-to-vertex
  (left-right) = `2R`.

`_hexagon_path` currently uses `radius = min(bounds.width(),
bounds.height()) / 2` for *both* orientations — for flat-top, that
inscribes the hex to the shorter dimension, not necessarily aligning
top/bottom with the bounds at all. Fix: for `flat_top=True` only,
solve for the radius that makes the flat-to-flat height exactly equal
`bounds.height()`: `radius = bounds.height() / math.sqrt(3)`. Still a
single, constant radius (regular hexagon, unchanged shape) — this can
legitimately make the hex *wider* than the document if `2 * radius >
bounds.width()` (a tall/narrow document), which is accepted
deliberately: real flat-top hex-tile art conventionally spans the
tile's full height and overlaps horizontally in an actual tessellated
grid, matching what this preview is trying to show. Pointy-top's own
sizing is unchanged (still `min(width, height) / 2`).

## Verification

Extend `tests/verify/verify_svg_editor_widget.py`:

- The two hex-preview buttons live inside a `QFrame`, not directly in
  `top_toolbar`'s own widget list.
- `_hexagon_path(bounds, flat_top=True)`'s vertical extent (bounding
  rect height) matches `bounds.height()` (within floating-point
  tolerance) for a non-square document; its horizontal extent is
  `2 * radius`, independent of `bounds.width()` (confirms it's sized
  off height alone, not clamped to fit width).
- The hexagon stays regular at the new radius (all six edge lengths
  equal, within tolerance) — not just "the right height," genuinely
  still a proper hexagon.
- Pointy-top's own sizing is unchanged (still `min(width, height) / 2`
  behavior, same as before this TODO).
- Full `tests/verify/` regression suite.
