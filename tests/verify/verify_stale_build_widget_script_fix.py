import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk.server.bridge_client import render_bridge_client  # noqa: E402
from desk.server.runner import start_server  # noqa: E402
from desk.temp_ui import (  # noqa: E402
    BUILD_WIDGET_SCRIPT_FILENAME,
    CUSTOM_WIDGETS_DOC_FILENAME,
    SPLIT_DOC_CONTENT,
    TEMPUI_DOC_VERSION,
    write_tempui_docs,
)
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


check("TEMPUI_DOC_VERSION bumped to at least 29", TEMPUI_DOC_VERSION >= 29)
custom_widgets_doc = SPLIT_DOC_CONTENT[CUSTOM_WIDGETS_DOC_FILENAME]
new_features_doc = SPLIT_DOC_CONTENT["tempui-new-features.md"]
check("Version 29 entry present in new-features doc", "## Version 29" in new_features_doc)
check(
    "Version 29 entry mentions the stale-sibling warning",
    "scripts/build_widget.py" in new_features_doc and "warns" in new_features_doc,
)
check(
    "Version 29 entry mentions old-build cleanup",
    "leftover" in new_features_doc or "cleanup" in new_features_doc or "deletes" in new_features_doc,
)


def _write_widget_source(widget_dir, keyword):
    widget_dir.mkdir(parents=True)
    (widget_dir / "widget.json").write_text(
        json.dumps({"keyword": keyword, "label": keyword, "width": 300, "height": 200})
    )
    (widget_dir / "tsconfig.json").write_text(
        json.dumps({"compilerOptions": {"strict": True, "target": "ES2019", "lib": ["DOM", "ES2019"], "outDir": "build"}})
    )
    (widget_dir / f"{widget_dir.name}.ts").write_text(
        "class Widget extends HTMLElement {}\ncustomElements.define(\"x-widget\", Widget);\n"
    )
    (widget_dir / "widget.html").write_text(
        "<!doctype html><html><head><script>\n/* BUILD:COMPILED_JS */\n</script></head><body></body></html>"
    )


def test_stale_sibling_warning_printed_when_present():
    if shutil.which("tsc") is None:
        check("tsc available for stale-sibling-warning check", False)
        return
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        temp_dir = project_dir / ".desk_temp"
        temp_dir.mkdir()
        write_tempui_docs(temp_dir)
        script_path = temp_dir / BUILD_WIDGET_SCRIPT_FILENAME

        (project_dir / "scripts").mkdir()
        (project_dir / "scripts" / "build_widget.py").write_text("# a stale, pre-029047b copy\n")

        widget_dir = project_dir / ".desk_temp" / "widgets" / "warnwidget"
        _write_widget_source(widget_dir, "WarnWidget")

        result = subprocess.run(
            [sys.executable, str(script_path), str(widget_dir.relative_to(project_dir))],
            cwd=project_dir, capture_output=True, text=True,
        )
        check("build with a stale sibling present still succeeds", result.returncode == 0)
        check(
            "stderr warns about the stale scripts/build_widget.py sibling",
            "scripts/build_widget.py" in result.stderr and ".desk_temp/build_widget.py" in result.stderr,
        )


def test_no_warning_when_no_sibling_exists():
    if shutil.which("tsc") is None:
        check("tsc available for no-sibling check", False)
        return
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        temp_dir = project_dir / ".desk_temp"
        temp_dir.mkdir()
        write_tempui_docs(temp_dir)
        script_path = temp_dir / BUILD_WIDGET_SCRIPT_FILENAME

        widget_dir = project_dir / ".desk_temp" / "widgets" / "nowarnwidget"
        _write_widget_source(widget_dir, "NoWarnWidget")

        result = subprocess.run(
            [sys.executable, str(script_path), str(widget_dir.relative_to(project_dir))],
            cwd=project_dir, capture_output=True, text=True,
        )
        check("build with no stale sibling succeeds", result.returncode == 0)
        check("stderr has no stale-sibling warning when there is no sibling", "scripts/build_widget.py" not in result.stderr)


