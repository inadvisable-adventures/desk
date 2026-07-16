# Parking Lot

This file captures thoughts and TODO items that arise during work on other things, to be revisited later. Items here are not prioritized or planned — they are reminders to come back to something. When ready to act on an item, move it to `TODO.md` and remove it from here.

## Items

- **Browser widget's back/forward buttons can get stuck stale
  (enabled/disabled state, not the underlying navigation itself)**

  Surfaced while verifying TODO `e35bcf0` (contained pop-ups) —
  confirmed present identically on the pristine, pre-`e35bcf0` widget
  too, so it's unrelated to that fix, not a regression from it.
  `BrowserWidget._on_url_changed` (`widgets/browser/widget.py`) calls
  `_update_nav_buttons()`, which reads `self._view.history()
  .canGoBack()/.canGoForward()` synchronously at that moment. Confirmed
  directly: right after two real navigations, `history().canGoBack()`
  already correctly returns `True`, but `_back_button.isEnabled()` is
  stuck `False` — nothing re-syncs it later, since `_update_nav_buttons`
  is only ever called from inside `_on_url_changed`. Clicking Back
  itself still works fine (the underlying `QWebEngineHistory` state is
  correct) — only the *button's own enabled/disabled UI state* can lag
  or get stuck wrong, presumably because `urlChanged` can fire before
  `QWebEngineHistory` has fully settled for that navigation. Likely
  fix: also refresh nav-button state from `loadFinished` (or another
  signal that reliably fires after history has settled), not just
  `urlChanged` alone -- not designed/verified yet.

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

