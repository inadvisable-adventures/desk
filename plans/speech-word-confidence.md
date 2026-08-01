# Expose per-word transcription confidence (TODO `76949eb`)

## Summary

`mlx_whisper.transcribe()` already computes real confidence signal —
per-segment `avg_logprob`/`no_speech_prob`/`compression_ratio` always,
and (when called with `word_timestamps=True`) a per-segment `"words"`
list of `{word, start, end, probability}` — but `desk.speech
.transcribe()` (TODO `1cd0ca2`) throws all of it away and returns only
the plain joined text. This plan changes `transcribe()` to return the
per-word confidence alongside the text, and has the Voice Input widget
(TODO `b32fb81`) visually flag low-confidence words in its result box,
so a misrecognition like "hit the thing" → "hit the button" is at
least flagged as uncertain rather than looking identical to a
high-confidence transcription.

## Affected files

- `src/desk/speech.py` — `transcribe()`'s return type and the
  `mlx_whisper.transcribe()` call.
- `widgets/voice_input/widget.py` — consumes the new return type,
  highlights low-confidence words.
- `tests/verify/verify_speech_transcription.py` — update for the new
  return type; add real-audio coverage of the confidence values
  themselves.
- `tests/verify/verify_voice_input_widget.py` — add coverage of the
  highlighting behavior.
- `LEARNINGS.md` — only if something during implementation turns out
  to be non-obvious (e.g. anything about how `add_word_timestamps`
  buckets punctuation into neighboring words — see open question
  below); not assumed up front.

## Design decisions

### Return shape: a small dataclass, not a bigger dict

Add to `src/desk/speech.py`:

```python
@dataclass(frozen=True)
class WordConfidence:
    word: str
    probability: float  # 0.0-1.0, mlx_whisper's own per-word score

@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    words: list[WordConfidence]
```

`transcribe()` changes from `-> str` to `-> TranscriptionResult`. This
is a breaking change to `transcribe()`'s signature, but it has exactly
one caller in the whole codebase (`widgets/voice_input/widget.py`) —
per this project's CLAUDE.md-adjacent conventions there's no reason to
keep a str-returning shim around for a single internal call site.
`.text` is still `result["text"].strip()`, unchanged.

Rejected alternative: returning `mlx_whisper`'s raw `result` dict
(or its `"segments"`) directly. That leaks an untyped, library-specific
shape into a module boundary that's supposed to hide `mlx_whisper` as
an implementation detail (see the module's own docstring/TODO
`1cd0ca2`'s framing) — the caller would need to know about segments at
all, when all it actually wants is "the text" and "a flat list of
words with confidence." Flattening segments into one `words` list here
is a small amount of work that keeps that boundary intact.

### Always request word timestamps

`transcribe()` will always pass `word_timestamps=True` rather than
taking an opt-in parameter — there's exactly one caller today and it
always wants this. Cost: `word_timestamps=True` runs an extra
cross-attention/DTW alignment pass after decoding, so every
transcription gets measurably slower. Needs to be measured during
implementation (real timing, before/after, on this project's own
`large-v3-turbo` default) and noted in the TODO writeup — if the
regression is large enough to hurt the widget's felt responsiveness,
switch to a `include_words: bool = True` parameter instead so a
hypothetical future non-UI caller (batch transcription, say) could
opt out. Default to the simpler always-on version unless that
measurement says otherwise.

### Surfacing confidence in the widget: highlight, don't block

`widgets/voice_input/widget.py`'s `_text_edit` is a `QPlainTextEdit`.
Rather than switching to `QTextEdit`/rich text, use
`QPlainTextEdit.setExtraSelections()` (works directly on
`QPlainTextEdit`, no widget-type change) to apply a background color
to the character range of every word whose `probability` is below a
threshold constant (e.g. `LOW_CONFIDENCE_THRESHOLD = 0.5` — mirrors
`no_speech_threshold`'s default of `0.6` used elsewhere in
`mlx_whisper` as "this is roughly where the model itself stops
trusting its own output," picked as a starting point to revisit once
real usage data (i.e. the user's own future "was this actually wrong"
feedback) exists).

Locating each word's character offset in the final text: build the
plain-text string by joining `words[i].word` in order (matching how
`mlx_whisper` already concatenates them into `result["text"]` — confirm
this directly against a real transcription rather than assuming
whitespace/punctuation joins line up losslessly) and track running
offsets while doing so, rather than using `str.find()` per word (fails
on repeated words).

Not in scope for this plan (explicitly deferred, not forgotten):
- A tooltip/hover showing the exact numeric probability per word —
  real value, but requires mouse-position-to-text-offset handling
  (`cursorForPosition` + `QToolTip.showText`) that's a separable UI
  chunk on top of the highlighting itself. Flag as a natural follow-up
  once highlighting alone is confirmed to look right.
- Doing anything with segment-level `no_speech_prob`/`avg_logprob`
  (e.g. an overall "this whole clip was noisy" banner) — the user
  specifically asked about individual words being wrong, which segment
  -level stats don't localize. Worth a future TODO if it comes up
  again, not bundled into this one.

### Open question to resolve during implementation, not blocking planning

Whether `mlx_whisper`'s word list attaches leading/trailing punctuation
to the word it's adjacent to (its `prepend_punctuations`/
`append_punctuations` parameters suggest yes) needs confirming directly
against real output before writing the offset-tracking join logic above
— if punctuation is its own list entry instead, the join algorithm
needs a small adjustment (skip highlighting bare punctuation entries
even if their probability is low, since a low-confidence comma isn't
meaningful to the user the way a low-confidence word is).

