# Parking Lot

This file captures thoughts and TODO items that arise during work on other things, to be revisited later. Items here are not prioritized or planned — they are reminders to come back to something. When ready to act on an item, move it to `TODO.md` and remove it from here.

## Items

- **Packaging & distribution**

  App bundling (e.g. PyInstaller) and installation/run instructions, so
  Desk can be distributed to and run by someone without a Python dev
  environment already set up.

  Moved here from `TODO.md` (was `TODO b66dfac`, `PENDING`) — blocked on
  two questions unresolved since early in this project (originally
  `design-docs/architecture.md`'s own Open Questions):
  - **Distribution target**: a PyInstaller-bundled standalone app, a
    pip-installable package with a console-script entry point, or
    something else?
  - **Platform scope**: macOS-only for now (matching where all
    development/verification has actually happened so far), or
    cross-platform (Linux/Windows) from the first packaged release?

  `plans/packaging-and-distribution.md` has a sketch of what's affected
  once these are answered. When ready to act on this, move it back to
  `TODO.md` with the answers.

- **Local speech-to-text (Whisper) for voice input**

  > **Note (still deciding):** I am still thinking about which way I want to proceed, but currently I am thinking of going with `large-v3-turbo` as recommended. We should also be sure to include a download script and back-up download instructions for the model.

  Investigated adding voice transcription. Anthropic does not offer a hosted speech-to-text API or transcription feature usable with a Claude subscription — Claude's API has no audio input endpoint, so any voice pipeline needs a separate transcription step whose output text is then passed to Claude.

  Two local (non-Anthropic) options on macOS:
  - **macOS `Speech` framework** (`SFSpeechRecognizer`), reachable from Python via `pyobjc-framework-Speech`. Native, no extra download, supports on-device and server-assisted recognition, but the Python binding is awkward (Objective-C-first API), requires user authorization prompts, server-assisted mode has usage throttling, and arbitrary audio files often need format conversion first.
  - **Local Whisper** (OpenAI, MIT-licensed, free including commercial use, no API costs — only local compute). Recommended over the Speech framework for a normal Python-native interface. On Apple Silicon, `mlx-whisper` (uses Apple's MLX framework) or `whisper.cpp` are the fastest runners; `mlx-whisper` in particular is well-suited to M-series chips.

  Whisper model sizes:

  | Model | Parameters | Disk size (~) | Notes |
  |---|---|---|---|
  | `tiny` | 39M | ~75 MB | Fastest, least accurate |
  | `base` | 74M | ~145 MB | Good for quick drafts |
  | `small` | 244M | ~485 MB | Solid balance |
  | `medium` | 769M | ~1.5 GB | Noticeably better accuracy |
  | `large` (v1/v2/v3) | 1550M | ~2.9–3 GB | Best accuracy, slowest |
  | `large-v3-turbo` | ~809M | ~1.6 GB | Most of `large`'s accuracy at roughly `medium`'s speed |

  Each size except `large`/`turbo` also has an English-only variant (`tiny.en`, etc.) that's slightly more accurate for English-only use. Quantized builds (4-bit/8-bit, via `mlx-whisper`/`whisper.cpp`) shrink memory footprint and speed further below the listed disk sizes.

  Follow-ups to handle when this is picked up:
  - Add a script to download the chosen model (currently leaning `large-v3-turbo`).
  - Document back-up/manual download instructions in case the script's source is unreachable.

- **TODO item editor may be torn down mid-edit by hot reload**

  Surfaced while investigating TODO 62e8b05 (see
  `plans/fix-todo-editor-caret-focus-freeze.md`). `_ItemDialog` is
  parented to `TodoWidget` (`widgets/todo/widget.py`). If
  `widgets/todo/widget.py` itself is edited/saved while the item editor
  is open (plausible during active development on this widget), the hot
  -reload machinery (`PythonWidgetHost._rebuild`, via `WidgetWatcher`)
  tears down and replaces the old `TodoWidget`, which would tear down
  the open `_ItemDialog` (a Qt child) along with it — silently closing
  the editor, discarding any unsaved text, mid-edit.

  Not fixed — doesn't match TODO 62e8b05's actual reported symptom (a
  transient caret blink, not the whole editor vanishing), and is
  unconfirmed (found by code inspection, not reproduced). Worth
  revisiting if a "the item editor closed by itself" report ever comes
  in for real.

- **`WidgetSpawnMenu._activate_item` has the same emit-then-close
  use-after-delete shape TODO c8f6fb3 just fixed in `_DeskListPopup`**

  Both are `Qt.WindowType.Popup` + `WA_DeleteOnClose` widgets whose
  `_activate_item` emits a signal and only then calls `self.close()`.
  TODO c8f6fb3 confirmed directly that this ordering crashes
  (`RuntimeError: wrapped C/C++ object ... has been deleted`) if anything
  downstream of the emitted signal shows a modal dialog before returning
  — the modal steals active-window status, which auto-closes the still
  -open Popup, and its `WA_DeleteOnClose` gets processed by the modal's
  own nested event loop while the emitting object is still on the call
  stack. `WidgetSpawnMenu.widget_chosen` doesn't currently lead to any
  modal dialog, so it hasn't actually crashed — but that's circumstantial
  (a property of what `DeskWindow._on_widget_add_requested`/
  `_place_widget` happen to do today), not structural. Worth applying the
  same "close before emit" reordering there too if this widget's
  downstream behavior ever grows a confirmation dialog, or proactively
  as a hardening pass.

- **`DeskWindow.switch_desk` has the same `_load_desk_widgets`-before-
  `_refresh_picker` ordering bug TODO 1a051d1 fixed in `__init__`**

  TODO 1a051d1 fixed `DeskWindow.__init__` constructing saved widgets
  (via `_load_desk_widgets`) before `_refresh_picker()` ever ran — the
  only place that populates `current_context`'s current-desk-directory —
  which made a saved `TodoWidget` always see no directory at boot.
  `switch_desk` (`src/desk/shell/window.py`) has the *identical* line
  order: `self._load_desk_widgets(new_desk)` runs before
  `self._refresh_picker()`. That fix was scoped to the specific reported
  regression (boot-time) and never touched this second call site — so
  switching *to* a Desk with a saved `TodoWidget` (or any future
  `python` widget that reads `current_context` at construction, like the
  code editor's Desk-directory-aware Open button, TODO 14d14e7) still
  sees the *previous* Desk's directory, not the one just switched to.
  Not fixed here (found while implementing TODO 14d14e7, not itself
  reported) — same one-line reorder as TODO 1a051d1's fix would apply;
  worth doing proactively or the next time a "wrong directory after
  switching Desks" symptom is reported for real.

- **Personal information audit: one leaked absolute path with local
  username**

  Searched the working tree and the full commit history (`git log --all
  -p`) for personal information beyond the commit author name/email
  (the standard git identity used for commits). Found exactly one hit:
  `TODO.md` (inside the `COMPLETED` item `fa288ce`) contains a pasted
  console traceback with a literal local absolute path, revealing the
  local macOS username and folder layout. It appears in this one spot
  only — never introduced or removed anywhere else in history. No other
  emails, hostnames, machine names, or `~`-relative paths beyond the
  generic (non-personal) `~/.desk/` convention mentioned in
  `design-docs/architecture.md` and `plans/desk-concept.md`. Also noted:
  `.git/config`'s `origin` remote contains the GitHub username, but
  that's just the repo's public clone URL, not something embedded in a
  commit. Redacting the current `TODO.md` line is a normal edit;
  actually scrubbing it from history would require a destructive
  history rewrite (`git filter-repo` or similar) — not done here,
  pending explicit direction.

  **Update:** a second instance turned up after this audit was written —
  TODO `b44e8ba` (the Desk-picker segfault report) quotes console output
  containing the same kind of local absolute path, the same
  username/folder-layout leak, again inside pasted terminal output. Same
  disposition as the first: harmless as a redaction (just descriptive
  text in a bug report), but would need a history rewrite to actually
  remove from git history. Worth a single redaction pass over both
  spots (and anything similar added in the future) rather than fixing
  piecemeal, if/when the history-rewrite question above is ever acted
  on.

  **Update 2 (2026-07-07):** both spots above, plus a third instance in
  `plans/todo-parser-checkbox-format.md`, were redacted to `~`-relative
  paths with the local username and folder name removed. This repo has
  no prior commits containing these files, so no history rewrite was
  needed.

  **Decision:** Make a new repo for Desk under Inadvisable Adventures
  without the in-repo TODO tracking.

- **Open questions: ownership protocol for TODO items, and whether work
  tracking belongs in-repo/in-Desk at all**

  Raised alongside the personal-info audit / new-repo decision above.
  Several related, unresolved questions to think through together next
  time work tracking comes up:

  - **Ownership/in-progress protocol**: right now an item just gets
    `[planned: <file>.md]` appended in place in `TODO.md` while it's
    being worked. Should an item instead get *moved out* of `TODO.md`
    entirely while active — e.g. into an `in_progress_plan/` (or
    similar) folder — so `TODO.md` only ever shows not-yet-started work,
    and the "this is currently claimed/being worked" state is visible
    from the *filesystem* (a file existing in that folder) rather than
    a marker inside a shared file?
  - **Process-file organization**: should `TODO.md`, `PARKINGLOT.md`,
    `LEARNINGS.md`, `plans/`, etc. (all the "process" scaffolding, as
    opposed to the app's own source) move out of the repo root into one
    subdirectory?
  - **Or should none of it be committed at all** — e.g. live under
    `.desk_temp/` (already gitignored per TODO a02b001) instead of being
    tracked in git history in the first place?
  - **Bigger question**: is a flat Markdown file even the right
    substrate for this, or should "work item tracking" be a real
    database or a local microservice that can actually dole out/claim
    work items (supporting real ownership, concurrent agents, querying,
    etc.) instead of file-based conventions enforced only by
    `development-process.md`?
  - **If so**: do we vibecode that microservice ourselves, and does it
    become a feature *of Desk* (i.e. Desk grows a built-in work-item-
    tracking service other tools/agents can talk to), or does it stay a
    separate, standalone tool?

  Not decided — parking here to revisit as a real design discussion
  rather than deciding piecemeal mid-task. Connects to the "new repo
  under Inadvisable Adventures without in-repo TODO tracking" decision
  just above, which may end up being the actual resolution to several
  of these at once.

- **How should Claude author its own temp-UI DSL and interpreter code?
  Should temp-UI widgets be real widgets too?**

  Open design question around the Temporary UI feature (TODO a02b001)
  and its follow-ons (Question / Lightning Round widgets). Right now
  the temp-UI DSL and its interpreters are hand-written parts of Desk's
  own codebase; a temp-UI "widget kind" (`question`, `lightning_round`)
  is a real widget under `widgets/`. Questions to work through:
  - How do we handle Claude writing its *own* temp-UI DSL and adding
    the interpreter code for it? I.e. an agent inventing a new temp-UI
    construct and the code that renders/handles it, rather than only
    emitting instances of the fixed, pre-built DSL keywords.
  - Should all temp-UI widgets be actual (first-class, under `widgets/`)
    widgets too, or should some remain purely DSL-driven/ephemeral? What
    distinguishes "this deserves to be a real widget" from "this is a
    one-off temp-UI construct"?
  - Interacts with the general widget contract (`build() -> QWidget`,
    hot reload, `instance_id`) and with how much of Desk an agent is
    allowed/expected to extend at runtime vs. via committed code.

- **New widget: side-by-side container (two widget instances, swap/
  reorient, cross-widget `postMessage`)**

  A container widget with two side-by-side spots, one widget instance
  in each. Requirements:
  - Two spots for two different widget instances, one on each side.
  - A button to swap which widget is on which side.
  - Switchable between horizontal (side-by-side) and vertical (stacked)
    orientation.
  - The two contained widgets can communicate with each other via an
    implementation of the browser `postMessage()` protocol (main-thread
    /worker-style message passing — see the standard `postMessage`/
    `onmessage` + structured-clone model). Widgets can *optionally*
    publish their API for `postMessage`/`onmessage` messages so the
    other side knows what it can send/expects to receive.
  - Depends on / motivates a Desk-side inter-widget messaging mechanism
    modeled on `postMessage`; think about how that relates to the
    existing Bridge API and `current_context` hooks.

- **New widget: editor-with-view (a side-by-side of the editor + the
  markdown viewer)**

  A concrete instance of the side-by-side container above: the code
  editor widget on one side and the markdown renderer widget (TODO
  `6bf83a9`) on the other, so editing a Markdown file shows a live
  rendered preview beside it. Blocked on both the side-by-side
  container widget and the markdown renderer widget existing first
  (and, for a *live* preview, on the two communicating — e.g. via the
  container's `postMessage` mechanism, or simply by both pointing at
  the same file with the viewer's file watcher picking up saves).

- **Post-build binding (session/source-file) is lost on a widget's own
  hot reload**

  A general limitation shared by every widget kind that relies on
  DeskWindow binding something into it *after* `build()`: the Temporary
  UI widgets (`_bind_temp_ui_widget` → `set_source_file`) and now the
  claude widget (`_bind_claude_widget` → `start_session`, TODO
  1d7331b). `PythonWidgetHost._rebuild` (hot reload, fired when the
  widget's own `widget.py` is edited) re-runs `build()` to make a fresh
  instance but does *not* re-run DeskWindow's post-build binding — so a
  temp-UI widget loses its source file, and a claude widget comes back
  as a blank shell with no `claude` relaunch (the previous PTY/session
  is gone regardless, since a rebuild makes a brand-new
  `TerminalWidget`). Developer-only edge case (only happens while
  actively editing that widget's code). Could be fixed generally by
  having `PythonWidgetHost` remember and replay whatever binding
  DeskWindow applied, or by having DeskWindow re-bind on the broker's
  `widget_changed` signal — revisit if hot-reloading these widgets
  mid-use becomes a real annoyance.

- **How should Claude watch for a temp-UI response — and should it all
  be a skill?**

  Moved here from `TODO.md` (was `1d22456`): "figure out a way to get
  claude to watch for the response from tempui. should it all be a skill
  instead?" Open design/research question, not a concrete task yet. When
  an agent poses a question via Temporary UI (TODO a02b001 — a file in
  `.desk_temp/` that Desk renders as a Question/Lightning Round widget),
  the user's chosen answer is appended back to that same file as an
  `Answer`/answer line. The open problem is how the *agent* notices that
  answer arrived without polling in an ad-hoc way:
  - Should this be packaged as a Claude Code **skill** (a documented
    "ask via temp-UI, then wait for the answer" capability the agent
    invokes) rather than bespoke per-agent watching logic? The TODO's
    own "should it all be a skill instead?" points this way.
  - If a skill: does it block/poll the file, use a file watcher, or
    something else? How does it fit the existing `.desk_temp` DSL and
    `desk-temporary-ui.md` doc that already instruct agents?
  - Connects to the broader parked question above on how Claude should
    author its own temp-UI DSL/interpreters and whether temp-UI widgets
    should all be real widgets — these may want to be designed together
    as "the agent ⇄ Desk temp-UI protocol" rather than piecemeal.

  Not decided — parking to revisit as a deliberate design discussion.

- **Migrate the TempUI/Claude widget bindings onto widget-local storage
  too, instead of their current bespoke, one-off wiring**

  Surfaced building the Markdown widget (TODO 6bf83a9): it opens/renders
  a Markdown file the user picks, but — like the Code Editor widget —
  the chosen file was *not* remembered across a Desk reload. TODO
  fb76057 built the general mechanism this needed ("widget-local
  storage": `WidgetState.state: dict`, `get_widget_local_storage()`/
  `set_widget_local_storage()` duck-typed onto a widget, a generalized
  post-build binding in `DeskWindow`) — but deliberately scoped to just
  the mechanism, not wiring any specific widget onto it. The original
  motivating case (Markdown/Markdown (Old, Basic)/Editor remembering
  their open file) is now done, under TODO `02eda20`. Still parked: the
  existing per-kind `_bind_temp_ui_widget`/`_bind_claude_widget`
  special-cases could migrate onto this same mechanism instead of their
  current bespoke wiring — a clean answer would simplify both, but isn't
  decided or scoped yet.

  Not decided — parking to revisit as its own design discussion.

- **In-widget zoom/pan for the SVG Viewer**

  TODO c7d6e4d's SVG Viewer widget (`widgets/svg_viewer/`) only fits
  the SVG to the widget's own size (aspect-preserved). For a large or
  detailed diagram, independent zoom/pan within the widget (distinct
  from the Workspace Canvas's own zoom of the whole widget frame) would
  help; out of scope for that item, worth its own TODO if it comes up.

- **Wire `.svg` results in the File Explorer / Markdown widgets to open
  in the SVG Viewer**

  Right now the File Explorer (TODO b927389) always opens a selected
  file in a new Editor widget instance regardless of extension, and the
  Markdown widget (TODO a76e723, renamed from "Markdown (Extended)" /
  `markdown_ex`, TODO 858752b) renders embedded images (including SVG)
  via `QTextBrowser`'s own native/indirect handling, not the new SVG
  Viewer widget (TODO c7d6e4d, built after both of those). Neither was
  asked to integrate with it. Worth revisiting once there's an actual
  need (e.g. double-clicking a `.svg` in the explorer opening a real
  vector view instead of raw XML in the Editor).

- **A generalized mechanism for "check immediately before create, abort
  recoverably if it already exists"**

  TODO `4716585` applied this pattern by hand at each file/directory
  -creation call site in the New Desk flow specifically (`.desk_temp`,
  `.gitignore`, `development-process.md`, the `.desk` file itself) --
  re-verify existence right before the actual create/write, treat
  "already there" as a normal, recoverable branch rather than
  clobbering or crashing. Every other widget that creates a new file
  (Markdown's "Save As", Stack's "Save as Markdown", any future one)
  either needs the same hand-written check or currently doesn't have
  it at all. Worth designing a small, reusable helper/pattern for this
  instead of re-deriving the same three-line shape at each call site --
  e.g. something like `create_if_absent(path, write_fn) -> bool`
  (returns whether it actually created vs. found existing), or a
  context-manager shape. Not designed yet; revisit once there's a
  second or third widget that would clearly benefit, to avoid guessing
  at the right generalization from just one example.

- **The Bridge API's `require_caller` can't resolve a tempui-DSL
  -defined custom widget kind at all — every capability-gated call
  (`workspace.*`/`fs.*`/`widgets.*`) 400s for one**

  Surfaced building TODO `5734529`'s `self.getLocalStorage`/
  `setLocalStorage` (deliberately *not* built on `require_caller`, for
  exactly this reason). `require_caller`'s dependency (`src/desk/server
  /app.py`) looks the calling widget up via `discover_widgets
  (widgets_dir).get(x_desk_widget_id)` — which only ever scans the
  real, on-disk `widgets/` directory. A tempui-DSL-defined custom
  widget (TODO `91b3f42`) has no such directory; its `WidgetInfo` only
  ever lives in the live `DeskWindow._widgets` catalog. So a custom
  widget's own JS calling *any* existing Bridge capability —
  `workspace.getState()`, `fs.readFile`/`writeFile`, `widgets.list`/
  `open`/`close`, even the technically-uncapabilitied
  `self.getManifest()` — gets a `400 Unknown widget id` today, not just
  the state-persistence gap TODO `5734529` fixed. Would need
  `require_caller` (or a new equivalent) to resolve against the live,
  `GuiBridge`-reachable catalog instead of (or in addition to)
  `discover_widgets(widgets_dir)` -- not designed yet; parking rather
  than guessing at the right generalization from a single specific
  fix's own narrow workaround.

- **Scrolling while hovering over a widget scrolls the Desk instead of
  the widget**

  Right now a mouse-wheel scroll over a widget frame appears to scroll/
  pan the Workspace Canvas underneath it rather than scrolling the
  widget's own content. It should instead be captured by whichever
  widget is under the cursor and scroll that widget, not the Desk.

  Alongside that fix, add a minimap like `world-timelines`'s, so that
  panning/navigating the Desk canvas still has a reliable way to get
  around once wheel-scroll is no longer available as a canvas-pan
  gesture over a widget.

  Not designed yet -- parking rather than guessing at scope (e.g.
  exactly which widget kinds currently rely on wheel-scroll-as-canvas
  -pan today, and what the minimap should actually show/support beyond
  "like world-timelines's").

- **Locked widgets still show the resize-edge cursors**

  A locked widget's edges shouldn't do anything (resizing is disabled
  while locked), but the custom edge-resize mouse cursors still appear
  when hovering there, which is misleading -- it looks like resizing is
  still available. Should be suppressed while the widget is locked.

- **Context-menu clicks/taps that fall through an unhandled widget
  should not reach the Desk underneath**

  A right-click (or equivalent context-menu gesture) that a widget
  doesn't itself handle currently appears to fall through to the
  Workspace Canvas below it, presumably opening/triggering the Desk's
  own context menu. It should instead just be ignored/swallowed at the
  widget boundary when the widget doesn't handle it, not passed through
  to the Desk.

- **A visible inner outline around a widget's content area**

  There's currently no visual boundary marking where a widget's frame
  ends and its actual content begins. An inner outline around the
  content area (distinct from the widget frame's own outer border)
  would make that boundary clear.

- **`kind: "html"` widgets with more than one file silently fail to
  load, because relative-path sub-resource requests lose the auth
  token**

  From `DESK_FEEDBACK-2026-07-13T012144.md` (TODO `4ab5875`,
  investigating `widgets/hex_flower`'s blank page). A widget's main
  page is loaded with the per-launch token as a query parameter, but a
  plain relative-path browser reference (`<script src>`, `<link
  href>`, CSS `url(...)`, `<img src>`) does not carry that query string
  forward, and a native resource tag can't attach a custom header
  either -- so every such sub-resource request arrives at
  `TokenAuthMiddleware` with no credential and gets `401`'d, silently
  aborting the module/resource graph with no console output. This
  affects any `kind: "html"` widget built as an ordinary multi-file web
  project; only tempui `DefineWidget` widgets avoid it today, as a side
  effect of being forced into one inlined HTML file (TODO `91b3f42`),
  not because anyone intentionally avoided the bug. The suggested fix:
  a same-origin cookie set when a widget's main page is served,
  alongside (not replacing) the existing query-param/`X-Desk-Token`
  -header checks -- cookies are the one credential mechanism a browser
  attaches automatically to every same-origin request, including plain
  `<script src>`/`<link href>` loads. Not designed/implemented yet.

- **Reconsider `DefineWidget`'s single-inlined-file requirement, once
  the relative-path/token gap above is fixed**

  From the same feedback doc. Inlining everything into one base64
  -encoded HTML document is convenient for an agent to author quickly,
  but stops working well for anything non-trivial (as `hex_flower`,
  ported from a real multi-file TypeScript project, illustrates).
  Once the auth gap above no longer forces this, worth reconsidering
  whether `DefineWidget` could support a small set of named files (e.g.
  an HTML entry plus a script and a stylesheet) instead of one inlined
  document. Depends on the item above; not designed yet.

- **No visible signal when a `kind: "html"` widget fails to load**

  From the same feedback doc. Right now a `kind: "html"` widget that
  fails for any reason (the token gap above, a script error, whatever)
  just renders as a silent blank page indistinguishable from several
  other failure modes, with no console output surfaced anywhere. Worth
  some visible failure signal -- e.g. surfacing the widget's own
  `javaScriptConsoleMessage` output somewhere inspectable (a log file,
  a debug panel), and/or a generic "this widget failed to render"
  placeholder shown in place of a silent blank page.

- **A known-good, minimal multi-file `kind: "html"` widget template**

  From the same feedback doc. A checked-in (or docs-referenced) minimal
  example of a working multi-file `kind: "html"` widget would give a
  future agent building something like `hex_flower` a template to diff
  against, rather than discovering gaps like the one above the hard way
  after already doing a real port of an existing project.

- **Document the auth-token requirement for a `kind: "html"` widget's
  own asset requests**

  From the same feedback doc. `design-docs/architecture.md`'s
  description of `kind: "html"` widgets doesn't mention the auth token
  at all. It should state plainly that every request the browser makes
  for a widget's own page -- not just the top-level navigation -- must
  carry the per-launch token, and that ordinary relative-path resource
  references do not carry the token forward and will be rejected, so a
  widget with more than one file won't load until the underlying gap
  (above) is fixed.

- **No single doc lays out what does/doesn't work yet for a `kind:
  "html"` widget built from scratch (as opposed to a tempui
  `DefineWidget` single-file widget)**

  From the same feedback doc. E.g. "single self-contained HTML file:
  works"; "multiple files loaded via relative paths: currently broken,
  see [gap]". Without that, a reasonable, competently-built ordinary
  web project (exactly what happened with `hex_flower`) silently fails
  with zero diagnostic signal and no way for whoever built it to have
  known in advance.

- **No guidance on how to debug a blank `kind: "html"` widget**

  From the same feedback doc. Nothing currently tells a widget author
  how to tell their widget failed to load. A "how to debug a blank
  widget" note (start from: is the custom element even defined? check
  `document.querySelector(...).shadowRoot`; are there failed network
  requests?) would shorten this kind of investigation considerably --
  today the failure mode is a silent blank page with no console
  output, indistinguishable from several other possible failures (bad
  HTML, a crashed script, wrong entry point, etc.).

- **"Domain" packages: widgets, DSL extensions, new DSLs, and agent
  instructions bundled and distributed together — probably needs a
  formalization of DSLs for Desk first**

  Idea: a "domain" package could bundle together whatever a particular
  use case needs — widgets, extensions to any known DSL, entirely new
  DSLs, and agent instructions for using them — as one distributable,
  installable unit, rather than each of those being separately
  authored/wired into Desk by hand.

  This probably requires formalizing "DSL" as a real concept in Desk
  first (right now the tempui DSL is a fixed, hand-written set of
  keywords/interpreters in `src/desk/temp_ui.py`, not a general
  mechanism other DSLs could plug into). Two sub-parts that formalization
  would likely need:
  - A DSL for *specifying* a DSL (possibly with embedded code for its
    interpreter/behavior) — i.e. a meta-DSL a domain package author
    writes to define a new DSL's keywords/grammar/semantics, rather
    than hand-writing Python interpreter code the way tempui's own
    keywords are today.
  - A DSL for *specifying widgets* themselves, as a more declarative
    alternative to hand-authoring `widget.json` + a `build()` function
    (or, for `DefineWidget`, hand-authoring/base64-inlining raw HTML).

  Connects to the parked question above on how Claude should author
  its own temp-UI DSL/interpreters and whether temp-UI widgets should
  all be real widgets — that question and this one are likely facets
  of the same underlying "how far does Desk's own extensibility go, and
  what's the authoring surface for it" design space, and may want to be
  thought through together.

  Not designed — a large, open-ended idea, parking as a direction to
  think about rather than a scoped task.

- **A way to end a claude widget's session so it can get new
  instructions — maybe an "end session" button?**

  Right now a claude widget (`widgets/claude/widget.py`) is bound to
  one `claude --session-id`/`--resume` session for its lifetime
  (`ClaudeWidget.start_session`) — the initial `CLAUDE_WIDGET_PROMPT`
  is only ever sent once, on first launch. There's no way from the
  widget itself to end that session and start a fresh one with new
  instructions, short of destroying and re-placing the whole widget.
  An "end session" button (or similar) that lets the current session
  end and a new one begin — presumably resending the initial Desk
  prompt, the same as a fresh launch — would let a claude widget be
  reused for a new task without a full widget teardown/recreate.

  Not designed — how this interacts with `--resume`, the persisted
  `instance_id`-as-session-id (see `plans/claude-widget-session-resume.md`),
  and the widget's own PTY/`exec` lifecycle isn't worked out yet.

- **How to get claude to better engage with tempui's communication
  capabilities when running inside Desk**

  Open question: a `claude` session running inside a claude widget
  (`CLAUDE_WIDGET_PROMPT`, pointing it at `desk-temporary-ui.md`) does
  not reliably make good use of what tempui actually offers it for
  communicating back to the user — e.g. asking a `Question`, running a
  `LightningRound`, or otherwise using the Temporary UI channel instead
  of just talking in the terminal. Not clear yet whether this is a
  prompt-wording problem, a discoverability problem (the agent doesn't
  realize a given moment calls for one of these), a docs-structure
  problem (connects to the parked question above on how Claude should
  watch for a temp-UI response and whether it should be a skill), or
  something else entirely.

  Not designed/scoped — parking as a direction to investigate (e.g.
  observe real sessions and see where they fail to reach for tempui)
  rather than guessing at a fix.

- **The claude widget's hosted terminal has real problems — worth
  fixing, or should Desk talk to claude a different way entirely?**

  The claude widget (`TerminalWidget`-hosted, `widgets/claude/widget.py`)
  isn't working quite right as a hosted console app:
  - Drag-and-drop doesn't work.
  - Some more-advanced terminal rendering doesn't quite work and
    causes weird visual artifacts.
  - The app isn't notified when the console window's size changes
    (no resize signal reaching the PTY/the app running inside it).

  Open question, not just a bug list: is it worth fixing all of these
  (which would make Desk's terminal hosting better generally, for
  `claude` and any other TUI app run in a `TerminalWidget`), or is
  there a fundamentally different way for Desk to interact with
  `claude` that sidesteps hosting a full interactive terminal
  altogether (e.g. driving it more directly/programmatically) and that
  Desk could integrate with more cleanly than a hosted console app?

  Not designed/decided — parking as a direction to think through
  rather than a scoped task; likely worth deciding before sinking
  effort into fixing the terminal-hosting issues piecemeal.

- **`TODO.md` formatting/structure: blank lines between entries,
  archiving old items, and priority/dependency lists instead of file
  order**

  Three related open questions about `TODO.md` itself, not its content:

  - **Blank lines between entries.** `TODO.md` doesn't render properly
    in an ordinary Markdown viewer because there's no blank line
    between one item and the next (Markdown treats adjacent
    non-blank lines as one paragraph). Checked whether adding blank
    lines between entries would break the TODO widget's parsing
    (`src/desk/todo_file.py`, `parse_todo_file`): it wouldn't — an
    item's boundary is found by regex-matching the *start* of the
    *next* item (`ITEM_START_RE`), not by blank-line separation, so an
    added trailing blank line would just become part of the preceding
    item's own preserved `raw_text` and round-trip unchanged. Safe to
    do; not yet done.
  - **Archiving old items.** Should old (`COMPLETED`/`SUPERSEDED`)
    items start moving out of `TODO.md` into some kind of archive, now
    that the file has grown quite long? Not decided — connects to the
    already-parked "process-file organization"/new-repo questions
    above.
  - **`required-direct-prior: []`/`priority-direct-prior: []` instead
    of file order.** Right now both an item's priority (its position
    in the file, top to bottom) and any dependency it has on another
    item are expressed the same way: physical ordering in the file —
    conflating "must come after" (a real dependency) with "happens to
    be prioritized after" (just a preference), and making a pure
    priority change a cut-and-paste move instead of a simple edit.
    Idea: give each item explicit `required-direct-prior: [<id>, ...]`
    (hard dependencies — this item cannot start before those finish)
    and `priority-direct-prior: [<id>, ...]` (soft ordering preference)
    lists instead, so reprioritizing is an edit to these lists rather
    than moving the item's text block, and true dependencies are
    distinguished from mere priority. Not designed — would need working
    out how the TODO widget/`development-process.md`'s own "Prioritizing
    TODO Items" section would use these lists to determine actual work
    order, and how required-vs-priority interacts when they conflict.
