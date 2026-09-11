# Investigation: does our Whisper stack support prompting/lexicons for better recognition?

Read `mlx_whisper`'s actual `transcribe()`/`DecodingOptions` source
(`.venv/lib/python3.13/site-packages/mlx_whisper/transcribe.py` and
`decoding.py`, version 0.4.3 as currently pinned) rather than going
off memory of upstream OpenAI Whisper — this project vendors its own
local model via `mlx-whisper`, not OpenAI's hosted API, so the two can
diverge. Confirmed `src/desk/speech.py`'s `transcribe()` (its one
caller in this repo) does not currently pass any of this; nothing
found in `widgets/voice_input/` or `tests/` sets it either.

## Short answer

Yes, one mechanism: **`initial_prompt`**, a plain string passed straight
through to `mlx_whisper.transcribe()`. There is no separate
"lexicon"/word-boost/hotword-list feature — Whisper's architecture has
no such concept. `initial_prompt` is the only lever, and it works by
biasing the model's decoding context, not by hard-constraining output.

## How `initial_prompt` actually works (`transcribe.py:257-261`, `:296`)

```python
if initial_prompt is not None:
    initial_prompt_tokens = tokenizer.encode(" " + initial_prompt.strip())
    all_tokens.extend(initial_prompt_tokens)
...
decode_options["prompt"] = all_tokens[prompt_reset_since:]
```

It's tokenized once and prepended to `all_tokens`, the running token
history that gets fed back in as decoding context for *every* 30-second
window (via `condition_on_previous_text`, default `True`) — not just
the first one, despite the parameter's docstring saying "for the first
window." In practice it keeps influencing decoding for the whole clip
unless `condition_on_previous_text=False` or a high-temperature retry
resets `prompt_reset_since`.

This is context conditioning, the same trick as GPT-style prompting:
the model sees prior tokens and produces more-likely-consistent
continuations. It is **not** a hard constraint — it raises the
probability of matching vocabulary/style, it doesn't forbid other
output. Proper nouns, jargon, or an unusual spelling given in the
prompt are *more likely* to be transcribed correctly, not guaranteed.

The upstream docstring (`transcribe.py:124-127`) confirms the intended
use directly:

> Optional text to provide as a prompt for the first window. This can
> be used to provide, or "prompt-engineer" a context for
> transcription, e.g. custom vocabularies or proper nouns to make it
> more likely to predict those word correctly.

## Related but distinct: `prefix` (`decoding.py:104`, `:483-492`)

`DecodingOptions` also has a `prefix` field, reachable through
`transcribe()`'s `**decode_options` passthrough. Unlike `initial_prompt`,
`prefix` is injected as forced leading tokens of the *current* decode
call itself (concatenated directly onto the token sequence before
sampling starts), not just prior context. It's meant for forcing an
exact continuation (e.g. resuming a known partial transcript), not
general vocabulary hinting — the wrong tool for "here are some names
that might come up."

## What's NOT available

- No hotword/word-boost list (an array of strings with individual
  boost weights) — some ASR systems (e.g. cloud STT APIs) have this;
  Whisper's architecture doesn't.
- No true lexicon/pronunciation-dictionary mechanism.
- No per-word forced alignment to a known vocabulary at decode time.
  (The existing `WordConfidence`/`words` output in `speech.py` is
  *post-hoc* per-word confidence from the alignment pass, unrelated to
  input-side biasing.)

Everything context-related funnels through the one `initial_prompt`
string. It's the same shape of lever OpenAI's hosted Whisper API
exposes as its `prompt` parameter — unsurprising, since `mlx-whisper`
is a direct port of the same reference implementation.

## If we want to use this

`transcribe()` in `src/desk/speech.py` would need an `initial_prompt`
argument threaded through to its own `mlx_whisper.transcribe(...,
initial_prompt=...)` call. Practical notes for whoever picks this up:

- Keep it short. It consumes the same context window as everything
  else (`n_ctx // 2` tokens max per `decoding.py:490`); a long prompt
  gets silently truncated from the front.
- It's plain natural-language-ish text, not a structured list — e.g.
  `"Desk, Claude, Anthropic, mlx-whisper, TODO"` reads fine, there's no
  special syntax.
- Since `condition_on_previous_text` defaults to `True`, one
  `initial_prompt` keeps nudging every window of a long dictation, not
  just the first few seconds — good for consistent proper-noun spelling
  throughout, but also means a bad/irrelevant prompt keeps steering the
  whole transcription, not just the start.
