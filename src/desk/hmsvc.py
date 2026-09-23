"""Desk-hosted microservices (TODO e75b165) -- user-authored Python
services stored under `<project>/desk_hmsvc/<name>/service.py`, launched
and supervised by Desk. See plans/desk-hosted-microservices.md.

Each service runs as its own subprocess (`python -m desk.hmsvc_host`) on
a loopback port Desk allocates, so a crashing or blocking service can't
stall Desk's GUI or Local Web Server, and can always be killed. This
module is deliberately Qt-free and thread-safe (a plain `threading.Lock`
plus per-service supervisor threads), the same shape as
`desk.event_mediator`: it's used directly by the manager widget and
DeskWindow on the GUI thread, and by the Bridge API's route handlers on
the server's background thread.

A service's own access to Desk (events, state) is over the existing
Bridge REST API, authenticated with the per-launch token and the
synthetic caller id `hmsvc:<name>` (see `caller_id`); `service.json`'s
`capabilities` decide which Bridge capabilities that identity holds."""

import json
import os
import socket
import subprocess
import sys
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

HMSVC_DIRNAME = "desk_hmsvc"
SERVICE_ENTRY_FILENAME = "service.py"
SERVICE_MANIFEST_FILENAME = "service.json"
HMSVC_CHANGED_EVENT = "desk.hmsvc.changed"
DEFAULT_CAPABILITIES = ("state", "events")
CALLER_ID_PREFIX = "hmsvc:"

LOG_LINE_LIMIT = 500
STARTUP_TIMEOUT_SECONDS = 15.0
STOP_GRACE_SECONDS = 3.0

STATUS_STOPPED = "stopped"
STATUS_STARTING = "starting"
STATUS_RUNNING = "running"
STATUS_EXITED = "exited"  # exited on its own with code 0
STATUS_CRASHED = "crashed"  # exited on its own, non-zero (or never became ready)

# src/desk/hmsvc.py -> src/, put on a service subprocess's PYTHONPATH so
# `from desk.hmsvc_client import desk` works inside service code.
_SRC_DIR = Path(__file__).resolve().parents[1]


def caller_id(name: str) -> str:
    return CALLER_ID_PREFIX + name


def service_name_from_caller_id(value: str) -> str | None:
    return value[len(CALLER_ID_PREFIX):] if value.startswith(CALLER_ID_PREFIX) else None


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def lan_address() -> str | None:
    """Best-effort address other devices on the local network can reach
    this machine at (no packet is actually sent), or None."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("10.255.255.255", 1))
            address = sock.getsockname()[0]
    except OSError:
        return None
    return None if address.startswith("127.") else address


def _port_accepts(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return True
    except OSError:
        return False


def _resolve_interpreter(project_dir: Path, python: str | None, venv: str | None) -> tuple[str, str | None]:
    """Which Python interpreter a service's subprocess launches under
    (TODO 0375f64). `python` (an absolute interpreter path, for a venv
    living outside the project) takes precedence over `venv` (a
    project-relative venv directory, resolved to `<venv>/bin/python`);
    neither given falls back to Desk's own interpreter (`sys.executable`,
    today's only behavior) with no error. Returns `(interpreter, error)`
    -- a configured-but-missing interpreter is an error, not a silent
    fallback, so a service that needs its own native deps doesn't
    silently (and confusingly) run under Desk's interpreter instead."""
    if python:
        candidate = Path(python).expanduser()
    elif venv:
        candidate = project_dir / venv / "bin" / "python"
    else:
        return sys.executable, None
    if not candidate.is_file():
        return "", f"configured interpreter not found: {candidate}"
    return str(candidate), None


@dataclass
class _Service:
    name: str
    description: str = ""
    capabilities: list[str] = field(default_factory=lambda: list(DEFAULT_CAPABILITIES))
    autostart: bool = False
    external: bool = False
    venv: str | None = None
    python: str | None = None
    status: str = STATUS_STOPPED
    port: int | None = None
    pid: int | None = None
    started_at: float | None = None
    exit_code: int | None = None
    process: subprocess.Popen | None = None
    stop_requested: bool = False
    logs: deque = field(default_factory=lambda: deque(maxlen=LOG_LINE_LIMIT))


