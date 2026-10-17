# Docs callout: desk events can be bare signals or carry the data; over ~1 KB use a file [COMPLETED]

TODO item `361b4f8`. Related: TODO `71d11da`, `30069f6` (the agent event tools, done). Source:
`../FEEDBACK/FEEDBACK-DESK-agent-qa-file-polling-2026-10-13-1845.md`.

## Summary

The tempui inter-widget documentation presents `desk.events` only as "tell another widget
something happened". Add an explicit callout that an event can be a bare signal with no payload
(a message meaning "I updated the file"), or a rich one that skips files entirely by carrying in
the payload what would have been written to a file, and recommend a file for anything over about
1 KB. Guidance only; no API changes.

## Affected files

`src/desk/temp_ui.py` only (generated docs): `_CUSTOM_WIDGETS_DOC`'s "Sending and receiving
named messages" section (new subsection), `_PORTING_DOC`'s "Making pieces talk to each other"
bullet (one sentence + pointer), the `tempui-agent-events.md` text (point to the callout), a new
changelog tag + `_NEW_FEATURES` entry. Plus `tests/verify/verify_events_payload_or_file_callout.py`.

## Content (the reasons behind the 1 KB advice, all true of the code)

- Every subscriber gets its own copy of the payload in a queue.
- Every published event is written in full to `MEDIATED-EVENT-LOG.tsv`.
- Events are not stored for late subscribers: only events published after `subscribe` arrive, so
  anything a widget must see after being (re)opened has to be in a file or the state store; the
  event is then only the nudge.
- The agent tool `desk_raise_event` hard-limits payloads to 64 KiB (the 1 KB figure is advice;
  64 KiB is the refusal limit).

## Steps and verification

1. Write the subsection and the porting-doc sentence; cross-link both ways with
   `tempui-agent-events.md`.
2. Mint a tag, add the `_NEW_FEATURES` entry.
3. Verify script: the subsection exists in the custom-widgets doc with the no-payload example, the
   payload-instead-of-file example, the 1 KB advice and the late-subscriber caveat; the 64 KiB
   figure quoted equals `MAX_EVENT_PAYLOAD_BYTES`; the porting doc and agent-events doc point to it;
   the tag has an entry. Then the whole `tests/verify/` set.
