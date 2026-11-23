"""Desk's side of DeskRecorder (TODO b9689cd, plans/desk-recorder-app.md).

`RecorderService` starts `DeskRecorder.app`, talks to it over a Unix
socket in the line protocol of `desk.recorder_protocol`, and keeps the
last-known state of each feature (transcription, screen, camera). It is
plain thread-safe Python with no Qt, shared by the Bridge routes, the MCP
tools and the Recorder widget -- same shape as `desk.hmsvc.HmsvcManager`.

Desk LISTENS on the socket and the app connects out, so a connection
means the app is up and a closed connection means it died. The app is
started through LaunchServices (`open -n -a`), not as Desk's child, so
macOS attributes its Screen Recording / Camera / Microphone permissions to
the app itself, not to whatever launched Desk.
"""
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable

from desk import recorder_protocol as proto
from desk import transcript_pool
from desk.widget_logs import WidgetLogStore, new_recording_id, now_ms

APP_NAME = "DeskRecorder.app"
TRANSCRIPT_LOG_NAME = "transcript"
RECORDINGS_DIRNAME = "recordings"
# The app sends a heartbeat every second; this much silence means it hung.
HEARTBEAT_STALE_SECONDS = 5.0


class RecorderError(RuntimeError):
    pass


def default_app_candidates() -> list[Path]:
    env = os.environ.get("DESK_RECORDER_APP")
    candidates = [Path(env)] if env else []
    candidates += [Path.home() / "Applications" / APP_NAME, Path("/Applications") / APP_NAME]
    return candidates


def locate_app() -> Path | None:
    for candidate in default_app_candidates():
        if candidate.is_dir():
            return candidate
    return None


def _open_app(app: Path, socket_path: str) -> None:
    subprocess.run(["open", "-n", str(app), "--args", "--socket", socket_path], check=True, capture_output=True)


def _blank_feature() -> dict:
    return {"state": "idle", "detail": "", "path": None, "dropped": 0, "session": None}


