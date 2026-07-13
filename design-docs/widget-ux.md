# Desk — Widget UX

This document specifies the UX chrome every widget gets on the Workspace
Canvas, regardless of widget kind (`python` or `html` — see
`design-docs/architecture.md`'s Widget Model). It's split out from the main
architecture doc because it's specifically about the interactive
frame/chrome around a widget, not the widget's own content or how that
content is built/rendered.

## Goals

- Every widget placed on the Workspace Canvas gets the same base chrome,
  regardless of whether its content is a native `QWidget` (`python` kind) or
  a `QWebEngineView` (`html` kind) — chrome is provided once, at the
  canvas-integration layer, not duplicated per widget kind.
- A **titlebar** across the top of the widget, showing its title, that acts
  as a **drag handle**: pressing and dragging it moves the widget around the
  Workspace Canvas.
- A **frame** around the widget with **resize handles on the left, right,
  and bottom edges** (not the top — that's the titlebar), each draggable to
  resize the widget.
- Both drag and resize must behave correctly regardless of the Workspace
  Canvas's current zoom level (see [Zoom-Correct Dragging](#zoom-correct-dragging)).
- The chrome (titlebar, resize handles) stays a **constant size on screen**
  regardless of zoom — zooming should only magnify each widget's *content*,
  not its frame (see [Chrome Stays a Constant Screen Size](#chrome-stays-a-constant-screen-size)).
- A small persistent **zoom control** (fit-to-content, reset, slider),
  shown only at non-unity zoom (see [Zoom Control](#zoom-control)).
- A top-left **Desk picker** (distinct, independently clickable name and
  directory labels: name opens an MRU picker, directory opens the
  directory picker directly) for switching/relocating the currently-open
  Desk (see [Desk Picker](#desk-picker)).
- A right-click **add widget menu** with a typeable filter, for adding new
  widget instances to the current Desk (see [Add Widget Menu](#add-widget-menu)).
- A **close button** ("✕") in the titlebar's upper-right corner: click to
  remove that widget instance from the canvas and the current Desk, after a
  confirmation prompt (see [Close Button](#close-button)).

## Non-Goals (for now)

- Corner handles / diagonal resize (only edges, per the Goals above).
- Minimizing/collapsing a widget from the chrome (closing is covered above;
  minimize/collapse is not).
- Snapping, alignment guides, or grid layout assistance while dragging.
- How/when a widget's position/size is persisted (that's
  `design-docs/architecture.md`'s Desk Model — this doc only covers the
  interactive chrome and the Desk Picker HUD itself, not serialization).

## Design

### `WidgetFrame`

A single `WidgetFrame(QWidget)` wraps any widget content (a
`PythonWidgetHost` or a `ChromiumWidget`) and is what actually gets placed
on the canvas (`WorkspaceView.add_widget()` builds one internally — callers
just pass their content widget and a title, they don't construct
`WidgetFrame` themselves). Layout (plain Qt layouts, no manual
`resizeEvent`-driven positioning):

```
┌───────────────────────────────────┐
│ Titlebar (drag handle)            │  <- QVBoxLayout, row 1
├─┬───────────────────────────────┬─┤
│L│                               │R│  <- QHBoxLayout, row 2:
│ │           content             │ │     left handle | content | right handle
├─┴───────────────────────────────┴─┤
│         bottom handle             │  <- QVBoxLayout, row 3
└───────────────────────────────────┘
```

- Titlebar: fixed height, shows the widget's title (a non-selectable
  `QLabel`, per `CLAUDE.md`'s "labels should not be user-selectable"
  convention), full drag-handle behavior, plus a close button at its right
  edge (see [Close Button](#close-button)).
- Left/right handles: fixed-width thin strips, horizontal-resize cursor.
- Bottom handle: fixed-height thin strip, vertical-resize cursor.
- `content`: the wrapped widget, stretched to fill the remaining space
  (`QSizePolicy.Policy.Expanding` in both directions, set by `WidgetFrame`
  regardless of the content widget's own default policy).

`WidgetFrame` itself also has a small 1px border by default (TODO
`ff6514a`, `#4a4d51`) so adjacent widgets — and a widget against the
plain canvas background — stay visually distinguishable, counter
-scaled to a constant on-screen thickness like every other piece of
chrome here. The stylesheet rule is scoped to the `WidgetFrame` class
name specifically (`WidgetFrame { ... }`, not a bare `QWidget { ... }`
selector), since an unscoped `QWidget` rule would cascade the border
onto every nested child widget inside arbitrary widget content.

### Zoom-Correct Dragging

`WidgetFrame` (and its titlebar/handles) is embedded on the
`QGraphicsScene` via `QGraphicsProxyWidget` (see
`design-docs/architecture.md`'s Workspace Canvas). Dragging the titlebar or
a resize handle needs to move/resize that proxy correctly regardless of the
canvas's current zoom level (`WorkspaceView.wheelEvent` scales the whole
view).

**Drag/resize tracking happens centrally in `WorkspaceView`, not in the
titlebar/handle widgets themselves.** An earlier version of this design had
each chrome widget track its own drag via its own
`mousePressEvent`/`mouseMoveEvent`, reading `event.globalPosition()` (or
`position()`, or `scenePosition()` — all three were tried). All three are
unreliable: they're read from the `QMouseEvent` that `QGraphicsProxyWidget`
constructs when forwarding a scene-level event down into an *embedded*
widget, and that translation does not reliably preserve real screen
coordinates once the view is at non-unity zoom — confirmed directly (real
trackpad hardware showed dragging was scaled specifically when zoomed out;
constructing real `QMouseEvent`s and routing them through the view at
various zoom levels reproduced it, off by a scale-dependent factor
regardless of which coordinate field was read).

`WorkspaceView` itself is not embedded in anything — it's the actual
top-level view widget, receiving events forwarded from its own viewport
(the standard way `QGraphicsView` subclasses handle mouse/wheel events,
exactly like this class's `wheelEvent` already did) — so its own
`mousePressEvent`/`mouseMoveEvent`/`mouseReleaseEvent` give reliable,
untranslated coordinates regardless of zoom. The approach:

1. On a left-button press, hit-test whether the click landed on a
   titlebar or resize handle: find the topmost `QGraphicsProxyWidget` at
   that viewport position (`self.itemAt(...)`), resolve its embedded
   `WidgetFrame`, map the click into the frame's own local coordinates
   (`self.mapToScene(...) - item.pos()`, using the same
   local-pixel-equals-scene-unit relationship established elsewhere in
   this doc), and call `frame.childAt(local_point)`, walking up
   `parentWidget()` until hitting a `_TitleBar`/`_ResizeHandle` or `None`.
2. If it hit chrome, `WorkspaceView` takes over the whole drag: on each
   mouse move, compute the incremental screen-pixel delta since the last
   event (both read from `WorkspaceView`'s own, reliable
   `event.position()`), divide by `self._scale` to get the equivalent
   delta in *scene* units, and apply it directly: `proxy.moveBy(dx, dy)`
   for a titlebar hit, or the per-edge resize math below for a handle hit.
3. If the press didn't hit chrome, `super().mousePressEvent(event)` runs
   instead — normal content interaction and background `ScrollHandDrag`
   panning are unaffected.

The chrome widgets themselves (`_TitleBar`, `_ResizeHandle`) are now purely
visual — background, cursor shape, `apply_scale` — with no mouse event
handling of their own.

Resize math per edge (`w`/`h` = current proxy size, `dx`/`dy` = the
scene-unit delta for this event):

- **Right**: `new_w = max(MIN_WIDTH, w + dx)`; resize only (top-left
  anchor unaffected).
- **Bottom**: `new_h = max(MIN_HEIGHT, h + dy)`; resize only.
- **Left**: `new_w = max(MIN_WIDTH, w - dx)`; resize *and* move by
  `(w - new_w, 0)` so the right edge stays fixed while the left edge
  follows the cursor.

### Minimum Size

`MIN_WIDTH`/`MIN_HEIGHT` constants (e.g. 200×120) prevent a widget from
being resized down to nothing/negative size, regardless of how far a
handle is dragged.

### Chrome Stays a Constant Screen Size

Zooming the Workspace Canvas magnifies the whole `WidgetFrame` proxy
(chrome and content alike), since it's one `QGraphicsProxyWidget` scaled by
the view's transform. To keep the *chrome* a constant screen size while
still letting *content* zoom/pan with the view, `WidgetFrame` counter-scales
its own chrome's local Qt-widget sizes inversely to the view's current
zoom: `set_view_scale(view_scale)` sets the titlebar's local height to
`round(TITLEBAR_HEIGHT / view_scale)`, each resize handle's local thickness
to `round(HANDLE_THICKNESS / view_scale)`, and the titlebar label's font
size to `round(TITLEBAR_FONT_PT / view_scale)`. Since the view later
multiplies everything by that same `view_scale` when rendering, these
counter-scaled local sizes land back at the original constant pixel sizes
on screen. `WorkspaceView` keeps a list of every placed `WidgetFrame` and
calls `set_view_scale()` on all of them whenever zoom changes (wheel,
pinch, slider, fit-to-content, reset). Content is unaffected — it simply
gets whatever space remains in the layout after the (now differently
-sized) chrome takes its fixed share, so it continues to zoom/pan with the
view exactly as before.

An alternative considered: a separate `QGraphicsItem` with
`ItemIgnoresTransformations` for the chrome, kept in position-sync with a
separate content-only proxy. More "correct" in the sense that it's Qt's
purpose-built mechanism for constant-screen-size scene content, but
requires maintaining a second graphics item per widget kept in sync on
every pan/zoom/move/resize. Counter-scaling keeps the existing "one
`WidgetFrame` proxy per widget" structure entirely intact.

The titlebar label itself is no longer fully static after construction:
`WidgetFrame.set_external(bool)` (TODO a053e3a) appends `" [EXTERNAL]"`
to it for a widget whose loaded file lives outside the current Desk
directory (`_TitleBar` keeps the original title string and an
`_external` flag, recomputing the label text from both). `DeskWindow`
wires this generically for any placed widget exposing an
`external_path_changed(bool)` signal -- see
`plans/widget-external-file-indicator.md`.

### Close Button

A `_CloseButton` ("✕") sits at the titlebar's right edge, counter-scaled
the same way as the rest of the chrome (its own `apply_scale()`, called
from `_TitleBar.apply_scale`) so it stays a constant screen size too.

Like the titlebar and resize handles, it's **purely visual** — no click
handling of its own. `WorkspaceView.mousePressEvent` already intercepts and
`accept()`s every press landing anywhere in the titlebar's screen-space
bounds before it can reach an embedded child widget (see [Zoom-Correct
Dragging](#zoom-correct-dragging)), so a real `QPushButton.clicked` inside
the titlebar would never actually fire. Instead, `_hit_test_chrome` gains a
`(frame, "close")` hit kind, checked before the general titlebar case since
`_CloseButton` is itself nested inside `_TitleBar`'s layout.

`WorkspaceView` treats a close-button hit as an ordinary **click**, not a
drag: a press remembers which frame's close button was hit and which
button kind it was (`_button_press: tuple[WidgetFrame, str] | None` --
generalized, TODO cdf45cb, to also cover the bring-to-front/send-to-back
buttons below, not just close) without starting a drag session; the
matching release re-runs the hit test and only fires the corresponding
action if the release landed on the *same* button (press-then-drag-away is
a cancelled click, matching normal button semantics — release elsewhere
does nothing and does not fall through to starting a drag).

`DeskWindow` connects `widget_close_requested`, shows a confirmation prompt
(same `Confirm`-callable pattern as switching/relocating a Desk — see
`design-docs/architecture.md`'s Desk Model), and on confirmation removes
the widget from the canvas and re-saves the current Desk. See
`plans/widget-close-button.md`.

### Bring to Front / Send to Back Buttons

Two more chrome buttons (`_BringToFrontButton` "▲", `_SendToBackButton`
"▼", both sharing a `_TitlebarButton` base class with `_CloseButton`) sit
left of the close button, in that order. Same purely-visual/centralized
-click-handling shape as the close button — `_hit_test_chrome` recognizes
`(frame, "bring_to_front")`/`(frame, "send_to_back")` the same way.

Unlike close (which needs `DeskWindow` confirmation and Desk-state
removal), these are handled entirely inside `WorkspaceView` itself:
`bring_to_front(frame)`/`send_to_back(frame)` set the frame's
`QGraphicsProxyWidget.setZValue()` to one above the current maximum, or
one below the current minimum, across every placed frame (`self._frames`)
— not a fixed constant, so repeated clicks on different widgets keep
stacking correctly rather than tying. This is genuine `QGraphicsScene`
stacking order, so it also affects which widget wins an overlapping click,
not just paint order. Session-only — no z-order field exists on
`WidgetState`, so stacking order isn't persisted across a Desk save/reload
(everything reverts to implicit insertion-order stacking on next load).
See `plans/widget-z-order-buttons.md`.

### Widget Focus

A widget is considered "focused" (TODO `397770c`) whenever any control
inside its content currently has real Qt keyboard focus — its titlebar
background shifts slightly (`#3a3d41` unfocused -> `#4a4e54` focused)
to show that. Driven centrally, once, by `WorkspaceView` — not
something any individual widget kind implements itself — via
`QGraphicsScene.focusItemChanged`, **not** `QApplication.focusChanged`:
confirmed directly that the latter reports the `QGraphicsView` itself,
never the specific embedded control, for anything placed via
`QGraphicsProxyWidget` (see `LEARNINGS.md`). The scene-level signal
correctly reports the `QGraphicsProxyWidget` whose embedded hierarchy
now holds focus; `proxy.widget().focusWidget()` (a plain `QWidget`
method) then resolves the specific focused descendant within it, which
`WidgetFrame` remembers (`remember_focused_widget`).

Clicking then releasing a widget's titlebar without dragging (TODO
`a1c701d`, `WorkspaceView`'s existing `TITLEBAR_CLICK_THRESHOLD`-based
click-vs-drag distinction — the same shape as the close/bring-to-front
/send-to-back buttons' own press-then-release-on-target matching)
re-focuses whichever control most recently had focus inside that
widget (`WidgetFrame.focus_last_widget`), falling back to `content`
itself if nothing has been focused inside it yet. Tracked via a
titlebar press/position pair kept separate from the drag-tracking
state, so a locked widget (TODO `8d05920`, which skips starting an
actual drag on its titlebar) still supports click-to-focus.

### Lock Widgets

A widget can be locked in place (TODO `8d05920`) via a `_LockButton`
("🔒") among the titlebar's usual button row. While locked, `_TitleBar
.set_locked(True)` hides every other titlebar button (lock,
bring-to-front, send-to-back, close — a hidden `QHBoxLayout` child
takes zero space by default, so the row genuinely collapses down to
just the title and a `_UnlockButton` ("🔓"), not merely a visual
de-emphasis) and `WorkspaceView` stops treating its titlebar press as
drag-eligible and its resize-handle presses as resize-eligible
(swallowed instead). Click-to-focus (see Widget Focus above) still
works, since that's tracked separately from the drag state. `"lock"`/
`"unlock"` are two more `_hit_test_chrome` button kinds sharing the
exact same press-then-release-on-target click machinery
close/bring-to-front/send-to-back already use.

Unlike z-order (session-only, see Bring to Front / Send to Back
above), locked state **is** persisted — a `locked: bool` field on
`WidgetState` (`desks.py`, defaulting `False` so an old `.desk` file
loads unaffected), captured in `_capture_desk_state` and reapplied in
`_load_desk_widgets`. It's a chrome-level concept `WidgetFrame` itself
owns, not routed through the "widget-local storage" mechanism (TODO
fb76057), which is for the wrapped *content* widget's own data.

### Zoom Control

A `ZoomControl(QWidget)` is a plain child widget of `WorkspaceView
.viewport()` (not a scene item), positioned in the lower-right corner and
repositioned on `resizeEvent`. It renders in screen space, unaffected by
the canvas's own zoom/pan, exactly like any floating HUD overlay on a
`QGraphicsView`. It's hidden whenever the canvas is at unity zoom
(`abs(scale - 1.0) <= epsilon`) and shown otherwise. It provides:

- **Fit** — fits `scene().itemsBoundingRect()`, expanded by a margin of
  0.1% of its own width/height on each side, via `QGraphicsView.fitInView`
  (`Qt.AspectRatioMode.KeepAspectRatio`), with the resulting scale clamped
  to `[MIN_SCALE, MAX_SCALE]`.
- **100%** — resets zoom to unity (`reset_zoom()`).
- **A zoom slider** (10%–400%, matching `MIN_SCALE`/`MAX_SCALE`) — sets an
  absolute zoom level directly, and stays in sync (without feedback loops)
  when zoom changes via any other means.

Zoom changes triggered by the HUD (slider/fit/reset) temporarily switch the
view's `transformationAnchor` to `AnchorViewCenter` around the underlying
`scale()`/`fitInView()` call, since the cursor may be sitting over the HUD
itself when these are triggered, and anchoring zoom under it (as
`AnchorUnderMouse`, used for wheel/pinch, would) would be a confusing place
to zoom toward.

### Desk Picker

A `DeskPicker(QWidget)` is a plain child widget of `WorkspaceView
.viewport()` (screen space, not a scene item — same pattern as
`ZoomControl`), anchored to the **top-left** corner (`ZoomControl` takes
the bottom-right). It always shows the current Desk's name (its file's
stem — see `design-docs/architecture.md`'s Desk Model) *and* its
associated directory, as two distinct, independently clickable label
"chips" (`_ClickableLabel`, a non-selectable `QLabel` with its own hover
style and `clicked` signal), separated by a plain `"—"`:

- **Name** — bold, brighter text, half-alpha pill background
  (`rgba(40, 42, 46, 128)`). Click opens `_DeskListPopup`: a stable,
  fully-visible-immediately `QListWidget` of MRU desks (current one
  pre-selected) followed by three muted **action rows** — "＋ New
  Desk…", "✎ Rename current Desk…", and "… Open another Desk…" — using
  the same `Qt.WindowType.Popup` pattern as `WidgetSpawnMenu`
  (click-away/Escape dismissal). A single click/Enter on an item picks
  it and closes. MRU rows carry their `Path` in `PATH_ROLE`; the action
  rows carry a `"new"`/`"rename"`/`"browse"` string in `ACTION_ROLE`.
- **Directory** — regular weight, dimmer text (`#b8bcc2`), a fainter pill
  background. Click opens the directory picker directly — no separate
  button.

Each chip's hover style (an accent-colored background — the same
`#3daee9` accent used elsewhere, e.g. `widgets/todo/widget.py`'s
`FILTER_BUTTON_STYLE` — plus an underline) is independent of the other's,
so they read as genuinely separate interactive regions rather than one
ambiguous label. (Previously: a single always-visible label plus, on
whole-widget hover via `enterEvent`/`leaveEvent`, a `QComboBox` MRU
dropdown and a `QPushButton` opening a directory picker — reworked for
being "finicky and strange" per TODO 8beab6e; see
`plans/desk-picker-split-name-directory-click.md`. The directory always
being visible, not just discoverable by hovering, predates this and is
otherwise unchanged — see `plans/desk-picker-always-show-directory.md`.)

`DeskPicker` is a "dumb" component: it emits `desk_chosen(Path)` (an MRU
entry was picked), `browse_requested()` (the "Open another Desk…" action
was picked — the picker itself doesn't own a `QFileDialog`),
`new_desk_requested()` / `rename_requested()` (the "New Desk…" /
"Rename current Desk…" actions), and `directory_change_requested()`
(the directory chip was clicked) — each one re-emitted from
`_DeskListPopup`'s own identically-named signal via
`desk.shell.qt_utils.deferred` (TODO `8c9436b`), not a direct
signal-to-signal connection: `_DeskListPopup` is a `WA_DeleteOnClose`,
`QListWidget`-based popup, and a receiver showing a modal dialog
synchronously (as several of `DeskWindow`'s own handlers do) risks a
real, reproduced segfault — the modal's own nested event loop
processes the popup's deferred deletion while a stale, still-in-flight
native mouse event might still target it. See `LEARNINGS.md`.
`DeskWindow` (which owns the actual
current-Desk state and the canvas) decides what to do with each —
including confirmation before acting, since switching Desks or changing
the current Desk's directory both need to confirm first. `DeskWindow`
always saves the current Desk *before* switching (rather than offering a
discard path), so confirming "Switch to X?" can never silently lose
layout changes.

`new_desk_requested` opens `NewDeskDialog` (TODO `4716585`,
`src/desk/shell/new_desk_dialog.py`) — a single dialog collecting
every New Desk decision at once: name, target directory (a read-only
field plus a "Browse…" button, defaulting to the current Desk's
directory), and checkboxes for creating `.desk_temp`, creating/updating
`.gitignore`, and (only shown if the current Desk has one to copy)
copying `development-process.md`. This replaced a chain of up to five
sequential modal popups (name, directory, dev-process-copy confirm,
`.desk_temp` confirm, `.gitignore` confirm) — both for convenience and
because that chain of nested `exec()` calls was implicated in a real
segfault (see `plans/fix-new-desk-flow-crash.md`): closing
`_DeskListPopup` (`WA_DeleteOnClose`) only *schedules* its deletion,
which actually runs during the next nested event loop — a long chain
of them was a wide window for a stale, still-in-flight mouse event to
be delivered to an already-destroyed list widget.

`DeskWindow.new_desk(name, directory, *, create_temp_ui,
create_gitignore, copy_development_process)` creates a new `.desk` in
`directory` and switches to it (no "Switch to X?" confirm — naming it
is the intent). A Desk with no saved widgets gets `cb2790d`'s seeded
Markdown-with-README (or Scratch-with-template) layout, not the old
one-of-every-widget default — and, since `switch_desk` now provisions
`.desk_temp`/`.gitignore` *before* placing any widget (previously
after), that seeded widget never starts running while a provisioning
decision is still in flight. `DeskWindow.rename_current_desk(new_name)`
renames the current Desk's file in place (a Desk's name *is* its file
stem), preserving its widgets/view and leaving its directory (and thus
`.desk_temp`) untouched. Both refuse a name that already exists (via a
`_warn` dialog) — `new_desk` re-checks this immediately before its
actual save too, not just at the top, since `switch_desk` in between
does real work that takes real time — and get their name via an
injectable `_prompt_fn` (mirroring `_confirm_fn`, so both are
substitutable in headless tests) for `rename_current_desk`, or
`NewDeskDialog`'s own fields for `new_desk`.

### Add Widget Menu

Right-clicking anywhere on the Workspace Canvas opens a `WidgetSpawnMenu` —
a small popup listing the discovered widget catalog, with a typeable
filter box at the top. Qt has no built-in menu with a live-filterable
query (`QMenu`'s keyboard handling only does prefix/mnemonic jumping), so
this is a dedicated `QWidget` (`Qt.WindowType.Popup`, giving it the same
click-away/focus-loss auto-close behavior as a real `QMenu`) rather than a
`QMenu` subclass:

- A `QLineEdit` filter box (auto-focused on open) above a `QTreeWidget` of
  matching entries, live-filtered as the user types (case-insensitive
  substring match against the widget's name or id).
- Up/Down move the list selection without the line edit losing focus;
  Return (with a selection), or clicking/double-clicking a row, chooses
  it; Escape or clicking away closes the popup without choosing anything.
- Entries are grouped into two collapsible sections (TODO ed483e2),
  "Active" (expanded by default) and "Deprecated" (collapsed by
  default) — driven by a new `WidgetInfo.deprecated: bool` field
  (`widget.json`'s optional `"deprecated"` key, `false` unless set).
  `QTreeWidget` gives native expand/collapse for free via two
  persistent, non-selectable top-level group items; re-filtering only
  rebuilds each group's *children*, never the group headers themselves,
  so a group the user manually expanded/collapsed stays that way while
  typing. Up/Down/Return only ever reach an actual widget entry — never
  a group header, and never an entry sitting inside a currently
  -collapsed group (a filter match doesn't auto-expand its group).

`WorkspaceView` builds the menu from a catalog it's told about once, at
construction (`set_widget_catalog` — the only piece of the wider widget
catalog the canvas itself needs to know), positions it at the right-click
location, and — on a choice — emits `widget_add_requested(widget_id,
scene_pos)`, re-emitted from the menu's own signal via `desk.shell
.qt_utils.deferred` (TODO `8c9436b`) — `WidgetSpawnMenu`, like
`_DeskListPopup`, is a `WA_DeleteOnClose`, `QAbstractItemView`
(`QTreeWidget`)-based popup, the same shape a real, reproduced segfault
was confirmed against; see `LEARNINGS.md`. `DeskWindow` handles the
(deferred) signal by placing a new instance through
the *same* `_place_widget` path already used for loading a Desk's saved
widgets and the fresh-desk fallback, so this can't drift out of sync with
how widgets are placed anywhere else in the app.

- **Paste entry** (TODO `f74945e`): a `Paste` item pinned first (outside
  the Active/Deprecated groups, unaffected by the typed filter), shown
  only if the clipboard has anything pasteable at the moment the menu
  is opened. Choosing it emits `paste_requested(scene_pos)`; `DeskWindow`
  writes the clipboard content into a new `.desk_temp/<uuid>` tempui
  file and opens it immediately at the click position — a `Markdown
  <label>` entry (TODO `9743419`) if the clipboard offers an explicit
  `text/markdown` flavor, else a `Scratch <label>` entry (TODO
  `f8d9cec`) for any other text. A clipboard image (no tempui DSL
  exists for binary content) is instead saved directly as
  `PASTED-ITEM-<timestamp>.png` in the project directory — no widget is
  opened for that case. See `plans/paste-clipboard-routing.md`.

Any right-click opens this same menu — there's no special-casing for
right-clicking empty canvas vs. an existing widget's chrome/content. A
widget-specific context menu (close, duplicate, etc.) is a reasonable
future feature, not a reason to complicate this one.

## Trackpad Zoom Input

Two independent trackpad-driven zoom inputs are supported:

- **Two-finger scroll** (`wheelEvent`): the zoom factor is proportional to
  the actual scroll delta (`exp(pixel_delta * SENSITIVITY)`, using
  `event.pixelDelta()` when available — which macOS trackpads report
  directly — falling back to `event.angleDelta() / 8` for a traditional
  mouse wheel) rather than a flat step per event, so a continuous gesture
  (which fires many more, smaller events on a trackpad than a wheel's
  discrete notches) feels proportional instead of jumping in large steps.
- **Pinch** (native trackpad pinch gesture, distinct from two-finger
  scroll): handled via `QEvent.Type.NativeGesture` /
  `Qt.NativeGestureType.ZoomNativeGesture` in an `event()` override (PyQt6
  doesn't expose a dedicated `nativeGestureEvent()` override point —
  confirmed via introspection — so this goes through the generic `event()`
  override instead). The gesture's `value()` is applied as `factor = 1.0 +
  value()`.

Both are carved out when the cursor is over a widget's own scrollable
content: `WorkspaceView.wheelEvent` hit-tests (`_scrollable_at`, same
shape as `_hit_test_chrome`) whether the position under the cursor is
inside a `QAbstractScrollArea` (what every scrollable Qt widget —
`QListWidget`, `QScrollArea`, `QTextEdit`, ...) is built on; if so, the
wheel event is forwarded via `super().wheelEvent(event)` so Qt's normal
scene-forwarding delivers it to that widget to scroll its own content,
instead of zooming the canvas. Pinch-to-zoom is unaffected by this carve
-out since it's handled separately, in `event()`, not `wheelEvent`. See
`plans/todo-widget-scrollable.md`.

## Open Questions

- Corner handles for diagonal resize — deferred (Non-Goals); worth adding
  if edge-only resize proves awkward in practice.
- Whether the titlebar should show anything beyond the widget's id/title
  (e.g. a kind indicator, a close button) — deferred to when widget
  lifecycle management (closing, etc.) is designed.
- Visual styling (colors, borders) is intentionally minimal for now — just
  enough to be legible and to make the handles discoverable via cursor
  shape; a real visual design pass is future work.

(Resolved: drag/resize behavior at non-unity zoom, including the
specifically-reported "scaled when zoomed out" symptom, was root-caused
and fixed — see [Zoom-Correct Dragging](#zoom-correct-dragging). Verified
via realistic event simulation at 0.25×–4× zoom for the titlebar and all
three resize handles; real-hardware confirmation is still the ultimate
check, per usual for interactive UX in this environment.)

## Future Work

- Minimize/collapse affordances in the titlebar (close is implemented —
  see [Close Button](#close-button)).
- Corner resize handles.
- Snapping/alignment while dragging.
- Keyboard-driven move/resize (accessibility).
