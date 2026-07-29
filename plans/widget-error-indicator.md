# Plan: TODO d4d6c71 — widget instance titlebar error indicator

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
2. A `kind: "python"` widget's runtime exception, from **anywhere** in its
   own code (not just a `build()`-time failure) — per direct user
   decision, via a new `QApplication.notify()` override that wraps every
   Qt event dispatch app-wide and attributes an exception to the
   enclosing `WidgetFrame` by walking the receiver's `QObject` parent
   chain. This deliberately makes the *whole app* resilient to an
   uncaught exception during event dispatch, not just widget content —
   see "Scope note" below.

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

### 4. `kind: "python"` wiring — `QApplication.notify()` override

New file `src/desk/shell/app_notify.py`:

```python
class DeskApplication(QApplication):
    def notify(self, receiver, event) -> bool:
        try:
            return super().notify(receiver, event)
        except Exception:
            logger.error("Uncaught exception dispatching %s to %r", event.type(), receiver, exc_info=True)
            frame = _enclosing_widget_frame(receiver)
            if frame is not None and isinstance(frame.content, PythonWidgetHost):
                message = traceback.format_exc()
                QTimer.singleShot(0, lambda f=frame, m=message: f.set_error(True, m))
            return False
```

- `_enclosing_widget_frame(receiver)`: walks `receiver.parent()`
  (`QObject.parent()`, works for any `QObject`, not just `QWidget`)
  until it finds a `WidgetFrame` instance or runs out of ancestors.
- Deferred via `QTimer.singleShot(0, ...)` rather than calling
  `frame.set_error` synchronously from inside `notify()` itself —
  `notify()` is about as reentrancy-sensitive a call stack as this
  codebase has (it's *the* dispatch point for literally every Qt
  event); deferring one event-loop turn is the same defensive shape
  already used elsewhere here for exactly this kind of concern (see
  `WidgetFrame._reassert_size`'s own comment).
  `src/desk/app.py`: `app = DeskApplication(sys.argv)` instead of the
  plain `QApplication` — the only call site that needs to change.

#### Scope note (explicit, per direct user decision)

Catching every exception during `notify()` app-wide is necessarily
uniform — there's no way to try/except only for "receivers that happen
to live inside a widget's own content" *before* the exception has
already happened and been walked back to its receiver. A structural side
effect: an uncaught exception anywhere in Desk's own chrome code (not
just widget content) now also gets caught and logged here instead of
propagating (previously fatal in this app, per `crash_handler.py`'s own
docstring and several existing call-site comments describing exactly
that). This is an intentional, disclosed consequence of the chosen
approach (full runtime coverage), not an accidental scope expansion —
still fully logged (via `logger.error(..., exc_info=True)`, same
diagnostic visibility `crash_handler.py`'s existing global
`sys.excepthook` already provides, just one layer earlier and with
per-widget attribution when a `WidgetFrame` is found in the receiver's
ancestry). `crash_handler.py`'s own `sys.excepthook` installation is
unchanged and stays as a second, independent safety net for anything
`notify()` itself doesn't cover (e.g. an exception raised outside any
Qt event dispatch at all).

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
- **`kind: "python"` real notify() capture**: a real `DeskApplication`,
  a real `WidgetFrame` wrapping a real `PythonWidgetHost`-hosted widget
  whose button click handler raises — dispatch a real `QMouseEvent`/
  direct `event()` call so it genuinely goes through `notify()`, confirm
  `frame.set_error(True, ...)` was called (via `app.processEvents()` to
  let the deferred `singleShot(0)` fire) and the app did not crash;
  confirm a subsequent, unrelated event still dispatches normally
  afterward (the override doesn't wedge the event loop); confirm an
  exception with no enclosing `WidgetFrame` in its receiver's ancestry
  is still caught (doesn't crash the process) even though no indicator
  lights up anywhere.
- Full `tests/verify/` regression suite.
