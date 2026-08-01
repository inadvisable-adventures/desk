# Plan: TODO f9d2dc7 — Whisper model download script and setup documentation

From `PARKINGLOT.md`'s "Local speech-to-text (Whisper) for voice input"
item: before any code depends on a Whisper model being present, this
project needs (1) a script that fetches the chosen model on demand and
(2) a markdown doc covering both the normal path and a manual backup
path, per the parking lot item's own explicit follow-up list and the
user's direct instruction that **no downloaded model file is ever
committed to the repo**.

This TODO is infrastructure-only — no transcription code yet (that is
TODO `1cd0ca2`) and no UI (TODO `b32fb81`). It exists first because
both later items depend on a model actually being resolvable on disk,
and because getting the "never committed" guarantee right is easiest
to reason about in isolation.

## Model choice

`large-v3-turbo`, matching the parking lot item's own stated
conclusion ("I am thinking of going with `large-v3-turbo` as
recommended"). Runner: `mlx-whisper` (Apple Silicon only, via Apple's
MLX framework) — also the parking lot item's own conclusion, chosen
over the macOS `Speech` framework for having a normal Python-native
interface. This means the feature is Apple-Silicon-only for now; that
matches the parked research and isn't being re-litigated here. Wider
platform support (`whisper.cpp`, CPU-only `openai-whisper`) is a
separate future concern, not silently folded into this TODO.

## Where the model lives (and why it can never be committed)

`mlx-whisper` resolves models from the Hugging Face Hub and caches
them under the standard Hugging Face cache directory
(`~/.cache/huggingface/hub` by default, or `$HF_HOME` if set) —
**outside this repo's working tree entirely**, the same way `pip`'s
own package cache is outside it. As long as nothing in this project
ever points that cache *inside* the repo, there is nothing to
gitignore because nothing downloaded ever lands under version control
in the first place. This is the design, not an incidental detail: it
means "don't commit the model" is structurally true rather than
relying on a `.gitignore` entry someone could forget.

Still, add a defensive `.gitignore` entry (`models/whisper/` or similar
— pick the literal path the script/module use for any *optional*
override, e.g. a `DESK_WHISPER_MODEL_DIR` environment variable for
testing against a throwaway local copy) so an override used during
development or testing can never be accidentally staged either. Belt
and suspenders, per the user's explicit ask.

## `scripts/download_whisper_model.py`

A standalone script (same `scripts/` directory as
`todo_item_ids.py`), runnable as `python3
scripts/download_whisper_model.py` with no arguments for the default
(`large-v3-turbo`), or `python3 scripts/download_whisper_model.py
<model-size>` for another size from the parking lot item's own table
(`tiny`, `base`, `small`, `medium`, `large`, `large-v3-turbo`, and the
`.en` variants).

Behavior:
- Resolves the real `mlx-community/whisper-<size>` Hugging Face repo
  id for the requested size (the `mlx-community` org publishes
  MLX-converted weights for every standard Whisper size).
- Triggers a real download/cache-population by loading the model once
  (`mlx_whisper`'s own loader already handles "already cached, skip"
  vs. "fetch, cache" — this script doesn't reimplement that, just
  calls it so the *first* download happens here, deliberately, with
  visible progress, rather than silently blocking the first real
  dictation attempt in TODO `b32fb81`'s widget).
- Prints the resolved local cache path and on-disk size when done, so
  it's easy to confirm the download actually landed outside the repo.
- Exits with a clear, actionable error (not a raw traceback) if there
  is no network access, pointing at the manual backup instructions
  below.

## `design-docs/whisper-model-setup.md`

New standalone doc (same pattern as e.g.
`qtextbrowser-images-svg-controls.md` — a focused topic doc at the
repo root, or under `design-docs/`; placing it under `design-docs/`
since it documents a real architectural dependency, not a one-off
investigation). Contents:
- Why local Whisper, briefly (mirrors the parking lot item's own
  reasoning: no Anthropic-hosted transcription endpoint exists).
- Hardware requirement: Apple Silicon only, for now.
- Normal path: run `scripts/download_whisper_model.py`, what it
  prints, where the model ends up (the Hugging Face cache, *not* this
  repo), how to confirm it worked.
- Manual backup path, for when the script's normal source (Hugging
  Face Hub) is unreachable:
  - Installing and using `huggingface-cli download
    mlx-community/whisper-large-v3-turbo --local-dir <dir>` against a
    mirror or a machine with existing access, then copying the
    resulting directory onto the target machine and pointing
    `HF_HOME`/the cache at it.
  - Converting an original OpenAI Whisper checkpoint to MLX format
    directly via `mlx_whisper.convert`, for the case where even the
    `mlx-community` weights are unreachable but the original OpenAI
    release still is.
- An explicit, called-out note: models are never part of this git
  repo; if a downloaded file is ever seen inside the working tree,
  something has gone wrong (wrong `HF_HOME`, wrong override env var)
  and should not be committed.

## Verification

New `tests/verify/verify_whisper_model_download_script.py`:
- The script resolves the correct Hugging Face repo id for each
  documented size string (a pure string-mapping check, no real
  network call needed for this part).
- Running the script with an unreachable/fake Hugging Face endpoint
  (e.g. pointing `HF_ENDPOINT` at a real local server that always
  404s, or a deliberately wrong host) produces the documented clear
  error rather than a raw traceback — real subprocess invocation, real
  failure, not mocked.
- The default cache location the script/module resolve to is
  confirmed to be outside `Path(__file__).resolve().parents[...]`
  (the repo root) — a real assertion against real `Path` values, not
  an assumption.
- `git status --porcelain` after a real (network-permitting, if CI
  allows; otherwise skip with a clear skip reason logged, matching
  this repo's "make a note in the plan that it was skipped" rule for
  steps needing an unavailable resource) run of the script shows no
  new tracked-or-untracked files inside the repo tree.
- `design-docs/whisper-model-setup.md` exists and mentions both the
  script and the manual `huggingface-cli` backup path.
- Full `tests/verify/` regression suite.