def test_rebuilding_same_keyword_leaves_exactly_one_file():
    if shutil.which("tsc") is None:
        check("tsc available for old-build cleanup check", False)
        return
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        temp_dir = project_dir / ".desk_temp"
        temp_dir.mkdir()
        write_tempui_docs(temp_dir)
        script_path = temp_dir / BUILD_WIDGET_SCRIPT_FILENAME

        widget_dir = project_dir / ".desk_temp" / "widgets" / "dupwidget"
        _write_widget_source(widget_dir, "DupWidget")
        other_widget_dir = project_dir / ".desk_temp" / "widgets" / "otherwidget"
        _write_widget_source(other_widget_dir, "OtherWidget")

        def run_build(rel_dir):
            result = subprocess.run(
                [sys.executable, str(script_path), str(rel_dir.relative_to(project_dir))],
                cwd=project_dir, capture_output=True, text=True,
            )
            check(f"build of {rel_dir.name} succeeded", result.returncode == 0)
            return project_dir / result.stdout.strip()

        other_out = run_build(other_widget_dir)
        first_out = run_build(widget_dir)
        second_out = run_build(widget_dir)

        check("the two DupWidget builds produced different output files", first_out != second_out)
        check("the first DupWidget build output was deleted after the rebuild", not first_out.is_file())
        check("the second (latest) DupWidget build output still exists", second_out.is_file())
        check("the unrelated OtherWidget build output was left untouched", other_out.is_file())

        dupwidget_files = [
            p for p in temp_dir.iterdir()
            if p.is_file() and p.open(encoding="utf-8").readline().startswith("DefineWidget\tDupWidget\t")
        ]
        check("exactly one DupWidget DefineWidget file remains in .desk_temp", len(dupwidget_files) == 1)


class _FakeDesk:
    def __init__(self, directory):
        self.directory = directory


class _FakeGuiWindow:
    def __init__(self, directory, capabilities=()):
        self.current_desk = _FakeDesk(directory)
        self._capabilities = list(capabilities)

    def get_widget_info(self, widget_id):
        return WidgetInfo(
            id=widget_id, path=Path("."), kind="html", name=widget_id, entry="index.html",
            capabilities=self._capabilities, default_size=None,
        )

    def open_editor_or_scrap(self, path):
        pass


def _run_with_pumped_event_loop(fn, timeout=10):
    outcome = {}

    def run():
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            outcome["error"] = e
        finally:
            outcome["done"] = True

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    deadline = time.time() + timeout
    while not outcome.get("done") and time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)
    thread.join(timeout=1)
    assert outcome.get("done"), "background request never finished"
    if "error" in outcome:
        raise outcome["error"]


def test_bridge_client_error_exposes_status_403():
    if shutil.which("node") is None:
        check("node available for bridge client err.status check", False)
        return
    with tempfile.TemporaryDirectory() as d:
        widgets_dir = Path(d) / "widgets"
        widgets_dir.mkdir()
        desk_dir = Path(d) / "my-project"
        desk_dir.mkdir()
        handle = start_server(widgets_dir=widgets_dir)
        try:
            fake_window = _FakeGuiWindow(desk_dir, capabilities=())
            handle.gui_bridge.attach(fake_window)
            base = f"http://{handle.host}:{handle.port}"
            client_js = render_bridge_client("some_widget", "some_instance", handle.token)

            outcome = {}

            def run_request():
                script_path = Path(d) / "bridge_client_check.js"
                # window.desk.* assumes a `window` global -- not present in
                # plain Node -- so this file starts by supplying one.
                script_path.write_text(
                    "global.window = {};\n"
                    # The real page fetch()es a relative path against its
                    # own origin -- plain Node has no such origin, so
                    # relative requests are rebased onto the real server
                    # here instead.
                    f"const __base_fetch__ = fetch;\n"
                    f"global.fetch = (url, opts) => __base_fetch__(\n"
                    f"  typeof url === \"string\" && url.startsWith(\"/\") ? {json.dumps(base)} + url : url,\n"
                    f"  opts,\n"
                    f");\n"
                    + client_js
                    + "\n(async () => {\n"
                    "  try {\n"
                    '    await window.desk.editor.openOrScrap("a.txt");\n'
                    "    console.log(JSON.stringify({ threw: false }));\n"
                    "  } catch (e) {\n"
                    "    console.log(JSON.stringify({ threw: true, status: e.status, message: e.message }));\n"
                    "  }\n"
                    "})();\n"
                )
                outcome["result"] = subprocess.run(
                    ["node", str(script_path)],
                    cwd=str(Path(d)), capture_output=True, text=True, timeout=10,
                )

            _run_with_pumped_event_loop(run_request)

            result = outcome["result"]
            check("node script ran without error", result.returncode == 0)
            if result.returncode != 0:
                print(result.stdout)
                print(result.stderr)
            parsed = json.loads(result.stdout.strip().splitlines()[-1]) if result.stdout.strip() else {}
            check("the fetch call threw for a 403 response", parsed.get("threw") is True)
            check("the thrown Error exposes status === 403", parsed.get("status") == 403)
            check("the thrown Error's message still names the status", "403" in (parsed.get("message") or ""))
        finally:
            handle.stop()


test_stale_sibling_warning_printed_when_present()
test_no_warning_when_no_sibling_exists()
test_rebuilding_same_keyword_leaves_exactly_one_file()
test_bridge_client_error_exposes_status_403()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