## Step-by-step implementation

1. In `src/desk/speech.py`: add `WordConfidence`/`TranscriptionResult`
   dataclasses (needs `from dataclasses import dataclass`). Change
   `transcribe()` to call `mlx_whisper.transcribe(samples,
   path_or_hf_repo=MODEL_REPO, word_timestamps=True)`, flatten
   `result["segments"][*]["words"]` into one ordered `list
   [WordConfidence]`, and return `TranscriptionResult(text=result
   ["text"].strip(), words=...)`.
2. Confirm directly (real transcription, not assumed) how punctuation
   is bucketed into `words` entries — resolve the open question above
   before writing the join/offset logic.
3. In `widgets/voice_input/widget.py`:
   - `_transcribe_in_background`/the `_Relay.finished` signal now carry
     a `TranscriptionResult | None` instead of `str | None`.
   - `_on_transcription_finished`: set the plain text from `.text` as
     today, then compute character ranges for words below
     `LOW_CONFIDENCE_THRESHOLD` and apply them via
     `self._text_edit.setExtraSelections(...)`.
   - Re-run `_update_copy_button_enabled`/copy behavior unaffected
     (still plain `.toPlainText()`, no markup leaks into the copied
     text).
4. Update `tests/verify/verify_speech_transcription.py`: adjust
   existing assertions for the new `TranscriptionResult` return type;
   add a real (no mocking) check that a known utterance produces a
   non-empty `words` list with `0.0 <= probability <= 1.0` for each
   entry, and that concatenating `words[*].word` reproduces `.text`
   (validating the offset-tracking assumption from design decisions
   above, not just asserting it).
5. Update `tests/verify/verify_voice_input_widget.py`: since real
   microphone/model-driven low-confidence output isn't reproducible on
   demand, drive `_on_transcription_finished` directly with a
   hand-built `TranscriptionResult` containing a deliberately
   low-probability word and confirm `setExtraSelections` was actually
   applied to the right character range — real Qt widget, injected
   data, not a mocked widget.
6. Measure real transcription latency before/after `word_timestamps
   =True` (per "Always request word timestamps" above) on this
   project's own default model; note the numbers in the TODO
   `76949eb` completion writeup regardless of outcome.
7. Run the full `tests/verify/` suite to confirm no regressions.

## Key tradeoffs

- Breaking `transcribe()`'s return type instead of adding a parallel
  `transcribe_with_confidence()` function: keeps one call site, one
  behavior, no risk of the plain-`str` path silently going stale next
  to a richer one nobody remembers to also update. Justified by there
  being exactly one caller today.
- Highlighting via `QPlainTextEdit.setExtraSelections()` instead of
  switching to `QTextEdit`: smaller diff, no rich-text/HTML round
  -tripping to reason about, and this project's CLAUDE.md already
  steers away from hand-built HTML/CSS in widget code where a simpler
  native mechanism exists.
- Fixed `LOW_CONFIDENCE_THRESHOLD` constant rather than a user-facing
  sensitivity setting: this is a first pass at making the signal
  visible at all: a config knob is easy to add later once there's a
  sense of whether the default threshold is even in the right
  ballpark.
