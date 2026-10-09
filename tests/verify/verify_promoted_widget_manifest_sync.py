"""TODO 8bbc484: a promoted widget's [STALE] rebuild re-syncs capabilities/state_schema
from its source's widget.json (see plans/promoted-widget-manifest-sync.md)."""
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from desk.custom_widgets import read_source_manifest  # noqa: E402
from desk.shell.window import DeskWindow  # noqa: E402
from desk.temp_ui import CustomWidgetDefinition  # noqa: E402

passed = failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


class Win:
    def __init__(self, directory, answer):
        self.current_desk = SimpleNamespace(directory=directory)
        self._custom_widget_definitions = {}
        self.answer = answer
        self.asked = []
        self.notified = []
        self.registered = []

    def _confirm_added_capabilities(self, label, added):
        self.asked.append(list(added))
        return self.answer

    def _notify_widget_manifest_synced(self, keyword, label, summary):
        self.notified.append(summary)

    def _register_custom_widget(self, definition, source):
        self.registered.append((definition.capabilities[:], dict(definition.state_schema)))
        return True


Win._rebuild_promoted_widget = DeskWindow._rebuild_promoted_widget
Win._sync_definition_from_manifest = DeskWindow._sync_definition_from_manifest


def make(tmp, answer, manifest, caps=("state",), schema=None):
    src = tmp / "desk_widgets" / "w"
    src.mkdir(parents=True, exist_ok=True)
    if manifest is not None:
        (src / "widget.json").write_text(manifest if isinstance(manifest, str) else json.dumps(manifest))
    d = CustomWidgetDefinition(keyword="W", label="W", html_b64="", capabilities=list(caps),
                               state_schema=dict(schema or {}), source_path="desk_widgets/w")
    win = Win(tmp, answer)
    win._custom_widget_definitions["W"] = d
    return win, d


with tempfile.TemporaryDirectory() as t:
    tmp = Path(t)
    check("manifest read", (make(tmp, True, {"capabilities": ["a"], "state_schema": {"k": "number"}}), read_source_manifest(tmp, "desk_widgets/w"))[1] == (["a"], {"k": "number"}))
    for bad in ("{not json", "[]", json.dumps({"capabilities": "state"}), json.dumps({"capabilities": [1]}), json.dumps({"state_schema": {"k": 1}})):
        make(tmp, True, bad)
        check(f"malformed manifest -> None: {bad[:20]}", read_source_manifest(tmp, "desk_widgets/w") is None)
    check("missing manifest -> None", read_source_manifest(tmp, "desk_widgets/nope") is None)

with tempfile.TemporaryDirectory() as t:
    win, d = make(Path(t), True, {"capabilities": ["state", "hmsvc"]})
    check("rebuild succeeds", win._rebuild_promoted_widget("W"))
    check("asked about the added capability", win.asked == [["hmsvc"]])
    check("granted capability applied before re-register", win.registered[-1][0] == ["state", "hmsvc"])
    check("stored definition updated", d.capabilities == ["state", "hmsvc"])
    check("notified of the addition", win.notified and "added capabilities: hmsvc" in win.notified[0])

with tempfile.TemporaryDirectory() as t:
    win, d = make(Path(t), False, {"capabilities": ["hmsvc"]}, caps=("state", "fs"))
    win._rebuild_promoted_widget("W")
    check("declined: addition not applied", "hmsvc" not in d.capabilities)
    check("declined: removal still applied", d.capabilities == [])
    check("declined: notification mentions removal only", win.notified and "removed capabilities: state, fs" in win.notified[0] and "added" not in win.notified[0])

with tempfile.TemporaryDirectory() as t:
    win, d = make(Path(t), True, {"capabilities": ["state"], "state_schema": {"k": "string"}})
    win._rebuild_promoted_widget("W")
    check("no confirmation when nothing added", win.asked == [])
    check("state_schema applied", d.state_schema == {"k": "string"})
    check("notified of schema update", win.notified == ["state schema updated"])

with tempfile.TemporaryDirectory() as t:
    win, d = make(Path(t), True, {"capabilities": ["state"]})
    win._rebuild_promoted_widget("W")
    check("unchanged manifest: no prompt, no notification", not win.asked and not win.notified)

with tempfile.TemporaryDirectory() as t:
    win, d = make(Path(t), True, "{half writ")
    win._rebuild_promoted_widget("W")
    check("broken manifest keeps stored capabilities", d.capabilities == ["state"] and win.registered)

    d.source_path = None
    win.registered.clear()
    check("no source_path still re-registers", win._rebuild_promoted_widget("W") and win.registered)
    check("unknown keyword fails", not win._rebuild_promoted_widget("nope"))

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
