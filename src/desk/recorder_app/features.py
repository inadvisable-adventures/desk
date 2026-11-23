"""The four DeskRecorder features (TODO b9689cd): transcription, screen
recording, camera video and standalone microphone audio. Each is
independent: its own permission, its own start/stop and state, and a
failure in one never touches another.

A feature talks to Desk only through `send(name, *fields)` (a thread-safe
callable that writes a protocol line) and runs its Qt objects on the main
thread. `run_on_main(fn)` is how a worker thread hands work back.
"""
import base64
import os
import queue
import threading
import time
import wave
from pathlib import Path
from typing import Callable

import numpy as np
from PyQt6.QtCore import QBuffer, QIODeviceBase, QObject, Qt, QTimer, QUrl
from PyQt6.QtMultimedia import (
    QAudio,
    QAudioDevice,
    QAudioFormat,
    QAudioInput,
    QAudioSource,
    QCamera,
    QMediaCaptureSession,
    QMediaDevices,
    QMediaFormat,
    QMediaRecorder,
    QScreenCapture,
    QVideoSink,
    QWindowCapture,
)
from PyQt6.QtGui import QGuiApplication

from desk import transcript_pool
from desk.recorder_app import permissions
from desk.recorder_app.segmenter import SAMPLE_RATE, Job, UtteranceSegmenter
from desk.recorder_app.transcriber import Phrase, Transcriber
from desk.recorder_protocol import unquote_token

Send = Callable[..., None]
RunOnMain = Callable[[Callable[[], None]], None]

# Test hooks (never set in normal use): feed transcription from a WAV file in
# real time instead of the microphone, and use a stub instead of whisper.
FAKE_AUDIO_ENV = "DESK_RECORDER_FAKE_AUDIO"
FAKE_TRANSCRIBER_ENV = "DESK_RECORDER_FAKE_TRANSCRIBER"

LEVEL_INTERVAL_SECONDS = 0.1  # ~10/s: plenty for a meter, cheap on the socket

SCREEN_DENIED_MESSAGE = (
    "Screen Recording is not allowed for DeskRecorder. Allow it in System Settings > Privacy & Security > "
    "Screen Recording, then quit and reopen DeskRecorder (macOS only applies it after a restart)."
)

# TODO d95a323: `preview-frame` tuning -- low-fps/small/lossy on purpose.
# The protocol is plain, buffered-on-newline text (see recorder_protocol.py's
# own docstring); a few-KB base64 JPEG per line needs no new framing, a full
# raw frame stream at recording fps/resolution would.
PREVIEW_INTERVAL_SECONDS = 0.5  # ~2 fps
PREVIEW_MAX_WIDTH = 320
PREVIEW_JPEG_QUALITY = 60


class StubTranscriber:
    """`seconds of audio -> 'utterance <n> (<s>s)'`, for tests. Returns one
    `Phrase` spanning the whole chunk -- real whisper would return several,
    but nothing here depends on sub-chunking."""

    def __init__(self) -> None:
        self.count = 0

    def load(self) -> None:
        pass

    def transcribe(self, audio: np.ndarray) -> list[Phrase]:
        self.count += 1
        duration = len(audio) / SAMPLE_RATE
        return [Phrase(text=f"utterance {self.count} ({duration:.1f}s)", start_s=0.0, end_s=duration)]


