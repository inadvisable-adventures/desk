"""Live data-flow view for the Claude (Desk) widget (TODO eb50b84).

An abstracted pipeline diagram animated from ClaudeSession's
`session_event` stream (TODO 20ca851) -- see
plans/claude-desk-data-flow-view.md and design-docs/architecture.md item
30's "Observability principle". Plain QPainter; no new dependency.

`advance(dt)` is the entire simulation, so tests drive it directly; the
QTimer only calls it while the view is visible and something is animating.
"""
from dataclasses import dataclass

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QWidget

# name -> (column, lane) on a 4-column, 2-lane grid; label shown in the node.
NODES: dict[str, tuple[int, int, str]] = {
    "prompt": (0, 0, "Prompt"),
    "queue": (1, 0, "Queue"),
    "session": (2, 0, "Session"),
    "cli": (3, 0, "SDK / CLI"),
    "stream": (3, 1, "Stream"),
    "reader": (2, 1, "Reader"),
    "history": (1, 1, "History"),
}
OUTBOUND_PATH = ["prompt", "queue", "session", "cli"]
INBOUND_PATH = ["cli", "stream", "reader", "history"]
EDGES = list(zip(OUTBOUND_PATH, OUTBOUND_PATH[1:])) + list(zip(INBOUND_PATH, INBOUND_PATH[1:]))

SOLICITED_COLOR = QColor("#3daee9")
UNSOLICITED_COLOR = QColor("#e8a33d")
COMPLETE_COLOR = QColor("#3dae5c")
ERROR_COLOR = QColor("#da3232")

# Path fractions per second: a marker crosses a whole path in ~1.2s.
MARKER_SPEED = 1 / 1.2
FLASH_SECONDS = 1.0
TICK_MS = 33
TERMINAL_STATUSES = ("completed", "failed", "killed", "stopped", "cancelled")


@dataclass
class Marker:
    path: list[str]
    color: QColor
    label: str
    progress: float = 0.0


@dataclass
class _NodeState:
    flash: float = 0.0  # seconds of error flash remaining
    seen: int = 0


