# Voice input for the Claude (Desk) widget (TODO `fe7d8f2`) (COMPLETED)

## Summary

Add a mic/record button to `ClaudeDeskWidget`'s prompt row
(`widgets/claude_desk/widget.py`, TODO `a596dbf`) so a prompt can be
dictated the same way the standalone Voice Input widget (TODO
`b32fb81`) already supports, via `desk.speech.transcribe` (TODO
`1cd0ca2`), instead of only ever typing into `_prompt_input`.

The mic-capture-and-transcribe pipeline currently lives entirely
inside `widgets/voice_input/widget.py` (`QAudioSource` setup, WAV
writing, background-thread transcription). Since widget directories
can't import each other, and this capability is now needed by a
*second* widget, this plan extracts it into a new shared module,
`src/desk/voice_capture.py` — the same "shared widget logic lives in
`desk.` proper" pattern `desk.terminal_widget` (extracted from the
Console widget for the original Claude widget to reuse) and
`desk.claude_session` already established, rather than pasting a
second, independently-drifting copy of ~80 lines of `QAudioSource`/
threading logic into `claude_desk/widget.py`.

## Affected files

- New `src/desk/voice_capture.py` — `MicRecorder(QObject)`: owns the
  `QAudioSource` lifecycle, WAV writing, and background-thread
  transcription via `desk.speech.transcribe`, reporting back through
  `pyqtSignal`s. Extracted near-verbatim from
  `widgets/voice_input/widget.py`'s existing `_write_wav`/
  `_transcribe_in_background`/`_start_recording`/`_stop_recording`/
  `_on_audio_ready_read`/`_process_captured_audio`. Owns capture +
  transcription only, no UI (no buttons/labels/text edit) — each
  widget builds its own UI on top.
- `widgets/voice_input/widget.py` — refactored to use `MicRecorder`
  instead of owning the capture logic directly. Its own UI (record/
  stop button text, status label, low-confidence highlighting via
  `word_offsets`/`setExtraSelections`, copy-to-clipboard) is
  unchanged — this is a pure extraction, not a behavior change, and
  the existing `tests/verify/verify_voice_input_widget.py` coverage
  must keep passing basically as-is (confirming the refactor didn't
  change behavior), with internal-shape assertions updated for the
  new structure.
- `widgets/claude_desk/widget.py` — a new mic button
  (`_mic_button`, "🎤"/"■" toggle, mirroring Voice Input's own
  "●"/"■" record/stop convention) placed to the left of
  `_prompt_input` in the prompt row. On stop, the transcribed text is
  set into `_prompt_input` (**not** auto-sent) — the user reviews/
  edits it and hits Send/Enter themselves, exactly like a typed
  prompt. No low-confidence-word highlighting here: `_prompt_input` is
  a `QLineEdit`, which has no `QTextEdit.ExtraSelection`-style
  per-character formatting mechanism the way `QPlainTextEdit` does —
  out of scope for this item (raising the confidence-highlighting
  mechanism to work on `QLineEdit` too, or switching `_prompt_input`
  to a richer widget, is a separable follow-up, not bundled in here).
- New `tests/verify/verify_voice_capture.py` — real, non-mocked
  coverage of `MicRecorder` directly (real mic capture, real
  synthesized-speech transcription, real WAV cleanup, real error
  paths), the successor to the capture-specific portions of
  `verify_voice_input_widget.py`'s existing coverage.
- `tests/verify/verify_voice_input_widget.py` — updated for the new
  internal structure (drives `widget._mic_recorder` instead of
  `widget._audio_source` directly where the refactor changes what's
  reachable), full regression re-confirmed.
- `tests/verify/verify_claude_desk_widget.py` — new checks: a real
  mic-button click → injected synthesized PCM (matching Voice Input's
  own test technique, since a real, unattended test environment can't
  reliably produce meaningful live microphone content on demand) →
  `_prompt_input` populated with the transcribed text, confirmed
  *not* auto-sent (no new turn started until the user explicitly hits
  Send).
- `TODO.md` — mark `fe7d8f2` `COMPLETED`.

## Design decisions

- **`MicRecorder` owns exactly capture + transcription, no UI at
  all.** Each widget keeps deciding its own button text/status
  presentation; the shared piece is only "record mic audio, produce a
  `TranscriptionResult`."
- **Signals**: `recording_started`, `recording_stopped` (fires once
  capture actually stops, before transcription begins — lets a caller
  show a "Transcribing..." status distinct from "Recording..."), and
  `transcription_finished(result: TranscriptionResult | None, error:
  str | None)` — the same two-value shape
  `widgets/voice_input/widget.py`'s existing `_Relay.finished` already
  uses.
- **Ownership/cleanup**: `MicRecorder` is itself a `QObject`;
  instantiated as `self._mic_recorder = MicRecorder(self)` inside each
  widget, giving it normal Qt parent-child cleanup for free — no
  special teardown wiring needed beyond what already exists.
- **Claude (Desk)'s transcribed text lands in the prompt box, not
  auto-sent.** Mirrors how a typed prompt already works (nothing is
  sent until Send/Enter) and gives the user a chance to fix a
  misrecognition before it goes to Claude — especially relevant given
  TODO `76949eb` already found real misrecognitions happen.
- **No low-confidence highlighting in the Claude (Desk) prompt box**:
  `QLineEdit` has no per-character rich formatting mechanism
  equivalent to `QPlainTextEdit.setExtraSelections()`. Not solved
  here.
- **Not in scope**: exposing recording state in the widget's `_status_label`
  in any way beyond simple text (no dedicated recording-specific UI
  chrome beyond the mic button's own toggled label); queuing multiple
  dictated prompts (that's the separate, already-filed TODO
  `e1f6391`, about queuing generally, not specific to voice).

## Step-by-step implementation

1. Create `src/desk/voice_capture.py` with `MicRecorder`, moving the
   relevant logic out of `widgets/voice_input/widget.py` largely
   unchanged (module-level `_write_wav`/`_transcribe_in_background`
   become methods/module-level helpers of the new module instead).
2. Refactor `widgets/voice_input/widget.py` to construct and drive a
   `MicRecorder` instead of managing `QAudioSource` itself. Confirm
   its own existing verify coverage still passes (behavior-preserving
   refactor, not a rewrite).
3. Add the mic button + wiring to `widgets/claude_desk/widget.py`,
   using the same `MicRecorder`.
4. Write `tests/verify/verify_voice_capture.py` for the new shared
   module directly.
5. Update `tests/verify/verify_voice_input_widget.py` for the new
   internal shape.
6. Add new checks to `tests/verify/verify_claude_desk_widget.py` for
   the Claude (Desk) widget's mic button.
7. Run the full `tests/verify/` regression suite.
8. Mark `TODO.md`'s `fe7d8f2` entry `COMPLETED` with a verification
   writeup; mark this plan's title `(COMPLETED)`.

## Key tradeoffs

- Refactoring an already-shipped, already-tested widget
  (`voice_input`) as part of landing a feature for a *different*
  widget is a real, deliberate cost — accepted because the
  alternative (a second hand-copied mic-capture implementation) is a
  worse, compounding cost the moment either copy needs a bugfix, and
  because this project already has clear precedent for exactly this
  kind of extraction once a second widget needs the same capability.
- No confidence highlighting in Claude (Desk)'s prompt box: accepted
  as a real gap for now rather than switching `_prompt_input` to a
  richer widget just to support it — the plan for TODO `8df6797`
  (multi-line prompt input) may be a more natural point to revisit
  this, since it's already considering a `_prompt_input` widget-type
  change for an unrelated reason.