class RecorderService:
    def __init__(
        self,
        launcher: Callable[[Path, str], None] = _open_app,
        app_locator: Callable[[], Path | None] = locate_app,
    ) -> None:
        self._launcher = launcher
        self._app_locator = app_locator
        self._lock = threading.RLock()
        self._start_lock = threading.Lock()
        self._conn: socket.socket | None = None
        self._features = {name: _blank_feature() for name in proto.FEATURES}
        # TODO d95a323: latest base64 JPEG per video feature ("screen"/
        # "camera" -- never "transcribe", which has no video) -- kept
        # separate from `_features` rather than folded in, since that
        # dict is returned verbatim as JSON by `status()`/`feature_status()`
        # (and so `desk_recorder_status`/the Recorder widget's own poll
        # loop); every caller of those would pay for a multi-KB image
        # they didn't ask for otherwise. See `latest_preview`.
        self._previews: dict[str, str] = {}
        # `AudioFeature`'s live input level (0.0-1.0), feature name ->
        # latest value -- same "poll-driven, not change-notification"
        # reasoning as `_previews`, see `latest_level`.
        self._levels: dict[str, float] = {}
        self._hello = threading.Event()
        self._last_heartbeat: float | None = None
        self._sources: dict[str, list[str]] = {}
        self._sources_done = threading.Event()
        self._changed = threading.Condition(self._lock)
        self._listeners: list[Callable[[], None]] = []
        self._desk_dir_provider: Callable[[], Path | None] = lambda: None
        self._widget_logs: WidgetLogStore | None = None
        self._socket_dir: str | None = None
        self._app_path: Path | None = None

    # --- wiring ---------------------------------------------------------

    def configure(
        self, desk_dir_provider: Callable[[], Path | None], widget_logs: WidgetLogStore | None = None
    ) -> None:
        self._desk_dir_provider = desk_dir_provider
        self._widget_logs = widget_logs

    def add_listener(self, listener: Callable[[], None]) -> None:
        """Called (from the reader thread) after any state change."""
        self._listeners.append(listener)

    def _notify(self) -> None:
        with self._changed:
            self._changed.notify_all()
        for listener in list(self._listeners):
            try:
                listener()
            except Exception:  # noqa: BLE001 -- a listener must not kill the reader thread
                pass

    def desk_dir(self) -> Path:
        directory = self._desk_dir_provider()
        if directory is None:
            raise RecorderError("No current Desk directory")
        return directory

    def pool_dir(self) -> Path:
        return transcript_pool.pool_dir(self.desk_dir())

    def recordings_dir(self) -> Path:
        directory = self.desk_dir() / ".desk_temp" / RECORDINGS_DIRNAME
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    # --- connection -----------------------------------------------------

    def connected(self) -> bool:
        with self._lock:
            return self._conn is not None

    def ensure_running(self, timeout: float = 20.0) -> None:
        """Starts DeskRecorder.app if it is not connected, and waits for
        its `hello`."""
        with self._start_lock:
            if self.connected():
                return
            app = self._app_locator()
            if app is None:
                raise RecorderError(
                    f"{APP_NAME} not found. Build and install it with scripts/build_desk_recorder_app.sh "
                    "(or set DESK_RECORDER_APP)."
                )
            self._app_path = app
            self._socket_dir = tempfile.mkdtemp(prefix="deskrec-")
            path = os.path.join(self._socket_dir, "s")
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                server.bind(path)
                server.listen(1)
                server.settimeout(timeout)
                self._hello.clear()
                try:
                    self._launcher(app, path)
                except (OSError, subprocess.CalledProcessError) as e:
                    raise RecorderError(f"Could not launch {APP_NAME}: {e}") from e
                try:
                    conn, _ = server.accept()
                except socket.timeout as e:
                    raise RecorderError(f"{APP_NAME} did not connect within {timeout:.0f}s") from e
            finally:
                server.close()
                shutil.rmtree(self._socket_dir, ignore_errors=True)
            with self._lock:
                self._conn = conn
                self._last_heartbeat = time.monotonic()
                self._features = {name: _blank_feature() for name in proto.FEATURES}
                # A fresh app instance: an old preview frame from before
                # this (re)connect would be actively misleading, unlike a
                # feature that's merely stopped (see latest_preview's own
                # docstring for why that case keeps its last frame).
                self._previews = {}
                self._levels = {}
            threading.Thread(target=self._read_loop, args=(conn,), daemon=True, name="recorder-reader").start()
            if not self._hello.wait(timeout):
                raise RecorderError(f"{APP_NAME} connected but did not say hello")
            self._notify()

    def _send(self, name: str, *fields: str) -> None:
        data = proto.encode(name, *fields)
        with self._lock:
            conn = self._conn
            if conn is None:
                raise RecorderError("DeskRecorder is not running")
            try:
                conn.sendall(data)
            except OSError as e:
                raise RecorderError(f"Lost the connection to DeskRecorder: {e}") from e

    def _read_loop(self, conn: socket.socket) -> None:
        buffer = b""
        try:
            while True:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    line, _, buffer = buffer.partition(b"\n")
                    try:
                        self._handle(proto.decode(line))
                    except proto.ProtocolError:
                        continue  # an unreadable line from the app is ignored
        except OSError:
            pass
        finally:
            with self._lock:
                if self._conn is conn:
                    self._conn = None
                    for feature in self._features.values():
                        if feature["state"] not in ("idle", "error", "denied"):
                            feature["state"] = "disconnected"
                    self._last_heartbeat = None
            try:
                conn.close()
            except OSError:
                pass
            self._sources_done.set()
            self._notify()

    def _handle(self, message: proto.Message) -> None:
        name, fields = message.name, message.fields
        with self._lock:
            if name == "hello":
                self._hello.set()
            elif name == "heartbeat":
                self._last_heartbeat = time.monotonic()
            elif name == "state" and fields[0] in self._features:
                feature = self._features[fields[0]]
                feature["state"], feature["detail"] = fields[1], fields[2]
            elif name == "started" and fields[0] in self._features:
                self._features[fields[0]]["state"] = "running"
            elif name == "stopped" and fields[0] in self._features:
                feature = self._features[fields[0]]
                feature["state"] = "idle"
                feature["path"] = None if fields[1] in ("", "-") else fields[1]
            elif name == "error" and fields[0] in self._features:
                feature = self._features[fields[0]]
                feature["state"], feature["detail"] = "error", fields[1]
            elif name == "dropped" and fields[0] in self._features:
                try:
                    self._features[fields[0]]["dropped"] = int(fields[1])
                except ValueError:
                    pass
            elif name == "source":
                self._sources.setdefault(fields[0], []).append(fields[1])
            elif name == "sources-end":
                self._sources_done.set()
            elif name == "preview-frame" and fields[0] in self._features:
                self._previews[fields[0]] = fields[1]
            elif name == "level" and fields[0] in self._features:
                try:
                    self._levels[fields[0]] = float(fields[1])
                except ValueError:
                    pass
        if name == "final":
            self._record_final(fields)
        # preview-frame/level arrive at a few-times-a-second rate (TODO
        # d95a323) -- excluded from _notify() for the same reason heartbeat
        # already is: a poll-driven consumer (see latest_preview,
        # latest_level) doesn't need a change-notification storm at that
        # rate, and every *other* listener would otherwise get woken for an
        # update it doesn't care about.
        if name not in ("heartbeat", "preview-frame", "level"):
            self._notify()

    def _record_final(self, fields: tuple[str, ...]) -> None:
        """Mirror a finished transcript segment into the widget-log store so
        an agent can query it by time (`desk_query_widget_log`)."""
        if self._widget_logs is None:
            return
        _session, start_ms, _end_ms, text = fields
        try:
            self._widget_logs.append(TRANSCRIPT_LOG_NAME, [(int(start_ms), text)])
        except ValueError:
            pass

    # --- commands -------------------------------------------------------

    def start(self, feature: str, target: str | None = None, device: str | None = None, wait: float = 0.0) -> dict:
        """Starts one feature (starting the app first if needed). Returns
        that feature's status; the real outcome (running, denied, error)
        arrives as state changes, so pass `wait` seconds to give it time."""
        if feature not in proto.FEATURES:
            raise RecorderError(f"Unknown feature {feature!r} (one of {', '.join(proto.FEATURES)})")
        self.ensure_running()
        with self._lock:
            current = self._features[feature]["state"]
            if current in ("starting", "running"):
                return dict(self._features[feature])
            self._features[feature] = {**_blank_feature(), "state": "starting"}
        stamp = time.strftime("%Y%m%d-%H%M%S")
        try:
            if feature == "transcribe":
                session = new_recording_id(now_ms())
                self._features[feature]["session"] = session
                self._send("start-transcribe", session, str(self.pool_dir()))
            elif feature == "screen":
                path = self.recordings_dir() / f"screen-{stamp}.mp4"
                self._features[feature]["path"] = str(path)
                self._send("start-screen", target or "screen", str(path))
            elif feature == "camera":
                path = self.recordings_dir() / f"camera-{stamp}.mp4"
                self._features[feature]["path"] = str(path)
                self._send("start-camera", device or "default", str(path))
            else:
                assert feature == "audio"  # the only one left, given the proto.FEATURES check above
                path = self.recordings_dir() / f"audio-{stamp}.wav"
                self._features[feature]["path"] = str(path)
                self._send("start-audio", device or "default", str(path))
        except Exception:
            with self._lock:
                self._features[feature]["state"] = "error"
            raise
        self._notify()
        if wait > 0:
            self._wait_for(feature, wait)
        return self.feature_status(feature)

    def _wait_for(self, feature: str, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        with self._changed:
            while self._features[feature]["state"] == "starting":
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._changed.wait(remaining)

    def stop(self, feature: str) -> dict:
        if feature not in proto.FEATURES:
            raise RecorderError(f"Unknown feature {feature!r} (one of {', '.join(proto.FEATURES)})")
        with self._lock:
            if self._conn is None or self._features[feature]["state"] in ("idle", "error", "denied"):
                return dict(self._features[feature])
            self._features[feature]["state"] = "stopping"
        self._send("stop", feature)
        self._notify()
        return self.feature_status(feature)

    def request_sources(self, timeout: float = 5.0) -> dict[str, list[str]]:
        """Windows, screens and cameras the app can capture."""
        self.ensure_running()
        with self._lock:
            self._sources = {}
            self._sources_done.clear()
        self._send("sources")
        self._sources_done.wait(timeout)
        with self._lock:
            return {kind: list(names) for kind, names in self._sources.items()}

    def feature_status(self, feature: str) -> dict:
        with self._lock:
            return {"feature": feature, **self._features[feature]}

    def latest_preview(self, feature: str) -> str | None:
        """TODO d95a323: the most recent base64 JPEG `feature` ("screen" or
        "camera") has sent, or `None` if none has arrived yet this
        connection. Deliberately keeps returning the last frame after that
        feature stops recording (like a paused video's last frame) rather
        than clearing it -- only a fresh `ensure_running()` connect clears
        `_previews` outright, since an old frame from a since-replaced app
        instance would be actively misleading, not just stale."""
        with self._lock:
            return self._previews.get(feature)

    def latest_level(self, feature: str) -> float | None:
        """`AudioFeature`'s most recent input level (0.0-1.0), or `None` if
        none has arrived yet this connection. Unlike `latest_preview`, a
        caller should treat this as meaningless once that feature is no
        longer `running` (a frozen non-zero level reads as "still live",
        unlike a frozen video frame) -- `feature_status`'s own `state`
        already says so; this method doesn't duplicate that check."""
        with self._lock:
            return self._levels.get(feature)

    def status(self) -> dict:
        with self._lock:
            age = None if self._last_heartbeat is None else time.monotonic() - self._last_heartbeat
            return {
                "connected": self._conn is not None,
                "app": str(self._app_path or self._app_locator() or "") or None,
                "heartbeat_age_seconds": age,
                "stale": age is not None and age > HEARTBEAT_STALE_SECONDS,
                "features": {name: dict(feature) for name, feature in self._features.items()},
            }

    def shutdown(self) -> None:
        """Asks the app to quit and drops the connection (Desk is exiting)."""
        with self._lock:
            conn = self._conn
        if conn is None:
            return
        try:
            self._send("quit")
        except RecorderError:
            pass
        try:
            conn.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
