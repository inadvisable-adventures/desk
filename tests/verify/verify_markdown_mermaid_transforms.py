import importlib.util
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")

from PyQt6.QtWidgets import QApplication, QLabel  # noqa: E402

app = QApplication(sys.argv)

from desk.shell import current_context  # noqa: E402
from desk.svg_view import SvgView  # noqa: E402
from desk_services.transforms.service import TransformsService  # noqa: E402

REPO_ROOT = Path("/Users/mphair/inadvisable-adventures/desk")

_spec = importlib.util.spec_from_file_location("markdown_widget_mermaid_test", REPO_ROOT / "widgets/markdown/widget.py")
markdown_widget = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(markdown_widget)

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
"""

STATE_SOURCE = """stateDiagram-v2
    [*] --> Idle
"""

SEQUENCE_SOURCE = """sequenceDiagram
    Alice->>Bob: Hello Bob
"""


def find_labels(widget):
    return widget.findChildren(QLabel)


def test_flowchart_calls_the_right_transform():
    calls = []

    def fake_runner(transform_id, content, config):
        calls.append((transform_id, content, config))
        raise RuntimeError("no real transform needed for this check")

    with patch.object(current_context, "get_transform_runner_blocking", return_value=fake_runner):
        markdown_widget._build_mermaid_widget(FLOWCHART_SOURCE)

    check(
        "a flowchart block calls the mermaid_flowchart_svg transform with its own content",
        calls == [("mermaid_flowchart_svg", FLOWCHART_SOURCE, None)],
    )


def test_state_calls_the_right_transform():
    calls = []

    def fake_runner(transform_id, content, config):
        calls.append((transform_id, content, config))
        raise RuntimeError("no real transform needed for this check")

    with patch.object(current_context, "get_transform_runner_blocking", return_value=fake_runner):
        markdown_widget._build_mermaid_widget(STATE_SOURCE)

    check(
        "a state-diagram block calls the mermaid_state_svg transform with its own content",
        calls == [("mermaid_state_svg", STATE_SOURCE, None)],
    )


def test_unsupported_diagram_skips_the_transform_entirely():
    calls = []

    def fake_runner(transform_id, content, config):
        calls.append((transform_id, content, config))
        return "<svg></svg>"

    with patch.object(current_context, "get_transform_runner_blocking", return_value=fake_runner):
        widget = markdown_widget._build_mermaid_widget(SEQUENCE_SOURCE)

    check("an unsupported diagram type never calls any transform at all", calls == [])
    labels = find_labels(widget)
    check(
        "an unsupported diagram type shows the raw source in the plain-text fallback",
        any("Alice->>Bob" in label.text() for label in labels),
    )
    check(
        "the fallback shows the explanatory note",
        any("unsupported or unparseable" in label.text() for label in labels),
    )


def test_successful_render_returns_a_valid_svg_view():
    def fake_runner(transform_id, content, config):
        return '<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>'

    with patch.object(current_context, "get_transform_runner_blocking", return_value=fake_runner):
        widget = markdown_widget._build_mermaid_widget(FLOWCHART_SOURCE)

    check("a successful transform result renders as a real, valid SvgView", isinstance(widget, SvgView) and widget.is_valid())


def test_transform_failure_falls_back_to_plain_text():
    def failing_runner(transform_id, content, config):
        raise RuntimeError("deliberate failure")

    with patch.object(current_context, "get_transform_runner_blocking", return_value=failing_runner):
        widget = markdown_widget._build_mermaid_widget(FLOWCHART_SOURCE)

    check("a transform that raises falls back to plain text, not a crash", not isinstance(widget, SvgView))
    labels = find_labels(widget)
    check("the failure's fallback shows the raw source", any("Start Node" in label.text() for label in labels))


def test_invalid_svg_output_falls_back_to_plain_text():
    def bad_runner(transform_id, content, config):
        return "this is not valid svg at all"

    with patch.object(current_context, "get_transform_runner_blocking", return_value=bad_runner):
        widget = markdown_widget._build_mermaid_widget(FLOWCHART_SOURCE)

    check("invalid SVG output from a transform falls back to plain text, not a broken view", not isinstance(widget, SvgView))


def test_no_runner_registered_falls_back_gracefully():
    with patch.object(current_context, "get_transform_runner_blocking", return_value=None):
        widget = markdown_widget._build_mermaid_widget(FLOWCHART_SOURCE)

    check("no registered transform runner at all still falls back gracefully", not isinstance(widget, SvgView))


def test_real_end_to_end_via_a_real_transforms_service():
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        shutil.copytree(REPO_ROOT / "desk_transforms" / "mermaid_flowchart_svg", project_dir / "mermaid_flowchart_svg")
        shutil.copytree(REPO_ROOT / "desk_transforms" / "mermaid_state_svg", project_dir / "mermaid_state_svg")

        service = TransformsService()
        service.discover(None, project_dir)

        with patch.object(current_context, "get_transform_runner_blocking", return_value=service.run_blocking):
            flowchart_widget = markdown_widget._build_mermaid_widget(FLOWCHART_SOURCE)
            state_widget = markdown_widget._build_mermaid_widget(STATE_SOURCE)

        check(
            "real end-to-end: a flowchart block renders as a real, valid SVG via the real service",
            isinstance(flowchart_widget, SvgView) and flowchart_widget.is_valid(),
        )
        check(
            "real end-to-end: a state-diagram block renders as a real, valid SVG via the real service",
            isinstance(state_widget, SvgView) and state_widget.is_valid(),
        )


test_flowchart_calls_the_right_transform()
test_state_calls_the_right_transform()
test_unsupported_diagram_skips_the_transform_entirely()
test_successful_render_returns_a_valid_svg_view()
test_transform_failure_falls_back_to_plain_text()
test_invalid_svg_output_falls_back_to_plain_text()
test_no_runner_registered_falls_back_gracefully()
test_real_end_to_end_via_a_real_transforms_service()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
