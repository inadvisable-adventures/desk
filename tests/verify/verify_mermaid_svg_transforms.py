import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")

from PyQt6.QtGui import QFont, QFontMetricsF, QPalette  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from desk.mermaid import MermaidParseError, build_scene, layout, parse, render_svg  # noqa: E402
from desk_services.transforms.service import TransformsService  # noqa: E402

REPO_ROOT = Path("/Users/mphair/inadvisable-adventures/desk")

passed = 0
failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


FLOWCHART_SOURCE = """flowchart TD
    A[Start Node] --> B{Decision}
    B --> C[End Node]
"""

STATE_SOURCE = """stateDiagram-v2
    [*] --> Idle
    Idle --> Running : begin
    Running --> [*]
"""

SEQUENCE_SOURCE = """sequenceDiagram
    Alice->>Bob: Hello Bob
"""


def _measure(text):
    metrics = QFontMetricsF(QFont())
    return metrics.horizontalAdvance(text), metrics.height()


def test_render_svg_produces_real_svg():
    diagram = parse(FLOWCHART_SOURCE)
    result = layout(diagram, _measure)
    scene = build_scene(diagram, result, QPalette())
    svg = render_svg(scene)
    check("render_svg produces a real, well-formed SVG document", svg.strip().startswith("<?xml") and "<svg" in svg)
    check("the flowchart's node label text appears in the rendered SVG", "Start Node" in svg)


def load_transform_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


flowchart_mod = load_transform_module(
    "mermaid_flowchart_svg_test", REPO_ROOT / "desk_transforms/mermaid_flowchart_svg/transform.py"
)
state_mod = load_transform_module("mermaid_state_svg_test", REPO_ROOT / "desk_transforms/mermaid_state_svg/transform.py")


def test_flowchart_transform_produces_real_svg():
    svg = flowchart_mod.run(FLOWCHART_SOURCE, None)
    check("mermaid_flowchart_svg.run() produces real SVG", "<svg" in svg and "Start Node" in svg)


def test_state_transform_produces_real_svg():
    svg = state_mod.run(STATE_SOURCE, None)
    check("mermaid_state_svg.run() produces real SVG", "<svg" in svg and "Running" in svg)


def test_flowchart_transform_rejects_state_source():
    try:
        flowchart_mod.run(STATE_SOURCE, None)
        check("mermaid_flowchart_svg.run() rejects state-diagram source", False)
    except ValueError as e:
        check("mermaid_flowchart_svg.run() rejects state-diagram source", "state" in str(e))


def test_state_transform_rejects_flowchart_source():
    try:
        state_mod.run(FLOWCHART_SOURCE, None)
        check("mermaid_state_svg.run() rejects flowchart source", False)
    except ValueError as e:
        check("mermaid_state_svg.run() rejects flowchart source", "flowchart" in str(e))


def test_both_transforms_propagate_mermaid_parse_error_for_unsupported_diagrams():
    try:
        flowchart_mod.run(SEQUENCE_SOURCE, None)
        check("mermaid_flowchart_svg.run() propagates MermaidParseError for unsupported diagrams", False)
    except MermaidParseError:
        check("mermaid_flowchart_svg.run() propagates MermaidParseError for unsupported diagrams", True)

    try:
        state_mod.run(SEQUENCE_SOURCE, None)
        check("mermaid_state_svg.run() propagates MermaidParseError for unsupported diagrams", False)
    except MermaidParseError:
        check("mermaid_state_svg.run() propagates MermaidParseError for unsupported diagrams", True)


def test_both_transforms_end_to_end_via_transforms_service():
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        real_flowchart_dir = REPO_ROOT / "desk_transforms" / "mermaid_flowchart_svg"
        real_state_dir = REPO_ROOT / "desk_transforms" / "mermaid_state_svg"

        import shutil

        shutil.copytree(real_flowchart_dir, project_dir / "mermaid_flowchart_svg")
        shutil.copytree(real_state_dir, project_dir / "mermaid_state_svg")

        service = TransformsService()
        transforms, errors = service.discover(None, project_dir)
        check(
            "TransformsService discovers both real Mermaid transforms with no errors",
            "mermaid_flowchart_svg" in transforms and "mermaid_state_svg" in transforms and not errors,
        )
        check(
            "discovered manifests report the expected input/output types",
            transforms["mermaid_flowchart_svg"].input_type == "mermaid-flowchart"
            and transforms["mermaid_flowchart_svg"].output_type == "svg"
            and transforms["mermaid_state_svg"].input_type == "mermaid-state",
        )

        flowchart_svg = service.run_blocking("mermaid_flowchart_svg", FLOWCHART_SOURCE)
        check("end-to-end run_blocking through the real service produces real SVG (flowchart)", "<svg" in flowchart_svg)

        state_svg = service.run_blocking("mermaid_state_svg", STATE_SOURCE)
        check("end-to-end run_blocking through the real service produces real SVG (state)", "<svg" in state_svg)


test_render_svg_produces_real_svg()
test_flowchart_transform_produces_real_svg()
test_state_transform_produces_real_svg()
test_flowchart_transform_rejects_state_source()
test_state_transform_rejects_flowchart_source()
test_both_transforms_propagate_mermaid_parse_error_for_unsupported_diagrams()
test_both_transforms_end_to_end_via_transforms_service()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
