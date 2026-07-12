import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTextBrowser,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from desk.file_watch import SingleFileWatcher
from desk.mermaid import MermaidDiagramWidget
from desk.shell import current_context

logger = logging.getLogger(__name__)

PLACEHOLDER_TEXT = "No file open — click Open to choose a Markdown file."
MARKDOWN_FILTER = "Markdown (*.md *.markdown *.mdown *.mkd *.mdwn);;All files (*)"

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^```\s*([A-Za-z0-9_+-]*)\s*$")


@dataclass
class _RawBlock:
    """One piece of a split document: a heading line, a raw Markdown
    chunk (fed to QTextBrowser.setMarkdown() verbatim -- covers
    everything Qt's own Markdown support already handles for free:
    bold/italic/links/lists/tables/blockquotes/images/non-Mermaid code
    fences), or an isolated ```mermaid fence's contents."""

    kind: str  # "heading" | "text" | "mermaid"
    level: int = 0
    content: str = ""


def _split_blocks(text: str) -> list[_RawBlock]:
    """Fence-aware split: a fenced code block's lines are never scanned
    for headings, and a ```mermaid fence is pulled out as its own block
    instead of staying in the surrounding text chunk."""
    blocks: list[_RawBlock] = []
    text_buf: list[str] = []
    lines = text.splitlines()
    i = 0

    def flush_text() -> None:
        if text_buf:
            joined = "\n".join(text_buf).strip("\n")
            if joined.strip():
                blocks.append(_RawBlock(kind="text", content=joined))
            text_buf.clear()

    while i < len(lines):
        line = lines[i]

        fence_match = _FENCE_RE.match(line)
        if fence_match:
            language = fence_match.group(1).lower()
            fence_lines = [line]
            body_lines: list[str] = []
            i += 1
            while i < len(lines) and lines[i].strip() != "```":
                fence_lines.append(lines[i])
                body_lines.append(lines[i])
                i += 1
            if i < len(lines):
                fence_lines.append(lines[i])  # closing fence
                i += 1
            if language == "mermaid":
                flush_text()
                blocks.append(_RawBlock(kind="mermaid", content="\n".join(body_lines)))
            else:
                text_buf.extend(fence_lines)
            continue

        heading_match = _HEADING_RE.match(line)
        if heading_match:
            flush_text()
            blocks.append(
                _RawBlock(kind="heading", level=len(heading_match.group(1)), content=heading_match.group(2).strip())
            )
            i += 1
            continue

        text_buf.append(line)
        i += 1

    flush_text()
    return blocks


@dataclass
class _Section:
    level: int
    title: str
    blocks: list[_RawBlock] = field(default_factory=list)
    children: list["_Section"] = field(default_factory=list)


def _build_sections(blocks: list[_RawBlock]) -> tuple[list[_RawBlock], list[_Section]]:
    """Folds a flat block list into a heading-nested outline: returns
    (blocks before the first heading, top-level sections)."""
    preamble: list[_RawBlock] = []
    roots: list[_Section] = []
    stack: list[_Section] = []

    for block in blocks:
        if block.kind == "heading":
            section = _Section(level=block.level, title=block.content)
            while stack and stack[-1].level >= section.level:
                stack.pop()
            (stack[-1].children if stack else roots).append(section)
            stack.append(section)
        elif stack:
            stack[-1].blocks.append(block)
        else:
            preamble.append(block)

    return preamble, roots


