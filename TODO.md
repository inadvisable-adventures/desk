# TODO

Items are worked in the order they're listed here, top to bottom — see
`development-process.md`'s "Item IDs" section. Each item has a permanent,
content-derived id (7 lowercase hex digits); ids carry no ordering
information and are never reused or reassigned, even if an item is later
reordered or its description edited.

1239cfd. COMPLETED: Stop using counting numbers to identify TODO items — this
   item's own id (visible once this file is converted, right below)
   proves the scheme it describes. Priority/work order is now
   exclusively the item's physical position in this file, top to bottom;
   sequential numbers were only ever a side effect of that order, not a
   real identity, and renumbering on every reorder was pure churn.
   Replaced with a permanent, content-derived 7-lowercase-hex-digit id
   per item, generated once (`scripts/todo_item_ids.py`) and never
   recomputed afterward — even if the item's own description is later
   edited. Referred to going forward as e.g. "TODO 2c36b01". Performed
   the one-time conversion of this file (every item's leading number
   replaced with its id; every "item N" / "items N/M/..." cross
   -reference in the file rewritten to "TODO <id>" / "TODO <id>/TODO
   <id>..."). `development-process.md` updated with the new scheme (see
   its "Item IDs" section) and the "Prioritizing TODO Items" section
   simplified — reordering is now just moving an item's text block,
   no renumbering step needed. Procedure recorded in
   `how-to-convert-item-id-one-time.md` for reuse in other projects.
c76cf23. COMPLETED: Project scaffolding & dependency management — Python package
   layout, `pyproject.toml`, dev dependencies (PyQt6, PyQt6-WebEngine,
   FastAPI, uvicorn, watchdog, websockets), entry point script.
   [planned: project-scaffolding.md]
bbee592. COMPLETED: Local web server — FastAPI/uvicorn app bound to loopback
   with an unpredictable per-launch port and auth token, static asset
   serving, base REST/WebSocket scaffolding.
   [planned: local-web-server.md]
b7c3757. COMPLETED: Desk Shell — PyQt6 `QMainWindow` + `QWebEngineView` that
   starts the local web server in-process and loads it, basic app
   lifecycle (startup/shutdown, quitting cleanly stops the server).
   [planned: desk-shell.md]
9f7b7a5. COMPLETED (SUPERSEDED by TODO 8941224): Workspace SPA shell — the
   pannable/zoomable canvas viewport (no widgets yet), served as static
   assets by the local web server. Per updated requirements (see
   `CLAUDE.md` and `design-docs/architecture.md`), the web-based Workspace
   SPA has been removed and replaced by a native Python/Qt Workspace
   Canvas — see TODO 8941224. Kept here for history; the Vite-based frontend it
   describes no longer exists in the codebase.
   [planned: workspace-spa-shell.md]
8941224. COMPLETED: Python-native Workspace Canvas & Chromium Widget hot-reload
   backend — replace the Vite-based Workspace SPA with a native
   `QGraphicsView`/`QGraphicsScene` canvas (pan/zoom in Qt, no browser
   involved); local web server (already Python, already part of the Desk
   process) gains per-widget static serving plus a `watchdog`-based source
   watcher; introduce `ChromiumWidget` (a `QWebEngineView` embedded via
   `QGraphicsProxyWidget`) as the generic building block for hosting a
   hot-loaded SPA on the canvas, wired to the watcher through an in-process
   Hot Reload Broker (Qt signal).
   [planned: python-native-workspace-canvas.md]
600eea1. COMPLETED: Fix widget frame drag/resize — the `WidgetFrame` chrome
   (see TODO 6090103) renders correctly (titlebar, resize handle cursors/
   icons all show up as expected in the demo), but interacting with it
   doesn't work: dragging the titlebar doesn't move the widget, and
   dragging the edge handles doesn't resize it. The headless `_on_drag`
   -math checks done when TODO 6090103 was built passed, so the bug is
   likely in the real mouse-event delivery path (e.g.
   `mousePressEvent`/`mouseMoveEvent` wiring, event acceptance, or a
   conflict with `WorkspaceView`'s own `ScrollHandDrag` panning) rather
   than the drag/resize math itself.
   **Prioritized ahead of TODO d3d913d.**
   [planned: fix-widget-frame-drag-resize.md]
d3d913d. COMPLETED: Widget manifest & loader — `widget.json` schema, discovery of widgets
   from a widgets directory (building on TODO 498f727's `python`/`html` kind
   detection), capability declarations, mounting `kind: "html"` widgets as
   `ChromiumWidget` instances on the canvas (building on TODO 8941224's
   primitive) instead of the iframe approach originally described.
   [planned: widget-manifest-loader.md]
45ca161. COMPLETED (SUPERSEDED by TODO 498f727): Python-backed widgets (interim,
   in-process) — a `kind: "python"` widget shipped a `widget.py` with a
   `render() -> str` function, rendered to HTML and served over HTTP by
   the Local Web Server. Per updated requirements (see
   `design-docs/architecture.md`), this has been replaced: `python`
   widgets now render directly as native `QWidget`s with no local
   server/HTTP involved at all — see TODO 498f727. Kept here for history; the
   HTTP-rendering code this item added no longer exists in the codebase.
   [planned: python-backed-widgets.md]
498f727. COMPLETED: Native Qt Python widget hosting — `kind: "python"` widgets ship a
   `widget.py` exposing `build() -> QWidget`; a `PythonWidgetHost` in the
   Desk Shell imports the module directly and embeds the returned
   `QWidget` on the canvas (via `QGraphicsProxyWidget`) — no HTTP, no
   local server, no browser. Hot reload means re-importing the module
   fresh and swapping in a newly-built widget. `discover_widgets`/
   `WidgetWatcher` move out of `desk.server` into a shared `desk.widgets`
   module, since they're no longer HTTP-server concerns. The shipped
   example widget (`widgets/demo/`) becomes a native `QWidget` instead of
   server-rendered HTML. The Local Web Server continues to exist, now
   scoped to only `kind: "html"` widgets + the future Bridge API.
   [planned: python-native-widget-hosting.md]
6090103. COMPLETED: Widget UX chrome (drag/resize) — every widget on the canvas gets a
    common `WidgetFrame` wrapper (built once, at the canvas-integration
    layer, wrapping either a `PythonWidgetHost` or `ChromiumWidget`
    uniformly): a titlebar across the top that acts as a drag handle to
    move the widget, and a frame with resize handles on the left, right,
    and bottom edges. Dragging/resizing must stay correct at any Workspace
    Canvas zoom level. Full spec in the new `design-docs/widget-ux.md`.
    Note: originally marked COMPLETED based on headless verification of
    the drag/resize math only, which missed that interactive dragging
    didn't actually work in the running app (a missing `event.accept()`
    bug); fixed by TODO 600eea1, which also added a realistic event-path
    regression check this item's own verification lacked.
    [planned: widget-ux-chrome.md]
d0d7b37. COMPLETED: Fix zoom/pan interaction & add a zoom control widget — several related
    Workspace Canvas zoom/pan UX problems reported from real trackpad use,
    plus a new always-available zoom control:
    - Trackpad pinch-to-zoom (pinch to zoom out, un-pinch/spread to zoom
      in) doesn't work correctly. `WorkspaceView` currently only zooms via
      `wheelEvent` (`QWheelEvent`, used for both mouse wheels and
      two-finger trackpad scroll), which doesn't distinguish scroll from a
      native pinch gesture — likely needs a `QNativeGestureEvent`
      (`PinchNativeGesture`) handler (or `QGestureEvent` via
      `grabGesture(Qt.GestureType.PinchGesture)`) so trackpad pinch is
      recognized as zoom input, distinct from two-finger scroll.
    - Two-finger-scroll-to-zoom is way too sensitive — needs damping/
      tuning of how `wheelEvent`'s delta maps to the zoom factor.
    - Dragging a widget gets increasingly sensitive as zoom increases.
      Investigated: the drag math itself is zoom-invariant by
      construction and unchanged; synthetic-event testing at non-unity
      zoom in this environment was inconclusive (devicePixelRatio=2.0
      interacting with manually-constructed `QMouseEvent`s — see
      `plans/zoom-pan-interaction-fixes.md`'s Status section and
      `design-docs/widget-ux.md`'s Open Questions). The chrome
      -counter-scaling fix below is the primary fix applied for this
      symptom; **real-hardware re-check recommended**.
    - Interaction model: zooming the canvas currently magnifies
      *everything* uniformly, including widget chrome (titlebar, resize
      handles), since the whole `WidgetFrame` is one `QGraphicsProxyWidget`
      scaled by the view's transform. Titlebars should stay a constant
      size on screen regardless of zoom — only each widget's own content
      area should zoom/pan with the view. Likely requires decoupling the
      chrome's rendering from the view's scale transform (e.g.
      counter-scaling the chrome, or restructuring what actually gets
      scaled).
    - New: a small persistent zoom control, anchored to the lower-right
      corner of the `WorkspaceView`'s viewport in screen space (not part
      of the zoomable/pannable scene), visible only when the current zoom
      is non-unity (≠ 1.0×): a "zoom to fit content" button (fits all
      widgets in view, with a small 0.1% margin), a "reset zoom" button
      (back to 1.0×/default), and a small zoom-level slider.
    **Prioritized ahead of TODO 7845a0f.**
    [planned: zoom-pan-interaction-fixes.md]
7845a0f. COMPLETED: Fix widget drag/resize scaling when zoomed out — confirmed on real
    trackpad hardware (following up on TODO d0d7b37's unresolved open
    question): dragging a widget's titlebar/resize handles is scaled
    (moves too much for a given cursor movement) specifically when the
    Workspace Canvas is zoomed *out*. Root cause under investigation:
    likely that `event.globalPosition()`/`position()`/`scenePosition()` as
    delivered to a `QGraphicsProxyWidget`-*embedded* child widget (the
    titlebar/resize handles) don't reliably reflect the real screen
    position at non-unity view scale — Qt appears to recompute these when
    translating a scene-level mouse event into the embedded widget's own
    `QMouseEvent`, and that recomputation doesn't round-trip cleanly
    through the view's current zoom.
    **Prioritized ahead of TODO 75d5d15.**
    [planned: fix-drag-scaling-when-zoomed-out.md]
