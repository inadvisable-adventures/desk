"""Video Player: opens and plays a single video file (e.g. a DeskRecorder
screen/camera recording, or the composite_recording Installed Job's own
composited output). Same `set_file(path)` + `SingleFileWatcher`
auto-reload shape as `widgets/image_viewer/widget.py` -- the closest
existing precedent for "open a single media file dropped via
OpenWithWidget" -- so this widget works as the `OpenWithWidget` target
for a video file the same way Image Viewer already does for images.
"""
import logging
import os
from pathlib import Path

# Must be set before anything in this process constructs its first
# QtMultimedia object (QMediaPlayer/QAudioOutput/...) -- Qt resolves and
# caches its multimedia backend plugin once per process on first real
# use, not per widget instance, and a later `os.environ` change can't
# retroactively undo an already-loaded backend. Qt's own FFmpeg backend
# (the default on macOS since Qt 6.5) has multiple independently
# -reported freeze/hang bugs in its own teardown path (e.g. Qt bug
# QTBUG-120198, a static-destructor hang in Qt6Multimedia -- see
# FEEDBACK-DESK-closing-a-kind-python-widget-that-owns-a-qmediaplayer-qtmult-2026-11-22-2258
# for the full investigation and sources), closely matching what hung
# this widget's own teardown *after* its own code had already finished.
# "darwin" selects the native AVFoundation backend instead -- already
# proven working on this machine (desk_recorder/launcher.m talks to
# AVFoundation directly for capture). `setdefault` so an operator's own
# already-set value always wins. NOTE: only takes effect from a fresh
# Desk start, and only if nothing else in the process touches
# QtMultimedia first (e.g. the Voice Input widget, if built earlier in
# the same session) -- not fixable from inside one project widget alone.
os.environ.setdefault("QT_MEDIA_BACKEND", "darwin")

from PyQt6.QtCore import QDir, QSizeF, Qt, QThread, QUrl
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from desk.file_watch import SingleFileWatcher
from desk.geometry import fit_rect
from desk.persisted_path import resolve_persisted_path
from desk.shell import current_context

logger = logging.getLogger(__name__)

VIDEO_FILTER = "Videos (*.mp4 *.mov *.m4v *.avi *.mkv *.webm);;All files (*)"


def _thread_tag(obj) -> str:
    """For diagnosing TODO FEEDBACK-DESK-closing-a-kind-python-widget...
    (the close-while-having-played app hang): which thread we're
    currently running on, and whether that matches `obj`'s own affinity
    -- a mismatch (a slot invoked off its receiver's own thread) would
    point straight at a cross-thread Qt Multimedia callback as the
    culprit. Remove once that investigation is done."""
    current = QThread.currentThread()
    owner = obj.thread()
    return f"thread={current!r} owner_thread={owner!r} same={current is owner}"


def _format_ms(ms: int) -> str:
    total_seconds = max(0, ms) // 1000
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


