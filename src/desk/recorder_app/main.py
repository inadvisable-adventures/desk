"""DeskRecorder's main loop (TODO b9689cd): connect to Desk's socket, say
hello, then run commands and send events until Desk says `quit` or goes
away. Qt objects live on the main thread; the socket reader is a thread
that hands each command over with a signal."""
import socket
import sys
import threading
import time

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtMultimedia import QMediaDevices, QWindowCapture

from desk import recorder_protocol as proto
from desk.recorder_app.features import AudioFeature, CameraFeature, Feature, ScreenFeature, TranscribeFeature

HEARTBEAT_MS = 1000


class RecorderApp(QObject):
    command = pyqtSignal(object)  # a decoded Message, from the reader thread
    main_call = pyqtSignal(object)  # a callable to run on the main thread
    disconnected = pyqtSignal()

    def __init__(self, conn: socket.socket) -> None:
        super().__init__()
        self._conn = conn
        self._send_lock = threading.Lock()
        self._alive = True
        self.command.connect(self._dispatch)
        self.main_call.connect(lambda fn: fn())
        self.disconnected.connect(self._on_disconnected)
        args = (self.send, self.main_call.emit)
        self.features: dict[str, Feature] = {
            "transcribe": TranscribeFeature(*args),
            "screen": ScreenFeature(*args),
            "camera": CameraFeature(*args),
            "audio": AudioFeature(*args),
        }
        self._heartbeat = QTimer(self)
        self._heartbeat.timeout.connect(lambda: self.send("heartbeat", str(int(time.time() * 1000))))

    # --- socket ---

    def send(self, name: str, *fields: str) -> None:
        """Thread-safe. A failed send means Desk is gone; the reader notices."""
        try:
            data = proto.encode(name, *fields)
        except proto.ProtocolError:
            return
        with self._send_lock:
            try:
                self._conn.sendall(data)
            except OSError:
                pass

    def start(self) -> None:
        self.send("hello", str(proto.PROTOCOL_VERSION))
        self._heartbeat.start(HEARTBEAT_MS)
        threading.Thread(target=self._read_loop, daemon=True, name="desk-socket").start()

    def _read_loop(self) -> None:
        buffer = b""
        try:
            while True:
                chunk = self._conn.recv(65536)
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    line, _, buffer = buffer.partition(b"\n")
                    try:
                        self.command.emit(proto.decode(line))
                    except proto.ProtocolError as e:
                        self.send("error", "transcribe", f"bad command: {e}")
        except OSError:
            pass
        self.disconnected.emit()

    def _on_disconnected(self) -> None:
        self.shutdown()

    # --- commands ---

    def _dispatch(self, message: proto.Message) -> None:
        name, f = message.name, message.fields
        try:
            if name == "start-transcribe":
                self.features["transcribe"].start(f[0], f[1])
            elif name == "start-screen":
                self.features["screen"].start(f[0], f[1])
            elif name == "start-camera":
                self.features["camera"].start(f[0], f[1])
            elif name == "start-audio":
                self.features["audio"].start(f[0], f[1])
            elif name == "stop":
                feature = self.features.get(f[0])
                if feature is None:
                    self.send("error", f[0], "unknown feature")
                else:
                    feature.stop()
            elif name == "status":
                for feature in self.features.values():
                    self.send("state", feature.name, feature.state, "")
            elif name == "sources":
                self._send_sources()
            elif name == "quit":
                self.shutdown()
        except Exception as e:  # noqa: BLE001 -- one bad command must not kill the recorder
            self.send("error", f[0] if f and f[0] in self.features else "transcribe", f"{name} failed: {e}")

    def _send_sources(self) -> None:
        for window in QWindowCapture.capturableWindows():
            self.send("source", "window", window.description())
        for screen in QGuiApplication.screens():
            self.send("source", "screen", screen.name())
        for camera in QMediaDevices.videoInputs():
            self.send("source", "camera", camera.description())
        for microphone in QMediaDevices.audioInputs():
            self.send("source", "microphone", microphone.description())
        self.send("sources-end")

    def shutdown(self) -> None:
        if not self._alive:
            return
        self._alive = False
        self._heartbeat.stop()
        for feature in self.features.values():
            try:
                feature.shutdown()
            except Exception:  # noqa: BLE001
                pass
        # Give recorders a moment to finalize their files, then leave.
        QTimer.singleShot(1500, QGuiApplication.quit)


def run(socket_path: str) -> int:
    app = QGuiApplication(sys.argv)
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.connect(socket_path)
    recorder = RecorderApp(conn)
    recorder.start()
    code = app.exec()
    try:
        conn.close()
    except OSError:
        pass
    return code
