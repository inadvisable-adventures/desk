# Plan: TODO 1cd0ca2 — local speech-to-text transcription module (mlx-whisper)

From `PARKINGLOT.md`'s "Local speech-to-text (Whisper) for voice
input" item. Builds the actual transcription engine on top of TODO
`f9d2dc7`'s model-download infrastructure. No UI here — that's TODO
`b32fb81`. This module is Python-only and audio-file-in,
text-out, so it can be verified without any real widget or Qt event
loop involvement beyond what `mlx-whisper` itself needs.

## Dependency

Add `mlx-whisper` to `pyproject.toml`'s `dependencies`. This is a
necessary dependency, not one CLAUDE.md's "avoid adding dependencies,
prefer bespoke solutions" guidance is meant to block — there is no
bespoke way to run a Whisper model (`design-docs/architecture.md`'s
own framing: that guidance is about *unnecessary* dependencies, not
refusing a necessary one once a bespoke alternative genuinely doesn't
exist). Audio *capture* (TODO `b32fb81`) does not need a new
dependency — PyQt6 already ships `QtMultimedia` (`QAudioSource` et
al.) in this project's installed PyQt6 wheel, confirmed directly
(`from PyQt6 import QtMultimedia` succeeds in `.venv`) — so this is
the one and only new dependency this whole feature needs.

## `src/desk/speech.py`

New module, sibling to `src/desk/mermaid.py`/`transforms.py` (existing
precedent for a focused, single-purpose module wrapping a specific
capability):

```python
MODEL_REPO = "mlx-community/whisper-large-v3-turbo"

class TranscriptionUnavailableError(RuntimeError):
    """Raised when the model isn't cached locally yet."""

def transcribe(audio_path: Path) -> str:
    ...
```

- `transcribe(audio_path)` calls `mlx_whisper.transcribe(str(audio_path),
  path_or_hf_repo=MODEL_REPO)` and returns the `"text"` field, stripped.
- Before calling into `mlx_whisper`, check whether the model is
  actually cached (via `huggingface_hub`'s own cache-scanning API,
  e.g. `huggingface_hub.scan_cache_dir()`, checking for `MODEL_REPO`)
  and raise `TranscriptionUnavailableError` with a message pointing at
  `scripts/download_whisper_model.py` and
  `design-docs/whisper-model-setup.md` if it's not — this is the
  actual reason TODO `f9d2dc7` exists as a *separate*, pre-requisite
  step: the first real dictation attempt should never silently block
  for minutes on an unannounced model download; it should fail fast
  with instructions.
- `MODEL_REPO` matches TODO `f9d2dc7`'s script's default exactly — if
  that TODO's implementation ends up resolving a different literal
  repo id string per size, keep this constant and that script's
  mapping in sync (single source of truth question to resolve during
  implementation, not now).

## Verification

New `tests/verify/verify_speech_transcription.py`:
- Real, non-mocked: with the model actually downloaded (via TODO
  `f9d2dc7`'s script, run once as a fixture/setup step — not
  network-mocked), transcribe a small, real, checked-in test audio
  fixture with known, unambiguous spoken content (e.g. a few spoken
  digits or a short fixed phrase) and assert the returned text
  matches (allowing for whisper's own minor punctuation/casing
  variance — compare on a normalized/lowercased basis).
- Confirm `transcribe()` raises `TranscriptionUnavailableError` (not
  some other exception, not a raw `mlx_whisper` internal error) when
  pointed at a model repo id that is deliberately never cached (a fake
  repo id string, not `MODEL_REPO` itself, so this check doesn't
  require *not* having the real model present).
- If the real model cannot be present in the environment running this
  particular verification pass (no network, no Apple Silicon), note
  that explicitly as a skip in the plan per this repo's process rule,
  rather than mocking `mlx_whisper` — a mocked transcription result
  would defeat the entire point of this test.
- Full `tests/verify/` regression suite.

## Open question to resolve during implementation, not now

Whether `MODEL_REPO`'s literal string should live in this module or be
imported from wherever TODO `f9d2dc7`'s download script defines its
own size→repo-id mapping, to avoid two hardcoded copies drifting apart
silently. Flagging here rather than guessing at an import path before
that script exists.
