# Event Poster widget

TODO `dc557b2`.

## Summary

A general-purpose `kind: "python"` widget for manually composing and
sending a named message over Desk's existing event mediator channel
(TODO `6f9c51b`, `desk.event_mediator`/`desk.shell.event_broker`) — a
hand-operated companion to the read-only Event Log widget
(`widgets/event_log/`), useful for testing/demoing a widget's
`bind_event_mediator`/`desk.events.onMessage` subscription handling
without having to script a real publisher.

Ships as `widgets/event_poster/`: an event-name field, a payload text
box, a Publish button, and a status line reporting the outcome.

## Design

### UI

- **Name** — a single-line `QLineEdit` (placeholder `event.name`,
  e.g. `"todo.item_added"`), matching the doc's convention of
  arbitrary agreed-upon strings. `returnPressed` also triggers publish
  (single-line field, so Enter has no competing "insert newline"
  meaning).
- **Payload** — a multi-line `QPlainTextEdit` (placeholder showing an
  example, e.g. `{"key": "value"} or plain text`), left empty for a
  `null` payload. Ctrl+Return also triggers publish, mirroring the
  TODO widget's item editor (TODO `8db7891`) — plain Return inserts a
  newline as normal multiline editing.
- **Publish** button — click triggers the same publish path.
- **Status label** — reports the outcome of the last publish attempt,
  or why publishing isn't currently possible (not yet bound to the
  event mediator, empty event name).

Neither field is cleared after a successful publish — this is a
repeated-testing tool (re-send the same or a tweaked message multiple
times while iterating on a subscriber elsewhere), not a one-shot form.

### Payload parsing

The payload box accepts either real JSON or plain text, since the doc
says payload is "any JSON-serializable value" but a tester typing
unquoted plain text (`ping`, not `"ping"`) is a common, reasonable
expectation for a quick manual test:

```python
def _parse_payload(text: str) -> tuple[object, bool]:
    text = text.strip()
    if not text:
        return None, True  # true == "was valid/deliberate JSON (or empty)"
    try:
        return json.loads(text), True
    except ValueError:
        return text, False  # fall back to the raw text as a string payload
```

The status label reflects which branch was taken (`(JSON payload)` /
`(text payload)` / `(no payload)`), so a user who *meant* to type JSON
and made a syntax mistake still gets useful feedback instead of a
silent misinterpretation.

### Binding to the event mediator

Same `bind_event_mediator(self, instance_id, mediator)` duck-typed
hook every mediator-aware python widget implements (TODO `6f9c51b`,
`DeskWindow._bind_event_mediator`) — constructs a
`desk.shell.event_broker.EventSubscription(mediator, instance_id)`
with no subscribed names (this widget only ever sends, never
receives) purely to get a correctly-identified `.publish(name,
payload)` call (it needs the *real* instance id as sender, which
`current_context.get_event_mediator()` alone can't provide — see how
`widgets/event_log/widget.py`'s `_clear_log` uses `current_context`
only for an operation that doesn't need a sender identity). The
Publish button (and Enter/Ctrl+Return shortcuts) are disabled until
this binding arrives, with the status label explaining why — mirrors
`widgets/event_log/widget.py`'s "No Desk directory available yet."
pattern for a widget that isn't fully wired up yet. In the real app
this binding happens synchronously at placement
(`DeskWindow._place_widget`), so in practice the window is only
unusable for a fraction of a placement call — the guard exists mainly
for headless construction (`build()` called standalone, e.g. in
tests) where no binding ever arrives.

## Affected files

- `widgets/event_poster/widget.json` — new manifest (`kind: "python"`,
  no capabilities needed — direct in-process access, same as
  `widgets/event_log/`).
- `widgets/event_poster/widget.py` — the widget.

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`):

- `_parse_payload`: empty → `(None, True)`; valid JSON object/array
  /number/string → parsed value, `True`; invalid JSON plain text →
  the raw string, `False`.
- Before `bind_event_mediator` is called: Publish disabled, status
  explains why; clicking/Enter/Ctrl+Return are no-ops.
- After binding to a real `EventMediator` (constructed directly, no
  server needed — same as TODO `6f9c51b`'s own core-mediator tests):
  clicking Publish with a name and a JSON payload delivers a
  correctly-shaped `MediatedEvent` (right name, right payload, right
  `sender_instance_id`) to another subscribed instance; an empty
  payload delivers `None`; a non-JSON payload delivers the raw text
  string; an empty event name is rejected client-side (no publish
  call reaches the mediator) with a status message, not a crash.
- `returnPressed` on the name field and Ctrl+Return in the payload
  box both trigger the same publish path as the button (exercised via
  the real widgets' signals/`keyPressEvent`, not by calling the
  handler directly).
- Fields retain their text after a successful publish (not cleared).
- `discover_widgets()` picks up the new manifest; a real
  `PythonWidgetHost` builds a working `EventPosterWidget`; a full
  `DeskWindow`-level regression places a real instance and confirms
  `_bind_event_mediator` wires it up via the same generic,
  widget-agnostic path every other mediator-aware widget already uses
  (no widget-specific code needed in `window.py`).

## Status

Not yet implemented — plan written first per `development-process.md`.
