# Note: the tests that start a real MicRecorder capture (a real
# QAudioSource against the actual default microphone) were split out
# to tests/verify/disabled_verify_voice_input_widget_mic.py and
# disabled there (TODO b2ab79f) -- they were audibly/visibly
# activating the system mic during routine regression sweeps. The
# tests remaining here (widget.json shape, control-tree structure,
# word_offsets against real transcription output, low-confidence
# highlighting) never touch the microphone and keep running normally.
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from PyQt6.QtWidgets import QApplication, QLabel, QPlainTextEdit, QPushButton  # noqa: E402

import desk.speech as speech  # noqa: E402

app = QApplication(sys.argv)

WIDGET_DIR = REPO_ROOT / "widgets" / "voice_input"

passed = 0
failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


def load_module(name, relative_path):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_widget_json_is_well_formed():
    manifest = json.loads((WIDGET_DIR / "widget.json").read_text())
    check("widget.json declares kind: python", manifest["kind"] == "python")
    check("widget.json entry is widget.py", manifest["entry"] == "widget.py")
    check("widget.json declares no capabilities (this is a kind:python widget, not HTML/Bridge)", manifest["capabilities"] == [])


voice_input_mod = load_module("voice_input_widget", "widgets/voice_input/widget.py")


def test_build_returns_expected_control_tree():
    widget = voice_input_mod.build()
    buttons = widget.findChildren(QPushButton)
    labels = widget.findChildren(QLabel)
    text_edits = widget.findChildren(QPlainTextEdit)
    check("exactly one record button and one copy button exist", len(buttons) == 2)
    check("a record button with the expected initial text exists", any(b.text() == "● Record" for b in buttons))
    check("a copy button exists", any(b.text() == "Copy" for b in buttons))
    check("copy button starts disabled (nothing transcribed yet)", widget._copy_button.isEnabled() is False)
    check("a status label exists", len(labels) >= 1)
    check("a text edit for the transcription result exists", len(text_edits) == 1)
    widget.deleteLater()


def test_word_offsets_reconstructs_real_transcription_offsets():
    """TODO 76949eb: word_offsets() against real model output (not just
    hand-built data). Each word's own .word string keeps its natural
    leading space (real content between words in the final text) --
    only the very *first* word loses its leading space, matching what
    transcribe()'s own text.strip() trims from the whole string
    (confirmed directly: real output's first-word slice has no leading
    space, every later word's does). The real, holistic invariant that
    matters for correct highlighting is that the offsets fully and
    exactly tile the text with no gaps or overlaps."""
    result = speech.transcribe(_synthesize_wav_path("Are we going to hit the thing or not"))
    offsets = voice_input_mod.word_offsets(result.text, result.words)
    check("word_offsets returns one entry per word for real transcription output", len(offsets) == len(result.words))
    check(
        "the first word's slice has no leading space (text.strip() trimmed it)",
        offsets and result.text[offsets[0][0] : offsets[0][1]] == result.words[0].word.lstrip(),
    )
    check(
        "every later word's slice keeps its own natural leading space",
        all(result.text[start:end] == word.word for (start, end, _p), word in list(zip(offsets, result.words))[1:]),
    )
    reconstructed = "".join(result.text[start:end] for start, end, _p in offsets)
    check("the offsets fully and exactly tile the text, no gaps or overlaps", reconstructed == result.text)


def test_low_confidence_word_is_highlighted():
    """Real microphone/model-driven low-confidence output isn't
    reproducible on demand, so this drives _on_transcription_finished
    directly with a hand-built TranscriptionResult containing one
    deliberately low-probability word -- real Qt widget, real
    setExtraSelections() call, injected data (TODO 76949eb)."""
    widget = voice_input_mod.build()
    text = "Hello world"
    result = speech.TranscriptionResult(
        text=text,
        words=[
            speech.WordConfidence(word="Hello", probability=0.95),
            speech.WordConfidence(word=" world", probability=0.1),
        ],
    )
    widget._on_transcription_finished(result, None)

    check("the transcribed text is set", widget._text_edit.toPlainText() == text)
    selections = widget._text_edit.extraSelections()
    check("exactly one low-confidence word is highlighted", len(selections) == 1)
    if selections:
        selected_cursor = selections[0].cursor
        check("the highlighted range covers exactly the low-confidence word", selected_cursor.selectedText() == " world")
        check("the highlight uses the configured low-confidence background color", selections[0].format.background().color() == voice_input_mod.LOW_CONFIDENCE_BACKGROUND)

    # A second, all-high-confidence result must clear any previous
    # highlighting rather than accumulating stale selections.
    clean_result = speech.TranscriptionResult(
        text="All good",
        words=[speech.WordConfidence(word="All", probability=0.99), speech.WordConfidence(word=" good", probability=0.98)],
    )
    widget._on_transcription_finished(clean_result, None)
    check("a fully high-confidence result clears extra selections", widget._text_edit.extraSelections() == [])

    widget.deleteLater()


def _synthesize_wav_path(text: str) -> Path:
    """Like synthesize_pcm, but returns a real WAV file path instead of
    raw PCM bytes -- for tests that call speech.transcribe() directly
    rather than driving it through the widget's own recording pipeline."""
    import tempfile

    tmp_dir = tempfile.mkdtemp()
    wav_path = Path(tmp_dir) / "sample.wav"
    subprocess.run(
        ["say", "-o", str(wav_path), "--file-format=WAVE", "--data-format=LEI16@16000", text],
        check=True,
    )
    return wav_path


test_widget_json_is_well_formed()
test_build_returns_expected_control_tree()
test_word_offsets_reconstructs_real_transcription_offsets()
test_low_confidence_word_is_highlighted()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
