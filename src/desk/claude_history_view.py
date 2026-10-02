"""Structured history view for the Claude (Desk) widget (TODO dffb428).

Replaces the single `QPlainTextEdit` the widget used to append every
kind of content into with a scroll area of individually framed entries,
each carrying real metadata (kind, turn id, timestamp, source) and
collapsible by default when long. See
plans/claude-desk-structured-history.md and design-docs/architecture.md
item 30's "Observability principle".

Lives in `desk.` proper (not widgets/claude_desk/) because the widget
module is loaded by file path and can't import siblings -- same reason
`desk.claude_session` lives here.

Qt-only, no new dependencies. History text is *content*, not a UI
label, so entry bodies stay selectable (CLAUDE.md); the tag/meta/toggle
chrome is not.
"""
import time
from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QGuiApplication
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

# kind -> (tag shown in the entry header, plain-text prefix used by
# toPlainText()/copy -- the same bracket convention the old text
# stream used, so copied history reads the same as before).
KINDS: dict[str, tuple[str, str]] = {
    "user": ("you", "> "),
    "queued": ("queued", "[queued] "),
    "assistant": ("claude", ""),
    "tool": ("tool", "[tool] "),
    "tool_result": ("result", "[tool result] "),
    "tool_error": ("tool error", "[tool error] "),
    "permission": ("permission", "[permission] "),
    "question": ("question", "[question] "),
    "error": ("error", "[error] "),
    "notice": ("", ""),
}
TOOL_KINDS = ("tool", "tool_result", "tool_error")

# Tool payloads: collapsed once they don't fit one line this wide (the
# original TODO ed5c62f rule, kept as-is).
TOOL_PREVIEW_MAX_CHARS = 80
# Everything else: collapsed once longer than this many lines/chars,
# showing the first PREVIEW_LINES lines (capped) until expanded.
TEXT_COLLAPSE_LINES = 4
TEXT_COLLAPSE_CHARS = 400
PREVIEW_LINES = 3
PREVIEW_MAX_CHARS = 240

_KIND_STYLE = {
    "user": "border-left: 3px solid #3daee9;",
    "queued": "border-left: 3px dashed #3daee9;",
    "tool": "background: rgba(128,128,128,0.12);",
    "tool_result": "background: rgba(128,128,128,0.12);",
    "tool_error": "background: rgba(220,50,50,0.15);",
    "error": "background: rgba(220,50,50,0.15); border-left: 3px solid #da3232;",
    "permission": "background: rgba(128,128,128,0.06);",
    "question": "background: rgba(128,128,128,0.06);",
}
_TURN_RULE = "border-top: 2px solid rgba(128,128,128,0.55);"
_ENTRY_RULE = "border-top: 1px solid rgba(128,128,128,0.2);"


def collapse_preview(kind: str, text: str) -> str | None:
    """A shorter stand-in for `text` shown while collapsed, or None if
    `text` is short enough to always show in full (no fold affordance)."""
    if kind in TOOL_KINDS:
        first_line, _, rest = text.partition("\n")
        if not rest and len(first_line) <= TOOL_PREVIEW_MAX_CHARS:
            return None
        return first_line[:TOOL_PREVIEW_MAX_CHARS].rstrip() + "…"
    lines = text.split("\n")
    if len(lines) <= TEXT_COLLAPSE_LINES and len(text) <= TEXT_COLLAPSE_CHARS:
        return None
    preview = "\n".join(lines[:PREVIEW_LINES])
    if len(preview) > PREVIEW_MAX_CHARS:
        preview = preview[:PREVIEW_MAX_CHARS].rstrip()
    return preview + "…"


@dataclass
class EntryMeta:
    """What an entry knows about itself beyond its text."""

    kind: str
    ts: float
    turn_id: int | None = None
    source: str = ""  # "" normally; "unsolicited" for CLI-initiated output


