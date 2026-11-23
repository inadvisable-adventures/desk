"""Recordings: lists DeskRecorder's own finished output -- screen/camera
videos, standalone audio recordings (desk.recorder_app.features
.AudioFeature), and transcript sessions (desk.transcript_pool) -- and
previews whichever one is selected: video/audio playback for a
recording, the timestamped transcript text for a session.

Browses what has already been recorded; it doesn't control recording
itself (that's widgets/recorder/widget.py, which only ever shows the
*newest* transcript session live) and it isn't a live view of an
in-progress capture (that's desk_widgets/video_preview/widget.py).

Playback reuses the exact QMediaPlayer/QVideoSink/QAudioOutput setup
desk_widgets/video_player/widget.py already established, including its
own `QT_MEDIA_BACKEND=darwin` workaround (Qt's default FFmpeg backend
has confirmed hang bugs in its own teardown path) and the
teardown-ordering precaution for the same hang -- duplicated rather
than imported, since widget directories can't import each other's
modules (see desk.voice_capture's own docstring for the same
constraint elsewhere: widgets/voice_input and widgets/claude_desk
share logic through desk.* instead). See that module for the fuller
rationale behind each piece copied here; this one only needed a single
media pane, not a file-open dialog, since the list on the left is the
file picker.
"""
import os

# Must be set before anything in this process constructs its first
# QtMultimedia object -- see desk_widgets/video_player/widget.py's own
# copy of this comment for why. Idempotent (`setdefault`).
os.environ.setdefault("QT_MEDIA_BACKEND", "darwin")

import logging  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from pathlib import Path  # noqa: E402

