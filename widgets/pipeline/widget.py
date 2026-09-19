"""The Pipeline widget (TODO `9d52dc4`): visualizes and controls the
execution of a pipe-chained verb DSL pipeline (`desk.pipeline_dsl`,
TODO `63bfd42`) as a Mermaid flowchart (`desk.mermaid`, TODO
`a76e723`, rendered via the same `mermaid_flowchart_svg` transform the
Markdown widget already uses for a ```mermaid fence).

Fed by an explicit "Input" drop target (`_DropTarget` below) instead
of always starting from `None` the way `desk_run_pipeline` does --
relies entirely on `desk.shell.canvas.WorkspaceView`'s drop-target
delegation (any descendant with `acceptDrops()` true gets first
refusal on a local-file drop before the canvas's own "open a new
widget" handling runs); nothing image-viewer- or window.py-specific is
duplicated here.

`map +| ... |+`'s own sub-pipeline (TODO `e4d73dc`) is drawn as its
own small node chain with a labeled edge branching out of the `map`
stage's node into it and a second labeled edge back, *not* nested
inside a real box -- `desk.mermaid`'s flowchart support has no
`subgraph`/`style`/`classdef` rendering (see `diagrams.md`'s "Known
limitations"), so there is no way to actually draw that box.
"""

import json
import logging
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desk import pipeline_dsl
from desk.shell import current_context
from desk.svg_view import SvgView

logger = logging.getLogger(__name__)

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}
_DEFAULT_PIPELINE = "split_channels | map +| open_image |+"
_DIAGRAM_MIN_HEIGHT = 100
_DIAGRAM_MAX_HEIGHT = 320
_DEBOUNCE_MS = 300
_ERROR_LABEL_MAX_CHARS = 60


