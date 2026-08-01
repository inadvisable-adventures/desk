"""Voice Input widget (TODO b32fb81): record from the microphone and
transcribe locally via desk.speech (mlx-whisper, TODO 1cd0ca2). See
PARKINGLOT.md's original "Local speech-to-text (Whisper) for voice
input" note and design-docs/whisper-model-setup.md for how the model
this depends on gets onto disk.

Deliberately a self-contained widget -- not wired into any other
widget's own text fields. See plans/voice-input-widget.md's "Scope
decision" for why.
"""
import os
import tempfile
import threading
import wave
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desk.speech import EXPECTED_SAMPLE_RATE, TranscriptionUnavailableError, transcribe

ERROR_STYLE = "color: #ff5c5c;"
STATUS_STYLE = "color: #9a9a9a;"


class _Relay(QObject):
    """Owns the pyqtSignal the background transcription thread reports
    through -- same shape as widgets/git_status/widget.py's own
    _Relay. Exactly one of text/error is not None."""

    finished = pyqtSignal(object, object)  # text: str | None, error: str | None


def _transcribe_in_background(wav_path: Path, relay: _Relay) -> None:
    """Module-level, not a method: runs on a background thread and must
    not touch any Qt widget directly -- only ever reports back via the
    relay's signal, same reasoning as widgets/git_status/widget.py's
    _run_git_status."""
    try:
        text: str | None = transcribe(wav_path)
        error: str | None = None
    except TranscriptionUnavailableError as exc:
        text = None
        error = str(exc)
    except Exception as exc:  # noqa: BLE001 -- surfaced to the user, not swallowed
        text = None
        error = f"Transcription failed: {exc}"
    finally:
        wav_path.unlink(missing_ok=True)
    relay.finished.emit(text, error)


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


class VoiceInputWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._audio_source: QAudioSource | None = None
        self._audio_io = None
        self._captured_chunks: list[bytes] = []

        self._record_button = QPushButton("● Record")
        self._record_button.clicked.connect(self._on_record_clicked)

        self._copy_button = QPushButton("Copy")
        self._copy_button.clicked.connect(self._on_copy_clicked)
        self._copy_button.setEnabled(False)

        self._status_label = QLabel("Idle.")
        self._status_label.setStyleSheet(STATUS_STYLE)
        self._status_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        self._text_edit = QPlainTextEdit()
        self._text_edit.setPlaceholderText("Transcribed text will appear here.")
        self._text_edit.textChanged.connect(self._update_copy_button_enabled)

        button_row = QHBoxLayout()
        button_row.addWidget(self._record_button)
        button_row.addWidget(self._copy_button)
        button_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addLayout(button_row)
        layout.addWidget(self._status_label)
        layout.addWidget(self._text_edit, stretch=1)

        self._relay = _Relay()
        self._relay.finished.connect(self._on_transcription_finished)

    def _update_copy_button_enabled(self) -> None:
        self._copy_button.setEnabled(bool(self._text_edit.toPlainText()))

    def _set_status(self, text: str, *, is_error: bool = False) -> None:
        self._status_label.setStyleSheet(ERROR_STYLE if is_error else STATUS_STYLE)
        self._status_label.setText(text)

    def _on_record_clicked(self) -> None:
        if self._audio_source is None:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self) -> None:
        fmt = QAudioFormat()
        fmt.setSampleRate(EXPECTED_SAMPLE_RATE)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)

        device = QMediaDevices.defaultAudioInput()
        if device.isNull():
            self._set_status("No microphone found.", is_error=True)
            return
        if not device.isFormatSupported(fmt):
            self._set_status("Default microphone does not support 16kHz mono 16-bit capture.", is_error=True)
            return

        self._captured_chunks = []
        self._audio_source = QAudioSource(device, fmt, self)
        self._audio_io = self._audio_source.start()
        self._audio_io.readyRead.connect(self._on_audio_ready_read)

        self._text_edit.clear()
        self._record_button.setText("■ Stop")
        self._set_status("Recording...")

    def _on_audio_ready_read(self) -> None:
        if self._audio_io is None:
            return
        data = bytes(self._audio_io.readAll())
        if data:
            self._captured_chunks.append(data)

    def _stop_recording(self) -> None:
        assert self._audio_source is not None
        self._audio_source.stop()
        self._audio_source = None
        self._audio_io = None
        self._process_captured_audio()

    def _process_captured_audio(self) -> None:
        """Split out from _stop_recording so tests can exercise the
        write-WAV -> background-transcribe -> UI-update pipeline against
        known, injected PCM data (e.g. real macOS `say`-synthesized
        speech) without depending on what a real microphone happens to
        pick up during an automated test run."""
        self._record_button.setText("● Record")
        self._record_button.setEnabled(False)

        pcm_bytes = b"".join(self._captured_chunks)
        self._captured_chunks = []
        if not pcm_bytes:
            self._set_status("No audio captured.", is_error=True)
            self._record_button.setEnabled(True)
            return

        wav_path = _write_wav(pcm_bytes)
        self._set_status("Transcribing...")
        thread = threading.Thread(target=_transcribe_in_background, args=(wav_path, self._relay), daemon=True)
        thread.start()

    def _on_transcription_finished(self, text: str | None, error: str | None) -> None:
        self._record_button.setEnabled(True)
        if error is not None:
            self._set_status(error, is_error=True)
            return
        self._text_edit.setPlainText(text)
        self._set_status("Done.")

    def _on_copy_clicked(self) -> None:
        QGuiApplication.clipboard().setText(self._text_edit.toPlainText())


def build() -> QWidget:
    return VoiceInputWidget()
