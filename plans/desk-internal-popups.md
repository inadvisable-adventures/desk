# Plan: TODO 359684f (COMPLETED) — desk-internal popups (scoped: widget-triggered confirm/warning dialogs)

## Scope (clarified with the user)

The original TODO wording said "replace all existing popup UI in Desk."
Clarified with the user: what they actually care about is popups
**triggered by widget code** (`widgets/*.py`) — these construct a real
`QMessageBox` parented to `self` (the embedded content widget itself,
living inside a `QGraphicsProxyWidget`), which shows as a real
top-level macOS window whose position/size Qt computes from the
parent's `mapToGlobal` — that computation doesn't account for the
canvas's own zoom/pan transform, so at non-1.0 zoom the dialog can
render in the wrong place, sized wrong, or appear to have content
outside its own window bounds.

**In scope**: every `QMessageBox` call in `widgets/*.py` (all parented
to `self`, confirmed via direct grep):
- `widgets/event_log/widget.py` `_confirm_clear` (Yes/No)
- `widgets/crash_log/widget.py` `_confirm_delete` (Yes/No)
- `widgets/questions/widget.py` `_confirm_discard` (Yes/No)
- `widgets/todo/widget.py` `_confirm_discard` (Yes/No)
- `widgets/stack/widget.py`: two `.warning()` (Ok) + one `.question()` (Yes/No)
- `widgets/editor/widget.py`: one `.warning()` (Ok) + `_handle_unsaved_changes`'s
  Save/Discard/Cancel (already isolated behind an injectable
  `self._confirm_unsaved` test hook — only the real-`QMessageBox` `else`
  branch changes)
- `widgets/svg_editor/widget.py`: one `.warning()` (Ok)

**Explicitly out of scope** (confirmed via research not to have this
bug, since they're parented to the main window, a real top-level
widget, not an embedded proxy — and/or don't fit a message+buttons
shape at all):
- `WidgetSpawnMenu` (needs a filterable widget list)
- `_DeskListPopup` (needs a scrollable MRU list)
- `NewDeskDialog` (needs free-text/checkboxes/a native directory picker)
- `src/desk/shell/window.py`'s own `_confirm_fn`/`_prompt_fn`/`_warn`/
  `_info`/`_warn_with_selectable_text`/`_confirm_stale_reload` — shell
  -level, parented to `DeskWindow` itself, not widget-embedded content;
  `_prompt_fn` also needs free-text input, out of scope for a
  message+buttons mechanism regardless of parenting.

Not attempting these lets this TODO stay narrowly focused on the actual
reported bug (widget-embedded popups rendering wrong under zoom/pan)
rather than a much larger, riskier rewrite of core interactive shell UI.

## Design

### New popup chrome: `WidgetFrame(..., is_popup=True)`

`WidgetFrame`/`_TitleBar` (`src/desk/shell/widget_frame.py`) get a new
`is_popup: bool = False` constructor param, threaded through to
`_TitleBar`. When `is_popup`, `_refresh_button_visibility`/
`_visible_button_widgets_for_full_state` short-circuit to show **only**
the title label and close button — no lock/unlock, no bring-to-front/
send-to-back, no eye button, no tempui-promote/stale indicators, and
`set_locked` is simply never called on a popup (so "never lockable" and
"not eye-button-focusable" both fall out of this one change, no new
interaction code needed). This reuses 100% of `WidgetFrame`'s existing
counter-scaling (`set_view_scale`/`apply_scale`) for free — a popup's
title/close button stay a constant on-screen size regardless of canvas
zoom, the same guarantee every other widget's chrome already has (see
design-docs/widget-ux.md's counter-scaling section) — satisfying
"act correctly under different levels of zoom" without new zoom-specific
code.

### Canvas integration: a separate list, not `_frames`

