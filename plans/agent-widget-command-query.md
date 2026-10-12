# Agent <-> widget command/query: named widget logs, timecoded transcripts, recording events, log-query MCP tool [COMPLETED]

TODO items: Track A `1f74c27`, Track B `9df5246`, Track C `51db3bd`, live end-to-end check `0532852`.

## Summary

Lets an agent (or the "Claude (Desk)" widget) query a widget designed to
cooperate with it. First slice, three pieces:

1. **Widget log API** (Bridge API): a widget appends time-stamped strings
   to a *named* log, fire-and-forget, minimal widget-side overhead.
2. **Recording integration** in "Claude (Desk)": keep the timecoded
   transcript of each recording in `.desk_temp/timecoded-transcripts/`,
   point to it from the pasted transcription, and publish `recording` /
   `stopped_recording` desk events so widgets know when to log.
3. **MCP tool** hosted by "Claude (Desk)" (`desk_mcp_server.py`):
   time-range queries over the named logs.

The three are coupled only through two small contracts (below). Fix the
contracts first; the tracks can then proceed independently.

## What already exists (verified in the code)

- Bridge capability-gated routes in `src/desk/server/app.py`
  (`require_caller("<capability>")`, `require_instance_id`); JS client in
  `src/desk/server/bridge_client.py` (`call(method, path, body)` returns a
  promise via `fetch`); `events.publish/subscribe/onMessage` already exist
  (capability `events`, `desk.event_mediator.EventMediator`, python widgets
  via `desk.shell.event_broker.EventSubscription` / `bind_event_mediator`).
  "Desk events" = these mediated events; publish never echoes to the sender.
- `desk_mcp_server.py`: tools are `@tool` async handlers in `_TOOLS`,
  GUI-thread work via `_call_on_gui_thread`. Session-scoped, built per
  `ClaudeSession.start()`.
- Recording: `desk.voice_capture.MicRecorder` (signals `recording_started`,
  `recording_stopped`, `transcription_finished(result, error)`), used by
  `widgets/claude_desk/widget.py` (`_on_mic_*`); `_on_mic_transcription_finished`
  currently just does `setPlainText(result.text)`.
- **Gap:** `desk.speech.transcribe` calls whisper with `word_timestamps=True`
  but `WordConfidence` keeps only `word` + `probability`; segment/word
  start/end times are discarded. Track B must retain them.

## Shared contracts (agree/commit these first, ~30 min, one agent)

### Contract 1: log store + clock

- A `desk.widget_logs.WidgetLogStore` (new module, Qt-free, thread-safe like
  `EventMediator`): `append(log_name, entries)`, `query(log_name,
  start, end, limit)`, `list_logs()`. One instance per app run, created
  next to the mediator in `desk.server.runner.start_server`, reachable by
  both the server routes (writer) and the MCP server (reader) the same way
  the mediator is.