class HistoryEntry(QFrame):
    def __init__(
        self,
        kind: str,
        text: str,
        *,
        ts: float | None = None,
        turn_id: int | None = None,
        source: str = "",
        turn_start: bool = False,
        reload_text: str | None = None,
        on_reload=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if kind not in KINDS:
            raise ValueError(f"unknown history entry kind: {kind!r}")
        self.meta = EntryMeta(kind=kind, ts=time.time() if ts is None else ts, turn_id=turn_id, source=source)
        self.text = text
        self.turn_start = turn_start
        self.reload_text = reload_text
        self._on_reload = on_reload
        self._preview = collapse_preview(kind, text)
        self.expanded = False

        self.setObjectName("historyEntry")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.setStyleSheet(
            "QFrame#historyEntry { "
            + (_TURN_RULE if turn_start else _ENTRY_RULE)
            + _KIND_STYLE.get(kind, "")
            + " }"
        )

        self._toggle = QPushButton()
        self._toggle.setFlat(True)
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.setStyleSheet(
            "QPushButton { text-align: left; border: none; font-weight: 600; } "
            "QPushButton:disabled { color: palette(text); }"
        )
        self._toggle.clicked.connect(self.toggle)
        # Labels for UI chrome are not selectable (CLAUDE.md); only the
        # entry body below is.
        self._meta_label = QLabel()
        self._meta_label.setStyleSheet("color: gray; font-size: 10px;")
        self._reload_button = QPushButton("↺ Reload")
        self._reload_button.setFlat(True)
        self._reload_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reload_button.clicked.connect(self._reload_clicked)
        self._reload_button.setVisible(False)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(self._toggle)
        header.addWidget(self._meta_label)
        header.addStretch(1)
        header.addWidget(self._reload_button)

        self._body = QLabel()
        self._body.setTextFormat(Qt.TextFormat.PlainText)
        self._body.setWordWrap(True)
        self._body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        if kind == "user":
            self._body.setStyleSheet("color: #3daee9; font-weight: 600;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(1)
        layout.addLayout(header)
        layout.addWidget(self._body)

        self._refresh()

    # -- presentation ---------------------------------------------------

    @property
    def collapsible(self) -> bool:
        return self._preview is not None

    @property
    def shown_text(self) -> str:
        """What the body currently displays (preview while collapsed)."""
        if self._preview is not None and not self.expanded:
            return self._preview
        return self.text

    def plain_text(self) -> str:
        """Full text with the legacy bracket prefix, expanded or not."""
        return KINDS[self.meta.kind][1] + self.text

    def toggle(self) -> None:
        if self.collapsible:
            self.expanded = not self.expanded
            self._refresh()

    def set_turn(self, turn_id: int | None) -> None:
        self.meta.turn_id = turn_id
        self._refresh()

    def _refresh(self) -> None:
        tag = KINDS[self.meta.kind][0]
        arrow = ("▾ " if self.expanded else "▸ ") if self.collapsible else ""
        self._toggle.setText(arrow + tag)
        self._toggle.setEnabled(self.collapsible)
        self._toggle.setVisible(bool(arrow or tag))
        stamp = time.strftime("%H:%M:%S", time.localtime(self.meta.ts))
        parts = [stamp]
        if self.meta.turn_id is not None:
            parts.insert(0, f"turn {self.meta.turn_id}")
        if self.meta.source:
            parts.append(self.meta.source)
        self._meta_label.setText(" · ".join(parts))
        self._body.setText(self.shown_text)
        self.setToolTip(" | ".join(parts))

    # -- reload (user entries) ------------------------------------------

    def enterEvent(self, event) -> None:
        if self.reload_text is not None and self._on_reload is not None:
            self._reload_button.setVisible(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._reload_button.setVisible(False)
        super().leaveEvent(event)

    def _reload_clicked(self) -> None:
        if self._on_reload is not None and self.reload_text is not None:
            self._on_reload(self.reload_text)


class HistoryView(QScrollArea):
    """A vertical stack of `HistoryEntry` frames that follows the bottom
    while the user hasn't scrolled away from it."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._layout.addStretch(1)
        self.setWidget(self._container)
        self._entries: list[HistoryEntry] = []
        self._follow_bottom = True
        self.on_reload = None  # set by the owner: callable(reload_text)

        bar = self.verticalScrollBar()
        bar.valueChanged.connect(lambda value: setattr(self, "_follow_bottom", value >= bar.maximum() - 4))
        bar.rangeChanged.connect(self._maybe_follow)

        # Selection can't span separate entry labels, so offer the whole
        # history as copyable text instead.
        copy_all = QAction("Copy all history", self)
        copy_all.triggered.connect(self._copy_all)
        self.addAction(copy_all)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)

    def add_entry(self, kind: str, text: str, **kwargs) -> HistoryEntry:
        entry = HistoryEntry(kind, text, on_reload=self._dispatch_reload, **kwargs)
        self._layout.insertWidget(self._layout.count() - 1, entry)
        self._entries.append(entry)
        return entry

    def entries(self) -> list[HistoryEntry]:
        return list(self._entries)

    def toPlainText(self) -> str:
        return "\n".join(entry.plain_text() for entry in self._entries)

    def _dispatch_reload(self, reload_text: str) -> None:
        if self.on_reload is not None:
            self.on_reload(reload_text)

    def _maybe_follow(self, _min: int, maximum: int) -> None:
        if self._follow_bottom:
            self.verticalScrollBar().setValue(maximum)

    def _copy_all(self) -> None:
        QGuiApplication.clipboard().setText(self.toPlainText())