from PyQt6.QtCore import QPoint, QSizeF, Qt, QTimer, QUrl  # noqa: E402
from PyQt6.QtGui import QImage, QPainter  # noqa: E402
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink  # noqa: E402
from PyQt6.QtWidgets import (  # noqa: E402
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from desk import audio_repair, transcript_pool
from desk.geometry import fit_rect
from desk.recorder_service import RecorderError, RecorderService
from desk.shell import current_context
from desk.shell.qt_controls import canvas_popup_point
from desk.widget_logs import format_time_iso

logger = logging.getLogger(__name__)

REFRESH_INTERVAL_MS = 10_000
KIND_LABELS = {"screen": "Screen", "camera": "Camera", "audio": "Audio", "transcript": "Transcript"}
# DeskRecorder's own recordings-dir naming (desk.recorder_service.start):
# "<feature>-<stamp>.<ext>". Transcript sessions live separately, in the
# transcript pool, keyed by session id rather than a file in this dir.
_RECORDING_GLOBS = (("screen-*.mp4", "screen"), ("camera-*.mp4", "camera"), ("audio-*.wav", "audio"))


@dataclass(frozen=True)
class Entry:
    kind: str  # "screen" | "camera" | "audio" | "transcript"
    name: str  # filename (recordings) or session id (transcript)
    timestamp_ms: int
    path: Path | None  # set for screen/camera/audio
    session: str | None  # set for transcript


def _format_ms(ms: int) -> str:
    total_seconds = max(0, ms) // 1000
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def _scan(service: RecorderService) -> list[Entry]:
    """Newest first. Both halves (files, transcript sessions) are
    independently optional -- a Desk with no current directory raises
    `RecorderError` from either `recordings_dir()` or `pool_dir()`, in
    which case that half just contributes nothing rather than failing
    the whole scan."""
    entries: list[Entry] = []
    try:
        recordings_dir = service.recordings_dir()
    except RecorderError:
        recordings_dir = None
    if recordings_dir is not None:
        for pattern, kind in _RECORDING_GLOBS:
            for path in recordings_dir.glob(pattern):
                try:
                    timestamp_ms = int(path.stat().st_mtime * 1000)
                except OSError:
                    continue
                entries.append(Entry(kind, path.name, timestamp_ms, path, None))
    try:
        pool = service.pool_dir()
    except RecorderError:
        pool = None
    if pool is not None:
        for info in transcript_pool.list_sessions(pool):
            entries.append(Entry("transcript", info.session, info.modified_ms, None, info.session))
    entries.sort(key=lambda e: e.timestamp_ms, reverse=True)
    return entries


class _VideoSurface(QWidget):
    """See desk_widgets/video_player/widget.py's own `_VideoSurface` for
    why this paints frames itself (`QPainter`) rather than using
    `QVideoWidget` -- duplicated, not imported, per this module's own
    docstring."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.sink = QVideoSink(self)
        self.sink.videoFrameChanged.connect(self._on_frame)
        self._image = QImage()

    def _on_frame(self, frame) -> None:
        image = frame.toImage()
        if not image.isNull():
            self._image = image
            self.update()

    def clear(self) -> None:
        self._image = QImage()
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        if self._image.isNull():
            return
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        target = fit_rect(QSizeF(self._image.size()), QSizeF(self.size()))
        painter.drawImage(target, self._image)


class RecordingsWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._service: RecorderService | None = current_context.get_recorder_service()
        self._entries: list[Entry] = []
        self._current: Entry | None = None
        self._slider_being_dragged = False

        # Labels are not user-selectable by default, per this project's
        # own UI convention.
        self._banner = QLabel()
        self._banner.setWordWrap(True)
        self._banner.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._on_selection_changed)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._show_context_menu)

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh)

        left = QVBoxLayout()
        left.addWidget(self._list, 1)
        left.addWidget(refresh_button)
        left_container = QWidget()
        left_container.setLayout(left)
        left_container.setMaximumWidth(280)

        # -- preview pane: media (video/audio) or transcript text, one at a time --
        self._video_surface = _VideoSurface()
        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._player.setVideoSink(self._video_surface.sink)
        self._player.setAudioOutput(self._audio_output)
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_playback_state_changed)
        self._player.errorOccurred.connect(self._on_player_error)

        self._play_button = QPushButton("Play")
        self._play_button.setEnabled(False)
        self._play_button.clicked.connect(self._toggle_play)
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 0)
        self._slider.setEnabled(False)
        self._slider.sliderPressed.connect(self._on_slider_pressed)
        self._slider.sliderReleased.connect(self._on_slider_released)
        self._time_label = QLabel("0:00 / 0:00")
        self._time_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        transport = QHBoxLayout()
        transport.addWidget(self._play_button)
        transport.addWidget(self._slider, 1)
        transport.addWidget(self._time_label)

        media_pane = QWidget()
        media_layout = QVBoxLayout(media_pane)
        media_layout.setContentsMargins(0, 0, 0, 0)
        media_layout.addWidget(self._video_surface, 1)
        media_layout.addLayout(transport)

        self._transcript_view = QPlainTextEdit()
        self._transcript_view.setReadOnly(True)  # content, not a label: selectable so it can be copied

        self._preview_stack = QStackedLayout()
        self._preview_stack.addWidget(media_pane)
        self._preview_stack.addWidget(self._transcript_view)
        preview_pane = QWidget()
        preview_pane.setLayout(self._preview_stack)

        self._detail_label = QLabel()
        self._detail_label.setWordWrap(True)
        self._detail_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        right = QVBoxLayout()
        right.addWidget(self._detail_label)
        right.addWidget(preview_pane, 1)
        right_container = QWidget()
        right_container.setLayout(right)

        body = QHBoxLayout()
        body.addWidget(left_container)
        body.addWidget(right_container, 1)

        layout = QVBoxLayout(self)
        layout.addWidget(self._banner)
        layout.addLayout(body, 1)

        # Capture each resource (not self) -- see
        # desk_widgets/video_player/widget.py's own teardown comment for
        # why: stop the player and disconnect the sink explicitly,
        # before Qt's own child-teardown cascade reaches them, as the
        # same defensive posture against a confirmed QMediaPlayer-close
        # hang (its FFmpeg backend blocking on a decoder/audio thread
        # during destruction while still mid-playback).
        player, sink = self._player, self._video_surface.sink

        def _teardown() -> None:
            sink.videoFrameChanged.disconnect()
            player.stop()

        self.destroyed.connect(_teardown)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.refresh)
        self._refresh_timer.start(REFRESH_INTERVAL_MS)

        self._show_placeholder()
        self.refresh()

    # -- listing -------------------------------------------------------------

    def refresh(self) -> None:
        if self._service is None:
            self._banner.setText("The recorder service is not available in this Desk.")
            return
        self._banner.setText("")
        previous = (self._current.kind, self._current.name) if self._current is not None else None
        self._entries = _scan(self._service)
        self._list.blockSignals(True)
        self._list.clear()
        restore_row = -1
        for row, entry in enumerate(self._entries):
            when = format_time_iso(entry.timestamp_ms)[:19].replace("T", " ")
            item = QListWidgetItem(f"{KIND_LABELS.get(entry.kind, entry.kind)} — {entry.name}  ({when})")
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self._list.addItem(item)
            if (entry.kind, entry.name) == previous:
                restore_row = row
        self._list.blockSignals(False)
        if not self._entries:
            self._banner.setText("No recordings yet — use the Recorder widget to make one.")
        if restore_row >= 0:
            self._list.setCurrentRow(restore_row)
        elif self._current is not None:
            # The previously-selected recording is gone (deleted on disk,
            # or this is a fresh scan after a Desk/session change).
            self._show_placeholder()

    def _on_selection_changed(self, current: "QListWidgetItem | None", _previous) -> None:
        entry = current.data(Qt.ItemDataRole.UserRole) if current is not None else None
        self._show_entry(entry)

    def _show_entry(self, entry: "Entry | None") -> None:
        self._current = entry
        if entry is None:
            self._show_placeholder()
            return
        if entry.kind == "transcript":
            self._player.stop()
            self._preview_stack.setCurrentIndex(1)
            self._load_transcript(entry.session)
            self._detail_label.setText(f"{KIND_LABELS[entry.kind]}: {entry.name}")
        else:
            self._preview_stack.setCurrentIndex(0)
            self._video_surface.clear()
            self._player.setSource(QUrl.fromLocalFile(str(entry.path)))
            self._play_button.setEnabled(True)
            self._slider.setEnabled(True)
            self._detail_label.setText(f"{KIND_LABELS[entry.kind]}: {entry.path}")

    # -- context menu --------------------------------------------------------

    def _show_context_menu(self, local_pos: QPoint) -> None:
        item = self._list.itemAt(local_pos)
        if item is None:
            return
        entry = item.data(Qt.ItemDataRole.UserRole)
        if entry is None or entry.kind != "audio":
            return  # only a standalone AudioFeature recording can have a mislabeled sample rate
        # parent=None -- see python-widget-conventions.md's "Popups from
        # embedded widgets" and desk.shell.qt_controls.canvas_popup_point's
        # own docstring: a QMenu parented to the embedded WidgetFrame lands
        # a constant offset away from where it was asked to open, and
        # canvas_popup_point (not plain mapToGlobal) is what accounts for
        # the canvas's own pan/zoom.
        menu = QMenu(None)
        repair_action = menu.addAction("Repair sample rate")
        chosen = menu.exec(canvas_popup_point(self._list, local_pos))
        if chosen is repair_action:
            self._repair_sample_rate(entry)

    def _repair_sample_rate(self, entry: "Entry") -> None:
        """desk.audio_repair only ever rewrites the WAV header (the
        sample data was never wrong -- see that module's own docstring
        for the bug this undoes), but the file on disk still changed, so
        a still-open QMediaPlayer source pointed at it needs reloading;
        `refresh()` (which re-selects the same entry if it's still
        current) takes care of that. The success/failure message goes on
        `_banner`, not `_detail_label` -- `refresh()`'s own re-selection
        overwrites `_detail_label` with the normal path info, so the
        banner is the only thing that survives to actually be seen."""
        try:
            old_rate, new_rate = audio_repair.repair_sample_rate(entry.path)
        except audio_repair.RepairError as e:
            self._banner.setText(f"Could not repair {entry.name}: {e}")
            return
        self.refresh()
        self._banner.setText(f"Repaired {entry.name}: {old_rate} Hz → {new_rate} Hz")

    def _show_placeholder(self) -> None:
        self._current = None
        self._preview_stack.setCurrentIndex(0)
        self._player.stop()
        self._video_surface.clear()
        self._play_button.setEnabled(False)
        self._slider.setEnabled(False)
        self._slider.setRange(0, 0)
        self._time_label.setText("0:00 / 0:00")
        self._detail_label.setText("Select a recording on the left to preview it here.")

    def _load_transcript(self, session: str) -> None:
        if self._service is None:
            self._transcript_view.setPlainText("")
            return
        try:
            pool = self._service.pool_dir()
        except RecorderError:
            self._transcript_view.setPlainText("")
            return
        segments = transcript_pool.read_collapsed(pool, session)
        lines = [f"[{format_time_iso(s.start_ms)[11:19]}]{'' if s.final else '~'} {s.text}" for s in segments]
        self._transcript_view.setPlainText("\n".join(lines) if lines else "(empty transcript)")

    # -- playback -------------------------------------------------------------

    def _toggle_play(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        self._play_button.setText("Pause" if state == QMediaPlayer.PlaybackState.PlayingState else "Play")

    def _on_duration_changed(self, duration_ms: int) -> None:
        self._slider.setRange(0, duration_ms)
        self._update_time_label()

    def _on_position_changed(self, position_ms: int) -> None:
        if not self._slider_being_dragged:
            self._slider.setValue(position_ms)
        self._update_time_label()

    def _update_time_label(self) -> None:
        self._time_label.setText(f"{_format_ms(self._player.position())} / {_format_ms(self._player.duration())}")

    def _on_slider_pressed(self) -> None:
        self._slider_being_dragged = True

    def _on_slider_released(self) -> None:
        self._slider_being_dragged = False
        self._player.setPosition(self._slider.value())

    def _on_player_error(self, error: QMediaPlayer.Error, error_string: str) -> None:
        if error != QMediaPlayer.Error.NoError:
            logger.error("Recordings widget playback error: %s", error_string)
            self._detail_label.setText(f"Playback error: {error_string}")

    # -- widget-local storage -- remembers which recording was selected,
    # same shape as desk_widgets/video_player/widget.py's own `path`
    # (and widgets/markdown's), so a plain Desk reload restores it.
    def get_widget_local_storage(self) -> dict:
        if self._current is None:
            return {}
        return {"kind": self._current.kind, "name": self._current.name}

    def set_widget_local_storage(self, data: dict) -> None:
        if not data:
            return
        target = (data.get("kind"), data.get("name"))
        for row in range(self._list.count()):
            entry = self._list.item(row).data(Qt.ItemDataRole.UserRole)
            if (entry.kind, entry.name) == target:
                self._list.setCurrentRow(row)
                return


def build() -> QWidget:
    return RecordingsWidget()
