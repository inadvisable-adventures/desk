"""MicRecorder (TODO fe7d8f2): the mic-capture-and-transcribe pipeline
shared by widgets/voice_input/widget.py (TODO b32fb81) and
widgets/claude_desk/widget.py (TODO a596dbf) -- widget directories
can't import each other, so this lives in desk. proper, the same
"shared widget logic lives in desk. proper" pattern
desk.terminal_widget/desk.claude_session already established.

Owns capture + transcription only, no UI at all -- each widget builds
its own record-button/status presentation on top, driven by this
class's signals."""
import os
import tempfile
import threading
import wave
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices

from desk.speech import (
    EXPECTED_SAMPLE_RATE,
    TranscriptionResult,
    TranscriptionUnavailableError,
    transcribe,
)


def _write_wav(pcm_bytes: bytes) -> Path:
    fd, path_str = tempfile.mkstemp(prefix="desk-voice-input-", suffix=".wav")
    os.close(fd)  # wave.open(path) below reopens it -- the fd from mkstemp is only for a race-free unique name
    path = Path(path_str)
    with wave.open(path_str, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(EXPECTED_SAMPLE_RATE)
        wav_file.writeframes(pcm_bytes)
    return path


def _transcribe_in_background(wav_path: Path, recorder: "MicRecorder") -> None:
    """Module-level, not a method: runs on a background thread and must
    not touch any Qt widget directly -- only ever reports back via
    recorder's own signal, same reasoning as
    widgets/git_status/widget.py's _run_git_status."""
    try:
        result: TranscriptionResult | None = transcribe(wav_path)
        error: str | None = None
    except TranscriptionUnavailableError as exc:
        result = None
        error = str(exc)
    except Exception as exc:  # noqa: BLE001 -- surfaced to the caller, not swallowed
        result = None
        error = f"Transcription failed: {exc}"
    finally:
        wav_path.unlink(missing_ok=True)
    recorder.transcription_finished.emit(result, error)


class MicRecorder(QObject):
    """One recording-and-transcription cycle at a time. Signals are
    emitted from whichever thread is relevant at the time (mostly the
    GUI thread, except transcription_finished, which fires from the
    background transcription thread) -- PyQt6 auto-queues delivery onto
    whichever thread each connected slot's receiver lives on, the same
    guarantee every other _Relay-shaped class in this codebase already
    relies on."""

    recording_started = pyqtSignal()
    # Fires once real capture stops, before transcription begins -- lets
    # a caller show a "Transcribing..." status distinct from
    # "Recording...".
    recording_stopped = pyqtSignal()
    transcription_finished = pyqtSignal(object, object)  # TranscriptionResult | None, error: str | None
    # A real problem starting a recording (no mic, unsupported format)
    # -- distinct from transcription_finished's error, which only
    # happens after a real recording attempt.
    error = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._audio_source: QAudioSource | None = None
        self._audio_io = None
        self._captured_chunks: list[bytes] = []

    def is_recording(self) -> bool:
        return self._audio_source is not None

    def start(self) -> None:
        fmt = QAudioFormat()
        fmt.setSampleRate(EXPECTED_SAMPLE_RATE)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)

        device = QMediaDevices.defaultAudioInput()
        if device.isNull():
            self.error.emit("No microphone found.")
            return
        if not device.isFormatSupported(fmt):
            self.error.emit("Default microphone does not support 16kHz mono 16-bit capture.")
            return

        self._captured_chunks = []
        self._audio_source = QAudioSource(device, fmt, self)
        self._audio_io = self._audio_source.start()
        self._audio_io.readyRead.connect(self._on_audio_ready_read)
        self.recording_started.emit()

    def _on_audio_ready_read(self) -> None:
        if self._audio_io is None:
            return
        data = bytes(self._audio_io.readAll())
        if data:
            self._captured_chunks.append(data)

    def stop(self) -> None:
        assert self._audio_source is not None
        self._audio_source.stop()
        self._audio_source = None
        self._audio_io = None
        self.recording_stopped.emit()
        self._process_captured_audio()

    def _process_captured_audio(self) -> None:
        """Split out from stop() so tests can exercise the
        write-WAV -> background-transcribe -> transcription_finished
        pipeline against known, injected PCM data (e.g. real macOS
        `say`-synthesized speech) without depending on what a real
        microphone happens to pick up during an automated test run --
        set self._captured_chunks directly, then call this."""
        pcm_bytes = b"".join(self._captured_chunks)
        self._captured_chunks = []
        if not pcm_bytes:
            self.error.emit("No audio captured.")
            return

        wav_path = _write_wav(pcm_bytes)
        thread = threading.Thread(target=_transcribe_in_background, args=(wav_path, self), daemon=True)
        thread.start()