def _read_manifest(directory: Path) -> tuple[str, list[str], bool, bool, str | None, str | None]:
    try:
        data = json.loads((directory / SERVICE_MANIFEST_FILENAME).read_text())
    except (OSError, ValueError):
        return "", list(DEFAULT_CAPABILITIES), False, False, None, None
    if not isinstance(data, dict):
        return "", list(DEFAULT_CAPABILITIES), False, False, None, None
    capabilities = data.get("capabilities", list(DEFAULT_CAPABILITIES))
    if not isinstance(capabilities, list):
        capabilities = list(DEFAULT_CAPABILITIES)
    venv = data.get("venv")
    python = data.get("python")
    return (
        str(data.get("description", "")),
        [str(c) for c in capabilities],
        bool(data.get("autostart", False)),
        bool(data.get("external", False)),
        str(venv) if venv else None,
        str(python) if python else None,
    )


class HmsvcManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._directory: Path | None = None
        self._services: dict[str, _Service] = {}
        self._listeners: list[Callable[[], None]] = []
        self._bridge_url = ""
        self._bridge_token = ""

    # -- configuration -------------------------------------------------

    def configure_bridge(self, url: str, token: str) -> None:
        """Where a service reaches Desk's Bridge API (base URL, no
        trailing slash) and the per-launch token; set once the Local
        Web Server is up."""
        with self._lock:
            self._bridge_url = url
            self._bridge_token = token

    def add_listener(self, listener: Callable[[], None]) -> None:
        """`listener()` is called (on whichever thread caused it) after
        any change to the service list or a service's status."""
        with self._lock:
            self._listeners.append(listener)

    def _notify(self) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener()
            except Exception:
                pass

    def set_directory(self, directory: Path) -> None:
        """Points the manager at a project directory. Switching to a
        different one stops every running service of the old one, then
        rescans and starts the new one's `autostart` services."""
        with self._lock:
            changed = self._directory is None or directory.resolve() != self._directory.resolve()
            if not changed:
                return
        self.stop_all()
        with self._lock:
            self._directory = directory
            self._services = {}
        self.refresh()
        for name in [s.name for s in self._snapshot_services() if s.autostart]:
            self.start(name)

    @property
    def services_dir(self) -> Path | None:
        with self._lock:
            return (self._directory / HMSVC_DIRNAME) if self._directory is not None else None

    def _snapshot_services(self) -> list[_Service]:
        with self._lock:
            return list(self._services.values())

    # -- discovery -----------------------------------------------------

    def refresh(self) -> None:
        """Rescans `desk_hmsvc/` -- picks up new/removed services and
        re-reads `service.json`, keeping runtime state for any service
        already known."""
        root = self.services_dir
        found: dict[str, tuple[str, list[str], bool, bool, str | None, str | None]] = {}
        if root is not None and root.is_dir():
            for path in sorted(root.iterdir()):
                if path.is_dir() and (path / SERVICE_ENTRY_FILENAME).is_file():
                    found[path.name] = _read_manifest(path)
        with self._lock:
            for name in list(self._services):
                service = self._services[name]
                if name not in found and service.process is None:
                    del self._services[name]
            for name, (description, capabilities, autostart, external, venv, python) in found.items():
                service = self._services.setdefault(name, _Service(name=name))
                service.description = description
                service.capabilities = capabilities
                service.autostart = autostart
                service.external = external
                service.venv = venv
                service.python = python
        self._notify()

    # -- queries -------------------------------------------------------

    def _info(self, service: _Service) -> dict:
        serving = service.port and service.status == STATUS_RUNNING
        lan = lan_address() if serving and service.external else None
        return {
            "name": service.name,
            "description": service.description,
            "status": service.status,
            "port": service.port,
            "pid": service.pid,
            "url": f"http://127.0.0.1:{service.port}/" if service.port and service.status == STATUS_RUNNING else None,
            "external": service.external,
            "lan_url": f"http://{lan}:{service.port}/" if lan else None,
            "capabilities": list(service.capabilities),
            "autostart": service.autostart,
            "started_at": service.started_at,
            "exit_code": service.exit_code,
        }

    def list_services(self) -> list[dict]:
        with self._lock:
            return [self._info(s) for s in sorted(self._services.values(), key=lambda s: s.name)]

    def get(self, name: str) -> dict | None:
        with self._lock:
            service = self._services.get(name)
            return self._info(service) if service is not None else None

    def get_logs(self, name: str, limit: int = LOG_LINE_LIMIT) -> list[str]:
        with self._lock:
            service = self._services.get(name)
            return list(service.logs)[-limit:] if service is not None else []

    def append_log(self, name: str, line: str) -> None:
        with self._lock:
            service = self._services.get(name)
            if service is not None:
                service.logs.append(line)

    def capabilities_for(self, name: str) -> list[str] | None:
        """The Bridge capabilities service `name` holds, or None if
        there is no such service."""
        with self._lock:
            service = self._services.get(name)
            return list(service.capabilities) if service is not None else None

    # -- lifecycle -----------------------------------------------------

    def start(self, name: str) -> tuple[bool, str]:
        with self._lock:
            service = self._services.get(name)
            if service is None or self._directory is None:
                return False, f"No service named {name!r}."
            if service.process is not None:
                return False, f"{name!r} is already {service.status}."
            interpreter, error = _resolve_interpreter(self._directory, service.python, service.venv)
            if error is not None:
                service.status = STATUS_CRASHED
                service.logs.append(f"[desk] {error}")
                threading.Thread(target=self._notify, daemon=True).start()
                return False, error
            port = _free_port()
            host = "0.0.0.0" if service.external else "127.0.0.1"
            env = dict(os.environ)
            env.update(
                {
                    "DESK_SERVICE_NAME": name,
                    "DESK_SERVICE_PORT": str(port),
                    "DESK_SERVICE_HOST": host,
                    "DESK_PROJECT_DIR": str(self._directory),
                    "DESK_BRIDGE_URL": self._bridge_url,
                    "DESK_BRIDGE_TOKEN": self._bridge_token,
                    "PYTHONUNBUFFERED": "1",
                    "PYTHONPATH": os.pathsep.join(
                        [str(_SRC_DIR)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
                    ),
                }
            )
            directory = self._directory / HMSVC_DIRNAME / name
            try:
                process = subprocess.Popen(
                    [interpreter, "-m", "desk.hmsvc_host", str(directory), str(port), host],
                    cwd=self._directory,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
            except OSError as e:
                service.status = STATUS_CRASHED
                service.logs.append(f"[desk] failed to launch: {e}")
                threading.Thread(target=self._notify, daemon=True).start()
                return False, str(e)
            service.process = process
            service.status = STATUS_STARTING
            service.port = port
            service.pid = process.pid
            service.started_at = time.time()
            service.exit_code = None
            service.stop_requested = False
            service.logs.append(
                f"[desk] starting on {host}:{port} (pid {process.pid})"
                + (f" using {interpreter}" if interpreter != sys.executable else "")
                + (" -- reachable from the local network, unauthenticated" if service.external else "")
            )
        threading.Thread(target=self._read_output, args=(service, process), daemon=True).start()
        threading.Thread(target=self._supervise, args=(service, process, port), daemon=True).start()
        self._notify()
        return True, f"Started {name!r} on port {port}."

    def _read_output(self, service: _Service, process: subprocess.Popen) -> None:
        assert process.stdout is not None
        for line in process.stdout:
            with self._lock:
                service.logs.append(line.rstrip("\n"))

    def _supervise(self, service: _Service, process: subprocess.Popen, port: int) -> None:
        deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
        while process.poll() is None and time.monotonic() < deadline:
            if _port_accepts(port):
                with self._lock:
                    if service.process is process:
                        service.status = STATUS_RUNNING
                self._notify()
                break
            time.sleep(0.1)
        else:
            if process.poll() is None:
                with self._lock:
                    service.logs.append(f"[desk] never became ready within {STARTUP_TIMEOUT_SECONDS:.0f}s; killing")
                process.kill()
        code = process.wait()
        with self._lock:
            if service.process is not process:
                return
            service.process = None
            service.pid = None
            service.exit_code = code
            if service.stop_requested:
                service.status = STATUS_STOPPED
            else:
                service.status = STATUS_EXITED if code == 0 else STATUS_CRASHED
            service.logs.append(f"[desk] exited with code {code}")
        self._notify()

    def stop(self, name: str) -> tuple[bool, str]:
        with self._lock:
            service = self._services.get(name)
            if service is None:
                return False, f"No service named {name!r}."
            process = service.process
            if process is None:
                return False, f"{name!r} is not running."
            service.stop_requested = True
        process.terminate()
        try:
            process.wait(timeout=STOP_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        # _supervise finalizes the state; wait for it so a caller can
        # rely on the status having settled.
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            with self._lock:
                if service.process is None:
                    break
            time.sleep(0.02)
        return True, f"Stopped {name!r}."

    def restart(self, name: str) -> tuple[bool, str]:
        with self._lock:
            running = name in self._services and self._services[name].process is not None
        if running:
            self.stop(name)
        return self.start(name)

    def stop_all(self) -> None:
        with self._lock:
            names = [n for n, s in self._services.items() if s.process is not None]
        for name in names:
            self.stop(name)
