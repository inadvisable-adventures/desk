"""Event Recorder (TODO 8d4826c) -- a diagnostic widget: "Record for 5s"
temporarily replaces the widget's own content with a blank surface that
records every raw Qt event landing on it, then shows a scrollable,
collapsed summary. Motivated directly by TODO 3846190: the user still
sees a trackpad two-finger-scroll gesture "getting missed" by widgets
even after that fix, and wants to observe empirically which events
actually arrive (this environment is headless and can't reproduce real
trackpad hardware input at all) rather than guessing further -- e.g.
some platforms report two-finger scroll as a NativeGesture
PanNativeGesture rather than (or alongside) a Wheel event, which TODO
3846190's own fix never considered at all (only ZoomNativeGesture/
pinch). See plans/event-recorder-widget.md."""

import time
from datetime import datetime

from PyQt6.QtCore import QEvent, Qt, QTimer
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QStackedLayout,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

RECORD_DURATION_SECONDS = 5

_MOUSE_EVENT_TYPES = (
    QEvent.Type.MouseButtonPress,
    QEvent.Type.MouseButtonRelease,
    QEvent.Type.MouseMove,
    QEvent.Type.MouseButtonDblClick,
)
_TOUCH_EVENT_TYPES = (QEvent.Type.TouchBegin, QEvent.Type.TouchUpdate, QEvent.Type.TouchEnd)


def _describe_event(event) -> str:
    """A short, type-specific one-line detail string -- deliberately
    not exhaustive (just enough to tell adjacent-but-different events
    apart at a glance); anything not specifically handled below just
    shows its type name alone, with no extra detail."""
    etype = event.type()
    if etype == QEvent.Type.Wheel:
        pd = event.pixelDelta()
        ad = event.angleDelta()
        return f"pixelDelta=({pd.x()}, {pd.y()}) angleDelta=({ad.x()}, {ad.y()})"
    if etype in _MOUSE_EVENT_TYPES:
        pos = event.position()
        return f"button={event.button().name} pos=({pos.x():.0f}, {pos.y():.0f})"
    if etype == QEvent.Type.NativeGesture:
        return f"gestureType={event.gestureType().name} value={event.value():.3f}"
    if etype in _TOUCH_EVENT_TYPES:
        points_fn = getattr(event, "points", None)
        count = len(points_fn()) if callable(points_fn) else "?"
        return f"points={count}"
    return ""


class _RecordingSurface(QWidget):
    """A plain, deliberately childless QWidget -- every event landing
    anywhere within its bounds is guaranteed to reach this widget's own
    event() directly, with no child widget able to intercept any of it
    first. Passive: still calls super().event(event) for every event,
    so normal Qt behavior is completely unaffected -- this only
    observes, never filters or swallows anything."""

    def __init__(self, parent=None) -> None:
        # Set before super().__init__() (TODO 8d4826c): QWidget's own
        # constructor can dispatch an internal event (delivered through
        # this same overridden event()) before this subclass's __init__
        # body would otherwise get a chance to run -- confirmed
        # directly (an AttributeError on self._recording, raised from
        # inside super().__init__() itself).
        self._recording = False
        self._events: list[tuple[float, "QEvent.Type", str]] = []
        self._start_time = 0.0
        super().__init__(parent)
        self.setStyleSheet("background-color: #2a2d31;")

    def start(self) -> None:
        self._events = []
        self._start_time = time.monotonic()
        self._recording = True

    def stop(self) -> list[tuple[float, "QEvent.Type", str]]:
        self._recording = False
        return self._events

    def event(self, event) -> bool:
        if self._recording:
            elapsed_ms = (time.monotonic() - self._start_time) * 1000.0
            self._events.append((elapsed_ms, event.type(), _describe_event(event)))
        return super().event(event)


def _collapse_adjacent(events: list[tuple[float, "QEvent.Type", str]]) -> list[dict]:
    """Run-length-encodes a time-ordered raw event list: consecutive
    events sharing the same event.type() merge into one group,
    regardless of how their own individual detail differs -- a
    different type appearing in between starts a new group even if the
    same type recurs later (never merged back into the earlier group)."""
    groups: list[dict] = []
    for elapsed_ms, etype, detail in events:
        if groups and groups[-1]["_type"] == etype:
            group = groups[-1]
            group["count"] += 1
            group["end_ms"] = elapsed_ms
            group["last_detail"] = detail
        else:
            groups.append(
                {
                    "_type": etype,
                    "type_name": etype.name,
                    "count": 1,
                    "start_ms": elapsed_ms,
                    "end_ms": elapsed_ms,
                    "first_detail": detail,
                    "last_detail": detail,
                }
            )
    return groups


