"""Asks the app's launcher to request a macOS permission (TODO b9689cd).

Qt refuses to request camera/microphone access from the Python child
process because the child has no Info.plist (found in the spike), and
the launcher (`desk_recorder/launcher.m`) is the process macOS knows as
DeskRecorder.app. So the launcher hands this process one end of a socket
pair (env `DESK_RECORDER_PERM_FD`); we write a permission name
(`camera`, `microphone` or `screen`) and read back one line:

- `granted`
- `denied`
- `restart` -- Screen Recording was just requested; macOS only applies it
  after the app is restarted.

Without that env var (running from a terminal while developing) the
permission is assumed to be handled by the terminal and `granted` is
returned. Blocking: call it from a worker thread, since a prompt waits
for the user.
"""
import os
import socket
import threading

PERMISSIONS = ("camera", "microphone", "screen")
_lock = threading.Lock()
_sock: socket.socket | None = None
_buffer = b""


def _connection() -> socket.socket | None:
    global _sock
    if _sock is None:
        fd = os.environ.get("DESK_RECORDER_PERM_FD")
        if not fd:
            return None
        _sock = socket.socket(fileno=int(fd))
    return _sock


def request(name: str, timeout: float = 300.0) -> str:
    global _buffer
    if name not in PERMISSIONS:
        raise ValueError(f"unknown permission {name!r}")
    with _lock:
        conn = _connection()
        if conn is None:
            return "granted"
        conn.settimeout(timeout)
        try:
            conn.sendall(f"{name}\n".encode())
            while b"\n" not in _buffer:
                chunk = conn.recv(256)
                if not chunk:
                    return "denied"
                _buffer += chunk
        except OSError:
            return "denied"
        line, _, _buffer = _buffer.partition(b"\n")
        answer = line.decode().strip()
        return answer if answer in ("granted", "denied", "restart") else "denied"
