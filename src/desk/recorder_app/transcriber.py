"""Whisper for the recorder (TODO b9689cd): the same model and library as
`desk.speech`, but on in-memory audio and with a guard against whisper's
habit of inventing text ("Thank you.") for near-silence."""
import numpy as np

from desk.speech import MODEL_REPO

# A segment whisper itself thinks is not speech AND is low confidence.
_NO_SPEECH_PROB = 0.6
_AVG_LOGPROB = -1.0


def filter_segments(segments: list[dict]) -> str:
    kept = [
        s.get("text", "").strip()
        for s in segments
        if not (s.get("no_speech_prob", 0.0) > _NO_SPEECH_PROB and s.get("avg_logprob", 0.0) < _AVG_LOGPROB)
    ]
    return " ".join(t for t in kept if t).strip()


class Transcriber:
    def __init__(self, model_repo: str = MODEL_REPO) -> None:
        self.model_repo = model_repo
        self._mlx = None

    def load(self) -> None:
        """Loads the model by transcribing a second of silence."""
        import mlx_whisper

        self._mlx = mlx_whisper
        mlx_whisper.transcribe(np.zeros(16000, dtype=np.float32), path_or_hf_repo=self.model_repo)

    def transcribe(self, audio: np.ndarray) -> str:
        if self._mlx is None:
            self.load()
        result = self._mlx.transcribe(audio, path_or_hf_repo=self.model_repo)
        return filter_segments(result.get("segments") or [{"text": result.get("text", "")}])