class Feature(QObject):
    name = ""

    def __init__(self, send: Send, run_on_main: RunOnMain) -> None:
        super().__init__()
        self.send = send
        self.run_on_main = run_on_main
        self.state = "idle"

    def set_state(self, state: str, detail: str = "") -> None:
        self.state = state
        self.send("state", self.name, state, detail)

    def fail(self, reason: str) -> None:
        self.state = "error"
        self.send("error", self.name, reason)

    def ask(self, needed: list[str], then: Callable[[dict[str, str]], None]) -> None:
        """Requests permissions off the main thread (a prompt can wait for
        the user, and the heartbeat must keep going), then runs
        `then(results)` on the main thread."""

        def work() -> None:
            results = {name: permissions.request(name) for name in needed}
            self.run_on_main(lambda: then(results))

        threading.Thread(target=work, daemon=True, name=f"permission-{self.name}").start()

    def busy(self) -> bool:
        return self.state in ("starting", "running", "stopping")

    def stop(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def shutdown(self) -> None:
        if self.busy():
            self.stop()


# --- transcription -------------------------------------------------------


class _WavSource(QObject):
    """Test hook: plays a 16 kHz mono WAV into `on_audio` at real-time pace."""

    def __init__(self, path: str, on_audio: Callable[[bytes], None], on_end: Callable[[], None]) -> None:
        super().__init__()
        with wave.open(path, "rb") as wav:
            self._data = wav.readframes(wav.getnframes())
        self._pos = 0
        self._on_audio = on_audio
        self._on_end = on_end
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        self._timer.start(100)

    def _tick(self) -> None:
        chunk = self._data[self._pos : self._pos + 3200]  # 100 ms
        self._pos += len(chunk)
        if chunk:
            self._on_audio(chunk)
        if self._pos >= len(self._data):
            self._timer.stop()
            self._on_end()

    def stop(self) -> None:
        self._timer.stop()


class _MicSource(QObject):
    def __init__(self, on_audio: Callable[[bytes], None]) -> None:
        super().__init__()
        fmt = QAudioFormat()
        fmt.setSampleRate(SAMPLE_RATE)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        self._source = QAudioSource(QMediaDevices.defaultAudioInput(), fmt)
        self._io = None
        self._on_audio = on_audio

    def start(self) -> None:
        self._io = self._source.start()
        self._io.readyRead.connect(lambda: self._on_audio(bytes(self._io.readAll())))

    def stop(self) -> None:
        self._source.stop()


class TranscribeFeature(Feature):
    name = "transcribe"

    def __init__(self, send: Send, run_on_main: RunOnMain) -> None:
        super().__init__(send, run_on_main)
        self._segmenter: UtteranceSegmenter | None = None
        self._source = None
        self._jobs: "queue.Queue[Job | None]" = queue.Queue()
        self._worker: threading.Thread | None = None
        self._transcriber = None
        self._session = ""
        self._pool = Path(".")
        self._t0_ms = 0

    def start(self, session: str, pool_dir: str) -> None:
        if self.busy():
            return
        self._session, self._pool = session, Path(pool_dir)
        self.set_state("starting", "waiting for microphone permission")
        self.ask(["microphone"], lambda results: self._after_permission(results["microphone"]))

    def _after_permission(self, result: str) -> None:
        if result != "granted":
            self.set_state("denied", "Microphone access is not allowed for DeskRecorder (System Settings > Privacy & Security > Microphone).")
            return
        self.set_state("starting", "loading the speech model")

        def load() -> None:
            try:
                transcriber = StubTranscriber() if os.environ.get(FAKE_TRANSCRIBER_ENV) else Transcriber()
                transcriber.load()
            except Exception as e:  # noqa: BLE001 -- reported to Desk, not swallowed
                self.run_on_main(lambda: self.fail(f"could not load the speech model: {e}"))
                return
            self.run_on_main(lambda: self._begin(transcriber))

        threading.Thread(target=load, daemon=True, name="whisper-load").start()

    def _begin(self, transcriber) -> None:
        if self.state != "starting":
            return  # stopped while loading
        self._transcriber = transcriber
        self._segmenter = UtteranceSegmenter()
        self._jobs = queue.Queue()
        self._worker = threading.Thread(target=self._work, daemon=True, name="whisper-worker")
        self._worker.start()
        fake = os.environ.get(FAKE_AUDIO_ENV)
        try:
            self._source = _WavSource(fake, self._on_audio, self._on_audio_end) if fake else _MicSource(self._on_audio)
            self._t0_ms = int(time.time() * 1000)
            self._source.start()
        except Exception as e:  # noqa: BLE001
            self.fail(f"could not start the microphone: {e}")
            self._jobs.put(None)
            return
        self.state = "running"
        self.send("started", self.name)

    def _on_audio(self, data: bytes) -> None:
        if self._segmenter is None or not data:
            return
        samples = np.frombuffer(data[: len(data) // 2 * 2], dtype=np.int16).astype(np.float32) / 32768.0
        for job in self._segmenter.feed(samples):
            self._jobs.put(job)

    def _on_audio_end(self) -> None:
        if self.state == "running":
            self.stop()

    def _work(self) -> None:
        seg = self._segmenter
        while True:
            job = self._jobs.get()
            if job is None:
                break
            if job.kind == "provisional" and not self._jobs.empty():
                continue  # busy: a provisional is only a preview, drop it
            try:
                phrases = self._transcriber.transcribe(job.audio)
            except Exception as e:  # noqa: BLE001
                self.send("error", self.name, f"transcription failed: {e}")
                continue
            if not phrases:
                continue
            start_ms = seg.sample_to_ms(job.start_sample, self._t0_ms)
            end_ms = seg.sample_to_ms(job.end_sample, self._t0_ms)
            text = " ".join(p.text for p in phrases)
            # `start_ms` is this chunk's own epoch anchor (sample 0 of
            # `job.audio`); each phrase's start_s/end_s is whisper's own
            # offset into that same chunk, so adding them gives every
            # phrase its own accurate wall-clock stamp instead of every
            # phrase in the utterance sharing one span (TODO: transcript
            # sync drift investigation).
            parts = tuple(
                transcript_pool.Part(
                    text=p.text,
                    start_ms=start_ms + round(p.start_s * 1000),
                    end_ms=start_ms + round(p.end_s * 1000),
                )
                for p in phrases
            )
            final = job.kind == "final"
            transcript_pool.append_segment(
                self._pool, transcript_pool.Segment(self._session, job.seq, start_ms, end_ms, text, final, parts)
            )
            if final:
                self.send("final", self._session, str(start_ms), str(end_ms), text.replace("\n", " "))
        self.run_on_main(self._finished)

    def _finished(self) -> None:
        self._source = None
        self._segmenter = None
        self.state = "idle"
        self.send("stopped", self.name, "-")

    def stop(self) -> None:
        if self.state == "starting":
            self.state = "idle"  # _begin sees this and does nothing
            self.send("stopped", self.name, "-")
            return
        if self.state != "running":
            return
        self.set_state("stopping")
        self._source.stop()
        for job in self._segmenter.flush():
            self._jobs.put(job)
        self._jobs.put(None)  # the worker drains the queue, then reports `stopped`


# --- screen and camera video ----------------------------------------------


class VideoFeature(Feature):
    """Shared recorder plumbing: one capture session -> one MP4."""

    needs: list[str] = []

    def __init__(self, send: Send, run_on_main: RunOnMain) -> None:
        super().__init__(send, run_on_main)
        self._session: QMediaCaptureSession | None = None
        self._recorder: QMediaRecorder | None = None
        self._source = None
        self._audio = None
        self._sink: QVideoSink | None = None
        self._path = ""
        self._last_frame = 0.0
        self._last_preview_sent = 0.0
        self._first_frame_ms: int | None = None
        self._stalls = 0
        self._report_timer: QTimer | None = None
        self._state_timer: QTimer | None = None
        self._finalize_timer: QTimer | None = None

    # subclasses
    def _make_source(self, args: str):  # returns (source, error_message_or_None)
        raise NotImplementedError

    def _attach(self, session: QMediaCaptureSession, source) -> None:
        raise NotImplementedError

    def _wants_audio(self) -> bool:
        return False

    def start(self, args: str, path: str) -> None:
        if self.busy():
            return
        self._args, self._path = args, path
        self.set_state("starting", "waiting for permission")
        self.ask(list(self.needs) + (["microphone"] if self._wants_audio() else []), self._after_permission)

    def _after_permission(self, results: dict[str, str]) -> None:
        for permission in self.needs:
            if results.get(permission) != "granted":
                self.set_state("denied", self._denial_message(permission, results[permission]))
                return
        mic = results.get("microphone") == "granted"
        source, error = self._make_source(self._args)
        if error:
            self.fail(error)
            return
        self._source = source
        self._session = QMediaCaptureSession()
        self._attach(self._session, source)
        if mic:
            self._audio = QAudioInput(QMediaDevices.defaultAudioInput())
            self._session.setAudioInput(self._audio)
        self._sink = QVideoSink()
        self._sink.videoFrameChanged.connect(self._on_frame)
        self._session.setVideoSink(self._sink)
        recorder = QMediaRecorder()
        fmt = QMediaFormat(QMediaFormat.FileFormat.MPEG4)
        fmt.setVideoCodec(QMediaFormat.VideoCodec.H264)
        if mic:
            fmt.setAudioCodec(QMediaFormat.AudioCodec.AAC)
        recorder.setMediaFormat(fmt)
        recorder.setQuality(QMediaRecorder.Quality.NormalQuality)
        self._session.setRecorder(recorder)
        recorder.setOutputLocation(QUrl.fromLocalFile(self._path))
        recorder.errorChanged.connect(lambda: self._on_recorder_error(recorder))
        self._recorder = recorder
        self._stalls = 0
        self._last_frame = 0.0
        self._last_preview_sent = 0.0
        self._first_frame_ms = None
        self._source.errorOccurred.connect(lambda *a: self._on_source_error(a[-1] if a else "capture error"))
        self._start_source()
        recorder.record()
        # PyQt cannot connect recorderStateChanged to a Python callable (its
        # enum argument has no metatype), so the state is polled.
        self._state_timer = QTimer(self)
        self._state_timer.timeout.connect(self._poll_recorder_state)
        self._state_timer.start(100)
        self._report_timer = QTimer(self)
        self._report_timer.timeout.connect(lambda: self.send("dropped", self.name, str(self._stalls)))
        self._report_timer.start(2000)

    def _start_source(self) -> None:
        self._source.start()

    def _denial_message(self, permission: str, result: str) -> str:
        if permission == "screen":
            return SCREEN_DENIED_MESSAGE
        return "Camera access is not allowed for DeskRecorder (System Settings > Privacy & Security > Camera)."

    def _on_frame(self, frame) -> None:
        if self._first_frame_ms is None:
            # TODO (transcript sync drift): the first frame actually
            # reaching this QVideoSink -- the same session the
            # QMediaRecorder is encoding -- is the one real, measured
            # wall-clock moment "recording started" exists for this
            # feature. Everything before this (permission prompt,
            # QMediaRecorder.record() being called, the output file being
            # created) can take an unpredictable extra beat on top, so the
            # file's own birthtime is only a guess at this timestamp, not
            # a measurement of it. Recorded here and handed to whoever
            # composites captions onto the video later (compositor.py's
            # `recording_start_epoch_ms`) via a sidecar file next to the
            # output, since this app and that job never run at the same
            # time and share no other channel.
            self._first_frame_ms = int(time.time() * 1000)
            self._write_frame0_sidecar()
        now = time.monotonic()
        if self._last_frame and now - self._last_frame > 0.1:
            self._stalls += 1  # a gap of over 100 ms between frames: a visible hitch
        self._last_frame = now
        if now - self._last_preview_sent >= PREVIEW_INTERVAL_SECONDS:
            self._last_preview_sent = now
            self._send_preview(frame)

    def _write_frame0_sidecar(self) -> None:
        """Best-effort: a missing sidecar just means whoever composites
        this recording falls back to the birthtime guess."""
        try:
            Path(f"{self._path}.frame0_ms").write_text(str(self._first_frame_ms), encoding="utf-8")
        except OSError:
            pass

    def _send_preview(self, frame) -> None:
        """TODO d95a323: a low-fps JPEG snapshot of this feature's own
        `QVideoSink` -- the exact frames this session is already handing
        to its `QMediaRecorder` -- sent to Desk over the existing control
        socket so a widget can show a live-ish preview without opening a
        second, independent camera/screen session of its own (which, in
        Desk's own process, hits the exact permission problem this whole
        app was built to solve -- see plans/deskrecorder-live-preview-frames.md)."""
        image = frame.toImage()
        if image.isNull():
            return
        if image.width() > PREVIEW_MAX_WIDTH:
            image = image.scaledToWidth(PREVIEW_MAX_WIDTH, Qt.TransformationMode.SmoothTransformation)
        buffer = QBuffer()
        buffer.open(QIODeviceBase.OpenModeFlag.WriteOnly)
        if not image.save(buffer, "JPEG", PREVIEW_JPEG_QUALITY):
            buffer.close()
            return
        encoded = base64.b64encode(bytes(buffer.data())).decode("ascii")
        buffer.close()
        self.send("preview-frame", self.name, encoded)

    def _on_source_error(self, message: str) -> None:
        if self.state in ("starting", "running"):
            self._teardown()
            self.fail(str(message))

    def _on_recorder_error(self, recorder: QMediaRecorder) -> None:
        if recorder.error() != QMediaRecorder.Error.NoError and self.state in ("starting", "running"):
            message = recorder.errorString() or "recorder error"
            self._teardown()
            self.fail(message)

    def _poll_recorder_state(self) -> None:
        if self._recorder is None:
            return
        state = self._recorder.recorderState()
        if state == QMediaRecorder.RecorderState.RecordingState and self.state == "starting":
            self.state = "running"
            self.send("started", self.name)
        elif state == QMediaRecorder.RecorderState.StoppedState and self.state == "stopping":
            self._finish_stop()

    def stop(self) -> None:
        if self.state == "starting" and self._recorder is None:
            self.state = "idle"
            self.send("stopped", self.name, "-")
            return
        if self.state not in ("running", "starting") or self._recorder is None:
            return
        self.set_state("stopping")
        self._recorder.stop()
        # The recorder finalizes the file asynchronously; don't wait forever.
        self._finalize_timer = QTimer(self)
        self._finalize_timer.setSingleShot(True)
        self._finalize_timer.timeout.connect(lambda: self.state == "stopping" and self._finish_stop())
        self._finalize_timer.start(10000)

    def _finish_stop(self) -> None:
        self._teardown()
        self.state = "idle"
        self.send("stopped", self.name, self._path if Path(self._path).exists() else "-")

    def _teardown(self) -> None:
        for timer in (self._report_timer, self._finalize_timer, self._state_timer):
            if timer is not None:
                timer.stop()
        self._report_timer = self._finalize_timer = self._state_timer = None
        if self._source is not None:
            try:
                self._source.stop()
            except Exception:  # noqa: BLE001
                pass
        self._recorder = self._session = self._source = self._audio = self._sink = None


class ScreenFeature(VideoFeature):
    name = "screen"
    needs = ["screen"]

    def _wants_audio(self) -> bool:
        return True  # a microphone track, when the microphone is allowed

    def _make_source(self, args: str):
        from desk.recorder_protocol import unquote_token

        if args == "screen":
            capture = QScreenCapture()
            capture.setScreen(QGuiApplication.primaryScreen())
            return capture, None
        title = unquote_token(args[len("window:") :]) if args.startswith("window:") else unquote_token(args)
        for window in QWindowCapture.capturableWindows():
            if title.lower() in window.description().lower():
                capture = QWindowCapture()
                capture.setWindow(window)
                return capture, None
        return None, f"no window matching {title!r}"

    def _attach(self, session: QMediaCaptureSession, source) -> None:
        if isinstance(source, QScreenCapture):
            session.setScreenCapture(source)
        else:
            session.setWindowCapture(source)


class CameraFeature(VideoFeature):
    name = "camera"
    needs = ["camera"]

    def _make_source(self, args: str):
        from desk.recorder_protocol import unquote_token

        devices = QMediaDevices.videoInputs()
        if not devices:
            return None, "no camera found"
        device = devices[0] if args == "default" else None
        wanted = unquote_token(args)
        if device is None:
            device = next((d for d in devices if wanted.lower() in d.description().lower()), None)
        if device is None:
            return None, f"no camera matching {wanted!r}"
        if args == "default":
            device = QMediaDevices.defaultVideoInput()
        return QCamera(device), None

    def _attach(self, session: QMediaCaptureSession, source) -> None:
        session.setCamera(source)


# --- standalone microphone audio -------------------------------------------


def _resolve_audio_device(selector: str) -> QAudioDevice | None:
    """`"default"` or a `quote_token`-quoted device description, the same
    shape `CameraFeature._make_source`'s `device` argument already uses --
    kept separate rather than shared with it since that one is tangled up
    with `QCamera` construction, not just device lookup."""
    devices = QMediaDevices.audioInputs()
    if selector in ("", "default"):
        default = QMediaDevices.defaultAudioInput()
        return None if default.isNull() else default
    wanted = unquote_token(selector)
    return next((d for d in devices if wanted.lower() in d.description().lower()), None)


# Qt's four sample formats -> (numpy dtype, zero point, scale to [-1, 1]).
# AudioFeature's WAV output is always mono 16-bit regardless of what a real
# input device's own native format turns out to be (a USB interface like a
# Zoom H6 is routinely multi-channel and/or not Int16 at all) -- this is
# the one place that has to know all four, so the WAV writer and level
# meter can both just deal in normalized mono float32.
_SAMPLE_DECODERS = {
    QAudioFormat.SampleFormat.UInt8: (np.uint8, 128.0, 127.0),
    QAudioFormat.SampleFormat.Int16: (np.int16, 0.0, 32768.0),
    QAudioFormat.SampleFormat.Int32: (np.int32, 0.0, 2147483648.0),
    QAudioFormat.SampleFormat.Float: (np.float32, 0.0, 1.0),
}


def _decode_to_mono_float32(data: bytes, fmt: QAudioFormat) -> np.ndarray:
    """Raw bytes from a `QAudioSource` already opened with `fmt`, decoded
    to mono float32 in [-1, 1]."""
    decoder = _SAMPLE_DECODERS.get(fmt.sampleFormat())
    if decoder is None:
        return np.zeros(0, dtype=np.float32)
    dtype, zero, scale = decoder
    itemsize = np.dtype(dtype).itemsize
    usable = len(data) - (len(data) % itemsize)
    if usable <= 0:
        return np.zeros(0, dtype=np.float32)
    samples = (np.frombuffer(data[:usable], dtype=dtype).astype(np.float32) - zero) / scale
    channels = max(1, fmt.channelCount())
    if channels > 1:
        frames = len(samples) // channels
        if frames == 0:
            return np.zeros(0, dtype=np.float32)
        samples = samples[: frames * channels].reshape(frames, channels).mean(axis=1)
    return samples


class AudioFeature(Feature):
    """A standalone, timestamped microphone recording, independent of the
    mic use already elsewhere in this app: `TranscribeFeature`'s own mic
    capture is tuned for whisper (16 kHz, chunked for VAD, never saved to
    disk) and `ScreenFeature`'s embedded track is always whatever
    `QMediaDevices.defaultAudioInput()` happens to be, with no way to pick
    a different one. This feature exists so a specific input device (the
    widget's own audio-input picker, `desk.recorder_app.main`'s `sources`
    reply now including `microphone` entries) can be recorded on its own,
    straight to a WAV file at the device's own real native quality
    (typically 44.1-48 kHz) rather than whisper's phone-quality 16 kHz --
    always the device's own `preferredFormat()`, never a requested rate:
    confirmed directly that this platform's QAudioSource backend doesn't
    actually resample when asked for a different one, it just silently
    mislabels the native rate as whatever was requested (see
    `_after_permission`'s own comment for the measurement that caught
    this -- it was the real cause of a real recording sounding "static-y,
    like it's dropping samples").

    Timestamped the same way `VideoFeature`'s `frame0_ms` sidecar is: the
    wall-clock moment real audio data actually first arrives, written to
    `<path>.frame0_ms`, not the (earlier, approximate) moment
    `QAudioSource.start()` merely returns -- see that method's own
    docstring and `compositor.py`'s `recording_start_epoch_ms`, which
    reads either kind of sidecar the same way.

    Also reports its live input level (`send("level", ...)`, 0.0-1.0,
    throttled to `LEVEL_INTERVAL_SECONDS`) for the widget's meter."""

    name = "audio"

    def __init__(self, send: Send, run_on_main: RunOnMain) -> None:
        super().__init__(send, run_on_main)
        self._device_selector = "default"
        self._path = ""
        self._source: QAudioSource | None = None
        self._io = None
        self._wav: wave.Wave_write | None = None
        self._first_sample_ms: int | None = None
        self._last_level_sent = 0.0
        self._error_timer: QTimer | None = None
        self._input_format: QAudioFormat | None = None

    def start(self, device: str, path: str) -> None:
        if self.busy():
            return
        self._device_selector, self._path = device, path
        self.set_state("starting", "waiting for microphone permission")
        self.ask(["microphone"], lambda results: self._after_permission(results["microphone"]))

    def _after_permission(self, result: str) -> None:
        if self.state != "starting":
            return  # stopped while waiting for permission
        if result != "granted":
            self.set_state(
                "denied",
                "Microphone access is not allowed for DeskRecorder (System Settings > Privacy & Security > "
                "Microphone).",
            )
            return
        audio_device = _resolve_audio_device(self._device_selector)
        if audio_device is None:
            self.fail(f"no microphone matching {self._device_selector!r}")
            return
        # Always the device's own native format -- never ask for a
        # specific sample rate (AUDIO_TRACK_SAMPLE_RATE doesn't exist
        # anymore; this used to try mono/Int16/44100 first and fall back
        # to preferredFormat() only if `isFormatSupported()` said no).
        # Confirmed directly, against this machine's real built-in mic:
        # `isFormatSupported(44100 Int16 mono)` reports True, `start()`
        # reports `format().sampleRate() == 44100`, but the real delivery
        # rate -- measured by counting bytes actually received over a
        # precisely-timed 5-second window -- was ~49976 Hz, i.e. the
        # mic's true native 48000 Hz, just mislabeled as 44100. Writing
        # that into a WAV declared as 44100 Hz is exactly a ~9% pitch/
        # speed mismatch baked into the file, which is what "static-y,
        # like it's dropping samples" was: not real data loss, but
        # Qt's own macOS/CoreAudio QAudioSource backend silently not
        # resampling when asked for a rate other than the hardware's
        # own, while still claiming success. Asking for `preferredFormat()`
        # unchanged and measuring the same way confirmed an honest,
        # accurate delivery rate (~47891 of a requested 48000, i.e. only
        # ordinary timing-loop slop) -- so that's the one rate this code
        # can actually trust. `_decode_to_mono_float32` below still has
        # to handle whatever channel count/sample format that turns out
        # to be (a device is routinely not mono Int16), but never a rate
        # *conversion* -- the WAV is written at this same, real rate.
        fmt = audio_device.preferredFormat()
        if (
            not fmt.isValid()
            or fmt.sampleRate() <= 0
            or fmt.channelCount() <= 0
            or fmt.sampleFormat() not in _SAMPLE_DECODERS
        ):
            self.fail(f"{audio_device.description()} has no audio format this can record")
            return
        try:
            wav = wave.open(self._path, "wb")
            wav.setnchannels(1)
            wav.setsampwidth(2)  # always mono 16-bit -- _on_audio downmixes/converts to this
            wav.setframerate(fmt.sampleRate())
        except OSError as e:
            self.fail(f"could not open {self._path}: {e}")
            return
        self._input_format = fmt
        self._first_sample_ms = None
        self._last_level_sent = 0.0
        try:
            source = QAudioSource(audio_device, fmt)
            io = source.start()
        except Exception as e:  # noqa: BLE001
            wav.close()
            self.fail(f"could not start the microphone: {e}")
            return
        if io is None:
            # QAudioSource.start() returning None -- rather than raising --
            # is how a real failure to open the device shows up (confirmed
            # against a real crash log: unchecked, the very next line
            # threw AttributeError inside a Qt-dispatched slot, which
            # PyQt6 cannot recover from -- qFatal() -> abort()).
            # `source.error()` is populated even though nothing was raised
            # -- surfaced here because, confirmed directly against a real
            # USB interface (every channel count/sample format/rate
            # combination it claims to support still failed identically
            # with CoreAudio's own "AudioOutputUnitStart failed"), this is
            # not a format problem this code can route around: it means
            # CoreAudio itself refused to start the device, almost always
            # because another app already has it open, or it is in an
            # exclusive-access mode.
            error_name = source.error().name
            try:
                source.stop()
            except Exception:  # noqa: BLE001
                pass
            wav.close()
            self.fail(
                f"could not open {audio_device.description()} ({error_name}) -- check whether another app "
                "already has this microphone open (another DAW, Audio MIDI Setup, a conferencing app, ...) "
                "and close it, then try again"
            )
            return
        self._wav, self._source, self._io = wav, source, io
        io.readyRead.connect(self._on_audio)
        # Unlike QScreenCapture/QWindowCapture/QCamera (VideoFeature's own
        # sources), QAudioSource has no errorOccurred signal at all -- just
        # a polled `error()` (same "PyQt6 won't deliver this one as a
        # signal" shape as QMediaRecorder's state, polled elsewhere in this
        # file for the same reason).
        self._error_timer = QTimer(self)
        self._error_timer.timeout.connect(self._poll_source_error)
        self._error_timer.start(200)
        self.state = "running"
        self.send("started", self.name)

    def _poll_source_error(self) -> None:
        if self._source is None or self.state != "running":
            return
        error = self._source.error()
        if error != QAudio.Error.NoError:
            self._on_source_error(str(error))

    def _on_audio(self) -> None:
        if self._io is None:
            return
        data = bytes(self._io.readAll())
        if not data:
            return
        if self._first_sample_ms is None:
            self._first_sample_ms = int(time.time() * 1000)
            self._write_frame0_sidecar()
        samples = _decode_to_mono_float32(data, self._input_format)
        if len(samples) == 0:
            return
        if self._wav is not None:
            pcm16 = (np.clip(samples, -1.0, 1.0) * 32767.0).astype(np.int16)
            try:
                self._wav.writeframes(pcm16.tobytes())
            except OSError:
                pass
        self._maybe_send_level(samples)

    def _maybe_send_level(self, samples: np.ndarray) -> None:
        now = time.monotonic()
        if now - self._last_level_sent < LEVEL_INTERVAL_SECONDS:
            return
        self._last_level_sent = now
        level = min(1.0, float(np.sqrt(np.mean(samples * samples))) * 4.0)  # RMS runs quiet; a flat gain reads better
        self.send("level", self.name, f"{level:.3f}")

    def _write_frame0_sidecar(self) -> None:
        """Best-effort: a missing sidecar just means whoever composites
        this recording falls back to its birthtime guess."""
        try:
            Path(f"{self._path}.frame0_ms").write_text(str(self._first_sample_ms), encoding="utf-8")
        except OSError:
            pass

    def _on_source_error(self, message: str) -> None:
        if self.state in ("starting", "running"):
            self._teardown()
            self.fail(str(message))

    def stop(self) -> None:
        if self.state == "starting":
            self.state = "idle"  # _after_permission sees this and does nothing
            self.send("stopped", self.name, "-")
            return
        if self.state != "running":
            return
        self.set_state("stopping")
        self._teardown()
        self.state = "idle"
        self.send("stopped", self.name, self._path if Path(self._path).exists() else "-")

    def _teardown(self) -> None:
        if self._error_timer is not None:
            self._error_timer.stop()
            self._error_timer = None
        if self._source is not None:
            try:
                self._source.stop()
            except Exception:  # noqa: BLE001
                pass
        if self._wav is not None:
            try:
                self._wav.close()
            except Exception:  # noqa: BLE001
                pass
        self._source = self._io = self._wav = None