Confirmed directly: `DeskWindow._capture_desk_state`/
`find_frame_by_instance_id`/`_find_frame_by_widget_id`/
`_refresh_stale_indicators_for` (`src/desk/shell/window.py`) all iterate
`self.view._frames` and assume every entry is a real, persisted,
`widget_id`-bearing placed widget — `_capture_desk_state` in particular
would crash (`AttributeError`) trying to persist a popup's plain content
widget. So popups get their own `WorkspaceView._popup_frames: list[WidgetFrame]`,
entirely separate from `_frames`:

- `WorkspaceView.add_popup(frame) -> QGraphicsProxyWidget`: mirrors
  `add_widget` (`set_view_scale`, `scene().addWidget`) but positions
  centered in the current viewport (same centering math
  `DeskWindow.open_widget_content_centered` already uses:
  `self.mapToScene(self.viewport().rect().center())`), appends to
  `_popup_frames` (not `_frames`), and sets a z-value guaranteed above
  every normal frame: `z = max(max(self._frame_z_values(), default=0.0),
  self._next_popup_z) + 1`, then `self._next_popup_z = z`. Because
  `_frame_z_values()` only ever iterates `self._frames`, popups are
  automatically excluded from the normal `bring_to_front`/`send_to_back`
  pool with no changes needed there — "always frontmost in z-order"
  falls out of this for free too.
- `_on_scale_changed`/`_rescale`: add a second loop over
  `self._popup_frames` (same `frame.set_view_scale(self._scale)` call)
  so popups rescale correctly alongside normal frames.
- `clear_widgets()` (Desk switch): also removes any open popups'
  proxies from the scene and resolves their pending result callback
  with `None` first (see below) — a Desk switch while a confirm popup
  happens to be open must not leave its caller's nested event loop
  blocked forever.