class _AutoHeightTextBrowser(QTextBrowser):
    """A QTextBrowser that sizes itself to its content's actual height
    instead of offering its own scrollable viewport -- so it behaves as
    an inline flowed block inside the outer QScrollArea, not a nested
    scroll area of its own."""

    def __init__(self, markdown: str, base_dir: Path, parent=None) -> None:
        super().__init__(parent)
        self.setOpenExternalLinks(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        # Resolves relative image references (raster and, indirectly via
        # the QtSvg image-format plugin, SVG -- see
        # qtextbrowser-images-svg-controls.md) against the source file's
        # own directory.
        self.document().setBaseUrl(QUrl.fromLocalFile(f"{base_dir}/"))
        self.setMarkdown(markdown)
        self.document().documentLayout().documentSizeChanged.connect(self._update_height)
        self._update_height()

    def _update_height(self, *_args) -> None:
        self.setFixedHeight(int(self.document().size().height()) + 4)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.document().setTextWidth(self.viewport().width())
        self._update_height()


def _build_block_widget(block: _RawBlock, base_dir: Path) -> QWidget:
    if block.kind == "mermaid":
        return MermaidDiagramWidget(block.content)
    return _AutoHeightTextBrowser(block.content, base_dir)


class _SectionWidget(QWidget):
    """A foldable section: a disclosure header (heading text, sized/
    weighted by level) plus a body holding this section's own blocks
    and, recursively, its child sections."""

    def __init__(self, section: _Section, base_dir: Path, parent=None) -> None:
        super().__init__(parent)
        self.section = section
        self.child_widgets: list["_SectionWidget"] = []
        self._parent_section_widget: "_SectionWidget | None" = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)

        self.toggle = QToolButton()
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow)
        self.toggle.setCheckable(True)
        self.toggle.setChecked(True)
        self.toggle.setAutoRaise(True)
        self.toggle.setText(section.title or "(untitled section)")
        font = self.toggle.font()
        font.setPointSize(max(9, 16 - section.level * 2))
        font.setBold(section.level <= 2)
        self.toggle.setFont(font)
        self.toggle.clicked.connect(self._on_toggle)
        outer.addWidget(self.toggle)

        self.body = QWidget()
        body_layout = QVBoxLayout(self.body)
        body_layout.setContentsMargins(18, 0, 0, 0)
        body_layout.setSpacing(6)
        for block in section.blocks:
            body_layout.addWidget(_build_block_widget(block, base_dir))
        for child in section.children:
            child_widget = _SectionWidget(child, base_dir)
            child_widget._parent_section_widget = self
            self.child_widgets.append(child_widget)
            body_layout.addWidget(child_widget)
        outer.addWidget(self.body)

    def _on_toggle(self, checked: bool) -> None:
        self.body.setVisible(checked)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)

    def set_expanded(self, expanded: bool) -> None:
        self.toggle.setChecked(expanded)
        self._on_toggle(expanded)