class _VideoSurface(QWidget):
    """Paints video frames itself via `QPainter`, instead of
    `QVideoWidget`. `QVideoWidget` renders through its own native/
    windowed video-output surface, which -- like a Qt popup/dialog, see
    "Popups from embedded widgets" in python-widget-conventions.md --
    doesn't composite correctly once embedded in the canvas's own
    `QGraphicsProxyWidget`: confirmed directly, audio played but no
    video frame ever appeared. A `QVideoSink`'s own frames, painted here
    the same ordinary way Image Viewer's `_AspectImageView` already
    paints a `QPixmap` (widgets/image_viewer/widget.py), sidestep that
    native-surface path entirely -- plain `QImage`/`QPainter`, the same
    alien-embedding-safe technique every other custom-painted widget in
    this canvas already relies on."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.sink = QVideoSink(self)
        self.sink.videoFrameChanged.connect(self._on_frame)
        self._image = QImage()
        self.frame_count = 0  # read by VideoPlayerWidget's teardown logging

    def _on_frame(self, frame) -> None:
        self.frame_count += 1
        if self.frame_count == 1:
            logger.info("video_player: first frame received (%s)", _thread_tag(self))
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


class VideoPlayerWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # Short per-instance tag for telling concurrent instances apart
        # in the shared desk.log while chasing TODO
        # FEEDBACK-DESK-closing-a-kind-python-widget... (the app hang on
        # close). Remove this whole debug-logging pass once that's
        # root-caused.
        self._debug_id = f"{id(self):x}"
        logger.info("video_player[%s]: constructed (%s)", self._debug_id, _thread_tag(self))
        self._current_path: Path | None = None
        self._last_dir = current_context.get_current_desk_directory() or Path.home()
        self._slider_being_dragged = False

        self._video_surface = _VideoSurface()
        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._player.setVideoSink(self._video_surface.sink)
        self._player.setAudioOutput(self._audio_output)
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_playback_state_changed)
        self._player.errorOccurred.connect(self._on_error)

        # Labels are not user-selectable by default, per this project's
        # own UI convention.
        self._label = QLabel()
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._time_label = QLabel("0:00 / 0:00")
        self._time_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        open_button = QPushButton("Open")
        open_button.clicked.connect(self._open_file)

        self._play_button = QPushButton("Play")
        self._play_button.setEnabled(False)
        self._play_button.clicked.connect(self._toggle_play)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 0)
        self._slider.setEnabled(False)
        self._slider.sliderPressed.connect(self._on_slider_pressed)
        self._slider.sliderReleased.connect(self._on_slider_released)

        toolbar = QHBoxLayout()
        toolbar.addWidget(open_button)
        toolbar.addWidget(self._play_button)
        toolbar.addStretch()
        toolbar.addWidget(self._label)

        transport = QHBoxLayout()
        transport.addWidget(self._slider, stretch=1)
        transport.addWidget(self._time_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(toolbar)
        layout.addWidget(self._video_surface, stretch=1)
        layout.addLayout(transport)

        self._watcher = SingleFileWatcher(self)
        self._watcher.changed.connect(self._reload)
        # Capture each resource (not self) so the teardown closure never
        # touches this widget's Qt state during destruction -- mirrors
        # the Image Viewer/Markdown widgets' own teardown pattern.
        #
        # player.stop() explicitly, before Qt's own child-teardown cascade
        # reaches it: closing this widget once hung the whole app (force
        # -quit required) with no exception logged anywhere, consistent
        # with QMediaPlayer's FFmpeg backend blocking on a decoder/audio
        # thread during destruction while still mid-playback. `destroyed`
        # fires at the very start of this QObject's own destructor --
        # before Qt deletes child QObjects like `self._player` -- so this
        # is the latest safe point to ask it to wind down first, the same
        # way `claude_desk/widget.py` stops its own session here. A clean
        # repro of the hang itself wasn't reproducible offscreen/headless
        # (no real GPU/audio teardown path there), so this is a
        # defensive-but-unconfirmed fix, not a proven root-cause fix.
        player, sink, surface = self._player, self._video_surface.sink, self._video_surface
        watcher = self._watcher
        debug_id = self._debug_id

        # Bracketing log around every sub-step (TODO
        # FEEDBACK-DESK-closing-a-kind-python-widget...): on a real hang,
        # the GUI thread never returns from whichever call is blocked, so
        # whichever "before X" line is the LAST one desk.log shows for
        # this debug_id *is* the culprit -- no "after X" line means that
        # call never returned. Remove this whole pass once root-caused.
        def _teardown() -> None:
            # `self` is already unsafe to touch here -- confirmed directly
            # (self.thread() raised "wrapped C/C++ object ... has been
            # deleted" the instant `destroyed` fired, in a headless repro
            # of this very logging). `player`/`sink`/`surface`/`watcher`
            # are separately-captured QObjects, still alive at this point
            # per Qt's own `destroyed`-signal docs (a parent's children
            # are only deleted *after* its own `destroyed` is emitted) --
            # use `_thread_tag(player)` instead, not `self`.
            logger.info(
                "video_player[%s]: destroyed handler entered, playbackState=%r frames_seen=%d (%s)",
                debug_id,
                player.playbackState(),
                surface.frame_count,
                _thread_tag(player),
            )
            logger.info("video_player[%s]: before sink.videoFrameChanged.disconnect()", debug_id)
            sink.videoFrameChanged.disconnect()
            logger.info("video_player[%s]: after sink.videoFrameChanged.disconnect()", debug_id)

            logger.info("video_player[%s]: before player.stop()", debug_id)
            player.stop()
            logger.info("video_player[%s]: after player.stop()", debug_id)

            logger.info("video_player[%s]: before watcher.stop()", debug_id)
            watcher.stop()
            logger.info("video_player[%s]: after watcher.stop() -- teardown complete", debug_id)

        self.destroyed.connect(_teardown)

        self._show_placeholder()

    def _show_placeholder(self) -> None:
        self._label.setText("(no file — click Open to choose a video file)")
        self._play_button.setEnabled(False)
        self._slider.setEnabled(False)
        self._slider.setRange(0, 0)
        self._time_label.setText("0:00 / 0:00")

    def _open_file(self) -> None:
        # The native macOS open panel (what QFileDialog.getOpenFileName
        # uses by default) hides dotfiles/dot-directories -- e.g.
        # .desk_temp/, where every DeskRecorder recording and the
        # composite_recording Installed Job's own output actually live
        # -- with no public Qt API to pre-enable "show hidden files"
        # there (only the user's own Cmd+Shift+. toggle does). Qt's own
        # non-native dialog has no such restriction, so ask for that
        # instead and explicitly include hidden entries in its filter.
        #
        # parent=None, not self: this widget's content is embedded in
        # the zoomable canvas via a QGraphicsProxyWidget, and a Qt
        # popup/dialog parented to that "alien" embed renders wrong --
        # see "Popups from embedded widgets" in
        # python-widget-conventions.md (confirmed directly: the dialog's
        # own content didn't display correctly with parent=self).
        dialog = QFileDialog(None, "Open Video File", str(self._last_dir), VIDEO_FILTER)
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dialog.setFilter(dialog.filter() | QDir.Filter.Hidden)
        if dialog.exec() and dialog.selectedFiles():
            self.set_file(Path(dialog.selectedFiles()[0]))

    def set_file(self, path: Path) -> None:
        """Point the widget at `path`: load it and watch it for changes.
        Public so other widgets (and `OpenWithWidget`) can open a file
        here programmatically, matching Image Viewer/Markdown's own
        `set_file`."""
        self._current_path = path
        self._last_dir = path.parent
        self._watcher.watch(path)
        self._reload()

    def _reload(self) -> None:
        path = self._current_path
        if path is None:
            self._show_placeholder()
            return
        if not path.is_file():
            self._label.setText(f"`{path.name}` no longer exists.")
            self._player.stop()
            self._video_surface.clear()
            self._play_button.setEnabled(False)
            self._slider.setEnabled(False)
            return
        was_playing = self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        self._player.setSource(QUrl.fromLocalFile(str(path)))
        self._label.setText(path.name)
        self._play_button.setEnabled(True)
        self._slider.setEnabled(True)
        if was_playing:
            self._player.play()

    def _toggle_play(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        logger.info("video_player[%s]: playbackStateChanged -> %r (%s)", self._debug_id, state, _thread_tag(self))
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

    def _on_error(self, error: QMediaPlayer.Error, error_string: str) -> None:
        if error != QMediaPlayer.Error.NoError:
            logger.error("Video playback error for %s: %s", self._current_path, error_string)
            self._label.setText(f"Playback error: {error_string}")

    # -- widget-local storage -- same shape as the Markdown widget's own
    # (widgets/markdown/widget.py), so `desk_place_widget`'s `state`
    # seeding and a plain Desk reload both restore the last-opened file.
    def get_widget_local_storage(self) -> dict:
        return {"path": str(self._current_path)} if self._current_path else {}

    def set_widget_local_storage(self, data: dict) -> None:
        path = resolve_persisted_path(data.get("path"))
        if path is not None:
            self.set_file(path)


def build() -> QWidget:
    return VideoPlayerWidget()
