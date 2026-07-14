# Event message channel service (mediator topology)

TODO `6f9c51b`.

## Summary

Add a general-purpose, named-message pub/sub channel to Desk, following
the GoF **mediator** pattern: widgets never talk to each other directly —
they only ever talk to one shared component of Desk itself (the
mediator), which tracks who's subscribed to what and delivers a published
message to the right subscribers. Reachable from `kind: "html"` widgets
via the Bridge API and from `kind: "python"` widgets via direct import
(same "REST for html, direct Python for python widgets" split every
other Bridge capability already follows — see
`design-docs/architecture.md`). Every publish is logged by default to
`MEDIATED-EVENT-LOG.tsv` in the current Desk's directory. A new `Event
Log` python widget views that log, with a live-tail mode and a
clear-with-confirmation action. The Bridge API's own doc
(`tempui-custom-widgets.md`, reached from `desk-temporary-ui.md`) gets a
new section describing all this, via the existing `TEMPUI_DOC_VERSION`
bump process (see `plans/tempui-doc-versioning.md`).

## Design

### Core: `desk/event_mediator.py` (new, plain Python, no Qt)

A single `EventMediator` instance, constructed once for the whole app
run (mirroring `GuiBridge`), shared by:

- the Local Web Server's async Bridge API handlers (background thread) —
  for `kind: "html"` widgets, and
- `kind: "python"` widgets, in-process, via a small Qt wrapper (see
  below) — no HTTP involved, same reasoning as every other python-widget
  -facing capability.

Deliberately Qt-free so it's trivially headless-testable and has no
thread affinity of its own — thread-safety comes from a plain
`threading.Lock` around subscription bookkeeping and one
`queue.Queue` per subscribed instance (thread-safe by construction), the
same "no GUI-thread requirement, just real thread safety" shape
`SelfWriteMemory`/`desk_services.file_watcher` already use elsewhere in
this codebase.

API:

- `subscribe(instance_id, name)` / `unsubscribe(instance_id, name)` /
  `unsubscribe_all(instance_id)` — per-instance-id subscription
  bookkeeping, keyed by the caller's **instance** id (never the widget
  -definition id) per the request.
- `publish(name, payload, sender_instance_id) -> MediatedEvent` — logs
  the event (see below), then delivers it to every *other*
  currently-subscribed instance (the sender itself never receives its
  own publish back — the common pub/sub default, avoids trivial
  self-echo loops; documented explicitly in the Bridge API doc so it's
  not a surprise).
- `poll(instance_id, timeout) -> MediatedEvent | None` — blocking
  (`queue.Queue.get(timeout=...)`) wait for the next message for one
  instance. Used only by the Bridge API's long-poll REST handler
  (running in a background thread via `run_in_executor`, the same
  "block a worker thread, not the event loop" shape `GuiBridge.call`
  already uses for `run_on_gui`).
- `drain(instance_id) -> list[MediatedEvent]` — non-blocking, returns
  everything currently queued. Used by the Python-widget-facing
  `QTimer`-polling wrapper (below), which must never block the GUI
  thread.
- `set_log_directory(directory | None)` — where `MEDIATED-EVENT-LOG.tsv`
  lives; kept in sync with the current Desk directory the same place
  `current_context.set_current_desk_directory` already is
  (`DeskWindow._refresh_picker`, the established single choke point for
  this — see its own comment on why).
- `clear_all()` — drops every subscription/queue at once, for a full
  Desk switch (mirrors `_html_widget_local_storage.clear()` right next
  to where that already happens in `switch_desk`).
- `clear_log()` — truncates the log file back to just its header row
  (used by the Event Log widget's Clear action, after confirmation).

`MediatedEvent` is a small dataclass: `timestamp` (UTC ISO8601),
`name`, `sender_instance_id`, `payload` (arbitrary JSON-serializable
data).

No REST/browser/python-widget caller is trusted to have already
JSON-encoded `payload` for the log — `json.dumps(payload,
separators=(",", ":"))` happens once, inside `_log`, with a
`repr()`-based fallback (still wrapped in `json.dumps` so the row stays
a well-formed TSV cell) if a python-widget-originated payload isn't
JSON-serializable at all. `json.dumps` also happens to make the log
TSV-safe for free: it escapes literal tabs/newlines inside a string
value to `\t`/`\n` two-character escapes, so a payload can never break
the TSV's own column/row structure.

### `MEDIATED-EVENT-LOG.tsv` format

Header row, then one row per publish, tab-separated:

```
timestamp	event_name	sender_instance_id	payload
2026-07-14T18:03:11.482911+00:00	todo.item_added	a1b2c3d4	{"id":"6f9c51b"}
```

Lives at the current Desk directory's root, alongside `TODO.md`/
`PARKINGLOT.md`/`QUESTIONS.md` — same "well-known file at the Desk
root" convention those already follow. Append-only from `EventMediator`
itself; only the Event Log widget's confirmed Clear action ever
truncates it (back to just the header row, not deleted — so a live
watcher sees a valid, still-existing TSV rather than a missing file).

### Bridge API: REST endpoints (`src/desk/server/app.py`)

New capability string `"events"` (capabilities are already
freeform strings per widget.json — `desk.widgets._parse_manifest`
does no fixed-enum validation — so this needs no schema change).
`create_app` gains an `event_mediator: EventMediator | None = None`
parameter (same optional-with-a-clear-503-if-missing shape
`gui_bridge` already has).

- `POST /api/bridge/events/subscribe` `{names: [str]}`
- `POST /api/bridge/events/unsubscribe` `{names: [str]}`
- `POST /api/bridge/events/publish` `{name: str, payload: Any}`
- `GET /api/bridge/events/poll?timeout=<seconds>` — long-poll; server
  -side clamps `timeout` to a max (30s) so one caller can't pin a
  background thread indefinitely. Returns `{event: {...} | null}`.

All four require both the `events` capability (`require_caller`) and
the calling instance's id (`require_instance_id`, the existing
`X-Desk-Instance-Id`-header dependency) — this *is* "the Bridge API
handling identity, using instance id not widget id" from the request:
`require_instance_id` already exists and is exactly this; `events.*`
just becomes its second consumer after `self.*`.

`publish`/`poll` run the (potentially blocking) mediator call via
`loop.run_in_executor(None, ...)`, the same pattern `run_on_gui`
already uses to avoid blocking the async event loop — `subscribe`/
`unsubscribe` are fast enough (just lock + set mutation) to call
inline.

### Bridge API: JS client (`src/desk/server/bridge_client.py`)

```js
desk.events = {
  subscribe: (names) => call("POST", ".../events/subscribe", { names }),
  unsubscribe: (names) => call("POST", ".../events/unsubscribe", { names }),
  publish: (name, payload) => call("POST", ".../events/publish", { name, payload }),
  onMessage: (callback) => { ... starts a background long-poll loop ... },
};
```

`onMessage` registers a callback and (if not already running) starts an
internal `async` loop that repeatedly calls the poll endpoint and
invokes every registered callback with `(name, payload,
senderInstanceId)` on each arrived event, looping again immediately.
No `offMessage` in this first cut — a widget's whole page (and its
in-flight fetch) is torn down when the widget closes, so there's
nothing to leak in the common case; documented as a known simplification
in the Bridge API doc rather than silently omitted.

### Python widgets: `desk/shell/event_broker.py` (new) + a generic bind hook

`kind: "python"` widgets never make an HTTP call for this (same as
every other python-widget capability) — but the shared `EventMediator`
is queue/blocking-based, which a GUI-thread Qt widget can't call
directly without freezing the UI. `EventSubscription(QObject)` wraps
this the same way `HotReloadBroker`/`SingleFileWatcher` already wrap a
non-Qt-native source into Qt signals:

- Subscribes to the given names on construction.
- A `QTimer` (default 150ms) calls `mediator.drain(instance_id)`
  (non-blocking) and re-emits each arrived message as a
  `message_received(name, payload, sender_instance_id)` Qt signal.
- `publish(name, payload)` / `subscribe(name)` / `unsubscribe(name)`
  convenience methods, delegating straight to the mediator.
- Cleans itself up via its own `destroyed` signal connected to a
  closure holding only plain captured values (`mediator`,
  `instance_id`), calling `mediator.unsubscribe_all(instance_id)` — the
  same "don't connect an object's `destroyed` to its own bound method,
  it never fires" fix already recorded in `LEARNINGS.md` for
  `TerminalWidget`'s own PTY cleanup. A widget parents its
  `EventSubscription` to itself, so Qt's normal parent/child deletion
  cascade (widget removed → `deleteLater()` → child `EventSubscription`
  destroyed → this fires) needs no extra wiring anywhere.

A widget opts in by defining an optional `bind_event_mediator(self,
instance_id, mediator)` method — duck-typed and generically called for
*every* placed python widget from a new `DeskWindow._bind_event_mediator`
(`_place_widget`, right alongside the existing generic
`_bind_external_indicator` call), mirroring `_bind_claude_widget`'s
"duck-typed on `start_session` so `window.py` needn't import the widget
class" reasoning exactly. No existing widget currently has any way to
learn its own instance id at `build()` time (confirmed: only the Claude
widget ever receives one, and only via this exact `_bind_*`-after
-placement style, not through `build()`'s signature) — this establishes
the same shape for events rather than changing the `build() -> QWidget`
contract.

### Wiring it all together

- `src/desk/server/runner.py`: `start_server` constructs one
  `EventMediator()` alongside `GuiBridge()`, passes it into
  `create_app(...)`, and exposes it as `ServerHandle.event_mediator`.
- `src/desk/shell/window.py`: `self._event_mediator =
  handle.event_mediator` (no new constructor parameter needed —
  `DeskWindow` already receives `handle`). Wired into
  `current_context.set_event_mediator` alongside the other `set_*`
  hooks at the end of `__init__`. `_refresh_picker` gains one line:
  `self._event_mediator.set_log_directory(self.current_desk.directory)`
  (same choke point `current_context.set_current_desk_directory`
  already uses, for the same reason). `switch_desk` gains
  `self._event_mediator.clear_all()` right next to the existing
  `self._html_widget_local_storage.clear()`. `close_widget_by_
  instance_id`/`close_widget` each gain a
  `self._event_mediator.unsubscribe_all(instance_id)` call — belt
  -and-suspenders for `kind: "html"` widgets specifically, since
  they have no `destroyed`-signal-based cleanup path the way python
  widgets do (harmless no-op if a python widget's own subscription
  already cleaned itself up first).
- `src/desk/shell/current_context.py`: new `set_event_mediator`/
  `get_event_mediator` hook pair, same minimal shape as every other
  hook already there.

### `widgets/event_log/` (new python widget)

- Resolves its log path the same way the TODO widget resolves
  `TODO.md`: `current_context.get_current_desk_directory() /
  desk.event_mediator.LOG_FILENAME`. Does **not** go through the live
  `EventMediator` instance for reading/clearing — it reads/truncates
  the TSV file directly, the same "just read/write the well-known
  file" shape the TODO/Parking Lot/Questions widgets already use. This
  keeps it decoupled from whether a mediator happens to be wired up at
  all, and matches how none of those other file-backed widgets go
  through some other live in-memory owner either.
- Display: a read-only `QTableWidget` (Timestamp / Event / Sender /
  Payload columns), parsed via `csv.reader(..., delimiter="\t")`
  (skip the header row), the same tabular-display building block the
  Sheet widget already uses.
- Live tail: a `SingleFileWatcher` (exact same reused component the
  TODO widget already watches `TODO.md` with) always keeps the table's
  content fresh; a checkable "Live Tail" toolbar button controls only
  whether new rows auto-scroll the view to the bottom — content itself
  always stays current regardless of the toggle, avoiding a second,
  separate "reload" affordance (matching this app's established
  preference for file-watching over manual reload buttons, e.g. TODO
  `d25e557` removing the TODO widget's Reload button outright).
- Clear button: `QMessageBox.question`-based confirmation, split into
  its own `_confirm_clear` method for headless testability (exact
  pattern already used by `CrashLogWidget._confirm_delete`), then
  overwrites the log file with just its header row (not delete —
  `SingleFileWatcher` still has something valid to watch afterward).

### Bridge API doc update (`tempui-custom-widgets.md` / `src/desk/temp_ui.py`)

Per the existing tempui-doc versioning process
(`plans/tempui-doc-versioning.md`): edit `_CUSTOM_WIDGETS_DOC` in
`src/desk/temp_ui.py` (the source of truth `tempui-custom-widgets.md`
is rendered from) to add a new subsection under "The Desk Bridge API"
covering `desk.events.subscribe/unsubscribe/publish/onMessage`, the
sender-never-receives-its-own-publish rule, the `events` capability
requirement, and a pointer to `MEDIATED-EVENT-LOG.tsv` for anyone
wanting to inspect traffic outside the new widget. Bump
`TEMPUI_DOC_VERSION` from 6 to 7 with an updated explanatory comment
-- a real new section, exactly the kind of change that constant's own
comment says warrants a bump (not a typo-fix). This is a *meaningful*
content change (not just this one file's docstring), so
`ensure_docs_current`'s existing refresh mechanism (already built,
untouched here) is what actually gets it in front of every
already-provisioned Desk directory, not a special case.

`design-docs/architecture.md` also gets one short addition: a mention
of the events capability alongside the existing
workspace/fs/widgets/self capability list, and a note that this is the
first Bridge API capability with a push/streaming shape (long-polled,
not a true WebSocket — the existing `/ws` echo endpoint stays
unused/vestigial, same as before; see design decision below for why).

## Key design decisions

- **Long-polling over the existing `/ws` WebSocket endpoint.** TODO
  `47b5731` explicitly decided against a push channel because its only
  cited use case (PTY streaming) became moot once the Console widget
  went native-Qt. That reasoning doesn't carry over here — this
  feature's whole point *is* push delivery — but a true WebSocket
  still isn't the better fit: browser `WebSocket` can't attach the
  custom `X-Desk-*` auth/identity headers the entire rest of the Bridge
  API relies on (only cookies/query-string/subprocotol are available at
  handshake time), so it would need its own bespoke auth path instead
  of reusing `require_caller`/`require_instance_id` as-is. A long-poll
  REST endpoint reuses both unchanged and stays consistent with "REST
  for request/response" as the Bridge API's one established shape.
  Trade-off accepted: each long-polling widget pins one background
  -thread-pool worker (via `run_in_executor`) for up to 30s at a time.
  Fine at this app's actual scale (a handful of widgets in one local,
  single-user desktop app) — noted here rather than silently accepted,
  per "no silent caps."
- **Sender excluded from its own publish.** Not specified by the
  request; chosen as the least-surprising pub/sub default (avoids
  trivial self-echo) and documented explicitly in the Bridge API doc
  so it's a documented decision, not a hidden gotcha.
- **`EventSubscription` (Qt wrapper) polls a non-blocking `drain()` via
  `QTimer`, not a background thread bounced through a cross-thread Qt
  signal (the `GuiBridge`/`HotReloadBroker` shape).** Simpler, and
  correct here specifically because delivery to a python widget never
  needs to block anything — unlike `GuiBridge.call`, which exists
  because the *caller* (an HTTP handler) genuinely needs to wait for a
  GUI-thread result before it can respond. Nothing here needs that.
- **Widgets get event capability via a duck-typed `bind_event_mediator`
  hook, not a `build()` signature change.** Consistent with every
  existing per-widget special case in `_place_widget`
  (`start_session`, `set_file`, `external_path_changed`) — the
  established way this codebase gives an already-built widget instance
  something it couldn't know at `build()` time.

## Affected files

- `src/desk/event_mediator.py` (new) — `EventMediator`, `MediatedEvent`,
  `LOG_FILENAME`, log read/parse/clear helpers shared with the widget.
- `src/desk/shell/event_broker.py` (new) — `EventSubscription`.
- `src/desk/server/app.py` — `events` capability, four new routes.
- `src/desk/server/bridge_client.py` — `desk.events.*` JS client.
- `src/desk/server/runner.py` — construct/wire `EventMediator`.
- `src/desk/shell/window.py` — wiring described above.
- `src/desk/shell/current_context.py` — new hook pair.
- `widgets/event_log/widget.json`, `widgets/event_log/widget.py` (new).
- `src/desk/temp_ui.py` — `_CUSTOM_WIDGETS_DOC` addition,
  `TEMPUI_DOC_VERSION` bump 6 → 7.
- `design-docs/architecture.md` — brief capability-list/push-shape note.

## Verification

Headless (`QT_QPA_PLATFORM=offscreen` where Qt is involved; plain
function/`TestClient` tests otherwise):

- `EventMediator`: subscribe/publish delivers to a subscribed instance,
  never back to the sender; unsubscribe/unsubscribe_all/clear_all all
  correctly stop further delivery; `poll` blocks and returns `None` on
  a real timeout, returns the event immediately once published from
  another thread; `drain` is non-blocking and returns everything
  queued; log file gets a header + one well-formed TSV row per publish
  (including a payload containing a literal tab/newline, confirming
  the `json.dumps` escaping keeps the row intact); `clear_log` leaves
  just the header, and a further publish appends correctly after a
  clear (no stray extra header).
- Bridge API routes, via FastAPI's `TestClient` against `create_app`
  directly (matching how the existing bridge endpoints were originally
  verified): subscribe → publish from a second simulated instance →
  poll returns it; missing `events` capability → 403; poll respects
  the timeout clamp; identity is genuinely per-instance-id (two
  instances of the same widget *id* have independent subscriptions).
- `EventSubscription`: a real `QTimer`-driven instance (real
  `QApplication`, offscreen) receives a message published from a
  plain-Python thread via its Qt signal; `destroyed`-triggered cleanup
  actually calls `unsubscribe_all` (regression-checked against the
  known "connecting an object's own `destroyed` to its own bound
  method never fires" trap — confirmed the plain-closure form here
  does fire).
- `DeskWindow._bind_event_mediator`: a fake python widget exposing
  `bind_event_mediator` gets called with its real instance id and the
  real mediator when placed via a real `DeskWindow`; one placed
  instance publishing is received by a second subscribed instance,
  end to end.
- `widgets/event_log`: parses a hand-written TSV fixture into the
  table correctly; `SingleFileWatcher`-driven live update on a real
  on-disk append; Live Tail toggle controls auto-scroll only, not
  whether content refreshes; Clear button requires confirmation
  (declining leaves the log untouched) and, once confirmed, leaves
  just the header row on disk.
- `ensure_docs_current`: a stale (`TEMPUI_DOC_VERSION` still 6) doc
  directory gets refreshed to 7 with the new events section present,
  same regression coverage `plans/tempui-doc-versioning.md` already
  established for this mechanism.
- Full scratchpad regression suite re-run.

## Status

Not yet implemented — plan written first per `development-process.md`.
