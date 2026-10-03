"""Verifies TODO `929e730`: per-instance Bridge credentials bind identity
server-side; spoofed identity headers are ignored; the deprecated shared-token
legacy path still works (and warns once) but can be disabled; credentials are
revoked; hmsvc services get their own. Real server over loopback HTTP."""

import json
import logging
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk.server.credentials import CredentialRegistry, Identity  # noqa: E402
from desk.server.runner import start_server  # noqa: E402
from desk.widgets import WidgetInfo  # noqa: E402

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


# -- registry --------------------------------------------------------------------------


def test_registry():
    reg = CredentialRegistry()
    a = reg.issue("editor", "inst-a")
    b = reg.issue("sheet", "inst-b")
    check("each instance gets a distinct unguessable token", a != b and len(a) >= 40)
    check("lookup maps a token to its bound identity", reg.lookup(a) == Identity("editor", "inst-a") and reg.lookup(b) == Identity("sheet", "inst-b"))
    check("unknown/empty tokens map to nothing", reg.lookup("nope") is None and reg.lookup(None) is None and reg.lookup("") is None)
    a2 = reg.issue("editor", "inst-a")
    check("re-issuing for an instance revokes its previous token", reg.lookup(a) is None and reg.lookup(a2) == Identity("editor", "inst-a"))
    check("revoke_instance revokes and reports", reg.revoke_instance("inst-b") is True and reg.lookup(b) is None and reg.revoke_instance("inst-b") is False)
    svc = reg.issue_service("worker")
    check("a service token acts as hmsvc:<name>", reg.lookup(svc) == Identity("hmsvc:worker", "hmsvc:worker"))
    reg.issue("x", "inst-c")
    check("revoke_all_widget_instances spares services", reg.revoke_all_widget_instances() == 2 and reg.lookup(svc) is not None and reg.lookup(a2) is None)
    check("revoke_service revokes it", reg.revoke_service("worker") is True and reg.lookup(svc) is None)
    check("active_count tracks live tokens", reg.active_count() == 0)


# -- server ---------------------------------------------------------------------------------


class _FakeDesk:
    def __init__(self, directory):
        self.directory = directory


class _FakeGuiWindow:
    """get_widget_info answers per-widget capabilities: 'privileged' has fs,
    'plain' has nothing."""

    def __init__(self, directory):
        self.current_desk = _FakeDesk(directory)
        self.caps = {"privileged": ["fs"], "plain": []}

    def get_widget_info(self, widget_id):
        if widget_id not in self.caps:
            return None
        return WidgetInfo(id=widget_id, path=Path("."), kind="html", name=widget_id, entry="index.html", capabilities=self.caps[widget_id], default_size=None, content_hash="abc")


def _request(url, token, headers=None, method="GET", body=None, cookie=None):
    all_headers = {"X-Desk-Token": token} if token else {}
    all_headers.update(headers or {})
    if cookie:
        all_headers["Cookie"] = cookie
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        all_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=all_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read().decode() or "{}"), r.headers
    except urllib.error.HTTPError as e:
        text = e.read().decode()
        try:
            payload = json.loads(text or "{}")
        except ValueError:
            payload = {"raw": text}
        return e.code, payload, e.headers


def _pump(fn, timeout=20):
    outcome = {}

    def run():
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            outcome["error"] = e
        finally:
            outcome["done"] = True

    t = threading.Thread(target=run, daemon=True)
    t.start()
    deadline = time.time() + timeout
    while not outcome.get("done") and time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)
    t.join(timeout=1)
    assert outcome.get("done"), "requests never finished"
    if "error" in outcome:
        raise outcome["error"]


class _LogCapture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def with_server(fn, **kwargs):
    with tempfile.TemporaryDirectory() as d:
        widgets_dir = Path(d) / "widgets"
        widgets_dir.mkdir()
        desk_dir = Path(d) / "project"
        desk_dir.mkdir()
        (desk_dir / "f.txt").write_text("hello")
        handle = start_server(widgets_dir=widgets_dir, **kwargs)
        try:
            handle.gui_bridge.attach(_FakeGuiWindow(desk_dir))
            fn(handle, f"http://{handle.host}:{handle.port}")
        finally:
            handle.stop()


