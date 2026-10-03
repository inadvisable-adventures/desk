"""Verifies TODO `18fa45f`: the fix actions offered wherever a tombstone use is
surfaced -- copy a command, launch an agent console seeded with instructions."""

import os
import sys
import tempfile
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.window  # noqa: E402,F401  (must precede QApplication)

from PyQt6.QtGui import QGuiApplication  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from desk.deprecations import Deprecation, UsageReport, agent_command, agent_instructions, format_error  # noqa: E402
from desk.shell import current_context  # noqa: E402

DeskWindow = desk.shell.window.DeskWindow
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


def dep(surface="bridge_js", old="fs.oldRead", replacement="fs.readFile", message="Call fs.readFile(path) instead."):
    return Deprecation("DEPR-920", surface, old, replacement, message, "2026-10-03")


def usage(d, instance="inst-1", detail=None, widget="editor"):
    return UsageReport(d, widget, instance, detail, 0.0)


# -- the seeded instructions ---------------------------------------------------------------


def test_agent_instructions():
    d = dep()
    text = agent_instructions(d, "Editor (inst-1)", ["Widget kind: `editor`", "Instance id: `inst-1`"])
    check("it carries the id, old API, replacement and message from the registry", all(s in text for s in ("DEPR-920", "`fs.oldRead`", "`fs.readFile`", "Call fs.readFile(path) instead.")))
    check("it says where Desk saw the use", "Reported at: Editor (inst-1)" in text and "Widget kind: `editor`" in text)
    check("it tells the agent what to do", "change it to use the replacement" in text and "check that it works" in text)
    check("it tells the agent not to hunt for the old API's docs, and never names the history store", "do not go looking for documentation of the old API" in text and "deprecated-docs" not in text)
    bare = agent_instructions(d)
    check("with no location it says so rather than leaving a hole", "search for the old name" in bare)
    check("a context line equal to the reported location isn't duplicated", agent_instructions(d, "X", ["X"]).count("- X") == 1)


# -- offering the actions ------------------------------------------------------------------------


class _Stub:
    def __init__(self, frames=None, widgets=None):
        self.frames = frames or {}
        self._widgets = widgets or {}
        self._custom_widget_definitions = {}
        self.launched = []
        self.asked = []
        self.answer = "dismiss"

    def find_frame_by_instance_id(self, iid):
        return self.frames.get(iid)

    def _display_name_for_instance(self, iid):
        return f"Editor ({iid})"

    def _ask_deprecation_action(self, message, command):
        self.asked.append((message, command))
        return self.answer

    def open_deprecation_agent(self, report):
        self.launched.append(report)


for name in ("_deprecation_where", "_deprecation_context", "_offer_deprecation_actions", "_on_widget_error_clicked"):
    setattr(_Stub, name, getattr(DeskWindow, name))


def test_offer_actions():
    d = dep()
    report = usage(d)
    stub = _Stub(frames={"inst-1": object()})
    clipboard = QGuiApplication.clipboard()
    clipboard.setText("untouched")
    stub.answer = "dismiss"
    stub._offer_deprecation_actions(report)
    check("the dialog gets the full tombstone message and the command naming the widget", stub.asked[0][0] == format_error(d, "Editor (inst-1)") and stub.asked[0][1] == agent_command(d, "Editor (inst-1)"))
    check("Dismiss does nothing", clipboard.text() == "untouched" and stub.launched == [])
    stub.answer = "copy"
    stub._offer_deprecation_actions(report)
    check("Copy command puts exactly the short command on the clipboard", clipboard.text() == agent_command(d, "Editor (inst-1)") and stub.launched == [])
    stub.answer = "launch"
    stub._offer_deprecation_actions(report)
    check("Launch agent console launches for this report", stub.launched == [report])
    frameless = _Stub()
    frameless.answer = "dismiss"
    frameless._offer_deprecation_actions(usage(dep("tempui_keyword", "OldKw", "Kw"), "uuid-1", "OldKw Title"))
    check("for a tempui file the command names the file's first line", "OldKw Title" in frameless.asked[0][1])


def test_context_per_surface():
    info = types.SimpleNamespace(name="Editor", kind="html", path=Path("/proj/widgets/editor"))
    stub = _Stub(frames={"inst-1": types.SimpleNamespace(content=types.SimpleNamespace(widget_id="editor"))}, widgets={"editor": info})
    stub._custom_widget_definitions = {"editor": types.SimpleNamespace(source_path="desk_widgets/editor/src")}
    lines = stub._deprecation_context(usage(dep(), detail="fs.oldRead"))
    flat = "\n".join(lines)
    check("a placed widget: kind and name, instance, source directory, authored-from path, the call", all(s in flat for s in ("`editor`", '"Editor"', "`inst-1`", "/proj/widgets/editor", "desk_widgets/editor/src", "fs.oldRead")))
    tempui = stub._deprecation_context(usage(dep("tempui_keyword", "OldKw", "Kw"), "uuid-1", "OldKw Title"))
    check("a tempui file: its path under .desk_temp and its first line", any(".desk_temp/uuid-1" in line for line in tempui) and any("OldKw Title" in line for line in tempui))
    manifest = stub._deprecation_context(usage(dep("manifest_field", "old_field", "new_field"), "/p/widget.json", "/p/widget.json: old_field"))
    check("a manifest: its path", manifest == ["Manifest: `/p/widget.json`"])
    hook = stub._deprecation_context(usage(dep("python_hook", "old_hook", "new_hook"), "/p/x.py:3", "/p/x.py:3"))
    check("a python hook: the call site", hook == ["Call site: `/p/x.py:3`"])
    gone = stub._deprecation_context(usage(dep(), "ghost", widget="missing"))
    check("a widget that is no longer placed still yields what is known", any("`missing`" in line for line in gone))


