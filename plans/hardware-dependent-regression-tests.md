# Properly integrate hardware-dependent regression tests (TODO `b2ab79f`)

## Summary

Several `tests/verify/` scripts exercise `desk.voice_capture.MicRecorder`
end to end, which means they start a real `QAudioSource` against the
machine's actual default microphone as part of running the normal
regression sweep (`.venv/bin/python3 tests/verify/*.py`). This was
audibly/visibly activating the system mic every time the full suite
ran, which isn't wanted -- these were disabled (the project's standard
`disabled_` prefix convention) as an immediate fix:

- `tests/verify/disabled_verify_voice_capture.py` (previously
  `verify_voice_capture.py`) -- every test in the file starts real
  capture, so the whole file was renamed.
- `tests/verify/disabled_verify_voice_input_widget_mic.py` -- split out
  of `tests/verify/verify_voice_input_widget.py`, which keeps its
  other, mic-free tests (widget.json shape, control-tree structure,
  `word_offsets` against real transcription output, low-confidence
  highlighting) running normally.
- `tests/verify/disabled_verify_claude_desk_widget_mic.py` -- split out
  of `tests/verify/verify_claude_desk_widget.py`, same shape: the rest
  of that file's coverage (session/permission/queueing/window-wiring)
  keeps running normally.

That's the immediate fix. This TODO is the follow-up: decide how
coverage like this should actually be integrated long-term, rather
than leaving it disabled indefinitely (which is a real, if smaller,
coverage gap -- these tests have caught real bugs before, e.g. TODO
`fe7d8f2`'s `_process_captured_audio()`-vs-`stop()` bug).

## Affected files

Not yet known precisely -- depends on which direction is chosen (see
Status below). Candidates: the three `disabled_*` files above (either
renamed back, rewritten to mock the hardware layer, or left as
manually-run scripts); possibly a new `tests/verify/README.md` section
documenting an "occasionally run these by hand" category if that ends
up being the chosen shape; possibly `desk/voice_capture.py` itself, if
a mockable seam is added there.

## Step-by-step implementation

Not written -- blocked on the open questions below.

## Status

Blocked on real answers, not just a judgment call this session should
make unilaterally -- recorded in `QUESTIONS.md`. The core tension: real
hardware capture is exactly the kind of thing this project's own
verification philosophy prefers (`tests/verify/README.md`,
`development-process.md`'s emphasis on real, non-mocked
verification throughout this whole session's work) -- but it has a
real, undesirable side effect (activating the mic) that plain business
-logic tests don't have, so the usual "just always run it" default
doesn't obviously apply here the same way.
