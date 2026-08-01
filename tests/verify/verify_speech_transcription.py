import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path("/Users/mphair/inadvisable-adventures/desk")
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from desk import speech  # noqa: E402
from download_whisper_model import MODEL_REPOS  # noqa: E402

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


def _synthesize_wav(text: str, path: Path) -> None:
    """Real macOS text-to-speech (the `say` CLI, always present on
    macOS) -- a real, non-synthetic audio pipeline end to end, rather
    than a mocked or hand-crafted tone. Not a Whisper-side dependency:
    only used to *produce* the test fixture at run time, so the fixture
    audio itself never needs to be checked into the repo."""
    subprocess.run(
        [
            "say",
            "-o", str(path),
            "--file-format=WAVE",
            "--data-format=LEI16@16000",
            text,
        ],
        check=True,
    )


def test_model_repo_matches_the_download_scripts_own_mapping():
    check(
        "desk.speech.MODEL_REPO matches scripts/download_whisper_model.py's own default entry",
        speech.MODEL_REPO == MODEL_REPOS["large-v3-turbo"],
    )


def test_transcribes_real_synthesized_speech():
    with tempfile.TemporaryDirectory() as tmp:
        wav_path = Path(tmp) / "sample.wav"
        _synthesize_wav("The quick brown fox jumps over the lazy dog", wav_path)
        text = speech.transcribe(wav_path)
        normalized = text.lower().strip().rstrip(".")
        check(
            "real synthesized speech transcribes back to (close to) the original text",
            "quick brown fox" in normalized and "lazy dog" in normalized,
        )


def test_rejects_wrong_format_wav():
    import wave

    with tempfile.TemporaryDirectory() as tmp:
        # A real WAV file, just not in the 16 kHz mono 16-bit PCM format
        # this module requires -- stereo, 44.1 kHz.
        wav_path = Path(tmp) / "wrong-format.wav"
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(44100)
            wf.writeframes(b"\x00\x00" * 4410 * 2)

        raised = False
        try:
            speech.transcribe(wav_path)
        except ValueError:
            raised = True
        check("a non-16kHz/mono/16-bit WAV raises ValueError instead of silently mis-transcribing", raised)


def test_unavailable_model_raises_clear_error():
    original_repo = speech.MODEL_REPO
    speech.MODEL_REPO = "mlx-community/whisper-this-repo-does-not-exist"
    try:
        raised = False
        message = ""
        try:
            speech.transcribe(Path("/dev/null"))
        except speech.TranscriptionUnavailableError as exc:
            raised = True
            message = str(exc)
        check("an uncached model repo raises TranscriptionUnavailableError", raised)
        check(
            "the error message points at the download script and setup doc",
            "download_whisper_model.py" in message and "whisper-model-setup.md" in message,
        )
    finally:
        speech.MODEL_REPO = original_repo


test_model_repo_matches_the_download_scripts_own_mapping()
test_transcribes_real_synthesized_speech()
test_rejects_wrong_format_wav()
test_unavailable_model_raises_clear_error()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