class _DropTarget(QFrame):
    """The pipeline's explicit input: an always-visible box labeled
    "Input" that accepts a dragged-and-dropped image file, becoming
    the pipeline's own initial piped value on Run. The dropped file is
    referenced by path, never copied -- nothing here needs it to
    outlive one synchronous Run."""

    file_dropped = pyqtSignal(Path)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._path: Path | None = None

        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setWordWrap(True)
        # CLAUDE.md: UI element labels are not user-selectable by default.
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        layout = QVBoxLayout(self)
        layout.addWidget(self._label)
        self.setMinimumHeight(56)
        self.setMinimumWidth(160)

        self._set_active(False)
        self._refresh_label()

    def _refresh_label(self) -> None:
        self._label.setText(f"Input\n{self._path.name}" if self._path is not None else "Input\n(drop an image here)")

    def _set_active(self, active: bool) -> None:
        self.setStyleSheet(
            "QFrame { border: 2px dashed palette(highlight); background: palette(alternate-base); }"
            if active
            else "QFrame { border: 2px dashed palette(mid); }"
        )

    def path(self) -> Path | None:
        return self._path

    def set_path(self, path: Path | None) -> None:
        self._path = path
        self._refresh_label()

    @staticmethod
    def _local_image_url(mime_data):
        for url in mime_data.urls():
            if url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in _IMAGE_SUFFIXES:
                return url
        return None

    def dragEnterEvent(self, event) -> None:
        if self._local_image_url(event.mimeData()) is not None:
            event.acceptProposedAction()
            self._set_active(True)
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if self._local_image_url(event.mimeData()) is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self._set_active(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:
        self._set_active(False)
        url = self._local_image_url(event.mimeData())
        if url is None:
            event.ignore()
            return
        event.acceptProposedAction()
        path = Path(url.toLocalFile())
        self.set_path(path)
        self.file_dropped.emit(path)


def _sanitize_label(text: str) -> str:
    """`[`/`]` are the one pair of characters that would break out of
    a rect node's own `[...]` syntax (`desk.mermaid`'s `_NODE_RE`) --
    no other shape is ever used for a stage node here, so no other
    bracket pair needs escaping."""
    return text.replace("[", "(").replace("]", ")")


def _truncate(text: str, max_chars: int = _ERROR_LABEL_MAX_CHARS) -> str:
    return text if len(text) <= max_chars else text[: max_chars - 1] + "…"


def _stage_text(path: str, stage: "pipeline_dsl.StageInfo") -> str:
    if stage.kind == "verb":
        args = " ".join(stage.args) if stage.args else ""
        return f"{path}. {stage.verb} {args}".rstrip()
    if stage.kind == "py":
        return f"{path}. py:"
    return f"{path}. map"


def _emit_chain(
    lines: list[str],
    stages: list["pipeline_dsl.StageInfo"],
    id_prefix: str,
    path_prefix: str,
    entry_id: str,
    entry_edge_label: str | None,
    statuses: list[dict] | None,
) -> str:
    """Emits one node + one connecting edge per stage in `stages`,
    chained onto `entry_id` (already emitted by the caller). A `map`
    stage recurses into its own `sub_stages` as a second small chain,
    branching out of and back into the `map` stage's own node (see the
    module docstring) -- supports a `map` nested inside a `map` since
    the DSL itself allows that. Returns the last node's id, so the
    caller can keep chaining after this call returns."""
    prev_id = entry_id
    for i, stage in enumerate(stages, start=1):
        node_id = f"{id_prefix}{i}"
        stage_path = f"{path_prefix}{i}"
        label = _stage_text(stage_path, stage)
        status = statuses[i - 1] if statuses and i - 1 < len(statuses) else None
        if status is not None:
            if status.get("ok"):
                label += " -- OK"
            else:
                label += f" -- FAILED: {_truncate(str(status.get('error')))}"
        label = _sanitize_label(label)
        lines.append(f"{node_id}[{label}]")

        edge_label = entry_edge_label if prev_id == entry_id else None
        if edge_label:
            lines.append(f"{prev_id} -->|{edge_label}| {node_id}")
        else:
            lines.append(f"{prev_id} --> {node_id}")

        if stage.kind == "map" and stage.sub_stages:
            last_sub = _emit_chain(
                lines, stage.sub_stages, f"{node_id}_", f"{stage_path}.", node_id, "each item", None
            )
            lines.append(f"{last_sub} -->|collected| {node_id}")

        prev_id = node_id
    return prev_id


def _to_mermaid_flowchart(stages: list["pipeline_dsl.StageInfo"], statuses: list[dict] | None = None) -> str:
    lines = ["flowchart LR", "input((Input))"]
    last = _emit_chain(lines, stages, "s", "", "input", None, statuses)
    lines.append(f"{last} --> output((Output))")
    return "\n".join(lines)


class PipelineWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        pipeline_label = QLabel("Pipeline:")
        pipeline_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        self._pipeline_edit = QPlainTextEdit(_DEFAULT_PIPELINE)
        self._pipeline_edit.setMaximumHeight(70)
        self._pipeline_edit.textChanged.connect(self._on_pipeline_text_changed)

        self._drop_target = _DropTarget()
        self._drop_target.file_dropped.connect(self._on_input_dropped)

        self._run_button = QPushButton("Run")
        self._run_button.clicked.connect(self._on_run_clicked)

        top_row = QHBoxLayout()
        top_row.addWidget(self._drop_target, stretch=1)
        top_row.addWidget(self._run_button, stretch=0, alignment=Qt.AlignmentFlag.AlignTop)

        self._diagram = SvgView()
        self._diagram.setMinimumHeight(_DIAGRAM_MIN_HEIGHT)

        self._status_label = QLabel()
        self._status_label.setWordWrap(True)
        self._status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self._output = QPlainTextEdit()
        self._output.setReadOnly(True)
        self._output.setMaximumHeight(120)
        self._output.setPlaceholderText("(Run to see the full result here)")

        layout = QVBoxLayout(self)
        layout.addWidget(pipeline_label)
        layout.addWidget(self._pipeline_edit)
        layout.addLayout(top_row)
        layout.addWidget(self._diagram, stretch=1)
        layout.addWidget(self._status_label)
        layout.addWidget(self._output)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(_DEBOUNCE_MS)
        self._debounce.timeout.connect(self._refresh_diagram)

        self._last_stage_statuses: list[dict] | None = None
        self._refresh_diagram()

    def _on_pipeline_text_changed(self) -> None:
        self._last_stage_statuses = None
        self._debounce.start()

    def _on_input_dropped(self, path: Path) -> None:
        self._status_label.setText(f"Input set: {path}")

    def _pipeline_text(self) -> str:
        return self._pipeline_edit.toPlainText().strip()

    def _show_diagram_message(self, text: str) -> None:
        self._diagram.clear()
        self._status_label.setText(text)

    def _refresh_diagram(self) -> None:
        text = self._pipeline_text()
        if not text:
            self._show_diagram_message("(empty pipeline)")
            return
        try:
            stages = pipeline_dsl.parse_pipeline(text)
        except ValueError as e:
            self._show_diagram_message(f"(pipeline doesn't parse yet: {e})")
            return
        self._render_mermaid(_to_mermaid_flowchart(stages, self._last_stage_statuses))

    def _render_mermaid(self, mermaid_source: str) -> None:
        runner = current_context.get_transform_runner_blocking()
        if runner is None:
            self._show_diagram_message("(no transform runner available yet)")
            return
        try:
            svg = runner("mermaid_flowchart_svg", mermaid_source, None)
        except Exception:
            logger.error("Failed to render pipeline diagram", exc_info=True)
            self._show_diagram_message("(failed to render diagram)")
            return
        if self._diagram.load(svg.encode("utf-8")) and self._diagram.is_valid():
            natural = self._diagram.content_size()
            if natural.width() > 0:
                height = min(_DIAGRAM_MAX_HEIGHT, max(_DIAGRAM_MIN_HEIGHT, natural.height()))
                self._diagram.setMinimumHeight(int(height))
        else:
            self._show_diagram_message("(failed to render diagram)")

    def _on_run_clicked(self) -> None:
        input_path = self._drop_target.path()
        if input_path is None:
            self._status_label.setText('Drop an input image onto "Input" first.')
            return
        text = self._pipeline_text()
        try:
            result = pipeline_dsl.run_pipeline(text, initial_value={"path": str(input_path)})
        except ValueError as e:
            self._status_label.setText(f"Pipeline error: {e}")
            return
        self._last_stage_statuses = result["stages"]
        if result["ok"]:
            self._status_label.setText("Succeeded.")
        else:
            self._status_label.setText(f"Failed: {result['stages'][-1]['error']}")
        self._output.setPlainText(json.dumps(result, indent=2, default=str))
        self._refresh_diagram()


def build() -> QWidget:
    return PipelineWidget()
