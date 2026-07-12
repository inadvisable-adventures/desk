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
b44e8ba. PENDING: Crash: segfault while interacting with the Desk picker.
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
   involved.

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
465c404. COMPLETED: Bug: in the File Explorer widget, the "Open Folder" button and
   the search box's chrome (background/border) don't scale with zoom,
   similar to how the tree-collapsing controls (">") were also not
   scaling properly before that was fixed. Screenshot: the widget
   zoomed in to roughly 3-4x -- the titlebar ("File Explorer" label,
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
   /desk-temporary-ui.md` in the File Explorer widget to open it (this
   opens it in a new Editor widget instance). This may or may not be
   related to work done around the same time on TODO a053e3a (the
   "[EXTERNAL]" titlebar marker). Traceback captured at the time (paths
   scrubbed to start at `./desk/`; trace is cut off after this point --
   no exception type/message was captured):

   ```
   Traceback (most recent call last):
     File "./desk/widgets/file_explorer/widget.py", line 246, in _open_index
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
67ab2df. Implement a general solution so that already-placed tempui
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
f668aef. Make the Question widget live-refresh when its tempui file is
   edited after being placed (resolved by TODO 67ab2df's general
   solution -- documented gap, see `PARKINGLOT.md`).
091bc27. Make the LightningRound widget live-refresh when its tempui
   file is edited after being placed (resolved by TODO 67ab2df's
   general solution -- same underlying gap as Question, not
   previously called out separately).
9ee505f. Make the Scratch widget live-refresh from its tempui file
   without clobbering unsaved local edits (resolved by TODO 67ab2df's
   general solution, which specifically had to account for this case).
6fbae42. Make the Markdown tempui-bound content widget (TODO 9743419)
   actually live-refresh as originally described (resolved by TODO
   67ab2df's general solution).
7a086ba. Add a Questions widget that works similarly to the TODO
   widget, but for managing QUESTIONS.md.
a801180. Add to the tempui instructions to always use QUESTIONS.md for
   any questions there are for the user. If adding a new question, send
   a top-right tempui notification that, when clicked, either visually
   focuses a currently-opened Questions widget (see TODO 7a086ba) or
   else opens a new Questions widget and focuses it.
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
cb2790d. When creating a new Desk, don't add all of the widgets to it --
   just open a markdown viewer of the README.md file if there is one
   for the project, or else add a Scratch widget with content for a
   basic readme that has a "# [desk name] README" at the top followed
   by a section called "## What this project is about or exploring...".
5915ac2. Drag and drop files into Desk should cause them to be opened
   as external.
f74945e. Add a "paste" item to the top of the widget menu if there is
   anything in the clipboard; if pasted, put the pasted material into
   a file in the temp directory and attempt to open it with a
   corresponding widget; if it is markdown, then just use the markdown
   approach we're implementing with the new DSL entry (TODO 9743419);
   if it is text but not markdown, open it as a scrap (if there isn't
   a DSL entry for that, add one -- see TODO f8d9cec's existing
   `Scratch` tempui capability); if it is non-text content (binary),
   paste it as a new file in the project directory with a filename
   like `PASTED-ITEM-[timestamp].[file extension]`.
