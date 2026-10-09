"""TODO 879bfb4: tempui-hmsvc.md documents what hmsvc authoring needs (see plans/tempui-hmsvc-doc.md)."""
import re
import sys

sys.path.insert(0, "src")

from desk.temp_ui import (  # noqa: E402
    CURRENT_TAGS, HMSVC_DOC_FILENAME, SPLIT_DOC_CONTENT, _CUSTOM_WIDGETS_DOC, _NEW_FEATURES, _PORTING_DOC,
)
import desk.hmsvc as hmsvc  # noqa: E402

passed = failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


doc = SPLIT_DOC_CONTENT[HMSVC_DOC_FILENAME]
tag = next(t for t in CURRENT_TAGS if "dedicated hmsvc doc" in t)
check("registered in SPLIT_DOC_CONTENT", HMSVC_DOC_FILENAME == "tempui-hmsvc.md")
check("changelog entry exists for its tag", tag in _NEW_FEATURES and "tempui-hmsvc.md" in _NEW_FEATURES[tag])
for key in ("description", "autostart", "external", "capabilities", "venv", "python"):
    check(f"documents service.json key {key!r}", f"- `{key}`" in doc)
check("documents module-level `app`", "module-level ASGI" in doc and "uvicorn" in doc)
check("documents Rescan / no live watcher", "Rescan" in doc and "no live file watcher" in doc)
check("documents management-only networking", "management only" in doc and "fetch()" in doc)
check("documents CORS + preflight", "CORS is mandatory" in doc and "OPTIONS" in doc)
check("log cap in doc matches code", f"{hmsvc.LOG_LINE_LIMIT} lines" in doc)
check("startup timeout in doc matches code", f"{int(hmsvc.STARTUP_TIMEOUT_SECONDS)} seconds" in doc)
check("default capabilities in doc match code", '["state", "events"]' in doc and hmsvc.DEFAULT_CAPABILITIES == ("state", "events"))
check("documents every list() field", all(f in doc for f in ("lan_url", "started_at", "exit_code", "autostart")))
check("custom-widgets doc and porting doc link to it", "tempui-hmsvc.md" in _CUSTOM_WIDGETS_DOC and "tempui-hmsvc.md" in _PORTING_DOC)

# the worked example is runnable
match = re.search(r"`desk_hmsvc/hello/service.py`.*?```python\n(.*?)```", doc, re.S)
check("worked example present", match is not None)
ns = {}
exec(match.group(1), ns)
import asyncio  # noqa: E402

sent = []


async def run(method):
    async def send(m):
        sent.append(m)

    async def receive():
        return {}

    await ns["app"]({"type": "http", "method": method, "path": "/x"}, receive, send)


asyncio.run(run("GET"))
check("example answers GET 200 with CORS", sent[0]["status"] == 200 and (b"access-control-allow-origin", b"*") in sent[0]["headers"])
sent.clear()
asyncio.run(run("OPTIONS"))
check("example answers preflight 204", sent[0]["status"] == 204)

from desk.temp_ui import DOC_TEMPLATE  # noqa: E402

nav_tag = next(t for t in CURRENT_TAGS if "check new-features doc" in t)
check("TODO 601dae5: overview has the thin-doc navigation rule", "too thinly to act on" in DOC_TEMPLATE and "FEEDBACK file" in DOC_TEMPLATE)
check("TODO 601dae5: changelog entry for the rule", nav_tag in _NEW_FEATURES)
dev = open("development-process.md").read()
check("TODO 601dae5: process doc has the dedicated-doc policy", "Give agent-visible features a real doc" in dev and "SPLIT_DOC_CONTENT" in dev)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
