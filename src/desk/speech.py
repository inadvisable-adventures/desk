"""Local speech-to-text transcription via mlx-whisper (TODO 1cd0ca2).

See design-docs/whisper-model-setup.md for how the model this module
uses gets onto disk (deliberately not this module's job -- see
TranscriptionUnavailableError below) and PARKINGLOT.md's original
"Local speech-to-text (Whisper) for voice input" note for why a local
model at all: Claude's API has no audio input endpoint, so any voice
pipeline needs its own local transcription step.
"""
import contextlib
import wave
from pathlib import Path

import numpy as np
from huggingface_hub import try_to_load_from_cache

# Matches scripts/download_whisper_model.py's own MODEL_REPOS["large-v3-turbo"]
# -- this project's chosen default size. Kept as an independent literal
# rather than importing that script's dict (a script under scripts/ is
# not part of the installed `desk` package, so importing it here would
# require sys.path surgery for no real benefit -- these two spellings
# are simple enough to keep in sync by hand; a verify check enforces
# that they don't drift apart, see tests/verify/verify_speech_transcription.py).
MODEL_REPO = "mlx-community/whisper-large-v3-turbo"

# The two files mlx_whisper.load_models.load_model actually reads --
# if either isn't fully cached yet, treat the model as unavailable
# rather than letting mlx_whisper silently block on downloading it.
_REQUIRED_FILES = ("config.json", "weights.safetensors")


class TranscriptionUnavailableError(RuntimeError):
    """Raised when MODEL_REPO isn't fully cached locally yet, instead of
    letting a transcribe() call silently block for however long a
    multi-gigabyte download takes in the middle of dictating something."""


def _model_is_cached() -> bool:
    return all(
        try_to_load_from_cache(repo_id=MODEL_REPO, filename=filename) is not None
        for filename in _REQUIRED_FILES
    )


EXPECTED_SAMPLE_RATE = 16000


def _read_wav_as_float32(audio_path: Path) -> np.ndarray:
    """Decodes a 16 kHz mono 16-bit PCM WAV file into the normalized
    float32 sample array mlx_whisper's model expects.

    Deliberately does not hand `str(audio_path)` to
    `mlx_whisper.transcribe()` directly: its own audio loader
    (`mlx_whisper.audio.load_audio`) unconditionally shells out to the
    `ffmpeg` CLI to decode *any* input file, including a plain WAV --
    confirmed directly (a `FileNotFoundError` on a machine with no
    `ffmpeg` installed and no package manager available to install
    it). Since this module's only caller (the Voice Input widget,
    TODO `b32fb81`) already records in exactly this format, decoding it
    ourselves with the stdlib `wave` module avoids needing `ffmpeg` --
    an extra system-level binary dependency -- entirely."""
    with wave.open(str(audio_path), "rb") as wav_file:
        if wav_file.getframerate() != EXPECTED_SAMPLE_RATE or wav_file.getnchannels() != 1 or wav_file.getsampwidth() != 2:
            raise ValueError(
                f"{audio_path} must be {EXPECTED_SAMPLE_RATE} Hz mono 16-bit PCM WAV, got "
                f"{wav_file.getframerate()} Hz, {wav_file.getnchannels()} channel(s), "
                f"{wav_file.getsampwidth() * 8}-bit"
            )
        frames = wav_file.readframes(wav_file.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


@contextlib.contextmanager
def _force_hub_offline():
    """mlx_whisper.transcribe() calls mlx_whisper.load_models.load_model(),
    which calls huggingface_hub.snapshot_download() on *every* call
    (memoized in-process by mlx_whisper's own ModelHolder, so only the
    first transcribe() per process actually hits this) -- and
    snapshot_download() contacts the Hub to resolve "main" to a commit
    hash even when every file it needs is already cached locally.

    Confirmed directly this is not just an extra log line: with the
    Hub genuinely unreachable (a black-holed connection, not a
    same-host "connection refused") rather than merely absent, that
    revision-resolution call blocks for the full request timeout --
    measured at ~77 seconds -- before falling back to the local cache.
    Since transcribe() only reaches this point after _model_is_cached()
    already confirmed the required files are on disk, there is nothing
    for a real network call to accomplish here.

    Setting the HF_HUB_OFFLINE *environment variable* at this point
    does not work, confirmed directly: huggingface_hub.constants
    .HF_HUB_OFFLINE is computed once, from os.environ, at the moment
    that module is first imported (which already happened by the time
    this function runs) -- every later read goes through
    constants.is_offline_mode(), which just returns that frozen
    module-level bool, not a live os.environ lookup. The env var must
    be patched directly on the module object instead; confirmed this
    way the same artificially-unreachable-network case above drops
    from ~77 seconds to ~1.5. Scoped via save/restore around just this
    call, not process-wide, so it never affects
    scripts/download_whisper_model.py (which deliberately does want
    the network) if the two ever ran in the same process."""
    from huggingface_hub import constants

    previous = constants.HF_HUB_OFFLINE
    constants.HF_HUB_OFFLINE = True
    try:
        yield
    finally:
        constants.HF_HUB_OFFLINE = previous


def transcribe(audio_path: Path) -> str:
    """Transcribe a 16 kHz mono 16-bit PCM WAV file to text using
    MODEL_REPO."""
    if not _model_is_cached():
        raise TranscriptionUnavailableError(
            f"{MODEL_REPO!r} is not downloaded yet. Run "
            "`python3 scripts/download_whisper_model.py` first -- see "
            "design-docs/whisper-model-setup.md."
        )

    import mlx_whisper

    samples = _read_wav_as_float32(audio_path)
    with _force_hub_offline():
        result = mlx_whisper.transcribe(samples, path_or_hf_repo=MODEL_REPO)
    return result["text"].strip()
