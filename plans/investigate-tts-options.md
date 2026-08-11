# Plan: TODO 676a133 — investigate offline TTS options

Moved from `PARKINGLOT.md`'s "Research offline text-to-speech (TTS)
options" entry. Research what a local/offline TTS engine for this
project would look like -- the reverse direction of the already-shipped
local speech-to-text work (`src/desk/speech.py`, TODOs
`f9d2dc7`/`1cd0ca2`/`b32fb81`, `mlx-whisper`-based). No application code
changes and no concrete use case yet (unlike the STT work, which had the
Voice Input widget as a clear target) -- a pure research write-up for a
future Claude instance (or the user) to act on when/if a use case
emerges.

## Approach

1. Survey candidate offline/local TTS libraries usable from Python,
   covering both a general cross-platform option and anything
   Apple-Silicon-optimized comparable to `mlx-whisper`'s own story
   (`design-docs/whisper-model-setup.md` notes MLX is Apple-Silicon-only
   with no Intel/other-platform fallback) -- e.g. `mlx-audio`/Kokoro,
   Piper, Coqui/XTTS, and macOS's own built-in `say`/`AVSpeechSynthesizer`
   as a zero-dependency baseline.
2. For each, note: license (of the library/toolkit *and* the model
   weights separately, since they can differ -- e.g. Coqui XTTS's
   non-commercial CPML weight license vs. its MPL 2.0 toolkit license),
   approximate model/download size, and voice quality as reported by
   others (no local listening test planned -- this is a landscape
   survey, not a hands-on benchmark).
3. Compare against this project's own dependency posture (`CLAUDE.md`'s
   "avoid adding dependencies, prefer bespoke solutions,"
   `design-docs/architecture.md`'s framing of that as being about
   *unnecessary* dependencies specifically, not refusing a necessary one)
   the same way `mlx-whisper` itself was judged unavoidable for STT
   (TODO `1cd0ca2`).
4. Write `investigations/tts_options.md` with a findings table and a
   ranked recommendation for whoever picks this up next -- explicitly
   not committing to one library, since there's no concrete use case yet
   to design against.

## Verification

No application code changes, so no new `tests/verify/` script. Confirm
the new file exists and the full regression suite still passes (nothing
should have changed, but check anyway per the standard process).