def test_bound_identity_beats_spoofed_headers():
    def body(handle, base):
        plain = handle.issue_credential("plain", "inst-plain")
        priv = handle.issue_credential("privileged", "inst-priv")
        out = {}

        def run():
            url = f"{base}/api/bridge/fs/readFile?path=f.txt"
            # No identity headers at all: identity comes from the credential.
            out["priv_no_headers"] = _request(url, priv)[:2]
            # 'plain' claims to be 'privileged' in its headers -- must NOT inherit fs.
            out["spoof"] = _request(url, plain, headers={"X-Desk-Widget-Id": "privileged", "X-Desk-Instance-Id": "inst-priv"})[:2]
            # 'privileged' claims to be 'plain' -- must NOT lose its own capability.
            out["priv_claims_plain"] = _request(url, priv, headers={"X-Desk-Widget-Id": "plain"})[:2]
            out["plain_honest"] = _request(url, plain, headers={"X-Desk-Widget-Id": "plain"})[:2]

        _pump(run)
        check("a bound credential identifies the caller with no identity headers", out["priv_no_headers"] == (200, {"contents": "hello"}))
        check("spoofing another widget's id with your own credential is refused (403, not that widget's fs)", out["spoof"][0] == 403)
        check("claiming a weaker identity does not change the bound one", out["priv_claims_plain"][0] == 200)
        check("a credential without the capability gets 403 even when honest", out["plain_honest"][0] == 403)

    with_server(body)


def test_instance_identity_comes_from_the_credential():
    def body(handle, base):
        tok = handle.issue_credential("plain", "inst-real")
        out = {}

        def run():
            url = f"{base}/api/bridge/self/setLocalStorage"
            out["set"] = _request(url, tok, headers={"X-Desk-Instance-Id": "inst-forged"}, method="POST", body={"data": {"k": 1}})[:2]
            out["get_real"] = _request(f"{base}/api/bridge/self/getLocalStorage", tok)[:2]

        saved = {}
        win = handle.gui_bridge.window
        win.set_html_widget_local_storage = lambda iid, data: saved.__setitem__(iid, data)
        win.get_html_widget_local_storage = lambda iid: saved.get(iid, {})
        _pump(run)
        check("local storage is keyed by the credential's instance, not a forged header", set(saved) == {"inst-real"} and out["set"][0] == 200)
        check("and reads back under the same credential", out["get_real"] == (200, {"data": {"k": 1}}))

    with_server(body)


def test_legacy_shared_token_still_works_and_warns_once():
    capture = _LogCapture()
    logger = logging.getLogger("desk.bridge")
    logger.addHandler(capture)
    logger.setLevel(logging.WARNING)

    def body(handle, base):
        out = {}
        handle.gui_bridge.window.get_html_widget_local_storage = lambda iid: {}

        def run():
            url = f"{base}/api/bridge/fs/readFile?path=f.txt"
            hdr = {"X-Desk-Widget-Id": "privileged", "X-Desk-Instance-Id": "legacy-1"}
            out["a"] = _request(url, handle.token, headers=hdr)[:2]
            out["b"] = _request(url, handle.token, headers=hdr)[:2]
            out["missing"] = _request(url, handle.token)[0]
            # Routes that only need the instance id (self.*) keep requiring just that header.
            out["self_only_instance"] = _request(f"{base}/api/bridge/self/getLocalStorage", handle.token, headers={"X-Desk-Instance-Id": "legacy-2"})[0]
            out["self_no_headers"] = _request(f"{base}/api/bridge/self/getLocalStorage", handle.token)[0]

        _pump(run)
        check("the deprecated shared token + header identity still works", out["a"] == (200, {"contents": "hello"}) and out["b"][0] == 200)
        check("a legacy call without the identity header is rejected as before (422)", out["missing"] == 422)
        check("legacy self.* routes still need only the instance-id header (and 422 without it)", out["self_only_instance"] == 200 and out["self_no_headers"] == 422)
        warnings = [m for m in capture.messages if "deprecated" in m]
        first_caller = [m for m in warnings if "'privileged'" in m and "'legacy-1'" in m]
        check("a deprecation warning is logged once per caller (two calls, one warning), naming its deprecation id", len(first_caller) == 1 and "DEPR-001" in first_caller[0] and "deprecated-docs" not in first_caller[0])
        check("a different caller gets its own warning", any("'legacy-2'" in m for m in warnings))

    try:
        with_server(body)
    finally:
        logger.removeHandler(capture)


def test_strict_mode_refuses_legacy_identity():
    def body(handle, base):
        tok = handle.issue_credential("privileged", "inst-1")
        out = {}

        def run():
            url = f"{base}/api/bridge/fs/readFile?path=f.txt"
            out["legacy"] = _request(url, handle.token, headers={"X-Desk-Widget-Id": "privileged", "X-Desk-Instance-Id": "x"})[:2]
            out["bound"] = _request(url, tok)[:2]
            out["ping"] = _request(f"{base}/api/ping", handle.token)[0]

        _pump(run)
        check("strict mode refuses shared-token header identity (403)", out["legacy"][0] == 403 and "per-instance" in out["legacy"][1]["detail"])
        check("strict mode still serves a bound credential", out["bound"] == (200, {"contents": "hello"}))
        check("and the shared token still authenticates non-identity routes", out["ping"] == 200)

    with_server(body, allow_legacy_identity=False)


