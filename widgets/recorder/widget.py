import threading

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from desk import recorder_protocol as proto
from desk import transcript_pool
from desk.recorder_service import RecorderError, RecorderService
from desk.shell import current_context
from desk.shell.qt_controls import PaintedComboBox
from desk.widget_logs import format_time_iso

POLL_INTERVAL_MS = 500
LEVEL_POLL_INTERVAL_MS = 100  # the meter alone, polled faster than everything else -- cheap, no I/O
FEATURE_TITLES = {
    "transcribe": "Transcription",
    "screen": "Screen recording",
    "camera": "Camera video",
    "audio": "Audio recording",
}
FEATURE_NEEDS = {
    "transcribe": "needs Microphone",
    "screen": "needs Screen Recording (+ Microphone for audio)",
    "camera": "needs Camera",
    "audio": "needs Microphone -- a separate, timestamped recording of just the input device picked below",
}
STATE_TEXT = {
    "idle": "off",
    "starting": "starting...",
    "running": "recording",
    "stopping": "stopping...",
    "error": "error",
    "denied": "permission denied",
    "disconnected": "lost the recorder",
}


class _Signals(QObject):
    error = pyqtSignal(str)
    sources = pyqtSignal(object)


class _LevelMeter(QWidget):
    """`AudioFeature`'s live input level (0.0-1.0), as a small horizontal
    bar next to the microphone picker. Plain `QWidget` + `paintEvent`, not
    a native-styled control and no popup of its own, so none of
    `python-widget-conventions.md`'s `PaintedComboBox`-style canvas
    problems (those are about controls that open a separately-positioned
    top-level popup) apply here."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._level = 0.0
        self.setFixedSize(70, 16)
        self.setToolTip("Microphone input level")

    def set_level(self, level: float) -> None:
        level = max(0.0, min(1.0, level))
        if level != self._level:
            self._level = level
            self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        try:
            rect = self.rect().adjusted(0, 0, -1, -1)
            painter.setPen(QColor(110, 110, 110))
            painter.setBrush(QColor(35, 35, 35))
            painter.drawRect(rect)
            fill_width = round((rect.width() - 2) * self._level)
            if fill_width > 0:
                color = QColor(220, 70, 70) if self._level > 0.85 else QColor(80, 190, 110)
                painter.fillRect(rect.x() + 1, rect.y() + 1, fill_width, rect.height() - 2, color)
        finally:
            painter.end()


class RecorderWidget(QWidget):
    """Controls for DeskRecorder.app (TODO b9689cd): one row per feature
    (transcription, screen recording, camera video, standalone audio),
    each started and stopped independently, and a live view of the newest
    transcript from the shared transcript pool. The audio row also carries
    the input-device picker for that standalone recording (transcription's
    own mic use stays on the system default; this is specifically for the
    saved track) and a live level meter next to it. The widget never
    records anything itself; it drives `desk.recorder_service
    .RecorderService`, which starts the app (and macOS asks for each
    permission the first time a feature needs it)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._service: RecorderService | None = current_context.get_recorder_service()
        self._signals = _Signals()
        self._signals.error.connect(self._show_error)
        self._signals.sources.connect(self._fill_sources)
        self._buttons: dict[str, QPushButton] = {}
        self._state_labels: dict[str, QLabel] = {}
        self._session: str | None = None
        self._offset = 0
        self._segments: dict[int, transcript_pool.Segment] = {}

        self._banner = QLabel()
        self._banner.setWordWrap(True)
        self._banner.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        layout = QVBoxLayout(self)
        layout.addWidget(self._banner)

        self._target_combo = PaintedComboBox()
        self._target_combo.addItem("Whole screen", "screen")
        self._camera_combo = PaintedComboBox()
        self._camera_combo.addItem("Default camera", "default")
        self._audio_combo = PaintedComboBox()
        self._audio_combo.addItem("Default microphone", "default")
        self._level_meter = _LevelMeter()
        extra = {"screen": self._target_combo, "camera": self._camera_combo, "audio": self._audio_combo}
        for feature in proto.FEATURES:
            row = QHBoxLayout()
            title = QLabel(FEATURE_TITLES[feature])
            title.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
            title.setToolTip(FEATURE_NEEDS[feature])
            title.setMinimumWidth(120)
            row.addWidget(title)
            if feature in extra:
                row.addWidget(extra[feature], 1)
            else:
                row.addStretch(1)
            if feature == "audio":
                row.addWidget(self._level_meter)
            state = QLabel(STATE_TEXT["idle"])
            state.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
            state.setMinimumWidth(110)
            self._state_labels[feature] = state
            row.addWidget(state)
            button = QPushButton("Start")
            button.clicked.connect(lambda _checked=False, f=feature: self._toggle(f))
            self._buttons[feature] = button
            row.addWidget(button)
            layout.addLayout(row)

        tools = QHBoxLayout()
        self._sources_button = QPushButton("Refresh windows, cameras and microphones")
        self._sources_button.clicked.connect(self._refresh_sources)
        tools.addWidget(self._sources_button)
        tools.addStretch(1)
        layout.addLayout(tools)

        self._detail = QLabel()
        self._detail.setWordWrap(True)
        self._detail.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        layout.addWidget(self._detail)

        heading = QLabel("Transcript (newest session; ~ marks text that may still change)")
        heading.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        layout.addWidget(heading)
        self._transcript = QPlainTextEdit()
        self._transcript.setReadOnly(True)  # content, not a label: selectable so it can be copied
        layout.addWidget(self._transcript, 1)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(POLL_INTERVAL_MS)
        self._level_timer = QTimer(self)
        self._level_timer.timeout.connect(self._refresh_level)
        self._level_timer.start(LEVEL_POLL_INTERVAL_MS)
        self.refresh()

    # --- actions ---

    def _run_async(self, fn) -> None:
        """Service calls can launch the app and wait for it, so they never
        run on the GUI thread; the outcome shows up through `refresh`."""

        def work() -> None:
            try:
                fn()
            except RecorderError as e:
                self._signals.error.emit(str(e))
            except Exception as e:  # noqa: BLE001 -- shown, not swallowed
                self._signals.error.emit(f"{type(e).__name__}: {e}")

        threading.Thread(target=work, daemon=True, name="recorder-widget").start()

    def _toggle(self, feature: str) -> None:
        if self._service is None:
            return
        service = self._service
        state = service.feature_status(feature)["state"]
        if state in ("starting", "running"):
            self._run_async(lambda: service.stop(feature))
            return
        target = device = None
        if feature == "screen":
            target = self._target_combo.currentData()
        elif feature == "camera":
            device = self._camera_combo.currentData()
        elif feature == "audio":
            device = self._audio_combo.currentData()
        self._detail.setText("")
        self._run_async(lambda: service.start(feature, target, device))

    def _refresh_level(self) -> None:
        service = self._service
        if service is None:
            return
        running = service.feature_status("audio")["state"] == "running"
        self._level_meter.set_level((service.latest_level("audio") or 0.0) if running else 0.0)

    def _refresh_sources(self) -> None:
        if self._service is None:
            return
        service = self._service
        self._detail.setText("Asking DeskRecorder for windows, cameras and microphones...")
        self._run_async(lambda: self._signals.sources.emit(service.request_sources()))

    def _fill_sources(self, sources: dict) -> None:
        self._target_combo.clear()
        self._target_combo.addItem("Whole screen", "screen")
        for title in sources.get("window", []):
            if title.strip():
                self._target_combo.addItem(title, "window:" + proto.quote_token(title))
        self._camera_combo.clear()
        self._camera_combo.addItem("Default camera", "default")
        for name in sources.get("camera", []):
            self._camera_combo.addItem(name, proto.quote_token(name))
        self._audio_combo.clear()
        self._audio_combo.addItem("Default microphone", "default")
        for name in sources.get("microphone", []):
            self._audio_combo.addItem(name, proto.quote_token(name))
        self._detail.setText("")

    def _show_error(self, message: str) -> None:
        self._detail.setText(message)

    # --- polling ---

    def refresh(self) -> None:
        service = self._service
        if service is None:
            self._banner.setText("The recorder service is not available in this Desk.")
            for button in self._buttons.values():
                button.setEnabled(False)
            return
        status = service.status()
        if status["connected"]:
            self._banner.setText("DeskRecorder is running." + ("  It has stopped responding." if status["stale"] else ""))
        elif service._app_locator() is None:
            self._banner.setText(
                "DeskRecorder.app is not installed. Build it with scripts/build_desk_recorder_app.sh; "
                "it starts when you turn a feature on."
            )
        else:
            self._banner.setText("DeskRecorder starts when you turn a feature on.")
        messages = []
        for feature, info in status["features"].items():
            self._state_labels[feature].setText(STATE_TEXT.get(info["state"], info["state"]))
            self._buttons[feature].setText("Stop" if info["state"] in ("starting", "running") else "Start")
            self._buttons[feature].setEnabled(info["state"] != "stopping")
            if info["detail"] and info["state"] in ("error", "denied", "starting"):
                messages.append(f"{FEATURE_TITLES[feature]}: {info['detail']}")
            if info["dropped"] and info["state"] == "running":
                messages.append(f"{FEATURE_TITLES[feature]}: {info['dropped']} stalls (gaps over 100 ms between frames)")
            if info["path"] and info["state"] in ("running", "idle"):
                messages.append(f"{FEATURE_TITLES[feature]} file: {info['path']}")
        if messages:
            self._detail.setText("\n".join(messages))
        self._refresh_transcript(status["features"]["transcribe"].get("session"))

    def _refresh_transcript(self, active_session: str | None) -> None:
        try:
            pool = self._service.pool_dir()
        except RecorderError:
            return
        sessions = transcript_pool.list_sessions(pool)
        newest = active_session or (sessions[-1].session if sessions else None)
        if newest is None:
            return
        if newest != self._session:
            self._session, self._offset, self._segments = newest, 0, {}
            self._transcript.clear()
        records, self._offset = transcript_pool.read_records(pool, newest, self._offset)
        if not records:
            return
        for record in records:
            self._segments[record.seq] = record
        lines = [
            f"[{format_time_iso(s.start_ms)[11:19]}]{'' if s.final else '~'} {s.text}"
            for s in (self._segments[seq] for seq in sorted(self._segments))
        ]
        self._transcript.setPlainText("\n".join(lines))
        scrollbar = self._transcript.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())


def build() -> QWidget:
    return RecorderWidget()
