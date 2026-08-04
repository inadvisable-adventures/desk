# Questions with optional answers

## TODO `b44e8ba`: segfault while interacting with the Desk picker -- need a reproduction

The reported crash (`Segmentation fault: 11`, no Python traceback) has
no captured repro steps beyond "interacting with the Desk picker" after
opening a `.desk` file. Code review (see
`plans/fix-desk-picker-segfault.md`) didn't turn up an obvious cause.

- What was the exact interaction right before the crash -- clicking the
  name label, clicking the directory label, just hovering, or something
  else (e.g. a trackpad gesture happening at the same time)?
- Does it reproduce consistently, or was it a one-off?
- Is there a macOS crash log for it (Console.app's "Crash Reports", or
  `~/Library/Logs/DiagnosticReports/`) with a real native stack trace?
  That would let this be root-caused directly instead of guessed at.

(Answer: resolved without a direct answer to the questions above --
two later crash reports (TODO 4716585, TODO 8c9436b) provided full
macOS crash logs for what turned out to be the same crashing call
chain inside Qt's own QListWidget mouse-event handling
(QAbstractItemView::mouseReleaseEvent), both traced to the same root
cause: a WA_DeleteOnClose, QListWidget-based popup (_DeskListPopup,
also reached "while interacting with the Desk picker") whose deferred
deletion could be processed by a downstream modal dialog's own nested
event loop while a stale, still-in-flight mouse event still targeted
it. Fixed under TODO 8c9436b (deferring the popup's own outgoing
signal re-emission via QTimer.singleShot, so nothing downstream ever
runs nested inside the same call stack as the originating click) --
see LEARNINGS.md and plans/fix-desk-picker-nested-dialog-crash.md for
the full mechanism. This item's own crash was never independently
reproduced, but the crashing code path, the widget involved, and the
"interacting with the Desk picker" trigger all match closely enough
that it's being closed as resolved by the same fix rather than left
open waiting for a third occurrence.)

## TODO `96013cf`/`858752b`: both name their rename target `markdown_old_basic` -- conflict

Two TODO items, added together, each rename a *different* widget to
the *same* new name:

- `96013cf`: rename `widgets/markdown/` (the plain Markdown widget) to
  `markdown_old_basic`.
- `858752b`: rename `widgets/markdown_ex/` (Markdown (Extended)) to
  `markdown_old_basic`.

Both can't be true -- two widget directories can't share one id/name.
Recorded verbatim as given rather than silently guessing which one was
meant, or inventing a different name for one of them.

- Which widget should actually become `markdown_old_basic`?
- Should the other one keep its current name, or get a different new
  name (e.g. something like `markdown_ex_old_basic`)? If so, what?

(Answer: good catch! markdown should become markdown_old_basic and markdown_ex should become markdown. we're replacing the old markdown widget with the new one, but we're keeping the old one around as deprecated.)

## TODO `9743419`: what makes a tempui file "markdown-based," and how should the save-a-copy filename be derived?

See `plans/markdown-rendering-doc-and-tempui-markdown.md` for full
context. Part 1 of this item (a Markdown-rendering-capabilities doc,
`markdown-rendering.md`) is done; parts 2/3 (Markdown (Extended)
rendering a tempui file directly, with a "save a copy" button) are
blocked on:

- Should "a tempui-based markdown file" be a **new explicit tempui
  keyword** (e.g. `Markdown <label>` as the first line, matching how
  `Scratch` -- TODO f8d9cec -- and `OpenMarkdown` already work), or
  should **any tempui file with no recognized keyword at all** fall
  back to being rendered as Markdown, instead of today's fallback to
  the Question widget? The second option changes existing,
  already-relied-upon fallback behavior for any malformed/typo'd
  tempui file, not just adding something new -- worth confirming
  before touching it.
- What's the actual filename-derivation algorithm for "a default file
  name derived from the first line of the markdown file" -- e.g. would
  `# My Investigation Notes` become `My Investigation Notes.md`
  verbatim, a slugified `my-investigation-notes.md`, or something else?

(Answer: option (a) -- a new explicit tempui DSL keyword, `Markdown
<label>`, matching Scratch/OpenMarkdown's shape. Unlike OpenMarkdown
(which points at an external target file), this one's own content
*is* the markdown to render, live, the same "render the tempui file
itself" pattern Question/LightningRound already use via
set_source_file -- not the fallback-for-any-unrecognized-keyword
option, which would have changed existing behavior. Placed on the new
default markdown widget (post-rename: markdown_ex becomes "markdown"),
since a tempui-bound instance shows a "Save As" button in place of
"Open" (no "open a different file" concept applies to a tempui-bound
instance). Saving writes the current content to a new file at the
project root, opens it in a *new*, ordinary file-backed markdown
widget instance, and leaves the original tempui-bound instance open
and still rendering live. The filename-derivation algorithm: slugified
to kebab-case, e.g. `# My Investigation Notes` -> `my-investigation
-notes.md`. "Save As" is scoped to just this widget for now --
generalizing something like it to other widgets is a separate, later
idea, not part of this TODO.)

## TODO `17ac2a8`: does anything reference the old basic markdown widget in a way that needs updating post-rename?

See `plans/audit-old-basic-markdown-widget-usage.md`. Searched the
whole codebase for any hardcoded markdown-widget-id reference (the
only way one widget opens another is `current_context
.get_widget_opener()("<widget_id>")`, since widget directories can't
import each other).