# -- launching the agent ---------------------------------------------------------------------------


def test_open_deprecation_agent():
    with tempfile.TemporaryDirectory() as d:
        previous = current_context.get_current_desk_directory()
        current_context.set_current_desk_directory(Path(d))
        try:
            claude = types.SimpleNamespace(default_size=(480, 560))
            info = types.SimpleNamespace(name="Editor", kind="html", path=Path("/proj/widgets/editor"))
            source_proxy = types.SimpleNamespace(sceneBoundingRect=lambda: types.SimpleNamespace(right=lambda: 500.0, top=lambda: 40.0))
            source = types.SimpleNamespace(graphicsProxyWidget=lambda: source_proxy, content=types.SimpleNamespace(widget_id="editor"))
            placed = []
            stub = types.SimpleNamespace(
                _widgets={desk.shell.window.CLAUDE_DESK_WIDGET_ID: claude, "editor": info},
                _custom_widget_definitions={},
                find_frame_by_instance_id=lambda iid: source if iid == "inst-1" else None,
                _display_name_for_instance=lambda iid: f"Editor ({iid})",
                view=types.SimpleNamespace(mapToScene=lambda p: types.SimpleNamespace(x=lambda: 10.0, y=lambda: 20.0), viewport=lambda: types.SimpleNamespace(rect=lambda: types.SimpleNamespace(center=lambda: None))),
                _place_widget=lambda *a, **kw: placed.append((a, kw)) or "FRAME",
            )
            stub._deprecation_where = lambda report: DeskWindow._deprecation_where(stub, report)
            stub._deprecation_context = lambda report: DeskWindow._deprecation_context(stub, report)
            stub._write_claude_instructions_file = lambda body, prefix: DeskWindow._write_claude_instructions_file(stub, body, prefix)
            result = DeskWindow.open_deprecation_agent(stub, usage(dep(), detail="fs.oldRead"))
            check("a Claude (Desk) widget is placed", result == "FRAME" and placed[0][0][0] == desk.shell.window.CLAUDE_DESK_WIDGET_ID)
            args, kwargs = placed[0]
            check("just right of the affected widget, at the widget's default size", args[2] == (524.0, 40.0) and args[3] == (480, 560))
            extra = kwargs["claude_extra_instructions"]
            files = sorted(Path(d, ".desk_temp").glob("deprecation-instructions-*.md"))
            check("its instructions are written to a file under .desk_temp (not bare-UUID named) and referenced", len(files) == 1 and files[0].name in extra)
            body = files[0].read_text()
            check("the file seeds the agent with the registry's message, the location and the instance", all(s in body for s in ("DEPR-920", "fs.readFile", "Editor (inst-1)", "`inst-1`", "/proj/widgets/editor", "fs.oldRead")) and "deprecated-docs" not in body)

            frameless = types.SimpleNamespace(**{**stub.__dict__})
            frameless.find_frame_by_instance_id = lambda iid: None
            frameless._deprecation_where = lambda report: DeskWindow._deprecation_where(frameless, report)
            frameless._deprecation_context = lambda report: DeskWindow._deprecation_context(frameless, report)
            frameless._write_claude_instructions_file = lambda body, prefix: DeskWindow._write_claude_instructions_file(frameless, body, prefix)
            DeskWindow.open_deprecation_agent(frameless, usage(dep("tempui_keyword", "OldKw", "Kw"), "uuid-1", "OldKw Title"))
            check("with no widget to sit beside it is view-centered", placed[1][0][2] == (10.0, 20.0))

            no_claude = types.SimpleNamespace(_widgets={})
            check("without a Claude (Desk) widget kind there is nothing to launch", DeskWindow.open_deprecation_agent(no_claude, usage(dep())) is None)
        finally:
            if previous is not None:
                current_context.set_current_desk_directory(previous)


# -- the [ERROR] marker click ---------------------------------------------------------------------------


class _ErrFrame:
    def __init__(self, report=None, message=""):
        self.has_error = True
        self.last_error_message = message
        self.deprecation_report = report
        self.cleared = False

    def set_error(self, has_error, message=""):
        self.has_error = has_error
        self.cleared = not has_error


def test_error_click_routing():
    d = dep()
    report = usage(d)
    stub = _Stub(frames={"inst-1": object()})
    stub.dismissed = []
    stub._confirm_widget_error_dismissed = lambda message: stub.dismissed.append(message)
    message = format_error(d, "Editor (inst-1)")
    frame = _ErrFrame(report, message)
    stub.answer = "copy"
    stub._on_widget_error_clicked(frame)
    check("clicking a tombstone marker offers the fix actions (not the plain dialog) and clears the marker", len(stub.asked) == 1 and stub.dismissed == [] and frame.cleared and frame.deprecation_report is None)
    other = _ErrFrame(report, "TypeError: something else broke")
    stub._on_widget_error_clicked(other)
    check("if a different error has since replaced the message, the plain error dialog is used", len(stub.asked) == 1 and stub.dismissed == ["TypeError: something else broke"])
    plain = _ErrFrame(None, "boom")
    stub._on_widget_error_clicked(plain)
    check("an ordinary error is unchanged", stub.dismissed[-1] == "boom" and len(stub.asked) == 1)
    quiet = _ErrFrame(report, message)
    quiet.has_error = False
    stub._on_widget_error_clicked(quiet)
    check("a marker that is not showing does nothing", len(stub.asked) == 1)


test_agent_instructions()
test_offer_actions()
test_context_per_surface()
test_open_deprecation_agent()
test_error_click_routing()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
