# Widget logs (let an agent ask a widget what happened)

See `desk-temporary-ui.md` (in this same directory) for this
directory's own overview and its current set of tags. This is not a
tempui-DSL file type: it is a Bridge API capability (`log`) for your
widget's own code, plus two MCP tools an agent calls to read what the
widget wrote.

A widget **appends** short, time-stamped strings to a **named log**; an
agent **queries** a log by time range. Use it to give an agent a
compact, timeline-shaped record of what a widget has been doing (user
actions, state changes, sensor readings, errors) without the agent
having to screenshot or poll the widget. It is a record for later
questions, not a command channel: the agent cannot push anything to the
widget through it.

## Appending (in the widget)

Declare the capability (`Capability<TAB>log` in a `DefineWidget`, or
`"log"` in a real `widget.json`'s `capabilities`), then:

- `desk.log.append(name, entries)` -- `entries` is an array of
  `{ s: "text", t: 1700000000000 }`. `s` is required; `t` is optional
  epoch **milliseconds** (UTC, e.g. `Date.now()`); omit it and Desk
  stamps the moment the entry arrives.
- `desk.log.line(name, s)` -- shorthand for `append(name, [{ s }])`.

Both are **fire-and-forget**: they return `undefined` (no promise to
await or catch), never throw, and send with `fetch(..., { keepalive:
true })`. A failed send (server down, capability missing, bad name) is
silently dropped, apart from one `console.warn` per page, so do not use
a log for anything you must not lose. Batch several entries into one
`append` call when you have them.

A log's **name** is any non-empty string. Pick a short descriptive name
followed by something unique per widget instance, so two copies of one
widget do not interleave, e.g. `"kanban-" + shortId`. A widget's JS is
not handed its instance id, so mint a short random suffix once and keep
it in `desk.self.getLocalStorage()`/`setLocalStorage()` (per instance,
survives a reload -- see the worked example). The agent discovers names
with `desk_list_widget_logs`, so a readable prefix matters.

Limits (silent, per Desk run): each log keeps its newest 10000 entries;
an entry's text is cut to 4096 characters; at most 500 distinct logs
exist at once. Logs live in Desk's memory only: they are cleared when
the Desk is switched or Desk quits, never written to disk.

Entries are kept in timestamp order (a client-supplied `t` may arrive
out of order; equal timestamps keep arrival order).

There is no JS read call: the capability's debugging route
`GET /api/bridge/log/list` returns `{ logs: [{ name, count, first_t,
last_t }] }` for anything that calls the Bridge directly, and reading
entries is the agent's job (below).

A `kind: "python"` widget skips HTTP and the capability:
`current_context.get_widget_log_store().append(name, [(None, "text")])`
(each entry a `(epoch_ms_or_None, text)` pair).

## Querying (the agent, via MCP)

Two read-only tools on the `desk` MCP server hosted by Claude (Desk);
like Desk's other tools they go through the normal approval prompt:

- `desk_list_widget_logs` -- JSON array of `{ name, count, first, last
  }` (times are local-zone ISO-8601). Call this first to see what
  exists.
- `desk_query_widget_log` -- arguments `log_name` (required), `start`,
  `end`, `limit` (default 200), `order`.
  - `start`/`end`: optional, **inclusive**; an ISO-8601 datetime (no
    zone means the Desk machine's local time, a trailing `Z` means UTC)
    or epoch milliseconds.
  - `order`: `"asc"` (default) returns the first `limit` entries in
    range, oldest first; `"desc"` returns the newest `limit`, newest
    first.
  - Result: one `<ISO time><TAB><text>` line per entry; if the range
    held more than `limit`, a final line says so (narrow the range or
    raise `limit`). An empty range says `(no entries in range)`; an
    unknown log name is an error.

All times are epoch milliseconds underneath, from one clock (the Desk
process's), so a widget's `Date.now()` on the same machine lines up
with the entries it did not stamp itself.

## Recording events and timecoded transcripts (Claude (Desk) voice input)

When the user dictates into a Claude (Desk) widget with its record
button, two things happen that tie widget logs to what was said.

**Desk events.** Claude (Desk) publishes, through the ordinary
`desk.events` channel (capability `events` to subscribe):

- `recording` -- `{ "recording_id": "rec-<ms>-<hex>", "started_at_ms":
  <epoch ms> }`, when capture begins. A widget that wants to log only
  while the user is talking starts logging here.
- `stopped_recording` -- `{ "recording_id": ..., "started_at_ms": ...,
  "stopped_at_ms": <epoch ms> }`, when capture ends. It fires for every
  recording that started, including one that ends up capturing no audio.
  A recording that fails to start (no microphone) publishes neither.

Subscribe with `desk.events.subscribe(["recording",
"stopped_recording"])` then `desk.events.onMessage(callback)`; the
payload is the callback's second argument. Transcription happens after
`stopped_recording`, so the transcript file below does not exist yet when
that event arrives.

**The timecoded transcript.** Once transcription finishes, Desk writes
`.desk_temp/timecoded-transcripts/<recording_id>.txt` (relative to the
project's Desk directory) and puts a note at the start of the text it
pastes into that widget's prompt box:

```
[Timecoded transcript: .desk_temp/timecoded-transcripts/<recording_id>.txt]
--- transcription ---
<the transcription, exactly as dictated>
```

The separator line `--- transcription ---` is always the same, so you
(or the user, who may delete the note before sending) can split on it.
If the file cannot be written, the plain transcription is pasted with no
note. The file looks like:

```
recording_id: rec-1760000000000-ab12
started_at_ms: 1760000000000
started_at: 2026-10-11T14:13:20.000-07:00

[00:00.000] first segment text
[00:03.420] second segment text
```

Timecodes are `[mm:ss.mmm]` offsets from the start of the audio, one
line per speech segment (a transcript with no segment data is one plain
text line instead). The absolute time of a line is `started_at_ms` plus
its offset in milliseconds (accurate to roughly the time the microphone
took to start, well under a second), the same epoch-millisecond clock
widget logs use.

**Correlating them.** To find what a widget was doing while a sentence
was spoken: read the transcript, compute that line's absolute time (and
the next line's, as the end), then call `desk_query_widget_log` with
`start`/`end` set to those epoch-ms values. A widget can make this
easier by including the `recording_id` in the entries it logs while
recording.

## Minimal worked example

In a widget with the `log` capability (and `Capability<TAB>log` in its
`DefineWidget`; add `Capability<TAB>events` for the recording part below):

```js
const { data } = await desk.self.getLocalStorage();
if (!data.logId) {
  data.logId = crypto.randomUUID().slice(0, 8);
  await desk.self.setLocalStorage(data);
}
const LOG = "clicker-" + data.logId;
let clicks = 0;
document.querySelector("button").addEventListener("click", () => {
  clicks += 1;
  desk.log.line(LOG, "clicked (" + clicks + " so far)" + (recordingId ? " [" + recordingId + "]" : ""));
});

// Tag entries made while the user is dictating with their recording id.
let recordingId = null;
desk.events.subscribe(["recording", "stopped_recording"]);
desk.events.onMessage((name, payload) => {
  recordingId = name === "recording" ? payload.recording_id : null;
  desk.log.line(LOG, name + " " + payload.recording_id);
});
```

Then the agent can ask for the last minute of it:

```
desk_list_widget_logs {}
desk_query_widget_log { "log_name": "clicker-<logId>",
                        "start": "2026-10-11T14:00:00", "limit": 50 }
```
