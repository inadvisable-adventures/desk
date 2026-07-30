# Plan: TODO d4d6c71 (COMPLETED) — widget instance titlebar error indicator

From `../FEEDBACK/FEEDBACK-DESK-widget-error-visibility-2026-07-21-0053.md`:
no widget kind currently surfaces "this instance hit an error" anywhere in
the UI. Add a small, high-contrast `[ERROR]` titlebar button (mirroring the
existing `[STALE]`/`[TEMPUI]` button pattern in `widget_frame.py` exactly)
that lights up for:

1. A `kind: "html"`/`DefineWidget`/browser-kind widget's uncaught JS
   exception, unhandled promise rejection, or explicit `console.error()`
   call — all three already surface through `ChromiumWidget`'s existing
   `_LoggingWebEnginePage.javaScriptConsoleMessage` override at
   `ErrorMessageLevel` (confirmed: this is the same callback
   QtWebEngine/Chromium's own devtools console is backed by, so an
   uncaught exception reaching the browser's console reaches this
   callback too, not just an explicit `console.error(...)` call).
2. A `kind: "python"` widget's `build()`-time failure (`widget.py` fails
   to import/construct) — already caught today, per-instance, by
   `PythonWidgetHost._rebuild`'s own try/except, just not surfaced
   anywhere but the log.

   **Revised scope, found during implementation (see "Investigation"
   below):** the user's first choice was full runtime coverage — any
   exception anywhere in a `kind: "python"` widget's own code, e.g. a
   button's click handler, not just a build failure — via a new
   `QApplication.notify()` override attributing an exception to the
   enclosing `WidgetFrame`. Empirically confirmed this doesn't work:
   PyQt6 intercepts an exception escaping a Python slot/virtual-method
   override *at the point it escapes that specific callback* (calling
   `sys.excepthook`, then aborting the process) — it never propagates
   back up through the call stack to an outer `notify()` override's own
   try/except at all. There is no single centralized mechanism that can
   catch this class of exception without it already having been fatal;
   only a try/except at each individual call site (inside the widget's
   own code) actually works, which is a fundamentally different,
   much larger task than this TODO's scope (retrofitting every widget's
   own callbacks, not a one-time infra change). Presented this finding to
   the user directly; re-scoped to build-time-failure coverage only (the
   originally-recommended option) per their decision.

### Investigation: why a `notify()` override can't catch a python
    widget's runtime exception

Reproduced directly, not just reasoned about: a `QApplication` subclass
overriding `notify()` with `try: return super().notify(...) except
Exception: ...`, given a real widget whose `event()` override raises when
sent a real `QEvent` via `app.sendEvent(...)` — the process aborted
(`SIGABRT`), the `except` block never ran. This matches, and is already
documented by, this repo's own `LEARNINGS.md` (`810a5d6` entry): *"a
single global backstop now exists (`desk.crash_handler`, ...
`sys.excepthook`-based logger, which does **not** prevent the crash
itself, only records it), but each hazard still has to be found and
hardened at its own call site."* PyQt6's own internal exception handling
for a Python virtual-method reimplementation or signal/slot callback
intercepts an escaping exception right there (calling `sys.excepthook`
and then, by default, aborting) — a `notify()` override one or more
frames up the call chain never gets a chance to catch it via ordinary
Python exception propagation, because the C++ call stack in between
can't safely unwind through a Python exception at all. This is a hard
architectural constraint of this app's PyQt6 setup, not a mistake in the
override's own implementation.

Clicking the button shows the captured error text in a small dialog and
clears the indicator (mirrors `_on_widget_stale_clicked`'s
show-info-then-update-state shape).

## Design

### 1. Titlebar UI (`src/desk/shell/widget_frame.py`)

Mirrors `_StaleIndicatorButton`/`_TitleBar.set_stale`/`WidgetFrame.set_stale`
exactly, since that's the closest existing precedent for "a clickable,
conditionally-visible titlebar indicator button":

