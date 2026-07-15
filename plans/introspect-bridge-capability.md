# Bridge API introspection service: DOM snapshot + console log of another html widget

TODO `9767c1a`.

## Summary

A new Bridge API capability, `introspect`, letting one `kind: "html"`
widget ask for a tree-view DOM snapshot and buffered console log of
*another* `kind: "html"` widget instance — gated by an actual,
in-the-moment confirmation dialog shown to the Desk user (not just a
static capability declaration, unlike every existing Bridge
capability), since this is a materially more sensitive ability than
anything else the Bridge API currently grants: it lets one widget see
another's rendered content and console output, not just its own state
or Desk-level metadata.

## Design

### Two new technical pieces needed first

1. **Console log capture.** `QWebEnginePage.javaScriptConsoleMessage`
   (confirmed: a virtual method to override, not a Qt signal) is the
   only way to observe a page's own `console.log`/`warn`/`error`
   output. `ChromiumWidget` currently uses the view's default,
   auto-created page — it needs an explicit, small
   `_LoggingWebEnginePage(QWebEnginePage)` subclass overriding this
   method into a bounded rolling buffer (last 200 entries: level,
   message, line number, source), set via `view.setPage(page)` before
   `.load(...)`. Every `kind: "html"` widget gets this buffer
   unconditionally (small, fixed memory cost) — not opt-in, since it's
   a passive log source queried on demand, not something that runs
   differently based on whether anyone ever asks for it.
2. **Bridging an async Qt callback into a synchronous cross-thread
   call.** Existing `GuiBridge.call(fn)` requires `fn()` to return its
   result *synchronously* on the GUI thread. A DOM snapshot needs
   `page().runJavaScript(js, callback)`, which is asynchronous —
   `callback` fires later, from the GUI thread's own event loop. If
   `fn()` tried to block waiting for that callback (e.g. via a
   `threading.Event.wait()` called from *inside* `fn()`, itself already
   running as a GUI-thread slot), the GUI thread's event loop could
   never get back around to actually running the queued callback that
   would unblock it — a real, self-inflicted deadlock (confirmed
   directly hitting the equivalent version of this exact deadlock shape
   while verifying TODO `f693275`, from a different angle: driving a
   `GuiBridge`-routed call from the same thread that owns the event
   loop). Fixed with a new `GuiBridge.call_async(starter)`: `starter
   (resolve)` runs on the GUI thread (via a second, dedicated
   fire-and-forget signal, not reusing `_call_requested`'s own
   "call fn then immediately mark done" semantics) and must return
   *without* blocking, after kicking off whatever async Qt operation it
   needs; `resolve(value)` -- called later, whenever that operation's
   own callback actually fires, itself back on the GUI thread's event
   loop, which stayed free the whole time -- is what actually completes
   the call. Only the *original calling* thread (a background executor
   thread, via `run_in_executor`, same as every existing Bridge
   GUI-thread call) ever blocks.

### The Bridge API surface

- New capability string: `introspect`.
- `POST /api/bridge/introspect/snapshot` `{target_instance_id}` →
  `{dom: {...tree...}, console: [{level, message, line, source}, ...]}`.
  Requires the *caller* to declare `introspect` (`require_caller`) and
  identifies the caller via `require_instance_id`, same shape as every
  other capability-gated route.
- `desk.introspect.snapshot(targetInstanceId)` added to the JS Bridge
  client (`bridge_client.py`).

### The permission gate