- Hit-testing (`_frame_at`/`_hit_test_chrome`) needs **no changes** —
  both work off `self.itemAt(...)` + an `isinstance(..., WidgetFrame)`
  check on whatever the scene returns, not off `self._frames`/
  `_popup_frames` — a popup is automatically click-through-correct
  (TODO `78bfa41`'s "widget under the cursor wins" policy) with no
  special-casing.
- New `popup_closed = pyqtSignal(WidgetFrame)` signal; `mouseReleaseEvent`'s
  `kind == "close"` branch checks `frame.is_popup` and emits this
  instead of the normal `widget_close_requested` (which triggers
  `DeskWindow`'s full "close a placed widget" bookkeeping — wrong for a
  popup that was never part of Desk's persisted widget list).

### `PopupsService` (`src/desk_services/popups/`)

Follows the file_watcher service's shell (plain class, module-level
`get_service()` singleton, `__init__.py` re-export) but is a deliberate
exception to that precedent's "no Qt dependency" property: a popup
service's whole job *is* building/placing a Qt widget frame, so
`desk_services.popups.service` imports `PyQt6` and
`desk.shell.widget_frame.WidgetFrame` directly, and is given the one
live `WorkspaceView` via `attach_view(view)` (dependency injection, not
a global import) — called once by `DeskWindow` at startup.

- `show(title, message, buttons: list[str], default: str | None, on_result: Callable[[str | None], None]) -> None`:
  non-blocking, the core primitive. Builds a small body widget (a
  word-wrapped, selectable `QLabel` for `message`, plus a `QHBoxLayout`
  of one `QPushButton` per label in `buttons` — the entry matching
  `default` gets `setDefault(True)`/initial focus so Enter triggers it,
  matching every existing call site's `QMessageBox.StandardButton.No`
  -as-default safety convention), wraps it in
  `WidgetFrame(title, body, is_popup=True)`, calls
  `self._view.add_popup(frame)`. Each button's `clicked` connects to a
  guarded (call-`on_result`-exactly-once) resolver that also removes the
  popup from the canvas; the body's `keyPressEvent` treats Escape the
  same as the close button (resolves `None`, matching `QMessageBox`'s
  own Escape-dismisses convention); `popup_closed` (for this specific
  frame) resolves `None` the same way.
- `show_blocking(title, message, buttons, default) -> str | None`:
  synchronous convenience for widget call sites (which today call
  `QMessageBox.question(...)` and use the return value immediately) —
  runs a nested `QEventLoop`, quit by the same resolver `show` already
  wires up. This is a new pattern in this codebase (no prior
  `QEventLoop` usage) but is the same idea `QDialog.exec()` already
  uses internally; documented inline given it's novel here.
- Both return `None` for "dismissed via close/Escape without picking a
  button," letting every migrated call site treat `None` the same as
  whatever its old "declined" branch was (`!= Yes`, `else: action =
  "cancel"`, etc.).

### Reaching this from a `kind: "python"` widget

`src/desk/shell/current_context.py` gets a new
`set_popup_opener`/`get_popup_opener` pair (same flat paired-functions
shape as `set_editor_or_scrap_opener`/etc.), bound once by `DeskWindow`
at startup to `popups_service.show_blocking`. Every migrated widget
call site replaces its `QMessageBox.question(self, title, text,
Yes|No, No) == Yes`-shaped call with
`current_context.get_popup_opener()(title, text, ["Yes", "No"], "No") == "Yes"`
(no `self`/parent-widget argument needed at all, since popups are
always centered in the current viewport regardless of which widget
triggered them — simpler than anchoring near the requesting widget's
own frame, and avoids needing to walk up a parent chain to find it).

### Bridge API (`src/desk/server/app.py`)

New `PopupsShowRequest` (`title: str`, `message: str`, `buttons: list[str]`,
`default: str | None = None`) and
`@app.post("/api/bridge/popups/show")`, gated
`require_caller("popups")` (a new capability name, same free-form
string convention as `events`/`fs`/`widgets`/`editor`/`filetypes`/
`introspect` — declared in a widget's own `widget.json` `capabilities`
list). Since the FastAPI server runs off the GUI thread, this uses the
already-established `run_on_gui_async`/`GuiBridge.call_async` pattern
(the same one `request_introspect_permission` already uses to let a
background-thread caller block on a GUI-thread modal): `await
run_on_gui_async(lambda resolve: popups_service.show(body.title,
body.message, body.buttons, body.default, resolve))`. Returns
`{"clicked": result}` (`result` possibly `null`).

### tempui docs

This is a new Bridge API capability/route from the perspective of an
agent running inside Desk — update `tempui-new-features.md` per
`development-process.md`'s standing "keep the tempui changelog docs
current" rule.

## Migration (7 files, `widgets/*.py`)

Each site's `QMessageBox` call is replaced with the equivalent
`current_context.get_popup_opener()(...)` call, preserving the exact
same title/message text and the same branch semantics (a "declined"
result is whatever the old code did for anything other than
`StandardButton.Yes`/`.Save`/etc.). `editor.py`'s Save/Discard/Cancel
picks `"Cancel"` as the popup's default button (the safe, non-destructive
choice) — `QMessageBox`'s implicit default there wasn't a deliberate
design choice worth preserving byte-for-byte.

## Verification

- New `tests/verify/verify_desk_internal_popups.py`: constructs a
  `WorkspaceView`, calls `add_popup` directly, and checks: the popup
  frame has no visible lock/eye/bring/send-to-back buttons; its z-value
  is above every existing normal frame's; `_frame_z_values()` (used by
  normal `bring_to_front`/`send_to_back`) does not include it;
  `set_view_scale`/zoom rescaling still resizes its title/close button
  correctly at a non-1.0 scale; clicking a body button resolves
  `show`'s `on_result` with that button's label exactly once; the close
  (X) button resolves `None` and removes the popup from the scene;
  `clear_widgets()` resolves any still-open popup with `None` instead
  of leaving it dangling.
- Update each migrated widget's own existing verify script (wherever
  its `_confirm_*`/unsaved-changes flow is already covered) to exercise
  the new `current_context.get_popup_opener()` hook instead of
  mocking/patching `QMessageBox` directly (grep each first to find
  which ones actually patch `QMessageBox`).
- Full `tests/verify/` regression suite.
- Manual note: actually visually confirming the popup renders
  correctly at non-1.0 zoom requires a real windowed (non-offscreen)
  run — noting here per process if that step ends up skipped in an
  offscreen-only environment.
