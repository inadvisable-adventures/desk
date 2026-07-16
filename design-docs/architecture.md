# Desk — Architecture & Design

## Overview

Desk is a Python desktop application, built on PyQt6. The zoomable/pannable
workspace itself — the "canvas" — is a native Python/Qt surface (a
`QGraphicsView`/`QGraphicsScene`), not a web page.

**Widgets are written in Python and render directly in the app as native Qt
widgets.** Since Desk is already a Qt application, the default way to build
and display a widget is a normal Qt pattern: a widget module exposes a
`build() -> QWidget`, the Desk Shell imports it directly and places the
resulting `QWidget` on the canvas (via `QGraphicsProxyWidget`) — no HTTP,
no local server, no browser involved for this default path at all.

A second, non-default widget kind exists for cases where a Desk *user*
wants a richer, custom SPA-based widget: such a widget is backed by its own
embedded Chromium browser (via QtWebEngine), pointed at a local webserver
that is part of the Desk process. This Chromium Widget mechanism is meant
more for what Desk users build than for Desk's own development — building
and running Desk (`pip install -e .`, `python -m desk`) never requires
Node, `npm`, or `tsc`; Desk is still able to run those tools on behalf of a
widget that needs them, but that's opt-in per-widget, not baseline. Browser
-side widget code that does exist follows the conventions in `CLAUDE.md`
(TypeScript in strict mode, minimal dependencies/bespoke solutions over
frameworks, `<template>`/`<slot>` over inline HTML in web components).

Both widget kinds can be dynamically reloaded without restarting the app —
edit a widget's source and see the change live, whether it's a native Qt
widget getting rebuilt or a Chromium widget's page reloading.

Two widgets are first-class citizens of Desk itself:

