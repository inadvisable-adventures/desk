"""Verifies TODO `0375f64`: a Desk-hosted microservice's `service.json`
can name its own Python interpreter (`"venv"`/`"python"`) instead of
always launching under `sys.executable`. See
`plans/hmsvc-custom-interpreter.md`. Real subprocesses, no mocks --
`HmsvcManager` is Qt-free, so no QApplication/server is needed here.

The "custom interpreter" in every case below is a real shell script
that appends a marker line to a file and then `exec`s the real
`sys.executable "$@"` -- this proves *which* interpreter actually ran
(the marker) while still ending up running real Python (so the service
still needs to import `uvicorn`/`desk.hmsvc_host` successfully, same as
production)."""

import json
import stat
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from desk.hmsvc import HmsvcManager  # noqa: E402

passed = 0
failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


def wait_until(predicate, timeout=15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


SERVICE_SOURCE = '''
async def app(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/plain")]})
    await send({"type": "http.response.body", "body": b"hi"})
'''


def write_marker_interpreter(path: Path, marker_file: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/bin/sh\n"
        f'echo used >> "{marker_file}"\n'
        f'exec "{sys.executable}" "$@"\n'
    )
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


import urllib.request  # noqa: E402


def http_get(url):
    with urllib.request.urlopen(url, timeout=10) as response:
        return response.read().decode()


with tempfile.TemporaryDirectory() as tmp:
    project = Path(tmp)
    manager = HmsvcManager()
    manager.configure_bridge("", "")

    # -- case 1: "venv" (project-relative) -----------------------------
    venv_marker = project / "venv_used.txt"
    write_marker_interpreter(project / "fake_venv" / "bin" / "python", venv_marker)
    svc_dir = project / "desk_hmsvc" / "venv_svc"
    svc_dir.mkdir(parents=True)
    (svc_dir / "service.py").write_text(SERVICE_SOURCE)
    (svc_dir / "service.json").write_text(json.dumps({"venv": "fake_venv"}))

    manager.set_directory(project)
    info = manager.get("venv_svc")
    check("venv field read from manifest", info is not None)

    ok, msg = manager.start("venv_svc")
    check("start accepted for venv-configured service", ok)
    check("becomes running", wait_until(lambda: manager.get("venv_svc")["status"] == "running"))
    info = manager.get("venv_svc")
    check("service answers HTTP through the custom interpreter", http_get(info["url"]) == "hi")
    check("venv interpreter actually ran", venv_marker.is_file() and venv_marker.read_text().strip() == "used")
    check("log names the custom interpreter", any("fake_venv" in line for line in manager.get_logs("venv_svc")))
    manager.stop("venv_svc")

    # -- case 2: "python" (absolute path, outside the project) --------
    with tempfile.TemporaryDirectory() as tmp2:
        outside = Path(tmp2)
        python_marker = outside / "python_used.txt"
        write_marker_interpreter(outside / "bin" / "python", python_marker)
        abs_dir = project / "desk_hmsvc" / "python_svc"
        abs_dir.mkdir(parents=True)
        (abs_dir / "service.py").write_text(SERVICE_SOURCE)
        (abs_dir / "service.json").write_text(json.dumps({"python": str(outside / "bin" / "python")}))
        manager.refresh()

        ok, msg = manager.start("python_svc")
        check("start accepted for python-configured service", ok)
        check("becomes running (absolute interpreter)", wait_until(lambda: manager.get("python_svc")["status"] == "running"))
        check("service answers HTTP (absolute interpreter)", http_get(manager.get("python_svc")["url"]) == "hi")
        check("absolute interpreter actually ran", python_marker.is_file() and python_marker.read_text().strip() == "used")
        manager.stop("python_svc")

    # -- case 3: misconfigured (missing interpreter) -------------------
    broken_dir = project / "desk_hmsvc" / "broken_svc"
    broken_dir.mkdir(parents=True)
    (broken_dir / "service.py").write_text(SERVICE_SOURCE)
    (broken_dir / "service.json").write_text(json.dumps({"venv": "does_not_exist"}))
    manager.refresh()

    ok, msg = manager.start("broken_svc")
    check("start refused for missing interpreter", ok is False)
    check("error names the missing path", "does_not_exist" in msg)
    check("service marked crashed, not left starting", manager.get("broken_svc")["status"] == "crashed")
    check("no subprocess was spawned", manager.get("broken_svc")["pid"] is None)
    check("reason recorded in the service's own log", any("does_not_exist" in line for line in manager.get_logs("broken_svc")))

    # -- case 4: default (neither field set) -> unchanged behavior ----
    default_dir = project / "desk_hmsvc" / "default_svc"
    default_dir.mkdir(parents=True)
    (default_dir / "service.py").write_text(SERVICE_SOURCE)
    (default_dir / "service.json").write_text(json.dumps({"description": "no interpreter override"}))
    manager.refresh()

    ok, msg = manager.start("default_svc")
    check("start accepted with no interpreter override", ok)
    check("becomes running under Desk's own interpreter", wait_until(lambda: manager.get("default_svc")["status"] == "running"))
    check(
        "default service's log doesn't mention a custom interpreter",
        not any("using" in line and "fake_venv" in line for line in manager.get_logs("default_svc")),
    )
    manager.stop("default_svc")

    manager.stop_all()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
