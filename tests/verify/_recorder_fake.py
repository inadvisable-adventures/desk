"""Shared by verify_recorder_service.py and verify_bridge_recorder.py (TODO b9689cd): a fake
DeskRecorder.app speaking the protocol over a real Unix socket."""
import socket
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from desk import recorder_protocol as proto  # noqa: E402
from desk import transcript_pool as pool  # noqa: E402


class FakeRecorder:
    """Speaks the app's side of the protocol. `deny` features answer
    start with a permission denial; `fail` ones with an error."""

    def __init__(self, deny=(), fail=(), heartbeat=True):
        self.deny, self.fail, self.heartbeat = set(deny), set(fail), heartbeat
        self.received = []
        self.sock = None
        self.alive = True

    def launch(self, app, path):
        threading.Thread(target=self._run, args=(path,), daemon=True).start()

    def send(self, name, *fields):
        self.sock.sendall(proto.encode(name, *fields))

    def _run(self, path):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(path)
        self.send("hello", str(proto.PROTOCOL_VERSION))
        if self.heartbeat:
            threading.Thread(target=self._beat, daemon=True).start()
        buf = b""
        while self.alive:
            try:
                chunk = self.sock.recv(4096)
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, _, buf = buf.partition(b"\n")
                message = proto.decode(line)
                self.received.append(message)
                self._reply(message)

    def _beat(self):
        while self.alive:
            try:
                self.send("heartbeat", str(int(time.time() * 1000)))
            except OSError:
                return
            time.sleep(0.1)

    def _reply(self, m):
        feature = {"start-transcribe": "transcribe", "start-screen": "screen", "start-camera": "camera"}.get(m.name)
        if feature:
            if feature in self.deny:
                self.send("state", feature, "denied", "Screen Recording permission was denied")
            elif feature in self.fail:
                self.send("error", feature, "no such device")
            else:
                self.send("started", feature)
                if feature == "transcribe":
                    session, pool_dir = m.fields
                    pool.append_segment(Path(pool_dir), pool.Segment(session, 0, 1000, 2000, "hello desk", True))
                    self.send("final", session, "1000", "2000", "hello desk")
        elif m.name == "stop":
            self.send("stopped", m.fields[0], "/some/file.mp4" if m.fields[0] != "transcribe" else "-")
        elif m.name == "sources":
            self.send("source", "window", "Desk - project")
            self.send("source", "camera", "FaceTime HD Camera")
            self.send("sources-end")

    def die(self):
        self.alive = False
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()