- `_ErrorIndicatorButton(QWidget)`: same shape as `_StaleIndicatorButton`
  (variable width sized to its own text, not a fixed square), label
  `"[ERROR]"`, but styled in a high-contrast red (the feedback's own "a
  red `!`, or similar" ask) via its `apply_scale`'s label stylesheet —
  the only chrome button with a non-default text color, deliberately, so
  it reads as urgent at a glance the way `[STALE]`'s neutral color
  doesn't.
- `_TitleBar`: `self.error_button = _ErrorIndicatorButton()`, added to
  the layout right after `self.stale_button` (grouping the three
  informational/indicator buttons — `[TEMPUI]`, `[STALE]`, `[ERROR]` —
  before the lock/front/back/close/eye/unlock action buttons, per the
  feedback's own "next to its `[TEMPUI]` button" framing). Wired into
  `_refresh_button_visibility` (`show and self._has_error`, same gating
  as `stale_button` — hidden in `title_only`/`greeked` chrome states,
  same as every indicator button except the eye button),
  `_visible_button_widgets_for_full_state`, and `apply_scale`. New
  `_button_target_width` entry (`"[ERROR]"` text).
- `_TitleBar.set_error(has_error: bool) -> None` mirrors `set_stale`.
- `WidgetFrame.set_error(has_error: bool, message: str = "") -> None`:
  stores `self.last_error_message = message`, calls
  `self._titlebar.set_error(has_error)`, `self._update_chrome_state()`
  (mirrors `set_stale`/`set_tempui_promotable`'s own shape exactly).

### 2. Click dispatch (`src/desk/shell/canvas.py`)

Mirrors the existing `stale` kind exactly:

- Add `_ErrorIndicatorButton` to `_hit_test_chrome`'s isinstance walk and
  its dispatch chain, returning `frame, "error"`.
- New `widget_error_clicked = pyqtSignal(WidgetFrame)` signal (alongside
  the existing `widget_stale_clicked`), emitted from
  `mouseReleaseEvent`'s `elif kind == "error":` branch.

### 3. `kind: "html"` wiring (`src/desk/shell/chromium_widget.py`)

`_LoggingWebEnginePage` already captures every console message including
`level == "error"` ones into its bounded `console_log` (TODO `9767c1a`,
serving the `introspect` capability) — reuse that classification instead
of duplicating it:

- New `_LoggingWebEnginePage.error_logged = pyqtSignal(str)`, emitted
  with the message text from inside `javaScriptConsoleMessage` whenever
  the classified level is `"error"` (right after appending to
  `console_log`, no behavior change to the existing buffer).
- `ChromiumWidget`: new `error_state_changed = pyqtSignal(bool, str)` —
  one signal covering both directions (`(True, message)` on a captured
  error, `(False, "")` on a reload) rather than two separate signals,
  so `DeskWindow` only needs one `connect(frame.set_error)` whose
  signature (`has_error: bool, message: str`) already matches
  positionally. Connects `self._logging_page.error_logged` to a small
  `_on_console_error(message)` that re-emits
  `error_state_changed.emit(True, message)`.
- `ChromiumWidget.reload()` override: emits
  `error_state_changed.emit(False, "")` (a hot-reloaded page starts
  fresh — same "reload clears stale-style state" convention `[STALE]`
  already establishes) before calling `super().reload()`. `HotReloadBroker
  .widget_changed` already routes through `_on_widget_changed` ->
  `self.reload()`, and `_on_widget_stale_clicked` already calls
  `frame.content.reload()` directly — overriding `reload()` itself
  (rather than adding a second method) covers both existing call sites
  for free, no other call site needs to change.
- `DeskWindow._place_widget`: new `self._bind_error_indicator(frame)`
  call (alongside the existing `_bind_external_indicator`/
  `_bind_event_mediator`), duck-typed the same way those already are —
  `if not isinstance(frame.content, ChromiumWidget): return`, else
  `frame.content.error_state_changed.connect(frame.set_error)`. A
  `kind: "python"` widget's `PythonWidgetHost` content has no such
  signal and is skipped here entirely — its errors are attributed a
  different way, see below.

### 4. `kind: "python"` wiring — `PythonWidgetHost.build_error_changed`

Mirrors `ChromiumWidget.error_state_changed`'s own `(bool, str)` shape:

- `PythonWidgetHost.build_error_changed = pyqtSignal(bool, str)`, plus a
  plain `self.build_error: str` attribute (`""` = no error). `_rebuild`'s
  existing except branch sets `self.build_error =
  traceback.format_exc()` and emits `(True, self.build_error)`; its
  success path sets `self.build_error = ""` and emits `(False, "")`.
- `DeskWindow._bind_error_indicator`: for a `PythonWidgetHost`, connects
  `build_error_changed` to `frame.set_error`, then immediately checks
  `content.build_error` and calls `frame.set_error(True, ...)` if
  already non-empty — same "connect, then check for already-happened
  state" shape `_bind_external_indicator` already uses, needed here
  because `_rebuild()` runs synchronously inside `PythonWidgetHost
  .__init__`, before any `WidgetFrame` wrapping it (and thus before this
  binding) exists yet.

### 5. Clicking the indicator (`src/desk/shell/window.py`)

Mirrors `_on_widget_stale_clicked`/`_confirm_stale_reload`'s
testability shape:

```python
def _on_widget_error_clicked(self, frame: WidgetFrame) -> None:
    if not frame.last_error_message:
        return
    self._confirm_widget_error_dismissed(frame.last_error_message)
    frame.set_error(False)

def _confirm_widget_error_dismissed(self, message: str) -> None:
    box = QMessageBox(self)
    box.setWindowTitle("Widget Error")
    box.setText("This widget instance hit an unhandled error.")
    box.setInformativeText(message)
    box.addButton("OK", QMessageBox.ButtonRole.AcceptRole)
    box.exec()
```

`self.view.widget_error_clicked.connect(self._on_widget_error_clicked)`
added alongside the existing `widget_stale_clicked` connection.
Acknowledging the dialog clears the indicator (same "diagnosed, now
handled" shape as reloading clears `[STALE]`) — a later error on the
same instance re-lights it.

## Verification

Extend `tests/verify/` (new script `verify_widget_error_indicator.py`,
mirroring `verify_stale_marker_click_dialog.py`'s `_FakeWindow`/real
click-hit-test-dispatch shape):

- **UI plumbing**: `[ERROR]` button hidden by default; `set_error(True, "boom")`
  shows it and stores `last_error_message`; a real click (`_hit_test_chrome`
  resolves to `(frame, "error")`, same as the existing stale-button click
  test) emits `widget_error_clicked`; `_on_widget_error_clicked` shows the
  dialog (via a recording `_confirm_widget_error_dismissed` override,
  same pattern as `_confirm_stale_reload_recording`) and clears the
  indicator afterward.
- **`kind: "html"` real capture**: a real `ChromiumWidget` (via
  `_place_widget`, pointed at a real locally-served `index.html` through
  `start_server`, same shape `verify_html_widget_local_storage.py`'s
  end-to-end test already establishes) whose page calls
  `console.error("boom")` — pump `app.processEvents()` until
  `error_state_changed` fires, confirm `(True, "boom")`; a separate page
  with an uncaught `throw new Error("boom2")` (no explicit `console.error`
  call) confirms the *uncaught exception* path specifically, not just
  literal `console.error` calls; confirm `reload()` emits
  `(False, "")` and clears `frame.last_error_message`.
- **`kind: "python"` real build-failure capture**: a real, on-disk
  `widget.py` whose `build()` raises, loaded via a real `PythonWidgetHost`
  and placed via `_place_widget` — confirm the frame is already showing
  `[ERROR]` immediately after placement (the pre-existing-state check in
  `_bind_error_indicator`, not a live signal); confirm `PythonWidgetHost
  .build_error` holds the traceback text. A second widget whose `build()`
  succeeds confirms no false positive. A hot-reload from a failing
  `build()` to a succeeding one (`broker.widget_changed.emit(...)` then
  a real `_rebuild()`) confirms `build_error_changed` fires `(False, "")`
  live and clears the indicator.
- Full `tests/verify/` regression suite.
