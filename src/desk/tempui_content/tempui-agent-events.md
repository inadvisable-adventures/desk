# Agent-raised desk events and waiting for them (agent <-> widget)

See `desk-temporary-ui.md` (in this same directory) for this
directory's own overview and its current set of tags. This is not a
tempui-DSL file type: it is two MCP tools on the `desk` server that connect
an agent to the same `desk.events` channel widgets use to talk to each
other, so an agent and a running widget can signal each other directly
instead of through a file one of them has to poll.
`desk_raise_event` sends an event to widgets; `desk_wait_for_event` waits
for one a widget sends.

## Raising an event

`desk_raise_event { "name": "<event name>", "payload": <any JSON, optional> }`

- Every widget instance subscribed to `name` receives it at once: an
  `html` widget through `desk.events.onMessage(callback)` (declare the
  `events` capability and call `desk.events.subscribe([name])` first), a
  `python` widget through `desk.shell.event_broker.EventSubscription`.
  The widget's callback sees `(name, payload)`, exactly as for an event
  another widget published.
- `payload` may be left out for a bare signal (a message that means "I
  updated the file"), or carry the data you would otherwise have written
  to a file (see "A signal, or the data itself" in
  `tempui-custom-widgets.md`). Keep it small: a message over about 1 KB
  should usually be a file, with the event only announcing it (for example
  `{ "path": ".desk_temp/foo.json" }`). The hard limit is 64 KiB of JSON;
  a bigger payload is refused, not truncated.
- `name` is any non-empty string up to 200 characters. Pick a specific
  one, since every widget that subscribes to a name receives it
  (`"samothrace-map.question"`, not `"question"`). Names starting with
  `desk.` and the names `recording` and `stopped_recording` are Desk's
  own and are refused.
- The result says how many widget instances were subscribed to `name` at
  the moment of publishing. `0` means nobody was listening (the widget
  is not placed, has not subscribed yet, or subscribes to another name);
  the event is not queued for later and is not delivered to a widget
  that subscribes afterward. The count is a snapshot, not a delivery
  guarantee.
- The event is also recorded in the Event Log (`MEDIATED-EVENT-LOG.tsv`),
  with the sender shown as `agent`.
- Like any other `desk` tool call, it asks the user for approval through
  Claude (Desk)'s normal approval flow.

## Worked example

A widget subscribes once, then reacts:

```
await desk.events.subscribe(["samothrace-map.question"]);
desk.events.onMessage((name, payload) => {
  if (name === "samothrace-map.question") showQuestion(payload);
});
```

and the agent asks it a question:

```
desk_raise_event { "name": "samothrace-map.question",
                   "payload": { "id": "q1", "prompt": "Is this connection correct?" } }
```

The widget's answer travels the other way as an ordinary `desk.events`
publish (`desk.events.publish("samothrace-map.answer", {...})`), which the
agent receives with `desk_wait_for_event`, below.

## Waiting for an event

`desk_wait_for_event { "name": "<event name>", "timeout_seconds": <optional> }`

Blocks until an event named `name` is published and returns JSON:

- `{ "status": "event", "name", "payload", "sender", "timestamp" }` -- the
  event. `sender` is the publishing widget instance's id; `payload` is
  `null` for a bare signal.
- `{ "status": "timeout", ... }` -- only if you passed `timeout_seconds`.
  Omit it to wait with no timeout.
- `{ "status": "ended", ... }` -- Desk was switched, which drops every
  subscription; nothing more will arrive on this call.

**Call it from a background sub-agent, never from the main conversation.**
With no timeout it can wait for hours, and while it waits the agent that
called it can do nothing else, so on the main conversation it would freeze
the whole session. Desk enforces what it can: a call made outside any
sub-agent is refused with an explanation. Desk cannot tell a *foreground*
sub-agent from a *background* one, so a foreground sub-agent is not
refused and would still block the main conversation: start it with the
Agent tool's `run_in_background`. The usual shape is a background sub-agent
whose whole job is a loop: wait, hand the result to whoever needs it (a file,
or its final report), wait again.

Things to know:

- **Listening lasts only while the call is in flight.** An event published
  between two calls (while the sub-agent is handling the previous one) is
  missed, and so is one published before the first call. Call again
  immediately after each return, and for anything that must not be lost let
  the widget also write it to a file, with the event as the nudge (or
  re-read that file after each return).
- The tool also receives events the agent itself raised with
  `desk_raise_event` (sender `agent`).
- Names are not restricted: you may wait on a `desk.`-prefixed Desk event or
  `recording`/`stopped_recording`.
- At most 8 waits can be in flight at once; further calls are refused.
- Cancelling the call, ending the session, or switching Desk stops the wait
  within about a second and removes its subscription.
- The harness running the agent may impose its own limit on how long one tool
  call may last. If a wait returns with an error rather than a status, call
  it again.
- Like any other `desk` tool call, it asks the user for approval through
  Claude (Desk)'s normal approval flow.
