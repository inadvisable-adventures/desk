# Investigation: offline/local text-to-speech (TTS) options

**TODO `676a133`.** Survey (as of August 2026) of the offline/local TTS
landscape usable from Python — the reverse direction of the
already-shipped local speech-to-text work (`src/desk/speech.py`, TODOs
`f9d2dc7`/`1cd0ca2`/`b32fb81`, `mlx-whisper`-based). This is a pure
research write-up, same as `PARKINGLOT.md`'s original framing: no
concrete use case is driving it yet (unlike the STT work, which had the
Voice Input widget as a clear target), so nothing here is a
recommendation to implement anything right now — it's tradeoffs for
whoever picks this up once a real use case exists. No application code
changed.

Method: external research (library docs, GitHub repos, Hugging Face
model cards, license texts), not hands-on installation/benchmarking —
matches the "figure out real options and their tradeoffs" scope
`PARKINGLOT.md` asked for, not a listening test. This space moves fast
(Coqui's company shut down in Jan 2024; Kokoro hit #1 on the TTS Arena
leaderboard in Jan 2026; Apple Silicon support landed in `mlx-audio`
only in the last few weeks as of this writing) — treat specifics below
as a snapshot, not a permanent ranking.

## The comparison point: how `mlx-whisper` was judged (TODO `1cd0ca2`)

Two things made `mlx-whisper` the obvious (only real) choice for local
STT, both worth checking for a TTS equivalent:

1. **No bespoke alternative exists.** There's no way to run a
   Whisper-quality speech recognizer without *some* real ML model —
   `design-docs/architecture.md`'s framing of `CLAUDE.md`'s dependency
   aversion is explicitly about avoiding *unnecessary* dependencies, not
   refusing a necessary one once a bespoke path is genuinely
   impractical. The same logic applies to TTS *if* a neural voice is the
   actual goal — but unlike STT, TTS has a real zero-dependency bespoke
   option (see macOS `say`, below), so the "is a new dependency even
   needed" question doesn't resolve the same way by default.
2. **Apple-Silicon-optimized, first-party-adjacent.** `mlx-whisper`
   lives in `ml-explore`'s own examples tree (the org that ships MLX
   itself) — effectively a reference implementation, not a third-party
   wrapper. `design-docs/whisper-model-setup.md` notes this only runs on
   Apple Silicon at all (MLX has no Intel/other-platform fallback), which
   Desk has already accepted as a real platform constraint for its voice
   features.

## Candidates

| Option | License (toolkit / weights) | Size | Apple-Silicon story | Notes |
|---|---|---|---|---|
| macOS `say` / `AVSpeechSynthesizer` | Apple system framework, no new dependency | 0 (already on every Mac) | Native, but not MLX-accelerated — a always-resident OS service, not a model Desk would run itself | Zero-dependency baseline |
| `mlx-audio` + Kokoro-82M | MIT / Apache 2.0 | ~300MB, 82M params | Direct MLX analog to `mlx-whisper`, third-party (not `ml-explore`-org) | Closest match to the STT precedent |
| Piper | MIT (archived) or GPL-3.0 (active fork) / MIT-era weights | ~75MB per voice (~15M params) | None — plain ONNX/CPU, runs anywhere including Apple Silicon | General cross-platform option |
| Coqui XTTS v2 | MPL 2.0 (toolkit) / **CPML, non-commercial** (weights) | Large (multi-GB, PyTorch) | None — PyTorch/MPS, no MLX optimization | Best quality/voice-cloning, wrong license shape for this project |

### macOS `say` / `AVSpeechSynthesizer` — zero-dependency baseline

Already installed on every Mac; nothing to download, nothing to add to
`pyproject.toml`. Two integration levels:

- **Trivial**: `subprocess.call(["say", text])` — literally the
  "bespoke solution" `CLAUDE.md` asks to prefer, no new dependency at
  all. No programmatic control beyond fire-and-forget (no word-boundary
  callbacks, no easy way to know when speech finishes without polling
  the process).
- **Fuller control**: `AVSpeechSynthesizer` (or the deprecated
  `NSSpeechSynthesizer`) via a native AppKit bridge — gives
  start/pause/word-boundary delegate callbacks, but means writing (or
  depending on) an Objective-C/Swift/PyObjC bridge layer, not a pure-
  Python call.

Since macOS Sonoma, the "Enhanced"/"Premium" system voices are neural
quality with sub-100ms start latency, fully on-device — genuinely
competitive with the small open models below for a short-utterance use
case. Caveat: the higher-quality voice packs are an extra one-time OS
download from System Settings, not something a script can silently
fetch — a real UX gap if Desk wanted to guarantee voice quality out of
the box.

### `mlx-audio` + Kokoro-82M — the direct `mlx-whisper` analog

