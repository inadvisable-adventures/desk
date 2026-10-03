"""Verifies TODO `df8138a`: the tombstone machinery (desk.deprecations) and the
surfaces wired to it -- python hooks, manifest fields (widget.json, service.json),
tempui keywords, the JS stub generator and DeskWindow's handling of reports.
Synthetic deprecations (ids DEPR-9xx) stand in for real ones and are removed
afterward. The wire-path tombstone (DEPR-001) is covered in
verify_bridge_per_instance_credentials.py and the JS one end to end in
verify_kind_html_auth_token_and_profile_isolation.py."""

import json
import logging
import os
import sys
import tempfile
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.window  # noqa: E402,F401  (must precede QApplication)

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from desk.deprecations import (  # noqa: E402
    DEPR_001,
    Deprecation,
    DeprecatedApiError,
    DeprecatedManifestError,
    DeprecationRegistry,
    agent_command,
    check_manifest,
    format_error,
    get_registry,
    tombstone,
)
from desk.hmsvc import _read_manifest  # noqa: E402
from desk.server.bridge_client import deprecated_stubs_js, render_bridge_client  # noqa: E402
from desk.temp_ui import detect_temp_ui_kind  # noqa: E402
from desk.widgets import _parse_manifest, discover_project_widgets  # noqa: E402

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


def dep(id="DEPR-900", surface="python_hook", old="old_fn", replacement="new_fn", message="Call new_fn() instead.", since="2026-10-03"):
    return Deprecation(id, surface, old, replacement, message, since)


# -- registry ---------------------------------------------------------------------------


def test_registry_basics():
    reg = DeprecationRegistry()
    d = reg.register(dep())
    check("registering returns the deprecation and it is retrievable", reg.get("DEPR-900") is d and reg.all() == [d])
    reg.register(dep())
    check("re-registering identical content is fine", len(reg.all()) == 1)
    try:
        reg.register(dep(replacement="something else"))
        conflict = False
    except ValueError:
        conflict = True
    check("re-registering an id with different content is an error", conflict)
    try:
        dep(surface="nonsense")
        bad = False
    except ValueError:
        bad = True
    check("an unknown surface is rejected", bad)
    reg.register(dep("DEPR-901", "tempui_keyword", "OldKeyword"))
    check("by_surface and the tempui keyword lookup", [x.id for x in reg.by_surface("tempui_keyword")] == ["DEPR-901"] and reg.tempui_keyword("OldKeyword").id == "DEPR-901" and reg.tempui_keyword("Nope") is None)
    reg.unregister("DEPR-901")
    check("unregister removes it", reg.get("DEPR-901") is None)


def test_reporting_dedupes_per_instance_and_notifies_listeners():
    reg = DeprecationRegistry()
    reg.register(dep())
    heard = []
    reg.add_listener(heard.append)
    first = reg.report("DEPR-900", "w1", "i1", "detail")
    again = reg.report("DEPR-900", "w1", "i1")
    other = reg.report("DEPR-900", "w1", "i2")
    check("the first report returns a UsageReport; a repeat for the same instance returns None", first is not None and again is None and other is not None)
    check("listeners hear each distinct (deprecation, instance) once", [(r.instance_id) for r in heard] == ["i1", "i2"])
    check("reports are listed in order", [r.instance_id for r in reg.reports()] == ["i1", "i2"])
    reg.forget_instance("i1")
    check("a forgotten instance reports again", reg.report("DEPR-900", "w1", "i1") is not None)
    try:
        reg.report("DEPR-nope", "w", "i")
        unknown = False
    except KeyError:
        unknown = True
    check("reporting an unknown id is a KeyError", unknown)

    broken = DeprecationRegistry()
    broken.register(dep())
    broken.add_listener(lambda r: 1 / 0)
    good = []
    broken.add_listener(good.append)
    logging.getLogger("desk.deprecations").setLevel(logging.CRITICAL)
    check("a failing listener neither breaks reporting nor starves the others", broken.report("DEPR-900", "w", "i") is not None and len(good) == 1)


def test_messages():
    d = dep(old="fs.oldRead", replacement="fs.readFile", message="Pass a path.")
    message = format_error(d, "widgets/x.html")
    check("the message names the old API, the replacement, the id and what to do", all(s in message for s in ("fs.oldRead", "fs.readFile", "Pass a path.", "[DEPR-900]")))
    check("it carries the short command to give an agent, naming where", "paste: Fix deprecated Desk API use DEPR-900: replace fs.oldRead with fs.readFile in widgets/x.html." in message)
    check("the command is short and standalone", agent_command(d) == "Fix deprecated Desk API use DEPR-900: replace fs.oldRead with fs.readFile.")
    check("the real DEPR-001 message is complete on its own and mentions no docs", "per-instance Bridge credential" in format_error(DEPR_001) and "deprecated-docs" not in format_error(DEPR_001) and "DEPR-001" in format_error(DEPR_001))