- A **code editor widget** (`QScintilla`-based) for opening, editing, and
  saving files. Full Desk-awareness — knowing it's running inside Desk and
  calling back into Desk's own APIs (workspace state, other widgets) — is
  aspirational; today it's a self-contained editor with plain file-dialog
  I/O and no automatic knowledge of the current Desk's directory (see
  [Components](#components) and `plans/code-editor-widget.md`).
- A **console widget** that hosts a real shell (bash), so that the user can
  run arbitrary commands — most importantly, launch `claude` (Claude Code)
  and interact with coding agents.

(Both ended up native-Qt rather than Chromium-based — see [Key Design
Decisions](#key-design-decisions--tradeoffs).)

This document describes the system's components, how they fit together, the
key design decisions behind that structure, and the tradeoffs considered.

## Goals

- A native-feeling desktop app (single window, native menus/shortcuts,
  native pan/zoom) whose default widgets are also native — Python code that
  builds and returns a `QWidget`, following ordinary Qt patterns, with no
  local server or browser involved.
- A workspace metaphor: an infinite pannable/zoomable 2D canvas holding
  widgets, similar to a whiteboard or node-graph editor — implemented
  natively in Qt.
- Widgets are dynamically loaded and can be reloaded in place (no full app
  restart) while iterating on them — for native Qt widgets, this means
  rebuilding the widget from freshly-reloaded source; for Chromium widgets,
  reloading the page.
- Python is the preferred/default widget language. HTML/CSS/TypeScript is
  available for a Desk user who wants a rich, custom SPA-based widget, via
  the same Chromium Widget/Local Web Server mechanism, but is not the
  default and is not needed for Desk's own baseline operation.
- Desk itself builds and runs with only Python tooling — no Node/npm/tsc
  required for baseline operation (see Overview).
- A code editor widget and a console/terminal widget are built in, and both
  are aware they're running inside Desk (they can query/drive Desk, not just
  render inertly inside it).
- The console widget can run a real shell so the primary coding-agent
  workflow — running `claude` in a terminal — works exactly as it would in
  any terminal emulator.

## Non-Goals (for now)

- Multi-user / remote collaboration. Desk is a local, single-user desktop
  tool. The local webserver (used only for Chromium/HTML widgets) binds to
  loopback only.
- A plugin marketplace or remote widget distribution. Widgets are loaded
  from the local filesystem.
- Mobile or web-hosted deployment. Desk is a native desktop shell.
- Sandboxing against actively malicious widgets. Widgets are trusted local
  code (the same trust level as any other script the user runs) — native
  Python widgets in particular run directly in the Shell process with no
  isolation boundary at all (see
  [Security Considerations](#security-considerations)).

## System Architecture

```
┌───────────────────────────────────────────────────────────────────────┐
│ Desk Shell (PyQt6 process)                                            │
│                                                                         │
│  ┌───────────────────────────────────────────────┐  ┌───────────────┐ │
│  │ QMainWindow                                     │  │ Local Web     │ │
│  │  └─ WorkspaceView (QGraphicsView/Scene, native  │  │ Server        │ │
│  │     pan/zoom — the Workspace Canvas)            │  │ (in-proc,     │ │
│  │                                                   │  │  Python) —    │ │
│  │   ┌───────────────┐  ┌───────────────┐          │  │  only for     │ │
│  │   │ PythonWidgetHost│  │ ChromiumWidget │  ...    │◄─┤  kind:"html"  │ │
│  │   │ (QWidget built  │  │ (QWebEngineView│         │  │  widgets:     │ │
│  │   │  by the widget's│  │  in a          │         │  │  - static     │ │
│  │   │  build(), in a  │  │  QGraphicsProxy│         │  │    assets     │ │
│  │   │  QGraphicsProxy │  │  Widget item), │         │  │  - REST API   │ │
│  │   │  Widget item);  │  │  loads its SPA │         │  │  - WebSocket  │ │
│  │   │  imported &     │  │  from the      │         │  │    API        │ │
│  │   │  called         │  │  Local Web     │         │  │  - PTY        │ │
│  │   │  directly, no   │  │  Server        │         │  │    session    │ │
│  │   │  HTTP/server    │  │                │         │  │    manager    │ │
│  │   └───────────────┘  └───────────────┘          │  └───────────────┘ │
│  │           ▲                   ▲                   │          ▲        │
│  │           └───────────────────┴── HotReloadBroker ─┼──────────┘        │
│  │              (in-process Qt signal, thread-safe:    │                  │
│  │               watcher thread → GUI thread)          │                  │
│  └───────────────────────────────────────────────────┘                  │
│                                                                         │
│  WidgetWatcher (background thread, via the shared File Watcher Service) │
│  watches widgets/ and feeds the HotReloadBroker for both widget kinds.  │
└───────────────────────────────────────────────────────────────────────┘
```

Native Python widgets never touch the Local Web Server or HTTP at all —
they're imported and instantiated directly by the Shell. Only `kind:
"html"` Chromium widgets go through it, for static asset serving and the
Desk Bridge API.

### Components

1. **Desk Shell** — the PyQt6 process. Owns the `QMainWindow`, the native
   Workspace Canvas, application lifecycle (startup/shutdown), native OS
   integration (menu bar, tray icon, global shortcuts, file dialogs). Also
   directly discovers and loads `kind: "python"` widgets (no server
   involved for those) and starts the Local Web Server (for `kind: "html"`
   widgets and the Bridge API).
2. **Local Web Server** — an in-process, part-of-Desk FastAPI + uvicorn
   server (Python) bound to `127.0.0.1` on an OS-assigned port. Serves only
   `kind: "html"` widgets' static SPA assets, and exposes the Desk Bridge
   API (REST for request/response calls, WebSocket for streaming/events:
   PTY I/O, workspace state sync). It has nothing to do with `kind:
   "python"` widgets.
3. **Workspace Canvas** — a native `QGraphicsView`/`QGraphicsScene` owned by
   the Desk Shell, implementing the pannable/zoomable surface directly in
   Qt (drag-to-pan, wheel-scroll/trackpad-pinch-to-zoom via view
   transforms, plus a small screen-space zoom control HUD) — no web page
   involved. Widgets of either kind are placed on it as
   `QGraphicsProxyWidget` items, wrapped in the common drag/resize chrome
   specified in `design-docs/widget-ux.md`, which also covers zoom
   input handling and why widget chrome stays a constant screen size
   while content zooms with the view. Also accepts OS-level file drops
   (TODO 5915ac2): dropping a file from outside Desk (Finder, another
   app) opens it by reference to wherever it already lives on disk —
   never copied into the project — in whichever widget kind its
   extension maps to (Markdown for `.md`, Image Viewer for `.svg`/raster
   images, Editor otherwise), which automatically picks up the
   "[EXTERNAL]" titlebar indicator the moment it's opened, since a
   dropped file is essentially always outside the current Desk
   directory. See `plans/drag-drop-open-external.md`.
4. **Python Widget Host** — the default, preferred building block: given a
   widget directory with a `widget.py` exposing `build() -> QWidget`,
   imports that module and calls `build()` directly (no subprocess, no
   HTTP), embedding the resulting `QWidget` on the canvas. On hot reload,
   re-imports the module fresh and swaps in a newly-built widget in place.
5. **Chromium Widget** — the building block for an SPA-based widget: a
   `QWebEngineView` (embedded on the canvas via `QGraphicsProxyWidget`) that
   loads that widget's URL from the Local Web Server. This exists for Desk
   users who want a custom, rich SPA widget — not the default path.
6. **Hot Reload Broker** — an in-process publish/subscribe point (a
   `QObject` with a Qt signal) connecting the `WidgetWatcher`'s background
   thread to the specific widget host (of either kind) on the GUI thread
   whose source changed, using Qt's thread-safe signal delivery.
7. **Widget Framework** — the manifest format, discovery/loading, and
   lifecycle (mount/unmount/reload) for widgets in general, built on top of
   the Python Widget Host (default) and Chromium Widget (for HTML/TS
   widgets) (see [Widget Model](#widget-model)).
8. **Desk Bridge API** — the capability-scoped interface *Chromium* widgets
   use to talk to Desk: read workspace state, read/write files, open/close
   other widget instances, introspect its own manifest. Implemented as
   REST endpoints on the Local Web Server (no WebSocket channel yet — see
   [Desk Bridge API](#desk-bridge-api)), wrapped by a small plain-JS client
   library injected into every Chromium Widget's page. Native Python
   widgets don't need this — they can just import Desk's own Python
   modules directly, in-process (see [Key Design
   Decisions](#key-design-decisions--tradeoffs)).
9. **Code Editor Widget** — a built-in `kind: "python"` widget (a
   `QScintilla`-based editor, not Chromium/Monaco — resolved; see Key
   Design Decisions) providing open/edit/save for a single file, with
   syntax highlighting selected by file extension. File I/O goes through a
   plain `QFileDialog`, not automatic Desk-directory awareness — at the
   time this widget was built, no `python` widget had a way to learn the
   current Desk's directory; `desk.shell.current_context` (see item 11's
   TODO Widget) since closed that specific gap, but this widget hasn't
   been revisited to use it (see `plans/code-editor-widget.md`). Watches
   its open file via `desk.file_watch.SingleFileWatcher` (TODO cee6f74)
   — an external change reloads silently if there are no unsaved local
   edits, or is flagged in the title label (without touching the
   buffer) if there are, e.g. when the TODO Widget writes a `TODO.md`
   this widget also has open. This "just works" across widgets with no
   extra plumbing because of the File Watcher Service's existing
   de-duplication (item 19) — every `SingleFileWatcher` on the same
   file's parent directory shares one native schedule and independently
   filters down to its own exact target path.
10. **Console Widget** — a built-in `kind: "python"` widget (a
    `QPlainTextEdit`-based terminal over a real PTY running `bash`, not
    Chromium/`xterm.js` — resolved; see Key Design Decisions) so the user
    can run anything a terminal can run, including `claude`. Real ANSI/
    VT100 interpretation via `pyte` (cursor position, screen-buffer state,
    color/attributes) renders the actual current terminal screen, so
    full-screen, redraw-in-place programs (`claude`'s own interface
    included) display correctly — not the regex-stripped/append-only
    approach an earlier version of this doc described, which broke
    exactly that case. `bash`'s working directory defaults to the current
    Desk's own directory (TODO `f447303`, via `TerminalWidget`'s `cwd`
    parameter) — previously unset, so it silently inherited wherever the
    Desk process itself happened to be launched from.
11. **TODO Widget** — a built-in `kind: "python"` widget
    (`widgets/todo/`) that reads the nearest `TODO.md` relative to the
    current Desk's directory (via `desk.shell.current_context` — a
    minimal, signal-free get/set pair; see `plans/todo-widget.md` for why
    that's enough for now) and shows it as a filterable
    (complete/incomplete/pending/superseded), drag-and-drop-reorderable
    list, with a hovering add-item dialog (matching `WidgetSpawnMenu`'s
    `Popup` pattern). Both reordering and adding write the file and commit
    it via real `git` operations scoped to the target file's own
    repository (skipped, not an error, if it isn't one) —
    reprioritization debounces its commit (1 minute of inactivity, or an
    add arriving first, which folds both changes into one commit).
    Parsing/rendering (`desk.todo_file`) and id generation
    (`desk.todo_ids`, also used by `scripts/todo_item_ids.py`) are shared,
    reusable modules, not widget-internal code.
12. **Claude Widget** — a built-in `kind: "python"` widget
    (`widgets/claude/`) that spawns the same real-PTY/`pyte` terminal
    mechanism as the Console Widget, then types an `exec claude …`
    invocation into the freshly-spawned shell: the shell's own startup/
    profile — `PATH`, aliases, `nvm`, etc. — loads first (same as a user
    launching it from a real terminal), then `exec` replaces the shell
    with `claude` in the same PTY process, so **quitting claude ends the
    PTY and the widget closes itself** rather than dropping back to a
    shell (TODO 5ddbef0, via a `TerminalWidget.process_exited` signal the
    DeskWindow binding uses to remove the frame). If `claude` isn't
    found, bash's `exec` fails and the interactive shell stays usable, so
    a missing `claude` still doesn't leave a dead pane. The
    initial prompt tells `claude` it's running inside Desk and points it
    at the current Desk's `.desk_temp/desk-temporary-ui.md` (via
    `desk.shell.current_context`, falling back to a plain relative-path
    description if no current Desk directory is known yet). The shared
    PTY/`pyte` machinery itself (`TerminalWidget`) was extracted out of
    `widgets/console/widget.py` into `desk.terminal_widget` for this
    reuse — widget directories can't import each other directly, so
    shared widget logic lives in `desk.` proper, the same pattern as
    `desk.todo_file`/`desk.temp_ui`. See `plans/claude-widget.md`. Like
    the Console Widget, `bash`'s (and thus, after `exec`, `claude`'s own)
    working directory defaults to the current Desk's directory (TODO
    `f447303`) instead of the Desk process's own cwd.
    **Session persistence/resume (TODO 1d7331b):** the widget's Desk
    `instance_id` is generated as a full UUID and doubles as its claude
    `--session-id` (the same instance_id-as-durable-identity pattern the
    Temporary UI widgets use). A fresh placement launches `claude
    --session-id <instance_id> "<prompt>"`; a widget restored from a
    saved Desk (same `instance_id`) instead launches `claude --resume
    <instance_id>` with no prompt, reconnecting to the same
    conversation. The launch is issued by `DeskWindow._bind_claude_widget`
    post-build (which knows the instance_id and whether it's a restore),
    not by `build()` itself. See `plans/claude-widget-session-resume.md`.
13. **Git Status Widget** — a built-in `kind: "python"` widget
    (`widgets/git_status/`) showing the current Desk directory's git
    status (resolved via `desk.shell.current_context` +
    `desk.git_utils.find_git_root`, same as the TODO/Code Editor
    widgets). Deliberately polls (`QTimer`, a few seconds) rather than
    watching the working tree with `watchdog` — almost any change
    anywhere in a repo can affect `git status`, making a precise watcher
    both complex and the compute burden the feature explicitly needs to
    avoid. The actual `git status`/branch subprocess calls run on a
    background thread (never the GUI thread, same reasoning as the TODO
    widget's own git-commit thread — see `LEARNINGS.md`), skip entirely
    while the widget isn't visible, and only trigger a redraw when the
    output actually changed since the last poll. See
    `plans/git-status-widget.md`.
14. **Markdown (Old, Basic) Widget** — a built-in, **deprecated**
    `kind: "python"` widget (`widgets/markdown_old_basic/`, id
    `markdown_old_basic` — renamed from `widgets/markdown/`/`markdown`,
    TODO 96013cf) that renders a chosen Markdown file via Qt's native
    `QTextBrowser.setMarkdown()` (no Markdown-library dependency) and
    auto-reloads it when the file changes on disk. File watching goes
    through `desk.file_watch.SingleFileWatcher` — a reusable single-file
    watcher (itself backed by the shared File Watcher Service, item 19
    above) extracted from the TODO widget's own original bespoke
    watcher, which now also uses it, so the two watchdog gotchas
    (FSEvents reports symlink-resolved paths; an atomic write lands as
    a `FileMovedEvent`/`dest_path`) live in one place; see
    `LEARNINGS.md`. The file is picked via an editor-style "Open" button
    seeded from the current Desk directory (`desk.shell.current_context`)
    and, like the Code Editor, is not persisted across a reload (the
    widget contract has no per-instance state payload yet — see
    `PARKINGLOT.md`). Replaced as the default Markdown experience by the
    widget in item 16 below, kept around deprecated (shown collapsed in
    the widget-add menu's Deprecated group, TODO ed483e2) rather than
    removed. See `plans/markdown-renderer-widget.md`.
15. **Sheet Widget** — a built-in `kind: "python"` widget
    (`widgets/sheet/`): a basic `QTableWidget`-backed spreadsheet with
    interactively resizable rows/columns, word-wrapped/clipped cells,
    all entries left-aligned and vertically centered (via each item's
    `textAlignment` plus a `setItemPrototype` so user-typed cells
    inherit it), and Add/Delete row & column controls. It serializes
    to/from **TSV** (tab-joined columns, newline-joined rows; ragged
    rows padded on load) through an editor-style Open/Save/Save As
    toolbar seeded from the current Desk directory. Like the Code
    Editor/Markdown widgets, the open file isn't persisted across a
    reload (no per-instance state payload — see `PARKINGLOT.md`); a `•`
    dirty marker flags unsaved edits. See `plans/sheet-widget.md`.
16. **Markdown Widget** — a built-in `kind: "python"` widget
    (`widgets/markdown/`, id `markdown` — renamed from
    `widgets/markdown_ex/`/`markdown_ex`, TODO 858752b, becoming the
    new default Markdown experience and replacing item 14 above, which
    was renamed to `markdown_old_basic` and deprecated in the same
    swap): a left-hand TOC `QTreeWidget` plus a foldable, heading-nested
    section view of the rendered document, with inline Mermaid diagram
    rendering. The raw Markdown is split (fence-aware, so a `#` inside
    a code block is never mistaken for a heading) into heading/text/
    ```mermaid blocks; each text chunk is fed to its own auto-height
    `QTextBrowser.setMarkdown()` (reusing Qt's native Markdown/image/
    indirect-SVG handling for free, same as the deprecated old-basic
    widget — see `qtextbrowser-images-svg-controls.md`), and each
    `mermaid` fence is rendered by `desk.mermaid.MermaidDiagramWidget`. Folding
    and the TOC are pure native-Qt composition (nested `QToolButton`
    disclosure sections) — no HTML/JS involved anywhere in this widget.
    `desk.mermaid` is a **bespoke, intentionally partial** Mermaid
    parser/layout/`QGraphicsScene` renderer (flowchart basic shapes +
    flat state diagrams only) rather than a vendored `mermaid.js` —
    per `CLAUDE.md`'s dependency aversion and direct user direction;
    any other diagram type or unparseable source falls back to showing
    the raw fenced source as plain text instead of erroring. See
    `plans/markdown-ex-widget.md`. Also TempUI-backed (TODO `42dd260`):
    an `OpenMarkdown <path>` temp-ui file (see
    `.desk_temp/desk-temporary-ui.md`'s DSL doc, `src/desk/temp_ui.py`)
    places a new instance and calls its `set_file` with the parsed
    target path — the widget itself needed no changes, since
    `set_file` already existed for programmatic opening. See
    `plans/tempui-open-markdown.md`.
17. **Project Files Widget** — a built-in `kind: "python"` widget
    (`widgets/project_files/`): a `_FileTreeView` (`QTreeView`
    subclass; see below) browsing the current Desk directory via a
    `QFileSystemModel` (lazy per-directory loading, Name column only,
    filtered to include hidden dotfiles/dotdirs — `QFileSystemModel`'s
    own default filter omits them). A search box swaps that out for a
    bespoke, synchronous search-results `QStandardItemModel` (a
    skip-listed — `.git`/`__pycache__`/`node_modules`/`.venv`/`build`/
    `dist` — recursive walk keeping only matches and the ancestor
    directories leading to one, `expandAll()`ed) while non-empty,
    debounced via `QTimer`; clearing it restores the `QFileSystemModel`
    and re-selects whatever file was last selected. **Not** built on
    `QSortFilterProxyModel.setRecursiveFilteringEnabled` — confirmed
    directly that Qt's own recursive filtering only sees data
    `QFileSystemModel` has already lazily loaded, silently missing
    matches in never-expanded branches. Double-click or Return on a
    file row opens it in a **new** Editor widget instance via
    `current_context`'s widget-opener hook (same mechanism the TODO
    widget's "open plan" button uses) — which required adding a public
    `EditorWidget.set_file()` (previously only a private `_load_file`)
    matching `MarkdownWidget`/`MarkdownExWidget`'s own `set_file`.
    `_FileTreeView` overrides `drawBranches` to paint its own simple
    expand/collapse arrow rather than relying on the native platform
    style — a native-style-drawn branch indicator was found to
    visually desync from its own (otherwise-correct) click hit-region
    once embedded in the Workspace Canvas's `QGraphicsProxyWidget` at
    non-1.0 zoom; see `LEARNINGS.md`. See `plans/file-explorer-widget.md`.
18. **Image Viewer Widget** — a built-in `kind: "python"` widget
    (`widgets/image_viewer/`), same shape as the plain Markdown widget
    (Open button seeded from the current Desk directory, `SingleFileWatcher`
    -driven live reload, a `set_file(path)` for programmatic opening):
    displays a single image file scaled to fit the widget with aspect
    ratio preserved, for both raster formats (`QPixmap`) and vector
    (`.svg`/`.svgz`, `QtSvg`'s bare `QSvgRenderer`), dispatched by
    extension and swapped via an internal `QStackedLayout`. Neither
    backend uses a stock `QLabel.setScaledContents`/`QSvgWidget` — both
    stretch non-uniformly to fill their whole rect regardless of the
    image's own aspect ratio (confirmed directly for `QSvgWidget`: a
    circle came out as a wide ellipse); both render into a manually
    letterboxed target rect (`fit_rect`) instead. An invalid/unparseable
    file shows a message instead of crashing or leaving a blank canvas.
    Originally raster-only (TODO `6e731c1`, `plans/image-drop-tempui.md`);
    the vector-rendering path was folded in from a previously-standalone
    SVG Viewer widget by TODO `4d21e7c` — see
    `design-docs/svg-viewing-and-editing.md`.
19. **File Watcher Service** (`desk_services.file_watcher`) — a single,
    process-wide `watchdog.observers.Observer`, lazily constructed via
    module-level `get_service()`. Every file/directory watcher in the
    app (`desk.file_watch.SingleFileWatcher`, `desk.widgets
    .WidgetWatcher`, `desk.shell.temp_ui_manager.TempUiManager`)
    schedules its watch onto this one shared `Observer` instead of
    constructing its own, each keeping its existing public API/signals
    unchanged. This exists because *separate* `Observer` instances
    watching overlapping/nested paths (e.g. a Desk directory and its
    own `.desk_temp/` subdirectory, previously watched by two different
    watchers) collide at macOS's FSEvents layer with `RuntimeError:
    Cannot add watch ... it is already scheduled` — routing every watch
    through one `Observer` eliminates that regardless of path overlap.
    Identical `(path, recursive)` requests from different callers share
    one native schedule and fan out to every subscriber. Also
    centralizes the two watchdog gotchas every consumer used to
    duplicate (FSEvents reports symlink-resolved paths; an atomic write
    lands as a `FileMovedEvent` whose real path is `dest_path`, not
    `src_path` — see `LEARNINGS.md`). See `plans/file-watcher-service.md`.
    A related, smaller shared helper, `desk.file_watch.SelfWriteMemory`
    (TODO cee6f74), centralizes "was this change notification just an
    echo of a write I made myself" the same way — used internally by
    both `SingleFileWatcher.record_own_write` and `TempUiManager
    .record_own_write` instead of each keeping its own separate
    last-written-text dict. `FileWatcherService._unsubscribe` tolerates
    the shared `Observer` already having been fully stopped by the time
    it runs (TODO `03f623a`) — `app.aboutToQuit`'s `get_service().stop()`
    and a widget's own `destroyed`-signal-triggered
    `SingleFileWatcher.stop()` fire at two different, unorderable
    -relative-to-each-other phases of shutdown, so a later `unschedule()`
    call can hit watchdog's own now-cleared internal bookkeeping; this
    used to crash the whole teardown with a `KeyError`, now it's a
    silent no-op (nothing left to unschedule, and the process is
    already quitting either way). See
    `plans/fix-teardown-keyerror.md`.
20. **Questions Widget** — a built-in `kind: "python"` widget
    (`widgets/questions/`) that reads the nearest `QUESTIONS.md` relative
    to the current Desk's directory and shows it as a filterable
    (unanswered/answered/all) list of question entries, each answerable
    via a hovering dialog (question text read-only, answer editable and
    pre-filled if already answered). Mirrors the TODO Widget's shape
    (file watching, `external_path_changed`, git-commit-backed writes)
    but adapted for `QUESTIONS.md`'s own format: an entry can reference
    more than one TODO id, and has just one answered/unanswered state
    rather than TODO.md's four-way status — so there's no drag-reorder
    or debounced commit, since entry order isn't a priority signal here.
    Parsing/rendering (`desk.questions_file`) is a separate, reusable
    module mirroring `desk.todo_file`'s shape, notably handling answer
    text that can itself contain nested parentheses (confirmed directly
    against this project's own `QUESTIONS.md`) via paren-depth tracking
    rather than a naive first-`)` scan. See `plans/questions-widget.md`.
    A `DeskWindow`-owned `SingleFileWatcher` (separate from the widget's
    own instance-level one) watches the nearest `QUESTIONS.md` for the
    current Desk's directory regardless of whether a Questions widget
    is currently open, so a newly-added entry surfaces as the same
    top-right notification mechanism the `.desk_temp` DSL uses; clicking
    it focuses an already-open Questions widget or opens and focuses a
    new one. `desk-temporary-ui.md` (the doc seeded into every Desk's
    `.desk_temp/`) now tells any agent to write open-ended questions for
    the user into `QUESTIONS.md` rather than the tempui DSL. See
    `plans/questions-notification-routing.md`.
21. **Crash Log Widget** — a built-in `kind: "python"` widget
    (`widgets/crash_log/`). `desk.crash_handler`'s global
    `sys.excepthook` (TODO `95f7ce9`) writes each uncaught exception's
    traceback to `.desk_temp/DESK-CRASH-<timestamp>.log` (TODO
    `7f51230`; previously the project directory itself), creating
    `.desk_temp` if needed with no consent prompt (crash logging is a
    non-negotiable diagnostic concern, unlike `TempUiManager`'s own
    creation of the same directory). On startup, `DeskWindow` opens a
    fresh Crash Log widget for every such file not already covered by
    a restored frame (the same "instance_id equals source filename"
    reconnection idea the tempui widgets use, keyed by the log's own
    filename) — leaving one open persists it like any other placed
    widget; closing it without deleting the file means it reopens next
    startup. The widget shows the log's raw text with a **Sanitize**
    button (strips an absolute path's OS/user-specific prefix down to
    its first `src` or `.venv` segment, transforming only the
    *displayed* text, never the file on disk) and a **Delete Log
    File** button (confirmed; deletes the file and closes the widget).
    See `plans/crash-log-widget.md`.
22. **Feedback Widget** — a built-in `kind: "python"` widget
    (`widgets/feedback/`). A free-form text area plus a **Screenshot**
    button (`current_context.get_main_window().grab()` — "internal,"
    not OS-level screen capture) that inserts a markdown image
    reference into the text, and a **Pick UI Element** button that
    shows a full-screen (covering the app's own window, not the OS
    desktop) translucent `_PickOverlay` — one click resolves a short,
    human-readable identifying path for whatever's underneath via a
    new `current_context.get_widget_path_resolver()` hook (wired to
    `WorkspaceView.describe_widget_at_global_pos`, **not**
    `QApplication.widgetAt`, which doesn't resolve into anything
    embedded via `QGraphicsProxyWidget` — the same gotcha already
    documented for `QApplication.focusChanged`, see `LEARNINGS.md`) and
    inserts it into the text at the current caret position. **Save
    Feedback** writes `DESK-feedback-<timestamp>.md` plus any
    screenshot PNGs into the current Desk's directory (the project
    root — feedback is meant to be reviewed/shared, unlike a crash log)
    — one base name, decided once by the first screenshot (or Save
    Feedback itself if none were taken), reused consistently for the
    `.md` and every `-screenshot-N.png` rather than a placeholder
    rewritten later. See `plans/feedback-widget.md`.
23. **SVG Editor Widget** — a built-in `kind: "python"` widget
    (`widgets/svg_editor/`, TODO `7076af5`) for actually editing (not
    just viewing — see the Image Viewer entry above) an SVG's basic
    shape primitives: `<rect>`/`<circle>`/`<ellipse>`/`<line>`/
    `<polyline>`/`<polygon>`/`<path>` (straight segments only — see
    `design-docs/svg-viewing-and-editing.md`'s "Supported element
    types")/`<text>`. `xml.etree.ElementTree` is the single source of
    truth (a wrapper object per recognized element pairs a
    `QGraphicsItem` with the live `ET.Element` it was parsed from;
    anything unrecognized round-trips untouched); a toolbox has one
    create-tool per type, plus two mutually-exclusive editing tools —
    Points (drag a path/polyline/polygon's individual vertices) and
    Shapes (move/resize a whole object, plus a fill/stroke/stroke-width
    property panel). Registered as the built-in `.svg` **edit** handler
    (`file_type_registry.BUILTIN_EDIT_WIDGET_BY_SUFFIX`), so Image
    Viewer's Edit button reaches it automatically. See
    `plans/svg-editor-widget.md`.
24. **Side by Side Widget** — a built-in `kind: "python"` widget
    (`widgets/side_by_side/`, TODO `d28885f`) that hosts two other
    `kind: "python"` widget instances at once, laid out in a
    `QSplitter` (a Swap button exchanges which splitter position each
    slot occupies; an Orientation button toggles horizontal/vertical).
    The first widget to nest another widget's content inside itself —
    each slot's `PythonWidgetHost` is constructed directly (two new
    `current_context` hooks, `get_widget_catalog_provider`/
    `get_hot_reload_broker`, let it do this without going through
    `DeskWindow._place_widget`, since slot content never gets its own
    canvas placement or `WidgetFrame`). A slot's own instance id is
    minted once and persisted (reused verbatim across rebuilds/reloads)
    so a child that keeps its own event-mediator subscriptions or
    widget-local storage doesn't lose them; the container's own
    `get_widget_local_storage`/`set_widget_local_storage` recurse into
    each occupied slot's content the same way, since a nested child
    never gets a top-level `WidgetState` of its own. Inter-widget
    communication is the *existing* mediated event system
    (`desk.event_mediator`, TODO `6f9c51b`) — no bespoke protocol
    invented; the container only guarantees both slots are properly
    bound to the shared bus. `kind: "html"` children are out of scope
    for this first pass. See
    `plans/side-by-side-widget-container.md`.
25. **Event Recorder Widget** — a built-in `kind: "python"` widget
    (`widgets/event_recorder/`, TODO `8d4826c`), a diagnostic tool: a
    "Record for 5s" button swaps the widget's own content out for a
    blank, deliberately childless `_RecordingSurface` filling the same
    space, whose overridden `event()` passively records *every* raw Qt
    event landing on it (no allowlist/blocklist) while still calling
    `super().event(event)` for each one, so normal behavior is
    completely unaffected. After 5 real seconds, the raw time-ordered
    event list is run-length-encoded — chronologically adjacent events
    sharing the same `event.type()` collapse into one summary group
    regardless of how their own individual detail differs, never
    re-merging with an earlier, non-adjacent run of the same type — and
    shown as a read-only table (type / count / elapsed range / first →
    last detail); groups aren't expandable, a one-way summary rather
    than an accordion. The last completed recording's groups persist
    via `get_widget_local_storage`/`set_widget_local_storage`. Built to
    let a user empirically observe which events actually reach a widget
    during a real interactive gesture — motivated by TODO `3846190`'s
    own fix still not resolving a reported trackpad two-finger-scroll
    gesture, and this environment having no way to reproduce real
    trackpad hardware input to investigate further otherwise. See
    `plans/event-recorder-widget.md`.
26. **Popups Service** (`desk_services.popups`, TODO `359684f`) — a
    single shared implementation of "show a desk-internal popup":
    `WidgetFrame(title, content, is_popup=True)` placed on the canvas
    (title + close button only, always frontmost, never lockable, not
    eye-button-focusable) instead of a real `QMessageBox` parented to
    the requesting widget's own content — a native top-level window
    whose position doesn't account for the canvas's own zoom/pan
    transform. Reached by `kind: "python"` widgets via
    `current_context.get_popup_opener()`, and by `kind: "html"` widgets
    via the Bridge API (`POST /api/bridge/popups/show`). See
    `design-docs/widget-ux.md`'s "Desk-Internal Popups" section and
    `plans/desk-internal-popups.md`.

### Widget Model

See `design-docs/widget-ux.md` for the interactive chrome (titlebar/drag,
resize handles) every widget gets on the canvas, regardless of kind — this
section covers what a widget *is* and how its content is built/served, not
the frame around it.

Desk widgets, regardless of implementation language, are defined by a
**manifest** (`widget.json`) in a directory (implemented in
`desk.widgets.discover_widgets`/`WidgetInfo`):

```json
{
  "name": "Console",
  "kind": "python",
  "entry": "widget.py",
  "capabilities": ["pty.spawn", "workspace.read"],
  "default_size": { "width": 640, "height": 400 }
}
```

- `kind` is **required** (`"python"` or `"html"`); everything else is
  optional and defaults sensibly (`name` → the widget's directory name,
  `entry` → `widget.py`/`index.html` depending on `kind`, `capabilities` →
  `[]`, `default_size` → `None`, meaning the canvas's own default). A
  directory with no `widget.json` at all is simply not discovered as a
  widget.
- There is deliberately **no `id` field**: a widget's id is always its
  directory name, never manifest-declared — see
  [Key Design Decisions](#key-design-decisions--tradeoffs) for why.

- **`kind: "python"`** (the preferred/default kind) widgets ship a Python
  module (`widget.py`, or whatever `entry` names) exposing a `build() ->
  QWidget` function. The Desk Shell imports it directly and calls
  `build()` in-process, on the GUI thread, embedding the returned
  `QWidget` on the canvas via a `PythonWidgetHost`/`QGraphicsProxyWidget`
  — no local server, no HTTP, nothing beyond Python and Qt. This is what
  Desk's own shipped example widget (`widgets/demo/`) uses, so `python -m
  desk` never needs Node/npm/tsc, and never round-trips through a browser
  for something Qt already renders natively.
- **`kind: "html"`** widgets ship their own `index.html`/TS(compiled
  JS)/CSS, for a Desk user who wants a richer, custom SPA-based widget.
  Each gets its own `ChromiumWidget` pointed at that widget's URL, served as
  static assets from the Local Web Server (e.g.
  `/widgets/com.desk.console/index.html`). Building such a widget (if it
  uses TypeScript, as `CLAUDE.md` requires for browser code) is the widget
  author's own build step — Desk itself doesn't need it built to run.
  `entry` is currently only honored for `python`-kind widgets — `html`-kind
  serving uses `StaticFiles(..., html=True)`, which always serves
  `index.html` specifically; a custom `entry` for `html`-kind isn't
  supported yet.
- **Tempui-DSL-defined custom widgets** (TODO `91b3f42`) are a third,
  dynamic way a `kind: "html"` `WidgetInfo` enters the live catalog —
  no `widgets/<id>/` directory at all. An agent (or any process writing
  into `.desk_temp/`) can introduce a brand-new widget kind at runtime
  via the `DefineWidget` tempui DSL keyword (see
  `desk-temporary-ui.md`'s own split-out `tempui-custom-widgets.md`,
  TODO `e57ce5f`): its entire
  implementation is one self-contained, base64-encoded HTML document
  (`desk.temp_ui.CustomWidgetDefinition`), decoded to a real directory
  (`desk.custom_widgets.materialize`, cached under
  `.desk_temp/custom_widgets/<keyword>/`) and mounted onto the
  already-running Local Web Server
  (`ServerHandle.mount_html_widget`) — otherwise rendered exactly like
  any other `kind: "html"` widget. `WidgetInfo.tempui_only=True`
  excludes it from the right-click "Add widget" catalog: it can only
  ever be placed via a later tempui file invoking its own new keyword,
  never through the ordinary catalog. Its placed instance's `[TEMPUI]`
  titlebar button offers to promote the definition into the current
  `.desk` file's own `custom_widgets` list — see `design-docs
  /widget-ux.md`'s "TempUI Custom Widgets and the [TEMPUI] Button"
  section for the button itself, and
  `desk.shell.window.DeskWindow._register_custom_widget` for the
  registration path shared by both tempui- and `.desk`-file-sourced
  definitions.

`desk-temporary-ui.md` itself is version-stamped (TODO `f7b1611`): an
HTML-comment note right under its own title (`<!-- desk-temporary-ui.md
version: N -- ... -->`) records a plain, manually-bumped integer
(`desk.temp_ui.TEMPUI_DOC_VERSION`) that the file's author increments
whenever `DOC_TEMPLATE`'s static content changes in a way that would
matter to an agent reading it — never auto-derived, since there's no
reliable way to detect "did this edit change the doc's *meaning*"
automatically. Before opening a Desk (`TempUiManager.provision`, called
at app startup and on every Desk switch), an already-existing doc's
version is checked against the current one; a mismatch — **including no
version note at all**, which always counts as out of date — rewrites
just the static content in place (`desk.temp_ui
.ensure_doc_version_current`), preserving the dynamic custom-widgets
section described above verbatim if present, so a Desk directory
provisioned long before some later doc improvement doesn't keep a
permanently stale copy.

Widgets declare **capabilities** in their manifest; the Desk Bridge only
grants the Bridge API surface a `kind: "html"` widget actually declared
(see [Security Considerations](#security-considerations)) — `kind:
"python"` widgets don't go through the Bridge API at all, since they can
just import whatever Desk-internal Python they need directly.
Capabilities stored on `WidgetInfo` are now enforced by the Bridge API —
see [Desk Bridge API](#desk-bridge-api).

### Hot Reload

A single `WidgetWatcher` (via `watchdog`) watches the whole widgets
directory on a background thread, regardless of widget kind. On a change:

1. The watcher thread determines which widget id the changed path belongs
   to and emits it through the **Hot Reload Broker** — a `QObject` with a
   Qt signal. Qt signal emission is thread-safe: because the broker and the
   widget host instances live on the GUI thread, Qt automatically queues
   the delivery onto that thread regardless of which thread emitted it.
2. For a `python` widget: its `PythonWidgetHost` re-imports `widget.py`
   fresh, calls `build()` again, and swaps the newly-built `QWidget` in
   for the old one (removing/deleting the old one). There is deliberately
   no caching of the loaded module, so this always reflects the latest
   source.
3. For an `html` widget: its `ChromiumWidget` calls
   `QWebEngineView.reload()` — no browser-side WebSocket listener or
   `widget.reload` protocol message is needed, since the "thing doing the
   reloading" is native Qt code, not JS running inside the page. (The
   Bridge API's WebSocket channel is still used for browser-initiated
   streaming, e.g. PTY I/O — just not for this.)

Discovery itself is also live, not just already-open instances' source:
`DeskWindow` re-runs `discover_widgets()` on every `widget_changed` event
(the same signal driving per-instance reload above) and refreshes the
widget catalog (the add-widget menu, and what `widget_id`s it recognizes).
A widget directory added, removed, or whose `widget.json` changes while
Desk is already running takes effect without a restart — see
`plans/generalized-hot-reload.md`.

### Desk Model

A **Desk** is a named set of widget instances together with their state
(each widget's canvas position/size) and the canvas's own pan/zoom, tied to
a directory on disk. Implemented in `desk.desks` (`Desk`, `WidgetState`,
`load_desk`/`save_desk`) and `desk.shell.window.DeskWindow` (which owns the
single currently-open `Desk` for the window — only one window exists for
now, and it can only have one Desk open at a time).

- **File format**: a `.desk` file (JSON) — `{"widgets": [{"widget_id",
  "x", "y", "width", "height", "state"}, ...], "pan_x", "pan_y", "scale"}`.
  A Desk's **name is its file's stem** (e.g. `my-project.desk` →
  "my-project"). Each widget's `"state"` is its **widget-local storage**
  (TODO fb76057) — an arbitrary, JSON-serializable per-instance payload a
  widget can read back on restore (`set_widget_local_storage(data)`) and
  update on every save (`get_widget_local_storage() -> dict`), both duck
  -typed and optional independently, wired generically in `DeskWindow`
  (not a per-widget-kind special case, unlike the existing TempUI/Claude
  bindings — see `PARKINGLOT.md` for whether those should eventually move
  onto this too). Pull-based: read fresh at each actual save, same as
  every other per-widget field, not tracked live. Used by the Stack
  widget (its frame list) and, for their currently-open file path (TODO
  `02eda20`), the Markdown, Markdown (Old, Basic), and Editor widgets —
  the latter three via a shared `desk.persisted_path.resolve_persisted_
  path(raw) -> Path | None` helper that tolerates a since-moved/deleted
  file at restore time by returning `None` (leaving the widget in its
  normal no-file-open placeholder state) instead of crashing or adopting
  a bogus path. A tempui-bound Markdown instance never persists a path
  this way — it's rebound fresh from the tempui file itself on every
  reload instead.
- **Directory association**: by default a Desk's file lives in its
  associated directory (`Desk.directory == Desk.path.parent`); on launch,
  Desk looks for existing `*.desk` files in the current working directory
  (most-recently-modified first) or falls back to `<cwd>/default.desk` (a
  path that may not exist yet — treated as a brand-new, empty Desk). A
  Desk with no saved widgets (TODO `cb2790d`) opens a Markdown viewer on
  the project's `README.md` if it has one, else seeds a Scratch widget
  with a minimal `# <name> README` starter template — replacing the
  original behavior of placing one instance of every discovered widget,
  which was a leftover bootstrapping default rather than a meaningful
  onboarding experience. See `plans/new-desk-default-widgets.md`.
- **Saving**: on quit, and immediately before switching to a different
  Desk or changing the current Desk's directory (so switching can never
  silently lose layout changes) — not continuously/debounced on every
  drag, for now.
- **Recently-used list**: a small global (not per-directory) MRU of
  opened `.desk` file paths, in `~/.desk/recent_desks.json`
  (`desk.recent_desks`), capped at 10 entries, deduped/moved-to-front on
  reopen. `prune_missing_mru_entries()` (TODO `8f5568f`) both filters out
  and actually *persists the removal of* an entry whose file no longer
  exists — used whenever the picker is shown, so a stale entry is
  forgotten rather than silently re-filtered forever; `load_mru()` stays
  a plain, non-persisting read for callers (like `add_to_mru`) that don't
  need that. Clicking an MRU entry whose file vanished since the picker
  was last shown warns (full path in selectable text) instead of
  `switch_desk` silently creating an empty stand-in Desk at that path.
- **Top-left picker UX**: see `design-docs/widget-ux.md`'s Desk Picker
  section for the `DeskPicker` HUD (collapsed half-alpha name label,
  expanding on hover to an MRU dropdown + directory-picker button) and its
  confirm-then-always-save-first switching behavior.
- **Explicitly decoupled (for now)**: the widget *catalog* (available
  widget **types**, from `DEFAULT_WIDGETS_DIR`) is not scoped to a Desk's
  directory — a Desk only affects which widget *instances* are placed and
  where, not which types are available to place. Whether widget discovery
  itself should become directory-scoped (e.g. a per-project `widgets/`
  folder) is an open question for a future item.

## Desk Bridge API

For **`kind: "html"`** widgets only, exposed as `window.desk.*` (a plain-JS
client — see Key Design Decisions for why not TypeScript/built — injected
into each Chromium Widget's page via a `QWebEngineScript` at
`DocumentCreation`, talking to the Local Web Server over REST) —
`python`-kind widgets don't need this, see [Widget Model](#widget-model):

| Call | Purpose | Capability |
|---|---|---|
| `desk.workspace.getState()` | Read the current Desk's live widget layout | `workspace` |
| `desk.fs.readFile(path)` / `writeFile(path, contents)` | Filesystem access | `fs` |
| `desk.widgets.list()` / `open(widgetId, opts)` / `close(instanceId)` | Manage widget instances | `widgets` |
| `desk.events.subscribe(names)` / `unsubscribe(names)` / `publish(name, payload)` / `onMessage(callback)` | Send/receive named messages via Desk's own mediator (TODO `6f9c51b`) | `events` |
| `desk.introspect.snapshot(targetInstanceId)` | DOM tree + console log of *another* widget instance (TODO `9767c1a`) — the only capability that also requires a live, per-request Desk-user confirmation, not just a manifest declaration | `introspect` |
| `desk.self.getManifest()` | A widget introspecting its own manifest | none |
| `desk.self.getLocalStorage()` / `setLocalStorage(data)` | Persist/restore this *instance's* own state across a Desk reload (TODO `5734529`) | none |

A widget ported from an existing project (e.g. `widgets/hex_flower`,
see `DESK_FEEDBACK-2026-07-13T012144.md`/TODO `4ab5875`) very likely
already has its own persistence mechanism (custom events, a global
variable, `localStorage`, whatever the original project used) — none
of that survives a Desk reload here, and porting the widget does not
rewire it automatically. It must be explicitly replaced with
`self.getLocalStorage`/`setLocalStorage` calls above; don't assume the
old mechanism keeps working just because the rest of the port did.

Each call (other than `self.getManifest`/`self.getLocalStorage`/
`self.setLocalStorage`, none privileged) is checked against the calling
widget's declared `capabilities` — coarse, resource-level strings
(`"workspace"`, `"fs"`, `"widgets"`), not one per method; see
`plans/desk-bridge-api.md`'s Key Design Decisions. The caller identifies
its *kind* via an `X-Desk-Widget-Id` header the injected client library
attaches automatically, and (TODO `5734529`) its specific *instance* via
a sibling `X-Desk-Instance-Id` header — `ChromiumWidget`/the injected
client are both constructed with a concrete `instance_id` up front (see
`DeskWindow._place_widget`), the same identity `WidgetState`/`WidgetFrame`
already carry, just newly threaded all the way to the calling page itself
(nothing before TODO `5734529` let the server tell two same-kind widget
instances apart at all, which `self.getLocalStorage`/`setLocalStorage`
fundamentally needs — `WidgetState.state` is per-*instance*).
`self.getLocalStorage`/`setLocalStorage` deliberately resolve the caller
from that header alone, not via the same `discover_widgets(widgets_dir)`
lookup every other route uses (which only ever finds real, on-disk
`widgets/<id>/` directories — see `PARKINGLOT.md` for the resulting gap
this doesn't fully close for tempui-DSL-defined custom widgets and every
*other* Bridge capability).

`workspace.getState`/`widgets.open`/`widgets.close`/`self.getLocalStorage`/
`self.setLocalStorage` touch live `DeskWindow`/`WorkspaceView` state
(the latter two via a new `_html_widget_local_storage: dict[instance_id,
dict]`, the `kind: "html"` counterpart to the existing `python`-kind
widget-local-storage duck-typed contract, TODO `fb76057`), which is
GUI-thread-owned while these routes run on the Local Web Server's
background thread; `desk.shell.bridge.GuiBridge` provides a synchronous
cross-thread call (emits a Qt signal, thread-safe like `HotReloadBroker`,
then blocks only the calling thread — offloaded to an executor so the
asyncio loop isn't stalled — until the GUI thread has run the callable
and produced a result). `fs.*`/`widgets.list`/`self.getManifest` don't
need this at all — plain filesystem/manifest reads served directly from
the request thread.

`widgets.close(instanceId)` needed real per-instance identity, which
nothing in the codebase had before this — `WidgetState`/`WidgetFrame` now
carry a short `instance_id` (generated at placement time, persisted,
backward-compatible with `.desk` files saved before it existed).

**Still no true WebSocket/push channel** (`onStateChange()`-style
subscriptions) — the original reasoning for deferring one still holds
(see `plans/desk-bridge-api.md`'s Scope section: none of
workspace/fs/widgets/self are inherently streaming, and the strongest
originally-cited case, a Chromium-hosted Console widget streaming PTY
output, is moot now that the Console widget resolved native-Qt). `events`
(TODO `6f9c51b`) is the first Bridge API capability with a genuine push
shape, but it's delivered via a long-polled REST route
(`GET /api/bridge/events/poll`, clamped server-side to 30s), not the
existing `/ws` echo endpoint — a real `WebSocket` handshake can't attach
the custom `X-Desk-*` headers `require_caller`/`require_instance_id`
already rely on for every other route (only cookies/query-string are
available at handshake time), so reusing REST plus those two existing
dependencies unchanged won this over a bespoke WebSocket auth path. See
`desk.event_mediator`/`plans/event-mediator-channel.md` for the
mediator-pattern pub/sub core this sits on top of, shared unchanged by
`kind: "python"` widgets via direct import
(`desk.shell.event_broker.EventSubscription`) rather than this REST
surface.

**`introspect` (TODO `9767c1a`) is the first Bridge API capability
gated by a live user confirmation, not just a manifest declaration** —
see [Security Considerations](#security-considerations). Building it
needed two new pieces: `ChromiumWidget` now sets an explicit
`_LoggingWebEnginePage` (overriding the virtual
`javaScriptConsoleMessage` method — there's no signal for this) so
every `html` widget has a small, bounded (200-entry) rolling buffer of
its own console output to query on demand; and `GuiBridge.call_async`
generalizes `GuiBridge.call` for a GUI-thread operation that's itself
asynchronous (`QWebEnginePage.runJavaScript`'s result only arrives via
a later callback) — `call`'s `fn()` is expected to return synchronously,
and a naive attempt to block *inside* `fn()` waiting for that later
callback would deadlock the GUI thread against its own event loop (the
callback that would unblock it can never run while the thread that
would process it is itself blocked waiting). `call_async`'s `starter`
must instead return immediately after kicking off the async operation;
only the original *calling* thread (a background executor thread, same
as every other Bridge GUI-thread call) ever blocks.

## Security Considerations

- The Local Web Server (used only for `kind: "html"` widgets) binds to
  `127.0.0.1` only and uses an unpredictable, per-launch port plus a
  per-launch token required on all requests, so other local
  processes/browser tabs can't drive Desk.
- `kind: "python"` widgets run directly in the Shell's own process, on the
  GUI thread, with no isolation boundary at all — the same trust level as
  any other Python script the user runs, and stronger integration than a
  Chromium widget gets (direct access to Desk's own Python objects, not
  just an HTTP API). There is no sandboxing for these; a misbehaving Python
  widget can affect the whole app (freeze the GUI thread, crash the
  process). This is an accepted tradeoff (see
  [Key Design Decisions](#key-design-decisions--tradeoffs)) since it's the
  same trust model as running any local script directly.
- `kind: "html"` widgets are each their own `QWebEngineView` (its own
  Chromium renderer process), giving them isolation from each other and
  from the Shell process by construction.
- The Bridge API is capability-scoped per the widget's manifest; a `html`
  widget that hasn't declared `pty.spawn` cannot spawn shell processes,
  even though the underlying backend can.
- `introspect` (TODO `9767c1a`) — letting one widget see another's DOM
  and console output — additionally requires the Desk user's live,
  in-the-moment approval of that specific (caller, target) pair, via a
  blocking confirmation dialog; declaring the capability in a manifest
  is necessary but not sufficient. Grants are in-memory only, per Desk
  session, never persisted to disk — switching Desks (or restarting)
  means asking again.
- The Console widget, if Chromium-hosted, is an intentional, explicit "full
  shell access" escape hatch (that's its purpose — running `claude` and
  other CLIs) and is a built-in widget, not something arbitrary third-party
  widgets get by default.

## Key Design Decisions & Tradeoffs

- **PyQt6 + QtWebEngine (Chromium) instead of Electron.** Keeps the app
  backend in Python (matching the rest of the intended ecosystem — spawning
  `claude`, local file/process access, etc.) while still getting a modern
  rendering engine for the UI, for the cases that do want a browser.
  Tradeoff: QtWebEngine ships its own Chromium build (larger install size,
  separate update cadence from system browsers), and PyQt6 licensing
  (GPL/commercial) should be confirmed against Desk's intended distribution
  model.
- **A native (Qt) Workspace Canvas, not a browser-hosted one.** Qt's
  `QGraphicsView`/`QGraphicsScene` provides pan/zoom natively with no extra
  dependencies, and `QGraphicsProxyWidget` is Qt's documented mechanism for
  embedding real widgets (of either kind) as scene items — no need to build
  and maintain a bespoke bundler-based SPA just to get pan/zoom, which also
  cuts against `CLAUDE.md`'s "avoid adding dependencies, prefer bespoke
  solutions" guidance.
- **`python`-kind widgets render as native `QWidget`s built directly by the
  Shell, not via a local HTTP server + Chromium view.** (This reverses an
  earlier version of this document, which routed *all* widgets — including
  Python ones — through a `ChromiumWidget` for a uniform rendering model.)
  Since Desk is already a Qt application, adding an HTTP round-trip and a
  full browser engine just to display Python-generated content was
  unnecessary machinery for something Qt already does natively and more
  directly: a widget module returns a `QWidget`, the Shell embeds it. This
  also means `python` widgets get direct, in-process access to any of
  Desk's own Python code they want to import, with no Bridge API needed at
  all for them. Tradeoff: no HTTP/process isolation boundary for `python`
  widgets (see Security Considerations) — accepted because they're trusted
  local code with the same trust level as any script run directly. Chromium
  is reserved for `kind: "html"` widgets (a Desk user's own custom SPA).
  Both built-in editor-style widgets ended up native-Qt in practice: the
  Console widget uses a `QPlainTextEdit`/`pyte` terminal, and the Code
  Editor widget uses `QScintilla`, rather than `xterm.js`/Monaco.
- **Hot reload for `python` widgets means "rebuild," not "refresh."** There
  is no way to "hot patch" an arbitrary already-constructed `QWidget` tree
  in place, so reload means: re-import the module fresh (no caching) and
  call `build()` again, then swap the new `QWidget` in for the old one.
  This mirrors the "always re-execute fresh, no cache invalidation" pattern
  used previously and gives correct behavior at the cost of full widget
  state being reset on every edit (no preservation of, e.g., scroll
  position or in-widget state across a reload) — acceptable for now; worth
  revisiting if that gets annoying in practice.
- **Hot reload delivered via an in-process Qt signal (Hot Reload Broker),
  not a WebSocket message to the browser.** For `html` widgets specifically,
  since the thing that needs to react to a widget's source changing is
  native Qt code (call `QWebEngineView.reload()`), routing the notification
  through Qt's own thread-safe signal/slot mechanism is simpler and more
  direct than round-tripping through a WebSocket into browser JS that would
  then have needed some way to reload its own page. The Bridge API's
  WebSocket channel remains for genuinely browser-initiated streaming (e.g.
  PTY I/O for a Chromium-hosted Console widget).
- **REST + WebSocket bridge instead of `QWebChannel`, for `html` widgets.**
  `QWebChannel` (Qt's built-in JS↔Python bridge) is a natural first thought,
  but ties the Bridge API to being inside QtWebEngine specifically. An
  HTTP/WebSocket API keeps the same widget SPAs testable in a normal
  browser during development and doesn't preclude adding a `QWebChannel`
  transport later if needed. (Moot for `python` widgets, which don't use
  the Bridge API at all.)
- **PTY-backed console, not a fake/emulated shell.** Whichever way the
  console widget ends up implemented, its entire purpose is to run `claude`
  and other real CLI tools exactly as a terminal would, so it must be a
  genuine PTY (`bash` as a real subprocess), not a restricted or emulated
  command runner.
- **Console widget is native-Qt (`kind: "python"`), not Chromium/`xterm
  .js`.** This is a *built-in, always-shipped* widget, unlike a
  Chromium/`html`-kind widget which is opt-in and something a Desk user
  chooses to add. Pulling in `xterm.js` (and therefore Node/npm/tsc) for
  a core, always-present part of Desk would reintroduce exactly the
  build-tooling dependency the earlier "prefer Python, no build step"
  pivot (see the `python`-kind decision above) deliberately moved away
  from. A plain `QSocketNotifier`-driven `QPlainTextEdit` over a real PTY
  needs nothing beyond the standard library's `pty` module.
- **Real ANSI/VT100 interpretation via `pyte`, not regex-stripped escape
  sequences.** Reverses an earlier version of this decision, which
  stripped escape sequences instead of interpreting them specifically to
  avoid a third-party dependency, accepting that full-screen TUI programs
  wouldn't render correctly as a stated tradeoff. That tradeoff turned out
  to be unacceptable: the concrete evidence (a screenshot of `claude`
  itself producing garbled, overlapping, cursor-less output) is that the
  widget's own explicitly-stated core purpose — running `claude` — is
  what breaks, not some secondary case. Real terminal emulation (cursor
  position, screen-buffer state, color/attribute tracking) is also deep,
  well-trodden territory where a small, focused, pure-Python library
  written for exactly this (`pyte`, LGPLv3, no C extensions) is a better
  bet than a hand-rolled partial VT100 parser accumulating its own subtle
  bugs. `CLAUDE.md`'s "prefer bespoke solutions" is about avoiding
  *unnecessary* dependencies, not refusing a necessary one once a bespoke
  attempt has concretely failed at the feature's stated purpose.
- **Code Editor widget is native-Qt (`QScintilla`), not Chromium/Monaco.**
  Same reasoning as the Console widget: a *built-in, always-shipped* widget
  pulling in Node/npm/tsc for Monaco would reintroduce the build-tooling
  dependency the "prefer Python, no build step" pivot moved away from, for
  a widget a plain native text-editing component handles well. No
  automatic Desk-directory awareness yet either — no `python` widget has a
  way to learn the current Desk's directory today, and building one-off
  plumbing just for this widget would preempt the Desk Bridge API's more
  general solution to the same problem; see `plans/code-editor-widget.md`.
- **Widget id is always the directory name, never read from the
  manifest.** `WidgetWatcher` computes a changed widget's id from the
  first path component under `widgets_dir` (i.e. the directory name) — if
  a manifest's `id` could differ from its directory name, the watcher's
  emitted id and `discover_widgets`'s map key would disagree and hot
  reload would silently never match for that widget. Simplest correct
  choice: don't support a manifest-declared `id` at all; the directory
  name is the identity, full stop. Could be revisited if the watcher were
  changed to resolve ids some other way, but there's no need for that yet.
- **Manifest required, no fallback to inferring `kind` from which file
  exists.** Maintaining two parallel discovery mechanisms (manifest, and
  the old "infer from `widget.py`/`index.html` presence") indefinitely
  would be more surface area for no real benefit, especially since Desk
  only ships one widget of its own. `widget.json` is now the one source of
  truth for a directory to be treated as a widget at all.
- **Bridge API client library is plain JS, not TypeScript, not built by
  `tsc`.** Same reasoning as the Console/Editor widgets: this is built-in,
  always-shipped Desk infrastructure every `html` widget gets
  unconditionally, not a Desk user's own custom widget code. `CLAUDE.md`'s
  "always use TypeScript in strict mode" is about the latter.
- **A synchronous cross-thread call (`GuiBridge`), not a fire-and-forget
  signal, for Bridge routes that touch live `DeskWindow` state.**
  `HotReloadBroker`'s existing pattern (Qt signal, thread-safe emission)
  is fire-and-forget — fine for "a file changed," wrong for "get me the
  current workspace state and give it back as an HTTP response," which
  needs an actual return value. `GuiBridge.call(fn)` blocks only the
  calling (background) thread — offloaded to an executor so it doesn't
  stall the asyncio event loop other requests are being served on — until
  the GUI thread has run `fn` and produced a result.
- **Coarse, resource-level Bridge capabilities (`"workspace"`, `"fs"`,
  `"widgets"`), not one per method.** Matches the level of detail
  `WidgetInfo.capabilities` (a flat `list[str]`) already implies; splitting
  further (e.g. `fs:read` vs `fs:write`) is a small, additive change later
  if a concrete widget actually needs the finer grain.
- **No WebSocket/push channel in the Bridge API yet.** See [Desk Bridge
  API](#desk-bridge-api) — deferred, not abandoned.
- **Minimal, additive `instance_id` on `WidgetState`/`WidgetFrame`, not a
  broader Desk-persistence redesign.** Only what
  `widgets.close(instanceId)` actually requires to be implementable at
  all — this codebase never had per-instance widget identity before (only
  per-*type*), and the Bridge API sketch's own naming already anticipated
  needing it.

## Open Questions

- Whether `kind: "html"` widget SPAs should use a JS framework at all — per
  `CLAUDE.md`'s preference for bespoke solutions over added dependencies,
  the default is plain (strict) TypeScript with no framework/bundler unless
  a specific widget's complexity clearly justifies one.
- Distribution/packaging target (PyInstaller app bundle, pip-installable
  CLI, etc.) and platform scope (macOS-only first, or cross-platform from
  day one)?
- Exact workspace persistence location/format versioning strategy as the
  schema evolves.

These are tracked as they come up; see `QUESTIONS.md` for anything currently
blocking a TODO item.

## Future Work

- Multi-window support (popping a widget out to its own OS window).
- A widget marketplace/registry for sharing widgets beyond the local
  filesystem.
- Richer inter-widget communication (pub/sub bus beyond direct Bridge calls
  or direct Python imports).
- Preserving a `python` widget's internal state across a hot-reload rebuild
  (currently every rebuild is a full fresh `QWidget`, with no state
  carried over).
