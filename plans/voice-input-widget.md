# Plan: TODO b32fb81 — Voice Input widget

From `PARKINGLOT.md`'s "Local speech-to-text (Whisper) for voice
input" item — the actual user-facing surface, built on TODO
`1cd0ca2`'s transcription module (which itself depends on TODO
`f9d2dc7`'s model download infrastructure existing and having been run
at least once).

## Scope decision: a self-contained widget, not a cross-widget dictation button

The parking lot item doesn't specify where transcribed text should
land. Rather than guessing at wiring a "dictate" affordance into every
existing text-entry surface (Scratch, Question, Todo item editor,
etc.) — a much larger, more invasive change touching many unrelated
widgets — this TODO delivers one new, independent widget, matching
this project's existing pattern of one focused capability per widget
(`git_diff`, `git_status`, `image_viewer`, etc. are all similarly
self-contained). It gives the feature a real, usable home immediately;
wiring dictation into other widgets' text fields is a natural, clearly
separable follow-up if wanted later, not something to fold in here
silently.

## `widgets/voice_input/widget.json`

```json
{
  "name": "Voice Input",
  "kind": "python",
  "entry": "widget.py",
  "capabilities": [],
  "default_size": { "width": 360, "height": 240 }
}
```

`kind: "python"` (not `"html"`) — this needs direct `QtMultimedia`
access for microphone capture, which is a Python/Qt concern, not
something to route through the Bridge API.

## `widgets/voice_input/widget.py`

`build() -> QWidget`, matching the existing `kind: "python"` contract
(`widgets/demo/widget.py`'s shape). Layout:
- A single toggle button: "● Record" / "■ Stop".
- A status label (idle / recording / transcribing / error).
- A read-only-until-transcribed, then editable `QPlainTextEdit`
  showing the transcription result.
- A "Copy" button (`QGuiApplication.clipboard().setText(...)`) —
  bespoke, no new dependency, Qt's own clipboard API.

### Audio capture

Use `QAudioSource` (PyQt6 `QtMultimedia`, already installed, no new
dependency) against the system default input device, at a format
`mlx-whisper`/`ffmpeg`-free decoding likes directly: 16 kHz mono
16-bit PCM (Whisper's own native rate; capturing at this rate up front
avoids needing a resampling step or an `ffmpeg` dependency later).
Write frames to a real temporary `.wav` file (Python's stdlib `wave`
module — no dependency) as they arrive, or buffer in memory and write
once on stop (buffering is simpler and recordings here are expected to
be short; revisit only if that proves wrong in practice).

On stop: close the WAV file, call `desk.speech.transcribe(path)` (TODO
`1cd0ca2`) on a background thread (`QThread`/`QRunnable` — this repo
already uses background threads elsewhere, e.g. `PythonWidgetHost`'s
own rebuild path, for a precedent of not blocking the Qt event loop
during real work) so the UI stays responsive during the (potentially
several-second) transcription call, then marshal the result back to
the main thread to populate the text edit. Delete the temporary WAV
file after transcription completes (success or failure) — nothing
audio-related should linger on disk any more than the model itself
does in the repo.

### Error handling

If `desk.speech.transcribe` raises `TranscriptionUnavailableError`
(TODO `1cd0ca2`), show that error's own message directly in the status
label/a dialog — it already names the download script and doc TODO
`f9d2dc7` produces, so no separate message needs to be authored here.

### macOS microphone permission

Real, concrete runtime consideration to verify during implementation,
not just code review: on macOS, the *first* real microphone access
from this process triggers a TCC permission prompt for whatever
process is actually running Desk (Terminal, or a packaged app bundle,
depending on how Desk is launched) — denying it silently yields empty/
silent audio rather than an exception in some Qt/Core Audio paths.
Implementation must confirm directly (by actually recording once in a
real run) what happens on both first-time-allow and a denied-permission
path, and surface a clear in-widget error for the denied case rather
than silently transcribing silence.

## Verification

New `tests/verify/verify_voice_input_widget.py`, following this
project's real-Qt-widget testing precedent (e.g.
`verify_svg_editor_widget.py`):
- `build()` returns a `QWidget` containing the expected child controls
  (record button, status label, text edit, copy button) — found by
  real Qt object tree traversal, not assumed structure.
- Clicking Record real-toggles button text/status and actually starts
  a `QAudioSource` (or a real, short, actual microphone-loopback/
  synthetic-tone capture if the test environment has no real
  microphone — confirm what's available in this project's CI/test
  environment before assuming a live mic is captureable there; note as
  a skip with reason if not).
- Stop triggers a real transcription call against a real short audio
  clip with known content (reuse or share the fixture from TODO
  `1cd0ca2`'s own verification) and the text edit ends up populated
  with the expected (normalized) text — real thread completion
  awaited via Qt's own signal/slot mechanism (e.g. `QSignalSpy` or a
  local event-loop `waitUntil`-style helper this repo may already use
  elsewhere — check `tests/verify/` for an existing pattern before
  inventing a new one).
- Copy button real-sets the system clipboard (`QGuiApplication
  .clipboard().text()` reads back what was set).
- The temporary WAV file is confirmed deleted after transcription
  completes.
- `TranscriptionUnavailableError` surfaces as a visible, real status
  message (force this path by pointing at a deliberately-uncached
  fake model repo for this one test only, not by mocking the
  transcription call's success path).
- Full `tests/verify/` regression suite.

## Note

`design-docs/architecture.md`'s widget catalogue/`custom-widget-
authoring.md` may be worth a short mention of this widget once built
(matching how other built-in widgets are documented there) — check
during implementation whether that catalogue is maintained per-widget
or left implicit; add an entry only if the existing convention calls
for one.
