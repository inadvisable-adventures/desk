"""Verifies the Pipeline widget's own pure-logic pieces (TODO
`9d52dc4`, see `plans/pipeline-widget.md`): Mermaid diagram generation
(`_to_mermaid_flowchart`), the "Input" drop target (`_DropTarget`), and
`build()`. `split_channels`/`parse_pipeline`/`run_pipeline`'s
`initial_value` param are covered by
`verify_pipeline_dsl_split_channels.py`; the canvas-level drop
-delegation mechanism this widget relies on by
`verify_canvas_drop_delegation.py`."""

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from PyQt6.QtCore import QMimeData, QUrl  # noqa: E402
from PyQt6.QtGui import QDropEvent, QDragEnterEvent  # noqa: E402
from PyQt6.QtCore import QPointF  # noqa: E402
from PyQt6.QtCore import Qt as QtCore_Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk import mermaid  # noqa: E402
from desk import pipeline_dsl  # noqa: E402
from desk.shell import current_context  # noqa: E402

_spec = importlib.util.spec_from_file_location("pipeline_widget_test", REPO_ROOT / "widgets/pipeline/widget.py")
pipeline_widget = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pipeline_widget)

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


# QDropEvent/QDragEnterEvent don't keep their own QMimeData argument
# alive (confirmed directly: a QMimeData built and only referenced
# locally inside a helper segfaults on the very next mimeData() access
# once Python garbage-collects it) -- every QMimeData built here is
# kept alive in this module-level list for the rest of the process.
_kept_mime_data = []


def _mime_for(path_or_url) -> QMimeData:
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path_or_url))])
    _kept_mime_data.append(mime)
    return mime


def _drop_event_for(path_or_url, local_pos=None) -> QDropEvent:
    return QDropEvent(
        local_pos or QPointF(0, 0),
        QtCore_Qt.DropAction.CopyAction,
        _mime_for(path_or_url),
        QtCore_Qt.MouseButton.LeftButton,
        QtCore_Qt.KeyboardModifier.NoModifier,
    )


def _drag_enter_event_for(path_or_url) -> QDragEnterEvent:
    return QDragEnterEvent(
        QPointF(0, 0).toPoint(),
        QtCore_Qt.DropAction.CopyAction,
        _mime_for(path_or_url),
        QtCore_Qt.MouseButton.LeftButton,
        QtCore_Qt.KeyboardModifier.NoModifier,
    )


# -- _to_mermaid_flowchart: real desk.mermaid.parse() round-trip ---------


def test_plain_pipeline_produces_a_parseable_linear_chain():
    stages = pipeline_dsl.parse_pipeline("reveal_widget abc | screenshot_desk out.png", pipeline_dsl.VERB_REGISTRY)
    source = pipeline_widget._to_mermaid_flowchart(stages)
    diagram = mermaid.parse(source)
    check("parses as a flowchart", diagram.kind == "flowchart")
    check("4 nodes: input, s1, s2, output", len(diagram.nodes) == 4)
    check("3 edges chaining them in order", len(diagram.edges) == 3)
    node_labels = {n.id: n.label for n in diagram.nodes}
    check("s1 label names the verb and its arg", node_labels["s1"] == "1. reveal_widget abc")
    check("s2 label names the second verb", node_labels["s2"] == "2. screenshot_desk out.png")


def test_py_stage_gets_a_fixed_label():
    stages = pipeline_dsl.parse_pipeline("py:MQ==", {})
    source = pipeline_widget._to_mermaid_flowchart(stages)
    diagram = mermaid.parse(source)
    node_labels = {n.id: n.label for n in diagram.nodes}
    check("py stage shows a fixed 'N. py:' label, not decoded source", node_labels["s1"] == "1. py:")


def test_map_stage_branches_out_and_back():
    registry = {"open_image": lambda piped: {"ok": True}}
    stages = pipeline_dsl.parse_pipeline("map +| open_image |+", registry)
    source = pipeline_widget._to_mermaid_flowchart(stages)
    diagram = mermaid.parse(source)
    node_ids = {n.id for n in diagram.nodes}
    check("map's own node exists", "s1" in node_ids)
    check("the sub-pipeline's own node exists", "s1_1" in node_ids)
    edges = {(e.source, e.target, e.label) for e in diagram.edges}
    check("a labeled edge branches from the map node into the sub-chain", ("s1", "s1_1", "each item") in edges)
    check("a labeled edge branches back from the sub-chain into the map node", ("s1_1", "s1", "collected") in edges)
    check("the map node also continues on to Output", ("s1", "output", None) in edges)