# -- python hook ------------------------------------------------------------------------------


def test_python_tombstone():
    reg = DeprecationRegistry()
    reg.register(dep())
    heard = []
    reg.add_listener(heard.append)
    old_function = tombstone("DEPR-900", reg)

    def caller():
        return old_function("any", "args", keyword=True)

    try:
        caller()
        raised = None
    except DeprecatedApiError as e:
        raised = e
    check("calling the old function raises DeprecatedApiError with the tombstone message", raised is not None and raised.deprecation.id == "DEPR-900" and "new_fn" in str(raised))
    check("it reports the caller's file and line to Desk", len(heard) == 1 and heard[0].detail.startswith(__file__) and heard[0].widget_id == "python")
    try:
        tombstone("DEPR-nope", reg)()
        unknown = False
    except KeyError:
        unknown = True
    check("a tombstone for an unregistered id fails loudly", unknown)


# -- manifest fields ----------------------------------------------------------------------------


def test_manifest_field_tombstones():
    registry = get_registry()
    registry.register(dep("DEPR-902", "manifest_field", "old_field", "new_field", "Rename the field."))
    heard = []
    registry.add_listener(heard.append)
    try:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            bad = root / "badwidget"
            bad.mkdir()
            (bad / "widget.json").write_text(json.dumps({"kind": "python", "old_field": True}))
            try:
                _parse_manifest(bad / "widget.json")
                raised = None
            except DeprecatedManifestError as e:
                raised = e
            check("widget.json using a deprecated field fails to load with the tombstone message", raised is not None and "new_field" in str(raised) and str(bad / "widget.json") in str(raised))
            check("it is a ValueError too, so existing skip-and-log loaders cope", isinstance(raised, ValueError))
            check("and it was reported with the manifest path", any(r.deprecation.id == "DEPR-902" and r.instance_id == str(bad / "widget.json") for r in heard))

            good = root / "goodwidget"
            good.mkdir()
            (good / "widget.json").write_text(json.dumps({"kind": "python"}))
            check("a clean manifest still loads", _parse_manifest(good / "widget.json").id == "goodwidget")

            logging.getLogger("desk.widgets").setLevel(logging.CRITICAL)
            found = discover_project_widgets(root)
            check("project widgets skip the tombstoned one and keep the rest", set(found) == {"goodwidget"})

            svc = root / "svc"
            svc.mkdir()
            (svc / "service.json").write_text(json.dumps({"capabilities": ["fs"], "autostart": True, "old_field": 1}))
            description, capabilities, autostart, external, venv, python = _read_manifest(svc)
            check("a service.json with a deprecated field is listed inert: message as description, no capabilities, no autostart", "new_field" in description and capabilities == [] and autostart is False)
            (svc / "service.json").write_text(json.dumps({"capabilities": ["fs"], "autostart": True}))
            check("a clean service.json is unchanged", _read_manifest(svc)[1] == ["fs"] and _read_manifest(svc)[2] is True)
    finally:
        registry.unregister("DEPR-902")


# -- tempui keywords ---------------------------------------------------------------------------------


def test_tempui_keyword_tombstone():
    registry = get_registry()
    registry.register(dep("DEPR-903", "tempui_keyword", "OldQuestion", "Question", "Use the Question keyword."))
    try:
        check("an old keyword is a tombstone kind, not silently a question", detect_temp_ui_kind("OldQuestion What now?\nA\nB") == "deprecated:DEPR-903")
        check("real keywords are unaffected", detect_temp_ui_kind("Scratch notes\nbody") == "scratch" and detect_temp_ui_kind("Question Which?\nA\nB") == "question")
        check("a registered custom widget keyword still wins over a tombstone of the same name", detect_temp_ui_kind("OldQuestion", custom_keywords={"OldQuestion"}) == "custom:OldQuestion")
        window_cls = desk.shell.window.DeskWindow
        heard = []
        registry.add_listener(heard.append)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "11111111-2222-3333-4444-555555555555"
            path.write_text("OldQuestion What now?\nA\nB\n")
            check("DeskWindow reports a tombstoned tempui file and does not act on it", window_cls._handle_deprecated_tempui_file(object(), path) is True and any(r.instance_id == path.name and r.widget_id == "tempui" for r in heard))
            path.write_text("Question Which?\nA\nB\n")
            check("a normal tempui file is left alone", window_cls._handle_deprecated_tempui_file(object(), path) is False)
            check("a missing file is left alone", window_cls._handle_deprecated_tempui_file(object(), Path(d) / "gone") is False)
    finally:
        registry.unregister("DEPR-903")


