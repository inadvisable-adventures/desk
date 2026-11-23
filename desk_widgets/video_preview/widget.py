"""Video Preview: a *live* view -- your own camera, one of your screens,
or what DeskRecorder.app is actually capturing -- independent of (not
playback of) any recorded file. Separate from `desk_widgets/video_player/`
(which plays back a finished recording) by explicit request; the two
share no code, matching how `widgets/image_viewer/widget.py` and the
Markdown widget's own viewer are also independent despite both
ultimately painting a decoded frame.

Three source modes, switchable per instance (each placed instance owns
its own `QCamera`/`QScreenCapture`/`QMediaCaptureSession`/preview-poll
timer, so multiple instances are fully independent of one another):
  - "Live Camera": QCamera, listing every QMediaDevices.videoInputs().
  - "Live Screen": QScreenCapture, listing every attached QScreen.
  - "DeskRecorder Capture" (TODO d95a323): polls
    `desk.recorder_service.RecorderService.latest_preview(feature)` --
    a low-fps JPEG snapshot DeskRecorder's own `VideoFeature` pipeline
    (src/desk/recorder_app/features.py) sends over the existing control
    socket, tapped from the exact `QVideoSink` it already has wired to
    the same `QMediaCaptureSession` driving its `QMediaRecorder`. No
    `QCamera`/`QScreenCapture` of our own in this mode, so no OS
    permission prompt for this widget at all -- it shows what
    DeskRecorder is *actually* recording, not an independent second
    capture of the same source. (An earlier version of this widget only
    had the first two modes, which independently opened the same kind
    of source DeskRecorder itself would -- that hit the exact permission
    problem DeskRecorder.app was built to solve in the first place the
    moment it was tried live; see plans/deskrecorder-live-preview-frames.md
    for the investigation, including why reading DeskRecorder's own
    in-progress output file directly isn't viable either -- its MP4
    muxer only writes the index atom at finalize/stop.)

The two independent-capture modes still poll+show DeskRecorder's own
actual state for the analogous feature as a status line alongside the
live picture, same as before -- an honest readout of whether DeskRecorder
itself is currently recording it, distinct from this widget's own
Start/Stop (which, in "DeskRecorder Capture" mode, only starts/stops
*this widget's own polling*, never DeskRecorder's actual recording).
"""
import base64
import logging
import os

# Must be set before anything in this process constructs its first
# QtMultimedia object -- see desk_widgets/video_player/widget.py's own
# copy of this comment (and
# FEEDBACK-DESK-resolved-confirmed-the-qmediaplayer-close-hang-feedback-desk-2026-11-23-1029
# for the full investigation) for why: Qt's default FFmpeg multimedia
# backend has confirmed hang bugs in its own teardown, and the backend
# is resolved once per process on first real use -- setting this here
# too (not just in video_player's module) means this widget is correct
# on its own even if it happens to be the first thing in a given
# session to touch QtMultimedia. Idempotent (`setdefault`).
os.environ.setdefault("QT_MEDIA_BACKEND", "darwin")

from PyQt6.QtCore import QSizeF, Qt, QTimer, QUrl  # noqa: E402 -- see setdefault above
from PyQt6.QtGui import QImage, QPainter  # noqa: E402
from PyQt6.QtMultimedia import (  # noqa: E402
    QCamera,
    QMediaCaptureSession,
    QMediaDevices,
    QScreenCapture,
    QVideoSink,
)
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget  # noqa: E402

from desk.geometry import fit_rect  # noqa: E402
from desk.recorder_service import RecorderService  # noqa: E402
from desk.shell import current_context  # noqa: E402
from desk.shell.qt_controls import PaintedComboBox  # noqa: E402

logger = logging.getLogger(__name__)

# DeskRecorder's own STATE_TEXT -- duplicated (not imported) from
# widgets/recorder/widget.py: small, and importing a sibling built-in
# widget module to share four strings isn't worth the coupling.
RECORDER_STATE_TEXT = {
    "idle": "off",
    "starting": "starting...",
    "running": "recording",
    "stopping": "stopping...",
    "error": "error",
    "denied": "permission denied",
    "disconnected": "lost the recorder",
}
RECORDER_POLL_INTERVAL_MS = 500  # matches widgets/recorder/widget.py's own POLL_INTERVAL_MS
STARTUP_GRACE_MS = 3000  # see _check_startup_stalled

MODE_CAMERA = "camera"
MODE_SCREEN = "screen"
MODE_RECORDER = "recorder"  # TODO d95a323 -- see _start's MODE_RECORDER branch
MODES = (MODE_CAMERA, MODE_SCREEN, MODE_RECORDER)
# DeskRecorder's own feature names (desk.recorder_protocol.FEATURES minus
# "transcribe", which has no video) -- the "DeskRecorder Capture" mode's
# own source combo lists these, not real devices/screens.
RECORDER_VIDEO_FEATURES = (("Screen", "screen"), ("Camera", "camera"))


