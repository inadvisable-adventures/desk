"""Verifies TODO `929e730`: per-instance Bridge credentials bind identity
server-side; spoofed identity headers are ignored; the shared-token identity
path is a DEPR-001 tombstone (TODO df8138a: reported to Desk, refused); credentials
are revoked; hmsvc services get their own. Real server over loopback HTTP."""

import json
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


def test_shared_token_identity_is_a_tombstone():
    """DEPR-001 (TODO df8138a): a request that relies on the shared launch
    token for identity is reported to Desk and refused, with the tombstone
    message -- no old behavior behind it."""
    from desk.deprecations import get_registry

    seen = []
    get_registry().add_listener(seen.append)

    def body(handle, base):
        out = {}
        handle.gui_bridge.window.get_html_widget_local_storage = lambda iid: {}

        def run():
            url = f"{base}/api/bridge/fs/readFile?path=f.txt"
            hdr = {"X-Desk-Widget-Id": "privileged", "X-Desk-Instance-Id": "tomb-1"}
            out["a"] = _request(url, handle.token, headers=hdr)
            out["b"] = _request(url, handle.token, headers=hdr)
            out["no_headers"] = _request(url, handle.token)[:2]
            out["self_only_instance"] = _request(f"{base}/api/bridge/self/getLocalStorage", handle.token, headers={"X-Desk-Instance-Id": "tomb-2"})
            out["report_route"] = _request(f"{base}/api/bridge/deprecations/report", handle.token, headers=hdr, method="POST", body={"id": "DEPR-001"})[:2]
            out["ping"] = _request(f"{base}/api/ping", handle.token)[0]

        _pump(run)
        status, payload, _headers = out["a"]
        check("the old shared-token identity is refused (403)", status == 403)
        detail = payload["detail"]
        check("the refusal says what to use now and carries the agent command", "per-instance Bridge credential" in detail and "[DEPR-001]" in detail and "paste:" in detail)
        check("it never points at the isolated old docs", "deprecated-docs" not in detail)
        check("a second identical call is also refused", out["b"][0] == 403)
        mine = [r for r in seen if r.instance_id == "tomb-1"]
        check("it is reported to Desk exactly once per instance, with what the caller claimed", len(mine) == 1 and mine[0].widget_id == "privileged" and "readFile" in (mine[0].detail or ""))
        check("without any headers it is refused the same way", out["no_headers"][0] == 403)
        check("routes that need only the instance id are refused too, and reported per instance", out["self_only_instance"][0] == 403 and any(r.instance_id == "tomb-2" for r in seen))
        check("even reporting a deprecation can't be done as the shared token", out["report_route"][0] == 403)
        check("the shared token still authenticates routes that need no identity", out["ping"] == 200)

    try:
        with_server(body)
    finally:
        get_registry().forget_instance("tomb-1")
        get_registry().forget_instance("tomb-2")


def test_registered_js_deprecation_is_reported_via_the_bound_credential():
    from desk.deprecations import Deprecation, get_registry

    registry = get_registry()
    dep = registry.register(Deprecation("DEPR-900", "bridge_js", "fs.oldRead", "fs.readFile", "Call fs.readFile(path) instead.", "2026-10-03"))
    seen = []
    registry.add_listener(seen.append)

    def body(handle, base):
        tok = handle.issue_credential("privileged", "inst-js")
        out = {}

        def run():
            report = f"{base}/api/bridge/deprecations/report"
            out["a"] = _request(report, tok, headers={"X-Desk-Widget-Id": "plain", "X-Desk-Instance-Id": "spoofed"}, method="POST", body={"id": "DEPR-900", "detail": "fs.oldRead"})
            out["b"] = _request(report, tok, method="POST", body={"id": "DEPR-900"})
            out["unknown"] = _request(report, tok, method="POST", body={"id": "DEPR-nope"})[0]

        _pump(run)
        check("the report route returns the message to throw", out["a"][0] == 200 and "fs.readFile" in out["a"][1]["message"] and "DEPR-900" in out["a"][1]["message"])
        mine = [r for r in seen if r.deprecation.id == "DEPR-900"]
        check("identity comes from the credential, not from claimed headers", len(mine) == 1 and (mine[0].widget_id, mine[0].instance_id) == ("privileged", "inst-js"))
        check("a second report from the same instance is accepted but not re-reported", out["b"][0] == 200 and len(mine) == 1)
        check("an unknown deprecation id is a 404", out["unknown"] == 404)

    try:
        with_server(body)
    finally:
        registry.unregister("DEPR-900")


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
test_shared_token_identity_is_a_tombstone()
test_registered_js_deprecation_is_reported_via_the_bound_credential()
test_revocation_and_unknown_tokens()
test_page_cookie_carries_the_per_instance_token()
test_hmsvc_services_get_their_own_credential()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
