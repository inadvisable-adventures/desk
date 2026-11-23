"""The three DeskRecorder features (TODO b9689cd): transcription, screen
recording and camera video. Each is independent: its own permission, its
own start/stop and state, and a failure in one never touches another.

A feature talks to Desk only through `send(name, *fields)` (a thread-safe
callable that writes a protocol line) and runs its Qt objects on the main
thread. `run_on_main(fn)` is how a worker thread hands work back.
"""
import os
import queue
import threading
import time
import wave
from pathlib import Path
from typing import Callable

import numpy as np
from PyQt6.QtCore import QObject, QTimer, QUrl
from PyQt6.QtMultimedia import (
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

Send = Callable[..., None]
RunOnMain = Callable[[Callable[[], None]], None]

# Test hooks (never set in normal use): feed transcription from a WAV file in
# real time instead of the microphone, and use a stub instead of whisper.
FAKE_AUDIO_ENV = "DESK_RECORDER_FAKE_AUDIO"
FAKE_TRANSCRIBER_ENV = "DESK_RECORDER_FAKE_TRANSCRIBER"

SCREEN_DENIED_MESSAGE = (
    "Screen Recording is not allowed for DeskRecorder. Allow it in System Settings > Privacy & Security > "
    "Screen Recording, then quit and reopen DeskRecorder (macOS only applies it after a restart)."
)


class StubTranscriber:
    """`seconds of audio -> 'utterance <n> (<s>s)'`, for tests."""

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

    def _on_frame(self, _frame) -> None:
        now = time.monotonic()
        if self._last_frame and now - self._last_frame > 0.1:
            self._stalls += 1  # a gap of over 100 ms between frames: a visible hitch
        self._last_frame = now

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
