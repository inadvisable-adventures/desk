# Plan: TODO a9e2ba7 (COMPLETED) — Markdown widget consumes Mermaid transforms via the Desk Service

See `design-docs/transforms.md`'s "Markdown widget: consuming
transforms via the Desk Service" section for the design rationale.

## Changed files

- **`src/desk/svg_view.py`** (new): `SvgView`, extracted verbatim from
  `widgets/image_viewer/widget.py`'s private `_AspectSvgView` (a bare
  `QSvgRenderer` into a letterboxed, aspect-preserving rect via
  `desk.geometry.fit_rect`), so the Markdown widget's own Mermaid-as-
  SVG rendering can reuse it instead of duplicating it. `_content_size`
  renamed to public `content_size()` — genuinely useful outside the
  class now too (a caller embedding this in a layout that doesn't
  otherwise size it needs the content's natural size to compute a
  sensible widget height).
- **`widgets/image_viewer/widget.py`**: deletes its own
  `_AspectSvgView`, imports `SvgView` from `desk.svg_view` instead;
  updated the handful of docstring/comment references.
- **`src/desk/mermaid.py`**: adds `detect_diagram_kind(text) -> str |
  None` (`"flowchart"` | `"state"` | `None`) — the diagram kind
  `parse()` would dispatch to, without doing the full parse; lets the
  Markdown widget decide which transform to call (or skip straight to
  the plain-text fallback for an unsupported type) without duplicating
  this module's own header-detection regexes. **Deletes
  `MermaidDiagramWidget`** (the `QGraphicsView` subclass) — this is the
  item that removes its one remaining caller, so this is the right
  place for its deletion (see TODO `05cfccc`'s own sequencing note).
  Removes now-unused `QFrame`/`QGraphicsView` imports.
- **`widgets/markdown/widget.py`**: `_build_block_widget`'s `"mermaid"`
  branch now calls a new `_build_mermaid_widget(content)`: detects the
  diagram kind (`detect_diagram_kind`), maps it to a transform id
  (`mermaid_flowchart_svg`/`mermaid_state_svg`), calls
  `current_context.get_transform_runner_blocking()(transform_id,
  content, None)`, and on success displays the returned SVG via a new
  `SvgView` (sized from its own `content_size()`, bounded the same way
  `MermaidDiagramWidget.MAX_HEIGHT` used to be). Any failure (no
  transform for this diagram type, no runner registered, the
  transform itself raising, or invalid/unparseable SVG output) falls
  back to a new `_mermaid_fallback_widget(content)` — the raw source
  text (monospace, selectable) plus the same "(unsupported or
  unparseable Mermaid diagram)" note `MermaidDiagramWidget`'s own
  except-branch used to show, now as a plain `QLabel`-based widget
  instead of a `QGraphicsScene` (no interactive scene needed for
  content that never renders as a diagram anyway). A broken transform
  call is caught broadly (`except Exception`) and logged, never
  propagated — matches TODO `810a5d6`'s "a broken call must never
  propagate out of here" discipline, since this runs while building a
  document's block widgets.

## Verification

- New `tests/verify/verify_markdown_mermaid_transforms.py`:
  `_build_mermaid_widget` calls the correct transform id for
  flowchart/state content (a fake runner recording its calls); an
  unsupported diagram type (`sequenceDiagram`) never calls any
  transform at all and shows the plain-text fallback with the raw
  source + explanatory note; a successful transform result renders as
  a real, valid `SvgView`; a transform that raises, one that returns
  invalid SVG, and no registered runner at all all fall back to plain
  text gracefully (never a crash); a real end-to-end pass through a
  real `TransformsService` (the actual `desk_transforms/
  mermaid_flowchart_svg`/`mermaid_state_svg` directories, real
  `run_blocking`) for both diagram kinds.
- Re-run `tests/verify/verify_image_viewer_svg_integration.py` to
  confirm the `SvgView` extraction didn't regress the Image Viewer
  widget.
- Full `tests/verify/` regression suite.