class MarkdownExWidget(QWidget):
    """Markdown viewer with a left-hand TOC treeview, foldable
    sections, and inline Mermaid diagram rendering (see desk.mermaid),
    on top of QTextBrowser's own native image/SVG handling for
    everything else. See plans/markdown-ex-widget.md."""

    external_path_changed = pyqtSignal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._current_path: Path | None = None
        self._last_dir = current_context.get_current_desk_directory() or Path.home()

        self._label = QLabel()
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        open_button = QPushButton("Open")
        open_button.clicked.connect(self._open_file)
        toolbar = QHBoxLayout()
        toolbar.addWidget(open_button)
        toolbar.addStretch()
        toolbar.addWidget(self._label)

        self._toc = QTreeWidget()
        self._toc.setHeaderHidden(True)
        self._toc.itemClicked.connect(self._on_toc_clicked)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(8, 8, 8, 8)
        self._content_layout.setSpacing(10)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setWidget(self._content)

        splitter = QSplitter()
        splitter.addWidget(self._toc)
        splitter.addWidget(self._scroll)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([220, 680])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(toolbar)
        layout.addWidget(splitter, stretch=1)

        self._watcher = SingleFileWatcher(self)
        self._watcher.changed.connect(self._reload)
        # Capture the watcher (not self) so the teardown closure never
        # touches this widget's Qt state during destruction -- mirrors
        # the Markdown/TODO widgets' own teardown pattern.
        watcher = self._watcher
        self.destroyed.connect(lambda: watcher.stop())

        self._show_placeholder()

    def _clear_content(self) -> None:
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._toc.clear()

    def _show_message(self, text: str) -> None:
        self._clear_content()
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._content_layout.addWidget(label)
        self._content_layout.addStretch(1)

    def _show_placeholder(self) -> None:
        self._label.setText("(no file)")
        self._show_message(PLACEHOLDER_TEXT)

    def _open_file(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open Markdown File", str(self._last_dir), MARKDOWN_FILTER
        )
        if filename:
            self.set_file(Path(filename))

    def set_file(self, path: Path) -> None:
        """Point the widget at `path`: render it and watch it for
        changes. Public so other widgets can open a file here
        programmatically, matching the plain Markdown widget."""
        self._current_path = path
        self._last_dir = path.parent
        self._watcher.watch(path)
        self._reload()
        self.refresh_external_path_status()

    def refresh_external_path_status(self) -> None:
        """Re-emits `external_path_changed` for the currently loaded file
        (TODO a053e3a) -- called here after every load, and once more by
        DeskWindow right after wiring the signal, since the file may
        already have been loaded before that connection existed.

        Wrapped defensively (TODO 810a5d6): this is a purely cosmetic
        titlebar feature reached from a Qt-signal-invoked slot chain
        where an uncaught exception is fatal to the whole process in
        this PyQt6 setup -- see plans/isolate-hot-reload-crash.md and
        LEARNINGS.md."""
        try:
            is_external = self._current_path is not None and current_context.path_is_external(
                self._current_path
            )
        except Exception:
            logger.error("Failed to compute external-path status for %s", self._current_path, exc_info=True)
            return
        self.external_path_changed.emit(is_external)

    def _reload(self) -> None:
        path = self._current_path
        if path is None:
            self._show_placeholder()
            return
        self._label.setText(path.name)
        try:
            text = path.read_text()
        except FileNotFoundError:
            self._show_message(f"`{path.name}` no longer exists.")
            return
        except OSError as error:
            self._show_message(f"Could not read `{path.name}`: {error}.")
            return
        self._render(text, path.parent)

    def _render(self, text: str, base_dir: Path) -> None:
        self._clear_content()

        preamble, sections = _build_sections(_split_blocks(text))
        for block in preamble:
            self._content_layout.addWidget(_build_block_widget(block, base_dir))
        for section in sections:
            section_widget = _SectionWidget(section, base_dir)
            self._content_layout.addWidget(section_widget)
            toc_item = QTreeWidgetItem([section.title or "(untitled section)"])
            self._toc.addTopLevelItem(toc_item)
            self._populate_toc(toc_item, section_widget)
        self._content_layout.addStretch(1)
        self._toc.expandAll()

    def _populate_toc(self, toc_item: QTreeWidgetItem, section_widget: _SectionWidget) -> None:
        # Stashed via Qt's own item data slot, not a Python-side id()->
        # widget dict: PyQt can hand back a freshly-allocated wrapper
        # object for the same underlying C++ QTreeWidgetItem on a later
        # access (e.g. from the itemClicked signal), which would silently
        # break an id()-keyed lookup.
        toc_item.setData(0, Qt.ItemDataRole.UserRole, section_widget)
        for child_widget in section_widget.child_widgets:
            child_item = QTreeWidgetItem([child_widget.section.title or "(untitled section)"])
            toc_item.addChild(child_item)
            self._populate_toc(child_item, child_widget)

    def _on_toc_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        section_widget = item.data(0, Qt.ItemDataRole.UserRole)
        if section_widget is None:
            return
        ancestor = section_widget._parent_section_widget
        while ancestor is not None:
            ancestor.set_expanded(True)
            ancestor = ancestor._parent_section_widget
        self._scroll.ensureWidgetVisible(section_widget)


def build() -> QWidget:
    return MarkdownExWidget()