- Timestamps: **epoch milliseconds, UTC, int** everywhere (log entries,
  transcript timecodes' absolute anchor, MCP query args). MCP tool also
  accepts ISO-8601 strings and converts. Transcript timecodes are
  recording-relative seconds plus a recorded absolute `started_at_ms`, so
  the two can be correlated.
- Memory-bounded ring per log (cap entries, e.g. 10k, and drop oldest);
  per-desk lifetime, cleared on desk switch (like `EventMediator.clear_all`).
  Optional persistence is out of scope (parking lot).
- Log name: any string; docs advise `<short-descriptive-name>-<uuid-or-hash>`
  (e.g. use the instance id from `self.getManifest`/`DESK_WIDGET_INSTANCE_ID`).

### Contract 2: desk event payloads

- `recording`: `{ "started_at_ms": int, "recording_id": str }`
- `stopped_recording`: `{ "recording_id": str, "started_at_ms": int, "stopped_at_ms": int }`
- Both published by the Claude (Desk) widget's instance via its
  `EventSubscription.publish` (python-widget side; no new infra). Widgets
  subscribe with the existing `events.subscribe(["recording",
  "stopped_recording"])`. `recording_id` = the transcript file's stem
  (below), so a widget's log can be tied to a transcript.

## Open design decision (flag to user; recommendation given)

**Log append wire shape.** Options: (a) two parallel arrays, (b)
`{ts, text}[]`, (c) single entry. Recommendation: **(b) batched
`[{t, s}]`, where `t` is optional epoch-ms (server stamps arrival time if
omitted)**, sent fire-and-forget. Rationale: the widget cost of (a) vs (b)
is one small object literal, and (a) introduces length-mismatch bugs; the
server stamping on omission gives zero-overhead logging for widgets that
don't care about sub-latency precision. Client helper:
`desk.log.append(name, entries)` returns `undefined` (no promise), uses
`fetch(..., {keepalive: true})` with errors swallowed (optionally one
`console.warn`), and a tiny `desk.log.line(name, s)` convenience =
`append(name, [{s}])`. Capability name: `log`. Python widgets get an
in-process `append` through a `current_context` hook (follow the
hook-signature rules in `development-process.md`).

## Track A: log API + MCP query tool (agent 1)

Files: new `src/desk/widget_logs.py`; `src/desk/server/app.py` +
`runner.py` (routes `POST /api/bridge/log/append`, `GET /api/bridge/log/list`
for debugging, capability `log` in manifests/docs); `bridge_client.py`
(`desk.log`); `src/desk/shell/desk_mcp_server.py` (new tool) and
`desk.shell.current_context` hook for the store (or direct handle); python
side hook.

Steps:
1. `WidgetLogStore` + `tests/verify/verify_widget_log_store.py`
   (ordering, range bounds inclusive/exclusive documented, ring cap,
   thread-safety smoke, server-stamped timestamps).
2. Bridge routes + capability wiring (`widget.capabilities` validation list;
   check the `fix-custom-widget-bridge-capability-resolution` conventions);
   JS `desk.log.append/line`, fire-and-forget with `keepalive`.
3. MCP tool `desk_query_widget_log(log_name, start, end, limit=200,
   order="asc")` and `desk_list_widget_logs()` (names, entry counts, first/last
   timestamp: an agent cannot query what it can't discover). Read-only;
   output as `ISO-time<TAB>text` lines plus truncation note. Respect the
   existing `can_use_tool` flow (read-only, so consider whether it belongs in
   any bypass list; decide, don't assume).
4. Verify end to end with an HTML test widget logging on a timer and the
   MCP tool querying it (headless where possible; note skipped browser steps
   in the plan per process).

## Track B: recording integration (agent 2)

Files: `src/desk/speech.py`, `src/desk/voice_capture.py`,
`widgets/claude_desk/widget.py` (and `widgets/voice_input/widget.py` only
if the shared change requires it), possibly a new `desk.timecoded_transcript`
module for formatting.

Steps:
1. `speech.py`: extend `TranscriptionResult` / `WordConfidence` (or add a
   parallel `segments` field) with start/end seconds. Keep `.text` and the
   existing byte-for-byte word-join invariant; update the existing
   verify scripts that assert on these types in the same commit.
2. `MicRecorder`: capture `started_at_ms` at `start()`; expose it (and a
   `recording_id`) alongside `transcription_finished`.
3. New module formatting the transcript (e.g. `[mm:ss.mmm] segment text`
   per segment, header with `started_at_ms`), writing it to
   `<desk dir>/.desk_temp/timecoded-transcripts/<recording_id>.txt` (same
   directory-resolution idiom as `_on_history_markdown`:
   `current_context.get_current_desk_directory()` + `TEMP_UI_DIRNAME`).
4. `_on_mic_transcription_finished`: prepend to the pasted text a note
   naming the **relative** path of the transcript, then a fixed separator
   line, then the raw transcription. Define the separator as a module
   constant (e.g. `TRANSCRIPT_NOTE_SEPARATOR = "\n--- transcription ---\n"`)
   so the user can see/strip it and tests can assert on it. Relative paths
   per CLAUDE.md. (Open: should the user be able to disable the note?
   Default on.)
5. Publish `recording` on `_on_mic_recording_started` and
   `stopped_recording` on `_on_mic_recording_stopped` per Contract 2, via
   the widget's `EventSubscription` (`bind_event_mediator` already binds
   it). Make sure an error path after `recording` (mic error) still emits
   `stopped_recording`.
6. Verify scripts for: transcript file contents/format, the pasted prefix +
   separator, event payloads/ordering (fake mediator).

## Track C (the other clone's agent, or whoever finishes first): glue, docs, changelog

- Agent-visible features need a dedicated doc registered in
  `SPLIT_DOC_CONTENT` (`tempui-widget-logs.md`) covering the log API, the
  two events and their payloads, the transcript path/format and the MCP
  tools; link it from `tempui-custom-widgets.md`'s Bridge API list and the
  changelog entries (`_NEW_FEATURES`, minted tag in `CURRENT_TAGS`), per
  `development-process.md` (any guidance wording edited in `temp_ui.py`
  counts as a feature and needs its own tag and entry).
- Update `design-docs/architecture.md` (Bridge API list, MCP tools) and
  `LEARNINGS.md` as surprises appear.
- A small reference widget (HTML) demonstrating: subscribe to `recording`,
  log events while recording, name its log `<name>-<instance id>`.

## Coordination between agents / clones

- The three TODO items (A `1f74c27`, B `9df5246`, C `51db3bd`) were added in one
  commit to `main` before work started, to avoid `TODO.md` merge conflicts.
- Touch-point files likely to conflict: `app.py`, `temp_ui.py` (changelog
  dicts), `desk_mcp_server.py`, `widgets/claude_desk/widget.py`. Tracks A and
  B deliberately do not edit the same file except `temp_ui.py` (left to
  Track C) and `design-docs/architecture.md` (Track C).
- Contracts 1 and 2 above are the only coupling; any change to them goes
  through the user first.

## Key risks / decisions

- Fire-and-forget over HTTP means silent loss on error; acceptable for a
  debugging/context log, documented.
- Whisper timestamps are only as good as `word_timestamps=True` alignment;
  segment-level timecodes are the guaranteed floor.
- Log memory growth is bounded by the ring cap; entry text length should
  also be capped (e.g. 4 KB) server-side.
- Querying by wall-clock time assumes the widget's own `Date.now()` and the
  Desk process clock agree (same machine: fine); that is why server stamping
  on omitted `t` is the default recommendation.

## Verification

Per-track verify scripts under `tests/verify/` (see above), plus a manual
end-to-end: record a clip in Claude (Desk) while the reference widget logs;
confirm the pasted note's relative path resolves, the transcript timecodes
line up with `desk_query_widget_log` results, and `recording` /
`stopped_recording` arrive at the widget. Browser/mic steps may be skipped
in headless runs; note any skipped step here.

## Status

Contracts 1 and 2 implemented (2026-10-11) in `src/desk/widget_logs.py`
(`WidgetLogStore`, `now_ms`, `parse_time_ms`, `format_time_iso`, the
`RECORDING_EVENT`/`STOPPED_RECORDING_EVENT` names, payload builders,
`new_recording_id`, `TIMECODED_TRANSCRIPTS_DIRNAME`), wired as
`ServerHandle.widget_logs` (`desk.server.runner`), cleared on desk switch,
and exposed to python widgets/the MCP server as
`current_context.get_widget_log_store()`. Query ranges are inclusive on both
ends. `tests/verify/verify_widget_log_store.py` passes. Tracks A, B, C should
build on these without changing them (changes go through the user).

### Track A (TODO 1f74c27) completed 2026-10-11

- `app.py`: `POST /api/bridge/log/append` (`{name, entries:[{s, t?}]}`) and
  `GET /api/bridge/log/list`, both gated on capability `log` (capabilities
  are free-form strings in `widget.json`; no registry to update).
- `bridge_client.py`: `desk.log.append(name, entries)` / `desk.log.line(name, s)`,
  fire-and-forget (`fetch` with `keepalive`, returns `undefined`, never throws,
  one `console.warn` per page on a non-OK response).
- `desk_mcp_server.py`: `desk_list_widget_logs`, `desk_query_widget_log`
  (inclusive `start`/`end`, ISO or epoch ms, `limit`, `order` asc/desc,
  truncation note). Read-only; deliberately NOT in the permission-bypass
  list, so they go through the normal approval flow like the other read-only
  Desk tools (`desk_list_widget_instances` etc.).
- Python widgets append through `current_context.get_widget_log_store()`
  directly (no HTTP, no capability check).
- Verified headlessly; the real-browser reference-widget run (a Chromium
  widget logging from a timer) was **skipped** and belongs with Track C's
  reference widget.
- Fixed a stale fake in `verify_new_desk_flow.py` (it lacked `_widget_logs`
  after the contracts commit made `switch_desk` clear it).

### Track C (TODO 51db3bd), log half, 2026-10-11

Done: `tempui-widget-logs.md`, tag `named widget logs + log query MCP tools
#211800`, links (overview, custom-widgets Bridge list, porting "What Desk
gives you"), architecture.md paragraph, `verify_tempui_widget_logs_doc.py`.
Decision: the "reference widget" is the doc's worked example rather than a
new built-in widget (less to maintain); a widget cannot learn its own
instance id in JS, so the doc advises a random suffix kept in
`getLocalStorage`. Left for after Track B: the recording-events and
transcript sections of the doc (documenting them now would describe
behavior that does not exist yet) and a worked example that logs while
recording.

### Track B status (TODO `9df5246`): COMPLETED 2026-10-11

Implemented as planned: `TranscriptSegment` and `start`/`end` on
`WordConfidence` (`speech.py`, backward-compatible defaults); `MicRecorder`
exposes `recording_id`/`started_at_ms`/`stopped_at_ms`;
`src/desk/timecoded_transcript.py` renders/writes
`.desk_temp/timecoded-transcripts/<recording_id>.txt` and builds the pasted
note (`TRANSCRIPT_NOTE_SEPARATOR = "\n--- transcription ---\n"`); the Claude
(Desk) widget publishes `recording` on start and `stopped_recording` on every
`recording_stopped` (which also precedes the "No audio captured." error), via
the mediator hook it already had. If the transcript file can't be written the
plain text is pasted. The note is always on (no disable option yet).
Verified headless with `tests/verify/verify_recording_integration.py` (fake
mediator, no mic/whisper); real-mic and real-whisper timestamp output was
skipped, so word/segment `start`/`end` keys from mlx_whisper are as yet
unconfirmed against a live run.

NOTE from user: I have verified that the timestamping works.
### Track C (TODO 51db3bd) completed 2026-10-11

After Track B merged (reviewed: events published from the widget's existing
mediator binding, transcript write failure falls back to plain text, the
`recording_stopped` event also precedes the "No audio captured." error, and a
failed mic start publishes nothing), `tempui-widget-logs.md` gained "Recording
events and timecoded transcripts" (event payloads, the note + separator, the
file format, correlating with `desk_query_widget_log`) and the worked example
now tags log lines with the active `recording_id`. New changelog tag
`recording events + timecoded transcripts #920929` (the log tag `#211800` was
left untouched so projects that already saw it are not confused). The doc's
statements are checked against `desk.timecoded_transcript`/`desk.widget_logs`
by `verify_tempui_widget_logs_doc.py`. Whole plan: all three TODOs complete.

### TODO `0532852` (live end-to-end check) completed 2026-10-11

Built a disposable `DefineWidget` (`.desk_temp/widgets/recording-log-check/`,
TS custom element, `log` + `events` capabilities, not promoted -- it's a
throwaway test instrument, not a feature) that logs a line per button
click and per `recording`/`stopped_recording` event, tagging click-entries
made while recording with the active `recording_id`, per
`tempui-widget-logs.md`'s worked example. Placed it in a real, running
Desk; the user recorded a clip narrating click counts while clicking the
widget's button.

Verified in the live session:
- `desk_list_widget_logs`/`desk_query_widget_log` worked end to end against
  a real Chromium-hosted widget (not headless) -- 9 entries (`recording`,
  7 clicks, `stopped_recording`), matching the widget's own on-page
  client-side counter exactly. **No entries were lost over the `keepalive`
  fetch** in real Chromium -- the one specifically flagged risk in the
  TODO didn't materialize.
- The pasted note + separator (`[Timecoded transcript: ...]` /
  `--- transcription ---`) and the transcript file
  (`.desk_temp/timecoded-transcripts/rec-1791772249929-2ab4.txt`) matched
  the documented format exactly (header fields, `[mm:ss.mmm]` per-segment
  lines).
- Correlation: computed each transcript segment's absolute time
  (`started_at_ms` + offset) and compared to the widget log's own
  timestamps. `recording` logged 40ms after `started_at_ms`;
  `stopped_recording` logged 131ms after `stopped_at_ms`; narrated click
  references ("I did six clicks before I said anything", "going to do
  another click now") landed within ~0.4-0.8s of the corresponding logged
  click entries -- well within the natural lag between describing an
  action and performing it. An agent can reliably correlate the two.
- No capability-acceptance prompt or wording issue arose -- `log`/`events`
  are plain manifest-declared capabilities (unlike `introspect`), and the
  widget ran immediately on placement with no confirmation dialog.
- One non-issue worth recording: the user's narration mentioned a second
  "another one now" click (implying 8 total) that never actually
  registered -- the widget's own client-side counter also stopped at 7,
  confirming the gap was a real human action (or a missed click), not a
  dropped log entry.

No code changes needed -- no rough edges found to fix or file. Test widget
left un-promoted and disposable per the TODO's own framing; its
`.desk_temp/` source and the placed instance are not durable project
artifacts.
