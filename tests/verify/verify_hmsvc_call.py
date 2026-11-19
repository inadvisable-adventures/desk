"""TODO ffd183b: desk_call_hmsvc / desk_list_hmsvcs -- an agent calls a Desk-hosted microservice over HTTP.
A real stdlib HTTP server stands in for the service; the manager is a small fake with the real shape."""
import asyncio
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from desk import hmsvc_call, temp_ui  # noqa: E402
from desk.shell import current_context  # noqa: E402
from desk.shell import desk_mcp_server as mcp  # noqa: E402

passed = failed = 0


def check(name, ok):
    global passed, failed
    if ok:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


seen = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _reply(self, status, ctype, payload, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(payload)

    def _handle(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode() if length else ""
        seen.append((self.command, self.path, self.headers.get("Content-Type"), body, self.headers.get("X-Test")))
        if self.path.startswith("/redirect"):
            self._reply(302, "text/plain", b"", {"Location": "http://example.invalid/elsewhere"})
        elif self.path.startswith("/missing"):
            self._reply(404, "application/json", b'{"detail": "Not Found"}')
        elif self.path.startswith("/big"):
            self._reply(200, "text/plain", b"x" * 300_000)
        elif self.path.startswith("/bin"):
            self._reply(200, "application/octet-stream", bytes(range(256)))
        elif self.path.startswith("/slow"):
            import time
            time.sleep(3)
            self._reply(200, "text/plain", b"late")
        else:
            self._reply(200, "application/json", json.dumps({"method": self.command, "path": self.path, "body": body}).encode())

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _handle


server = HTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
PORT = server.server_address[1]


class FakeManager:
    services = {
        "api": {"name": "api", "description": "d", "status": "running", "url": f"http://127.0.0.1:{PORT}/"},
        "idle": {"name": "idle", "description": "", "status": "stopped", "url": None},
        "dead": {"name": "dead", "description": "", "status": "running", "url": "http://127.0.0.1:1/"},
    }

    def get(self, name):
        return self.services.get(name)

    def list_services(self):
        return list(self.services.values())


m = FakeManager()


def call(**kw):
    return hmsvc_call.call_service(m, **kw)


def raises(fn, text):
    try:
        fn()
    except hmsvc_call.HmsvcCallError as e:
        return text in str(e)
    return False


r = call(name="api", path="/items?limit=5")
check("GET returns status, content type and the body", r["status"] == 200 and "json" in r["content_type"]
      and json.loads(r["body"]) == {"method": "GET", "path": "/items?limit=5", "body": ""} and r["truncated"] is False)
r = call(name="api", method="post", path="/x", json_body={"a": [1, 2]})
check("POST sends JSON with a JSON content type", json.loads(json.loads(r["body"])["body"]) == {"a": [1, 2]} and seen[-1][2] == "application/json")
r = call(name="api", method="PUT", path="/x", body="plain text")
check("a text body is sent as text", seen[-1][0] == "PUT" and seen[-1][3] == "plain text" and seen[-1][2].startswith("text/plain"))
r = call(name="api", method="PATCH", path="/x", json_body=5)
check("PATCH and a scalar JSON value work", seen[-1][0] == "PATCH" and seen[-1][3] == "5")
call(name="api", method="DELETE", path="/x")
check("DELETE works", seen[-1][0] == "DELETE")
call(name="api", path="/x", headers={"X-Test": "yes"})
check("custom headers are sent", seen[-1][4] == "yes")

r = call(name="api", path="/missing")
check("an HTTP error status is a normal result with the service's body", r["status"] == 404 and "Not Found" in r["body"])
r = call(name="api", path="/redirect")
check("a redirect is reported, not followed", r["status"] == 302 and r["location"] == "http://example.invalid/elsewhere")
r = call(name="api", path="/big")
check("a large body is capped and flagged", r["truncated"] is True and len(r["body"]) == hmsvc_call.MAX_RESPONSE_CHARS)
r = call(name="api", path="/bin")
check("a binary body is not shown", "binary response" in r["body"] and r["status"] == 200)

check("unknown service names the ones that exist", raises(lambda: call(name="nope"), "api, idle, dead"))
check("a stopped service says so", raises(lambda: call(name="idle"), "is stopped"))
check("an unreachable service reports it", raises(lambda: call(name="dead"), "Could not reach"))
for bad in ("items", "//evil.example/x", "/a b", "/a\\b", "/a\nb", "http://evil/", ""):
    check(f"bad path {bad!r} refused", raises(lambda b=bad: call(name="api", path=b), "path must"))
check("unknown method refused", raises(lambda: call(name="api", method="TRACE"), "method"))
check("json and body together refused", raises(lambda: call(name="api", method="POST", json_body=1, body="x"), "not both"))
check("a GET with a body is refused", raises(lambda: call(name="api", json_body={"a": 1}), "carries no body"))
check("Host header cannot be overridden", raises(lambda: call(name="api", headers={"Host": "evil"}), "cannot be overridden"))
check("header injection refused", raises(lambda: call(name="api", headers={"X": "a\r\nB: c"}), "single-line"))
check("bad timeout refused", raises(lambda: call(name="api", timeout="soon"), "timeout"))
check("a slow service times out clearly", raises(lambda: call(name="api", path="/slow", timeout=1), "Could not reach"))
check("the timeout is clamped", hmsvc_call.MAX_TIMEOUT_SECONDS == 120.0)

# ---- MCP tools ----
def tool_call(t, args):
    res = asyncio.run(t.handler(args))
    return res, res["content"][0]["text"]


check("both tools registered", mcp._list_hmsvcs in mcp._TOOLS and mcp._call_hmsvc in mcp._TOOLS
      and mcp._call_hmsvc.name == "desk_call_hmsvc" and mcp._list_hmsvcs.name == "desk_list_hmsvcs")
res, text = tool_call(mcp._call_hmsvc, {"name": "api"})
check("without a window the tool says Desk is not ready", res["is_error"] and "not reachable" in text)
current_context.set_main_window(type("W", (), {"_hmsvc": m})())
try:
    res, text = tool_call(mcp._list_hmsvcs, {})
    check("list tool returns the services", not res["is_error"] and [s["name"] for s in json.loads(text)] == ["api", "idle", "dead"])
    res, text = tool_call(mcp._call_hmsvc, {"name": "api", "method": "POST", "path": "/echo", "json": {"k": "v"}})
    out = json.loads(text)
    check("call tool returns the response as JSON", not res["is_error"] and out["status"] == 200
          and json.loads(json.loads(out["body"])["body"]) == {"k": "v"})
    res, text = tool_call(mcp._call_hmsvc, {"name": "idle"})
    check("a stopped service is a tool error", res["is_error"] and "stopped" in text)
    res, text = tool_call(mcp._call_hmsvc, {"name": "api", "path": "/missing"})
    check("a 404 is not a tool error", not res["is_error"] and json.loads(text)["status"] == 404)
finally:
    current_context.set_main_window(None)

# ---- docs ----
tag = "desk_call_hmsvc: agents call services #506728"
check("changelog tag current, with an entry", tag in temp_ui.CURRENT_TAGS and tag in temp_ui._NEW_FEATURES)
doc = temp_ui.SPLIT_DOC_CONTENT["tempui-hmsvc.md"]
check("the hmsvc doc names both tools", "desk_call_hmsvc" in doc and "desk_list_hmsvcs" in doc)

server.shutdown()
print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
