"""Mermaid Flowchart to SVG (TODO `05cfccc`). See design-docs/transforms.md.

A thin wrapper around desk.mermaid's parser/layout/scene-builder/SVG
-renderer -- reused exactly as-is, not reimplemented here. `parse`
dispatches by the source's own header regardless of which transform
calls it, so `Diagram.kind` is checked explicitly afterward to reject
state-diagram source reaching this flowchart-specific transform (and
vice versa for `mermaid_state_svg`)."""

from PyQt6.QtGui import QFont, QFontMetricsF, QPalette

from desk.mermaid import build_scene, layout, parse, render_svg


def _measure(text: str) -> tuple[float, float]:
    metrics = QFontMetricsF(QFont())
    return metrics.horizontalAdvance(text), metrics.height()


def run(input_data: str, config: dict | None) -> str:
    diagram = parse(input_data)
    if diagram.kind != "flowchart":
        raise ValueError(f"expected a flowchart diagram, got {diagram.kind!r}")
    result = layout(diagram, _measure)
    scene = build_scene(diagram, result, QPalette())
    return render_svg(scene)
