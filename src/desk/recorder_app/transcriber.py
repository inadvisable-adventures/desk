"""Whisper for the recorder (TODO b9689cd): the same model and library as
`desk.speech`, but on in-memory audio and with a guard against whisper's
habit of inventing text ("Thank you.") for near-silence.

Whisper decodes in its own sub-chunks within one `transcribe()` call (see
`investigations/live_transcription_chunking.md`'s read of
`mlx_whisper.transcribe`'s internal `seek` loop) and reports a `start`/`end`
(seconds into the audio it was given) per sub-chunk. `transcribe()` returns
those as `Phrase`s instead of collapsing them into one joined string, so a
caller that knows the wall-clock epoch of sample 0 of that audio (as
`TranscribeFeature` does) can stamp each phrase with its own accurate
timestamp -- rather than every phrase in a long utterance sharing one
timestamp spanning the whole thing."""
from dataclasses import dataclass

import numpy as np

from desk.recorder_app.segmenter import SAMPLE_RATE
from desk.speech import MODEL_REPO

# A segment whisper itself thinks is not speech AND is low confidence.
_NO_SPEECH_PROB = 0.6
_AVG_LOGPROB = -1.0


@dataclass(frozen=True)
class Phrase:
    """One of whisper's own sub-chunks: `text`, plus `start_s`/`end_s` --
    seconds into the audio array `Transcriber.transcribe` was given, not
    yet converted to a wall-clock timestamp."""

    text: str
    start_s: float
    end_s: float


def filter_segments(segments: list[dict]) -> list[Phrase]:
    phrases = []
    for s in segments:
        text = s.get("text", "").strip()
        if not text:
            continue
        if s.get("no_speech_prob", 0.0) > _NO_SPEECH_PROB and s.get("avg_logprob", 0.0) < _AVG_LOGPROB:
            continue
        phrases.append(Phrase(text=text, start_s=float(s.get("start", 0.0)), end_s=float(s.get("end", 0.0))))
    return phrases


class Transcriber:
    def __init__(self, model_repo: str = MODEL_REPO) -> None:
        self.model_repo = model_repo
        self._mlx = None

    def load(self) -> None:
        """Loads the model by transcribing a second of silence."""
        import mlx_whisper

        self._mlx = mlx_whisper
        mlx_whisper.transcribe(np.zeros(16000, dtype=np.float32), path_or_hf_repo=self.model_repo)

    def transcribe(self, audio: np.ndarray) -> list[Phrase]:
        if self._mlx is None:
            self.load()
        result = self._mlx.transcribe(audio, path_or_hf_repo=self.model_repo)
        segments = result.get("segments") or [
            {"text": result.get("text", ""), "start": 0.0, "end": len(audio) / SAMPLE_RATE}
        ]
        return filter_segments(segments)