(Answer: only one real reference exists -- the TODO widget's "open
plan" button (`widgets/todo/widget.py`'s `_open_hovered_plan`),
`opener("markdown")` + `set_file(plan_path)`. It already used the
*id* `"markdown"`, not anything specific to the old plain widget, so
the TODOs 96013cf/858752b rename already transparently upgrades it to
the new, strictly-more-capable widget (TOC/folding/Mermaid) via the
same `set_file(path)` call both widgets share -- no code change
needed. Checked `plans/markdown-ex-widget.md` for any documented
downside of the new widget that might argue for deliberately keeping
this call site on the old one (e.g. slower on large files); found
none.)

## TODO `b2ab79f`: how should hardware-dependent regression tests (real microphone capture) actually be integrated?

See `plans/hardware-dependent-regression-tests.md`. Several
`tests/verify/` scripts start a real `QAudioSource` against the actual
default microphone (`desk.voice_capture.MicRecorder`) as part of their
coverage, which was audibly/visibly activating the system mic every
time the full regression sweep ran. Disabled for now (`disabled_`
prefix) as an immediate fix, but that's a real coverage gap long-term
-- this kind of test has caught real bugs before (e.g. TODO `fe7d8f2`).

- Should these just be run occasionally by hand (e.g. before a release,
  or when touching `desk/voice_capture.py`/`desk/speech.py`/either
  voice-using widget specifically), and if so, is a `disabled_` prefix
  the right signal for "run me manually sometimes," or does that read
  too much like "broken, ignore"? Would a different naming convention
  (e.g. a `hardware_` prefix, or a separate `tests/verify/hardware/`
  subdirectory) communicate "opt-in, not broken" better than reusing
  the failure-oriented `disabled_` convention for a different reason?
- Is it worth adding a mockable seam to `desk/voice_capture.py` (e.g.
  an injectable audio-source factory) so most of this coverage could
  run without the real hardware, keeping only a small, occasional,
  explicitly-hardware-touching smoke test? `CLAUDE.md` says avoid new
  dependencies, but this wouldn't need one -- just a seam in code this
  project already owns.
- If real-hardware coverage is kept at all, should it require some
  explicit opt-in (an env var, a CLI flag to a future test runner) so
  it's *possible* to include in an occasional full run without editing
  file names back and forth each time?

## TODO `9bc522b`: how should regression tests that make real Claude API calls actually be integrated?

See `plans/live-claude-api-regression-tests.md`. Several
`tests/verify/` scripts start a real Claude session (`ClaudeSession`
via the Claude Agent SDK, or a real `claude` CLI process via
`ClaudeWidget`) as part of their coverage -- real network calls, real
API cost/quota, real dependence on live model behavior. Disabled
(`disabled_` prefix, extracted from three files) for now -- same
underlying tension as TODO `b2ab79f`. Likely shares an answer with
that item and with TODO `0d91c74` below (all three are "valuable real
-behavior coverage that has a real-world cost/side-effect a routine
sweep shouldn't incur") -- consider answering all three together
rather than in isolation.

- Same naming/signaling question as TODO `b2ab79f`: is `disabled_`
  the right convention for "opt-in, run occasionally," or does this
  deserve its own convention (and if it's shared with `b2ab79f`/
  `0d91c74`, should all three be unified under one scheme rather than
  three separately-invented ones)?
- Is there a lightweight way to mock the Claude Agent SDK/CLI layer
  for most of this coverage (e.g. a fake transport that returns
  scripted `ResultMessage`/tool-call sequences) while keeping one
  small, occasional, real-API smoke test? This is more involved than
  TODO `b2ab79f`'s hardware seam -- the SDK's own message/event shapes
  would need faithful faking, not just one audio-source class.
  `CLAUDE.md` says avoid new dependencies -- worth checking whether
  the SDK itself already exposes a testing/mock transport before
  building one from scratch.
- Real Claude API calls cost actual money (unlike the mic/network
  categories) -- does that argue for a stricter default (never run
  automatically, ever, even in an "occasional full sweep" mode) than
  the other two disabled categories get?

## TODO `0d91c74`: how should regression tests that make real Hugging Face Hub network calls actually be integrated?

See `plans/live-network-model-download-regression-tests.md`. Two
tests in `tests/verify/verify_whisper_model_download_script.py` reach
out to the live Hugging Face Hub over the network. Disabled (`disabled_`
prefix) for now. Smaller in scope than TODO `9bc522b`/TODO `b2ab79f`
(one file, two tests) -- may not need its own separate answer if a
shared "occasionally run these by hand" mechanism gets built for the
other two categories.

- Does this one actually need a mock, or is "run occasionally by hand,
  document that it needs internet access" sufficient given its small
  size (versus the mic/Claude-API categories, which have real
  side-effects or cost that argue more strongly for a real mechanism)?
- Should `test_repo_ids_are_real` be reduced in scope (e.g. only check
  the *default* model's repo id, not every configured size) to shrink
  how much real network dependency this test needs, independent of
  whichever integration answer is chosen?

## TODO `b6abde2`: how should regression tests that use the real system clipboard actually be integrated?

See `plans/system-clipboard-regression-tests.md`. Every test in
`tests/verify/verify_paste.py` touches the real system clipboard, and
two calls `clipboard.clear()` -- destroying whatever the user actually
had copied. Disabled outright for now (whole file). Unlike the other
three categories above, this isn't about cost/network/hardware
side-effects -- it's specifically about not clobbering real user
state during an automated sweep, which suggests a different, simpler
fix than "run occasionally by hand."

- Would a save-the-real-clipboard's-contents-before/restore-after
  wrapper (applied automatically around this file, or any future test
  that touches the clipboard) let this run in every normal sweep
  again, with no real downside? If so, does Qt's clipboard API
  actually round-trip every MIME flavor these tests set (plain text,
  `text/markdown`, an image) losslessly -- confirmed directly, not
  assumed -- before relying on it?
- If a save/restore wrapper works, should it become a standing
  convention for any future test that touches the clipboard, or is
  `verify_paste.py` a one-off?