Before the first successful snapshot for a given **(caller instance id,
target instance id)** pair in a session, `DeskWindow` shows a blocking
confirmation dialog (the same `QMessageBox.question`-via-`_confirm_fn`
shape every other consequential action already uses): *"`<caller
widget name>` wants to inspect `<target widget name>`'s DOM and console
log. Allow?"* (both names resolved from their `WidgetInfo`/instance,
not raw instance ids, for readability). Declining returns a `403` with
no data captured or leaked. Approving records the grant in a new,
in-memory `DeskWindow._introspect_grants: set[tuple[str, str]]`, so a
widget that's been granted once (e.g. a live DOM/console viewer that
legitimately polls) isn't re-prompted every call — this is a real,
anticipated use shape (TODO `7505703`'s "view all registered widgets"
item is exactly the kind of thing that would poll). Grants are
per-session, in-memory only (never persisted to `.desk`/disk) and
cleared on Desk switch, alongside the other per-instance state
`switch_desk` already clears (`_html_widget_local_storage.clear()`/
`_event_mediator.clear_all()`) — asking again after a switch is the
safe default; there's no existing "remember a security-relevant grant
across restarts" mechanism anywhere in this codebase to extend instead
of inventing one un-designed here.

The permission check itself runs via the *existing*, synchronous
`GuiBridge.call`/`run_on_gui` (showing a blocking modal is itself
already a normal blocking GUI operation, same as every other
`_confirm_fn` call site) — kept as a separate GUI-thread round-trip
from the `call_async`-based DOM snapshot itself, rather than combined
into one call, to keep "blocking modal dialog" and "non-blocking async
Qt callback" as two clearly separate concerns.

### DOM snapshot shape

A small, self-contained JS snippet (`DOM_SNAPSHOT_JS`, a Python string
constant next to `BRIDGE_CLIENT_TEMPLATE`) walks `document.documentElement`
and returns a plain JSON tree: `{tag, attrs, children}` for an element,
`{text}` for non-empty text content — bounded (max depth ~12, max ~50
children per node, attribute/text values truncated to 200 chars) so a
pathological page can't produce an unbounded payload.

## Affected files

- `src/desk/shell/bridge.py` — `GuiBridge.call_async`.
- `src/desk/shell/chromium_widget.py` — `_LoggingWebEnginePage`,
  wiring it into `ChromiumWidget`, `get_console_log()` accessor.
- `src/desk/shell/window.py` — `_introspect_grants`, a
  `request_introspect_permission(caller_instance_id, target_instance_id)
  -> bool` method (shows the dialog, records/reuses the grant), a
  `start_dom_snapshot(target_instance_id, resolve)` method (the
  `call_async` starter), `switch_desk`'s grant-clearing.
- `src/desk/server/app.py` — `introspect` capability, the new route.
- `src/desk/server/bridge_client.py` — `desk.introspect.snapshot`.
- `src/desk/temp_ui.py` — `_CUSTOM_WIDGETS_DOC` gains a short mention
  (capability table + one paragraph) so a `DefineWidget` widget author
  knows this exists; `TEMPUI_DOC_VERSION` bump.
- `design-docs/architecture.md` — capability table + Security
  Considerations note (this is the first Bridge capability requiring
  an interactive user confirmation, not just a static declaration —
  worth calling out there specifically).

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication`/
`QWebEngineView`, a real running server + real `DeskWindow`, same shape
established for TODO `f693275`'s verification, including driving any
`GuiBridge`-routed HTTP call from a background thread while the main
thread pumps `processEvents()` — required for `call_async` too, for
the same reason):

- `GuiBridge.call_async`: a `starter` that kicks off a real, genuinely
  -async operation (e.g. `QTimer.singleShot` from within `starter`
  calling `resolve` later, standing in for `runJavaScript`'s own
  callback shape) resolves correctly without deadlocking; an exception
  raised synchronously inside `starter` propagates to the caller; a
  `starter` that never calls `resolve` times out cleanly rather than
  hanging forever.
- `_LoggingWebEnginePage`: real `console.log`/`warn`/`error` calls from
  a loaded page are captured, in order, with the right level; the
  buffer is bounded (a page logging far more than the cap doesn't grow
  unbounded).
- Permission flow: first snapshot request for a given (caller, target)
  pair shows the confirmation dialog and blocks on it; declining
  returns `403` with no snapshot data in the response; approving
  returns real data and a second request for the *same* pair does not
  re-prompt; a request for a *different* target from the same caller
  does prompt again; grants are cleared on `switch_desk`.
- DOM snapshot: a real loaded page with nested elements and text
  produces a correctly-shaped, correctly-nested tree; a pathological
  deeply-nested/wide page is bounded (depth/child-count/text-length
  caps all confirmed to actually kick in, not just documented).
- End-to-end: capability-declared widget A successfully snapshots
  widget B's real DOM/console after approving the prompt; a widget
  without the `introspect` capability still `403`s before ever
  reaching the permission dialog at all (capability gate checked
  first); a request naming a target instance id that doesn't exist (or
  isn't a `kind: "html"` widget) `400`s.

## Status

Not yet implemented — plan written first per `development-process.md`.