def test_env_switch_makes_strict_the_default():
    os.environ["DESK_BRIDGE_ALLOW_LEGACY_IDENTITY"] = "0"
    try:
        def body(handle, base):
            out = {}

            def run():
                out["r"] = _request(f"{base}/api/bridge/fs/readFile?path=f.txt", handle.token, headers={"X-Desk-Widget-Id": "privileged", "X-Desk-Instance-Id": "x"})[0]

            _pump(run)
            check("DESK_BRIDGE_ALLOW_LEGACY_IDENTITY=0 enables strict mode", out["r"] == 403)

        with_server(body)
    finally:
        del os.environ["DESK_BRIDGE_ALLOW_LEGACY_IDENTITY"]


def test_revocation_and_unknown_tokens():
    def body(handle, base):
        tok = handle.issue_credential("privileged", "inst-1")
        out = {}

        def run():
            url = f"{base}/api/bridge/fs/readFile?path=f.txt"
            out["before"] = _request(url, tok)[0]
            handle.credentials.revoke_instance("inst-1")
            out["after"] = _request(url, tok)[0]
            out["garbage"] = _request(url, "not-a-token")[0]
            out["none"] = _request(url, None)[0]

        _pump(run)
        check("a revoked credential is refused outright (401)", out["before"] == 200 and out["after"] == 401)
        check("an unknown token or none at all is 401", out["garbage"] == 401 and out["none"] == 401)

    with_server(body)


def test_page_cookie_carries_the_per_instance_token():
    def body(handle, base):
        tok = handle.issue_credential("plain", "inst-1")
        out = {}

        def run():
            status, _body, headers = _request(f"{base}/api/ping?token={tok}", None)
            out["status"] = status
            out["cookie"] = headers.get("Set-Cookie", "")
            # The browser would send that cookie on sub-resource loads (no header, no query).
            out["with_cookie"] = _request(f"{base}/api/ping", None, cookie=f"desk_token={tok}")[0]

        _pump(run)
        check("a page loaded with its per-instance token gets that token as its cookie", out["status"] == 200 and tok in out["cookie"])
        check("the cookie authenticates the page's own sub-resource loads", out["with_cookie"] == 200)

    with_server(body)


def test_hmsvc_services_get_their_own_credential():
    def body(handle, base):
        mgr = handle.hmsvc_manager
        check("the manager is wired to issue and revoke per-service credentials", mgr._credential_issuer is not None and mgr._credential_revoker is not None)
        mgr.capabilities_for = lambda name: {"svc": ["events"], "nofs": ["events"]}.get(name)
        tok = handle.credentials.issue_service("svc")
        out = {}

        def run():
            sub = f"{base}/api/bridge/events/subscribe"
            out["ok"] = _request(sub, tok, method="POST", body={"names": ["x"]})[0]
            out["spoof"] = _request(sub, tok, headers={"X-Desk-Widget-Id": "privileged", "X-Desk-Instance-Id": "other"}, method="POST", body={"names": ["x"]})[0]
            out["no_fs"] = _request(f"{base}/api/bridge/fs/readFile?path=f.txt", tok)[0]

        _pump(run)
        check("a service token authenticates as that service and gets its capabilities", out["ok"] == 200)
        check("spoofed identity headers don't change which service it is", out["spoof"] == 200)
        check("a service is still limited to its declared capabilities (no fs -> 403)", out["no_fs"] == 403)
        handle.credentials.revoke_service("svc")
        out2 = {}

        def run2():
            out2["revoked"] = _request(f"{base}/api/bridge/events/subscribe", tok, method="POST", body={"names": ["x"]})[0]

        _pump(run2)
        check("revoking the service credential (as the manager does when the process ends) locks it out", out2["revoked"] == 401)

    with_server(body)


test_registry()
test_bound_identity_beats_spoofed_headers()
test_instance_identity_comes_from_the_credential()
test_legacy_shared_token_still_works_and_warns_once()
test_strict_mode_refuses_legacy_identity()
test_env_switch_makes_strict_the_default()
test_revocation_and_unknown_tokens()
test_page_cookie_carries_the_per_instance_token()
test_hmsvc_services_get_their_own_credential()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