75d5d15. COMPLETED: Introduce the Desk concept — a **Desk** is a named set of widgets
    together with their state (including metadata like each widget's size
    and location/position), associated with a directory on disk. Desks
    can be serialized/deserialized to a file, by default stored in the
    associated directory. A Desk's **name is the filename of its
    serialized file**.

    Top-left picker UX (a screen-space overlay over the Workspace Canvas,
    mirroring the zoom control's bottom-right placement from TODO d0d7b37) —
    actually **two pickers side by side**:
    - A **dropdown**: recently-used Desks (MRU) plus a trailing "..."
      entry (opens a full Desk file picker) — for switching which Desk is
      currently open.
    - A **button**: opens a directory picker, to set/change the
      *currently selected Desk's* associated directory.

    By default this picker area renders at **half-alpha** (semi
    -transparent) and shows only the current Desk's name (the two
    controls aren't separately visible); **on hover**, it splits into the
    two distinct controls above (dropdown + directory-picker button).

    Switching to a different Desk (via the dropdown) or changing the
    current Desk's associated directory (via the button) both require
    **confirmation** first, since either means switching away from
    whichever Desk is currently open.

    Each app window (only one window exists for now) can have only **one**
    Desk selected/open at a time.

    This formalizes and supersedes TODO acd87ae ("Workspace persistence") — see
    that item.
    **Prioritized ahead of TODO 37d50f2.**
    [planned: desk-concept.md]
37d50f2. COMPLETED: Add widget instances to a Desk via a right-click typeable-filter menu
    — right-clicking anywhere on the Workspace Canvas opens a small popup
    listing every registered widget type (from the discovered widget
    catalog), with a typeable filter box at the top that live-filters the
    list as the user types (substring match against the widget's
    name/id). Selecting an entry (click, double-click, or Enter with a
    selection) adds a new instance of that widget type to the current
    Desk, placed at the right-click location, sized per the widget's
    manifest `default_size`. Escape or clicking away closes the popup
    without adding anything.
    **Prioritized ahead of TODO 45659cc.**
    [planned: add-widget-context-menu.md]
45659cc. COMPLETED: Console widget — a real shell (`bash`), enabling running `claude`.
    Implementation resolved: native-Qt (a `QPlainTextEdit`-based terminal
    over a real PTY), not Chromium/`xterm.js` — see
    `plans/console-widget.md` and `design-docs/architecture.md`.
    **Prioritized ahead of TODO 255d777.**
    [planned: console-widget.md]
255d777. COMPLETED: Fix console widget rendering for full-screen TUI programs
    (e.g. `claude`) — confirmed via screenshot: running `claude` (Claude
    Code) in the Console widget produced garbled, overlapping, unreadable
    text with no visible cursor. Root cause: the regex-stripped-ANSI
    approach from TODO 45659cc only ever *appended* decoded bytes — it had no
    concept of cursor position, so a program that redraws its UI in place
    (cursor-positioning, box-drawing, colored status bars — exactly what
    `claude`'s own interface does) produced exactly this kind of garbled
    output. Fixed by adding `pyte` (real ANSI/VT100 terminal emulation) and
    rendering the *current terminal screen* from `pyte`'s screen buffer on
    every update, plus a real cursor at the reported position/visibility.
    **Prioritized ahead of TODO 950774b.**
    [planned: console-widget-real-terminal-emulation.md]
950774b. COMPLETED: Fix console widget crash on device-status-report / private
    CSI queries — confirmed via real-app crash log: running `claude` in the
    Console widget crashed the entire app (`Abort trap: 6`) with
    `TypeError: Screen.report_device_status() got an unexpected keyword
    argument 'private'`. Root cause: `pyte` 0.8.2's `Stream` dispatches
    DEC-private CSI sequences (`ESC[?...`) by calling the matching
    `Screen` method with an extra `private=True` keyword argument, but
    most of `pyte.Screen`'s CSI-handling methods (`report_device_status`,
    `cursor_position`, `cursor_to_column`, `set_margins`, and most cursor
    -movement/erase methods) don't accept a `private` keyword or `**kwargs`
    at all — a real, current upstream `pyte` gap (confirmed: 0.8.2 is the
    latest release), not something we got wrong. Fixed with a
    `_ResilientStream(pyte.Stream)` overriding `feed()` to recover
    per-character on a dispatch exception (a whole-call `try/except` was
    tried first but silently dropped real output queued after the bad
    sequence in the same chunk — see the plan's Status section), plus a
    `_PtyScreen(pyte.Screen)` overriding `write_process_input` to actually
    write device-status-report replies back to the real PTY instead of
    pyte's default no-op. Verified against the real originally-reported
    crash: launching `claude` now triggers and survives the exact same
    private-CSI sequence that used to abort the process.
    **Prioritized ahead of TODO 420c40d.**
    [planned: console-widget-pyte-private-csi-crash.md]
420c40d. COMPLETED: Code editor widget — file editing widget using the Desk
    Bridge API (if Chromium-hosted, e.g. Monaco) or direct Python calls (if
    native-Qt, e.g. `QScintilla`) for file I/O and project/workspace
    awareness. Implementation resolved: native Qt via `QScintilla`, not
    Chromium/Monaco (direct instruction). Ships as `widgets/editor/`: open/
    edit/save a file via `QFileDialog`, syntax highlighting selected by
    file extension, unsaved-changes confirmation (Save/Discard/Cancel)
    before opening a different file. Automatic Desk-directory ("project/
    workspace") awareness is explicitly out of scope for now — no `python`
    widget has a way to learn the current Desk's directory yet; see the
    plan for why that's better solved generally by the Desk Bridge API
    (TODO 47b5731) than bolted on ad hoc here.
    **Prioritized ahead of TODO c204861.**
    [planned: code-editor-widget.md]
c204861. COMPLETED: Add a widget close button — an "X" button in the upper-right
    corner of the `WidgetFrame` chrome (see TODO 6090103), which removes the
    widget (from the canvas and the current Desk) after a confirmation
    prompt, to guard against accidental clicks/data loss. A new
    `_CloseButton` chrome element is hit-tested centrally by
    `WorkspaceView` (like the existing titlebar/resize-handle chrome, not
    via a real `QPushButton.clicked`, since the view already intercepts
    every titlebar-area press before it could reach an embedded button —
    see the plan). Verified entirely headlessly (hit-testing, click-vs-
    drag-away semantics, confirm/cancel flow, drag/resize regression) —
    no step needed real-window/visual inspection.
    **Prioritized ahead of TODO 001d042.**
    [planned: widget-close-button.md]
001d042. COMPLETED: Generalized hot reload — extend the single-widget
    hot-reload mechanism (TODO 498f727 for `python` widgets, TODO 8941224
    for `html` widgets) to arbitrary manifest-discovered widgets of both
    kinds. Per-instance source reload already worked generically across
    both kinds (TODO 8941224/TODO 498f727) — the actual gap was that
    `discover_widgets()` only ever ran once at startup, so a widget
    directory added/removed/changed while running had no effect until
    restart. Fixed: `DeskWindow` re-runs
    `discover_widgets()` on every existing `widget_changed` event
    (reusing that signal, no new watcher plumbing needed) and refreshes
    the widget catalog (add-widget menu, recognized `widget_id`s).
    Verified entirely headlessly with a real `WidgetWatcher` against a
    temp directory (new/changed/removed widget directories, plus a
    regression check that per-instance source reload still works).
    [planned: generalized-hot-reload.md]
47b5731. COMPLETED: Desk Bridge API — capability-scoped REST endpoints
    (`workspace.getState`, `fs.readFile`/`writeFile`,
    `widgets.list/open/close`, `self.getManifest`) plus the client library
    injected into each `ChromiumWidget`'s page. Applies only to `kind:
    "html"` widgets — `python` widgets access Desk internals via direct
    Python imports instead (see `design-docs/architecture.md`). Shipped as
    REST-only for now (no WebSocket/push channel — its strongest cited use
    case, PTY streaming for a Chromium-hosted Console widget, is moot now
    that the Console widget resolved native-Qt; see the plan's Scope
    section). Added a minimal `instance_id` to `WidgetState`/`WidgetFrame`
    (backward-compatible with existing `.desk` files) since
    `widgets.close(instanceId)` needed real per-instance identity that
    didn't exist anywhere before. Cross-thread access to live
    `DeskWindow`/`WorkspaceView` state (for `workspace.getState`/
    `widgets.open`/`close`, which run on the Local Web Server's background
    thread) goes through a new `desk.shell.bridge.GuiBridge`. Verified
    entirely headlessly, including a real end-to-end round trip through an
    actual `QWebEngineView` (browser JS → local HTTP server → response).
    [planned: desk-bridge-api.md]
acd87ae. SUPERSEDED by TODO 75d5d15: Workspace persistence — save/restore widget
    instances, their `QGraphicsItem` position/size/z-order (now including
    the `WidgetFrame` chrome from TODO 6090103), and the canvas's pan/zoom
    transform to `workspace.json`. The Desk concept (TODO 75d5d15) formalizes
    this (directory association, named serialization, a directory-picker
    UI) — implement persistence there instead of as a bare
    `workspace.json` with no directory-association model.
71f125a. COMPLETED: Fix console widget selection highlighting and cursor
    visibility — when a TUI program presents multiple selectable options
    (e.g. `claude` offering a choice of several things), no highlight is
    rendered, so the user can't tell which option is currently selected.
    Separately, the terminal cursor still isn't rendered at all, so it's
    unclear where typed text will land, which makes navigating/editing
    multi-line text especially difficult. Both are rendering gaps in the
    `pyte`-based console renderer (see TODO 255d777/TODO 950774b). Root causes confirmed
    directly: reverse video (`ESC[7m` — the standard mechanism for
    terminal selection highlighting, and how many full-screen TUIs draw
    their own cursor) rendered nothing when colors were unset, since
    swapping two "default" colors that both resolved to `None` is a
    no-op; separately, `pyte`'s "bright" SGR colors (`ESC[90-97m`/
    `ESC[100-107m`, e.g. `"brightred"`) weren't resolved at all. Fixed
    with real, concrete default foreground/background colors (never
    `None`) resolved *before* swapping for reverse video, plus a bright
    -color map (including a defensive alias for a confirmed `pyte` 0.8.2
    typo, `"bfightmagenta"`). Verified with genuine pixel-level rendering
    checks (`grab()`/`QImage`/`pixelColor()`), not just property checks —
    the exact gap that let this bug through undetected originally.
    [planned: console-widget-highlight-cursor-rendering.md]
b9ade4f. COMPLETED: Investigate self-window screenshot capability — determine
    whether apps are allowed by default (notably on macOS) to capture
    screenshots of their own windows without extra user/OS permission. If
    so, this would let Desk capture screenshots of itself/its widgets from
    inside the running environment (e.g. useful for verification, or
    letting a widget inspect its own rendered state). **Conclusion: yes,
    no extra permission needed** — `QWidget.grab()`/`.render()` paint a
    widget's own content directly via Qt, never going through macOS's
    system-level screen-capture APIs (the ones that actually require the
    "Screen Recording" permission), so there's nothing for the OS
    permission system to gate. Already Desk's own de facto verification
    technique in practice — every pixel-level rendering check done for
    TODO 255d777/TODO 950774b/TODO 47b5731/TODO 71f125a already relies on
    it, dozens of times, with no permission prompt ever appearing. No new
    capability needed to build;
    a shared `desk.debug.screenshot()` helper is noted as possible future
    work if a second concrete need for one shows up.
    [planned: self-window-screenshot-capability.md]
4adfcad. COMPLETED: Fix Desk picker positioning — the "hovering" Desk picker
    (see TODO 75d5d15), anchored to the upper-left of the Workspace Canvas,
    should stay pinned to the upper-left of the app window itself at all
    times (screen space, like TODO d0d7b37's zoom control), rather than being
    tied to the current Desk/canvas in some way that lets it move or
    disappear when the Desk changes. Root cause confirmed directly: the
    picker was only ever positioned once, at construction, while a
    recurring internal Qt layout pass (plausibly `QGraphicsView`'s
    scrollbar/viewport geometry recalculation) silently displaces it on
    every resize (including the first, at initial `.show()`). `ZoomControl`
    never showed this bug since its bottom-right anchor already forces a
    reposition on every `resizeEvent` regardless. Fixed by reasserting the
    picker's fixed position on every `resizeEvent` too — deferred via
    `QTimer.singleShot(0, ...)`, since the displacing pass runs as a
    separate, later-queued layout event within the same iteration, so a
    synchronous reassertion (a first attempt at this fix) wasn't late
    enough and still got overwritten. Verified headlessly: stays correctly
    positioned after first show, after resizes, and after a real Desk
    switch.
    [planned: fix-desk-picker-positioning.md]
cde51d4. COMPLETED: Fix Desk picker's collapsed-state label — on startup,
    the top-left Desk picker widget (TODO 75d5d15) briefly shows "c" in
    its collapsed (half-alpha, unhovered) state instead of the current
    Desk's name, then on hover it switches to showing "default" and
    incorrectly stays showing "default" (rather than the actual current
    Desk name) even after the mouse leaves and it collapses back down.
    Two confirmed root causes: (1) the picker's outer bounds were locked
    in via `adjustSize()` at construction, while the label was still
    empty, and `set_current()` never re-triggered a resize afterward,
    clipping the label's real text; (2) the MRU dropdown only selected
    the current desk if it found a matching entry already in the
    persisted MRU list — on a desk's first open (before any save/switch
    has called `add_to_mru()`), no match exists, so it fell back to
    showing its first entry instead. Fixed: `set_current`/`set_mru` both
    call `adjustSize()`; `set_mru` inserts the current desk into its own
    entry list if the caller's list doesn't already include it. Verified
    headlessly, including a full-app regression using a real `DeskWindow`
    around a fresh, never-saved desk named "default" (the exact
    originally-reported scenario).
    [planned: fix-desk-picker-label.md]
d1205ef. COMPLETED: TODO widget — reads the "nearest" `TODO.md` (resolved
    relative to the current Desk's associated directory) and displays it
    as a filterable list (complete / incomplete / pending / etc.) of
    items. Each item is shown as at most 100 characters of its
    description, truncated with a trailing "..." if it doesn't fit. UX:
    items can be re-prioritized via drag-and-drop, and a new item can be
    added via an "add item" button that launches a hovering add-item
    dialog. Both re-prioritization and adding a new item must result in
    committing the change — but re-prioritization should debounce the
    commit: hold off until either a new item is added or 1 minute passes
    with no further re-prioritization. Ships as `widgets/todo/`, backed by
    two new shared modules (`desk.todo_file` for parsing/rendering,
    reused id-generation from `desk.todo_ids` — also extracted out of
    `scripts/todo_item_ids.py` so both share one implementation) and a
    minimal `desk.shell.current_context` giving `python` widgets their
    first way to learn the current Desk's directory (deferred since
    TODO 420c40d). Reordering uses `QListWidget`'s built-in
    `InternalMove` drag mode; adding uses a hovering `Popup` dialog
    matching `WidgetSpawnMenu`'s established pattern (TODO 37d50f2);
    commits are real `git` operations scoped to the target file's own
    repo (skipped, not crashed, if it isn't one), with the debounce
    correctly folding a pending reprioritization into an add's immediate
    commit, and a `destroyed`-triggered flush so closing the widget
    doesn't silently drop an unsaved reorder. Verified entirely
    headlessly, including placing the widget via a real `DeskWindow`
    pointed at this project's own directory and confirming it correctly
    loaded this very file.
    [planned: todo-widget.md]
1f9bd34. COMPLETED: Fix zoom control positioning — the zoom control
    widget (TODO d0d7b37), meant to be anchored to the lower-right corner
    of the app window in screen space, should stay pinned to the
    window's bottom-right at all times rather than being tied to the
    current Desk/canvas in some way that lets it move or disappear when
    the Desk changes (same underlying issue as TODO 4adfcad's Desk
    picker). Confirmed exactly that: the control starts hidden and only
    becomes visible the first time zoom leaves 1.0x, so the same
    recurring internal Qt layout-pass displacement TODO 4adfcad found
    wasn't caught until that moment (`(999, 774)` instead of the correct
    `(819, 664)`, confirmed directly) — the earlier investigation's own
    zoom-control check happened to mask this by zooming before resizing.
    Fixed with the identical `QTimer.singleShot(0, ...)`-deferred
    reassertion. Verified headlessly, including a regression check that
    the Desk picker and titlebar drag are unaffected.
    [planned: fix-zoom-control-positioning.md]
fa288ce. COMPLETED: Investigate `pyte`'s `private=True` CSI dispatch gap further — reported
    via pasted console output showing this is still surfacing at runtime:
    ```
    TypeError: Screen.report_device_status() got an unexpected keyword argument 'private'
    WARNING desk_widget_console: pyte failed to dispatch a terminal escape sequence; skipping it
    Traceback (most recent call last):
      File "~/desk/widgets/console/widget.py", line 109, in feed
        taking_plain_text = self._send_to_parser(data[offset:offset + 1])
      File ".../pyte/streams.py", line 213, in _send_to_parser
        return self._parser.send(data)
      File ".../pyte/streams.py", line 353, in _parser_fsm
        csi_dispatch[char](*params, private=True)
    TypeError: Screen.report_device_status() got an unexpected keyword argument 'private'
    ```
    This is the same root cause TODO 950774b already addressed (`pyte` 0.8.2's
    `Stream` calls CSI-dispatched `Screen` methods with an extra
    `private=True` keyword that most of them, including
    `report_device_status`, don't accept) — TODO 950774b's `_ResilientStream`
    is why this now logs a `WARNING` and keeps running instead of crashing
    the app, which is working as designed. Still, this warrants further
    investigation: is skip-and-log an acceptable permanent behavior, or
    should the affected `Screen` methods (`report_device_status`,
    `cursor_position`, `cursor_to_column`, `set_margins`, and other
    CSI-dispatched methods lacking `private`/`**kwargs` support) be patched
    /subclassed to actually handle the private-CSI variant correctly rather
    than dropping it? Also consider whether the warning-per-occurrence
    logging is too noisy for a case this routine (e.g. `claude` appears to
    trigger it on every startup). **Conclusion: keep skip-and-log
    permanently, no `Screen`-method patching** — most affected private
    CSI variants are obscure DEC status reports (printer/UDK/locator/
    macro-space/etc. status) with no single universally-correct reply,
    `claude` already works correctly end-to-end under the current guard
    (TODO 950774b's own verification), and this traceback's specific
    trigger (`report_device_status`, an `n`-suffixed DSR) is a
    *different* private query than TODO 950774b's confirmed trigger (a
    `c`-suffixed device-attributes query) — direct evidence the existing
    per-character guard already needs to (and does) cover multiple query
    kinds uniformly, not just the one first observed. **Logging was too
    noisy**: downgraded from `WARNING` + full traceback to `DEBUG` with no
    traceback — appropriate while newly diagnosed, unnecessary now that
    the root cause is fully understood and documented. Verified
    headlessly (guard still works; log record confirmed `DEBUG`/no
    traceback; full TODO 950774b regression suite re-run).
    [planned: pyte-private-csi-investigation.md]
ef1b2e7. COMPLETED: Hot reload crashes the whole app if a widget's rebuilt module
    raises during import or `build()`, instead of isolating the failure
    to that one widget. Confirmed via a real crash log: while a `claude`
    instance running inside the Desk console widget was actively editing
    `widgets/todo/widget.py` (mid-implementation of a "double-click to
    edit" feature — TODO d49f1cf), a hot-reload fired against an
    intermediate save that referenced a not-yet-defined method
    (`self._list.itemDoubleClicked.connect(self._show_edit_dialog)`,
    `_show_edit_dialog` undefined). Root cause: `PythonWidgetHost
    ._rebuild()` (`src/desk/shell/python_widget.py`) has no exception
    handling around re-importing the module or calling `build()` — any
    error there propagates straight out of `_on_widget_changed`, a Qt
    slot connected to the Hot Reload Broker's signal, which is apparently
    fatal to the whole process in this PyQt6 setup (`AttributeError` →
    `Abort trap: 6`, not just a failure to reload that one widget).
    Given this app's own stated core purpose is running `claude` to edit
    Desk's own widget code live, hitting a transient syntax/attribute/
    import error mid-edit is routine, not a rare edge case — and it
    currently takes down the entire app (losing all other unsaved Desk/
    widget state) every time. Needs: wrap the rebuild path in try/except;
    on failure, log the error and keep the previously-working widget in
    place (don't swap in a broken one) rather than crashing, so a bad
    intermediate save just means "hasn't picked up your latest edit yet,"
    not "the whole app just died." Fixed: `_rebuild()`'s re-import +
    `build()` call is now wrapped in `try/except`, logging an `ERROR`
    with full traceback and leaving the previous widget instance
    untouched on failure; a first-build failure (no previous widget to
    fall back to) shows a small inline error placeholder instead of a
    silently blank widget. Verified headlessly, including directly
    reproducing the exact originally-reported crash (a copy of the real
    `widgets/todo/widget.py` with the exact reported bug reintroduced,
    hot-reloaded) and confirming the app now survives it instead of
    aborting.
    [planned: isolate-hot-reload-crash.md]
8394e40. COMPLETED: The TODO widget list should be scrollable (in a way that
    doesn't get accidentally captured by Desk scrolling). Root cause: the
    TODO widget's `QListWidget` was already a scrollable
    `QAbstractScrollArea` and would have scrolled on a wheel/two-finger
    -scroll like any other Qt list — but it never received that event,
    since `WorkspaceView.wheelEvent` unconditionally treated every wheel
    event as a canvas zoom gesture regardless of what was under the
    cursor. Fixed generically (not TODO-widget-specific, so it also
    covers any future widget with scrollable content): a new
    `_scrollable_at` hit-test (same shape as the existing
    `_hit_test_chrome`) checks whether the cursor is over a
    `QAbstractScrollArea`-based embedded widget and, if so, forwards the
    wheel event via `super().wheelEvent(event)` (Qt's normal
    scene-forwarding path) instead of zooming the canvas. Pinch-to-zoom
    (handled separately via `NativeGestureEvent`) is unaffected. Verified
    headlessly with synthetic `QWheelEvent`s against a real
    `WorkspaceView`: scrolling over an embedded scrollable list scrolls it
    without changing canvas zoom; scrolling over empty canvas background
    still zooms as before; titlebar chrome hit-testing regression
    -checked and unaffected.
    [planned: todo-widget-scrollable.md]
d49f1cf. COMPLETED: double-clicking on a TODO item in the TODO widget
    should pop up an editor. Double-clicking a row opens the same
    hovering popup dialog used to add an item (generalized to
    `_ItemDialog`, taking an optional prefilled description), submitting
    updates that item in place — same permanent `item_id`, recomputed
    `status`/`raw_text` — and commits immediately (folding in any
    pending reprioritization), matching how adding an item already
    works. Picked up from an earlier session's crash (TODO ef1b2e7) that
    left this mid-edit: the `_AddItemDialog` → `_ItemDialog` rename and
    the double-click wiring were already in the file, but
    `_show_add_dialog` still referenced the old class name and
    `_show_edit_dialog`/`_edit_item` were never defined — both finished
    here. Verified headlessly, including exercising the real
    `itemDoubleClicked` signal wiring (not just calling the handler
    directly) and a full add/reprioritize regression check.
    [planned: todo-widget-edit-on-doubleclick.md]
742727d. COMPLETED: In the TODO widget UX, the filtering should be
    better distinguished visually, with a frame around them, and
    styling which better indicates that they are toggle buttons. Filter
    buttons now grouped in their own `QFrame`, separate from the
    Reload/Add Item action buttons, with QSS giving checked buttons a
    distinct filled color/border instead of relying on the platform
    style's often-subtle default checked appearance. Verified headlessly
    (buttons parented to the frame, styled, and toggling still correctly
    shows/hides rows).
    [planned: todo-widget-filter-styling.md]
8db7891. COMPLETED: the add/edit textbox on the TODO widget should be
    much larger, and multiline. `_ItemDialog`'s field is now a larger
    `QPlainTextEdit` (was a single-line `QLineEdit`); plain Return/Enter
    now inserts a newline like normal multiline editing, with
    Ctrl+Return as the submit shortcut (Escape still cancels, the "Add"
    button still submits by click regardless). Verified headlessly,
    including that add/edit both still work end-to-end and that a
    multi-line description is correctly preserved verbatim in the file
    itself.
    [planned: todo-widget-larger-multiline-textbox.md]
0f9445c. COMPLETED: The TODO items in the TODO widget should visually
    appear to be items rather than lines of text, including a small
    frame around each one so that it is clear that it is dragable.
    Styled via `QListWidget::item` QSS (border, rounded corners,
    padding, distinct `:selected` background) plus non-zero item
    spacing, so rows read as distinct cards rather than touching
    unstyled lines of text. Verified headlessly, including regression
    -checking filtering, drag-and-drop reordering, and double-click-to
    -edit are all unaffected by the styling-only change.
    [planned: todo-widget-item-framing.md]
6034b1d. COMPLETED: change the top-left hover ui to always show both the
    name and the associated directory, even when not hovered. The
    label (the only thing that ever showed the name) previously
    disappeared entirely on hover, and no state ever showed the
    directory as readable text — only a button to change it. Now the
    label (`"name — directory"`) is always visible; hover additionally
    shows the MRU dropdown/directory-picker button alongside it rather
    than replacing it. Verified headlessly, including a full-app
    regression via a real `DeskWindow`.
    [planned: desk-picker-always-show-directory.md]
bc75b07. COMPLETED: Simple browser widget with an address bar and
    forward/back/reload buttons. Ships as `widgets/browser/`: a
    `kind: "python"` widget using `QWebEngineView` directly (the same
    "python widgets can use any PyQt6 module directly" pattern the
    Console/Editor widgets already established), not the `ChromiumWidget`
    /local-server machinery (that's for one fixed `kind: "html"` widget's
    own bundled page, not arbitrary user-navigable URLs). Address bar
    uses `QUrl.fromUserInput` (Qt's own standard address-bar-style URL
    interpretation); back/forward buttons track real history
    availability via `QWebEngineView.history()`. Starts at `about:blank`.
    Verified entirely headlessly (address-bar navigation, bidirectional
    address-bar/URL sync, back/forward, button enabled-state), including
    a full-app regression placing it via a real `DeskWindow`.
    [planned: browser-widget.md]
62e8b05. COMPLETED: Bug: Sometimes when editing in the TODO widget's TODO item editor, the text caret will disappear; sometimes it comes back after a few seconds and sometimes it doesn't. it seems like it is loosing focus for some reason. It might be that other processes are stealing focus, but that seems unlikely.
   [planned: fix-todo-editor-caret-focus-freeze.md]
a629bea. COMPLETED: in the TODO widget, the item editor is using the exact same ux as the add, which means that it says "Add" on the bottom. change the UX to have two buttons, "discard" (for both edit and add) and the second button should say "add" (for add) or "save changes" (for edit); in both add/edit, confirm before discarding if there is any non-whitespace text. Also, change the UX so that it doesn't dismiss on click-away.
   [planned: todo-widget-editor-discard-save.md]
43845be. COMPLETED: Add a new Scratch Widget. Scratch is a multi-line
   textbox, but it has a title bar which says `Scratch: [label]` where
   the label is inline-editable. Ships as `widgets/scratch/`: a plain
   `QPlainTextEdit` body under an internal title row (distinct from the
   `WidgetFrame` chrome titlebar, which is a static per-kind string with
   no per-instance update hook) reading `Scratch: {label}`; double
   -clicking the label swaps it for a `QLineEdit`, committing back to
   display form on Enter or focus-out, falling back to `"untitled"` if
   committed blank. No file-backing/persistence — this item only asked
   for the widget itself. Verified entirely headlessly: initial state,
   entering/committing/clearing the editable label, body text entry,
   and a regression check that `discover_widgets` picks up the new
   manifest and a real `PythonWidgetHost` builds a working
   `ScratchWidget`.
   [planned: scratch-widget.md]
d25e557. COMPLETED: Add a file-watcher to the TODO widget so that
   external edits to the todo items are automatically shown. remove the
   "reload" button. if there is a conflict wherein a TODO item changes
   while it is being edited, put the current text into a scratch widget
   and label it with "TODO Item (#) Edit Conflict". A small dedicated
   `watchdog`-based watcher (distinct from the widget-hot-reload
   `WidgetWatcher`) watches the resolved `TODO.md`'s parent directory,
   debounced, reporting changes via a `pyqtSignal` relay (mirroring the
   existing commit-result relay). `_write_and_commit` now records the
   exact text it wrote so the watcher can tell its own echoed write
   apart from a real external edit. Currently-open edit dialogs are
   tracked (`item_id -> (dialog, description-as-loaded)`); on a real
   external change, any open edit whose item is now gone or whose
   description no longer matches the loaded snapshot is a conflict: its
   in-progress (possibly unsaved) text is moved into a new Scratch
   widget (TODO 43845be) labeled `TODO Item ({item_id}) Edit Conflict`,
   and the stale dialog is closed. A pending, uncommitted local
   reprioritization is flushed to disk first so it isn't silently lost
   by the reload. Since no `python` widget could previously place
   another widget instance on the canvas, added a minimal
   `current_context.set_widget_opener`/`get_widget_opener` pair (same
   shape as the existing current-directory hook) backed by a new
   `DeskWindow.open_widget_content` (returns the actual built widget
   instance, via a new `PythonWidgetHost.current` property) and a small
   `ScratchWidget.set_label`. The Reload button is removed from the
   toolbar. Verified entirely headlessly, including a real `watchdog`
   `Observer` picking up a genuine on-disk external change end-to-end
   (hitting, then fixing, the same macOS symlinked-`tempfile.mkdtemp()`
   -path gotcha `LEARNINGS.md` already documents for `WidgetWatcher`),
   the self-write echo being correctly ignored, the conflict/non
   -conflict paths (via a fake installed opener), the full add/edit/
   reprioritize regression, and a real `DeskWindow`'s opener wiring
   placing a genuine `ScratchWidget`/`BrowserWidget`.
   [planned: todo-widget-file-watcher.md]
e60817a. COMPLETED: In the TODO widget, the discard button should
   require confirmation: for add, when there is non-whitespace content;
   for edit, when the user has changed the content such that there
   would be a change. In the case of add, the confirmation should say
   "Discard this new item?" and in the case of edit, it should say
   "Discard changes?". `_ItemDialog` now takes an explicit `editing`
   flag and snapshots its `initial_text`; the discard-confirmation
   predicate is add-mode ("any non-whitespace content", unchanged from
   TODO a629bea) vs. edit-mode (text actually differs from the
   snapshot — previously every edit-discard confirmed unconditionally,
   even a no-op one, since an edit dialog is never prefilled empty),
   with the message matching each mode. Verified entirely headlessly:
   all four add/edit x confirm-needed/not-needed combinations, a
   revert-to-exact-original-text case (no confirmation), declining
   leaves the dialog open with text intact, and a full regression of
   the existing add/edit/reprioritize/watcher test suites.
   [planned: todo-widget-discard-confirmation-wording.md]
82d66c0. COMPLETED: Regression: the hovering ui in the upper-left and
   lower-right are not supposed to be attached to the desk, they are
   supposed to be attached to the corners of the window, no matter the
   zoom level, scroll/pan, or window-resize. Reproduced directly: panning
   (`centerOn`) and zoom operations that re-center the view
   (`zoom_to_fit`/`reset_zoom`) drifted the Desk picker/zoom control away
   from their pinned corners, sometimes off-screen entirely. Root cause,
   confirmed directly and more precise than TODO 4adfcad/TODO 1f9bd34's
   original "some internal layout pass" theory: `QAbstractScrollArea`
   (which `QGraphicsView` is) implements fast scrolling via
   `QWidget.scroll(dx, dy)` on the viewport, which — per `QWidget.scroll`'s
   own documented behavior — also moves any child widget fully inside the
   scrolled area by that same delta; the Desk picker/zoom control are
   exactly that (plain `QWidget` children of the viewport, not scene
   items), so any operation that shifts scroll position silently drags
   them along with it. Very likely the same actual mechanism behind the
   earlier resize-time drift too (the first resize already fires
   `scrollContentsBy` with nonzero deltas, given the huge/infinite scene
   rect). Fixed with a new `WorkspaceView.scrollContentsBy` override that
   reasserts both HUD widgets' positions after every scroll (guarded
   against firing before they exist, since `QGraphicsView.__init__` can
   invoke it during its own setup); the existing resize-time fix is left
   untouched, since it's independently needed for the zoom control's
   viewport-size-dependent target position. Verified entirely headlessly:
   reproduced the bug directly against the unfixed code, confirmed the
   fix holds after panning, `zoom_to_fit`, `reset_zoom`, wheel-style zoom,
   and a regression check of the existing resize-time fix and widget
   drag/positioning.
   [planned: fix-hover-ui-scroll-zoom-drift.md]
a02b001. COMPLETED: feature: temporary ui. This is a means by which
   agents can create temporary ui on Desk. In a directory ".desk_temp"
   (a subdirectory of the directory associated with the current Desk),
   files with uuid names will be watched for creation/edit and will
   result in new widgets showing in the Desk, corresponding to the
   file. The contents of the file should be the TempUI DSL, which has
   the syntax of per-line "keyword param1 param2...". To start, the
   only keywords are "Question," "Option," and "Answer" and the
   resulting widget should be a new type of widget, a "Question Widget"
   which displays the question and allows the selection of one of the
   options as an answer; when the user chooses an answer, it is
   appended to the corresponding file as an "answer" line. On boot or
   when a new associated directory is selected, do the following: (1)
   ensure that the temporary ui subdirectory exists (ask for permission
   from the user via a popup before creating it), (2) ensure that
   desk-temporary-ui.md (described later) exists, (3) ensure that the
   temporary ui subdirectory is in any .gitignore file (ask for
   permission before adding). In addition to the normal development
   process, also describe temporary ui, including the DSL in a file
   called desk-temporary-ui.md, stored in the temporary ui subdirectory
   (but ignored by temporary ui detection). In Desk, when a temporary
   ui file is added by an external process, show a persistant
   notification in the upper-right which, when clicked, actually
   instantiates the new widget, centered in the current view. When a
   temporary ui file is edited not by Desk, a notification should be
   shown (replacing any other notifications for the particular file)
   and when clicked the widget should either be centered in the view if
   it exists, or created as per the file added case.

   Shipped as: `desk.temp_ui` (DSL parsing, UUID-filename validity
   check, `.gitignore` handling, doc template), `desk.shell
   .temp_ui_manager.TempUiManager` (a dedicated directory watcher,
   distinct from the widget-hot-reload `WidgetWatcher`, with self-write
   suppression and directory provisioning), `desk.shell
   .temp_ui_notifications.TempUiNotificationStack` (a new top-right
   -corner HUD, stacked/replaced per file, sharing the same
   `scrollContentsBy`-pinning fix TODO 82d66c0 just added), and
   `widgets/question/` (the new Question Widget). A Question Widget's
   Desk `instance_id` is always set equal to its source file's uuid --
   this is how a restored/reloaded instance reconnects to the right
   file without any change to the fixed `build() -> QWidget` contract
   every widget kind relies on (`DeskWindow._load_desk_widgets` special
   -cases `widget_id == "question"` to rebind it). `desk.git_utils
   .find_git_root` extracted from `widgets/todo/widget.py` (now needed
   a second time). Verified entirely headlessly: DSL parsing/gitignore
   logic, the directory watcher's added/edited/self-write-suppression
   behavior (including a real bug found and fixed -- see LEARNINGS.md
   -- where a brand-new file was always misclassified as "edited"),
   the Question Widget's render/answer/placeholder behavior, the
   notification stack's positioning (including staying pinned through
   pan per TODO 82d66c0's fix), and a full-app `DeskWindow` regression:
   boot-time provisioning, a real notification click placing a bound
   Question Widget centered in the view, answering it, and -- the
   actual point of the `instance_id`-as-uuid design -- a simulated app
   restart (a fresh `DeskWindow` over the same saved Desk) correctly
   reconnecting to the file and showing the already-given answer.
   [planned: temporary-ui.md]
1a051d1. COMPLETED: Regression: the TODO widget no longer properly loads a
   TODO.md from the Desk-associated directory; it shows an error saying it
   can't find the TODO.md file.

   Root cause: `DeskWindow.__init__` (`src/desk/shell/window.py`)
   constructed saved widgets (`_load_desk_widgets`, which can build a
   `TodoWidget` that resolves its `TODO.md` path once, synchronously, at
   construction) before `_refresh_picker` ever ran -- the only place that
   populates `current_context`'s current-desk-directory. Previously
   masked by the TODO widget's own manual "Reload" button (both calls
   finished before the event loop started, so clicking Reload always saw
   the correct directory); TODO d25e557 removed that button in favor of
   automatic file-watching, which only fires on a later external change,
   never on initial load -- turning a cosmetic first-paint glitch into a
   permanent regression. Fixed by moving `_refresh_picker()` to run
   immediately after `self.current_desk` is assigned, before
   `_load_desk_widgets`. Verified by reproducing the exact bug directly
   against the unfixed ordering (a real `DeskWindow`, catalog trimmed to
   the `todo` widget, pointed at a directory with a real `TODO.md`, showed
   the "No TODO.md found" error) and confirming the fix resolves it
   immediately at construction, with no other `DeskWindow` behavior
   depending on the old order.
   [planned: fix-todo-widget-load-regression.md]
1217380. COMPLETED: The shell (Console widget) text caret outside of the
   app usually shows as a non-blinking box character; the shell text caret
   inside of the app does not show up at all.

   Root cause: `TerminalWidget.setReadOnly(True)` strips
   `Qt.TextInteractionFlag.TextEditable` from its interaction flags, a
   flag Qt's internal cursor-paint logic requires before it will ever
   draw the native blinking caret -- regardless of focus, cursor width,
   or cursor position all otherwise being correct (all individually
   confirmed fine in isolation). Fixed by rendering the cursor explicitly
   as a reverse-video block over its character cell in `_redraw()`
   (`_char_format`'s new `invert` parameter), the same mechanism already
   used for pyte's own SGR reverse-video, rather than depending on Qt's
   native (permanently invisible, for a read-only widget) cursor; the old
   `setTextCursor`/`setCursorWidth` calls, which never actually rendered
   anything, are removed. Verified headlessly against a real PTY: printed
   text and confirmed the tracked cursor cell's `QTextCharFormat` is
   inverted relative to its neighbor, confirmed the inversion respects a
   real `ESC[?25l`/`ESC[?25h` (DECTCEM) pair sent through the PTY, and
   confirmed the rejected alternative (re-adding `TextEditable` to the
   flags) would have silently flipped `isReadOnly()` back to `False`.
   [planned: console-widget-cursor-visibility.md]
8beab6e. COMPLETED: The upper-left Desk picker ux is finicky and strange; it
   shows the name of the current desk and the associated folder always,
   which is good, but on hover it pops up buttons to the side. Instead: make
   the name and associated folder more visually distinct from one-another on
   hover; when clicking on the name, bring up a more stable picker rather
   than the current weird drop-down thing; when clicking on the associated
   directory, bring up the directory picker directly (i.e. get rid of the
   "Directory…" button).

   Replaced the single always-visible label + hover-revealed
   `QComboBox`/`QPushButton` with two independently-styled,
   independently-hoverable clickable label chips (name: bold/brighter;
   directory: dimmer) via a new `_ClickableLabel`. Clicking the name opens
   `_DeskListPopup`, a stable `QListWidget`-based popup (`WidgetSpawnMenu`'s
   established `Qt.WindowType.Popup` pattern) listing MRU desks plus a
   trailing browse entry; clicking the directory chip emits
   `directory_change_requested` directly. `DeskPicker`'s external signal
   API (`desk_chosen`/`browse_requested`/`directory_change_requested`) is
   unchanged, so `DeskWindow` needed no changes. `design-docs/widget-ux.md`
   updated to match. Verified headlessly: label text/MRU state, independent
   per-chip hover styling, direct directory-click emission, popup contents/
   pre-selection/activation for both an MRU entry and the browse entry, and
   a full-app `DeskWindow` regression boot.
   [planned: desk-picker-split-name-directory-click.md]
c8f6fb3. COMPLETED: Crash: switching to a different Desk (via the Desk
   picker's name popup) crashes the whole app with `RuntimeError: wrapped
   C/C++ object of type _DeskListPopup has been deleted`, raised from
   `desk_picker.py`'s `_activate_item`.

   Root cause: `_activate_item` emitted `desk_chosen`/`browse_requested`
   (which can synchronously reach `DeskWindow._provision_temp_ui`'s real
   confirmation dialog via `switch_desk`) *before* calling `self.close()`.
   `_DeskListPopup` is a `Qt.WindowType.Popup` + `WA_DeleteOnClose` window;
   a modal dialog appearing steals active-window status, which
   auto-closes the still-open popup, and the modal's own nested event
   loop processes the resulting `deleteLater()` while `_activate_item` is
   still executing on that same (now-deleted) object -- so the later
   `self.close()` call crashed. Confirmed directly with a minimal,
   business-logic-free repro (any real modal `QDialog.exec()` shown from
   a downstream slot reproduces it). Fixed by closing the popup *before*
   emitting, and never touching `self` afterward. Verified headlessly:
   reproduced the crash against the unfixed ordering, confirmed the fix
   resolves it and preserves normal-path (no modal) behavior, and ran a
   full-app `DeskWindow` regression that exercises the real
   `switch_desk` -> `_provision_temp_ui` confirmation path with no crash.
   Noted the identical latent hazard in `WidgetSpawnMenu._activate_item`
   in `PARKINGLOT.md` (out of scope here).
   [planned: fix-desk-list-popup-deleted-mid-callback.md]
bb65aab. COMPLETED: Bug: temporary ui (TODO a02b001) notification did not
   show up. Reproduced by having an agent write a new temp UI file
   directly to `.desk_temp/` (a bare-UUID filename, DSL content with
   `Question`/`Option` lines, no `Answer` line yet — i.e. exactly the
   "file added" case `desk-temporary-ui.md`/TODO a02b001 describe) while
   Desk was presumably running against this project as the current
   Desk's associated directory. No persistent notification appeared in
   the upper-right corner. Needs investigation: whether `TempUiManager`'s
   watcher is actually running/attached to the right directory, whether
   detection or notification-stack display is silently failing, or
   whether the precondition (Desk running with this directory as the
   current Desk) didn't actually hold when this was observed.

   Investigated directly against this project's own real, already
   -provisioned `.desk_temp/` directory: ruled out the watcher not
   running and the notification stack silently failing (a plain new-file
   write is detected correctly). Ruled out TODO c8f6fb3's crash as the
   cause (timing: the crash happened ~3 minutes after the temp-UI file
   appeared, per `test.desk`'s own mtime — plenty of time for a working
   notification to have shown). Root cause: writing the file via a
   scratch-name-then-rename "atomic write" (common in editors/safe-write
   tools) reports as a `watchdog` `FileMovedEvent`, not
   Created/Modified, which `_DirectoryHandler.on_any_event`
   (`src/desk/shell/temp_ui_manager.py`) didn't handle at all -- and even
   a widened type check would still miss it, since a move's meaningful
   path is `dest_path` (where the file landed), not `src_path` (its
   scratch name, which never matches `is_temp_ui_filename`). Fixed by
   handling `FileMovedEvent` explicitly and reading `dest_path` for it.
   Verified headlessly against this project's real `.desk_temp/`
   directory: reproduced zero `file_added` events against the unfixed
   handler for an atomic write, confirmed the fix detects it correctly,
   and confirmed both plain-write and atomic-write edits of an
   already-known file still classify as `edited`, not `added`. Noted the
   identical gap in the TODO widget's own single-file watcher in
   `PARKINGLOT.md` (a different file, out of scope here).
   [planned: fix-temp-ui-watcher-missed-atomic-write.md]
54b0a9f. COMPLETED: Bug: the TODO widget's single-file watcher
   (`_SingleFileHandler` in `widgets/todo/widget.py`) has the same
   atomic-write blind spot TODO bb65aab fixed in `TempUiManager`'s directory
   watcher. It compares `event.src_path` against the exact watched
   `TODO.md` path; a `watchdog` rename/move reports as a `FileMovedEvent`
   whose meaningful path is `dest_path` (where the file landed), not
   `src_path` (the scratch name) -- so an editor/tool that saves via
   write-scratch-then-rename-over-`TODO.md` (a routine, safe-write
   pattern) is never detected as an external change. Apply the same
   `FileMovedEvent`/`dest_path`-aware fix here.

   Fixed by reading `event.dest_path` for a `FileMovedEvent` and
   `event.src_path` otherwise, mirroring TODO bb65aab's fix exactly.
   Verified headlessly: confirmed the exact mechanism in isolation (a
   real `FileMovedEvent` fails the old comparison, passes the new one),
   confirmed a real `TodoWidget` watching a real `TODO.md` correctly
   reloads after a scratch-name-then-`os.rename()` edit, and confirmed a
   plain direct write is still detected as before.
   [planned: fix-todo-widget-watcher-missed-atomic-write.md]
14d14e7. COMPLETED: The code editor "open" button should default to the
   directory associated with the Desk.

   `EditorWidget._last_dir` (the shared Open/Save-As default directory)
   now seeds from `desk.shell.current_context.get_current_desk_directory()`
   when known, falling back to `Path.home()` otherwise -- the same
   `current_context` mechanism the TODO widget already uses, resolved
   once at construction. `plans/code-editor-widget.md`'s original
   deferral no longer applies now that this mechanism exists. Verified
   headlessly: defaults to the current Desk directory when set, falls
   back to home when not, and still tracks an actually-opened file's own
   directory afterward as before. Found (but did not fix, out of scope
   here) a related latent bug in `DeskWindow.switch_desk` -- logged in
   `PARKINGLOT.md`.
   [planned: editor-open-default-desk-directory.md]
11aeb43. COMPLETED: Add a new type of tempui, called `LightningRound`. the first line in the tempui file should be `LightningRound\t[name]\t[prompt]`,  and it should then re-use `Option` but with the argument being a single character which will be used as the keyboard button to correlate with that option; these same options apply to all questions that this widget will ask. After at least two Options, following should be `LRItem\t[description]\t[answer or the string "unanswered"]; that is a "lightning round item." the UI should show one LRItem at a time (skipping those that already have one of the options as an answer), with buttons below it corresponding to the Options, labelled to make it clear that you can also use the keyboard (e.g. `Press [character]`). It should record the user's answers, replacing "unanswered" with the chosen character. Please be sure to update all of the tempui docs, especially those that are directions to claude.
   [planned: lightning-round-tempui.md]

   Added the LightningRound DSL (LightningRound/Option/LRItem keywords, tab-separated for the multi-field lines) via a dedicated parse_lightning_round/LightningRoundDocument (a LightningRound file's shape -- one prompt, shared options, a list of items -- differs structurally from Question's single question/answer, so it isn't shoehorned into parse_temp_ui) and record_lightning_round_answer (rewrites exactly the targeted LRItem line's answer field in place). New widgets/lightning_round/ widget kind, same build()/set_source_file contract as QuestionWidget: shows the first unanswered item and one "Press <character>" button per option, answerable by click or by pressing the matching key (case-insensitively), advancing to the next unanswered item until all are answered. window.py's previously Question-only wiring (_load_desk_widgets, _notify_temp_ui, _activate_temp_ui) now routes by each file's own detected kind (detect_temp_ui_kind) instead of a hardcoded widget id -- _bind_question_widget renamed to the already-generic _bind_temp_ui_widget. DOC_TEMPLATE gains a LightningRound section for agents/Claude to read; this project's own already-provisioned .desk_temp/desk-temporary-ui.md refreshed by hand to match (provisioning only writes it once, not on every boot).

   Verified headlessly: DSL round-trip parsing and kind detection, record_lightning_round_answer's precise in-place rewrite (every other line untouched), the widget's full click/keyboard/advance/completed-state behavior against a real file, _temp_ui_widget_id_for's routing for both file shapes, and a full-app DeskWindow regression confirming both a saved lightning_round widget and the existing question widget correctly reconnect to their source files.
6907120. COMPLETED: create a new widget, "claude" which runs the claude cli in a shell, so similar to the console widget. it should pass an argument to the invocation of claude that sets the first message/prompt to claude to be something like "You are running inside of Desk. Please read this document to understand the implications of that: [path to the document in .desk_temp which explains things like tempui]"

   Extracted the Console widget's generic PTY/pyte TerminalWidget out of widgets/console/widget.py into a shared desk.terminal_widget (widget directories can't import each other directly), parameterized by an optional command list (defaulting to bash). console/widget.py is now a thin shim over it. New widgets/claude/ widget spawns the same shell, then types the claude invocation into it (via a new TerminalWidget.type_into_shell) rather than exec-ing claude directly, so the user's normal shell profile/PATH/aliases load first and the shell stays usable if claude exits. The initial prompt points at the current Desk's .desk_temp/desk-temporary-ui.md via current_context, falling back to a relative-path description if no current Desk directory is known yet. design-docs/architecture.md updated with a new Claude Widget component entry.

   Verified headlessly against real PTYs: console widget regression (still spawns a working bash shell via the shared module), TerminalWidget(command=...) actually running the requested command, type_into_shell delivering text exactly like a keystroke would, and the claude widget end-to-end with a fake claude script on PATH -- both a precise capture of the exact text typed into the shell (confirming the real doc path, independent of terminal line-wrap) and a full end-to-end confirmation that the fake claude binary actually received and echoed the prompt back through the real PTY.
   [planned: claude-widget.md]
ef77819. COMPLETED: create a new python widget, "git status", which displays git status. This should be implemented in a way to keep it relatively fresh without adding too much of a compute burden.

   Polls (QTimer, 3s) rather than watching the working tree with watchdog -- almost any change anywhere in a repo can affect git status, making a precise watcher both complex and the compute burden the TODO itself warns against. git status/branch subprocess calls run on a background thread (never the GUI thread, same reasoning as the TODO widget's own git-commit thread), skip entirely while the widget isn't visible, and only trigger a redraw when the output actually changed since the last poll. New widgets/git_status/ widget kind; design-docs/architecture.md updated with a new component entry.

   A real bug was found and fixed during verification: the initial poll (meant to show real status immediately rather than leaving the widget blank until the first timer tick) reused the same isVisible() gate as later polls, but a widget is never visible at the moment its own __init__ finishes -- it silently never ran. Fixed by giving _poll an initial=True bypass for the one call made from __init__. Verified headlessly against real git repos (including this project's own): no-repo/clean/dirty states, the redundant-redraw skip, the isVisible() gate and its initial-poll fix (confirmed directly by never calling .show() at all), and a full-app DeskWindow regression placing the widget against this project's real repository.
   [planned: git-status-widget.md]
6cf4543. COMPLETED: lightning round ui doesn't seem to be accepting key-presses. should we maybe add a "click here to use keyboard" button or something?

   Root cause confirmed headlessly: clicking an option button, or empty
   stretch space within the widget, already correctly grabs keyboard
   focus -- but clicking the prompt/item text (the most natural place to
   click, since that's the actual question being read) lands on a
   `QLabel` child, and Qt's click-to-focus handling only ever considers
   the exact child widget under the cursor. Since `QLabel` defaults to
   `Qt.FocusPolicy.NoFocus` (ordinary Qt behavior, not specific to being
   embedded via `QGraphicsProxyWidget`), the click never reaches the
   parent `LightningRoundWidget`'s own `Qt.FocusPolicy.StrongFocus`, so
   keys pressed afterward go nowhere. Fixed with an event filter on
   `_prompt_label`/`_item_label` that grabs focus for the widget on
   `QEvent.Type.MouseButtonPress`, deferred via `QTimer.singleShot(0,
   ...)` -- confirmed directly that a synchronous `setFocus()` call
   inside the filter is silently clobbered immediately afterward by
   `QGraphicsProxyWidget`'s own under-cursor focus resolution for that
   same press, the same "something else reasserts state right after
   this" shape already seen in `canvas.py`'s HUD-positioning fixes.
   Addressed the root cause directly rather than adding a "click here to
   use keyboard" affordance, since that would only work around the real
   gap. Verified entirely headlessly against a real `WorkspaceView`
   /`WidgetFrame`-wrapped instance (an initial reproduction attempt
   turned out to mistakenly click the titlebar chrome instead of the
   label; corrected by computing the label's true on-screen position via
   `label.mapTo(frame, ...)`), including regression checks that button
   -click, empty-space-click, and titlebar-drag behavior are all
   unaffected.
   [planned: lightning-round-keyboard-focus.md]
c8e3b28. COMPLETED: need to give focus to text boxes when we pop them up,
   e.g. in add/edit TODO item in TODO widget

   Root cause: `_ItemDialog(self)` (`self` being the embedded
   `TodoWidget`) resolves `self.window()` to that widget's `WidgetFrame`,
   which is never itself shown as an independent OS-level window (only
   embedded into the real `DeskWindow` via `QGraphicsProxyWidget`).
   Parenting a genuinely separate top-level `Qt.WindowType.Tool` window
   to it made every per-widget signal (`hasFocus()`, `isActiveWindow()`)
   report success, but the real, single, global
   `QApplication.focusWidget()` never actually moved to it -- confirmed
   directly against a real running `DeskWindow`, not just an isolated
   dialog (which misleadingly looked correct on its own). Fixed by
   parenting `_ItemDialog` to `QApplication.activeWindow()` (the real
   `DeskWindow`) instead of the embedded widget, via a new
   `TodoWidget._new_item_dialog` helper used by both
   `_show_add_dialog`/`_show_edit_dialog`; since this breaks Qt's
   automatic parent-child object lifetime, the dialog's lifetime is now
   tied to `TodoWidget` explicitly (`self.destroyed.connect(dialog
   .close)`) instead. Also fixed the premature, always-a-no-op
   `self._field.setFocus()` call in `_ItemDialog.__init__` (called
   before the widget was ever shown) by moving it into a deferred
   `showEvent` handler that also calls `raise_()`/`activateWindow()`.
   Verified headlessly against a real, shown `DeskWindow` with a real
   embedded `TodoWidget`: reproduced the bug directly (clicking "Add
   Item" left `QApplication.focusWidget()` on the `WorkspaceView`, not
   the popped-up dialog), confirmed the fix moves real focus to the
   dialog's field for both add and edit, confirmed an open dialog is
   still torn down when `TodoWidget` is destroyed (e.g. by hot reload),
   and regression-checked `selectAll()`/Ctrl+Enter-submit/discard
   -confirmation wording are unaffected. See `LEARNINGS.md` for the new
   entry on this `QGraphicsProxyWidget`-embedded-window-as-parent
   gotcha, and `PARKINGLOT.md` for an unrelated, out-of-scope background
   -thread warning noticed along the way.
   [planned: todo-item-dialog-focus.md]
61141b3. COMPLETED: add the last committed/reloaded time to the
   lower-right of the todo widget, on the same line as the filename

   Added a new right-aligned `_timestamp_label` alongside the existing
   `_status_label` (which keeps a stretch factor, pushing the timestamp
   to the lower-right), in a new `QHBoxLayout` replacing the old single
   -label bottom row. A new `_touch_timestamp(verb)` helper sets it to
   `f"{verb} HH:MM:SS"`, called with "Reloaded" from both `reload()`
   (when a `TODO.md` is actually found) and `_on_external_change()`
   (an external-edit-triggered reload), and with "Committed"/"Saved"
   from `_report_commit_status()`'s two branches (a real commit vs. the
   saved-but-not-a-git-repo case). Starts blank until the first reload/
   commit. Verified headlessly: each of the above call sites sets the
   expected text, the no-TODO.md-found case leaves it blank,
   `_status_label`'s own text is unaffected, and a full-app `DeskWindow`
   regression with a real placed `todo` widget shows both labels
   correctly side by side.
   [planned: todo-widget-last-updated-timestamp.md]
a76e723. COMPLETED: Implement a markdown viewer widget (markdown_ex)
   which can show embedded SVGs as well as mermaid diagrams, with
   folding support and a TOC treeview on the left-hand-side.
   [planned: markdown-ex-widget.md]
5a2f5b9. COMPLETED: Bug: the TODO widget's file parsing doesn't seem to
   work for e.g. world-timelines/TODO.md -- needs investigation into why
   that particular file fails to parse/display correctly (format
   assumptions parse_todo_file makes that don't hold for it, item-id
   regex mismatch, etc.).

   Root cause, confirmed directly against the real file: every item in
   world-timelines/TODO.md uses a GitHub-style checklist marker
   (`- [x] N. ...`) before the id, which `ITEM_START_RE` (anchored at
   line start, expecting the id immediately) never matched at all --
   `parse_todo_file` found zero item starts, so the whole file became
   `preamble` and the widget showed an empty list, not a crash. Fixed
   by widening `ITEM_START_RE` (`src/desk/todo_file.py`) to optionally
   match a leading `- [ ]`/`- [x]` marker before the id, and using its
   checked state as a status fallback in `parse_todo_file` (only when
   this project's own COMPLETED:/SUPERSEDED/PENDING description-prefix
   convention doesn't already say otherwise, so it never overrides an
   explicit status). One line in the file (`- PENDING 21. ...`, no
   checkbox at all) is a one-off, different convention, deliberately
   left out of scope -- it's silently absorbed into the preceding
   item's text rather than crashing. Verified headlessly: this
   project's own `TODO.md` still parses identically; the real
   world-timelines `TODO.md` now parses all 62 checklist items as
   `completed`; a synthetic unchecked `- [ ]` item parses as
   `incomplete`; an explicit `PENDING:` description prefix still wins
   over a checked checkbox; and a full-app `DeskWindow` regression
   placing a real `todo` widget against a copy of the actual file shows
   all 62 items instead of an empty list.
   [planned: todo-parser-checkbox-format.md]
cbeda83. COMPLETED: Make the Desk picker a little more substantial,
   including a way to make a new desk and a way to rename the current
   desk.

   Added three muted action rows to the name-chip popup
   (`_DeskListPopup`): "＋ New Desk…", "✎ Rename current Desk…", and the
   existing browse entry (relabelled "… Open another Desk…"),
   distinguished from MRU desk rows by a new `ACTION_ROLE`. `DeskPicker`
   re-emits two new signals (`new_desk_requested`/`rename_requested`)
   through its existing dumb-component pattern; `_activate_item` keeps
   the TODO c8f6fb3 close-before-emit ordering. `DeskWindow` gains
   `new_desk(name)` (creates a `.desk` in the current directory and
   switches to it, persisting immediately; a fresh desk gets the
   documented demo layout, not a special empty case) and
   `rename_current_desk(new_name)` (renames the `.desk` file in place --
   a Desk's name is its file stem -- preserving widgets/view, updating
   the MRU so the stale name drops out, leaving the directory/.desk_temp
   untouched); both refuse an existing name via a new injectable `_warn`
   and get their name via a new injectable `_prompt_fn` mirroring
   `_confirm_fn` (so both are substitutable in headless tests). Verified
   headlessly: popup row layout + each row emitting exactly its matching
   signal; new_desk create/persist/switch/MRU/collision behavior;
   rename file-move/state-preservation/MRU-update/collision/no-op/
   directory-untouched behavior. `design-docs/widget-ux.md` updated.
   [planned: desk-picker-new-and-rename.md]
1d7331b. COMPLETED: Update the claude widget to monitor the name/id of the
   claude session and store that as part of the widget state so that it can
   be resumed on reload; if there is no better way to do that, write in
   instructions in the initial Desk prompt that claude should write a temp
   file in a known place in the .desk_temp directory that Desk can monitor;
   if resuming a session on reload, don't pass the initial Desk prompt.

   Found a better way than monitoring/scraping the session id: the claude
   CLI's `--session-id <uuid>` (assign a session up front) and `--resume
   <uuid>` flags let Desk *assign* the session, and the widget's persisted
   Desk `instance_id` can double as that UUID -- the same instance_id-as
   -durable-identity pattern the Temporary UI widgets use -- so no
   WidgetState schema change was needed, and the "have claude write a temp
   file" fallback is unnecessary. New `ClaudeWidget(TerminalWidget)` with a
   `start_session(session_id, resume)` method (fresh: `claude --session-id
   <uuid> "<prompt>"`; resume: `claude --resume <uuid>`, no prompt);
   `build()` now just spawns the shell, with the launch issued post-build
   by a new `DeskWindow._bind_claude_widget`. `_place_widget` gained a
   `restore` flag: a fresh claude placement gets a full-uuid4 instance_id
   (needed for a valid `--session-id`) and launches fresh; a widget
   restored via `_load_desk_widgets` (restore=True) resumes with its saved
   instance_id. Verified headlessly (fresh/resume/build command behavior;
   and a full-app fresh-launch -> save -> new-DeskWindow-reload -> resume
   flow preserving the session id, console widget unaffected).
   `design-docs/architecture.md` updated; a general "post-build binding is
   lost on hot reload" limitation (shared with temp-UI widgets) logged in
   `PARKINGLOT.md`.
   [planned: claude-widget-session-resume.md]
6bf83a9. COMPLETED: add a markdown renderer widget which puts a file
   watcher on a markdown file and renders it.

   New `widgets/markdown/` widget: renders a chosen Markdown file via
   Qt's native `QTextBrowser.setMarkdown()` (no Markdown-library
   dependency, per CLAUDE.md's prefer-bespoke guidance) and auto-reloads
   it on external change. The file is picked via an editor-style "Open"
   button seeded from the current Desk directory (current_context); not
   persisted across reload (matches the editor widget -- the widget
   contract has no per-instance state payload, logged as a follow-up in
   PARKINGLOT.md). File watching uses a new reusable
   `desk.file_watch.SingleFileWatcher`, extracted from the TODO widget's
   own watcher so its two watchdog gotchas (FSEvents symlink-resolved
   paths; atomic-write FileMovedEvent/dest_path -- see LEARNINGS.md) live
   in one place; the TODO widget was left on its own copy for now (its
   self-write suppression is entangled), with consolidation noted in
   PARKINGLOT.md. Verified headlessly: the watcher (plain/atomic write,
   symlinked tempdir, unrelated-file ignore, stop/restart); the widget
   (placeholder, render, external-edit auto-reload, deleted-file note,
   recreate-reloads); and a full-app DeskWindow placement. design-docs/
   architecture.md updated with a Markdown Widget entry.
   [planned: markdown-renderer-widget.md]
c758ddf. COMPLETED: a "sheet" widget which implements a basic spreadsheet
   (resizable rows and columns, wordwrap or clip for overflow, all
   entries are left-aligned and vertically centered) which serializes/
   saves as TSV files.

   New `widgets/sheet/` widget built on `QTableWidget`, which covers
   every requirement natively (no spreadsheet dependency): interactively
   resizable rows/columns (both headers Interactive), word-wrapped/
   clipped cells (`setWordWrap(True)`), all entries left-aligned +
   vertically centered via each item's `textAlignment` plus a
   `setItemPrototype` so cells the user creates by typing inherit the
   alignment. TSV serialization (tab-joined columns, newline-joined
   rows; ragged rows padded on load) via an editor-style Open/Save/Save
   As toolbar seeded from the Desk directory, plus Add/Delete Row &
   Column controls and a `•` dirty marker. Open file not persisted
   across reload (same as editor/markdown widgets -- parked
   widget-state-payload gap). Verified headlessly (config, alignment
   incl. prototype clone, TSV save round-trip, ragged-load padding, add/
   delete row+column, dirty marker) and via a full-app DeskWindow
   placement + TSV round-trip. design-docs/architecture.md updated.
   [planned: sheet-widget.md]
3be392a. COMPLETED: bug: special interactions don't work (like using an
   arrow to change the selection on a list of questions or shift-tab to
   cycle mode) in Claude or console widgets

   Root cause: `TerminalWidget.keyPressEvent` only sent the 4 KEY_BYTES
   entries, Ctrl+C/D, and anything with a non-empty `event.text()` --
   arrows, Shift+Tab, Home/End, Page Up/Down, Delete, Insert, and Escape
   all have empty text and weren't mapped, so pressing them sent nothing
   at all. Added their ANSI sequences: cursor keys + Home/End are
   CSI (`ESC [`) normally but SS3 (`ESC O`) when the app has enabled
   application-cursor-keys mode (DECCKM, tracked by pyte in
   `screen.mode` as `1 << 5`) -- which claude's TUI uses, so honoring it
   is what makes its arrow navigation actually work; Shift+Tab
   (Key_Backtab) -> `ESC [ Z`; Escape/Delete/Insert/PageUp/PageDown ->
   their sequences; and generalized Ctrl+C/D to Ctrl+A..Z -> control
   bytes 0x01..0x1a. Refactored into a `_key_to_bytes` helper. Verified
   headlessly (spying on os.write to the PTY): normal-vs-DECCKM arrow
   encodings, Shift+Tab/Escape/Delete/PageUp/PageDown, Ctrl+letter, and
   regressions for plain text/Return/Tab/Backspace. Modified cursor keys,
   function keys, and the keypad are deliberately out of scope (see
   plan).
   [planned: terminal-special-keys.md]
c44e88f. COMPLETED: bug: scroll wheel doesn't work in browser widget

   Root cause: `WorkspaceView.wheelEvent` only forwards a wheel event to
   an embedded widget (rather than zooming the canvas) when
   `_scrollable_at` finds a `QAbstractScrollArea` ancestor under the
   cursor -- but `QWebEngineView` isn't one (its chain is `QWidget ->
   QWebEngineView -> BrowserWidget -> WidgetFrame`, confirmed by probe),
   so wheel events over the browser were eaten as canvas zoom. Fixed by
   adding `QWebEngineView` to that check (also fixes scrollable
   kind:"html"/ChromiumWidget pages). During verification this exposed a
   second, intermittent bug: QtWebEngine bounces an unconsumed wheel
   event (non-scrollable/at-limit page) back up the parent chain, which
   synchronously re-enters wheelEvent mid-forward and recurses until the
   stack overflows (`RecursionError`) -- fixed with a `_forwarding_wheel`
   re-entrancy guard that drops the bounced-back event. Verified
   headlessly against a real embedded browser widget (run repeatedly for
   stability): scrollable-over-web-view, wheel-doesn't-zoom-over-browser,
   the guard, empty-canvas-still-zooms, and a QAbstractScrollArea
   regression. New LEARNINGS.md entry on the wheel-bounce recursion.
   [planned: browser-widget-scroll.md]
846303c. COMPLETED: mouse-based selection doesn't work in claude cli
   running in console (it is usually the case that I can just select text
   to copy it)

   Root cause: `_redraw()` (run on every PTY read) wiped and rebuilt the
   whole document from pyte's screen buffer, destroying any active
   selection -- and a live TUI like claude repaints near-continuously, so
   a selection vanished as fast as it was made. Fixed by preserving the
   selection's anchor/position across the rebuild (the redraw always
   produces the same fixed PTY_ROWS x PTY_COLS grid, so a character
   offset denotes the same cell before/after). Also added the standard
   "Ctrl+C copies when there's a selection, sends SIGINT otherwise"
   convention so the selection can actually be copied -- which also
   sidesteps macOS's Cmd->Control mapping (whichever key Qt reports as
   Ctrl+C copies a live selection). Verified headlessly: selection
   survives a redraw; Ctrl+C-with-selection copies to the clipboard and
   sends nothing to the PTY; Ctrl+C-without-selection sends 0x03 and
   leaves the clipboard alone; a no-selection redraw introduces none.
   [planned: terminal-mouse-selection.md]
2dca4c8. COMPLETED: can claude be started in auto mode with CLI args? if
   yes, please change the claude widget to do that.

   Yes -- the claude CLI's `--permission-mode` has an "auto" choice.
   Added `--permission-mode auto` (via a PERMISSION_MODE_ARGS constant)
   to both the fresh (`claude --session-id <uuid> --permission-mode auto
   "<prompt>"`) and resume (`claude --resume <uuid> --permission-mode
   auto`) commands in `ClaudeWidget.start_session`. Verified headlessly
   (both commands include the flag; prompt only on fresh) and re-ran the
   full-app session/resume flow (TODO 1d7331b) with the updated commands.
   [planned: claude-widget-auto-mode.md]
5ddbef0. COMPLETED: quitting claude in the widget should close the widget,
   not exit to shell. does the claude CLI need to be run in the context
   of a shell? or if yes, is there a way to force the shell to exit if
   claude cli does?

   Answers: running via a shell is worth keeping (bash loads the user's
   profile so claude is found/runs as in a real terminal); and yes,
   `exec` forces the shell to exit with claude. Changed
   `ClaudeWidget.start_session` to type `exec claude …` -- bash loads its
   profile then replaces itself with claude in the same PTY, so quitting
   claude ends the PTY (and if claude isn't found, exec fails and the
   shell stays, preserving the original claude-not-found safety). Added a
   `TerminalWidget.process_exited` signal (emitted on PTY EOF in
   `_on_readable`); the claude widget's DeskWindow binding
   (`_bind_claude_widget`) connects it to `close_widget_by_instance_id`
   (deferred via QTimer.singleShot so removal doesn't run inside the
   notifier callback). The Console widget is unaffected (still just shows
   "[process exited]"). Verified headlessly: exec commands, the
   process_exited signal on child exit, and a full-app claude frame being
   removed on process exit. design-docs/architecture.md updated.
   [planned: claude-widget-close-on-exit.md]
b25412e. COMPLETED: if there is a plan listed in a todo item, detect that
   and provide a button on hover to open the plan document in Desk.

   `desk.todo_file` now parses the `[planned: <file>]` marker into a new
   `TodoItem.plan` field. The TODO widget shows a single floating "📄
   Plan" button that follows the mouse to the hovered row (via
   `itemEntered` + mouse tracking) -- deliberately *not* a per-row
   `setItemWidget`, which is fragile with the list's InternalMove
   drag-reorder -- shown only over rows whose item has a plan, hidden
   over plan-less rows / on list-leave / on scroll / on repopulate.
   Clicking it opens the plan (`<todo dir>/plans/<file>`) in the Markdown
   renderer widget (TODO 6bf83a9) via the existing `current_context`
   widget-opener hook; `MarkdownWidget` gained a public `set_file(path)`
   for that. Verified headlessly (plan parsing; button show/position/
   hide behavior; open-via-opener) and full-app (clicking places a
   markdown widget rendering the plan). Affordance style (floating hover
   button) and target widget (markdown renderer) were chosen
   autonomously -- the AskUserQuestion went unanswered (user away) -- and
   are easily swapped for the toolbar/context-menu or the editor later
   (see plan).
   [planned: todo-open-plan-button.md]
b927389. COMPLETED: Add a tree-view project directory/file explorer
   widget. Add a search/filter textbox at the top which temporarily
   hides everything but the tree-paths to the results and the results
   themselves, e.g.
   if searching for "foo" in a directory with a structure like (a (b
   ...) (c (foo) ...) (d ...)), then a -> c -> foo would show, not b
   or d. clearing the search should restore the view but the current
   file should remain selected. if a user double-clicks on a filename
   or hits enter while a filename is selected, open the file in a new
   instance of the Editor widget.
   [planned: file-explorer-widget.md]
c7d6e4d. COMPLETED: Implement an SVG-rendering widget.
   [planned: svg-viewer-widget.md]
42dd260. COMPLETED: Add new tempui capabilities to allow claude to
   open markdown files in the GUI.
   [planned: tempui-open-markdown.md]
b44e8ba. COMPLETED: Crash: segfault while interacting with the Desk picker.
   Console output before the crash: `python -m desk` started normally,
   discovered widgets `browser`, `claude`, `console`, `demo`, `editor`,
   `git_status`, `lightning_round`, `question`, `scratch`, `todo`, opened
   `~/desk/test.desk` -- then `Segmentation fault:
   11` with no Python traceback at all (a real OS-level crash, not a
   caught/logged exception). Needs investigation: no traceback means the fault
   is likely inside Qt/PyQt or a C extension, not plain Python -- reproduce
   the exact picker interaction that triggered it (name click vs. directory
   click vs. hover), and check for any known-fragile native code path (e.g.
   LEARNINGS.md's QNativeGestureEvent segfault note) that could plausibly be
   involved. Resolved by TODO 8c9436b: two later crash reports pinned
   the same crashing call chain (QAbstractItemView::mouseReleaseEvent,
   a QListWidget-based Desk-picker popup) with full crash logs, never
   independently reproduced from this item's own report but a close
   enough match to close as resolved by the same fix. See
   QUESTIONS.md's own entry for this item.
8c9436b. COMPLETED: Crash: segfault while loading an already-existing .desk file
   from the Desk picker. Full macOS crash report provided (kept out of
   the repo per explicit instruction, not pasted here or anywhere else
   in the project) -- same `QAbstractItemView::mouseReleaseEvent` ->
   `QListView::mouseReleaseEvent` -> `sipQListWidget
   ::mouseReleaseEvent` crashing-thread shape as the already-fixed New
   -Desk-flow segfault (TODO 4716585), strongly suggesting the same
   underlying `_DeskListPopup`/`WA_DeleteOnClose` class of bug, just
   reached via "load an existing Desk" instead of "create a new one."
   Likely resolves `b44e8ba` too (same crash shape, that report just
   never had a crash log to confirm against).
   [planned: fix-desk-picker-nested-dialog-crash.md]
02eda20. COMPLETED: Wire the Markdown and Editor widgets onto widget-local
   storage (TODO fb76057) so their currently-open file path actually
   persists and restores across a Desk reload -- currently every
   widget's `"state"` in a saved `.desk` file is an empty `{}`, even
   for widgets with an obvious per-instance thing to remember (already
   tracked in `PARKINGLOT.md`, never wired up for any real widget).
   Tolerate a since-moved/deleted file gracefully at restore time, not
   as a crash or silent misbehavior. Also wired up the Markdown (Old,
   Basic) widget (named alongside Markdown/Editor in PARKINGLOT.md's
   original tracked gap, though not in this item's own title) via a
   new shared `desk.persisted_path.resolve_persisted_path` helper.
   [planned: widget-local-storage-file-paths.md]
ff6514a. COMPLETED: Small borders around widgets by default, to visually
   distinguish one widget from another and from the canvas.
   [planned: widget-borders.md]
8d05920. COMPLETED: Lock widgets in place so that only the title and an unlock
   icon show in the top bar of the widget -- unable to be moved,
   resized, or moved in z order while locked. [planned: lock-widgets.md]
cbbb661. COMPLETED: Editor widget needs a different color text caret when
   focused -- black-on-black doesn't work well.
   [planned: editor-dark-mode-and-wrap.md]
f2aede6. COMPLETED: Feedback widget: able to take internal screenshots of the app
   and make a DESK-feedback-[timestamp].md with the internal
   screenshots attached, and also a temp mode (with full-screen
   overlay) launched by a button which allows UI elements to be
   clicked and an identifying UI path will be pasted into the feedback
   either at the current caret position or at the end.
   [planned: feedback-widget.md]
397770c. COMPLETED: Introduce the idea of focus in the app: individual controls
   in a widget can have focus, and if so the widget itself is also
   focused. The titlebar of a widget should change slightly when the
   widget is focused. [planned: widget-focus-concept.md]
a1c701d. COMPLETED: Clicking then releasing the title bar of a widget should
   activate/focus the current caret inside of it.
   [planned: widget-focus-concept.md]
17a2720. COMPLETED: The white background on the editor line numbers is good for
   separating but bad for dark mode. Instead, draw a vertical line
   between the numbers area and the editor box, and draw the numbers
   in a slightly different color than the default text in the box.
   [planned: editor-dark-mode-and-wrap.md]
1d6777f. COMPLETED: Wrap too-long lines in the editor, and keep the line number
   aligned with the top line. [planned: editor-dark-mode-and-wrap.md]
f447303. COMPLETED: When opening new instances of the Claude or Console widgets,
   the default working directory should be the active project (current
   Desk) directory, not wherever the Desk process itself is running
   from. [planned: claude-console-default-cwd.md]
4716585. COMPLETED: Crash: creating a new Desk segfaulted right as the
   ".desk_temp" creation confirmation dialog was answered ("Yes"), with
   the new Desk's seeded Markdown-with-README widget (TODO cb2790d)
   seemingly appearing "at the same time." A full macOS crash report
   was provided for this one (kept out of the repo per explicit
   instruction, not pasted here or anywhere else in the project) --
   `EXC_BAD_ACCESS`/`SIGSEGV` on the main thread inside
   `QAbstractItemView::mouseReleaseEvent` ->
   `QListView::mouseReleaseEvent` -> `sipQListWidget
   ::mouseReleaseEvent`, reached via the normal Cocoa mouse-event
   -delivery path -- the faulting address looks like reused/garbage
   memory, the shape of a use-after-free, not a null-deref. Likely
   involves the same `_DeskListPopup` (a `QListWidget`-based,
   `WA_DeleteOnClose` popup) class of bug as `b44e8ba` above -- that
   report also names the Desk picker specifically, and never had a
   crash log to confirm against until now; fixing this may resolve
   that one too, though it's recorded separately since `b44e8ba`'s own
   trigger (just "interacting with the picker") wasn't confirmed to be
   New-Desk-creation specifically.

   Do the following:
   1. Refactor the "New Desk" flow so all of its questions are one
      single dialog (checkboxes/a path-picker-launcher/textboxes)
      instead of popping up one after another: (a) name (textbox); (b)
      path (a picker-launcher button showing the currently-selected
      default path); (c) create `.desk_temp` for tempui (checkbox);
      (d) create or update `.gitignore` with Desk-specific patterns
      (checkbox). Update the `.gitignore` process to be able to append
      to it if it can't already, and make sure that in both the create
      and update cases there's an empty line and then a comment saying
      the entries are Desk-specific.
   2. When opening a new Desk for the first time, take all of the
      appropriate actions (directory/file provisioning) before opening
      it (placing any widgets), so it isn't trying to do conflicting
      things in parallel.
   3. When creating directories and files, check immediately before
      the create that the item doesn't already exist, and abort in a
      recoverable way (e.g. switching to the "already exists" path) if
      it's found to. Do this per-widget for now; also see the
      `PARKINGLOT.md` item on a more generalized mechanism for this.
   [planned: fix-new-desk-flow-crash.md]
03f623a. COMPLETED: Crash: quitting the app with Cmd+Q raises a `KeyError` partway
   through teardown, so it doesn't tear down cleanly. Traceback:

   ```
   Traceback (most recent call last):
     File "./desk-stable/widgets/todo/widget.py", line 434, in _flush_on_teardown
       watcher.stop()
       ~~~~~~~~~~~~^^
     File "./desk-stable/src/desk/file_watch.py", line 107, in stop
       self._handle.cancel()
       ~~~~~~~~~~~~~~~~~~~^^
     File "./desk-stable/src/desk_services/file_watcher/service.py", line 83, in cancel
       self._service._unsubscribe(self._key, self._callback)
       ~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^
     File "./desk-stable/src/desk_services/file_watcher/service.py", line 135, in _unsubscribe
       self._observer.unschedule(watch)
       ~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^
     File "./desk-stable/.venv/lib/python3.13/site-packages/watchdog/observers/api.py", line 363, in unschedule
       emitter = self._emitter_for_watch[watch]
                 ~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^
   KeyError: <ObservedWatch: path='./desk-stable', is_recursive=False>
   ```

   Likely root cause (from reading `desk/app.py` and
   `desk_services/file_watcher/service.py`, not yet confirmed by
   reproducing): `desk/app.py`'s `main()` connects
   `get_service().stop()` to `app.aboutToQuit` *last*, with a comment
   claiming this makes it run after "every individual consumer's own
   aboutToQuit-triggered watcher.stop()/handle.cancel()" -- but the
   TODO widget's `watcher.stop()` here isn't wired to `aboutToQuit` at
   all; it's in `_flush_on_teardown`, connected to the widget's own
   `destroyed` signal, which fires later, as part of Qt's actual
   widget-teardown cascade *after* `aboutToQuit` has already finished
   running. So `aboutToQuit`'s `get_service().stop()` -- which stops
   (and presumably clears) the whole shared `watchdog.observers
   .Observer` -- can easily run *before* a `destroyed`-triggered
   `SingleFileWatcher.stop()` (TODO widget, Questions widget, and any
   other widget with the same flush-on-teardown pattern) tries to
   unschedule its own watch from that now-already-stopped Observer,
   which watchdog itself no longer has bookkeeping for -- hence the
   `KeyError`. Likely fix direction: make
   `FileWatcherService._unsubscribe`/`WatchHandle.cancel()` tolerant of
   the shared Observer already being stopped (nothing meaningful left
   to unschedule at that point), rather than trying to guarantee a
   connection-order invariant across two fundamentally different Qt
   signals (`aboutToQuit` vs. a widget's own `destroyed`) that can't
   actually be ordered against each other that way.
   [planned: fix-teardown-keyerror.md]
7f51230. COMPLETED: Store crash logs in the current active project directory's
   `.desk_temp` folder instead of the project directory itself. On
   startup, if there are any crash logs present, open a new Crash Log
   widget for each one. The Crash Log widget reads a crash log and has
   a "Sanitize" button that strips off anything from the beginning of
   a path in the text that isn't relevant to finding the code --
   everything up to (but leaving) the `src` or `.venv` directory, for
   example. [planned: crash-log-widget.md]

   Investigated via code review: ruled out the QNativeGestureEvent note
   as a direct cause (Desk only reads native gesture events, never
   constructs them); reviewed desk_picker.py/canvas.py for other fragile
   patterns (nothing else found); confirmed this is a different, more
   severe symptom than TODO c8f6fb3's already-fixed `_DeskListPopup`
   crash (that one raised a catchable `RuntimeError` with a full
   traceback; this is a true segfault with none). Blocked on a specific
   reproduction -- see `QUESTIONS.md` and
   `plans/fix-desk-picker-segfault.md`.
   [planned: fix-desk-picker-segfault.md]
578cb6b. COMPLETED: Create a service for filewatchers in Desk, both from the app
   and from widgets. create a new `desk-services` directory under
   `./src/`, and create a sub-directory file-watcher, and put the
   implementation in there. For now, only implement the APIs that are
   needed by the app and widgets. The currently active watchers should
   be tracked and managed by this service. Watches should be
   de-duplicated as appropriate, such that a single watcher might make
   more than one notification; the goal of the de-duplication is to
   fix an issue that I've seen with file watchers in the current
   version of desk, which shows an error ("RuntimeError: Cannot add
   watch <ObservedWatch: path=... is_recursive=False> - it is already
   scheduled.").
   [planned: file-watcher-service.md]
cee6f74. COMPLETED: Refactor TempUiManager and the TODO widget's file-watching so
   they share the self-write-echo-suppression logic instead of each
   having its own copy, routing the TODO widget onto
   `SingleFileWatcher.record_own_write` instead of its own separate
   check. Additionally, add file-watching to the Editor widget so that
   if a file it has open is edited elsewhere (e.g. TODO.md edited by
   the TODO widget) while there are no local unsaved changes, it
   detects and reloads the external change -- relying on the
   file-watcher service's existing de-duplication/dispatch (TODO
   578cb6b), not a new mechanism; if there are local unsaved changes,
   flag the conflict without clobbering them. Performance for a
   pathologically-high-frequency writer on a single watched file is
   explicitly out of scope for now -- revisit only if it becomes a
   real, observed problem.
   [planned: file-watch-self-write-consolidation.md]
465c404. COMPLETED: Bug: in the Project Files widget, the "Open Folder" button and
   the search box's chrome (background/border) don't scale with zoom,
   similar to how the tree-collapsing controls (">") were also not
   scaling properly before that was fixed. Screenshot: the widget
   zoomed in to roughly 3-4x -- the titlebar ("Project Files" label,
   "x" close button) renders at the normal constant screen size, as
   designed, but within the widget's own content the "Open Folder"
   button's text is huge and overflows well outside its own grey
   rounded-pill background (which stayed a visibly smaller size), and
   the "Search..." placeholder text is similarly oversized and
   overflows past the right edge of the search box's own thin border.
   The text itself correctly scales with zoom; each control's own
   native-style-painted background/border chrome does not, desyncing
   from it.
   [planned: file-explorer-toolbar-zoom-scaling.md]
a053e3a. COMPLETED: Update widgets which load files to note in the title bar for
   the widget if the widget is loading a file from a path outside of
   the currently associated directory, by showing "[EXTERNAL]".
   [planned: widget-external-file-indicator.md]
95f7ce9. COMPLETED: Add a global error handler: on an uncaught exception anywhere
   in the app, attempt to append the stack trace to a file called
   `DESK-CRASH-[timestamp].log` in the project folder. Must not itself
   "further crash" if writing that log fails for any reason.
   [planned: global-crash-log-handler.md]
810a5d6. COMPLETED: Investigate and fix: a segmentation fault occurred opening
   `./necro-4x/necro-4x.desk`. The last action taken in that Desk
   beforehand was double-clicking `./necro-4x/.desk_temp
   /desk-temporary-ui.md` in the Project Files widget to open it (this
   opens it in a new Editor widget instance). This may or may not be
   related to work done around the same time on TODO a053e3a (the
   "[EXTERNAL]" titlebar marker). Traceback captured at the time (paths
   scrubbed to start at `./desk/`; trace is cut off after this point --
   no exception type/message was captured):

   ```
   Traceback (most recent call last):
     File "./desk/widgets/project_files/widget.py", line 246, in _open_index
       widget.set_file(path)
       ~~~~~~~~~~~~~~~^^^^^^
     File "./desk/widgets/editor/widget.py", line 181, in set_file
       self._load_file(path)
       ~~~~~~~~~~~~~~~^^^^^^
     File "./desk/widgets/editor/widget.py", line 146, in _load_file
       self.refresh_external_path_status()
       ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^
     File "./desk/widgets/editor/widget.py", line 155, in refresh_external_path_status
       is_external = self._current_path is not None and current_context.path_is_external(
   ```
   [planned: segfault-open-tempui-file-in-editor.md]
10b0321. COMPLETED: in the TODO widget, please change the pop-up item adder/editor so that it is restricted to remain visually within the TODO widget itself.
   [planned: todo-widget-popup-stays-within-bounds.md]
f8d9cec. COMPLETED: Add a new (or existing?) tempui capability to allow agents to add "scratch" text, and make it clear in the tempui instructions given to claude that when the user refers to "scratch," that is what is meant, unless there is a more pressing local meaning.
   [planned: tempui-scratch-capability.md]
cdf45cb. COMPLETED: Add "bring to front" and "send to back" buttons to the top-right of widgets, left of the "x" button, which move it in visual z-order to the front or back, respectively.
   [planned: widget-z-order-buttons.md]
ed483e2. COMPLETED: split the widget-adding popup menu list of popups into collapsible groups, with the current groups being "active" and "deprecated", and default to showing active as shown and deprecated as collapsed.
   [planned: widget-spawn-menu-groups.md]
9743419. COMPLETED: Add a md file to the source with a description of the markdown rendering capabilities of Desk. update the markdown_ex markdown viewer to be able to show a tempui-based markdown file; in that case, add a "save a copy" button to replace "open" and default to the root of the project directory with a default file name derived from the first line of the markdown file; once that file is saved, it should be opened in a new normal markdown_ex widget, and the original tempui one should remain open.
   [planned: markdown-rendering-doc-and-tempui-markdown.md]
fb76057. COMPLETED: Ensure that "widget-local storage" exists: a means by which
   widgets can store data in the current .desk file. Checked: this
   capability does not yet exist -- `WidgetState` currently only holds
   geometry + `instance_id`, no per-instance state payload.
   `PARKINGLOT.md` already has a parked note on this exact gap
   ("Widgets can't persist an arbitrary per-instance chosen file across
   reload"), scoping the same underlying design question: a `state:
   dict` on `WidgetState`, a widget-side read/write protocol, and a
   generalized post-build binding replacing the current per-kind
   `_bind_temp_ui_widget`/`_bind_claude_widget` special-cases. If/when
   this is built (or if some equivalent mechanism already exists
   elsewhere and was missed), it should be consistently branded
   "widget-local storage" throughout code, docs, and future TODO items.
   [planned: widget-local-storage.md]
ac212bc. COMPLETED: Create a "stack" widget to keep track of nested discussions,
   with its data stored in widget-local storage (see TODO fb76057 --
   depends on that capability existing), plus a button to copy the
   stack as markdown into a project file called `STACK-[timestamp].md`,
   and the ability to load from an appropriately-formatted stack
   markdown file.
   [planned: stack-widget.md]
4c3fe4b. COMPLETED: When creating a new .desk, the user should pick both the title
   and the initial associated directory (today, `new_desk` only prompts
   for a name/title and always creates the new Desk inside the
   *current* Desk's directory, with no directory picker at all), with
   the directory picker defaulting to the current Desk's associated
   directory.
   [planned: new-desk-directory-picker.md]
fbd0554. COMPLETED: Add an option during new Desk creation to initialize the new
   Desk with a `development-process.md`, sourced initially from the
   current Desk's own `development-process.md`. Additionally: if a
   `development-process.md` exists for a Desk's associated project when
   a Claude widget is opened, add an instruction to read that file to
   the initial prompt given to claude (see `CLAUDE_WIDGET_PROMPT` in
   `widgets/claude/widget.py`, which already conditions its prompt on
   the current Desk's directory).
   [planned: development-process-seeding.md]
67ab2df. COMPLETED: Implement a general solution so that already-placed tempui
   -bound widgets live-refresh when their `.desk_temp` file is
   genuinely edited externally, instead of a notification click only
   centering the view on stale content (surfaced while implementing
   TODO 9743419 -- I'd described that capability as "live," which
   wasn't true of any tempui-bound widget kind). Reuses the existing
   generalized `_bind_temp_ui_content` dispatch; a widget with local
   editable state that a blind refresh could clobber (only Scratch, so
   far) opts out via a new optional `has_unsaved_local_edits()` hook.
   Resolves TODOs `f668aef`/`091bc27`/`9ee505f`/`6fbae42` below as part
   of the same implementation, rather than separately.
   [planned: tempui-live-refresh.md]
f668aef. COMPLETED: Make the Question widget live-refresh when its tempui file is
   edited after being placed (resolved by TODO 67ab2df's general
   solution -- documented gap, see `PARKINGLOT.md`).
091bc27. COMPLETED: Make the LightningRound widget live-refresh when its tempui
   file is edited after being placed (resolved by TODO 67ab2df's
   general solution -- same underlying gap as Question, not
   previously called out separately).
9ee505f. COMPLETED: Make the Scratch widget live-refresh from its tempui file
   without clobbering unsaved local edits (resolved by TODO 67ab2df's
   general solution, which specifically had to account for this case).
6fbae42. COMPLETED: Make the Markdown tempui-bound content widget (TODO 9743419)
   actually live-refresh as originally described (resolved by TODO
   67ab2df's general solution).
cb2790d. COMPLETED: When creating a new Desk, don't add all of the widgets to it --
   just open a markdown viewer of the README.md file if there is one
   for the project, or else add a Scratch widget with content for a
   basic readme that has a "# [desk name] README" at the top followed
   by a section called "## What this project is about or exploring...".
   [planned: new-desk-default-widgets.md]
7a086ba. COMPLETED: Add a Questions widget that works similarly to the TODO
   widget, but for managing QUESTIONS.md. [planned: questions-widget.md]
a801180. COMPLETED: Add to the tempui instructions to always use QUESTIONS.md for
   any questions there are for the user. If adding a new question, send
   a top-right tempui notification that, when clicked, either visually
   focuses a currently-opened Questions widget (see TODO 7a086ba) or
   else opens a new Questions widget and focuses it.
   [planned: questions-notification-routing.md]
96013cf. COMPLETED: Rename the current markdown widget (`widgets/markdown/`) as
   `markdown_old_basic`, and add a timestamped note near the top of
   relevant plans that this rename was done, but don't change the rest
   of the plan. Mark that widget as deprecated and confirm that it
   shows up in the deprecated group in the widget-add context menu
   (depends on TODO ed483e2's active/deprecated grouping existing).
   [planned: markdown-widget-identity-swap.md]
858752b. COMPLETED: rename the current markdown_ex
   widget (`widgets/markdown_ex/`) as `markdown` -- not
   `markdown_old_basic` as originally (conflictingly) written; the
   user clarified markdown_ex becomes the new default "markdown"
   widget while the plain widget (TODO 96013cf) becomes the deprecated
   `markdown_old_basic`, replacing it. Add a timestamped note near the
   top of relevant plans that this rename was done, but don't change
   the rest of the plan.
   [planned: markdown-widget-identity-swap.md]
17ac2a8. COMPLETED: Check for places in the code where the old basic markdown
   widget is being used, and add to QUESTIONS.md about whether or not
   they should be updated to point to the new markdown widget. (Depends
   on TODO 96013cf/858752b's rename(s) actually happening first, and on
   resolving which widget "the new markdown widget" refers to.)
   [planned: audit-old-basic-markdown-widget-usage.md]
5915ac2. COMPLETED: Drag and drop files into Desk should cause them to be opened
   as external. [planned: drag-drop-open-external.md]
f74945e. COMPLETED: Add a "paste" item to the top of the widget menu if there is
   anything in the clipboard; if pasted, put the pasted material into
   a file in the temp directory and attempt to open it with a
   corresponding widget; if it is markdown, then just use the markdown
   approach we're implementing with the new DSL entry (TODO 9743419);
   if it is text but not markdown, open it as a scrap (if there isn't
   a DSL entry for that, add one -- see TODO f8d9cec's existing
   `Scratch` tempui capability); if it is non-text content (binary),
   paste it as a new file in the project directory with a filename
   like `PASTED-ITEM-[timestamp].[file extension]`.
   [planned: paste-clipboard-routing.md]
8f5568f. COMPLETED: When the desk-switching MRU is shown, or when one of its items
   is clicked, ensure the shown/clicked item's file is still where
   it's expected to be (i.e. that it hasn't moved or been deleted).
   Checked: `desk.recent_desks.load_mru()` already filters missing
   files out of what it *returns* on every call (`p.is_file()`), but
   never persists that removal back to `~/.desk/recent_desks.json` --
   the stale entry just gets silently re-filtered every time, forever.
   If a file is missing when showing the MRU, actually remove it from
   the persisted list (not just the in-memory display). If the user
   clicks an MRU item whose file is missing, do not continue the "load
   new desk" operation -- checked: `DeskWindow.switch_desk`'s current
   behavior for a nonexistent path (`Desk(path=path)`) silently creates
   a brand-new *empty* Desk at that path instead, with no warning at
   all. Instead, show a modal pop-up warning that the file is no
   longer there, giving the full path in selectable/copyable text (an
   explicit exception to `CLAUDE.md`'s general "labels shouldn't be
   user-selectable" convention, matching its own "unless specifically
   requested" carve-out). [planned: mru-file-existence-check.md]
c458012. COMPLETED: `scripts/todo_item_ids.py` only works when run from a directory
   that both has that exact script at that path and can import this
   app's own `desk` package (`make_item_id` actually lives in
   `desk.todo_ids`) -- neither holds for a brand-new project Desk, even
   though TODO fbd0554 already seeds that project with a
   `development-process.md` whose own "Item IDs" section tells you to
   run exactly that script. Add seeding it (self-contained, no `desk`
   package dependency left) to the new-Desk initialization process
   alongside `development-process.md`, and update `.gitignore`
   provisioning to also cover what running it produces
   (`scripts/__pycache__/`).
   [planned: seed-todo-item-ids-script.md]
e69f209. COMPLETED: Bug: when widgets with carets overlap visually, sometimes
   focus seems to switch between them while typing.
   [planned: trap-widget-tab-focus.md]
91b3f42. COMPLETED: Feature: New widgets and extension of tempui DSL inside the
   .desk_temp. Only in-browser (html/css/js) widgets (no python) can be
   loaded this way. Introduce new tempui DSL for introducing new types
   of widgets to be used in the current Desk. All code should be
   base64 encoded when it is embedded in another file. Widgets defined
   in tempui can only be added to the Desk by tempui. Additionally,
   add constructs to the tempui DSL to allow the extension of the
   tempui DSL, so that a tempui-based widget can be invoked by tempui.
   In tempui-defined widgets' titlebar, add a button that says
   [TEMPUI], which, if pressed, offers to promote the widget to the
   Desk; if user confirms, then store the widget in the .desk file and
   also include the tempui DSL extension in a list in the .desk file,
   as well, re-pointing it towards the .desk file version of the
   widget, and removing it from tempui. Widgets in the .desk file
   should be registered just like built-in widgets at startup and
   after being added. All widgets and tempui DSL extensions must have
   a human-friendly label that can be shown in the UI (i.e. no UUIDs
   for widget names). Ensure the tempui md file explains the tempui
   side of things so that agents can use this feature. On startup or
   when a new tempui DSL item is added, ensure that the tempui md file
   includes information about all of the tempui DSL extensions in the
   .desk_temp folder or in the .desk file.
   [planned: tempui-custom-widgets.md]
f7b1611. COMPLETED: We need to make sure that the tempui md file is up-to-date, not
   just with the tempui DSL but with new versions of the rest of the
   document. Introduce a version number as a note at the top, with a
   simple integer version number that gets manually updated as the
   content changes (include a comment in the code that explains the
   versioning process). Before opening a Desk, ensure that the tempui
   md main content is up-to-date with the expected version; if there
   is no version, that means that it is out of date; be certain not to
   clobber the DSL extensions, if there are any.
   [planned: tempui-doc-versioning.md]
6857997. COMPLETED: Bug: [TEMPUI] should only be shown if the widget definition is
   in .desk_temp, not if it is in the .desk file.
   [planned: fix-tempui-promote-button-and-spawn-menu.md]
2b2a642. COMPLETED: Bug: promoted a temp widget and it is in the .desk file, but it
   is not showing up in the list of active widgets in the add-widget
   context menu, even after reloading the app.
   [planned: fix-tempui-promote-button-and-spawn-menu.md]
5734529. COMPLETED: Another Claude instance running inside of a Desk was trying to
   implement a tempui widget, and it had the following feedback: "Not
   Implemented: state persistence (no widget-local-storage wiring --
   the Desk Bridge API exists for html widgets but nothing implements
   save/restore for one yet)." Fix that, including adding a
   description of the (updated) Bridge API to the tempui md file.
   [planned: html-widget-local-storage-bridge-api.md]
e57ce5f. COMPLETED: It's probably time to split out the tempui md file into multiple
   pieces. Keep the original file, but split out the content of some
   of the less-general sections into other files and reference them
   with relative paths. The version number in the "main" (original)
   file will stand for all of the files, they don't each need their
   own. Keep the list of tempui DSL extensions in the main file, in
   its own section at the bottom, as it is, now. Also, none of the
   documents should mention Desk source code or repo documents (e.g.
   do not mention the Desk architecture document); the documents Desk
   provides in .desk_temp should be sufficient. Check for places where
   the original file is mentioned in the code and make sure that all
   of those sites are updated, e.g. desk-load-time checks.
   [planned: split-tempui-doc.md]
855ca76. COMPLETED: Bug: the Claude widget's prompt tells the agent to follow the
   tempui doc's links to the other split-out files unconditionally.
   Instead, tell the agent to follow those links only as needed, e.g.
   it should only read tempui-lightning-round.md if it needs to run a
   lightning round; desk-temporary-ui.md should include just enough
   context for each one that the agent can understand the use cases
   without opening them.
   [planned: fix-claude-prompt-tempui-links-wording.md]
4ab5875. COMPLETED: widgets/hex_flower (another Claude instance's port of
   ../../claude-projects/hexsheet's hexflower sheet item) renders a
   blank page when run locally. Investigate what is failing and write
   a DESK_FEEDBACK-[timestamp].md file with suggestions for how to (a)
   update the documentation so that similar issues do not happen in
   the future, and (b) make additional improvements to the tempui
   widget feature to help this kind of work go better in the future.
   [planned: investigate-hex-flower-blank-page.md]
411d0e0. COMPLETED: Whatever guidance covers the Bridge API's local-storage calls
   should make clear that a ported widget's own prior persistence
   mechanism (custom events, global variables, whatever the original
   project used) needs to be explicitly re-wired to
   `self.getLocalStorage`/`setLocalStorage` -- porting a widget doesn't
   make its old persistence approach work inside Desk automatically,
   and there's currently nothing prompting an agent to check for that
   mismatch.
   [planned: document-persistence-rewiring-for-ported-widgets.md]
c0875bc. COMPLETED: tempui DSL addition which enables Desk to initiate a
   conversation about a parking lot item with a new claude session,
   where the new session is still given instructions about being
   embedded in Desk but also is at the end of the intro prompted with
   something like "let's discuss an item from PARKINGLOT.md: [full
   parking lot item text]".
   [planned: tempui-discuss-parking-lot-item.md]
46e1b42. COMPLETED: Add a button to each of the questions displayed in the
   question widget: the button should be labeled "Discuss" and
   clicking it should do the same thing as the tempui DSL addition
   (TODO c0875bc).
   [planned: questions-widget-discuss-button.md]
624ff3a. COMPLETED: Bug: launching a DiscussParkingLotItem tempui discussion (TODO
   c0875bc) failed to let claude start -- something about dumping the
   entire PARKINGLOT.md item's text into the initial launch prompt
   broke it. Instead of embedding the full item text, the tempui file
   should just reference the item by its line number in PARKINGLOT.md,
   and the new session should read the file itself. Additionally, add
   an instruction telling claude not to immediately start a new
   discussion in Desk (e.g. by creating another DiscussParkingLotItem
   file) but to just have the discussion in the current session.

   Traced the full launch path: the assembled prompt was already
   correctly passed through a single `shlex.quote(...)` call before
   being spliced into the `exec claude ...` command typed into the
   PTY, so this wasn't naive/unescaped shell interpolation -- but the
   full parking-lot item's raw markdown text is unbounded, real prose
   (backticks, quotes, blank lines), and at least two still-plausible
   failure modes exist independent of the quoting itself: bash's
   default interactive `histexpand` performs `!`-history-expansion even
   inside a single-quoted argument, and the whole quoted blob is
   written to the PTY in one shot immediately after spawning bash,
   before it's certain readline has taken over the terminal in raw
   mode (risking the kernel tty layer's canonical-mode line-length
   limit). Neither was independently reproduced, but shortening the
   message sidesteps both regardless of which (if either) is the exact
   mechanism.

   `DiscussParkingLotItem`'s DSL shape changed from "first line label,
   rest of file the full verbatim item text" to "first line label,
   second line `Line <N>` (the item's starting line number in
   PARKINGLOT.md, written by the creating agent)" --
   `parse_discuss_parking_lot_item` now returns `(label, line_number)`.
   `_place_discuss_claude_widget` (`src/desk/shell/window.py`, shared
   with the Questions widget's Discuss button, TODO 46e1b42) gained a
   `parking_lot_line: int | None` param: when given, it builds a short
   "read PARKINGLOT.md yourself at that line" reference instead of
   splicing in full text; the Questions-widget path (full `item_text`,
   unaffected -- QUESTIONS.md entries aren't line-number-addressed and
   weren't reported broken) is unchanged. Both paths now get a shared
   trailing instruction telling the new session to discuss it in this
   same session rather than starting another new Desk discussion of
   its own. `TEMPUI_DOC_VERSION` bumped 5 -> 6; this project's own
   already-provisioned `.desk_temp/desk-temporary-ui.md` and
   `tempui-discuss-parking-lot-item.md` refreshed via a real
   `ensure_docs_current` run (not hand-edited) so they exactly match
   the new source; the originally-reported demo tempui file rewritten
   to the new `Line <N>` format. Verified headlessly (real
   `DeskWindow`-method-on-a-double pattern): `parse_discuss_parking_lot_item`
   round-trip/rejection cases; `_place_discuss_claude_widget`'s built
   instructions for both the line-number and full-text paths (each
   contains its expected content plus the new "don't start a new
   discussion" sentence); `_activate_temp_ui`'s CLAUDE_WIDGET_ID branch
   correctly extracts and forwards the line number; the final
   `exec claude ...` command string built end-to-end from the new,
   short prompt (~1000 chars, well short of anything that was ~1500-
   3000+ chars with a real item's full text spliced in).
   [planned: fix-discuss-parking-lot-item-launch-prompt.md]

a48e968. COMPLETED: New widget: Parking Lot. Reads the nearest `PARKINGLOT.md` and
   displays each item's title in a scrollable list. Each row has a
   "Discuss" button in a column on the right that launches a new
   claude session to discuss that item. Double-clicking a row's title
   instead opens just that one item in a Markdown widget, via the
   tempui mechanism.

   Implemented as a new `src/desk/parking_lot_file.py` parser (mirrors
   `desk.questions_file`'s shape: dataclass + regex parser) that reads
   PARKINGLOT.md's top-level `- **Title**` bullets into
   `ParkingLotEntry(title, line_number, raw_text)` -- `line_number`
   uses the exact same "starting `- **Title**` bullet line" definition
   the tempui `DiscussParkingLotItem` keyword's own doc already
   established (TODO 624ff3a), so it's directly usable by
   `_place_discuss_claude_widget`'s existing `parking_lot_line`
   parameter. A wrapped (multi-line) title, e.g. this file's own
   `WidgetSpawnMenu._activate_item` entry, collapses correctly to one
   line.

   New `widgets/parking_lot/` widget, modeled on
   `widgets/questions/widget.py`'s shape (file watching,
   `external_path_changed`) but read-only. Each row is a
   `setItemWidget`-placed `QLabel` (title) + fixed-width `QPushButton`
   ("Discuss") -- a real column of Discuss buttons down the right edge,
   as asked for, rather than the Questions widget's single floating
   hover button (which doesn't fit that description). Since
   `setItemWidget` content doesn't reach `QListWidget.itemDoubleClicked`
   (mouse events over a child widget go straight to that child, not
   the list view underneath), the title label is a small `_TitleLabel`
   subclass that reports its own `mouseDoubleClickEvent` as a signal.
   Double-clicking writes a `Markdown <title>` tempui file (the
   existing keyword/format from `desk.temp_ui.parse_markdown_tempui`)
   into `.desk_temp/`, reusing Desk's existing tempui notification/
   placement flow rather than placing a Markdown widget directly --
   matches "loads ... as tempui" literally. The Discuss button calls
   the `current_context` "discuss starter" hook with the item's line
   number, not its full text, avoiding a repeat of the exact
   launch-prompt-length problem TODO 624ff3a fixed.

   `DeskWindow.start_discussion` (the discuss-starter hook, TODO
   46e1b42) widened to accept an optional `parking_lot_line` parameter
   (and `item_text` given a default of `""`), forwarding both straight
   through to the already-`parking_lot_line`-aware
   `_place_discuss_claude_widget`. The existing Questions-widget call
   site (`starter("QUESTIONS.md", entry.raw_text)`) is untouched and
   still works unchanged. `current_context.py`'s discuss-starter hook
   type/docstring updated to match.

   Verified headlessly (`QT_QPA_PLATFORM=offscreen`, real
   `QApplication`): `parse_parking_lot_file` against this project's own
   real PARKINGLOT.md (33 items, correct title/line_number/raw_text for
   the first and a wrapped-title item); constructing the real widget
   against a synthetic PARKINGLOT.md shows the right rows; a real Qt
   `QMouseEvent` double-click dispatched to the title label (not just a
   direct method call) fires `_open_item` and writes a tempui file
   whose content round-trips through `parse_markdown_tempui` back to
   `(title, raw_text)`; clicking a row's Discuss button (direct call)
   reaches a fake discuss-starter hook with `("PARKINGLOT.md", "",
   line_number)`; `DeskWindow.start_discussion`'s widened signature
   verified both in its new kwarg-only call style and the existing
   Questions-widget two-positional-arg style (unbound-method-on-a-
   double pattern); `discover_widgets` picks up the new
   `widgets/parking_lot/` directory correctly.

   Not exercised: right-clicking the canvas / actually placing the
   widget from the spawn menu in a live GUI session, and a real
   `claude` binary launch from the Discuss button (same limitation
   noted in every prior widget/claude-launch TODO in this project).
   [planned: parking-lot-widget.md]

fc17b55. COMPLETED: Bug: a claude launch prompt built by
   `_place_discuss_claude_widget` embeds a literal `\n\n` in the middle
   of the prompt string. When typed into an interactive bash/readline
   PTY, each raw `\n` byte is treated as pressing Enter regardless of
   shell-quote state, breaking the still-open `shlex.quote`d command
   and leaving the shell stuck at a `>` continuation prompt instead of
   launching claude. Reported live via the new Parking Lot widget's
   Discuss button. Fixed at the source (`_place_discuss_claude_widget`'s
   leading `f"\n\n..."` replaced with a plain leading space, matching
   `_development_process_instruction()`'s existing convention) and
   defensively at the actual boundary (`ClaudeWidget.start_session` now
   replaces any stray `\n` in the assembled prompt with a space before
   `shlex.quote`, so any future caller of `extra_instructions` can't
   reintroduce this). Verified with a real, live PTY (`pty.openpty()` +
   `subprocess.Popen(["bash", ...])`, one `os.write` of the whole
   command exactly like `type_into_shell`): the old buggy instructions
   reproduce the reported stuck-at-`CONT>`-continuation-prompt behavior
   exactly, while the fixed instructions plus the new normalization
   produce a single clean line with no continuation prompt.
   [planned: fix-embedded-newline-breaks-claude-launch-prompt.md]

51be2bc. COMPLETED: Bug: after TODO fc17b55's fix, starting a Parking Lot
   "Discuss" session still gets stuck -- the shell just sits there, and
   typing a stray `'` plus Enter is enough to unstick it and launch
   claude. Root cause confirmed directly (not just the suspected
   mid-command truncation TODO fc17b55's own investigation flagged but
   never confirmed): this environment's PTY canonical-mode line limit
   (`PC_MAX_CANON`) is exactly 1024 bytes, and a single unterminated
   line longer than that is truncated at that boundary -- critically,
   including the line's own terminating newline if it falls past the
   boundary, which leaves a blocked shell `read`/`readline` with no way
   to ever see a complete line (matching the reported "just sits
   there" symptom exactly). `_place_discuss_claude_widget`'s
   apostrophe-heavy hand-written instructions (plus the shared
   `CLAUDE_WIDGET_PROMPT`, which had one too) made an already-long
   command line long enough to risk crossing that boundary. Fixed per
   direct instruction: stop splicing the actual discussion instructions
   into the command line at all -- `_place_discuss_claude_widget` now
   writes them to a standalone file under `.desk_temp`
   (`_write_discuss_instructions_file`) and passes only a short,
   fixed-shape, apostrophe-free instruction pointing at that file, so
   the command line's length no longer depends on the discussion
   content's length at all (confirmed: the real, realistic assembled
   command is 711 bytes, regardless of how long the referenced file's
   content is). `CLAUDE_WIDGET_PROMPT`'s own remaining apostrophe was
   also reworded away. Investigating the exact mechanism also surfaced
   a second, independent gap in the same delivery path:
   `TerminalWidget.type_into_shell`'s single `os.write` to a
   non-blocking PTY master fd never checked how many bytes it actually
   wrote, silently dropping any unwritten remainder forever -- fixed
   with a bounded retry loop (defense in depth; it can't rescue a line
   that's fundamentally longer than the kernel's own line buffer, which
   is what the file-based redesign actually fixes). Verified
   headlessly: the built `claude_extra_instructions`/prompt contain no
   `'` character for either Discuss-launch path, the written file
   exists with the exact expected content and isn't mistaken for a
   temp-ui widget file, a real live PTY test directly isolated and
   confirmed the 1024-byte truncation-eats-the-newline mechanism, and a
   simulated genuine short-write test confirmed `type_into_shell`'s new
   retry loop actually recovers a payload the old single-call code
   would have silently truncated. A clean live before/after repro of
   the exact original "stuck" symptom via the old apostrophe-heavy
   command was attempted but didn't reproduce consistently in this
   session's sandboxed environment (see the plan's Verification section
   for why) -- a weaker result than a clean repro, though the
   underlying mechanism is independently confirmed above via a
   dedicated isolated test.
   [planned: fix-discuss-claude-prompt-file-based-instructions.md]

6f9c51b. COMPLETED: Add an event message channel service to Desk,
   following the "mediator" topology (a component of Desk itself acts
   as mediator -- widgets never talk to each other directly). Via the
   Bridge API, widgets should be able to register for and receive
   named messages, and to send named messages. The Bridge API should
   handle identity details (use the widget's *instance* id, not its
   widget-definition id). Events are logged by default into a file
   called MEDIATED-EVENT-LOG.tsv. Also build a python widget to view
   logged events, with a "live tail" mode and functionality to clear
   the log (with confirmation). Add a description of the usage of
   these events to the Bridge API document (the `DefineWidget`/Bridge
   API section of the tempui docs, `tempui-custom-widgets.md`),
   following the existing versioning process for updating tempui
   documents (`TEMPUI_DOC_VERSION` in `src/desk/temp_ui.py`).
   **Prioritized ahead of all other items** (there were no other open
   items at the time, so this was a no-op in practice, but recorded per
   the request).

   Shipped as: a new, Qt-free `desk.event_mediator.EventMediator`
   (thread-safe via a lock plus one `queue.Queue` per subscribed
   *instance* id, never the widget-definition id) -- one shared
   instance for the whole app run, constructed in
   `desk.server.runner.start_server` alongside the existing
   `GuiBridge`, and reachable both from the Local Web Server's new
   `POST/GET /api/bridge/events/{subscribe,unsubscribe,publish,poll}`
   routes (`events` capability; `poll` is a clamped-to-30s long-poll,
   not a true WebSocket -- browser `WebSocket` can't attach the custom
   `X-Desk-*` auth/identity headers every other Bridge route already
   relies on) for `kind: "html"` widgets, and from `kind: "python"`
   widgets directly in-process via a new
   `desk.shell.event_broker.EventSubscription` (a `QTimer`-polled Qt
   wrapper, never blocking the GUI thread) reached through a new,
   generically-called `DeskWindow._bind_event_mediator` duck-typed
   hook (`bind_event_mediator(instance_id, mediator)`, mirroring
   `_bind_claude_widget`'s existing "resolved after `build()`, not
   through it" shape -- no widget currently had any way to learn its
   own instance id from `build()`'s signature alone). The mediator's
   own `MEDIATED-EVENT-LOG.tsv` (in the current Desk directory, kept in
   sync via the same `_refresh_picker` choke point
   `current_context.set_current_desk_directory` already uses) logs
   every publish regardless of origin, JSON-encoding the payload (which
   also makes the TSV row safe for free, since `json.dumps` escapes any
   literal tab/newline inside a string value). The sender never
   receives its own publish back (a documented, deliberate default, not
   specified by the request). New `widgets/event_log/`: a read-only
   `QTableWidget` view of the log, kept fresh by a `SingleFileWatcher`
   (same reused component the TODO widget already watches `TODO.md`
   with) regardless of a "Live Tail" toggle, which controls only
   whether a refresh auto-scrolls to the bottom; a Clear action
   (`QMessageBox`-confirmed, split into its own headlessly-testable
   `_confirm_clear` method, matching `CrashLogWidget`'s
   `_confirm_delete`) routes through the live mediator when one is
   wired up (reusing its write lock, so it can't race a concurrent
   publish's own log append) rather than writing the file itself.
   `tempui-custom-widgets.md` (source: `_CUSTOM_WIDGETS_DOC` in
   `src/desk/temp_ui.py`) gained a new "Sending and receiving named
   messages" section describing `desk.events.*`, per the existing
   `TEMPUI_DOC_VERSION` process (bumped 6 -> 7, so every
   already-provisioned Desk directory picks up the refreshed doc via
   the existing `ensure_docs_current` mechanism, not a special case).
   `design-docs/architecture.md`'s Bridge API section and capability
   table updated to match.

   Verified headlessly throughout (`QT_QPA_PLATFORM=offscreen`; a real
   running server via `desk.server.runner.start_server` for the REST
   surface, since `httpx`/`starlette.testclient` isn't installed --
   `urllib.request` against the real server instead, arguably closer to
   the real integration boundary anyway): the mediator core (sender
   -exclusion, subscribe/unsubscribe/unsubscribe_all/clear_all,
   non-blocking `drain`, genuinely-blocking `poll` receiving a real
   cross-thread publish and correctly timing out, tab/newline-safe TSV
   logging, `clear_log`); the four REST routes end to end including a
   403 on a missing `events` capability and fully independent
   subscriptions between two instances of the same widget id;
   `EventSubscription`'s Qt-signal delivery and its
   `destroyed`-triggered cleanup; `DeskWindow._bind_event_mediator` end
   to end via a real `DeskWindow` and a scratch widget (distinct
   instance ids, cross-instance delivery, sender exclusion, and
   subscription cleanup on close, all via the real, generic binding
   path -- no widget-specific code in `window.py`); the Event Log
   widget's parsing/formatting/live-tail/clear-confirmation behavior,
   including the lock-safe mediator-routed clear path specifically; a
   full real-app-shaped boot against this project's own actual
   `widgets/` directory (all ~20 shipped widgets) placing a real Event
   Log widget that live-picks-up a real publish landing in a real,
   on-disk log file; and `ensure_docs_current` refreshing a
   version-6-stuck doc directory to 7 with the new section present.
   [planned: event-mediator-channel.md]

f693275. COMPLETED: Bug: reported live -- after restarting Desk, the tempui-DSL
   -defined `Alice`/`Bob`/`Starter` widgets (built for TODO 6f9c51b) all
   fail with `subscribe failed: ... (400): {"detail":"Unknown widget
   id: 'Alice'"}`. Root cause already flagged in PARKINGLOT.md (the
   "The Bridge API's `require_caller` can't resolve a tempui-DSL
   -defined custom widget kind at all" entry, surfaced back when TODO
   `5734529` built self.getLocalStorage/setLocalStorage): `require_
   caller` (`src/desk/server/app.py`) resolves the calling widget only
   via `discover_widgets(widgets_dir).get(x_desk_widget_id)`, which
   only ever scans the real, on-disk `widgets/` directory -- a
   tempui-DSL-defined custom widget (TODO `91b3f42`) has no such
   directory; its `WidgetInfo` only lives in the live `DeskWindow
   ._widgets` catalog. This blocks *any* capability-gated Bridge call
   (`workspace.*`/`fs.*`/`widgets.*`/the new `events.*`) for a custom
   widget, not just `events`. Separately, even a fixed lookup wouldn't
   be enough on its own: `_register_custom_widget` always registers a
   custom widget with `capabilities=[]` hardcoded, since the
   `DefineWidget` tempui DSL has no way to declare any -- needs a new
   `Capability` DSL line too. Now that a second real feature (`events`)
   is blocked by this, worth actually designing and fixing rather than
   re-parking (see the PARKINGLOT.md entry's own "not designed yet;
   parking rather than guessing at the right generalization from a
   single specific fix's own narrow workaround").
   **Prioritized ahead of all other items** (live-blocking a feature
   the user is actively using right now).

   Fixed: `require_caller` (`src/desk/server/app.py`) now falls back
   to the live, `GuiBridge`-reachable widget catalog (a new
   `DeskWindow.get_widget_info` accessor) when `discover_widgets
   (widgets_dir)`'s on-disk scan misses -- resolving every existing
   capability (`workspace`/`fs`/`widgets`) for a tempui-DSL-defined
   custom widget, not just `events`. The `DefineWidget` tempui DSL
   gained a new, repeatable `Capability<TAB>name` line;
   `CustomWidgetDefinition` carries it through to the `WidgetInfo`
   `_register_custom_widget` builds (previously always `capabilities=
   []`), and `.desk`-file persistence round-trips it (defaulting to
   `[]` for a pre-existing `.desk` file with no such key, so old files
   keep loading fine). `tempui-custom-widgets.md` documents the new
   line (`TEMPUI_DOC_VERSION` 7 -> 8); the now-resolved PARKINGLOT.md
   entry removed. This project's own live `Alice`/`Bob`/`Starter`
   `DefineWidget` files (`.desk_temp/`, untracked) were edited in place
   to add `Capability\tevents`, so they'll work again once Desk is
   restarted (this fix is in `src/desk/**`, which only takes effect on
   restart, unlike widget source).

   Verified headlessly, including against a real `DeskWindow` + real
   running server reproducing the exact originally-reported failure
   (now fixed) alongside a regression check that a custom widget
   *without* the right capability still correctly 403s, a truly
   -unknown widget id still 400s, and a real on-disk widget's own fast
   -path resolution is unaffected. See the plan's Status section for a
   testing note on a real GuiBridge-threading deadlock hit (and fixed)
   in the verification script itself, not the implementation.
   [planned: fix-custom-widget-bridge-capability-resolution.md]
1e75140. COMPLETED: write a document about the starter/alice/bob
   experiment and store it in design-docs. Shipped as
   `design-docs/alice-bob-starter-experiment.md`: what the three
   widgets do, the reaction rule (Alice reacts to any integer < 10,
   Bob additionally requires it be positive), why Bob's extra
   condition is necessary (the mediator excludes only the sender from
   its own publish, not every other subscriber -- both Alice and Bob
   receive Starter's seed `0` since neither is its sender, so without
   the filter both would react and produce a duplicate branch), the
   resulting 0->10 chain, the `Capability` DSL line each widget
   declares (TODO f693275), and a pointer to where `DefineWidget`
   widgets actually live (a Desk directory's own gitignored
   `.desk_temp/`, not source control -- there is no checked-in copy of
   the exact HTML).
   [planned: starter-alice-bob-experiment-doc.md]
e35bcf0. COMPLETED: pop-ups from inside the browser widget show up in a
   separate macos window. is there any way to avoid that? could they be
   fully contained within the widget frame, instead?

   Root cause: `BrowserWidget` never connected to `QWebEnginePage
   .newWindowRequested`, so Qt WebEngine's own default handling created
   a genuinely separate, unmanaged top-level native window for any
   `window.open()`/`target="_blank"` request -- yes, avoidable, and
   fully containable. Fixed: `BrowserWidget` now has a second, embedded
   pop-up `QWebEngineView` shown via a `QStackedWidget` in place of the
   main page (URL label + close button), and connects
   `newWindowRequested` to redirect every request into it via
   `request.openIn(...)` -- the same pattern Qt's own `simplebrowser`
   example uses. A *fresh* view/page is created per pop-up open (not
   reused across opens): verification found that reusing one could hit
   a real, reproducible internal Chromium consistency assertion on a
   second rapid redirect, fixed by always tearing down and recreating
   instead. Verified headlessly against a real local HTTP page's own
   `window.open()` button (real JS click, not a Python stand-in),
   confirming `QApplication.topLevelWidgets()`'s count never increases,
   the pop-up panel shows the right content, both `window.close()` and
   the widget's own close button return to the main page, and repeated
   open/close/reopen no longer crashes on exit (reproduced the crash
   consistently pre-fix, confirmed gone across multiple stress runs
   post-fix). A separate, pre-existing bug found (not caused) during
   this verification -- the Back/Forward buttons' own enabled/disabled
   state can go stale after a real navigation, confirmed present
   identically on the untouched original file -- was parked in
   `PARKINGLOT.md` rather than fixed here, being unrelated to what this
   item asked for.
   [planned: browser-widget-contained-popups.md]
9767c1a. COMPLETED: add a Bridge API service by which a widget (with
   permission from the Desk user) can get a tree-view snapshot of the
   dom and console log of an html-based widget.

   Shipped as a new `introspect` capability + `desk.introspect
   .snapshot(targetInstanceId)` -> `{dom, console}`. Two new pieces
   needed first: `ChromiumWidget` now sets an explicit
   `_LoggingWebEnginePage` (overriding the virtual
   `javaScriptConsoleMessage` -- no signal exists for this) giving
   every `html` widget a bounded 200-entry rolling console-output
   buffer, queried on demand; and a new `GuiBridge.call_async`,
   generalizing `GuiBridge.call` for a GUI-thread operation that's
   itself async (`QWebEnginePage.runJavaScript`'s result only arrives
   via a later callback) -- blocking naively inside `call`'s own `fn()`
   waiting for that callback would deadlock the GUI thread against its
   own event loop, so `call_async`'s `starter` must instead kick off
   the operation and return immediately, with `resolve(value)` (called
   later, whenever the real callback fires) actually completing the
   call. Unlike every other Bridge capability, `introspect` is not
   satisfied by a manifest declaration alone: the first request for a
   given (caller, target) pair shows the Desk user a blocking
   confirmation dialog naming both widgets (`DeskWindow
   .request_introspect_permission`); declining returns no data at all.
   Grants are in-memory only (`DeskWindow._introspect_grants`), cleared
   on `switch_desk`, never persisted to disk. `tempui-custom-widgets.md`
   documents the new capability and its permission model
   (`TEMPUI_DOC_VERSION` 8 -> 9); `design-docs/architecture.md`'s
   capability table and Security Considerations updated to match.

   Verified headlessly end to end via a real `DeskWindow` with three
   real placed `html` widgets: a capability-less caller `403`s before
   ever reaching the permission dialog; an approved request returns a
   correctly-nested real DOM tree (confirmed against the target's
   actual markup, not a stub) plus its real captured console log
   (`info`/`error` entries, right levels); a repeat request for the
   same pair succeeds without re-prompting (confirmed via a
   confirm-call counter); an unknown target `400`s; a declined request
   to a different target `403`s with no grant recorded and no data
   returned; and `switch_desk` clears every grant. `GuiBridge.call_async`
   and the console-log buffer were also verified in isolation (a
   genuinely-async resolution path with no deadlock, exception
   propagation, clean timeout; real `console.log`/`warn`/`error`
   capture and the 200-entry bound).
   [planned: introspect-bridge-capability.md]
33d3e8d. COMPLETED: do an audit of all of the UI and confirm that they don't fail to scale properly when zooming; fix anything that violates that. when the titlebar is too small to hold the buttons without growing the widget width, just show the title; if it is still too small, then for so long as that is true, "greek" the widget (show just a rectangle with the frame color; if the user clicks on a "greeked" widget, zoom/pan the desk so that widget is showing, with 20% margins on all sides. Add a button to widget title bars (labelled with an eye emoji) to do the same thing (zoom/pan to show the widget)

   Part 1 (audit): re-verified headlessly that titlebar/resize-handle/
   border counter-scaling and the three HUD overlays (`ZoomControl`,
   `DeskPicker`, `TempUiNotificationStack`) genuinely stay constant
   on-screen across zoom/pan/resize -- everything already held, no
   fixes needed there.

   Part 2 (degrade + greek): `WidgetFrame` gained a
   `chrome_state ∈ {"full","title_only","greeked"}`, recomputed on
   both `set_view_scale` and the frame's own `resizeEvent` (so a
   resize-handle drag degrades chrome too, not just zooming) from
   thresholds computed off the same fixed on-screen constants the
   counter-scaling itself targets. A `QStackedWidget` swaps to a plain
   `BORDER_COLOR`-filled page while greeked (no titlebar/handles
   reachable); a new `_EyeButton` joins the titlebar's usual button
   row; `WorkspaceView._hit_test_chrome` short-circuits on
   `frame.is_greeked` so a click anywhere on a greeked widget's bounds
   -- and the eye button, from any chrome state -- both dispatch to a
   new `zoom_to_widget(frame, margin_fraction=0.2)`, sharing its core
   fit/clamp logic with the existing `zoom_to_fit` via a new private
   `_fit_rect` helper.

   Found and fixed one real, pre-existing bug along the way (not
   introduced by this change, and independently blocking reliable
   greeking): `WidgetFrame`, once embedded via `QGraphicsProxyWidget`,
   silently grew itself back up to fit its layout's inflated minimum
   size (counter-scaled chrome's *local* sizes balloon at low
   `view_scale`) on a deferred, later-processed event -- not
   synchronously, so a check performed immediately after a zoom change
   could pass by accident while the same check failed once the event
   loop actually ran. `QLayout.SetNoConstraint` alone only partially
   fixed it; the full fix mirrors the existing Desk picker/zoom control
   HUD-drift fix (TODO `82d66c0`/`4adfcad`/`1f9bd34`): snapshot the
   known-good size before scaling, reassert it via
   `QTimer.singleShot(0, ...)` after. See the new `LEARNINGS.md` entry.

   Verified entirely headlessly (real `WorkspaceView`/`WidgetFrame`s,
   synthetic `QMouseEvent`s routed through the real mouse-event
   handlers): the audit re-checks; full → title_only → greeked
   transitions via both wheel-zoom and a manual resize-handle drag;
   title_only/greeked visual states; click-anywhere-on-greeked and the
   eye button both correctly zoom/pan with a real ~20% margin; the eye
   button correctly shrinks the full-chrome width budget (and is
   excluded, like the other action buttons, while locked); `zoom_to_fit`
   regression-checked against the `_fit_rect` refactor; a 10-cycle
   repeated-zoom stress test confirming the size-reassertion fix holds
   stably; and a full regression of every pre-existing titlebar button
   plus titlebar/resize-handle drag.
   [planned: audit-and-greek-widgets.md]
dc557b2. COMPLETED: create a general event poster widget

   Shipped as `widgets/event_poster/`: a name field, a multi-line
   payload box, a Publish button, and a status line. Binds to the
   event mediator (TODO `6f9c51b`) via the same duck-typed
   `bind_event_mediator(instance_id, mediator)` hook every
   mediator-aware `python` widget implements, using
   `desk.shell.event_broker.EventSubscription` purely to get a
   correctly-identified `.publish(name, payload)` call (needs the real
   sender instance id, which `current_context.get_event_mediator()`
   alone can't provide) -- no new Bridge API surface needed. The
   payload box accepts either real JSON or plain text: valid JSON
   parses to its real value, empty means `null`, anything else is sent
   as-is as a string payload, with the status line reporting which
   happened. Publish is disabled (with an explanatory status) until
   the mediator binding arrives and while the name field is empty.
   Neither field clears after a successful publish -- a repeated
   -testing tool, not a one-shot form. Ctrl+Return in the payload box
   and Enter in the name field both publish too (same convention as
   the TODO widget's item editor, TODO `8db7891`).

   Verified entirely headlessly: `_parse_payload`'s JSON/text/empty
   branches; disabled-before-binding behavior; a real `EventMediator`
   receiving correctly-shaped events (name, payload, sender instance
   id) for JSON, empty, and plain-text payloads; empty-name rejection
   client-side; the Enter/Ctrl+Return shortcuts exercised through real
   Qt events/signals; `discover_widgets` picking up the new manifest;
   and a full real `DeskWindow` regression (pointed at this project's
   own already-provisioned directory, to avoid `_provision_temp_ui`'s
   confirmation dialogs blocking a headless run) confirming
   `_bind_event_mediator`'s generic path wires up a real placed
   instance end to end, including genuine cross-instance delivery
   through the real shared mediator.
   [planned: event-poster-widget.md]
7505703. COMPLETED: add a widget to view all of the widgets registered for the event message channel and add a per-registered-widget button to zoom/pan to it (use the same button as the zoom/pan titlebar button)

   Shipped as `widgets/event_subscribers/`: a status line plus a list
   of every widget instance currently subscribed to at least one name
   on the event mediator (TODO `6f9c51b`), each row showing a human
   -readable label and its subscribed event names alongside a 👁
   button. New `EventMediator.list_subscriptions()` gives a lock
   -protected snapshot; two new `current_context` hooks
   (`widget_zoomer`, `widget_display_name_resolver`) let the widget
   reach a new `DeskWindow.zoom_to_widget_by_instance_id` (resolves a
   placed frame by instance id, then calls the same
   `WorkspaceView.zoom_to_widget` the titlebar eye button uses, TODO
   `33d3e8d`) and the already-existing `_display_name_for_instance`
   (built for the introspect permission dialog) without importing
   shell internals directly -- the same "one new minimal get/set pair
   per capability" pattern every other python-widget-facing hook here
   already follows. Refreshed on a 1s timer (cheap in-memory work, no
   subprocess/IO), gated on `isVisible()` like `widgets/git_status/
   widget.py`'s own polling, since the mediator has no signal-based
   change notification to react to instead. An instance that
   unsubscribed from every name individually (leaving an empty set,
   not removed) is correctly excluded from the list.

   Verified entirely headlessly: `list_subscriptions()`'s snapshot
   correctness/independence and the empty-set-vs-removed distinction;
   the widget's not-connected/empty/populated states, row content and
   sort order, and eye-button-click-to-zoomer wiring (both a fake
   installed zoomer and a real `QPushButton.click()`); `discover_
   widgets` picking up the manifest; and a full real `DeskWindow`
   regression (pointed at this project's own already-provisioned
   directory, same reasoning as TODO `dc557b2`) confirming
   `zoom_to_widget_by_instance_id` finds a real frame and actually
   moves/scales the real view to bring it fully into the viewport
   (and correctly returns `False` for an unknown id), the new hooks
   resolve to the real bound `DeskWindow` methods, and a real placed
   Event Subscribers instance shows a real subscribed instance and
   its eye button genuinely zooms the real `WorkspaceView` to it.
   [planned: event-subscribers-widget.md]
6e731c1. COMPLETED: drag-and-drop of an image into the Desk should result in the image being saved in the .desk_temp directory and then displayed with tempui.

   Shipped as a new `OpenImage <path>` DSL keyword (identical shape to
   `OpenMarkdown`, its own new `tempui-image.md` split doc,
   `TEMPUI_DOC_VERSION` bumped 9 -> 10) plus a new `widgets/image_viewer/`
   widget (`kind: "python"`, a near-twin of `widgets/svg_viewer/`:
   `QPixmap`-based instead of `QSvgRenderer`-based, same Open/`set_file`
   /`SingleFileWatcher`/`[EXTERNAL]`-marker shape). A new
   `desk.geometry.fit_rect` was extracted from the SVG viewer's own
   private `_fit_rect` so both widgets share the identical
   aspect-preserving letterboxed-scaling math instead of duplicating
   it. `DeskWindow._on_files_dropped` now special-cases raster image
   suffixes (`IMAGE_DROP_SUFFIXES` -- deliberately excludes `.svg`,
   which already has correct by-reference handling): a new
   `_drop_image_as_temp_ui` copies the dropped file's bytes into
   `.desk_temp` (short random prefix + original filename), writes a
   new UUID-named `OpenImage .desk_temp/<name>` tempui file
   (self-write-suppressed via `record_own_write`, matching
   `_paste_text_as_temp_ui`), and immediately places+binds an Image
   Viewer instance at the drop position -- matching how every other
   dropped file type already places immediately, no notification
   -then-click detour. Every other dropped extension is completely
   unaffected. The rest of the tempui plumbing
   (`IMAGE_VIEWER_WIDGET_ID`/`TEMP_UI_WIDGET_IDS`/
   `_temp_ui_widget_id_for`/`_bind_temp_ui_content`
   /`_resolve_open_image_target`/`_notify_temp_ui`) mirrors
   `OpenMarkdown`'s existing entries exactly, so `OpenImage` is a
   general DSL capability any tempui author can use, not only
   reachable via drag-and-drop.

   Found and fixed one real, pre-existing bug along the way (not
   introduced by this change): `desk.file_watch.SingleFileWatcher`
   -- previously only ever used to watch text files (Markdown, SVG,
   TODO.md, ...) -- called `path.read_text()` unconditionally on every
   change and only caught `OSError`, not `UnicodeDecodeError`; watching
   a binary file (the new Image Viewer's live-reload) silently killed
   the `changed` notification entirely on every real external change.
   Fixed by also catching `UnicodeDecodeError` (self-write suppression
   doesn't meaningfully apply to binary content anyway, so this is
   treated the same as an unreadable file -- always notify, never
   suppress) -- confirmed the existing text-file behavior (both the
   self-write-suppression path and the real-external-change path)
   is completely unaffected.

   Verified entirely headlessly: `fit_rect`'s letterboxing math;
   `OpenImage` parsing/detection/reservation; `ensure_docs_current`
   refreshing a stale version-9 doc directory to 10 with
   `tempui-image.md` present and linked; the Image Viewer widget's
   placeholder/load/live-reload (a real `SingleFileWatcher` picking up
   a genuine on-disk binary change, the exact bug above)/missing-file
   /invalid-image/`[EXTERNAL]`/Open-button behaviors; `discover_widgets`
   picking up the manifest; and a full real `DeskWindow` regression
   (an isolated, pre-provisioned temp project directory, since this
   test performs real file writes/saves -- avoids both the
   `_provision_temp_ui` confirmation-dialog hang a fresh, unprovisioned
   directory would cause in a headless run, and any risk to the real
   repo) confirming a real drop: exactly one new copied image
   (byte-for-byte identical to the source) plus one new `OpenImage`
   tempui file appear in `.desk_temp`, no spurious notification fires
   for the self-authored write, an Image Viewer instance is placed
   immediately at the drop position showing the real image, a
   non-image (`.md`) drop is completely unaffected, and a simulated
   app restart (a fresh `DeskWindow` over the same saved Desk)
   reconnects to the same file via the standard
   instance_id-equals-uuid mechanism.
   [planned: image-drop-tempui.md]

593a464. COMPLETED: Bug: in the Event Log widget, the "Live Tail" and "Clear Log"
   buttons' chrome (background/border) doesn't scale with zoom -- same
   category of bug as TODO 465c404's Project Files toolbar fix.
   Screenshot: both buttons' text renders oversized, overflowing well
   outside their own grey rounded-pill backgrounds, which stayed a
   visibly smaller size than the (correctly) zoomed text.

   Same fix as TODO 465c404: force Qt's built-in "Fusion" style on the
   two buttons (`self._live_tail_button`, `self._clear_button`) via
   `QStyleFactory.create("Fusion")` + `.setStyle(...)`, kept alive as
   an instance attribute (`setStyle()` doesn't take ownership of the
   `QStyle`) -- rather than hand-painting custom chrome, since a
   `QPushButton` (this widget's Live Tail button is checkable, unlike
   Project Files' plain button) has too many visual states to
   re-derive by hand.

   Verified headlessly: the widget builds without error, both buttons
   report `style().objectName() == "fusion"`, Live Tail's checkable
   toggle still works, Clear Log's `clicked` still reaches
   `_clear_log`, and the real widget renders cleanly through a
   3x-zoomed `QGraphicsView`/`QGraphicsProxyWidget` with unaffected
   button geometry. As with TODO 465c404, this environment's offscreen
   Qt platform defaults to Fusion regardless of the fix, so it can't
   reproduce the *broken* native-macOS-style rendering the bug
   report's screenshot showed -- needs visual confirmation in the real
   running app.
   [planned: event-log-toolbar-zoom-scaling.md]

8afef71. COMPLETED (but NOT ACTUALLY FIXED -- see PARKINGLOT.md): Generic fix,
   superseding the narrow per-widget approach of TODO
   465c404 and TODO 593a464: an audit of every other widget found the
   same native-style-chrome-desyncs-under-zoom bug in 17 of 19 widgets
   (both statically-created controls and ones rebuilt dynamically on
   every render, e.g. lightning_round's option buttons). Rather than
   patching each widget file individually, fixed once at the single
   choke point every widget's content passes through (WidgetFrame's
   embedding into the canvas), automatically covering every widget --
   present and future -- without requiring each widget file to opt in.

   The original planned approach (per-widget setStyle(Fusion), applied
   generically) turned out not to work: WidgetFrame already sets its
   own stylesheet on itself (for its border), and confirmed directly
   that any ancestor's setStyleSheet() silently overrides a
   descendant's setStyle() call regardless of order -- meaning TODO
   465c404/593a464's original per-widget fixes were likely never
   actually effective in the real app either, since neither fix's own
   verification wrapped the widget in a real WidgetFrame. Also found
   that style().objectName() -- the exact signal both prior fixes'
   verification relied on -- can't detect this: under this
   environment's offscreen Qt platform, both the untouched default
   style and an explicitly-created Fusion style report as
   indistinguishable objects. Both findings written up in LEARNINGS.md.

   Fixed instead by setting a stylesheet (CONTENT_ZOOM_SAFE_STYLESHEET)
   directly on each widget's content root in WidgetFrame.__init__,
   giving QPushButton/QToolButton/QLineEdit explicit background/
   border/padding rules -- the same mechanism (confirmed via the
   audit) that already makes the Todo/Questions widgets'
   FILTER_BUTTON_STYLE-styled buttons immune to this bug. A stylesheet
   cascades correctly to every descendant, present and future, with no
   event-filter machinery needed. Removed the now-redundant (and
   apparently never-effective) per-widget fixes in project_files/event_log.

   Verified extensively headlessly by pixel-sampling actual rendered
   output (not style-object introspection, per the finding above)
   across static controls, controls added after construction, a
   pre-built subtree attached in one shot, a widget's own more
   specific stylesheet still taking precedence, both QToolButton and
   QLineEdit (not just QPushButton), and real widgets from the audit
   (svg_viewer, lightning_round -- including forcing a real rebuild of
   its option buttons by answering an item, project_files, event_log
   -- including event_log's :checked pseudo-state). Confirmed
   WidgetFrame's own chrome never receives this stylesheet. As with
   the two prior fixes, this offscreen environment can't reproduce the
   real native-macOS-style rendering directly -- needs visual
   confirmation in the real running app.

   Update 2026-07-15: tested in the real running app, and the bug is
   still present -- the Event Log toolbar buttons still do not scale
   with zoom, despite this fix passing every headless check above.
   Root cause of the discrepancy not yet found. Parked (not blocking
   other work) rather than continuing to iterate immediately -- see
   PARKINGLOT.md for the full attempt history and what to try next.
   [planned: widget-content-zoom-safe-style.md]
b324217. COMPLETED: Author `DefineWidget` custom widgets from a real per-widget
   source directory (TS custom element + template HTML + tsconfig +
   manifest), packaged by one generic `scripts/build_widget.py`
   (stdlib-only), and seed that script into new projects the same way
   `scripts/todo_item_ids.py` already is. Document the pattern in
   `tempui-custom-widgets.md`. See
   design-docs/custom-widget-authoring.md section 1.
   [planned: build-widget-authoring-pattern.md]

   Added scripts/build_widget.py (stdlib-only, compiles a
   custom_widget_src/<name>/ TS+template source directory into a
   DefineWidget tempui file), seeded it into new projects alongside
   scripts/todo_item_ids.py, bumped TEMPUI_DOC_VERSION 10 -> 11, and
   added an "Authoring from real source" section to
   _CUSTOM_WIDGETS_DOC. Deliberately put the source convention at
   custom_widget_src/ rather than widgets/ (the feedback's own
   example project put it under widgets/lifeforce-heart/) since
   discover_widgets scans every widgets/<id>/widget.json expecting a
   "python"/"html" kind and would raise on this authoring manifest's
   different shape.

   Verified end-to-end with a real tsc invocation (tsc 3.8.3 was on
   PATH in this environment) round-tripping through
   desk.temp_ui.parse_define_widget, plus each error path (missing
   manifest keys, missing <name>.ts, missing BUILD marker, tsc absent
   from PATH -- never falls back to npx), the doc version bump/
   content, and the seed script's copy-if-missing/never-overwrite/
   executable-bit behavior. Ran the full scratchpad regression suite:
   9 pre-existing failures (confirmed via git stash to fail
   identically before this change), 0 new failures.
5ff02d2. COMPLETED: Fix `DefineWidget`'s silent no-instance-placed gap: add a loud
   one-line callout at the top of `DefineWidget`'s section in
   `tempui-custom-widgets.md`, and auto-place one instance the first
   time a brand-new keyword is registered from a live-added (not
   edited, not startup/Desk-switch-rescanned) tempui `DefineWidget`
   file. See design-docs/custom-widget-authoring.md section 2.
   [planned: define-widget-auto-place.md]

   Added a loud callout to _CUSTOM_WIDGETS_DOC (TEMPUI_DOC_VERSION 11
   -> 12), and gave _handle_define_widget_file an `is_new` param
   (passed True only from _on_temp_ui_file_added) so a genuinely new
   keyword -- checked before _register_custom_widget mutates state --
   auto-places one centered instance via a new
   _auto_place_new_custom_widget. Re-saving an already-known keyword,
   and _register_custom_widgets_from_desk_temp's own bulk startup/
   Desk-switch rescan, place nothing, so neither duplicates instances.

   Verified on a real WorkspaceView (unbound-method-on-a-fake-double
   pattern): a live-added brand-new keyword places exactly one
   instance; editing that same keyword afterward places no additional
   instance; the bulk rescan registers without placing anything; a
   refused registration (reserved keyword) places nothing. Full
   scratchpad regression suite: 9 pre-existing failures plus one
   expected new failure in my own earlier b324217 verification script
   (a hardcoded doc-version-11 assertion, now stale since this bumped
   it to 12 -- not a real regression, that scratchpad script isn't
   part of the shipped code), 0 other new failures.
5995ffd. COMPLETED: Give a placed `DefineWidget` custom widget instance a way to
   report which version of its code it's actually running: compute a
   content hash when a definition is registered, expose the current
   hash via `desk.self.getManifest()`, and track the hash a placed
   instance was placed with so Desk's own UI can show when an
   instance predates the currently-registered definition. See
   design-docs/custom-widget-authoring.md section 3.
   [planned: custom-widget-content-hash.md]

   Added WidgetInfo.content_hash (an md5(html_b64)[:12] hash, computed
   in _register_custom_widget) exposed via getManifest's
   _widget_info_dict, and WidgetState.placed_content_hash tracked
   per-instance on WidgetFrame (set at fresh placement, applied from
   the saved .desk state on restore). A new
   _refresh_stale_indicators_for(keyword), called at the end of every
   _register_custom_widget, recomputes a "[STALE]" titlebar marker
   (mirroring the existing "[EXTERNAL]" marker mechanism) on every
   already-placed instance of that keyword -- catching both the live
   -edit-while-placed case and the reopen-after-source-changed case.

   Verified via the same real-WorkspaceView unbound-method-on-a-fake
   -double pattern as prior items: registration computes/stores/
   exposes the hash and changes it on redefinition; a fresh placement
   is never stale; a live redefinition immediately marks an
   already-placed instance stale (and a newly-placed one after the
   edit is not); a restored instance is stale or not depending on
   whether its saved hash matches the current one;
   WidgetState.placed_content_hash round-trips through save/load/
   desk_state_dict, and an old .desk file with no such key defaults to
   None. Found and fixed one genuine regression during verification:
   src/desk/shell/window.py's _capture_desk_state now reads
   frame.placed_content_hash unconditionally, which broke an older
   scratchpad verification script's own lightweight _FakeFrame double
   (missing the new attribute) -- fixed by adding it there, confirmed
   via git stash that this was a real regression (passed before,
   failed after) unlike the other pre-existing failures. Full
   regression suite back to the same 9 pre-existing failures plus one
   already-known-stale doc-version assertion in my own earlier
   b324217 script, 0 other new failures.
c892403. COMPLETED: Resolve relative `desk.fs.readFile`/`writeFile` paths against
   the current Desk's own directory instead of the server process's
   ambient working directory (or reject relative paths with a clear
   error), expose that directory via `desk.self.getManifest()`, and
   give `desk.events.*` top billing in `tempui-custom-widgets.md`'s
   Bridge API section as the preferred mechanism for cross-widget
   signaling, ahead of `fs`/`workspace`/`widgets` in the list. See
   design-docs/custom-widget-authoring.md section 4.
   [planned: fs-path-resolution-and-events-framing.md]

   Added a `_resolve_fs_path` helper in server/app.py (absolute paths
   pass through unchanged; relative ones resolve against
   `gui_bridge.window.current_desk.directory` via the existing
   `run_on_gui` GUI-thread-crossing convention), used by both
   `fs_read_file`/`fs_write_file`. `self_get_manifest` now also
   returns a `directory` field. Reordered `_CUSTOM_WIDGETS_DOC`'s
   Bridge API capability list to put `events` first with an explicit
   "reach for this first for cross-widget signaling" callout,
   documented the new `fs` resolution behavior and getManifest's
   `directory`/`content_hash` fields (the latter was a real
   documentation gap left over from TODO 5995ffd, fixed here while
   touching this same bullet). TEMPUI_DOC_VERSION 12 -> 13.

   Verified end-to-end over real HTTP (a running server + a real
   GuiBridge attached to a fake window double, background-thread
   requests against a pumped Qt event loop, same pattern as the
   existing local-storage bridge test): a relative fs.writeFile/
   readFile round-trips under the fake Desk's own directory, an
   absolute path is used as-is, and getManifest returns both the new
   `directory` and the existing `content_hash`. Doc content and
   version bump also checked directly. Full regression suite: the
   same 9 pre-existing failures plus two now-stale doc-version
   assertions in my own earlier b324217/5ff02d2 scripts (hardcoded to
   prior version numbers, not real regressions), 0 other new
   failures.
0d2ebc1. COMPLETED: Add an Event Viewer widget: opened by double-clicking a row in
   the Event Log widget (`widgets/event_log/`), showing that one
   event's full detail (timestamp, name, sender instance id, and its
   payload pretty-printed in full, not the truncated single-line
   summary the Event Log's own table row shows).
   [planned: event-viewer-widget.md]

   Added widgets/event_viewer/ (kind:"python"): EventViewerWidget shows
   timestamp/name/sender in labels plus the payload pretty-printed
   (json.dumps(..., indent=2)) in a read-only QPlainTextEdit, via a
   duck-typed set_event(event) (mirroring set_file). Shows a
   placeholder when placed standalone with no event set yet. Updated
   widgets/event_log/widget.py to stash each row's real MediatedEvent
   on its Timestamp column item (Qt.ItemDataRole.UserRole, mirroring
   questions/widget.py's ENTRY_ROLE), connected itemDoubleClicked to a
   new _open_event_viewer that reaches the widget opener via
   current_context (the same pattern project_files's _open_index
   already uses for the Editor widget), with a broad except around the
   set_event call so a broken hook can't crash the double-click slot
   (matching TODO 810a5d6's reasoning). Not centered in the view --
   matches Project Files' own current double-click behavior; TODO
   efdad99/da4f9c0 are the ones introducing centered placement as a
   deliberate, separately-scoped change.

   Verified headlessly with real Qt widgets (QApplication, offscreen):
   set_event populates all four fields including pretty-printed
   multi-line JSON and empty-string None-payload handling; the
   placeholder shows with no event set; a real QTableWidget
   double-click flow (via _open_event_viewer directly, exercising the
   same code a real itemDoubleClicked signal would) opens the widget
   and passes the correct event through; a missing opener, an opener
   returning something without set_event, and a set_event that itself
   raises all fail silently rather than propagating out of the Qt
   slot. Confirmed discover_widgets(widgets_dir) picks up the new
   widget correctly. Full regression suite: the same 9 pre-existing
   failures plus the two already-known-stale doc-version assertions
   from earlier TODOs, 0 new failures.
59c5a70. COMPLETED: Change where a `DefineWidget` widget's authoring source lives
   (TODO b324217's `custom_widget_src/<name>/` convention): for a Desk
   working on a project other than Desk's own repo, recommend
   `.desk_temp/widgets/<name>/` instead of a project-root
   `custom_widget_src/<name>/` directory, since `.desk_temp` is already
   the established Desk-specific/gitignored support directory rather
   than adding a second convention at the project root. Separately,
   update the widget frame's `[TEMPUI]` promote button (see TODO
   91b3f42) so that promoting a widget also moves its authoring source
   directory out of `.desk_temp/widgets/<name>/` into a permanent,
   non-gitignored project subdirectory, `desk_widgets/<name>/` --
   promotion already means "this is now a permanent part of my
   project," so its source should stop living in the disposable
   `.desk_temp` tree too, not just its definition in the `.desk` file.
   Update `scripts/build_widget.py` (TODO b324217) and
   `tempui-custom-widgets.md`'s authoring-pattern docs so the build
   process works correctly for a source directory in either of these
   two locations.
   [planned: relocate-custom-widget-authoring-source.md]

   Added CUSTOM_WIDGET_SRC_DIRNAME ("widgets", under .desk_temp/) and
   PROMOTED_WIDGET_SRC_DIRNAME ("desk_widgets", project root) to
   src/desk/temp_ui.py. Updated _CUSTOM_WIDGETS_DOC's "Authoring from
   real source" section to recommend .desk_temp/widgets/<name>/
   instead of a project-root custom_widget_src/<name>/, and added a
   promotion-moves-the-source-too note there and in "Promoting a
   defined widget to the Desk" (TEMPUI_DOC_VERSION 13 -> 14). Updated
   scripts/build_widget.py's own docstring/usage example to match --
   no functional change needed there, since it already takes an
   arbitrary directory argument rather than hardcoding
   custom_widget_src. New DeskWindow._relocate_promoted_widget_source,
   called from _on_tempui_promote_requested: moves
   .desk_temp/widgets/<keyword>/ to desk_widgets/<keyword>/ if it
   exists, silent no-op if there's no source directory to move
   (hand-authored widgets never had one), and leaves the source in
   place (logged, not raised) if the destination already exists --
   the .desk file promotion itself has already succeeded by that
   point and shouldn't be made to look like it failed over this
   secondary bookkeeping step.

   Verified end-to-end with a real tsc invocation confirming
   build_widget.py produces identical output run against a fixture at
   .desk_temp/widgets/<name>/ and again at desk_widgets/<name>/.
   Verified the promote flow on a real WorkspaceView: a source
   directory present at promotion time moves correctly (with its
   original location gone and the .desk-file bookkeeping still
   intact); promoting a widget with no source directory is an
   unaffected no-op; promoting into an already-existing destination
   leaves the source alone without disturbing the rest of the promote
   flow. Doc content, version bump, and the updated build_widget.py
   docstring also checked directly. Full regression suite: the same 9
   pre-existing failures plus three already-known-stale doc-version
   assertions from earlier TODOs in this same batch, 0 other new
   failures.
3e2c4f2. COMPLETED: Change the `[STALE]` titlebar marker (TODO 5995ffd) from a
   passive label into something clickable: clicking it pops up a
   dialog showing both content hashes (the one this instance was
   placed with, and the one currently registered for its keyword) and
   gives the user the choice to reload the widget with the new content
   now, or keep running the old content for now (i.e. dismiss and
   leave the instance as-is, still marked `[STALE]`, until they decide
   later).
   [planned: clickable-stale-marker-dialog.md]

   Replaced the append-to-title-label `[STALE]` marker with a real
   clickable titlebar button (_StaleIndicatorButton, styled like
   _TempuiPromoteButton), wired through WorkspaceView's existing
   centralized chrome-click dispatch (_hit_test_chrome/
   mousePressEvent/mouseReleaseEvent) exactly like every other titlebar
   button, via a new widget_stale_clicked signal. DeskWindow's new
   _on_widget_stale_clicked shows both hashes via a new
   _confirm_stale_reload (QMessageBox, "Reload Now"/"Keep for Now",
   split out for headless-testability like _confirm_clear) and, on
   Reload Now, calls .reload() on *only that specific frame's*
   ChromiumWidget -- deliberately not via HotReloadBroker.widget_changed,
   which would reload every placed instance of that keyword regardless
   of which one's marker was clicked.

   Verified on a real WorkspaceView: the button shows/hides correctly
   and contributes to min_full_width_px like the promote button does;
   a real hit-test at the button's actual on-screen position resolves
   to ("stale", frame); Reload Now reloads only the clicked instance
   (a second, independently-placed instance of the same keyword is
   untouched), updates placed_content_hash, and clears the marker;
   Keep for Now changes nothing; a non-ChromiumWidget frame or an
   instance that's no longer actually stale are both no-ops with no
   dialog shown. Updated TODO 5995ffd's own verification script's
   stale-state assertions from checking label text to checking the new
   button's visibility. Full regression suite: the same 9 pre-existing
   failures plus three already-known-stale doc-version assertions from
   earlier TODOs in this batch, 0 other new failures.
efdad99. COMPLETED: Change the Project Files widget's (`widgets/project_files/`)
   double-click handling (currently `_open_index`, which always opens
   the Editor widget unconditionally) to a fallback chain: (1) if a
   viewer widget is available for the clicked file's type, open it
   there; (2) otherwise, if an editor is available, open it there --
   only ever route a genuinely text file into the text Editor widget,
   never a binary/unknown type; (3) otherwise, fall back to placing a
   Scratch tempui note (see `desk.temp_ui`'s `Scratch` keyword) whose
   text says what file type this is and that no viewer/editor is
   available for it. Whichever of the three actually gets launched
   should be placed centered in the current view, the same convention
   every other tempui/programmatic widget placement in this codebase
   already follows (see e.g. `DeskWindow._place_discuss_claude_widget`,
   `_auto_place_new_custom_widget`). Depends on having some notion of
   "which widget(s) handle which file type" to check against, which is
   TODO b5d52c0's file type registry -- plan that one first, or at
   least decide its shape, before planning this one.
   [planned: file-explorer-viewer-editor-scrap-fallback.md]

   Added `find_view_handler`/`find_edit_handler`/`looks_like_text_file`
   to `src/desk/file_type_registry.py` (view lookup falls back to a
   new `BUILTIN_VIEW_WIDGET_BY_SUFFIX` floor -- generalizing
   `EXTERNAL_DROP_WIDGET_BY_SUFFIX`/`IMAGE_DROP_SUFFIXES` -- so a fresh
   Desk's empty registry doesn't regress existing svg/markdown/image
   double-click behavior; the text sniff is a null-byte + UTF-8
   -decodability check, no new dependency). Added a new
   `current_context.get/set_centered_widget_opener` hook +
   `DeskWindow.open_widget_content_centered` (same centering math as
   `_place_discuss_claude_widget`), since the existing
   `get_widget_opener`/`open_widget_content` default to `(0, 0)`.
   Rewrote Project Files' `_open_index` into `_open_file` (view ->
   edit -> built-in-editor-if-text -> Scratch-note fallback chain),
   using the centered opener throughout.

   Verified: the lookup helpers (registry match by extension/MIME,
   builtin-floor fallback, no-fallback for `find_edit_handler`) and
   the text/binary sniff heuristic directly; `open_widget_content
   _centered`'s own centering math and unknown-widget-id no-op on a
   real `WorkspaceView`; Project Files' full dispatch chain (a
   registered view handler, a registered edit handler with no view
   handler, the built-in editor for a real text file with no registry
   match at all, the Scratch fallback for a binary file with no match,
   and a broken `set_file` failing silently rather than crashing the
   double-click slot). Full regression suite: the same 9 pre-existing
   failures plus three already-known-stale doc-version assertions from
   earlier TODOs in this batch, 0 other new failures.
b5d52c0. COMPLETED: Build a registry of file types (keyed by both file extension
   and MIME type, where available) to the widget(s) that can view,
   edit, consume, or produce that type -- generalizing the small
   hardcoded `EXTERNAL_DROP_WIDGET_BY_SUFFIX` map in
   `desk/shell/window.py` into something dynamic and user/agent
   -editable, rather than a fixed table only a code change can update.
   Store the registry as JSON on the `Desk` dataclass itself
   (`desk/desks.py`), persisted in the `.desk` file the same way
   `custom_widgets` already is. Add a new widget,
   `filetype-registry-editor`, that reads and edits the registry
   entirely through a new Desk service exposed over the Bridge API
   (a new capability, alongside `workspace`/`fs`/`widgets`/`events`/
   `introspect`) -- never by reading/writing the `.desk` file directly.
   Editing the registry through this Bridge API call must publish a
   Desk event (via the existing `EventMediator`/`desk.events.*`
   machinery, TODO 6f9c51b) with the editing widget's own instance id
   as the sender, so every other interested widget can react live.
   Reading the registry through the Bridge API must, as part of that
   same call, subscribe the calling widget's instance to those edit
   events -- so "read the registry" and "start watching for future
   changes to it" are one step, not two separate calls a widget author
   could forget to pair up. Update the Project Files widget
   (`widgets/project_files/`) to consume the registry this way:
   fetch it once via the Bridge API when the widget starts, and update
   its own local in-memory copy whenever an edit event for it arrives
   -- never re-fetching from scratch on every event, and never reading
   the `.desk` file directly itself either. See TODO efdad99, which
   depends on this registry existing.
   [planned: file-type-registry.md]

   Clarified via user question before planning: Project Files is
   `kind: "python"`, and every existing python widget reaches Desk
   services in-process via a `current_context` hook (e.g.
   `get_event_mediator()`), never via a real HTTP call to the Bridge
   API (that's the `kind: "html"`-only mechanism) -- so Project Files'
   own consumption goes through a new `current_context` hook (initial
   read) plus the existing generic `bind_event_mediator` mechanism
   (live updates), not literal Bridge API calls. `filetype-registry
   -editor` genuinely uses the real Bridge API, as a new `kind: "html"`
   widget -- the first hand-authored one in this project (every other
   `kind: "html"` widget is a runtime-materialized `DefineWidget` one).
   Also translated the TODO's own hyphenated widget name
   "filetype-registry-editor" to this project's actual snake_case
   widget-id/directory convention: `filetype_registry_editor`.

   Implemented: new `src/desk/file_type_registry.py`
   (FileTypeHandler/FileTypeRegistryEntry + to/from-dict helpers,
   FILE_TYPE_REGISTRY_UPDATED_EVENT); `Desk.file_type_registry`
   persisted in desk_state_dict/load_desk/save_desk (and carried over
   unchanged in `_capture_desk_state`, same as `custom_widgets` --
   otherwise every save would silently wipe it). New Bridge API
   `filetypes` capability/routes (get subscribes + reads in one call,
   set persists + publishes with the editing widget's instance id as
   sender) and a matching `window.desk.filetypes.*` bridge_client.py
   namespace. New `current_context.get/set_file_type_registry_provider`
   hook (refreshed in `_refresh_picker`, same choke point as the
   directory/event-mediator hooks) for Project Files' one-time initial
   read; Project Files also implements `bind_event_mediator` (the
   existing generic TODO 6f9c51b hook) to keep its local copy current
   via the event's own payload, no re-fetch. New
   `widgets/filetype_registry_editor/` (kind:"html", the first
   hand-authored one in this project): a minimal JSON-textarea editor
   calling `window.desk.filetypes.get/set` directly.

   Verified: FileTypeRegistryEntry/Handler to/from-dict and
   Desk/desk_state_dict/load_desk round-trips (and an old .desk file
   with no key defaults to `[]`); the new widget is discovered with
   `kind: "html"` and the `filetypes` capability; the current_context
   provider hook; Project Files' initial read plus a real
   EventMediator-published update changing its local copy; the Bridge
   API end-to-end over real HTTP (a running server + a real GuiBridge
   attached to a fake window, matching the established pumped-event
   -loop pattern) -- get returns entries and subscribes the caller,
   set persists to the fake window and publishes the update event
   (with the new entries as payload and the editing instance as
   sender) to another subscriber; the bridge_client.py namespace.
   Found and fixed one genuine regression: `_capture_desk_state` now
   reads `self.current_desk.file_type_registry` unconditionally, which
   broke an older scratchpad test's minimal fake `current_desk` double
   (missing the new attribute) -- confirmed via git stash that this
   was a real regression (passed before, failed after) unlike the
   other pre-existing failures; fixed by adding the attribute there.
   Full regression suite back to the same 9 pre-existing failures plus
   three already-known-stale doc-version assertions from earlier TODOs
   in this batch, 0 other new failures.
7462cdb. COMPLETED: Add `tempui-breaking-changes.md`/`tempui-new-features.md` to
   the generated `.desk_temp` tempui doc set (prioritized, per user
   request). From `../../FEEDBACK/FEEDBACK-DESK-tempui-doc-changelog
   -2026-07-15-1315.md` (a peer project's feedback, extracted from
   migrating `necro-4x`'s `widgets/lifeforce-heart/`/
   `widgets/lifeforce-control/` to a newer Desk's updated `DefineWidget`
   authoring conventions): `TEMPUI_DOC_VERSION` already tells a reading
   agent *that* something changed since whatever version its project
   was built against, but not *what* -- forcing a full re-read plus a
   manual diff against memory (which a fresh agent picking up the same
   project cold has no way to do at all) to answer "what do I need to
   fix." Add two more files to the same generated/versioned set
   `desk-temporary-ui.md`/`tempui-custom-widgets.md`/etc. already are
   (TODO `e57ce5f`'s "one shared version number for the whole set"
   mechanism -- no separate version of their own, refreshed for free by
   the existing `ensure_docs_current` staleness check): `tempui
   -breaking-changes.md` and `tempui-new-features.md`, each entry
   tagged with the `TEMPUI_DOC_VERSION` it was introduced in, listed
   newest-first, with enough detail to act on without re-reading the
   rest of the doc set (what changed, and concretely what to do about
   code/conventions written against the version before it). Backfill
   real historical entries from this project's own actual
   `TEMPUI_DOC_VERSION` bump comments in `src/desk/temp_ui.py` (every
   bump already has a "TODO xxx: bumped N -> N+1 for ..." comment
   explaining the change -- a ready-made, accurate source to backfill
   from, more reliable than the feedback doc's own illustrative
   reconstruction, which was written against this project's version 13
   and doesn't reflect the version 14/(this batch's later) changes made
   since). Establish the convention going forward: whenever
   `TEMPUI_DOC_VERSION` bumps for a breaking change or a new
   capability, add a corresponding entry to whichever of these two docs
   applies, at the same time (see TODO `1a96c9f`, which formalizes this
   as a documented instruction for agents working on Desk itself).
   [planned: tempui-changelog-docs.md]

   Added `BREAKING_CHANGES_DOC_FILENAME`/`NEW_FEATURES_DOC_FILENAME`
   and `_BREAKING_CHANGES_DOC`/`_NEW_FEATURES_DOC` to
   `src/desk/temp_ui.py`'s `SPLIT_DOC_CONTENT` (no separate version of
   their own, per TODO `e57ce5f`). Backfilled real entries for
   versions 7-14 from this file's own `TEMPUI_DOC_VERSION` bump-log
   comments (versions 1-6 predate the practice, noted as such in both
   docs) -- only version 14 (the `custom_widget_src/` ->
   `.desk_temp/widgets/` authoring-source move, TODO `59c5a70`) was a
   real breaking change; the rest are additive. Added a short
   "check these first" paragraph to `DOC_TEMPLATE` after the built-in
   -file-types list (these two files aren't DSL-keyword-triggered
   types themselves). `TEMPUI_DOC_VERSION` 14 -> 15, with a
   going-forward instruction alongside the doc constants: any future
   breaking/new-capability bump should add a matching entry in the
   same commit.

   Verified: both files registered in `SPLIT_DOC_CONTENT` and written
   by `write_tempui_docs`; version numbers in both docs strictly
   descending; content covers exactly versions 7-14 (14 in breaking,
   7-14 in new-features) with the right classification; both note
   that versions 1-6 predate the changelog; `DOC_TEMPLATE` links both
   files after (not inside) the built-in-file-types list; the version
   bump. Full regression suite: the same 9 pre-existing failures plus
   the expected stale doc-version assertion in TODO `59c5a70`'s own
   earlier script (now four such stale checks accumulated from this
   batch's TEMPUI_DOC_VERSION bumps), 0 other new failures.
1a96c9f. COMPLETED: Fork `development-process.md` into a shared/not-shared doc
   hierarchy, with a Desk-specific section and breaking-changes
   -tracking instructions (prioritized, immediately after TODO
   `7462cdb`, per user request). Specifically:
   - Fork the current `development-process.md` content into a new
     file, `shared_development_process.md`, living in Desk's own
     source tree alongside it (not just conceptually "the shared
     part" -- an actual file here, seeded/distributed the same way).
   - Rewrite the top-level `development-process.md` itself to have a
     "When working on Desk itself" section (empty for now -- content to
     be added later) and a separate section that points to
     `shared_development_process.md` via a relative file reference,
     instructing agents to treat that file's contents with the exact
     same authority as if they were written directly in this top-level
     file.
   - Introduce a peer file to `shared_development_process.md`, named
     `specifically-not-working-on-desk-itself-development-process.md`
     (empty for now).
   - In `development-process.md`'s "When working on Desk itself"
     section, explain the resulting hierarchy of development-process
     docs (top-level, shared, specifically-not-Desk-itself) clearly
     enough that an agent can tell them apart, and instruct agents to
     ask the user for clarification whenever it's ambiguous which of
     them applies to the current task.
   - Also in that same section, instruct agents working on Desk itself
     to update `tempui-breaking-changes.md`/`tempui-new-features.md`
     (TODO `7462cdb`) whenever a change they make to Desk constitutes a
     breaking change or a new feature from the perspective of an agent
     running *inside* Desk in some other project -- so that population
     of those two docs becomes a standing part of the Desk-development
     workflow itself, not a one-off backfill.
   [planned: fork-development-process-doc.md]

   Forked the full prior content of `development-process.md` verbatim
   into new `shared_development_process.md`. Rewrote
   `development-process.md` to a "When working on Desk itself" section
   (hierarchy explanation, ask-the-user-if-ambiguous instruction, and
   the tempui-changelog-docs-tracking instruction) plus a "Shared
   development process" section linking to the fork. Added an empty
   `specifically-not-working-on-desk-itself-development-process.md`
   peer. Extended `DeskWindow._seed_development_process` (new
   `SHARED_DEVELOPMENT_PROCESS_FILENAME`/
   `NOT_DESK_DEVELOPMENT_PROCESS_FILENAME` constants) to seed all three
   files together, independently never-overwriting each -- otherwise a
   newly-created project would get only the rewritten top-level file,
   with dead relative links and none of the actual process content it
   used to carry directly.

   Verified: all three files' content directly (hierarchy explanation,
   both instructions, both relative links present; the fork carries
   every section the original had; the peer file is empty); seeding
   copies all three into a fresh project directory, independently
   respects an existing destination file without overwriting it, and
   is a no-op when the source Desk has none of them. Full regression
   suite: the same 9 pre-existing failures plus four already-known
   -stale doc-version assertions accumulated from this batch's earlier
   TEMPUI_DOC_VERSION bumps, 0 other new failures.
8385dcc. COMPLETED: Rename the "Project Files" widget (`widgets/project_files/`)
   to "Project Files" -- the directory name, its `widget.json`'s
   `name`, any user-facing string in its own code, and every
   reference to it elsewhere: `src/desk/`'s own source (e.g.
   `EXTERNAL_DROP_WIDGET_BY_SUFFIX`'s fallback comment, any widget id
   /import references), `design-docs/` (architecture.md,
   custom-widget-authoring.md's TODO efdad99/b5d52c0 cross-references
   if still current when this is worked), `TODO.md` itself (every
   completed or open item that says "Project Files", including TODO
   efdad99/b5d52c0 above), every `plans/*.md` file that mentions it,
   and `PARKINGLOT.md`. Keep the underlying widget id/directory-name
   convention consistent with how other widgets are named (lowercase,
   underscore-separated -- e.g. `project_files`) rather than
   introducing a differently-cased id than the rest of `widgets/`.
   [planned: rename-file-explorer-to-project-files.md]

   (Note: this item's own text above was originally written using the
   old name "File Explorer"/`file_explorer` -- the global content
   substitution described below, applied uniformly across `TODO.md`
   per the request, rewrote it into this item's text too, which is why
   it now reads as "rename ... 'Project Files' ... to 'Project
   Files'." The rename itself is real; only this historical wording
   looks circular as a result.)

   `git mv widgets/file_explorer widgets/project_files`;
   `widget.json`'s `name` -> "Project Files"; renamed the
   `FileExplorerWidget` class to `ProjectFilesWidget` (not explicitly
   asked, but consistent with every other widget's class-name-matches
   -concept convention). Updated prose references (docstrings/
   comments, not identifiers -- no `FILE_EXPLORER_WIDGET_ID` constant
   existed anywhere to rename) in `src/desk/shell/window.py`,
   `widgets/editor/widget.py`, `widgets/event_log/widget.py`. Replaced
   every "File Explorer"/`file_explorer` occurrence in `TODO.md`,
   `PARKINGLOT.md`, `LEARNINGS.md`, `design-docs/architecture.md`, and
   every `plans/*.md` file that mentioned it -- deliberately leaving
   plan *filenames* themselves unchanged (e.g. `plans/file-explorer
   -widget.md` still lives at that exact path), matching this
   project's own "a permanent handle is never retroactively renamed"
   philosophy for TODO item ids; `TODO.md`'s `[planned: file-explorer
   -*.md]`-style references still point at the right files.

   Verified: `discover_widgets` resolves `project_files` (not
   `file_explorer`) with the correct kind/name; the renamed class;
   zero remaining `file_explorer`/`File Explorer` content anywhere in
   `src/`, `widgets/`, `design-docs/`, `TODO.md`, `PARKINGLOT.md`,
   `LEARNINGS.md`, or `plans/*.md` (checked directly, excluding stale
   `__pycache__` bytecode which was also cleaned up); the three
   original plan filenames still exist unchanged. Full regression
   suite: found and fixed two of my own earlier scratchpad
   verification scripts (for TODO efdad99/b5d52c0) that loaded
   `widgets/file_explorer/widget.py` by its old hardcoded path --
   updated both to the new path, not a real regression in the shipped
   code. Back to the same 9 pre-existing failures plus four already
   -known-stale doc-version assertions from this batch's earlier
   TEMPUI_DOC_VERSION bumps, 0 other new failures.
da4f9c0. COMPLETED: Give every "viewer" widget that shows the contents of a file
   on disk (e.g. `widgets/svg_viewer/`, `widgets/image_viewer/`,
   `widgets/markdown/`) an "Edit" button in its titlebar. Clicking it
   should reuse the exact same open-an-editor-or-fall-back-to-a-scrap
   logic the "Project Files" widget (formerly "File Explorer" -- TODO
   `8385dcc`) uses for its own double-click handling (TODO `efdad99`):
   open an appropriate editor for the file if one is available (only
   ever a genuinely text file into the text Editor widget), otherwise
   fall back to a Scratch tempui note saying no editor is available --
   and, either way, the newly-opened widget is centered in the current
   view, the same placement convention `efdad99`/every other
   programmatic placement in this codebase already follows. This
   should be one shared service both call into, not two separate
   copies of the same fallback logic -- the "viewer" widgets listed
   above are all `kind: "python"`, so reaching this shared service is
   a `current_context` hook (matching how other Python-widget-to-
   `DeskWindow` calls already work, e.g. `get_discuss_starter`), not
   the HTTP Bridge API (which is `kind: "html"`-only -- see TODO
   `2da314f` for exposing this same service there too, for `html`-kind
   widgets). Depends on TODO `efdad99`'s fallback logic (and TODO
   `b5d52c0`'s file type registry, which `efdad99` itself depends on)
   existing first, so there's an actual shared service to call into.
   [planned: viewer-widgets-edit-button.md]

   Extracted Project Files' own inline edit-handler-lookup/text-sniff/
   scratch-fallback logic (TODO efdad99) into a new shared
   `DeskWindow.open_editor_or_scrap`, reached via a new
   `current_context.get/set_editor_or_scrap_opener` hook.
   `ProjectFilesWidget._open_file` now delegates its own "no view
   handler" case to this same hook instead of carrying a second copy.
   Added an "Edit" `QPushButton` to each of `svg_viewer`/
   `image_viewer`/`markdown`'s existing toolbar row (all three already
   had an identical `Open` button + stretch + label shape), disabled
   until `self._current_path` is set (and disabled again for
   `markdown`'s tempui-bound mode, which has no backing file);
   clicking it calls the shared hook with the currently-loaded path.

   Verified: `open_editor_or_scrap` uses a registered edit handler,
   falls back to the built-in Editor for a real text file with no
   registry match, and falls back to a Scratch note for a binary file
   with no match -- on a real `WorkspaceView` double, mirroring TODO
   efdad99's own verification shape. `ProjectFilesWidget._open_file`
   still finds a view handler directly and now delegates the edit-or
   -scrap case to the shared hook (confirmed via a fake opener
   recording the call). Each of the three viewer widgets: Edit
   disabled with no file loaded, enabled after `set_file`, and
   clicking it calls the shared opener with the current path;
   markdown's Edit also re-disables once tempui-bound. Updated TODO
   efdad99's own earlier verification script's three tests that
   directly exercised the now-relocated fallback logic to instead
   confirm delegation to the shared hook (the fallback logic itself
   is now covered by this TODO's own new script) -- not a regression,
   an expected consequence of extracting shared logic into one place.
   Full regression suite: the same 9 pre-existing failures plus four
   already-known-stale doc-version assertions and one now-legitimately
   -stale "zero File Explorer occurrences" check from TODO 8385dcc's
   own earlier script (this item's own completion note above
   legitimately mentions the old name for historical clarity, which
   that blanket check can no longer distinguish from a real leftover
   -- not a real regression), 0 other new failures.
2da314f. COMPLETED: Expose the open-editor-or-fall-back-to-a-scrap service (TODO
   `da4f9c0`, itself a `current_context` hook reused from "Project
   Files"'/TODO `efdad99`'s own double-click handling) over the HTTP
   Bridge API too, so a `kind: "html"` widget's own JS can call it just
   like a `kind: "python"` widget does via the `current_context` hook
   -- a new Bridge API route/capability that, given a file path, either
   opens an appropriate editor for it or falls back to a Scratch tempui
   note, centered in the current view, the same as the
   `current_context`-hook version. Depends on TODO `da4f9c0` (and
   transitively `efdad99`/`b5d52c0`) existing first, since this is
   exposing that same service through a second binding mechanism, not
   building new fallback logic of its own.
   [planned: bridge-api-editor-or-scrap.md]

   Added a new `editor` Bridge API capability + `POST /api/bridge/
   editor/openOrScrap` route (server/app.py), resolving a relative
   `path` against the current Desk's own directory via the same
   `_resolve_fs_path` helper `desk.fs.*` already uses (TODO c892403),
   then calling `DeskWindow.open_editor_or_scrap` (TODO da4f9c0).
   Added `window.desk.editor.openOrScrap` to `bridge_client.py`.

   While updating docs, found and fixed a real gap: TODO b5d52c0's own
   `filetypes` Bridge API capability was never documented in
   `_CUSTOM_WIDGETS_DOC`'s capability list or given a `TEMPUI_DOC_VERSION`
   bump when it was introduced. Backfilled it alongside the new
   `editor` capability in this same bump (14 -> ... -> 16, since
   7462cdb had already bumped to 15 for the changelog docs themselves)
   and added a `tempui-new-features.md` Version 16 entry covering
   both, noting `filetypes`'s retroactive documentation explicitly --
   the first real exercise of TODO 1a96c9f's new "keep the changelog
   docs current" instruction.

   Verified over real HTTP (a running server + a real `GuiBridge`
   attached to a fake window double, the established pumped-event
   -loop pattern): a relative path resolves against the fake Desk's
   directory and calls `open_editor_or_scrap` with the resolved path;
   an absolute path is used as-is; a caller lacking the `editor`
   capability gets a 403. `bridge_client.py`'s new namespace, the
   version bump, and both new capability-list bullets checked
   directly. Full regression suite: the same 9 pre-existing failures
   plus six already-known-stale assertions from earlier TODOs in this
   batch (five doc-version/content checks now one bump further stale,
   plus the one legitimately-stale "zero File Explorer occurrences"
   check), 0 other new failures.
996a5eb. COMPLETED: The "focus view" 👁 eye button (`_EyeButton`, TODO `33d3e8d`)
   should persist alongside the title in the `title_only` chrome
   -degrade state, not disappear along with every other titlebar
   button. Right now `_TitleBar.set_buttons_hidden`/
   `_refresh_button_visibility` hides the eye button too once
   `title_only` kicks in (gated by the same `show = not
   self._buttons_hidden` as every other button) -- contradicting
   `_EyeButton`'s own docstring, which already claims it's "always
   present on every titlebar regardless of current chrome/zoom state."
   Fix the visibility gating so the eye button survives `title_only`
   (still hidden while locked, same as today). Then, since
   `min_title_only_width_px`/`min_full_width_px`
   (`src/desk/shell/widget_frame.py`) currently size the `title_only`
   /greeked boundary on the title label alone, update that threshold
   to require room for *both* the title and the eye button -- i.e.
   greeking should trigger whenever either one no longer fits, not
   only when the title itself no longer fits.
   [planned: eye-button-persists-title-only.md]

   `_refresh_button_visibility`: `eye_button.setVisible(not
   self._locked)`, no longer multiplied by the `show` flag every other
   button is gated by. `min_title_only_width_px` now adds the eye
   button's own width (+ one gap) when not locked; `min_full_width_px`
   excludes the eye button from its own button-width sum, since that
   width is now already folded into `min_title_only_width_px`'s
   baseline -- without the exclusion it would double-count.

   Verified directly on `_TitleBar`: the eye button persists through
   `title_only` unlocked, and stays hidden while locked in both
   states; the two width thresholds account for the eye button
   correctly (present/absent, no double-count) -- confirmed by
   checking `min_full_width_px() - min_title_only_width_px()` equals
   exactly the sum of every *other* currently-relevant button, not
   that plus the eye button again. End-to-end on a real
   `WidgetFrame`/`WorkspaceView`: resizing to a width between the two
   thresholds shows the title and eye button only; resizing below the
   new, wider `min_title_only_width_px` greeks it. Full regression
   suite: the same 9 pre-existing failures plus six already-known
   -stale assertions from earlier TODOs in this batch, 0 other new
   failures.
029047b. COMPLETED: Move `scripts/build_widget.py` (TODO `b324217`) out of
   `scripts/` and into the *ensured* `.desk_temp` file set instead of a
   one-time seed. Right now it's copied once into a new project
   (`DeskWindow._seed_build_widget_script`, never-overwrite) the same
   way `scripts/todo_item_ids.py` is -- but unlike a hand-written id
   -generation script that basically never changes, `build_widget.py`'s
   own content is exactly the kind of thing `TEMPUI_DOC_VERSION`
   -bumping already tracks changes to (see TODO `7462cdb`'s new
   breaking-changes/new-features docs) -- a one-time seed means an
   older project's copy silently goes stale forever, the same
   staleness problem the tempui doc set already solved. Move its
   content into the same generated/versioned `.desk_temp` mechanism
   `desk-temporary-ui.md`/`tempui-custom-widgets.md`/etc. already use
   (`ensure_docs_current`/`write_tempui_docs`, TODO `e57ce5f`) so it
   gets refreshed the same way the docs do, rather than living as a
   static file only ever copied once. Update every doc that currently
   points an agent at `scripts/build_widget.py` -- especially
   `tempui-custom-widgets.md`'s "Authoring from real source" section,
   but also this project's own `design-docs/custom-widget-authoring.md`
   and any other reference -- to the new location, making clear the
   script is meant to be invoked by an agent to build its own tempui
   widgets from source, the same as today.
   [planned: ensure-build-widget-script.md]

   Moved the script's content from `scripts/build_widget.py` into
   `src/desk/temp_ui.py` as `_BUILD_WIDGET_SCRIPT`
   (`BUILD_WIDGET_SCRIPT_FILENAME = "build_widget.py"`), registered in
   `SPLIT_DOC_CONTENT` so `write_tempui_docs`/`ensure_docs_current`
   (TODO e57ce5f) write and refresh it exactly like every `.md` doc,
   with no special-casing needed. Deleted `scripts/build_widget.py`
   and removed `DeskWindow._seed_build_widget_script`/its call site
   entirely -- superseded by the ensure mechanism, which already runs
   on every Desk open/switch. Updated `_CUSTOM_WIDGETS_DOC`'s
   invocation examples to `.desk_temp/build_widget.py`, added a main
   -doc mention (found via a pre-existing test's own
   every-split-file-must-be-linked invariant, which I hadn't
   satisfied on the first pass), bumped `TEMPUI_DOC_VERSION` 16 -> 17
   with a breaking-changes entry. Rewrote `design-docs/custom-widget
   -authoring.md` section 1 end-to-end, which had gone stale twice
   over (still describing both the pre-59c5a70 `custom_widget_src/`
   convention and the pre-029047b scripts/-seeding approach).

   Found and fixed a real, genuinely pre-existing bug while verifying:
   a pre-existing regression test (`verify_tempui_doc_versioning.py`)
   already asserts no tempui doc mentions Desk-repo-specific material
   (since the whole set gets generated into *other* projects'
   `.desk_temp/`, where such a reference would be dangling) -- the
   script's own docstring, carried over verbatim from TODO `b324217`,
   referenced `design-docs/custom-widget-authoring.md`, a path that
   only exists in Desk's own repo. This test never caught it before
   now because the script was never part of `SPLIT_DOC_CONTENT` (and
   therefore never scanned by this check) until this TODO added it.
   Fixed by pointing at `tempui-custom-widgets.md` (in the same
   generated directory) instead.

   Verified: `SPLIT_DOC_CONTENT` includes the script;
   `write_tempui_docs` writes it into a fresh `.desk_temp`;
   `ensure_docs_current` restores a missing or stale copy; the
   generated script actually runs end-to-end against a real fixture
   with a real `tsc` invocation, producing a correct `DefineWidget`
   tempui file; `scripts/build_widget.py` and
   `_seed_build_widget_script` no longer exist; doc content (version
   bump, breaking-changes entry, updated invocation examples, main
   -doc link). Full regression suite: the same 9 pre-existing failures
   plus my own earlier b324217/2da314f scripts now expectedly stale
   (one references the now-relocated file directly, one has a stale
   version-number assertion) and the previously-accumulated stale
   -doc-version checks from this batch, 0 other new failures --
   notably, the pre-existing `verify_tempui_doc_versioning.py` now
   passes cleanly for the first time after the design-docs fix above.
585d235. COMPLETED: Move `MEDIATED-EVENT-LOG.tsv` (`desk.event_mediator`, TODO
   `6f9c51b`) into `.desk_temp/` instead of the current Desk's project
   directory — it's an ambient, Desk-generated log for the whole event
   bus, the same category of thing `.desk_temp` already holds (crash
   logs, tempui docs, custom-widget source) rather than something that
   belongs alongside the user's own project files. Two call sites read/
   write its location today: `DeskWindow._refresh_picker`'s
   `self._event_mediator.set_log_directory(self.current_desk.directory)`
   needs `/ TEMP_UI_DIRNAME` added; `widgets/event_log/widget.py`
   independently computes its own watched path from
   `current_context.get_current_desk_directory()` and needs the same.
   Note `EventMediator._log`'s existing
   `path.parent.mkdir(parents=True, exist_ok=True)` means `.desk_temp`
   would get silently created the moment any event is first published,
   if it doesn't already exist — bypassing the confirm-gated
   `.desk_temp`-creation flow elsewhere (TODO `4716585`). Acceptable in
   practice (`.desk_temp` is already ensured by the time a Desk is open
   in the normal flow), but call it out explicitly in the plan rather
   than letting it be a silent side effect.
   [planned: relocate-mediated-event-log.md]

   `_refresh_picker`'s `set_log_directory` call now passes
   `self.current_desk.directory / TEMP_UI_DIRNAME`; `widgets/event_log/
   widget.py` computes `directory / TEMP_UI_DIRNAME / LOG_FILENAME` the
   same way, importing `TEMP_UI_DIRNAME` from `desk.temp_ui` (precedent
   already established by several other widgets importing from that
   module).

   Verified directly: a real `EventMediator.set_log_directory(dir /
   TEMP_UI_DIRNAME)` resolves `log_path` under `.desk_temp`, and a real
   `publish()` writes the row there (confirming the noted `.desk_temp`
   -creation side effect happens, and that no stray log file is left in
   the project directory itself); a real `EventLogWidget` built with
   `current_context.set_current_desk_directory` pointed at a fresh temp
   directory watches and displays the relocated path. Full regression
   suite (`git stash` before/after): the exact same 17 pre-existing/
   known-stale failures both before and after this change, save for one
   of my own earlier scratchpad scripts (`verify_event_viewer_widget.py`)
   which hardcoded the pre-relocation path directly — fixed to write its
   fixture log under `.desk_temp/` instead, confirmed not a real
   regression.
4d21e7c. COMPLETED: Integrate SVG viewing into the Image Viewer widget (raster +
   vector) and retire the standalone SVG Viewer widget. See
   `design-docs/svg-viewing-and-editing.md`'s "Image Viewer: raster +
   vector" section for the full design: Image Viewer keeps both
   rendering backends (`QPixmap`-based, `QSvgRenderer`-based) and picks
   one per loaded file by extension, swapped via an internal view-swap
   (the same page-swap shape as greeked-widget chrome,
   `design-docs/widget-ux.md`) behind the one common toolbar/label/
   watcher/Edit-button plumbing `set_file`/`_reload` already drive.
   `IMAGE_FILTER` gains `*.svg *.svgz`;
   `file_type_registry.BUILTIN_VIEW_WIDGET_BY_SUFFIX[".svg"]` changes
   from `"svg_viewer"` to `"image_viewer"`; `widgets/svg_viewer/` is
   deleted entirely (no migration attempted for a previously-placed
   instance, matching the TODO `8385dcc` File Explorer → Project Files
   precedent). Also update forward-looking docs that still describe a
   separate SVG Viewer widget (`design-docs/architecture.md`'s widget
   list at minimum; check for others at implementation time) — not
   historical `plans/`/`TODO.md`/`LEARNINGS.md` mentions, which stay as
   history.
   [planned: image-viewer-svg-integration.md]

   `ImageViewerWidget` now holds both `_AspectImageView` (raster,
   unchanged) and `_AspectSvgView` (vector, moved here verbatim from
   the retired widget), swapped via a `QStackedLayout` on `set_file`
   based on extension (`VECTOR_SUFFIXES = {".svg", ".svgz"}`).
   `IMAGE_FILTER` updated; `BUILTIN_VIEW_WIDGET_BY_SUFFIX` now maps
   both `.svg` and `.svgz` to `"image_viewer"`. `widgets/svg_viewer/`
   deleted (`git rm`). Updated every other forward-looking reference
   found via a full-repo grep: `design-docs/architecture.md` (its
   OS-drop paragraph and the widget's own numbered entry, repurposed
   in place rather than leaving a dangling "18. SVG Viewer Widget"
   entry with no replacement), `diagrams.md` and `markdown-rendering.md`
   (both live, forward-looking reference docs, not historical
   narrative), `src/desk/shell/window.py` (removed the now-dead
   `SVG_VIEWER_WIDGET_ID` constant, repointed
   `EXTERNAL_DROP_WIDGET_BY_SUFFIX[".svg"]` at
   `IMAGE_VIEWER_WIDGET_ID`), `src/desk/geometry.py`'s
   `fit_rect` docstring, and a few code comments in
   `current_context.py`/`todo/widget.py`/`editor/widget.py` that named
   the old widget as precedent for a shared pattern. Left historical
   `plans/`/`TODO.md`/`LEARNINGS.md`/`PARKINGLOT.md` mentions alone.

   Verified directly: a real `ImageViewerWidget` loads a real PNG
   fixture onto the raster page and a real SVG fixture (both a
   hand-written one and one of the repo's own `diagram-assets/*.svg`
   files) onto the vector page, switches back and forth correctly, and
   shows an error label (not a crash) for invalid content of either
   kind; `find_view_handler` resolves a bare `.svg` to `"image_viewer"`
   with an empty registry; `widgets/svg_viewer/` no longer exists; no
   remaining `svg_viewer`/`SvgViewerWidget` reference anywhere in
   `src/`/`widgets/`. Full regression suite (`git stash` before/after):
   back to the same 17 pre-existing/known-stale failures, after fixing
   three of my own earlier scripts that hardcoded the old widget id/
   path directly (`verify_drag_drop.py`'s `SVG_VIEWER_WIDGET_ID` import
   and dispatch assertion, `verify_file_explorer_fallback_chain.py`'s
   builtin-fallback assertion, `verify_viewer_widgets_edit_button.py`'s
   direct `widgets/svg_viewer/widget.py` load) — all confirmed as
   expected staleness, not real regressions, the same pattern already
   seen for the Project Files rename and the `build_widget.py` move.
7076af5. COMPLETED: New SVG Editor widget (`widgets/svg_editor/`) with a basic
   visual-object toolbox and point/shape editing tools. See
   `design-docs/svg-viewing-and-editing.md`'s "Supported element types"
   and "SVG Editor widget" sections: a closed set of editable object
   types (`<rect>`, `<circle>`, `<ellipse>`, `<line>`, `<polyline>`,
   `<polygon>`, `<path>`, `<text>`), a create-tool per type in the
   toolbox, and two mutually-exclusive editing tools — Points (drag a
   path/polyline/polygon's individual vertices) and Shapes (select a
   whole object to move/resize/transform and edit its fill/stroke/
   stroke-width as a unit). `kind: "python"`, same Open/file-watcher/
   auto-reload/Save shape as every other file-backed widget here;
   `xml.etree.ElementTree` for parsing/serializing (no new dependency,
   per `CLAUDE.md`), a `QGraphicsScene` with one custom `QGraphicsItem`
   subclass per supported type. Also add
   `file_type_registry.BUILTIN_EDIT_WIDGET_BY_SUFFIX = {".svg":
   "svg_editor"}` and have `find_edit_handler` fall back to it the same
   way `find_view_handler` already falls back to
   `BUILTIN_VIEW_WIDGET_BY_SUFFIX` — otherwise Image Viewer's Edit
   button would keep opening `.svg` files in the plain text Editor by
   default even after this widget exists. Depends on TODO `4d21e7c`
   (so Image Viewer is the thing whose Edit button actually exercises
   this) but not blocked by it — can be implemented in either order.
   [planned: svg-editor-widget.md]

   `widgets/svg_editor/widget.py`: `xml.etree.ElementTree` is the
   single source of truth (`SvgObject` subclasses -- `RectObject`/
   `CircleObject`/`EllipseObject`/`LineObject`/`PolylineObject`/
   `PolygonObject`/`PathObject`/`TextObject` -- pair a `QGraphicsItem`
   with the live `ET.Element` it was parsed from; anything
   unrecognized, including a `<path>` whose `d` isn't the supported
   straight-line-only M/L/Z grammar, is simply never touched, giving
   verbatim round-tripping for free). Toolbox: one create-tool button
   per type (click-to-place with a fixed default size for the
   single-click types; click-to-add-vertices, Enter/double-click to
   finish, for polyline/polygon/path), plus Points and Shapes tools.
   Both editing tools' drag-handles are hit-tested and tracked at the
   `_EditorView` level (mirrors `WorkspaceView`'s own resize-handle
   pattern, `design-docs/widget-ux.md`'s "Zoom-Correct Dragging") rather
   than making the handles themselves draggable Qt items. Shapes tool
   also drives a small fill/stroke/stroke-width property panel. Added
   `file_type_registry.BUILTIN_EDIT_WIDGET_BY_SUFFIX = {".svg":
   "svg_editor"}`, `find_edit_handler` now falls back to it the same
   way `find_view_handler` already falls back to
   `BUILTIN_VIEW_WIDGET_BY_SUFFIX` — Image Viewer's Edit button needed
   no changes at all to pick this up, since it already goes through
   `current_context.get_editor_or_scrap_opener()` →
   `DeskWindow.open_editor_or_scrap` → `find_edit_handler`. Added a new
   numbered widget-list entry (23) to `design-docs/architecture.md`.

   A real, non-obvious correctness point handled directly while
   writing this (not found via a later bug, but worth recording): every
   wrapper's geometry read/write goes through `item.mapToScene`/
   `mapFromScene`, not raw `item.pos()`/local-coordinate arithmetic --
   a native Qt drag (Shapes tool's own whole-object move) changes an
   item's `pos()` without touching its local geometry, so anything
   that read local coordinates directly (e.g. a naive `line().p1()`
   for `LineObject`, or a polyline's stored point list) would silently
   ignore any prior native drag when serializing or placing a Points
   -tool handle. `mapToScene`/`mapFromScene` are unaffected by that
   distinction since they always resolve true scene position
   regardless of how much of the offset lives in `pos()` vs. local
   coordinates.

   Verified directly: a real `SvgEditorWidget` (headless `QApplication`)
   creates one of each of the 8 supported types via its toolbox
   click-to-place/click-to-add-vertices flow with the right resulting
   `ET.Element` tag/attributes; save-then-load-in-a-fresh-widget round
   -trips both a resized rect (via a simulated Shapes-tool corner drag)
   and a natively-drag-moved circle correctly; a loaded document mixing
   a recognized `<rect>`, an unrelated `<defs>` block, and an
   unsupported curved `<path>` keeps only the `<rect>` as an editable
   object and round-trips the other two completely untouched after a
   no-edits save; the Points tool moves exactly one polygon vertex
   without disturbing the others; the Shapes tool's corner-drag resizes
   a rect and keeps a circle's `rx`/`ry` equal under resize; the
   property panel's fill/stroke/stroke-width setters apply to the
   selected item and sync correctly to its element; unsupported `<path>`
   grammar (curves, lowercase/relative commands) is correctly rejected;
   `find_edit_handler` resolves a bare `.svg` to `"svg_editor"` with an
   empty registry; `discover_widgets` picks up the new manifest
   correctly. Full regression suite (`git stash` before/after): the
   same 17 pre-existing/known-stale failures, 0 new failures.

   Found and fixed one real, reproducible crash during verification:
   `QGraphicsScene.selectionChanged`'s connected slot
   (`_on_selection_changed`) could fire against an already-destroyed
   `QGraphicsScene` C++ object during widget teardown
   (`RuntimeError: wrapped C/C++ object ... has been deleted`), the
   same class of Qt-signal-invoked-slot-outliving-its-object issue this
   codebase already guards elsewhere (LEARNINGS.md, TODO `810a5d6`).
   Fixed two ways: gave the scene an explicit Qt parent
   (`QGraphicsScene(self)`, tying its lifetime to the widget's own
   ownership tree) and wrapped the slot's scene access in the same
   established defensive `try`/`except RuntimeError` pattern used for
   every other Qt-signal-invoked slot chain here.
d28885f. COMPLETED: New side-by-side widget container: two widget-instance slots in
   one `WidgetFrame`, a button to swap which slot is on which side, and
   a horizontal/vertical orientation toggle — the parking-lot design
   (moved out of `PARKINGLOT.md`), except inter-widget communication
   uses the *existing* mediated event system (`desk.event_mediator`,
   TODO `6f9c51b`) instead of inventing a new `postMessage`-modeled
   protocol. Key points, confirmed by reading the current widget
   -hosting code before adding this item:
   - No widget today hosts another widget's content nested inside
     itself — instance ids are minted 1:1 with a `WidgetFrame`'s own
     construction (`canvas.add_widget`), and `DeskWindow
     ._bind_event_mediator` only ever wires the *top-level* hosted
     content, never anything a widget builds internally. This
     container has to replicate that wiring itself for each of its two
     slots: mint its own instance id per slot, and call
     `content.bind_event_mediator(instance_id, mediator)` on each
     slot's content if it exposes the hook (same duck-typed shape
     `DeskWindow` already uses), tearing down via
     `mediator.unsubscribe_all(instance_id)` when a slot's widget
     changes or the container itself is destroyed.
   - Each slot's instance id must be **persisted** on `WidgetState`
     (alongside the container's own top-level instance id) and reused
     verbatim on reload, not re-minted — otherwise a child widget that
     keeps its own per-instance-id persisted state (e.g. which file
     it has open) would silently lose it every session.
   - `current_context` has no hook today for a widget to enumerate the
     available widget catalog. Add one (mirroring the existing
     `set_widget_opener` pattern) so each slot can offer a "choose a
     widget type" picker; scope the catalog this container offers to
     `kind: "python"` widgets only for this first pass — nesting a
     `kind: "html"` widget's own `QWebEngineView`/browser-profile
     overhead inside another widget's layout is a bigger, separate
     concern, out of scope here.
   - Reuse `PythonWidgetHost` directly per slot (constructed by the
     container itself, not through `DeskWindow._place_widget`, since
     slot content never gets its own canvas placement) so each slot
     gets ordinary hot-reload-on-source-change behavior for free.
   - `EventMediator` is plain name-based pub/sub (broadcast to every
     subscriber of a name except the sender) with no parent/child or
     point-to-point concept — this container doesn't need to invent one
     either: it just ensures both slots are properly bound to the
     shared mediator with stable instance ids, the same as any other
     placed widget. Any actual message protocol between two specific
     widget types (e.g. the parked "editor-with-view" pairing) is that
     pairing's own concern, not something this container defines.
   - A `QSplitter` (horizontal or vertical per the orientation toggle)
     is a natural fit for the two slots — gives a draggable divider for
     free, and swapping sides is just re-inserting the same two child
     widgets in the other order, no rebuild needed.
   [planned: side-by-side-widget-container.md]

   New `widgets/side_by_side/widget.py`. Two new `current_context` hooks
   (`get_widget_catalog_provider`/`set_widget_catalog_provider`,
   `get_hot_reload_broker`/`set_hot_reload_broker`), wired once at
   `DeskWindow.__init__`; a new `DeskWindow.get_widget_catalog_dicts()`
   backs the former, filtered to `kind: "python"` (reads `self._widgets`
   fresh each call, so a later `discover_widgets()` refresh is picked
   up automatically). Persistence needed **no new `WidgetState`/`Desk`
   field at all** — it reuses the existing generic widget-local-storage
   mechanism (TODO `fb76057`) end to end: `{"orientation", "order":
   [0,1]-or-[1,0], "slots": [{"widget_id", "instance_id",
   "local_storage"}, ...]}`, with the container's own
   `get_widget_local_storage`/`set_widget_local_storage` recursing into
   each occupied slot's own content the same hooks (since a nested
   child never gets a top-level `WidgetState`/`WidgetFrame` of its
   own — without this, a slot's child would silently forget its own
   state, e.g. an Editor's open file, every Desk reload). Two fixed
   slot identities (`_Slot`, never reassigned) plus a separate
   `self._order: list[int]` recording which slot occupies which
   `QSplitter` position — Swap only flips `_order` and re-lays-out via
   `QSplitter.insertWidget` (which natively re-parents/moves a widget
   already in the splitter), so a slot's own instance id/mediator
   bindings/local storage are never disturbed by swapping. Each
   occupied slot's `PythonWidgetHost` is bound to the shared
   `EventMediator` (`current_context.get_event_mediator()`, no new hook
   needed there) via the same duck-typed `bind_event_mediator`
   hook `DeskWindow._bind_event_mediator` already uses for top-level
   frames — re-run after every hot-reload rebuild too (the container's
   own `HotReloadBroker.widget_changed` connection, alongside the one
   the host itself already has, since a rebuild swaps in a fresh
   `.current` that needs re-binding). Re-picking a slot's widget type
   mints a fresh instance id and unsubscribes the old one; the
   container's own teardown (captured plain values in a closure
   connected to `self.destroyed`, per the established "connecting to
   your own bound method silently never fires" pattern) unsubscribes
   both slots' instance ids when the container itself is destroyed.
   Added a new numbered widget-list entry (24) to
   `design-docs/architecture.md`.

   Verified directly, with a real `EventMediator`/`HotReloadBroker` and
   the real discovered widget catalog: choosing a widget for each slot
   builds a real `PythonWidgetHost` showing that widget's actual
   content; a publish from one slot's bound instance id is genuinely
   received by a third, independently-subscribed instance (proof the
   slots are on the shared bus, not an isolated one); re-picking a
   slot's widget type mints a new instance id and fully unsubscribes
   the old one; Swap exchanges splitter positions without changing
   either slot's instance id or rebuilding either host; Orientation
   toggles correctly; a full persistence round-trip (including a
   swapped order and a nested Editor child's own open-file local
   storage) correctly restores every piece of state on a totally fresh
   instance. Full regression suite (`git stash` before/after): the same
   17 pre-existing/known-stale failures, 0 new.
06fa070. COMPLETED: Investigate `tests/verify/disabled_verify_bridge_api_editor_or_scrap.py`:
   currently fails on a single stale `TEMPUI_DOC_VERSION == 16`
   assertion (now 17); every other check in the script passes. Per the
   new "Verification scripts" process (`development-process.md`):
   update the assertion (or drop the version check) if that's genuinely
   the whole issue, rewrite for equivalent coverage, or delete.
   [planned: investigate-disabled-verify-bridge-api-editor-or-scrap.md]

   Confirmed the suspected cause was the whole issue: loosened the
   assertion to `TEMPUI_DOC_VERSION >= 16` and re-enabled the script
   (renamed back to `verify_bridge_api_editor_or_scrap.py`, no other
   changes needed). Full `tests/verify/` suite: 16 remaining known
   -disabled scripts, 0 new failures among the enabled ones.
1082bd4. COMPLETED: Investigate `tests/verify/disabled_verify_build_widget.py`: fails at
   import time (`import build_widget`) since TODO `029047b` deleted
   `scripts/build_widget.py`, moving its content into
   `src/desk/temp_ui.py`'s generated `_BUILD_WIDGET_SCRIPT`. Rewrite
   against the generated script, or delete if
   `tests/verify/verify_ensure_build_widget_script.py` already covers
   the same ground.
   [planned: investigate-disabled-verify-build-widget.md]

   Not redundant with `verify_ensure_build_widget_script.py` (which
   only covers the generated script's happy path) — this one exercises
   5 distinct `BuildError` scenarios plus a "never falls back to npx"
   check, real coverage worth keeping. Rewrote it: generates the real
   script into a fresh temp `.desk_temp/` (`write_tempui_docs`) and
   dynamically imports it (`importlib.util.spec_from_file_location`)
   instead of a static `scripts/` import; every fixture now built
   inline under `tempfile.TemporaryDirectory()` instead of the old
   session-specific scratchpad path. Re-enabled as
   `verify_build_widget.py`, all 6 original checks represented and
   passing. Full `tests/verify/` suite: 15 remaining known-disabled
   scripts, 0 new failures among the enabled ones.
69ebfb0. COMPLETED: Investigate `tests/verify/disabled_verify_build_widget_doc_and_seed.py`:
   tests `DeskWindow._seed_build_widget_script` (removed by TODO
   `029047b`) and pre-`59c5a70` doc content (`custom_widget_src`,
   `TEMPUI_DOC_VERSION == 11`) — a design superseded twice over. Likely
   just delete.
   [planned: investigate-disabled-verify-build-widget-doc-and-seed.md]

   Confirmed directly: the current `_CUSTOM_WIDGETS_DOC` content
   contains neither `custom_widget_src/<name>/` nor
   `scripts/build_widget.py` anymore, and `_seed_build_widget_script`
   no longer exists at all. Deleted the file outright — the ensure
   -mechanism's current behavior is already covered by
   `verify_ensure_build_widget_script.py`, nothing here was worth
   patching forward. Full `tests/verify/` suite: 14 remaining known
   -disabled scripts, 0 new failures among the enabled ones.
a96c091. COMPLETED: Investigate `tests/verify/disabled_verify_crash_handler.py`: checks for
   `DESK-CRASH-*.log` in the Desk's project directory directly, but
   TODO `7f51230` relocated crash logs to `.desk_temp/`. Update the
   glob if that's the whole issue.
   [planned: investigate-disabled-verify-crash-handler.md]

   Confirmed the suspected cause was the whole issue: both globs
   (`test_writes_log_in_current_desk_dir`/`test_falls_back_to_cwd`)
   updated to look under `.desk_temp/`, matching `crash_handler
   ._log_path()`'s real current behavior. Re-enabled as
   `verify_crash_handler.py`. Full `tests/verify/` suite: 13 remaining
   known-disabled scripts, 0 new failures among the enabled ones.
fea158d. COMPLETED: Investigate `tests/verify/disabled_verify_define_widget_auto_place.py`:
   fails on a single stale `TEMPUI_DOC_VERSION == 12` assertion (now
   17). Same category as TODO `06fa070`.
   [planned: investigate-disabled-verify-define-widget-auto-place.md]

   Confirmed same as TODO `06fa070`: loosened to `>= 12`, re-enabled as
   `verify_define_widget_auto_place.py`. Full `tests/verify/` suite: 12
   remaining known-disabled scripts, 0 new failures among the enabled
   ones.
3c613af. COMPLETED: Investigate `tests/verify/disabled_verify_discuss_parking_lot_item.py`:
   asserts `parse_discuss_parking_lot_item` returns `(label,
   full_body_text)`, but TODO `624ff3a` deliberately changed its
   contract to `(label, line_number)`. Rewrite against the current
   contract, or delete if later coverage already exists.
   [planned: investigate-disabled-verify-discuss-parking-lot-item.md]

   No enabled script covered `_place_discuss_claude_widget`/
   `_write_discuss_instructions_file`/`parse_discuss_parking_lot_item`
   at all — real coverage gap, rewrote rather than deleted. Updated the
   parsing test against `(label, line_number)`; loosened the stale
   `TEMPUI_DOC_VERSION == 5` assertion; rewrote the end-to-end
   `_activate_temp_ui` test against the current `Line <N>` tempui file
   format and the file-based instructions delivery (TODO `51be2bc` —
   no more embedding a marker string directly in the item text, which
   was the entire point of `624ff3a`; instead confirms a
   `.desk_temp/discuss-instructions-*.md` file was written with the
   expected line-number reference and that the claude widget's prompt
   points at it). Also had to add two more attributes/methods to the
   test's own fake `DeskWindow` double
   (`_bind_event_mediator`/`_event_mediator`,
   `_custom_widget_content_hash`) that the real `_place_widget` now
   requires — the exact same fixture-drift class of thing several other
   disabled scripts in this batch hit independently.
   `test_claude_widget_start_session_appends_extra_instructions`/
   `test_claude_widget_start_session_resume_ignores_extra_instructions`
   needed no changes (they exercise `ClaudeWidget.start_session`
   directly, unaffected by either contract change). Full
   `tests/verify/` suite: 11 remaining known-disabled scripts, 0 new
   failures among the enabled ones.
294f8a2. COMPLETED: Investigate `tests/verify/disabled_verify_file_explorer.py`: imports the
   pre-rename `widgets/file_explorer/` directory (TODO `8385dcc`
   renamed it to `project_files`). Likely just delete, since
   `verify_rename_project_files.py`/
   `verify_file_explorer_fallback_chain.py` already cover the renamed
   widget.
   [planned: investigate-disabled-verify-file-explorer.md]

   Two independent reasons it was obsolete, not just the rename: its
   actual assertions tested a per-widget manual Fusion-style-forcing
   workaround (TODO `593a464`) that TODO `8afef71` removed entirely
   (`_toolbar_style` no longer exists in `widgets/project_files/
   widget.py` at all). Deleted outright — its Open Folder/search-box
   coverage was incidental to that removed workaround, not dedicated
   coverage worth preserving on its own. Full `tests/verify/` suite: 10
   remaining known-disabled scripts, 0 new failures among the enabled
   ones.
9b89129. COMPLETED: Investigate `tests/verify/disabled_verify_fs_path_resolution_and_events_doc.py`:
   fails on a single stale `TEMPUI_DOC_VERSION == 13` assertion (now
   17). Same category as TODO `06fa070`.
   [planned: investigate-disabled-verify-fs-path-resolution-and-events-doc.md]

   Confirmed same as TODO `06fa070`: loosened to `>= 13`, re-enabled as
   `verify_fs_path_resolution_and_events_doc.py`. Full `tests/verify/`
   suite: 9 remaining known-disabled scripts, 0 new failures among the
   enabled ones.
6a5202c. COMPLETED: Investigate `tests/verify/disabled_verify_html_widget_local_storage.py`:
   its own fake `DeskWindow` double lacks `_bind_event_mediator`, which
   the real `_place_widget` has called unconditionally since TODO
   `6f9c51b`. Add the missing stub if that's the whole issue.
   [planned: investigate-disabled-verify-html-widget-local-storage.md]

   Confirmed fixture drift, plus a second gap found once the first was
   fixed: `_custom_widget_content_hash` was also missing from the fake
   double (same attribute several other disabled scripts in this batch
   were missing too). Added both; re-enabled as
   `verify_html_widget_local_storage.py`. Full `tests/verify/` suite: 8
   remaining known-disabled scripts, 0 new failures among the enabled
   ones.
6e9def4. COMPLETED: Investigate `tests/verify/disabled_verify_new_desk_directory.py`: its own
   fake `DeskWindow` double's `switch_desk` doesn't accept the real
   method's `provisioning` parameter. Update the fake double's
   signature if that's the whole issue.
   [planned: investigate-disabled-verify-new-desk-directory.md]

   Confirmed the suspected cause was the whole issue: added
   `provisioning=None` (accepted and ignored — nothing in this script's
   own assertions inspects it) to the fake's `switch_desk` signature.
   Re-enabled as `verify_new_desk_directory.py`. Full `tests/verify/`
   suite: 7 remaining known-disabled scripts, 0 new failures among the
   enabled ones.
086e922. COMPLETED: Investigate `tests/verify/disabled_verify_new_desk_flow.py`: its own fake
   `DeskWindow` double lacks `_event_mediator`, which the real
   `switch_desk` has called (`.clear_all()`) since TODO `6f9c51b`. Add
   the missing attribute if that's the whole issue.
   [planned: investigate-disabled-verify-new-desk-flow.md]

   Confirmed fixture drift, plus a second gap found once the first was
   fixed: `_introspect_grants` (a Bridge API introspection-grant cache
   `switch_desk` also clears) was missing too. Added a real
   `EventMediator()` and an empty `set()` for the grant cache;
   re-enabled as `verify_new_desk_flow.py`. Full `tests/verify/` suite:
   6 remaining known-disabled scripts, 0 new failures among the enabled
   ones.
f7469bc. COMPLETED: Investigate `tests/verify/disabled_verify_questions_discuss_button.py`:
   its own fake `DeskWindow` double lacks
   `_write_discuss_instructions_file`, which the real
   `_place_discuss_claude_widget` now calls. Add the missing stub if
   that's the whole issue.
   [planned: investigate-disabled-verify-questions-discuss-button.md]

   Same root cause as TODO `3c613af`: instructions are now delivered
   via a standalone `.desk_temp/discuss-instructions-*.md` file (TODO
   `51be2bc`), not spliced into the prompt — affects this script's
   `item_text` branch too, not just the `parking_lot_line` one. Added
   the missing fake-double attributes/methods
   (`_write_discuss_instructions_file`,
   `_bind_event_mediator`/`_event_mediator`,
   `_custom_widget_content_hash`) and rewrote the assertion checking
   the widget's terminal output directly for the marker text —
   confirms instead that the prompt points at a discuss-instructions
   file and that the file itself contains the expected text. Full
   `tests/verify/` suite: 5 remaining known-disabled scripts, 0 new
   failures among the enabled ones.
ba0bd9a. COMPLETED: Investigate `tests/verify/disabled_verify_relocate_promoted_widget_source.py`:
   reads `scripts/build_widget.py` directly, deleted by TODO `029047b`
   (already flagged as expected-stale at the time but never fixed).
   Same category as TODO `1082bd4`.
   [planned: investigate-disabled-verify-relocate-promoted-widget-source.md]

   Only 1 of the script's 5 test functions was actually stale — the
   other 4 (source-directory-moved-on-promotion, no-source-no-op,
   pre-existing-destination-not-clobbered) exercise
   `_relocate_promoted_widget_source` directly, unrelated to the
   build-widget-script relocation, still fully current. Fixed the one
   stale function to check the in-memory generated content
   (`SPLIT_DOC_CONTENT[BUILD_WIDGET_SCRIPT_FILENAME]`) instead of
   reading the deleted `scripts/build_widget.py` from disk, plus
   loosened one more stale `TEMPUI_DOC_VERSION == 14` assertion found
   along the way. Re-enabled as
   `verify_relocate_promoted_widget_source.py`. Full `tests/verify/`
   suite: 4 remaining known-disabled scripts, 0 new failures among the
   enabled ones.
f3120bb. COMPLETED: Investigate `tests/verify/disabled_verify_rename_project_files.py`: its
   "no remaining File Explorer content anywhere" grep doesn't account
   for this project's own convention of preserving historical mentions
   (TODO.md's own completed-item text, a rename plan's prose). Confirm
   whether the check's scope should just exclude those, or whether it
   was always unsatisfiable.
   [planned: investigate-disabled-verify-rename-project-files.md]

   Confirmed: the check's scope (`design-docs`, `TODO.md`,
   `PARKINGLOT.md`, `LEARNINGS.md`, `plans`) was checking something
   this project's own conventions never actually promise — likely
   unsatisfiable from very early on, not a later regression. Scoped
   the "no remaining content" grep down to `src`/`widgets` only (actual
   code, where the old name genuinely shouldn't appear at all); the
   plan-filenames-preserved check below it already covers the one
   legitimate exception in `plans/` at the filename level. Re-enabled
   as `verify_rename_project_files.py`. Full `tests/verify/` suite: 3
   remaining known-disabled scripts, 0 new failures among the enabled
   ones.
f7c2f60. COMPLETED: Investigate `tests/verify/disabled_verify_segfault_fix.py`: imports the
   pre-rename `widgets/markdown_ex/` directory (TODO `858752b` renamed
   it to `markdown`). Update the path (and `MarkdownExWidget` →
   `MarkdownWidget` if referenced) if that's the whole issue.
   [planned: investigate-disabled-verify-segfault-fix.md]

   Three independent staleness issues across its 4 test functions, not
   one: `test_refresh_external_path_status_hardened`'s widget list had
   both a duplicate `markdown_ex` entry (already covered by `markdown`)
   and a `svg_viewer` entry (retired by TODO `4d21e7c`, this same
   session — replaced with `image_viewer`); `test_open_index_hardened`
   imported the pre-rename `file_explorer` path *and* registered its
   broken fake opener through the wrong hook
   (`get_widget_opener`, not `get_centered_widget_opener`) with no
   file-type-registry entry, meaning even a path-only fix would have
   left it silently not exercising the actual hardening it claims to
   (a downstream widget's broken `set_file()` not crashing
   `_open_in_widget`'s own `try`/`except`) — rewrote it to register a
   fake view handler via `current_context
   .set_file_type_registry_provider` and the correct centered-opener
   hook, so it now genuinely reaches and exercises that `try`/`except`.
   The other two test functions needed no changes. Full `tests/verify/`
   suite: 2 remaining known-disabled scripts, 0 new failures among the
   enabled ones.
28119c6. COMPLETED: Investigate `tests/verify/disabled_verify_tempui_changelog_docs.py`: 3
   assertions hardcode the doc set's version range as of TODO `7462cdb`
   (when `TEMPUI_DOC_VERSION` was 14); it's since grown through 17.
   Decide whether to keep updating them by hand per bump or rewrite as
   a looser "covers every version up to current" check.
   [planned: investigate-disabled-verify-tempui-changelog-docs.md]

   Checked the actual current content before choosing a fix: the
   version lists are **not** contiguous (`breaking_versions == [17,
   14]`, `features_versions == [16, 14..7]` — version 15, TODO
   `1a96c9f`, has no features-doc entry at all since it wasn't
   agent-in-Desk-visible behavior) — a naive "contiguous through
   current" rewrite would have been wrong, not just looser. Loosened
   `TEMPUI_DOC_VERSION == 15` to `>= 15`, and replaced the two exact
   -list-equality checks with ones confirming only that the *original*
   `7462cdb` backfill is still present (`all(v in features_versions
   for v in range(7, 15))`, `14 in breaking_versions`) — robust to
   further versions being added later without needing hand-updates
   each time. Re-enabled as `verify_tempui_changelog_docs.py`. Full
   `tests/verify/` suite: 1 remaining known-disabled script, 0 new
   failures among the enabled ones.
d8a6c96. COMPLETED: Investigate `tests/verify/disabled_verify_tempui_custom_widgets.py`: its
   own fake `DeskWindow` double lacks `_custom_widget_content_hash`,
   which the real `_register_custom_widget` now sets. Add the missing
   attribute if that's the whole issue.
   [planned: investigate-disabled-verify-tempui-custom-widgets.md]

   Confirmed fixture drift, plus two further gaps surfaced only once
   earlier ones were fixed (each only reachable after the previous fix
   let execution proceed further): `_refresh_stale_indicators_for`
   needed binding (and its own `self.view._frames` dependency needed
   an empty list added to the lightweight `_FakeView` double), and
   `_relocate_promoted_widget_source` needed binding too. Also added
   `_bind_event_mediator`/`_event_mediator` to `_FakeWindowWithView`
   preemptively (same gap fixed in several sibling scripts this batch).
   Re-enabled as `verify_tempui_custom_widgets.py`.

   Full `tests/verify/` suite: **0 remaining disabled scripts** — every
   one of the 17 disabled in this batch (TODO.md's own moves-and
   -disables commit) has now been investigated and either fixed,
   rewritten, or deleted; all 67 scripts in `tests/verify/` currently
   pass.
dafbaab. COMPLETED: Remove the feature where a newly defined tempui `DefineWidget`
   keyword automatically gets one instance placed on the Desk (TODO
   `5ff02d2`) — per direct user feedback, it proved too confusing in
   practice. Revert the auto-place call entirely
   (`DeskWindow._handle_define_widget_file`'s `is_new`-gated call to
   `_auto_place_new_custom_widget`, itself deleted), keeping only the
   "louder docs" half of `5ff02d2`'s original fix (the callout that
   defining a kind never places an instance by itself) — update that
   callout in `_CUSTOM_WIDGETS_DOC` (`src/desk/temp_ui.py`) to no
   longer describe the now-removed auto-place behavior, bump
   `TEMPUI_DOC_VERSION`, and add a `tempui-breaking-changes.md` entry
   (this is breaking from an in-Desk agent's perspective — an agent
   that had learned to rely on auto-placement for a brand-new keyword
   now needs to invoke it explicitly, same as every other tempui kind
   always required). Also update `design-docs/custom-widget-authoring.md`
   section 2, which currently proposes the two-part fix (louder docs +
   auto-place) as still-current design.
   [planned: remove-define-widget-auto-place.md]

   `DeskWindow._on_temp_ui_file_added` now calls
   `_handle_define_widget_file(path)` with no `is_new` argument;
   `_handle_define_widget_file` no longer takes that parameter at all
   (dropped along with the `keyword_already_known` local and the
   auto-place call), and `_auto_place_new_custom_widget` is deleted
   outright. Dropped the same method's mentions from
   `open_widget_content_centered`'s docstring and
   `current_context.set_centered_widget_opener`'s. `_CUSTOM_WIDGETS_DOC`'s
   callout rewritten to state plainly that `DefineWidget` never places
   an instance by itself — brand-new keyword or redefinition alike —
   full stop, no auto-placed exception. `TEMPUI_DOC_VERSION` 17 → 18,
   with a new Version 18 entry in `tempui-breaking-changes.md`
   explicitly noting this reverts the Version 12 new-features entry;
   that Version 12 entry itself is left untouched as dated historical
   record (same precedent as Version 14's own breaking change
   deferring to the breaking-changes doc rather than being rewritten).
   `design-docs/custom-widget-authoring.md` section 2 rewritten to
   describe the actual single-part fix (doc callout only) plus a
   "tried and reverted" note explaining the auto-place half's own
   history and why it was pulled.

   `tests/verify/verify_define_widget_auto_place.py` renamed to
   `verify_define_widget_no_auto_place.py` with every assertion
   flipped: a brand-new keyword registered via the live-added path now
   places zero instances too, converging with the other three
   already-nothing-placed paths (edit-of-known-keyword, bulk rescan,
   failed registration) — kept as explicit regression protection
   against reintroducing the removed behavior by accident, rather than
   deleted.

   Verified directly: the real, unbound `DeskWindow
   ._handle_define_widget_file` (no `is_new` param) registers a
   brand-new keyword via a fake window double with a real
   `WorkspaceView`, and `win.view._frames` stays empty — same for the
   other three paths, all previously and still nothing-placed;
   `_auto_place_new_custom_widget` no longer exists as an attribute on
   `DeskWindow`; doc content (version bump, breaking-changes entry,
   simplified callout, no remaining "auto-places" wording). Full
   regression suite (`git stash` before/after): fixed one more of my
   own earlier scripts' hardcoded exact-version assertion
   (`verify_ensure_build_widget_script.py`, `== 17` → `>= 17`,
   consistent with the `>=`-loosening already applied to several
   similar assertions in the previous TODO batch) — confirmed not a
   real regression. 0 other new failures across all 65 scripts in
   `tests/verify/`.
3846190. COMPLETED: Fix widget content event routing: zoom/pan interactions on
   individual widgets are generally unsuccessful — Desk's own canvas
   (`WorkspaceView`, `src/desk/shell/canvas.py`) is grabbing events that
   should go to whichever widget's content the cursor is over. Per
   direct user report: "If there is an active widget and the mouse
   cursor is over the active widget, then that widget should get all
   the events, including clicks (left and right), pans, zooms, etc."
   Confirmed three independent, real gaps (one via a real, headless
   repro, not just reading code — see the plan): (1) `contextMenuEvent`
   unconditionally shows `WidgetSpawnMenu`, stealing every right-click
   regardless of what's under the cursor; (2) the `event()` override's
   `NativeGesture`/pinch-zoom handling unconditionally zooms the
   canvas, with no carve-out at all (unlike wheel-scroll's own
   existing, deliberate one); (3) click-and-drag starting inside a
   placed widget's own content, when that specific spot doesn't itself
   consume the drag, leaks through Qt's own `ScrollHandDrag` fallback
   and pans the *outer* canvas instead — confirmed empirically (a real
   press/move/release sequence against a real `WorkspaceView` moved the
   view's own scrollbars by the exact drag delta). Wheel-scroll itself
   is unaffected/already correct (TODO c44e88f's existing
   `_scrollable_at` carve-out).
   [planned: widget-content-event-priority.md]

   New `WorkspaceView._frame_at(view_pos)` helper (same `itemAt`-based
   shape as `_hit_test_chrome`/`_scrollable_at`, but broader — any
   placed widget's bounds, not just chrome or scroll areas).
   `contextMenuEvent` now hit-tests first and forwards via
   `super().contextMenuEvent(event)` when over widget content, instead
   of unconditionally showing `WidgetSpawnMenu`. `event()`'s
   `NativeGesture` handling now reuses `_scrollable_at` (the same gate
   `wheelEvent` already uses, deliberately not the broader
   `_frame_at` — keeps pinch consistent with wheel's own existing
   behavior, still zooming the canvas over non-scrollable content like
   a plain image viewer). `mousePressEvent`'s existing chrome-vs-content
   fallthrough now checks `_frame_at` for the non-chrome case: over
   widget content, drag mode is temporarily switched to `NoDrag` for
   just the one `super().mousePressEvent(event)` call (restored
   immediately after), preventing Qt's own hand-scroll-start decision
   from ever engaging for that press — content interaction still
   happens normally in the same call. Updated `design-docs/widget-ux.md`
   (Trackpad Zoom Input, Add Widget Menu, Zoom-Correct Dragging
   sections) to match the new, actual behavior — the "Trackpad Zoom
   Input" section's own opening line ("Both are carved out...") was
   already inconsistent with its closing sentence ("Pinch-to-zoom is
   unaffected by this carve-out") even before this fix; now genuinely
   true.

   Verified directly, each via a real, headless `WorkspaceView` (not
   just reading code): (1) a real press/move/move/release `QMouseEvent`
   sequence dragging inside a placed widget's own content no longer
   moves the view's own scrollbars at all (previously moved them by the
   exact drag delta — confirmed via `git stash`), while the identical
   sequence starting on truly empty canvas still pans it exactly as
   before; (2) a real `QContextMenuEvent` positioned over widget content
   no longer constructs `WidgetSpawnMenu` (patched to confirm), while
   the same event over empty canvas still does; (3) a duck-typed
   native-gesture event (constructing/dispatching a *real*
   `QNativeGestureEvent` segfaulted in this offscreen environment,
   unrelated to the logic under test) confirms pinch no longer zooms
   the canvas over a scrollable widget's content, while still zooming
   over non-scrollable content and empty canvas alike. Full regression
   suite (`git stash` before/after): the new
   `verify_widget_content_event_priority.py` script's 3 previously
   -failing checks (drag/right-click/pinch over content) are exactly
   the ones this fix makes pass, with all 4 "should still work exactly
   as before" checks (background pan, empty-canvas right-click, pinch
   over non-scrollable content and empty canvas) passing both before
   and after — confirming this is a targeted fix, not a side effect.
   Re-ran every chrome-focused script (titlebar drag, resize handles,
   lock, z-order, eye button, stale marker, widget focus, TODO widget's
   own file-watcher-driven reload) to confirm chrome interactions are
   completely unaffected. 0 other new failures across all 66 scripts in
   `tests/verify/`.
8d4826c. COMPLETED: New Event Recorder widget: a "Record for 5s" button that
   temporarily hides the widget's own content (keeping its full size)
   and records every raw Qt event that lands on it during that window,
   then shows a scrollable list of what happened — chronologically
   -adjacent events (even with differing payloads) collapsed into
   collapsed-but-uncollapsable summary groups before display. Motivated
   directly by TODO `3846190`: the user still sees a trackpad
   two-finger-scroll gesture "getting missed" by widgets even after
   that fix, and wants to observe empirically (this environment can't
   reproduce real trackpad hardware input at all) exactly which events
   actually arrive, rather than guessing further — e.g. some platforms
   report two-finger scroll as a `NativeGesture` `PanNativeGesture`
   rather than (or alongside) a `Wheel` event, which TODO `3846190`'s
   own fix never considered at all (only `ZoomNativeGesture`/pinch).
   [planned: event-recorder-widget.md]

   New `widgets/event_recorder/`: `_RecordingSurface(QWidget)` is
   deliberately childless (so nothing can intercept an event before
   its own `event()` override sees it) and passive (always calls
   `super().event(event)`, recording is pure observation, never a
   filter). `_collapse_adjacent` run-length-encodes the raw,
   time-ordered event list by `event.type()`; `_group_to_display_dict`
   strips the raw (non-JSON-serializable) `QEvent.Type` enum member
   before the result is shown in a read-only `QTableWidget` (matching
   Event Log widget's own established shape) or persisted via widget
   -local storage. A live countdown in the status label updates every
   second during the 5s window. Added a new numbered widget-list entry
   (25) to `design-docs/architecture.md`.

   Found and fixed one real bug during verification: `QWidget`'s own
   constructor can dispatch an internal event (delivered through this
   same overridden `event()`) *before* `_RecordingSurface.__init__`'s
   body would otherwise get a chance to run — confirmed directly (an
   `AttributeError` on `self._recording`, raised from inside
   `super().__init__()` itself, not from any caller). Fixed by setting
   `_recording`/`_events`/`_start_time` *before* calling
   `super().__init__(parent)`.

   Verified directly (real `QMouseEvent`/`QWheelEvent` instances
   dispatched straight to `_RecordingSurface.event()` — constructing
   and *dispatching* a real `QNativeGestureEvent` segfaulted in this
   offscreen environment during TODO `3846190`'s own verification,
   unrelated to the logic under test here, so `_describe_event`'s
   native-gesture branch is verified separately via a duck-typed fake
   instead, a plain function call with no `QWidget.event()` dispatch
   involved): events are only captured between `start()`/`stop()`;
   `_collapse_adjacent` produces the right number of groups and
   correctly keeps two non-adjacent runs of the *same* type separate
   (not merged into one); the full widget flow (bypassing the real 5s
   timer directly) switches pages correctly, disables/re-enables the
   record button, and populates the results table correctly;
   `get_widget_local_storage`/`set_widget_local_storage` round-trips a
   completed recording's groups onto a fresh instance, and an
   empty/no-prior-recording payload is a safe no-op. `discover_widgets`
   picks up the new manifest correctly. Full regression suite (`git
   stash` before/after): 0 new failures across all 67 scripts in
   `tests/verify/`.
