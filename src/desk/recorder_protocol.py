"""The line protocol between Desk and DeskRecorder.app (TODO b9689cd,
plans/desk-recorder-app.md).

Plain text, one message per line: `<name> <field> <field> ... <last field>`.
Fields are separated by single spaces; the LAST field of a message that
takes free text (a path, an error message, transcript text) is the rest of
the line, so it may contain spaces but never a newline. A field that is not
last and may contain spaces (a window title, a camera name) is percent-
quoted with `quote_token`. No JSON: the protocol is small and fixed.

Desk -> recorder: start-transcribe, start-screen, start-camera,
start-audio, stop, status, sources, quit.
Recorder -> Desk: hello, started, stopped, error, status, dropped,
heartbeat, source, sources-end, final, preview-frame, level. (Transcript
text itself lives in the transcript pool; `final` is only a notification
so Desk can mirror it into the widget-log store. `preview-frame` (TODO
d95a323) is a low-fps JPEG snapshot of what a video feature -- screen or
camera -- is actually capturing, base64-encoded as its own last field;
no `quote_token` needed, since base64's alphabet never contains a space
or newline. `level` is `AudioFeature`'s live input level, 0.0-1.0, sent a
few times a second while it runs, for the widget's meter.)
"""
from dataclasses import dataclass
from urllib.parse import quote, unquote

PROTOCOL_VERSION = 1
FEATURES = ("transcribe", "screen", "camera", "audio")
# `status` states a feature can report.
STATES = ("idle", "starting", "running", "stopping", "error", "denied", "disconnected")

# name -> number of fields. The last field is "the rest of the line"
# (it may be empty); every message with 0 fields takes none.
_ARITY: dict[str, int] = {
    # Desk -> recorder
    "start-transcribe": 2,  # <session_id> <pool_dir...>
    "start-screen": 2,  # <target> <path...>   target: `screen` or `window:<quoted title>`
    "start-camera": 2,  # <device> <path...>   device: `default` or `<quoted name>`
    "start-audio": 2,  # <device> <path...>   device: `default` or `<quoted name>`
    "stop": 1,  # <feature>
    "status": 0,
    "sources": 0,
    "quit": 0,
    # recorder -> Desk
    "hello": 1,  # <protocol version>
    "started": 1,  # <feature>
    "stopped": 2,  # <feature> <path or ->
    "error": 2,  # <feature> <reason...>
    "state": 3,  # <feature> <state> <detail...>  (`status` replies are `state` lines)
    "dropped": 2,  # <feature> <count>
    "heartbeat": 1,  # <epoch ms>
    "source": 2,  # <kind: window|screen|camera|microphone> <name...>
    "sources-end": 0,
    "final": 4,  # <session> <start_ms> <end_ms> <text...>
    "preview-frame": 2,  # <feature> <base64-jpeg...>
    "level": 2,  # <feature> <level 0.0-1.0...>
}


class ProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class Message:
    name: str
    fields: tuple[str, ...] = ()


def quote_token(text: str) -> str:
    """For a non-last field that may contain spaces."""
    return quote(text, safe="")


def unquote_token(text: str) -> str:
    return unquote(text)


def _check_free_text(text: str) -> None:
    if "\n" in text or "\r" in text:
        raise ProtocolError("a protocol field must not contain a newline")


def encode(name: str, *fields: str) -> bytes:
    arity = _ARITY.get(name)
    if arity is None:
        raise ProtocolError(f"unknown message {name!r}")
    if len(fields) != arity:
        raise ProtocolError(f"{name} takes {arity} field(s), got {len(fields)}")
    parts = [name]
    for index, field in enumerate(fields):
        field = str(field)
        _check_free_text(field)
        is_last = index == arity - 1
        if not is_last and (" " in field or field == ""):
            raise ProtocolError(f"{name}: field {index + 1} must be a non-empty token without spaces (quote it)")
        parts.append(field)
    return (" ".join(parts) + "\n").encode("utf-8")


def decode(line: str | bytes) -> Message:
    if isinstance(line, bytes):
        line = line.decode("utf-8", errors="replace")
    line = line.rstrip("\r\n")
    name, _, rest = line.partition(" ")
    arity = _ARITY.get(name)
    if arity is None:
        raise ProtocolError(f"unknown message {name!r}")
    if arity == 0:
        return Message(name)
    parts = rest.split(" ", arity - 1) if rest or arity > 1 else [""]
    if len(parts) == arity - 1:
        parts.append("")  # an empty trailing free-text field
    if len(parts) != arity or (arity == 1 and parts[0] == "" and not rest):
        raise ProtocolError(f"{name} takes {arity} field(s)")
    if any(part == "" for part in parts[:-1]):
        raise ProtocolError(f"{name}: empty field")
    return Message(name, tuple(parts))