- **Hot reload (`PythonWidgetHost._rebuild`) doesn't fully preserve a widget's own state**

  Two known consequences of `PythonWidgetHost._rebuild` (fired when a
  widget's own `widget.py` is edited/saved) re-running `build()` to
  make a fresh instance without fully restoring everything that was
  true of the old one:

  - **A child dialog can be torn down mid-edit.** Surfaced while
    investigating TODO 62e8b05 (see
    `plans/fix-todo-editor-caret-focus-freeze.md`). `_ItemDialog` is
    parented to `TodoWidget` (`widgets/todo/widget.py`). If
    `widgets/todo/widget.py` itself is edited/saved while the item
    editor is open (plausible during active development on this
    widget), the hot-reload machinery (via `WidgetWatcher`) tears down
    and replaces the old `TodoWidget`, which would tear down the open
    `_ItemDialog` (a Qt child) along with it — silently closing the
    editor, discarding any unsaved text, mid-edit. Not fixed — doesn't
    match TODO 62e8b05's actual reported symptom (a transient caret
    blink, not the whole editor vanishing), and is unconfirmed (found
    by code inspection, not reproduced). Worth revisiting if a "the
    item editor closed by itself" report ever comes in for real.
  - **Post-build binding (session/source-file) is lost, and could
    migrate onto widget-local storage instead.** A general limitation
    shared by every widget kind that relies on DeskWindow binding
    something into it *after* `build()`: the Temporary UI widgets
    (`_bind_temp_ui_widget` → `set_source_file`) and the claude widget
    (`_bind_claude_widget` → `start_session`, TODO 1d7331b). `_rebuild`
    does *not* re-run DeskWindow's post-build binding — so a temp-UI
    widget loses its source file, and a claude widget comes back as a
    blank shell with no `claude` relaunch (the previous PTY/session is
    gone regardless, since a rebuild makes a brand-new
    `TerminalWidget`). Developer-only edge case (only happens while
    actively editing that widget's code). Could be fixed generally by
    having `PythonWidgetHost` remember and replay whatever binding
    DeskWindow applied, or by having DeskWindow re-bind on the
    broker's `widget_changed` signal. Separately: TODO `fb76057` built
    a general "widget-local storage" mechanism (`WidgetState.state:
    dict`, `get_widget_local_storage()`/`set_widget_local_storage()`)
    originally motivated by the Markdown/Editor widgets remembering
    their open file (now done, TODO `02eda20`) — the existing per-kind
    `_bind_temp_ui_widget`/`_bind_claude_widget` special-cases above
    could migrate onto this same mechanism instead of their current
    bespoke wiring, which might incidentally fix the hot-reload loss
    too, but isn't decided or scoped yet.

  Not decided — parking to revisit as its own design discussion, or
  the next time either symptom is hit for real.

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

- **Process/TODO-tracking meta-questions: ownership protocol, file
  organization, `TODO.md` formatting, and a per-project glossary**

  Several related, unresolved questions about how this project's own
  process/work-tracking materials (`TODO.md`, `PARKINGLOT.md`,
  `LEARNINGS.md`, `plans/`, etc.) should work, raised alongside the
  personal-info audit / new-repo decision above — to think through
  together next time work tracking comes up, rather than deciding
  piecemeal:

  - **Ownership/in-progress protocol.** Right now an item just gets
    `[planned: <file>.md]` appended in place in `TODO.md` while it's
    being worked. Should an item instead get *moved out* of `TODO.md`
    entirely while active — e.g. into an `in_progress_plan/` (or
    similar) folder — so `TODO.md` only ever shows not-yet-started
    work, and the "this is currently claimed/being worked" state is
    visible from the *filesystem* (a file existing in that folder)
    rather than a marker inside a shared file?
  - **Process-file organization.** Should `TODO.md`, `PARKINGLOT.md`,
    `LEARNINGS.md`, `plans/`, etc. (all the "process" scaffolding, as
    opposed to the app's own source) move out of the repo root into
    one subdirectory? Or should none of it be committed at all — e.g.
    live under `.desk_temp/` (already gitignored per TODO a02b001)
    instead of being tracked in git history in the first place?
  - **Bigger question: is a flat Markdown file even the right
    substrate for this**, or should "work item tracking" be a real
    database or a local microservice that can actually dole out/claim
    work items (supporting real ownership, concurrent agents,
    querying, etc.) instead of file-based conventions enforced only by
    `development-process.md`? If so, do we vibecode that microservice
    ourselves, and does it become a feature *of Desk* (a built-in
    work-item-tracking service other tools/agents can talk to), or
    stay a separate, standalone tool?
  - **`TODO.md` formatting.** Three narrower, `TODO.md`-specific
    questions:
    - **Blank lines between entries.** `TODO.md` doesn't render
      properly in an ordinary Markdown viewer because there's no
      blank line between one item and the next (Markdown treats
      adjacent non-blank lines as one paragraph). Checked whether
      adding blank lines between entries would break the TODO
      widget's parsing (`src/desk/todo_file.py`, `parse_todo_file`):
      it wouldn't — an item's boundary is found by regex-matching the
      *start* of the *next* item (`ITEM_START_RE`), not by
      blank-line separation, so an added trailing blank line would
      just become part of the preceding item's own preserved
      `raw_text` and round-trip unchanged. Safe to do; not yet done.
    - **Archiving old items.** Should old (`COMPLETED`/`SUPERSEDED`)
      items start moving out of `TODO.md` into some kind of archive,
      now that the file has grown quite long?
    - **`required-direct-prior: []`/`priority-direct-prior: []`
      instead of file order.** Right now both an item's priority (its
      position in the file, top to bottom) and any dependency it has
      on another item are expressed the same way: physical ordering
      in the file — conflating "must come after" (a real dependency)
      with "happens to be prioritized after" (just a preference), and
      making a pure priority change a cut-and-paste move instead of a
      simple edit. Idea: give each item explicit
      `required-direct-prior: [<id>, ...]` (hard dependencies — this
      item cannot start before those finish) and
      `priority-direct-prior: [<id>, ...]` (soft ordering preference)
      lists instead, so reprioritizing is an edit to these lists
      rather than moving the item's text block, and true dependencies
      are distinguished from mere priority. Would need working out
      how the TODO widget/`development-process.md`'s own
      "Prioritizing TODO Items" section would use these lists to
      determine actual work order, and how required-vs-priority
      interacts when they conflict.
  - **Per-project glossary and active memory management.** For both
    Desk (the app) and this project's own development process: a
    per-project glossary, and reorganizing process materials so they
    don't consume context when irrelevant to the task at hand. More
    active memory management generally — possibly with dedicated
    tools for working with memory, connecting to `LEARNINGS.md`,
    and/or some kind of online shared "useful learnings" tool.

  Not decided — parking here to revisit as a real design discussion
  rather than deciding piecemeal mid-task. Connects to the "new repo
  under Inadvisable Adventures without in-repo TODO tracking" decision
  in the personal-info-audit item above, which may end up being the
  actual resolution to several of these at once.

- **Desk extensibility: formalizing DSLs, "domain" packages, and
  widget-composition ("crystallization") packaging**

  Several related, cross-referencing ideas about how far Desk's own
  extensibility goes and what the authoring surface for it should look
  like — likely facets of the same underlying design space, parked
  together to be thought through as one discussion rather than
  piecemeal:

  - **Claude authoring its own temp-UI DSL/interpreter code; should
    temp-UI widgets be real widgets too?** Open design question around
    the Temporary UI feature (TODO a02b001) and its follow-ons
    (Question / Lightning Round widgets). Right now the temp-UI DSL
    and its interpreters are hand-written parts of Desk's own
    codebase; a temp-UI "widget kind" (`question`, `lightning_round`)
    is a real widget under `widgets/`. How do we handle Claude writing
    its *own* temp-UI DSL and adding the interpreter code for it —
    an agent inventing a new temp-UI construct and the code that
    renders/handles it, rather than only emitting instances of the
    fixed, pre-built DSL keywords? Should all temp-UI widgets be
    actual (first-class, under `widgets/`) widgets too, or should some
    remain purely DSL-driven/ephemeral — what distinguishes "this
    deserves to be a real widget" from "this is a one-off temp-UI
    construct"? Interacts with the general widget contract (`build()
    -> QWidget`, hot reload, `instance_id`) and with how much of Desk
    an agent is allowed/expected to extend at runtime vs. via
    committed code. Also connects to a separate, narrower question:
    how should Claude *watch for* a temp-UI response (moved here from
    `TODO.md`, was `1d22456`) — when an agent poses a question via
    Temporary UI, the user's chosen answer is appended back to that
    same file as an `Answer` line, and the open problem is how the
    agent notices that answer arrived without polling in an ad-hoc
    way. Should this be packaged as a Claude Code **skill** (a
    documented "ask via temp-UI, then wait for the answer" capability)
    rather than bespoke per-agent watching logic — and if so, does it
    block/poll the file, use a file watcher, or something else? These
    may want to be designed together as "the agent ⇄ Desk temp-UI
    protocol" rather than in isolation.
  - **"Domain" packages.** A "domain" package could bundle together
    whatever a particular use case needs — widgets, extensions to any
    known DSL, entirely new DSLs, and agent instructions for using
    them — as one distributable, installable unit, rather than each
    of those being separately authored/wired into Desk by hand. This
    probably requires formalizing "DSL" as a real concept in Desk
    first (right now the tempui DSL is a fixed, hand-written set of
    keywords/interpreters in `src/desk/temp_ui.py`, not a general
    mechanism other DSLs could plug into). Two sub-parts that
    formalization would likely need: a DSL for *specifying* a DSL
    (possibly with embedded code for its interpreter/behavior) — a
    meta-DSL a domain package author writes to define a new DSL's
    keywords/grammar/semantics, rather than hand-writing Python
    interpreter code the way tempui's own keywords are today; and a
    DSL for *specifying widgets* themselves, as a more declarative
    alternative to hand-authoring `widget.json` + a `build()` function
    (or, for `DefineWidget`, hand-authoring/base64-inlining raw HTML).
  - **Concrete candidate data DSLs.** If/once the DSL formalization
    above happens, candidate new DSLs to build on it: a file/stream
    format DSL, a syntax DSL (e.g. a grammar), a database DSL
    (schema/queries?), and a disk layout DSL.
  - **Widget-composition/packaging ("crystallization").** Let a group
    of widgets be composed/packaged into a standalone "app" that
    doesn't need every one of Desk's own built-in tools available to
    it — a re-architected, packaged subset rather than the full Desk
    environment.

  Not designed — a large, open-ended set of directions, parked
  together as a design space to think about rather than a scoped
  task.

- **New widget: editor-with-view (a side-by-side of the editor + the
  markdown viewer)**

  A concrete instance of the side-by-side container widget (TODO
  `d28885f`): the code editor widget on one side and the markdown
  renderer widget (TODO `6bf83a9`) on the other, so editing a Markdown
  file shows a live rendered preview beside it. Blocked on the markdown
  renderer widget existing first (it already does) and, for a *live*
  preview, on the two communicating — e.g. via the container's
  mediated-event-based messaging (TODO `d28885f`), or simply by both
  pointing at the same file with the viewer's file watcher picking up
  saves.

- **SVG Viewer widget: in-widget zoom/pan**

  It currently only fits the SVG to the widget's own size (aspect
  -preserved). For a large or detailed diagram, independent zoom/pan
  within the widget (distinct from the Workspace Canvas's own zoom of
  the whole widget frame) would help. This rendering now lives in the
  Image Viewer widget rather than a standalone SVG Viewer widget (see
  `design-docs/svg-viewing-and-editing.md`, TODOs `4d21e7c`/`7076af5`)
  — still out of scope for those items, worth its own TODO if it comes
  up.

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

- **Add a minimap for navigating the Desk canvas**

  Originally paired with "scrolling while hovering over a widget
  scrolls the Desk instead of the widget" — that underlying problem is
  now fully resolved (TODO `3846190`/TODO `78bfa41`: a widget under the
  cursor gets *all* of click/right-click/wheel/pinch, no exceptions,
  not even for a non-scrollable widget), which means wheel-scroll is no
  longer available as a canvas-pan gesture at all whenever the cursor
  happens to be over any placed widget. A minimap (like
  `world-timelines`'s) would give panning/navigating the canvas a
  reliable way to work regardless of what's under the cursor.

  Not designed yet -- parking rather than guessing at scope (what the
  minimap should actually show/support beyond "like
  `world-timelines`'s").

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

- **`kind: "html"` widget robustness and docs (from the hex_flower
  blank-page investigation)**

  A cluster of related findings/suggestions from
  `DESK_FEEDBACK-2026-07-13T012144.md` (TODO `4ab5875`, investigating
  `widgets/hex_flower`'s blank page):

  - **Root cause: relative-path sub-resource requests lose the auth
    token.** A widget's main page is loaded with the per-launch token
    as a query parameter, but a plain relative-path browser reference
    (`<script src>`, `<link href>`, CSS `url(...)`, `<img src>`) does
    not carry that query string forward, and a native resource tag
    can't attach a custom header either -- so every such sub-resource
    request arrives at `TokenAuthMiddleware` with no credential and
    gets `401`'d, silently aborting the module/resource graph with no
    console output. This affects any `kind: "html"` widget built as an
    ordinary multi-file web project; only tempui `DefineWidget`
    widgets avoid it today, as a side effect of being forced into one
    inlined HTML file (TODO `91b3f42`), not because anyone
    intentionally avoided the bug. Suggested fix: a same-origin cookie
    set when a widget's main page is served, alongside (not replacing)
    the existing query-param/`X-Desk-Token`-header checks -- cookies
    are the one credential mechanism a browser attaches automatically
    to every same-origin request, including plain `<script src>`/
    `<link href>` loads. Not designed/implemented yet.
  - **Reconsider `DefineWidget`'s single-inlined-file requirement,
    once the above is fixed.** Inlining everything into one
    base64-encoded HTML document is convenient for an agent to author
    quickly, but stops working well for anything non-trivial (as
    `hex_flower`, ported from a real multi-file TypeScript project,
    illustrates). Once the auth gap above no longer forces this, worth
    reconsidering whether `DefineWidget` could support a small set of
    named files (e.g. an HTML entry plus a script and a stylesheet)
    instead of one inlined document. Depends on the item above.
  - **No visible signal when a `kind: "html"` widget fails to load.**
    Right now such a widget that fails for any reason (the token gap
    above, a script error, whatever) just renders as a silent blank
    page indistinguishable from several other failure modes, with no
    console output surfaced anywhere. Worth some visible failure
    signal -- e.g. surfacing the widget's own
    `javaScriptConsoleMessage` output somewhere inspectable (a log
    file, a debug panel), and/or a generic "this widget failed to
    render" placeholder shown in place of a silent blank page.
  - **A known-good, minimal multi-file `kind: "html"` widget
    template.** A checked-in (or docs-referenced) minimal example of a
    working multi-file `kind: "html"` widget would give a future agent
    building something like `hex_flower` a template to diff against,
    rather than discovering gaps like the one above the hard way after
    already doing a real port of an existing project.
  - **Document the auth-token requirement for a widget's own asset
    requests.** `design-docs/architecture.md`'s description of `kind:
    "html"` widgets doesn't mention the auth token at all. It should
    state plainly that every request the browser makes for a widget's
    own page -- not just the top-level navigation -- must carry the
    per-launch token, and that ordinary relative-path resource
    references do not carry the token forward and will be rejected, so
    a widget with more than one file won't load until the underlying
    gap above is fixed.
  - **No single doc lays out what does/doesn't work yet** for a `kind:
    "html"` widget built from scratch (as opposed to a tempui
    `DefineWidget` single-file widget) -- e.g. "single self-contained
    HTML file: works"; "multiple files loaded via relative paths:
    currently broken, see [gap]". Without that, a reasonable,
    competently-built ordinary web project (exactly what happened with
    `hex_flower`) silently fails with zero diagnostic signal and no
    way for whoever built it to have known in advance.
  - **No guidance on how to debug a blank `kind: "html"` widget.**
    Nothing currently tells a widget author how to tell their widget
    failed to load. A "how to debug a blank widget" note (start from:
    is the custom element even defined? check
    `document.querySelector(...).shadowRoot`; are there failed network
    requests?) would shorten this kind of investigation considerably
    -- today the failure mode is a silent blank page with no console
    output, indistinguishable from several other possible failures
    (bad HTML, a crashed script, wrong entry point, etc.).

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
  problem, or something else entirely.

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

- **PDF viewer**

  A widget for viewing PDF files.

- **Pixel editor**

  A widget for pixel-art/raster image editing.

- **Nonlinear soundtrack/video editor with associated tight-bound per-audio-track transcript**

  An editor for audio/video, non-linear (not a simple single-timeline
  cut tool), with a transcript kept tightly bound to its own audio
  track.

- **Hexsheet tools, and generalizing them to work for tables too**

  Widget(s) porting/supporting `hexsheet`'s own tools. Connects to
  `widgets/hex_flower`'s own investigation (TODO `4ab5875`,
  `DESK_FEEDBACK-2026-07-13T012144.md`) -- an earlier, incomplete
  attempt at part of this. Follow-on: once built, generalize the tools
  to also support ordinary tables, not just hex layouts.

- **Rich wiki-style linking and editing of markdown**

  Markdown editing with wiki-style linking between documents (e.g.
  `[[Some Page]]`-style cross-references, backlinks) -- richer than
  the existing Markdown widget's plain rendering.

- **Conlanging tools**

  Widget(s) for constructed-language (conlang) work.

- **Tools for working with different local models**

  Widget(s)/tooling for interacting with local (non-Anthropic) models.

- **Move the receipts app to Desk; bring over some pipeline-debugging tools and computer-vision stuff too**

  Port the existing (external) receipts app into Desk, and pull in
  some of its pipeline-debugging tooling and computer-vision-related
  capabilities as Desk widgets/tools as well.

- **Widget docking (becomes a collapsing panel attached to a side of the viewport)**

  Let a widget be "docked" to an edge of the viewport instead of
  floating freely on the canvas -- turning it into a collapsible side
  panel rather than an ordinary placed widget.

- **Easy screenshot of the view inside Desk, turned into a `.desk_temp` file opened as a Scratch**

  A quick way to screenshot the current canvas view from within Desk
  itself, saved as a file in `.desk_temp` and opened as a Scratch
  widget (or similar) -- rather than needing an external screenshot
  tool and a separate import step.

- **Introduce "scrap" into the project's own vocabulary -- basically "scratch," but Desk-specific**

  A naming idea: "scrap" would mean essentially the same thing as
  "scratch" (arbitrary free-form notes/content), but as Desk's own
  specific term for it. Connects to the already-parked "per-project
  glossary" idea above -- this is exactly the kind of term such a
  glossary would want to capture.

- **Widget toolbar buttons still desync from zoom in the real app,
  despite three attempts (TODO `465c404`, `593a464`, `8afef71`)**

  The underlying bug: native-platform-style-painted Qt controls
  (`QPushButton`, `QLineEdit`, `QToolButton`, etc.) visually desync
  their background/border chrome from their text/position once
  embedded via `QGraphicsProxyWidget` and viewed at a non-1.0
  `QGraphicsView` zoom scale, because native theme painting
  (`QMacStyle` on macOS) doesn't respect the enclosing view's zoom
  transform. See `LEARNINGS.md`'s "A native-style-drawn control ...
  can visually desync from its own click hit-region once embedded in
  a zoomed `QGraphicsProxyWidget`" entry.

  Attempts so far, in order:
  - **TODO `465c404`** (Project Files toolbar) and **TODO `593a464`**
    (Event Log toolbar) each force-set `QStyleFactory.create("Fusion")`
    directly onto the specific affected buttons via `widget.setStyle(...)`.
  - **TODO `8afef71`** (generic fix): a follow-up audit found the same
    bug in 17 of 19 widgets, so rather than repeat the per-widget
    `setStyle()` patch everywhere, the fix moved to the single choke
    point every widget passes through (`WidgetFrame.__init__`,
    `src/desk/shell/widget_frame.py`). While implementing it, direct
    testing found the original `setStyle()`-based approach doesn't
    actually work once a widget is wrapped in a real `WidgetFrame`:
    `WidgetFrame` already calls `setStyleSheet()` on itself (for its
    own border), and **any ancestor's `setStyleSheet()` silently
    overrides a descendant's explicit `setStyle()` call, regardless of
    call order** -- meaning TODO `465c404`/`593a464`'s original fixes
    were likely never actually effective in the real app either, since
    neither fix's own verification wrapped the widget in a real
    `WidgetFrame`. Also found that `style().objectName()` -- the exact
    signal both prior fixes' verification relied on -- can't detect
    this in this offscreen test environment: the untouched default
    style and an explicitly-created Fusion style report as
    indistinguishable objects there. Both gotchas are written up in
    `LEARNINGS.md`. Switched instead to setting a stylesheet
    (`CONTENT_ZOOM_SAFE_STYLESHEET`) directly on each widget's content
    root, giving `QPushButton`/`QToolButton`/`QLineEdit` explicit
    `background`/`border`/`padding` rules so Qt's CSS engine paints
    them instead of deferring to native theme calls -- the same
    mechanism that already made the Todo/Questions widgets'
    `FILTER_BUTTON_STYLE`-styled buttons immune to this bug. Verified
    extensively headlessly by pixel-sampling actual rendered output
    (`widget.grab().toImage().pixelColor(...)`, since
    `style().objectName()` proved unreliable) across static controls,
    dynamically-added controls, a pre-built subtree, pseudo-states, and
    several real widgets (`svg_viewer`, `lightning_round`,
    `project_files`, `event_log`) -- all passed.

  **2026-07-15: confirmed still broken in the real running app.**
  After TODO `8afef71` landed, the Event Log widget's toolbar buttons
  still do not scale with zoom -- the same symptom as the original
  screenshot report, despite every headless verification check above
  passing. Root cause of the discrepancy not yet found. The leading
  suspect, not yet confirmed: this project's headless verification
  (`QT_QPA_PLATFORM=offscreen`) doesn't reproduce real `QMacStyle`
  native chrome painting, and something about how the CSS engine
  interacts with real native theme painting -- as opposed to the
  offscreen platform's painting -- may make the stylesheet cascade
  behave differently than it did in every headless test. This is
  speculative; it hasn't actually been tested directly.

  Not fixed -- parking here (per explicit request) so it doesn't block
  other work, rather than continuing to iterate on a third design
  blind. When picked back up: test directly in the real running macOS
  app rather than relying on headless verification alone (a gap
  flagged, but not actually caused a wrong conclusion, in the first
  two attempts -- this time it did); a real screenshot of the
  before/after state would help confirm whether the stylesheet is
  being applied/painted at all versus painted-but-still-desynced from
  the zoom transform for some other reason. See
  `plans/widget-content-zoom-safe-style.md` (TODO `8afef71`) for the
  full design and verification detail, and `LEARNINGS.md` for the two
  Qt gotchas found along the way.

- **Viewer / (editor?) for code stored base64-encoded in `.desk_temp` and `.desk` files**

  `DefineWidget` tempui files and promoted custom widgets (TODO
  `91b3f42`) store their entire HTML implementation as base64-encoded
  text, both in `.desk_temp` files and in the `.desk` file itself --
  currently opaque/unreadable without manually decoding it by hand. A
  widget for viewing (and maybe editing) that embedded code directly,
  rather than needing an external decode step, would help when
  inspecting or debugging a custom widget's actual implementation.

- **Docs on widget taxonomy and lifecycles**

  A real taxonomy of the different kinds of widget in Desk -- covering
  everything from tempui-placed ones (`Question`, `Scratch`,
  `DefineWidget`-defined custom widgets, ...) through the two built-in
  widget kinds (`python`/`PythonWidgetHost`, `html`/`ChromiumWidget`),
  and also considering each one's actual implementation
  language+paradigm (a `widgets/<id>/widget.py` Python `QWidget`
  subclass vs. a hand-authored `DefineWidget` inline HTML/CSS/JS
  document vs. a TS-authored `custom_widget_src/<name>/` one, once TODO
  `b324217`'s build pattern exists -- these aren't the same thing even
  when they end up looking similar at runtime once placed). Each
  taxonomy entry should document its own lifecycle (creation/
  placement, restore-on-reload, hot-reload behavior, promotion where
  applicable, teardown) with its own Mermaid chart, rather than one
  giant diagram trying to cover every kind at once. The documentation
  should be organized so that an agent working specifically on a
  tempui widget doesn't need to read about, say, a built-in Python
  widget's own lifecycle to understand tempui's -- split by taxonomy
  entry (mirroring how the `tempui-*.md` split-doc convention already
  separates unrelated DSL concerns from each other) rather than one
  monolithic document covering every kind of widget at once.

- **A way for agents (e.g. a CLI coding session working in this repo)
  to reach into the running app for more than just reading/writing
  files -- starting with forcing a save**

  Surfaced when asked whether an agent working here could see a new
  Event Recorder widget's (TODO `8d4826c`) state after it's placed on
  the current Desk: right now the only channel into a running Desk
  instance from outside the GUI process itself is the filesystem --
  reading whatever's already been written to a `.desk` file,
  `.desk_temp/`, etc. `save_current_desk()` (`src/desk/shell/window.py`)
  only actually runs on specific structural actions (quit, Desk
  switch, widget removal/rename, ...), not automatically after
  ordinary widget interaction (e.g. clicking Event Recorder's "Record
  for 5s"). So a filesystem-only agent has no way to force a fresh
  snapshot of live widget state onto disk without asking the human
  user to quit or switch Desks first.

  The existing Bridge API (`src/desk/server/app.py`, `/api/bridge/...`)
  already lets one *widget* call into the running app (workspace
  state, local storage, opening/closing widgets, publishing events,
  cross-widget introspection via `/api/bridge/introspect/snapshot`) --
  but every endpoint is scoped to a specific widget instance/token
  (`require_caller`/`require_instance_id`), not to an out-of-band
  caller like a CLI agent working in the repo outside any widget.
  Worth thinking about whether that same Bridge API could be extended
  with a distinct "agent" caller identity, or whether a separate,
  narrower channel makes more sense -- starting with the single most
  obviously useful capability: forcing an on-demand
  `save_current_desk()` so an agent doesn't have to wait for/ask for a
  structural action to happen first.

  Broader than just "force save" once started: what else should an
  agent be able to reach into the running app for -- e.g. listing
  currently-placed widgets and their instance ids without parsing the
  `.desk` file by hand, reading a specific widget's *live* (not just
  last-saved) local storage, or triggering a specific widget action
  programmatically? Connects to the already-parked "how should Claude
  better engage with tempui" and claude-widget items above, and to the
  process-tracking meta-questions item's "real database/microservice
  for work tracking" tangent -- this is the same underlying shape (a
  real API surface for an agent to talk to Desk) applied to live app
  state instead of task tracking.

  Not designed -- needs its own security/trust discussion (should any
  local process be able to force actions in a running GUI app the user
  is looking at, and if so how is that authenticated/scoped) before
  picking a mechanism.
