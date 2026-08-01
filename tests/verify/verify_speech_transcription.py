import logging
import subprocess
import sys
import tempfile
import time
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
        result = speech.transcribe(wav_path)
        normalized = result.text.lower().strip().rstrip(".")
        check(
            "real synthesized speech transcribes back to (close to) the original text",
            "quick brown fox" in normalized and "lazy dog" in normalized,
        )


def test_transcribe_returns_per_word_confidence():
    """TODO 76949eb: transcribe() returns TranscriptionResult(text,
    words), not a plain str -- real, non-mocked check that .words is
    populated with plausible per-word probabilities, and that joining
    every word's own .word string back together reproduces .text
    exactly (the assumption widgets/voice_input/widget.py's own
    word_offsets relies on for highlighting -- confirmed directly here,
    not just assumed)."""
    with tempfile.TemporaryDirectory() as tmp:
        wav_path = Path(tmp) / "sample.wav"
        _synthesize_wav("Are we going to hit the thing or not", wav_path)
        result = speech.transcribe(wav_path)
        check("transcribe() returns a TranscriptionResult", isinstance(result, speech.TranscriptionResult))
        check("result.words is non-empty for real speech", len(result.words) > 0)
        check(
            "every word has a real probability in [0.0, 1.0]",
            all(isinstance(w, speech.WordConfidence) and 0.0 <= w.probability <= 1.0 for w in result.words),
        )
        joined = "".join(w.word for w in result.words)
        check("joining every word's own .word string reproduces the untrimmed text", joined.strip() == result.text)


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


def test_transcribe_makes_no_network_calls_once_cached():
    """mlx_whisper.transcribe() itself calls huggingface_hub
    .snapshot_download() on every invocation (memoized per-process by
    mlx_whisper's own ModelHolder, so only the first call in a real app
    session actually reaches this) even when the model is fully
    cached, to resolve "main" to a commit hash -- confirmed directly by
    watching httpx's own request log during a real call before
    desk.speech._force_hub_offline existed. Guards against that
    regression by asserting no HTTP request is logged during a real
    transcribe() call, not just that it completes."""
    http_log = []

    class _CapturingHandler(logging.Handler):
        def emit(self, record):
            http_log.append(record.getMessage())

    handler = _CapturingHandler()
    httpx_logger = logging.getLogger("httpx")
    previous_level = httpx_logger.level
    httpx_logger.addHandler(handler)
    httpx_logger.setLevel(logging.INFO)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            wav_path = Path(tmp) / "sample.wav"
            _synthesize_wav("No network calls should happen here", wav_path)
            speech.transcribe(wav_path)
    finally:
        httpx_logger.removeHandler(handler)
        httpx_logger.setLevel(previous_level)

    check("transcribing an already-cached model makes zero logged HTTP requests", not http_log)


def test_transcribe_does_not_hang_when_the_hub_is_genuinely_unreachable():
    """Real, non-mocked reproduction of the bug _force_hub_offline
    fixes: point at a black-holed (non-responding, not merely
    connection-refused) address so huggingface_hub's own revision
    -resolution network call can't fail fast -- confirmed directly
    that before the fix this took ~77 seconds to fall back to the
    local cache; with the fix, well under 15."""
    script = (
        "import sys, time; "
        "sys.path.insert(0, 'src'); "
        "from desk import speech; "
        "start = time.time(); "
        "result = speech.transcribe(sys.argv[1]); "
        "print(f'{time.time() - start:.2f} {result.text}')"
    )
    with tempfile.TemporaryDirectory() as tmp:
        wav_path = Path(tmp) / "sample.wav"
        _synthesize_wav("Should not hang even when offline", wav_path)

        import os

        env = dict(os.environ)
        env["HF_ENDPOINT"] = "http://10.255.255.1"  # non-routable; refuses nothing, just never responds
        env["HF_HUB_ETAG_TIMEOUT"] = "3"

        start = time.time()
        result = subprocess.run(
            [sys.executable, "-c", script, str(wav_path)],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env=env,
            timeout=30,
        )
        elapsed = time.time() - start

    check("transcribe() with an unreachable Hub still succeeds", result.returncode == 0)
    check(f"transcribe() with an unreachable Hub returns well under the old ~77s hang (took {elapsed:.1f}s)", elapsed < 15)


test_model_repo_matches_the_download_scripts_own_mapping()
test_transcribes_real_synthesized_speech()
test_transcribe_returns_per_word_confidence()
test_rejects_wrong_format_wav()
test_unavailable_model_raises_clear_error()
test_transcribe_makes_no_network_calls_once_cached()
test_transcribe_does_not_hang_when_the_hub_is_genuinely_unreachable()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
