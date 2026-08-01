# Whisper model setup (local speech-to-text)

Desk's voice input feature (the Voice Input widget, `widgets/voice_input/`,
and `src/desk/speech.py`) transcribes speech locally, using OpenAI's
Whisper model run through [`mlx-whisper`](https://github.com/ml-explore/mlx-examples/tree/main/whisper)
(Apple's MLX framework). There is no Anthropic-hosted speech-to-text
endpoint to call instead -- Claude's API has no audio input, so any
voice pipeline needs its own local transcription step whose output
text is what actually gets used.

This only runs on Apple Silicon (MLX is Apple-Silicon-only). There is
no fallback for Intel Macs or other platforms yet.

**No `ffmpeg` install needed.** `mlx-whisper`'s own path-based audio
loader shells out to the `ffmpeg` CLI for *any* input format,
including plain WAV (see `LEARNINGS.md`) -- but `src/desk/speech.py`
never takes that path. It decodes the 16 kHz mono 16-bit PCM WAV the
Voice Input widget records directly (stdlib `wave` module) and hands
`mlx_whisper.transcribe()` the resulting sample array instead of a
file path, which skips `ffmpeg` entirely.

## Models are never part of this git repo

`mlx-whisper` resolves and caches models through the Hugging Face Hub
cache (`~/.cache/huggingface/hub` by default, or `$HF_HOME`/
`$HF_HUB_CACHE` if set) -- a location outside this repo's working tree
entirely, the same way `pip`'s own package cache is outside it. Nothing
downloaded this way can ever land under version control by accident;
there is no repo-local models directory to gitignore because there is
no repo-local models directory at all. If a downloaded model file is
ever found inside this repo's working tree, something has gone wrong
(a misconfigured `HF_HOME`, most likely) -- it should be removed, not
committed.

## Normal path: run the download script

```
python3 scripts/download_whisper_model.py            # default: large-v3-turbo
python3 scripts/download_whisper_model.py medium      # or any other supported size
```

This fetches (or confirms an already-cached) model, loads it once
through `mlx-whisper`'s own loader as a real check that the cached
files are actually usable, and prints the resolved local cache path
and its on-disk size. Run it once before using the Voice Input widget
for the first time -- transcription itself (`src/desk.speech.transcribe`)
deliberately does *not* trigger a first-time download on its own; it
raises a clear error pointing back here instead, so a multi-minute
download never happens silently in the middle of dictating something.

Supported sizes (`scripts/download_whisper_model.py`'s `MODEL_REPOS`,
each individually confirmed to exist on the Hub, not a guessed naming
convention -- the `mlx-community` org does not publish a uniformly
named repo for every size):

| Size | Notes |
|---|---|
| `tiny` / `tiny.en` | Fastest, least accurate |
| `base` / `base.en` | Good for quick drafts |
| `small` / `small.en` | Solid balance |
| `medium` / `medium.en` | Noticeably better accuracy |
| `large` | Best accuracy, slowest (Whisper v3) |
| `large-v3-turbo` | **Default.** Most of `large`'s accuracy at roughly `medium`'s speed |

The `.en` variants are English-only and slightly more accurate for
English-only use. `large-v3-turbo` has no English-only variant.

## Manual backup path

If Hugging Face Hub itself is unreachable from the machine that needs
the model, two options, in order of preference:

1. **Fetch on a machine that does have access, then copy the cache
   over.** Install the `huggingface_hub` CLI (`pip install
   "huggingface_hub[cli]"`) and run:

   ```
   huggingface-cli download mlx-community/whisper-large-v3-turbo --local-dir ~/whisper-large-v3-turbo
   ```

   (`--local-dir` deliberately points outside this repo -- anywhere
   under `~/` works, it just must not be a path inside this working
   tree, or it risks getting committed by accident.)

   (substitute the repo id for another size from the table above, via
   `scripts/download_whisper_model.py`'s `MODEL_REPOS` mapping). Copy
   the resulting directory onto the target machine and pass its path
   directly wherever a Hugging Face repo id is otherwise accepted --
   both `mlx_whisper.transcribe(..., path_or_hf_repo=...)` and
   `scripts/download_whisper_model.py`'s `snapshot_download` call
   accept a local directory path in place of a repo id.

2. **Convert an original OpenAI Whisper checkpoint directly**, for the
   rarer case where even the `mlx-community` weights are unreachable
   but OpenAI's own release still is. `mlx_whisper.convert` (from the
   `mlx-whisper` package, installed as part of this project's own
   dependencies) converts an original PyTorch Whisper checkpoint into
   the MLX weight format `mlx-whisper` expects. See
   [mlx-examples' Whisper conversion instructions](https://github.com/ml-explore/mlx-examples/blob/main/whisper/README.md)
   for the exact command -- this is a fallback for a genuinely
   unreachable Hub, not the normal path, so it isn't reproduced in
   full here.

## Verifying it worked

`scripts/download_whisper_model.py`'s own printed output already
confirms this (a resolved cache path and size, with no error). To
check independently:

```python
from huggingface_hub import scan_cache_dir
for repo in scan_cache_dir().repos:
    print(repo.repo_id, repo.size_on_disk)
```
