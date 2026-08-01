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
from PyQt6.QtGui import QColor, QGuiApplication, QTextCharFormat, QTextCursor
from PyQt6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from desk.speech import (
    EXPECTED_SAMPLE_RATE,
    TranscriptionResult,
    TranscriptionUnavailableError,
    WordConfidence,
    transcribe,
)

ERROR_STYLE = "color: #ff5c5c;"
STATUS_STYLE = "color: #9a9a9a;"

# TODO 76949eb: mirrors mlx_whisper's own no_speech_threshold default
# (0.6) -- "roughly where the model itself stops trusting its own
# output" -- picked as a starting point to revisit once real usage
# (i.e. actual "was this word actually wrong" feedback) exists.
LOW_CONFIDENCE_THRESHOLD = 0.5
LOW_CONFIDENCE_BACKGROUND = QColor("#5c3a3a")


class _Relay(QObject):
    """Owns the pyqtSignal the background transcription thread reports
    through -- same shape as widgets/git_status/widget.py's own
    _Relay. Exactly one of result/error is not None."""

    finished = pyqtSignal(object, object)  # result: TranscriptionResult | None, error: str | None


def _transcribe_in_background(wav_path: Path, relay: _Relay) -> None:
    """Module-level, not a method: runs on a background thread and must
    not touch any Qt widget directly -- only ever reports back via the
    relay's signal, same reasoning as widgets/git_status/widget.py's
    _run_git_status."""
    try:
        result: TranscriptionResult | None = transcribe(wav_path)
        error: str | None = None
    except TranscriptionUnavailableError as exc:
        result = None
        error = str(exc)
    except Exception as exc:  # noqa: BLE001 -- surfaced to the user, not swallowed
        result = None
        error = f"Transcription failed: {exc}"
    finally:
        wav_path.unlink(missing_ok=True)
    relay.finished.emit(result, error)


def word_offsets(text: str, words: list[WordConfidence]) -> list[tuple[int, int, float]]:
    """Returns (start, end, probability) character offsets into `text`
    for each word -- module-level and exported (not underscore
    -prefixed) so tests/verify/verify_voice_input_widget.py can drive
    it directly with hand-built data (TODO 76949eb).

    Reconstructs offsets by joining every word's own `.word` string
    (which already includes whatever leading whitespace/punctuation
    mlx_whisper attached to it) back together in order -- confirmed
    directly that this exactly reproduces transcribe()'s own untrimmed
    result["text"], so the only adjustment needed is for transcribe()'s
    own text.strip() (a leading-whitespace shift -- clamped, not
    dropped: the very first word's own leading space is almost always
    exactly what gets trimmed, so its *start* moves to 0 rather than
    the whole word being discarded)."""
    joined = "".join(w.word for w in words)
    lstrip_amount = len(joined) - len(joined.lstrip())
    offsets = []
    pos = 0
    for w in words:
        raw_start = pos
        pos += len(w.word)
        start = max(raw_start - lstrip_amount, 0)
        end = min(pos - lstrip_amount, len(text))
        if start < end:
            offsets.append((start, end, w.probability))
    return offsets


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

    def _on_transcription_finished(self, result: TranscriptionResult | None, error: str | None) -> None:
        self._record_button.setEnabled(True)
        if error is not None:
            self._set_status(error, is_error=True)
            return
        self._text_edit.setPlainText(result.text)
        self._highlight_low_confidence_words(result)
        self._set_status("Done.")

    def _highlight_low_confidence_words(self, result: TranscriptionResult) -> None:
        """Flags a low-confidence word (TODO 76949eb) via a background
        -color QTextEdit.ExtraSelection rather than switching _text_edit
        to rich text -- QPlainTextEdit.setExtraSelections() works
        directly on it, no HTML/CSS round-tripping to reason about."""
        selections = []
        for start, end, probability in word_offsets(result.text, result.words):
            if probability >= LOW_CONFIDENCE_THRESHOLD:
                continue
            cursor = QTextCursor(self._text_edit.document())
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            selection = QTextEdit.ExtraSelection()
            selection.cursor = cursor
            fmt = QTextCharFormat()
            fmt.setBackground(LOW_CONFIDENCE_BACKGROUND)
            # A numeric-probability hover tooltip is a real follow-up
            # (deferred, not forgotten -- see plans/speech-word
            # -confidence.md) needing real cursorForPosition() + QToolTip
            # wiring, which QTextCharFormat.setToolTip() alone does not
            # provide on a QPlainTextEdit -- not added here to avoid a
            # tooltip that looks configured but never actually shows.
            selection.format = fmt
            selections.append(selection)
        self._text_edit.setExtraSelections(selections)

    def _on_copy_clicked(self) -> None:
        QGuiApplication.clipboard().setText(self._text_edit.toPlainText())


def build() -> QWidget:
    return VoiceInputWidget()
