"""Cuts a continuous 16 kHz mono stream into utterances at pauses
(TODO b9689cd). Pure logic, no Qt and no whisper, so it is testable with
synthetic audio.

`feed(samples)` returns `Job`s for the caller to transcribe:
- a `final` job when an utterance ends (a pause of `silence_ms`, or the
  utterance reached `max_utterance_s`), carrying all its audio;
- a `provisional` job every `provisional_every_s` while speech continues,
  carrying the audio so far (the caller may drop one if it is still busy
  with the previous; it must never drop a final).
All jobs of one utterance share a `seq`. Positions are sample indexes in
the stream, so the caller turns them into wall-clock times.

Speech detection is energy-based (30 ms frames; the threshold follows the
background noise), which is crude but enough to find pauses in dictation.
"""
from dataclasses import dataclass

import numpy as np

SAMPLE_RATE = 16000


@dataclass(frozen=True)
class Job:
    kind: str  # "provisional" | "final"
    seq: int
    start_sample: int
    end_sample: int
    audio: np.ndarray  # float32 in [-1, 1]


class UtteranceSegmenter:
    def __init__(
        self,
        sample_rate: int = SAMPLE_RATE,
        frame_ms: int = 30,
        silence_ms: int = 700,
        min_speech_ms: int = 250,
        preroll_ms: int = 300,
        max_utterance_s: float = 25.0,
        provisional_every_s: float = 2.0,
        min_threshold: float = 0.01,
    ) -> None:
        self.rate = sample_rate
        self.frame = sample_rate * frame_ms // 1000
        self.silence_frames = max(1, silence_ms // frame_ms)
        self.min_speech_frames = max(1, min_speech_ms // frame_ms)
        self.preroll = sample_rate * preroll_ms // 1000
        self.max_samples = int(max_utterance_s * sample_rate)
        self.provisional_every = int(provisional_every_s * sample_rate)
        self.min_threshold = min_threshold
        self._buffer = np.zeros(0, dtype=np.float32)  # unconsumed samples
        self._buffer_start = 0  # stream index of _buffer[0]
        self._history = np.zeros(0, dtype=np.float32)  # recent samples before speech, for pre-roll
        self._noise = min_threshold / 3
        self._seq = 0
        self._speech_frames = 0  # consecutive loud frames while idle
        self._active = False
        self._utt_start = 0
        self._utt_audio: list[np.ndarray] = []
        self._utt_samples = 0
        self._silent_run = 0
        self._last_provisional = 0
        self._speech_total = 0

    @property
    def in_utterance(self) -> bool:
        return self._active

    def _threshold(self) -> float:
        return max(self.min_threshold, self._noise * 3.0)

    def feed(self, samples: np.ndarray) -> list[Job]:
        jobs: list[Job] = []
        self._buffer = np.concatenate([self._buffer, samples.astype(np.float32, copy=False)])
        while len(self._buffer) >= self.frame:
            frame = self._buffer[: self.frame]
            frame_start = self._buffer_start
            self._buffer = self._buffer[self.frame :]
            self._buffer_start += self.frame
            jobs.extend(self._frame(frame, frame_start))
        return jobs

    def _frame(self, frame: np.ndarray, frame_start: int) -> list[Job]:
        rms = float(np.sqrt(np.mean(frame * frame)))
        loud = rms > self._threshold()
        jobs: list[Job] = []
        if not self._active:
            if not loud:
                self._noise = 0.95 * self._noise + 0.05 * rms
            self._history = np.concatenate([self._history, frame])[-(self.preroll + self.frame * 4) :]
            self._speech_frames = self._speech_frames + 1 if loud else 0
            if self._speech_frames >= self.min_speech_frames:
                # Speech confirmed: start with a little audio from before it.
                lead = min(len(self._history), self.preroll + self.frame * (self._speech_frames - 1))
                lead_audio = self._history[len(self._history) - lead - 0 :]
                self._active = True
                self._utt_start = frame_start + self.frame - len(lead_audio)
                self._utt_audio = [lead_audio]
                self._utt_samples = len(lead_audio)
                self._silent_run = 0
                self._last_provisional = self._utt_samples
                self._speech_frames = 0
                self._history = np.zeros(0, dtype=np.float32)
            return jobs
        self._utt_audio.append(frame)
        self._utt_samples += len(frame)
        self._silent_run = 0 if loud else self._silent_run + 1
        end = frame_start + self.frame
        if self._silent_run >= self.silence_frames:
            jobs.append(self._finish(end))
        elif self._utt_samples >= self.max_samples:
            jobs.append(self._finish(end))
        elif self._utt_samples - self._last_provisional >= self.provisional_every:
            self._last_provisional = self._utt_samples
            jobs.append(Job("provisional", self._seq, self._utt_start, end, np.concatenate(self._utt_audio)))
        return jobs

    def _finish(self, end: int) -> Job:
        job = Job("final", self._seq, self._utt_start, end, np.concatenate(self._utt_audio))
        self._seq += 1
        self._active = False
        self._utt_audio = []
        self._utt_samples = 0
        self._silent_run = 0
        self._speech_frames = 0
        return job

    def flush(self) -> list[Job]:
        """Stream ended: finish an utterance in progress."""
        if not self._active:
            return []
        end = self._buffer_start + len(self._buffer)
        if len(self._buffer):
            self._utt_audio.append(self._buffer)
            self._buffer = np.zeros(0, dtype=np.float32)
        return [self._finish(end)]

    def sample_to_ms(self, sample: int, t0_ms: int) -> int:
        return t0_ms + sample * 1000 // self.rate