[`Blaizzy/mlx-audio`](https://github.com/Blaizzy/mlx-audio) is a TTS/
STT/STS library built on MLX itself, `pip install mlx-audio`, MIT
licensed. Its flagship small model, **Kokoro-82M**
([hexgrad/Kokoro-82M on Hugging Face](https://huggingface.co/hexgrad/Kokoro-82M)),
is 82M parameters (~300MB), **Apache 2.0** weights — free for commercial
and personal use, no ambiguity. Reportedly hit #1 on the TTS Arena
leaderboard in January 2026, beating models 10–100x its size; American
English voices are described as natural/expressive for the size. Ships
with dozens of voice presets (~54, per `mlx-audio`'s own docs) and some
multilingual support. `mlx-audio` also supports quantization (3–8 bit)
and other models (Qwen3-TTS, Dia, CSM) for anyone wanting to trade up in
quality/size later.

The genuine gap vs. `mlx-whisper`: `mlx-whisper` lives inside
`ml-explore`'s own repo (Apple's MLX team's own examples tree) —
`mlx-audio` is an independent third-party project (maintainer
"Blaizzy"), actively developed but without that same first-party-adjacent
provenance. Worth weighing if Desk cares about that distinction the way
it implicitly already relied on it for `mlx-whisper`.

### Piper — the general cross-platform option

[Piper](https://github.com/rhasspy/piper) (originally Rhasspy team) is a
small (~15M param, ~75MB per voice) ONNX/VITS model, CPU-only, no MLX/
GPU dependency at all — runs identically on Apple Silicon, Intel, Linux,
even a Raspberry Pi 4 in real time. Over 100 voices across 35+ languages.
This is the actual "general cross-platform option (vs. Apple-Silicon-
specific)" `PARKINGLOT.md`'s original item asked about.

License is the one messy point: the original `rhasspy/piper` repo (MIT)
is now archived; active development continues in a GPL-3.0 fork/
successor. The older MIT-era weights and voices reportedly remain usable
independently of which code trains/serves them, but this needs a closer
read of the actual repo state before relying on it — flagged here as an
open question, not resolved by this pass.

### Coqui XTTS v2 — best quality, wrong license for this project

Coqui Inc. (the company) shut down in January 2024, but the code/model
stay downloadable and a community fork keeps `pip install TTS` working
on current Python/PyTorch. XTTS v2 does voice cloning from a ~6-second
sample across 17 languages — the highest-quality, most capable option
surveyed here. The license is the disqualifying issue for Desk
specifically: the **toolkit** is MPL 2.0 (fine), but the **XTTS v2
model weights** are released under Coqui's own CPML (Coqui Public
Model License), which is **non-commercial only** — and since Coqui Inc.
no longer exists, there's no one left to sell a commercial weight
license even if wanted. Desk's own `LICENSE` is MIT and the project is
a general-purpose, freely-distributable tool, not a closed internal
app — bundling or defaulting to a non-commercial-only model would be a
real mismatch, not just a formality. Also meaningfully heavier
(multi-GB PyTorch model, no MLX acceleration, GPU/MPS strongly
preferred for real-time use) than either Kokoro or Piper.

## Answering the original question directly

> "whether anything comparable to `mlx-whisper`'s Apple-Silicon-optimized
> story exists for TTS specifically"

**Yes, with a caveat.** `mlx-audio` + Kokoro-82M is a real, current,
permissively-licensed (MIT/Apache 2.0) MLX-native analog — same
framework, same Apple Silicon acceleration story, comparable ease of
`pip install`. The caveat is provenance: it's a third-party project, not
part of `ml-explore`'s own org the way `mlx-whisper` is, so it carries a
bit more "is this actively maintained a year from now" risk than the STT
side of this already accepted.

## If this becomes a real feature (not a recommendation — just the shape of the decision)

No use case exists yet to design against, so this isn't a pick — just
what the tradeoff looks like whenever one shows up:

- If the need is "read this text aloud, occasionally, decent quality" —
  macOS `say`/`AVSpeechSynthesizer` costs zero new dependencies and
  matches `CLAUDE.md`'s dependency aversion most directly of any option
  here; the honest downside is thinner programmatic control (no clean
  word-boundary events without an AppKit bridge) and no guarantee the
  best-quality system voices are already downloaded.
- If the need is closer to Voice Input's own bar (a real, controllable,
  good-quality model Desk fully owns) — `mlx-audio` + Kokoro-82M is the
  closest match to how the STT side was already decided, with clean
  licensing (unlike XTTS) and genuine Apple Silicon acceleration
  (unlike Piper).
- **Rule out Coqui XTTS v2** for anything Desk would ship or default to,
  given the non-commercial-only weight license — worth keeping in mind
  purely as a reference point for "best achievable quality," not as a
  candidate.
- Piper's cross-platform reach only matters if Desk ever needs TTS to
  work on non-Apple-Silicon hardware — not true of any current Desk
  voice feature, so this is the lowest-priority candidate unless that
  platform constraint changes first.
