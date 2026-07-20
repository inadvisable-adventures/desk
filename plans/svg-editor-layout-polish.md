# Plan: TODO 556f623 (COMPLETED) — SVG Editor layout polish (hex label, square viewBox, toolbox sections)

Direct user feedback, three independent UI/layout refinements:

1. The hex-preview buttons currently carry their own full labels ("Hex
   (Flat-top) Preview" / "Hex (Pointy-top) Preview"). Replace with a
   small, shared, two-line "Hex Preview" `QLabel` on the left side of
   `hex_preview_frame`, and shorten the buttons themselves to just
   "Flat-top" / "Pointy-top" — the shared label makes clear both
   buttons are part of the same feature, without repeating "Hex
   Preview" on each button.
2. `_new_empty_root()`'s default document (`viewBox`/`width`/`height`
   = `"0 0 400 300"`/`"400"`/`"300"`) isn't square, so neither hex
   preview orientation fits the document's own bounds by default
   (flat-top would already overflow width, pointy-top is inscribed to
   the shorter dimension). Change the default to a square (`400x400`).
   `_DEFAULT_BOUNDS` (the fallback `_document_bounds` uses for a
   loaded file with no usable `viewBox`/`width`/`height`) is changed
   to match, for the same reason and for consistency between the two
   "no information available" cases.
3. `_build_toolbox()` currently lists all 10 tools in one flat column
   with no grouping. Split into two headed sections: "Select + Edit"
   (Shapes, Points) at the top, then "Add" (Rectangle, Circle,
   Ellipse, Line, Polyline, Polygon, Path, Text) below it. Still one
   `QButtonGroup(exclusive=True)` spanning both sections — this is
   purely a visual reorganization, not a change to how many tools can
   be active at once.

## Design

### (1) Shared hex-preview label

Add a `QLabel("Hex\nPreview")` to `hex_preview_layout` *before* the two
buttons. Smaller font via a `setStyleSheet` (e.g. `font-size: 9pt;`),
and non-user-selectable via
`setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)` —
matching this codebase's existing convention for UI labels (see
`self._label`) and this project's own house rule (`CLAUDE.md`: "the
labels for UI elements should not be user-selectable, unless that is
specifically requested"). Button text becomes `"Flat-top"` /
`"Pointy-top"`.

### (2) Square default bounds

- `_new_empty_root()`: `viewBox="0 0 400 400"`, `width="400"`,
  `height="400"`.
- `_DEFAULT_BOUNDS = QRectF(0, 0, 400, 400)`.

`tests/verify/verify_svg_editor_widget.py`'s existing
`test_document_bounds_parsing` check ("falls back to the 400x300
default when nothing usable is present") needs updating to 400x400 to
match — a stale assertion made stale by this exact change, per
`development-process.md`'s "fix what your own change made stale"
expectation. Any test that constructs its own explicit non-square
`viewBox` (e.g. the `"0 0 400 300"` literal in the guide-rect test)
is unaffected — those are testing a *loaded* document's own declared
bounds, not either default.

### (3) Toolbox sections

Split the existing single `TOOL_LABELS` list into
`SELECT_EDIT_TOOL_LABELS = [("shapes", "Shapes"), ("points", "Points")]`
and `ADD_TOOL_LABELS` (the remaining 8, in their current relative
order); `TOOL_LABELS` becomes their concatenation (kept as the
single source of truth for "all valid tool ids", still useful even
though nothing outside `_build_toolbox` currently iterates it).
`_build_toolbox()` adds a non-selectable `QLabel("Select + Edit")`
header, then buttons for `SELECT_EDIT_TOOL_LABELS`, then a
`QLabel("Add")` header, then buttons for `ADD_TOOL_LABELS` — all still
registered with the same single `QButtonGroup(exclusive=True)` as
today, so exactly one tool remains active at a time.

## Verification

Extend `tests/verify/verify_svg_editor_widget.py`:

- The two hex-preview buttons' text is now `"Flat-top"`/`"Pointy-top"`
  (not the old full labels), and a label with the shared "Hex
  Preview" text exists as a sibling inside `hex_preview_frame`.
- `_new_empty_root()` produces a square document (`_document_bounds`
  gives equal width/height, 400x400).
- `_DEFAULT_BOUNDS` is 400x400; update the existing
  `test_document_bounds_parsing` fallback assertion to match.
- The toolbox contains a "Select + Edit" label positioned before the
  Shapes/Points buttons, and an "Add" label positioned before the
  remaining tool buttons (verify via the layout's widget order); all
  10 tool buttons are still members of the same exclusive button
  group.
- Full `tests/verify/` regression suite.
