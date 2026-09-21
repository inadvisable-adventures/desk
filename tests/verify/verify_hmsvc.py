"""Verifies TODO `e75b165`: Desk-hosted microservices (desk.hmsvc). See
`plans/desk-hosted-microservices.md`. Real subprocesses, a real Local
Web Server (`running_server`) with a stub window standing in for
DeskWindow's state API, and a real manager widget. The GUI thread is
spun via processEvents while worker threads do blocking calls, since
GuiBridge.call needs it."""

import json
import os
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.window  # noqa: E402,F401

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from desk.hmsvc import HMSVC_CHANGED_EVENT, HmsvcManager  # noqa: E402
from desk.server.runner import running_server  # noqa: E402
from desk.shell import current_context  # noqa: E402

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


def spin_until(predicate, timeout=15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def in_thread(fn):
    """Runs fn on a worker thread while spinning the GUI thread."""
    box = {}

    def run():
        try:
            box["value"] = fn()
        except Exception as e:  # noqa: BLE001
            box["error"] = e

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    spin_until(lambda: not thread.is_alive(), 20.0)
    if "error" in box:
        raise box["error"]
    return box.get("value")


def http_get(url):
    with urllib.request.urlopen(url, timeout=10) as response:
        return response.read().decode()


SERVICE_SOURCE = '''
import json
from desk.hmsvc_client import desk

async def app(scope, receive, send):
    if scope["type"] != "http":
        return
    path = scope["path"]
    if path == "/state":
        desk.state_set("hmsvc.test", {"n": 7})
        body = json.dumps(desk.state_get("hmsvc.test"))
    elif path == "/publish":
        desk.events_publish("svc.hello", {"from": "svc"})
        body = "ok"
    elif path == "/subpoll":
        desk.events_subscribe(["svc.ping"])
        body = json.dumps("subscribed")
    elif path == "/poll":
        body = json.dumps(desk.events_poll(5.0))
    elif path == "/denied":
        try:
            desk.workspace_get_state()
            body = "allowed"
        except Exception as e:
            body = "denied:" + str(e)[:3]
    else:
        print("hello from svc", flush=True)
        body = "hi"
    await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/plain")]})
    await send({"type": "http.response.body", "body": body.encode()})
'''


class StubWindow:
    def __init__(self):
        self.state = {}

    def get_state(self, key, type_hint=None):
        return self.state.get(key)

    def set_state(self, key, value, edit, instance_id, type_hint=None):
        self.state[key] = value


with tempfile.TemporaryDirectory() as tmp, running_server() as handle:
    project = Path(tmp)
    handle.gui_bridge.attach(StubWindow())
    manager = handle.hmsvc_manager
    changes = []
    manager.add_listener(lambda: changes.append(1))

    svc_dir = project / "desk_hmsvc" / "demo"
    svc_dir.mkdir(parents=True)
    (svc_dir / "service.py").write_text(SERVICE_SOURCE)
    (svc_dir / "service.json").write_text(json.dumps({"description": "a demo"}))
    broken = project / "desk_hmsvc" / "broken"
    broken.mkdir()
    (broken / "service.py").write_text("raise RuntimeError('boom')\n")
    (project / "desk_hmsvc" / "not_a_service").mkdir()

    manager.set_directory(project)
    services = {s["name"]: s for s in manager.list_services()}
    check("discovers dirs with service.py only", sorted(services) == ["broken", "demo"])
    check("manifest description read", services["demo"]["description"] == "a demo")
    check("default capabilities", services["demo"]["capabilities"] == ["state", "events"])
    check("initially stopped", services["demo"]["status"] == "stopped")
    check("change listener fired on scan", len(changes) > 0)

    # -- lifecycle -----------------------------------------------------
    ok, _ = manager.start("demo")
    check("start accepted", ok)
    check("becomes running", spin_until(lambda: manager.get("demo")["status"] == "running"))
    info = manager.get("demo")
    check("has port, pid, url", info["port"] and info["pid"] and info["url"] == f"http://127.0.0.1:{info['port']}/")
    check("service answers HTTP", http_get(info["url"]) == "hi")
    check("stdout captured to logs", spin_until(lambda: any("hello from svc" in l for l in manager.get_logs("demo"))))
    check("second start refused", manager.start("demo")[0] is False)

    # -- state + events through the Bridge ---------------------------
    base = info["url"]
    check("state round-trips via desk client", json.loads(in_thread(lambda: http_get(base + "state"))) == {"n": 7})
    check("state landed in Desk's window", handle.gui_bridge.window.state.get("hmsvc.test") == {"n": 7})

    handle.event_mediator.subscribe("listener", "svc.hello")
    in_thread(lambda: http_get(base + "publish"))
    events = handle.event_mediator.drain("listener")
    check("service-published event reaches Desk", len(events) == 1 and events[0].payload == {"from": "svc"})
    check("event sender is the service", events[0].sender_instance_id == "hmsvc:demo")

    in_thread(lambda: http_get(base + "subpoll"))
    box = {}
    poller = threading.Thread(target=lambda: box.update(v=json.loads(http_get(base + "poll"))), daemon=True)
    poller.start()
    time.sleep(0.3)
    handle.event_mediator.publish("svc.ping", {"n": 1}, "tester")
    spin_until(lambda: not poller.is_alive())
    check("service receives Desk event", box.get("v", {}) and box["v"]["payload"] == {"n": 1})

    check("capability without grant is denied", http_get(base + "denied").startswith("denied:403"))

    # -- Bridge hmsvc routes for html widgets -------------------------
    # (route-level: unknown widget id is rejected before capability)
    try:
        urllib.request.urlopen(
            urllib.request.Request(
                f"http://{handle.host}:{handle.port}/api/bridge/hmsvc/list",
                headers={"X-Desk-Token": handle.token, "X-Desk-Widget-Id": "hmsvc:demo", "X-Desk-Instance-Id": "x"},
            )
        )
        got = "allowed"
    except urllib.error.HTTPError as e:
        got = e.code
    check("hmsvc routes need the hmsvc capability", got == 403)

    ok, _ = manager.restart("demo")
    check("restart works", ok and spin_until(lambda: manager.get("demo")["status"] == "running"))
    check("restart gets a serving process", http_get(manager.get("demo")["url"]) == "hi")
    manager.stop("demo")
    check("stop -> stopped", manager.get("demo")["status"] == "stopped")
    check("stopped has no pid/url", manager.get("demo")["pid"] is None and manager.get("demo")["url"] is None)

    manager.start("broken")
    check("failing service is crashed", spin_until(lambda: manager.get("broken")["status"] == "crashed"))
    check("crash traceback in logs", any("boom" in l for l in manager.get_logs("broken")))

    # -- external binding ---------------------------------------------
    import subprocess

    ext = project / "desk_hmsvc" / "ext"
    ext.mkdir()
    (ext / "service.py").write_text(SERVICE_SOURCE)
    (ext / "service.json").write_text(json.dumps({"external": True}))
    manager.refresh()
    check("local-only service reports external False", manager.get("demo")["external"] is False)
    manager.start("demo")
    manager.start("ext")
    check("external service runs", spin_until(lambda: manager.get("ext")["status"] == "running"))
    spin_until(lambda: manager.get("demo")["status"] == "running")

    def listen_address(pid):
        out = subprocess.run(["lsof", "-a", "-p", str(pid), "-iTCP", "-sTCP:LISTEN", "-nP"], capture_output=True, text=True).stdout
        return out

    ext_listen = listen_address(manager.get("ext")["pid"])
    demo_listen = listen_address(manager.get("demo")["pid"])
    check("external service listens on all interfaces", "*:" in ext_listen)
    check("default service listens on loopback only", "127.0.0.1:" in demo_listen and "*:" not in demo_listen)
    check("external log notes LAN exposure", any("local network" in l for l in manager.get_logs("ext")))
    from desk.hmsvc import lan_address

    lan = lan_address()
    if lan is not None:
        check("lan_url reported for external service", manager.get("ext")["lan_url"] == f"http://{lan}:{manager.get('ext')['port']}/")
        check("service reachable via LAN address", http_get(manager.get("ext")["lan_url"]) == "hi")
    check("no lan_url for local-only service", manager.get("demo")["lan_url"] is None)
    manager.stop("ext")
    manager.stop("demo")

    # -- widget --------------------------------------------------------
    current_context.set_hmsvc_manager(manager)
    import importlib.util

    spec = importlib.util.spec_from_file_location("hmsvc_widget_check", REPO_ROOT / "widgets" / "hmsvc_manager" / "widget.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    widget = module.build()
    check("widget lists all services", widget._list.count() == 3)
    widget._select("broken")
    check("widget log pane shows selected logs", "boom" in widget._log_view.toPlainText())
    widget._on_mediated_event(HMSVC_CHANGED_EVENT, {"services": []}, "desk")
    check("widget follows change events", widget._list.count() == 0)

    # -- autostart + directory switch ---------------------------------
    other = project / "other"
    (other / "desk_hmsvc" / "auto").mkdir(parents=True)
    (other / "desk_hmsvc" / "auto" / "service.py").write_text(SERVICE_SOURCE)
    (other / "desk_hmsvc" / "auto" / "service.json").write_text(json.dumps({"autostart": True}))
    manager.start("demo")
    spin_until(lambda: manager.get("demo")["status"] == "running")
    demo_pid = manager.get("demo")["pid"]
    manager.set_directory(other)
    check("switching stops old services", manager.get("demo") is None)
    try:
        os.kill(demo_pid, 0)
        alive = True
    except OSError:
        alive = False
    check("old service process is gone", not alive)
    check("autostart service starts", spin_until(lambda: (manager.get("auto") or {}).get("status") == "running"))
    handle_pid = manager.get("auto")["pid"]

# leaving running_server calls stop_all
try:
    os.kill(handle_pid, 0)
    alive = True
except OSError:
    alive = False
check("server shutdown stops services", not alive)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