def _group_to_display_dict(group: dict) -> dict:
    """Strips the raw (non-JSON-serializable) QEvent.Type enum member
    _collapse_adjacent keeps around internally -- the shape actually
    shown in the results table and persisted via widget-local
    storage."""
    return {
        "type_name": group["type_name"],
        "count": group["count"],
        "start_ms": group["start_ms"],
        "end_ms": group["end_ms"],
        "first_detail": group["first_detail"],
        "last_detail": group["last_detail"],
    }


class EventRecorderWidget(QWidget):
    """See the module docstring and plans/event-recorder-widget.md."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._groups: list[dict] = []
        self._recorded_at: str | None = None
        self._remaining_seconds = 0

        self._record_button = QPushButton("Record for 5s")
        self._record_button.clicked.connect(self._start_recording)

        self._status_label = QLabel(
            "Click “Record for 5s”, then perform the gesture you want to inspect over this widget."
        )
        self._status_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._status_label.setWordWrap(True)

        toolbar = QHBoxLayout()
        toolbar.addWidget(self._record_button)
        toolbar.addWidget(self._status_label, stretch=1)

        self._results_table = QTableWidget(0, 4)
        self._results_table.setHorizontalHeaderLabels(["Type", "Count", "Elapsed (ms)", "First → Last"])
        self._results_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._results_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._results_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._results_table.verticalHeader().setVisible(False)

        self._surface = _RecordingSurface()

        self._stack = QStackedLayout()
        self._stack.addWidget(self._results_table)
        self._stack.addWidget(self._surface)
        stack_container = QWidget()
        stack_container.setLayout(self._stack)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(toolbar)
        layout.addWidget(stack_container, stretch=1)

        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(1000)
        self._countdown_timer.timeout.connect(self._on_countdown_tick)

        self._stop_timer = QTimer(self)
        self._stop_timer.setSingleShot(True)
        self._stop_timer.timeout.connect(self._stop_recording)

    def _start_recording(self) -> None:
        self._record_button.setEnabled(False)
        self._remaining_seconds = RECORD_DURATION_SECONDS
        self._status_label.setText(f"Recording… {self._remaining_seconds}s left")
        self._stack.setCurrentWidget(self._surface)
        self._surface.start()
        self._countdown_timer.start()
        self._stop_timer.start(RECORD_DURATION_SECONDS * 1000)

    def _on_countdown_tick(self) -> None:
        self._remaining_seconds -= 1
        if self._remaining_seconds > 0:
            self._status_label.setText(f"Recording… {self._remaining_seconds}s left")

    def _stop_recording(self) -> None:
        self._countdown_timer.stop()
        raw_events = self._surface.stop()
        self._stack.setCurrentWidget(self._results_table)
        self._record_button.setEnabled(True)

        groups = _collapse_adjacent(raw_events)
        self._groups = [_group_to_display_dict(g) for g in groups]
        self._recorded_at = datetime.now().isoformat(timespec="seconds")
        self._populate_results_table()
        self._status_label.setText(
            f"Recorded {len(raw_events)} raw event(s) → {len(self._groups)} group(s) at {self._recorded_at}."
        )

    def _populate_results_table(self) -> None:
        self._results_table.setRowCount(len(self._groups))
        for row, group in enumerate(self._groups):
            elapsed = f"{group['start_ms']:.0f}–{group['end_ms']:.0f}"
            if group["first_detail"] == group["last_detail"]:
                detail = group["first_detail"]
            else:
                detail = f"{group['first_detail']}  →  {group['last_detail']}"
            for column, text in enumerate((group["type_name"], str(group["count"]), elapsed, detail)):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._results_table.setItem(row, column, item)

    def get_widget_local_storage(self) -> dict:
        if not self._groups:
            return {}
        return {"recorded_at": self._recorded_at, "groups": self._groups}

    def set_widget_local_storage(self, data: dict) -> None:
        groups = data.get("groups")
        if not groups:
            return
        self._groups = groups
        self._recorded_at = data.get("recorded_at")
        self._populate_results_table()
        self._status_label.setText(f"Restored recording from {self._recorded_at} ({len(self._groups)} group(s)).")


def build() -> QWidget:
    return EventRecorderWidget()