def test_nested_map_recurses():
    registry = {"open_image": lambda piped: {"ok": True}}
    stages = pipeline_dsl.parse_pipeline("map +| map +| open_image |+ |+", registry)
    source = pipeline_widget._to_mermaid_flowchart(stages)
    diagram = mermaid.parse(source)
    node_ids = {n.id for n in diagram.nodes}
    check("outer map node exists", "s1" in node_ids)
    check("inner map node exists", "s1_1" in node_ids)
    check("innermost verb node exists", "s1_1_1" in node_ids)


def test_label_bracket_sanitization():
    registry = {"echo": lambda _, s: s}
    stages = pipeline_dsl.parse_pipeline("echo [bracketed]", registry)
    source = pipeline_widget._to_mermaid_flowchart(stages)
    # A raw, unsanitized '[' or ']' inside the arg would break _NODE_RE's
    # own rect-shape match (it stops at the first ']') -- confirm the real
    # parser still accepts this line and produces exactly one node for it.
    diagram = mermaid.parse(source)
    node_labels = {n.id: n.label for n in diagram.nodes}
    check("brackets in an arg are sanitized, not left to break the node syntax", "[" not in node_labels["s1"] and "]" not in node_labels["s1"])
    check("the sanitized text is still recognizable", "bracketed" in node_labels["s1"])


def test_status_annotation_only_on_attempted_stages():
    registry = {"a": lambda _: None, "b": lambda _: None, "c": lambda _: None}
    stages = pipeline_dsl.parse_pipeline("a | b | c", registry)
    # A fail-fast partial run: only 2 of 3 top-level stages were attempted.
    statuses = [{"ok": True}, {"ok": False, "error": "boom"}]
    source = pipeline_widget._to_mermaid_flowchart(stages, statuses)
    diagram = mermaid.parse(source)
    node_labels = {n.id: n.label for n in diagram.nodes}
    check("stage 1 annotated OK", node_labels["s1"].endswith("-- OK"))
    check("stage 2 annotated FAILED with the reason", "FAILED: boom" in node_labels["s2"])
    check("stage 3 (never attempted) has no status annotation", node_labels["s3"] == "3. c")


# -- _DropTarget -----------------------------------------------------------


def test_drop_target_ignores_a_non_image_file():
    target = pipeline_widget._DropTarget()
    received = []
    target.file_dropped.connect(received.append)
    event = _drop_event_for("/tmp/notes.txt")
    target.dropEvent(event)
    check("non-image drop leaves path unset", target.path() is None)
    check("no file_dropped signal for a non-image drop", received == [])


def test_drop_target_accepts_an_image_file():
    target = pipeline_widget._DropTarget()
    received = []
    target.file_dropped.connect(received.append)
    event = _drop_event_for("/tmp/photo.png")
    target.dropEvent(event)
    check("image drop sets the path", target.path() == Path("/tmp/photo.png"))
    check("file_dropped signal emitted with the same path", received == [Path("/tmp/photo.png")])


def test_drop_target_drag_enter_accepts_only_images():
    target = pipeline_widget._DropTarget()
    image_event = _drag_enter_event_for("/tmp/photo.jpg")
    target.dragEnterEvent(image_event)
    check("dragEnterEvent accepts a known image suffix", image_event.isAccepted())

    text_event = _drag_enter_event_for("/tmp/notes.txt")
    target.dragEnterEvent(text_event)
    check("dragEnterEvent ignores a non-image suffix", not text_event.isAccepted())


# -- build() -----------------------------------------------------------------


def test_build_returns_a_real_widget_with_the_default_pipeline():
    with patch.object(current_context, "get_transform_runner_blocking", return_value=None):
        widget = pipeline_widget.build()
    check("build() returns a PipelineWidget", isinstance(widget, pipeline_widget.PipelineWidget))
    check("pre-filled with the default example pipeline", widget._pipeline_edit.toPlainText() == pipeline_widget._DEFAULT_PIPELINE)
    check("drop target starts empty", widget._drop_target.path() is None)


def test_run_without_input_shows_a_message_and_does_not_crash():
    with patch.object(current_context, "get_transform_runner_blocking", return_value=None):
        widget = pipeline_widget.build()
        widget._on_run_clicked()
    check("status label prompts for an input drop", "Input" in widget._status_label.text())
    check("no result was recorded", widget._output.toPlainText() == "")


test_plain_pipeline_produces_a_parseable_linear_chain()
test_py_stage_gets_a_fixed_label()
test_map_stage_branches_out_and_back()
test_nested_map_recurses()
test_label_bracket_sanitization()
test_status_annotation_only_on_attempted_stages()
test_drop_target_ignores_a_non_image_file()
test_drop_target_accepts_an_image_file()
test_drop_target_drag_enter_accepts_only_images()
test_build_returns_a_real_widget_with_the_default_pipeline()
test_run_without_input_shows_a_message_and_does_not_crash()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