class FlowView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(120)
        self._markers: list[Marker] = []
        self._nodes = {name: _NodeState() for name in NODES}
        self.queue_depth = 0
        self.inflight_turn: int | None = None
        # TODO c1eb687: last RateLimitEvent status ("allowed" until told otherwise).
        self.rate_limit_status = "allowed"
        # TODO 5ce8447: seconds of silence while something is outstanding
        # once stale (None when fine); amber state on the Session node.
        self.stale_seconds: int | None = None
        self._tasks: dict[str, str] = {}
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(lambda: self.advance(TICK_MS / 1000))

    # -- model ------------------------------------------------------------

    @property
    def active_tasks(self) -> int:
        return sum(1 for status in self._tasks.values() if status not in TERMINAL_STATUSES)

    def markers(self) -> list[Marker]:
        return list(self._markers)

    def seen(self, node: str) -> int:
        return self._nodes[node].seen

    def flashing(self, node: str) -> bool:
        return self._nodes[node].flash > 0

    def set_stale(self, silent_seconds: float | None) -> None:
        self.stale_seconds = None if silent_seconds is None else int(silent_seconds)
        self.update()

    def set_queue_depth(self, depth: int) -> None:
        self.queue_depth = depth
        self.update()

    def feed(self, event: dict) -> None:
        """Consumes one ClaudeSession.session_event dict."""
        kind = event["kind"]
        turn_id = event.get("turn_id")
        solicited = event.get("solicited", True)
        color = SOLICITED_COLOR if solicited else UNSOLICITED_COLOR
        label = "" if turn_id is None else f"t{turn_id}"
        if kind == "rate_limit":
            # Connection-level state, not a message in flight: annotate
            # the CLI node instead of spawning a marker.
            self.rate_limit_status = event.get("data", {}).get("status", "allowed")
            self.update()
            return
        if kind == "turn_started":
            self.inflight_turn = turn_id
            self._spawn(OUTBOUND_PATH, color, label)
        elif kind == "protocol_violation" or kind == "session_error":
            self._nodes["reader"].flash = FLASH_SECONDS
            if kind == "session_error" and solicited:
                self.inflight_turn = None
        else:
            if kind == "turn_complete":
                color = COMPLETE_COLOR
                if solicited:
                    self.inflight_turn = None
            elif kind == "task_event":
                data = event.get("data", {})
                status = data.get("patch", {}).get("status")
                if status is not None:
                    self._tasks[data.get("task_id", "")] = status
                elif data.get("task_id", "") not in self._tasks:
                    self._tasks[data.get("task_id", "")] = "running"
            self._spawn(INBOUND_PATH, color, label or kind)
        self._start_timer_if_needed()
        self.update()

    def _spawn(self, path: list[str], color: QColor, label: str) -> None:
        self._markers.append(Marker(path=path, color=color, label=label))

    def advance(self, dt: float) -> None:
        """Moves every marker, retires the finished ones (counting each
        arrival at its path's later nodes), decays error flashes."""
        step = dt * MARKER_SPEED
        still_moving = []
        for marker in self._markers:
            before = marker.progress
            marker.progress = min(1.0, marker.progress + step)
            last = len(marker.path) - 1
            # A node counts a marker once, the moment it is first reached.
            for index in range(1, len(marker.path)):
                if before < index / last <= marker.progress:
                    self._nodes[marker.path[index]].seen += 1
            if marker.progress < 1.0:
                still_moving.append(marker)
        self._markers = still_moving
        for state in self._nodes.values():
            state.flash = max(0.0, state.flash - dt)
        if not self._markers and not any(state.flash for state in self._nodes.values()):
            self._timer.stop()
        self.update()

    def _start_timer_if_needed(self) -> None:
        if self.isVisible() and not self._timer.isActive():
            self._timer.start()

    # -- visibility drives the animation timer -------------------------------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._markers or any(state.flash for state in self._nodes.values()):
            self._timer.start()

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    # -- painting ----------------------------------------------------------

    def _node_rect(self, name: str) -> QRectF:
        column, lane, _label = NODES[name]
        width, height = self.width(), self.height()
        node_w = max(40.0, width / 4 - 14)
        node_h = max(28.0, height / 2 - 24)
        cx = width / 8 + column * width / 4
        cy = height * (0.28 if lane == 0 else 0.76)
        return QRectF(cx - node_w / 2, cy - node_h / 2, node_w, node_h)

    def _annotation(self, name: str) -> str:
        if name == "queue":
            return f"{self.queue_depth} queued"
        if name == "session":
            if self.stale_seconds is not None:
                return f"stale {self.stale_seconds}s"
            return "idle" if self.inflight_turn is None else f"turn {self.inflight_turn}"
        if name == "cli":
            note = {"allowed_warning": " · throttled", "rejected": " · RATE LIMITED"}.get(self.rate_limit_status, "")
            return f"{self.active_tasks} bg tasks{note}"
        return f"{self._nodes[name].seen} seen" if name in ("reader", "stream", "history") else ""

    def _point_on_path(self, marker: Marker) -> QPointF:
        segments = len(marker.path) - 1
        position = marker.progress * segments
        index = min(int(position), segments - 1)
        local = position - index
        a = self._node_rect(marker.path[index]).center()
        b = self._node_rect(marker.path[index + 1]).center()
        return QPointF(a.x() + (b.x() - a.x()) * local, a.y() + (b.y() - a.y()) * local)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        line = QColor(palette.color(palette.ColorRole.Mid))
        painter.setPen(QPen(line, 2))
        for a, b in EDGES:
            painter.drawLine(self._node_rect(a).center(), self._node_rect(b).center())
        for name, (_c, _l, label) in NODES.items():
            rect = self._node_rect(name)
            state = self._nodes[name]
            fill = QColor(palette.color(palette.ColorRole.Base))
            border = QColor(palette.color(palette.ColorRole.Mid))
            if name == "session" and self.stale_seconds is not None:
                border = UNSOLICITED_COLOR
            if name == "cli" and self.rate_limit_status != "allowed":
                border = ERROR_COLOR if self.rate_limit_status == "rejected" else UNSOLICITED_COLOR
            if state.flash > 0:
                fill = QColor(ERROR_COLOR)
                fill.setAlphaF(min(1.0, state.flash / FLASH_SECONDS))
                border = ERROR_COLOR
            painter.setPen(QPen(border, 1.5))
            painter.setBrush(fill)
            painter.drawRoundedRect(rect, 6, 6)
            painter.setPen(palette.color(palette.ColorRole.Text))
            painter.drawText(rect.adjusted(2, 2, -2, -rect.height() / 2), Qt.AlignmentFlag.AlignCenter, label)
            painter.setPen(palette.color(palette.ColorRole.PlaceholderText))
            painter.drawText(rect.adjusted(2, rect.height() / 2 - 2, -2, -2), Qt.AlignmentFlag.AlignCenter, self._annotation(name))
        for marker in self._markers:
            point = self._point_on_path(marker)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(marker.color)
            painter.drawEllipse(point, 6, 6)
            if marker.label:
                painter.setPen(palette.color(palette.ColorRole.Text))
                painter.drawText(QPointF(point.x() + 8, point.y() - 6), marker.label)
        painter.end()
