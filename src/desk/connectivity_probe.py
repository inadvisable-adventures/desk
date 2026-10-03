"""One-shot-at-a-time network reachability probe (TODO 5ce8447).

A bare, unauthenticated TCP connect to api.anthropic.com:443 -- no
request is sent, no credentials involved -- run on a short-lived thread
so the GUI never blocks, repeated every `interval` seconds while started.
stdlib only (CLAUDE.md: no new dependencies).

Caveat: success from Desk's own process doesn't guarantee the Claude CLI
subprocess's network path matches (proxy/VPN scoping can differ) -- a
strong signal, not a proof.
"""
import socket
import threading

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

PROBE_HOST = "api.anthropic.com"
PROBE_PORT = 443
PROBE_TIMEOUT = 3.0


def tcp_reachable(host: str = PROBE_HOST, port: int = PROBE_PORT, timeout: float = PROBE_TIMEOUT) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class ConnectivityProbe(QObject):
    """`result(bool)` is emitted (queued onto the GUI thread) after each probe."""

    result = pyqtSignal(bool)

    def __init__(self, interval: float = 5.0, check=tcp_reachable, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._check = check
        self._in_flight = False
        self._timer = QTimer(self)
        self._timer.setInterval(int(interval * 1000))
        self._timer.timeout.connect(self.probe_now)

    def is_running(self) -> bool:
        return self._timer.isActive()

    def start(self) -> None:
        """Probes immediately, then every interval until stop()."""
        if self._timer.isActive():
            return
        self._timer.start()
        self.probe_now()

    def stop(self) -> None:
        self._timer.stop()

    def probe_now(self) -> None:
        if self._in_flight:
            return
        self._in_flight = True

        def run() -> None:
            try:
                ok = bool(self._check())
            except Exception:  # noqa: BLE001 -- any failure means "not reachable"
                ok = False
            self._in_flight = False
            self.result.emit(ok)

        threading.Thread(target=run, daemon=True).start()
