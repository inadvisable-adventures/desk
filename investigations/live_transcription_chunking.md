# Investigation: is something closer to live transcription possible by breaking audio into smaller chunks? (TODO `8a5ea2b`)

Read `mlx_whisper`'s actual `transcribe()` source
(`.venv/lib/python3.13/site-packages/mlx_whisper/transcribe.py`,
version 0.4.3 as currently pinned) rather than assuming from upstream
Whisper docs, then ran a real experiment against this project's own
default model (`mlx-community/whisper-large-v3-turbo`) and a real
synthesized utterance -- not just read about the theory.

## Short answer

**Possible, but only via repeated full-buffer re-transcription, not a
true streaming/incremental API** -- `mlx_whisper` has no hook to feed
it audio incrementally or resume a partial decode. Doing this yourself
(call `transcribe()` again every second or so on the growing captured
buffer) is technically workable at roughly real-time cadence for a
short utterance (confirmed: each call costs about the same wall-clock
time regardless of how much audio is fed in, as long as it is under
Whisper's own 30-second window) -- but the *early* partial results are
genuinely unstable: words near the trailing edge of the buffer get
revised as more audio/context arrives, a real, visible "flicker"
problem any real implementation would need to design around, not just
a latency question.

## What `mlx_whisper.transcribe()` already does internally

`transcribe()` already processes its input in a sliding-window loop
internally (`transcribe.py`, the `while seek < seek_clip_end:` loop) --
audio is padded/trimmed and consumed in (up to) 30-second windows
(`N_FRAMES`/`N_SAMPLES`, Whisper's own fixed architecture window),
`seek` advancing based on where each decoded segment actually ended,
with `condition_on_previous_text` (default `True`) carrying prior
tokens forward as decoding context for later windows in the *same*
call. This is the core Whisper decode algorithm doing this already --
not something to reimplement.

What it does **not** do: accept audio incrementally. The whole buffer
is mel-spectrogrammed once, up front
(`mel = log_mel_spectrogram(audio, ...)`, `transcribe.py:150`), from a
single in-memory array passed in at call time. There is no "call this
again with just the new samples and continue from where you left off"
entry point -- every call starts fresh from the beginning of whatever
array it's given.

## Real experiment: transcribing a growing prefix of the same recording

Synthesized (real macOS `say`, not a hand-crafted tone) a ~5.6-second
sentence, then called `mlx_whisper.transcribe()` repeatedly on
successively longer prefixes of the *same* underlying audio array (1s,
2s, 3s, ... up to the full clip), against the already-warmed default
model:

```
total audio length: 5.64s
sentence: "The quick brown fox jumps over the lazy dog while the sun
sets slowly behind the distant purple mountains"

[ 1.00s audio] (0.98s to transcribe) -> " The quick brown fog"
[ 2.00s audio] (1.08s to transcribe) -> " The quick brown fox jumps over the lace"
[ 3.00s audio] (1.00s to transcribe) -> " The quick brown fox jumps over the lazy dog while the sun"
[ 4.00s audio] (1.01s to transcribe) -> " The quick brown fox jumps over the lazy dog while the sun sets slowly behind"
[ 5.00s audio] (1.02s to transcribe) -> " ...the distant purple moon."
[ 6.00s audio] (1.01s to transcribe) -> " ...the distant purple mountains."
[ 7.00s audio] (1.01s to transcribe) -> " ...the distant purple mountains." (unchanged)
[ 8.00s audio] (1.02s to transcribe) -> " ...the distant purple mountains." (unchanged, padded beyond real audio)
[ 5.64s audio] (1.01s to transcribe) -> " ...the distant purple mountains." (the real full clip)
```

(Full sentence elided as `...` above where unchanged from the previous
row; the actual script printed it in full every time.)

Two real findings from this, not assumed:

1. **Per-call latency is roughly constant (~1.0-1.1s) regardless of
   prefix length**, as long as the prefix stays under the model's
   30-second window -- consistent with the padding/single-window
   behavior above. This means a naive "re-transcribe the growing
   buffer every ~1 second" polling loop is roughly sustainable in
   real time for a short dictation: each call costs about as long as
   the interval between calls. It would **not** stay sustainable
   indefinitely, though -- past 30 seconds of audio, `mlx_whisper`'s
   own multi-window loop starts doing real additional work per extra
   30-second chunk, so total per-call cost would start climbing again
   for a long recording re-transcribed from t=0 every time.
2. **Partial results genuinely flicker.** The trailing word(s) of an
   in-progress utterance are frequently wrong or truncated
   mid-word ("fog" for "fox", "the lace" for "the lazy dog") until
   enough audio arrives for the model to disambiguate -- confirmed
   directly, not a hypothetical. It stabilizes once the buffer
   contains the whole utterance (matches by 5-6s of this 5.64s clip)
   but a live UI built on this would need to visibly show uncommitted/
   revisable text near the cursor, the same way real dictation UIs
   (e.g. macOS's own Dictation, or browser Web Speech API
   implementations) distinguish "interim" from "final" results --
   this is a real design problem to solve, not just an engineering
   latency one.

## What this would take to actually build (not designed, not committed to)

- No incremental/streaming hook exists in the installed `mlx_whisper`
  version to reuse -- any implementation is "re-transcribe the growing
  buffer on a timer," full stop. This is real, extra compute on every
  tick (proportional to buffer length once past 30s), not free.
- The Voice Input widget (`widgets/voice_input/widget.py`) and the
  Claude (Desk) mic button (`widgets/claude_desk/widget.py`, TODO
  `fe7d8f2`) both currently transcribe once, after the user explicitly
  stops recording -- wiring in a live-updating variant would need a
  visual "interim vs. final" distinction in the text widget (not just
  swapping in new text on a timer) to avoid the flicker above reading
  as broken.
- `desk.speech.transcribe()` (TODO `1cd0ca2`) and `desk.voice_capture
  .MicRecorder` (TODO `fe7d8f2`) would both need a genuinely different
  API shape for this (something that can be invoked repeatedly against
  a still-growing buffer, distinct from today's "record fully, then
  transcribe once" flow) -- a real redesign of both, not an additive
  change.

Given the real, non-trivial UX design question (how to show
interim/flickering results without it looking broken) and the
real, unbounded-growth compute cost for anything longer than a short
dictation, this is not filed as a ready-to-implement TODO -- it's a
"here's what's actually true if this gets picked up" reference for
whoever revisits the idea, matching how `PARKINGLOT.md`'s own
"research offline TTS options" item was left as pure research without
forcing a premature follow-up TODO.
