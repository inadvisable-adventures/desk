"""Mermaid State Diagram to SVG (TODO `05cfccc`). See design-docs/transforms.md.

A thin wrapper around desk.mermaid's parser/layout/scene-builder/SVG
-renderer -- reused exactly as-is, not reimplemented here. See
mermaid_flowchart_svg/transform.py for why Diagram.kind is checked
explicitly rather than trusting parse() alone."""

from PyQt6.QtGui import QFont, QFontMetricsF, QPalette

from desk.mermaid import build_scene, layout, parse, render_svg


def _measure(text: str) -> tuple[float, float]:
    metrics = QFontMetricsF(QFont())
    return metrics.horizontalAdvance(text), metrics.height()


def run(input_data: str, config: dict | None) -> str:
    diagram = parse(input_data)
    if diagram.kind != "state":
        raise ValueError(f"expected a state diagram, got {diagram.kind!r}")
    result = layout(diagram, _measure)
    scene = build_scene(diagram, result, QPalette())
    return render_svg(scene)