class _VideoSurface(QWidget):
    """Paints video frames itself via `QPainter` -- see
    desk_widgets/video_player/widget.py's own `_VideoSurface` for why
    (not `QVideoWidget`, whose native video-output surface doesn't
    composite correctly once embedded in the canvas's
    `QGraphicsProxyWidget`). Duplicated rather than imported across
    these two widgets' own separate modules, matching how this project
    doesn't share e.g. image_viewer's `_AspectImageView` elsewhere
    either -- a small, self-contained view class per widget."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.sink = QVideoSink(self)
        self.sink.videoFrameChanged.connect(self._on_frame)
        self._image = QImage()

    def _on_frame(self, frame) -> None:
        self.show_image(frame.toImage())

    def show_image(self, image: QImage) -> None:
        """The same paint path as `_on_frame`, but for a still `QImage`
        decoded elsewhere -- used by the "DeskRecorder Capture" mode
        (TODO d95a323), which polls `RecorderService.latest_preview`
        (discrete JPEG snapshots) rather than getting a continuous
        `QVideoSink` frame stream."""
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


def _screen_label(screen, index: int) -> str:
    name = screen.name()
    geometry = screen.geometry()
    base = name if name else f"Screen {index + 1}"
    return f"{base} ({geometry.width()}x{geometry.height()})"


class VideoPreviewWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._recorder_service: RecorderService | None = current_context.get_recorder_service()

        self._surface = _VideoSurface()
        self._session = QMediaCaptureSession(self)
        self._session.setVideoSink(self._surface.sink)
        self._camera: QCamera | None = None
        self._screen_capture: QScreenCapture | None = None
        self._active = False
        self._start_token = 0

        # TODO d95a323: "DeskRecorder Capture" mode polls
        # RecorderService.latest_preview instead of running its own
        # QCamera/QScreenCapture -- created once (parented, like
        # _recorder_timer below), only started/stopped by _start/_stop.
        self._preview_poll_timer = QTimer(self)
        self._preview_poll_timer.setInterval(RECORDER_POLL_INTERVAL_MS)
        self._preview_poll_timer.timeout.connect(self._poll_preview_frame)
        self._last_preview_b64: str | None = None

        self._mode_combo = PaintedComboBox()
        self._mode_combo.addItem("Live Camera", MODE_CAMERA)
        self._mode_combo.addItem("Live Screen", MODE_SCREEN)
        self._mode_combo.addItem("DeskRecorder Capture", MODE_RECORDER)
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        self._source_combo = PaintedComboBox()

        self._toggle_button = QPushButton("Start")
        self._toggle_button.clicked.connect(self._toggle_active)

        # Labels are not user-selectable by default, per this project's
        # own UI convention.
        self._own_status = QLabel()
        self._own_status.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._recorder_status = QLabel()
        self._recorder_status.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        toolbar = QHBoxLayout()
        toolbar.addWidget(self._mode_combo)
        toolbar.addWidget(self._source_combo, 1)
        toolbar.addWidget(self._toggle_button)

        status_row = QHBoxLayout()
        status_row.addWidget(self._own_status)
        status_row.addStretch(1)
        status_row.addWidget(self._recorder_status)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(toolbar)
        layout.addWidget(self._surface, stretch=1)
        layout.addLayout(status_row)

        self._recorder_timer = QTimer(self)
        self._recorder_timer.setInterval(RECORDER_POLL_INTERVAL_MS)
        self._recorder_timer.timeout.connect(self._poll_recorder_status)
        self._recorder_timer.start()

        # Capture each resource (not self) -- see
        # desk_widgets/video_player/widget.py's own teardown comment for
        # why: `self` is already unsafe to touch by the time `destroyed`
        # fires (confirmed directly, chasing the QMediaPlayer hang this
        # pattern is copied from), and stopping an active capture
        # explicitly before Qt's own child-teardown cascade reaches it
        # is the same defensive posture that investigation landed on.
        session = self._session
        timer = self._recorder_timer
        preview_timer = self._preview_poll_timer

        def _teardown() -> None:
            camera = self._camera
            screen_capture = self._screen_capture
            if camera is not None:
                camera.stop()
            if screen_capture is not None:
                screen_capture.stop()
            session.setCamera(None)
            session.setScreenCapture(None)
            timer.stop()
            preview_timer.stop()

        self.destroyed.connect(_teardown)

        self._set_mode(MODE_CAMERA, populate_source=True)
        self._update_own_status()
        self._poll_recorder_status()

    # -- mode / source selection -----------------------------------------

    def _on_mode_changed(self, _index: int) -> None:
        mode = self._mode_combo.currentData()
        self._set_mode(mode, populate_source=True)

    def _set_mode(self, mode: str, *, populate_source: bool, select_source: object = None) -> None:
        if self._active:
            self._stop()
        if self._mode_combo.currentData() != mode:
            self._mode_combo.setCurrentIndex(MODES.index(mode))
        if populate_source:
            self._populate_source_combo(mode, select=select_source)

    def _populate_source_combo(self, mode: str, *, select: object = None) -> None:
        self._source_combo.clear()
        if mode == MODE_CAMERA:
            for device in QMediaDevices.videoInputs():
                self._source_combo.addItem(device.description(), device)
            if select is not None:
                self._select_source_by(lambda data: bytes(data.id()).decode("utf-8", "replace") == select)
        elif mode == MODE_SCREEN:
            for index, screen in enumerate(QApplication.screens()):
                self._source_combo.addItem(_screen_label(screen, index), screen)
            if select is not None:
                self._select_source_by(lambda data: data.name() == select)
        else:  # MODE_RECORDER -- DeskRecorder's own feature names, not real devices
            for label, feature in RECORDER_VIDEO_FEATURES:
                self._source_combo.addItem(label, feature)
            if select is not None:
                self._select_source_by(lambda data: data == select)

    def _select_source_by(self, matches) -> None:
        for index in range(self._source_combo.count()):
            if matches(self._source_combo.itemData(index)):
                self._source_combo.setCurrentIndex(index)
                return

    # -- start / stop ------------------------------------------------------

    def _toggle_active(self) -> None:
        if self._active:
            self._stop()
        else:
            self._start()

    def _start(self) -> None:
        mode = self._mode_combo.currentData()
        source = self._source_combo.currentData()
        if source is None:
            kind = {MODE_CAMERA: "camera", MODE_SCREEN: "screen"}.get(mode, "DeskRecorder feature")
            self._own_status.setText(f"No {kind} available.")
            return
        if mode == MODE_RECORDER:
            self._start_recorder_mirror()
        else:
            self._start_independent_capture(mode, source)
        self._active = True
        self._mode_combo.setEnabled(False)
        self._source_combo.setEnabled(False)
        self._toggle_button.setText("Stop")
        self._update_own_status()

    def _start_independent_capture(self, mode: str, source) -> None:
        if mode == MODE_CAMERA:
            camera = QCamera(source, self)
            camera.errorOccurred.connect(self._on_capture_error)
            camera.activeChanged.connect(self._on_active_changed)
            self._session.setCamera(camera)
            self._camera = camera
            camera.start()
        else:
            screen_capture = QScreenCapture(self)
            screen_capture.setScreen(source)
            screen_capture.errorOccurred.connect(self._on_capture_error)
            screen_capture.activeChanged.connect(self._on_active_changed)
            self._session.setScreenCapture(screen_capture)
            self._screen_capture = screen_capture
            screen_capture.start()

        # Confirmed directly: a denied macOS camera/screen permission
        # doesn't reach QCamera/QScreenCapture's own errorOccurred signal
        # or error() property at all here (both stay NoError) -- it just
        # silently never goes active, leaving "Starting..." on screen
        # forever with no explanation. `_start_token` invalidates this
        # check if stop()/a mode switch/another start() happened first.
        # Not relevant to MODE_RECORDER -- no OS permission is involved
        # in polling RecorderService, so this check never runs for it.
        #
        # A child QTimer(self), not QTimer.singleShot(ms, lambda) --
        # confirmed directly that a bare singleShot lambda capturing
        # `self` isn't tied to this widget's own lifetime at all and
        # fires (RuntimeError: wrapped C/C++ object ... has been
        # deleted) even after the widget's already been torn down.
        # Parented here, Qt disconnects/destroys it along with this
        # widget the same safe way `self._recorder_timer` already is.
        self._start_token += 1
        token = self._start_token
        grace_timer = QTimer(self)
        grace_timer.setSingleShot(True)
        grace_timer.timeout.connect(lambda: self._check_startup_stalled(token))
        grace_timer.start(STARTUP_GRACE_MS)

    def _start_recorder_mirror(self) -> None:
        # TODO d95a323: no QCamera/QScreenCapture at all in this mode --
        # just poll RecorderService.latest_preview(feature), so no OS
        # permission prompt is involved for this widget in this mode.
        self._last_preview_b64 = None
        self._preview_poll_timer.start()
        self._poll_preview_frame()  # show whatever's already latest, don't wait a full interval

    def _poll_preview_frame(self) -> None:
        if self._recorder_service is None:
            return
        feature = self._source_combo.currentData()
        encoded = self._recorder_service.latest_preview(feature)
        if encoded is None or encoded == self._last_preview_b64:
            return
        self._last_preview_b64 = encoded
        try:
            raw = base64.b64decode(encoded)
        except (ValueError, TypeError):
            return
        image = QImage.fromData(raw, "JPEG")
        if not image.isNull():
            self._surface.show_image(image)

    def _check_startup_stalled(self, token: int) -> None:
        if token != self._start_token or not self._active:
            return
        live = (self._camera is not None and self._camera.isActive()) or (
            self._screen_capture is not None and self._screen_capture.isActive()
        )
        if not live:
            kind = "Camera" if self._camera is not None else "Screen Recording"
            self._own_status.setText(
                f"Not starting -- check {kind} permission in System Settings > Privacy & Security."
            )

    def _stop(self) -> None:
        # Parented to `self` (for deterministic teardown order -- see
        # the module docstring's own teardown comment), so dropping the
        # Python reference alone wouldn't release it: a repeated
        # start/stop/switch-source cycle would otherwise leak one
        # QCamera/QScreenCapture per cycle until this whole widget
        # closes. deleteLater() explicitly instead.
        if self._camera is not None:
            self._camera.stop()
            self._session.setCamera(None)
            self._camera.deleteLater()
            self._camera = None
        if self._screen_capture is not None:
            self._screen_capture.stop()
            self._session.setScreenCapture(None)
            self._screen_capture.deleteLater()
            self._screen_capture = None
        self._preview_poll_timer.stop()
        self._last_preview_b64 = None
        self._surface.clear()
        self._active = False
        self._mode_combo.setEnabled(True)
        self._source_combo.setEnabled(True)
        self._toggle_button.setText("Start")
        self._update_own_status()

    def _on_active_changed(self, _active: bool) -> None:
        self._update_own_status()

    def _on_capture_error(self, _error, error_string: str) -> None:
        logger.error("Video Preview capture error: %s", error_string)
        self._own_status.setText(f"Error: {error_string}")

    def _update_own_status(self) -> None:
        if not self._active:
            self._own_status.setText("Off")
            return
        if self._mode_combo.currentData() == MODE_RECORDER:
            # No OS "active" concept to check here -- we're just polling.
            # If DeskRecorder itself isn't actually recording this
            # feature, the DeskRecorder status line alongside this one
            # already says so; this just confirms our own poll is armed.
            self._own_status.setText("Live")
            return
        live = (self._camera is not None and self._camera.isActive()) or (
            self._screen_capture is not None and self._screen_capture.isActive()
        )
        self._own_status.setText("Live" if live else "Starting...")

    def _status_feature(self) -> str:
        """Which DeskRecorder feature ("screen"/"camera") the status line
        and (in MODE_RECORDER) the preview poll itself are about. For the
        two independent-capture modes this happens to equal the mode
        string itself; MODE_RECORDER's own analogous feature is instead
        whichever one the *source* combo currently selects (its mode
        string, "recorder", is never itself a DeskRecorder feature name)."""
        mode = self._mode_combo.currentData()
        return self._source_combo.currentData() if mode == MODE_RECORDER else mode

    # -- DeskRecorder's own status, polled (TODO this project's own
    # RecorderService.add_listener fires from a reader thread, not the
    # GUI thread -- widgets/recorder/widget.py already sidesteps that by
    # polling on a QTimer instead of subscribing directly; same here) --

    def _poll_recorder_status(self) -> None:
        if self._recorder_service is None:
            self._recorder_status.setText("DeskRecorder: unavailable")
            return
        feature = self._status_feature()
        if feature is None:
            self._recorder_status.setText("DeskRecorder: n/a")
            return
        state = self._recorder_service.feature_status(feature).get("state", "idle")
        text = RECORDER_STATE_TEXT.get(state, state)
        self._recorder_status.setText(f"DeskRecorder ({feature}): {text}")

    # -- widget-local storage -- same shape as the Video Player widget's
    # own (desk_widgets/video_player/widget.py), so each placed instance
    # remembers its own last-picked mode/source independently. Also
    # persists/restores whether it was actively previewing -- matching
    # Video Player's own `was_playing`-on-reload resume -- so a plain
    # Desk reload doesn't silently drop back to "Off" and need a manual
    # Start click again.
    def get_widget_local_storage(self) -> dict:
        mode = self._mode_combo.currentData()
        source = self._source_combo.currentData()
        if source is None:
            source_key = None
        elif mode == MODE_CAMERA:
            source_key = bytes(source.id()).decode("utf-8", "replace")
        elif mode == MODE_SCREEN:
            source_key = source.name()
        else:  # MODE_RECORDER -- source is already a plain "screen"/"camera" string
            source_key = source
        return {"mode": mode, "source": source_key, "active": self._active}

    def set_widget_local_storage(self, data: dict) -> None:
        mode = data.get("mode")
        if mode not in MODES:
            return
        source = data.get("source")
        self._set_mode(mode, populate_source=True, select_source=source)
        if data.get("active"):
            self._start()


def build() -> QWidget:
    return VideoPreviewWidget()