# -- JS stubs ------------------------------------------------------------------------------------------


def test_js_stub_generation():
    reg = DeprecationRegistry()
    check("no bridge_js deprecations -> no stub code", deprecated_stubs_js(reg) == "")
    reg.register(dep("DEPR-904", "bridge_js", "fs.oldRead", "fs.readFile", "Call fs.readFile(path)."))
    js = deprecated_stubs_js(reg)
    check("a stub is generated per bridge_js deprecation, keyed by id and dotted path", '"DEPR-904"' in js and '"fs.oldRead"' in js and "/api/bridge/deprecations/report" in js)
    check("the stub carries the message as a fallback in case reporting itself fails", "fs.readFile(path)" in js)
    page = render_bridge_client("w", "i", "tok", reg)
    check("the stubs are installed inside the injected client, after window.desk exists", page.index("window.desk = {") < page.index("DEPR-904") < page.rindex("})();"))
    check("with no deprecations the client is the same script as before (no stray placeholder)", "%(" not in render_bridge_client("w", "i", "tok", DeprecationRegistry()))


# -- DeskWindow handling of a report --------------------------------------------------------------------


class _Frame:
    def __init__(self):
        self.errors = []

    def set_error(self, has_error, message=""):
        self.errors.append((has_error, message))


def window_stub(frames):
    notices = []
    stub = types.SimpleNamespace(
        find_frame_by_instance_id=lambda iid: frames.get(iid),
        _notify_deprecated_usage=lambda message, command: notices.append((message, command)),
    )
    return stub, notices


def test_window_handles_reports():
    window_cls = desk.shell.window.DeskWindow
    reg = DeprecationRegistry()
    js = reg.register(dep("DEPR-910", "bridge_js", "fs.oldRead", "fs.readFile"))
    tui = reg.register(dep("DEPR-911", "tempui_keyword", "OldKw", "Kw"))
    man = reg.register(dep("DEPR-912", "manifest_field", "old_field", "new_field"))
    hook = reg.register(dep("DEPR-913", "python_hook", "old_hook", "new_hook"))
    wire = reg.register(dep("DEPR-914", "wire_path", "legacy auth", "credential"))
    frame = _Frame()
    stub, notices = window_stub({"inst-1": frame})
    logging.getLogger("desk.deprecations").setLevel(logging.CRITICAL)
    from desk.deprecations import UsageReport

    def usage(d, instance, detail=None):
        return UsageReport(d, "widget", instance, detail, 0.0)

    window_cls._on_deprecation_reported(stub, usage(js, "inst-1", "fs.oldRead"))
    check("a Bridge JS tombstone use lights the widget's [ERROR] marker with the full message and agent command", frame.errors and frame.errors[-1][0] is True and "fs.readFile" in frame.errors[-1][1] and "paste:" in frame.errors[-1][1])
    window_cls._on_deprecation_reported(stub, usage(wire, "inst-1"))
    check("a wire-path tombstone use does the same for the claimed instance", len(frame.errors) == 2)
    window_cls._on_deprecation_reported(stub, usage(js, "not-placed"))
    check("a report for an instance with no frame is harmless", len(frame.errors) == 2 and notices == [])
    window_cls._on_deprecation_reported(stub, usage(tui, "file-uuid", "OldKw Title"))
    check("a tempui tombstone use shows a notification with the message and the command naming the file's keyword line", len(notices) == 1 and "Kw" in notices[0][0] and "OldKw Title" in notices[0][1])
    window_cls._on_deprecation_reported(stub, usage(man, "/p/widget.json", "/p/widget.json: old_field"))
    check("a manifest tombstone shows a notification too", len(notices) == 2 and "widget.json" in notices[1][1])
    window_cls._on_deprecation_reported(stub, usage(hook, "/p/x.py:3", "/p/x.py:3"))
    check("a python hook tombstone is logged only (its caller is already getting the exception)", len(notices) == 2 and len(frame.errors) == 2)


test_registry_basics()
test_reporting_dedupes_per_instance_and_notifies_listeners()
test_messages()
test_python_tombstone()
test_manifest_field_tombstones()
test_tempui_keyword_tombstone()
test_js_stub_generation()
test_window_handles_reports()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
