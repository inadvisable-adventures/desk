import base64
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

# desk.shell.window (imports desk.shell.chromium_widget, which imports
# QtWebEngineWidgets) must be importable before QApplication is
# constructed -- see other verify scripts' identical comment on this
# same gotcha.
import desk.shell.window  # noqa: E402,F401

from PyQt6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from desk.hotreload import HotReloadBroker  # noqa: E402
from desk.schema_registry import SchemaRegistry  # noqa: E402
from desk.server.runner import start_server  # noqa: E402
from desk.shell.canvas import WorkspaceView  # noqa: E402
from desk.shell.chromium_widget import ChromiumWidget  # noqa: E402
from desk.shell.window import DeskWindow  # noqa: E402
from desk.shell.promoted_widget_source_watcher import PromotedWidgetSourceWatcher  # noqa: E402
from desk.temp_ui import JobDefinition  # noqa: E402

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


def pump(seconds=1.0):
    """See verify_kind_html_auth_token_and_profile_isolation.py's
    identical helper/docstring for why DeferredDelete is drained here
    too."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        time.sleep(0.02)


class _FakeWindowWithView:
    """Same shape as verify_html_widget_local_storage.py's own
    _FakeWindowWithView -- binds the real DeskWindow methods
    start_html_job actually needs (_place_widget and everything it
    calls) onto a lightweight double, real widgets_dir/ServerHandle
    included so the capability check is the real one, not simulated.
    Attached to the real GuiBridge itself (not a separate double): the
    Bridge API's require_caller falls back to
    gui_bridge.window.get_widget_info(widget_id) for a tempui-DSL
    -registered widget id (a Job included) -- resolving against this
    same object's own self._widgets is what makes the capability
    check below real, not simulated."""

    def __init__(self, directory, handle):
        self.current_desk = type("D", (), {"directory": directory, "path": directory / "x.desk"})()
        self._widgets = {}
        self._handle = handle
        self._broker = HotReloadBroker()
        self.view = WorkspaceView()
        self.view.resize(800, 600)
        self.view.show()
        self._custom_widget_sources = {}
        self._custom_widget_definitions = {}
        self._custom_widget_content_hash = {}
        # TODO 4eb3d9e: _register_custom_widget/_place_widget/
        # _on_widget_stale_clicked now also touch these.
        self._promoted_widget_source_watcher = PromotedWidgetSourceWatcher()
        self._promoted_widget_source_dirty = set()
        self._schema_registry = SchemaRegistry()

    def get_state_dict(self):
        """Resolves the real /api/bridge/workspace/getState route the
        job's own JS below calls."""
        return {"widgets": []}


_FakeWindowWithView._place_widget = DeskWindow._place_widget
_FakeWindowWithView._chromium_profile_dir = DeskWindow._chromium_profile_dir
_FakeWindowWithView._bind_claude_widget = DeskWindow._bind_claude_widget
_FakeWindowWithView._bind_external_indicator = DeskWindow._bind_external_indicator
_FakeWindowWithView._bind_event_mediator = DeskWindow._bind_event_mediator
_FakeWindowWithView._bind_error_indicator = DeskWindow._bind_error_indicator
_FakeWindowWithView._check_schema_conflict = DeskWindow._check_schema_conflict
_FakeWindowWithView._is_instance_currently_placed = DeskWindow._is_instance_currently_placed
_FakeWindowWithView._notify_schema_conflict = DeskWindow._notify_schema_conflict
_FakeWindowWithView._show_schema_conflict_popup = DeskWindow._show_schema_conflict_popup
_FakeWindowWithView.find_frame_by_instance_id = DeskWindow.find_frame_by_instance_id
_FakeWindowWithView.start_html_job = DeskWindow.start_html_job
_FakeWindowWithView.get_widget_info = DeskWindow.get_widget_info


JOB_SCRIPT_JS = """
<!doctype html><html><body><script>
(async () => {
  const results = {};
  try {
    await window.desk.workspace.getState();
    results.workspace = "ok";
  } catch (e) {
    results.workspace = "error:" + e.status;
  }
  try {
    await window.desk.fs.readFile("nonexistent.txt");
    results.fs = "ok";
  } catch (e) {
    results.fs = "error:" + e.status;
  }
  console.log(JSON.stringify(results));
})();
</script></body></html>
"""


def _make_job_definition(capabilities):
    return JobDefinition(
        kind="html",
        summary="Fetch workspace state via the Bridge API",
        script_b64=base64.b64encode(JOB_SCRIPT_JS.encode("utf-8")).decode("ascii"),
        capabilities=capabilities,
    )


def test_start_html_job_materializes_mounts_registers_and_places():
    import tempfile

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d) / "project"
        directory.mkdir()
        widgets_dir = Path(d) / "widgets"
        widgets_dir.mkdir()
        handle = start_server(widgets_dir=widgets_dir)
        try:
            win = _FakeWindowWithView(directory, handle)
            handle.gui_bridge.attach(win)
            definition = _make_job_definition(["workspace"])
            job_id = "test-job-1"

            statuses = []
            win.start_html_job(job_id, definition, lambda status, detail: statuses.append((status, detail)))

            check(
                "materialized a real index.html under .desk_temp/jobs/<job_id>/",
                (directory / ".desk_temp" / "jobs" / job_id / "index.html").is_file(),
            )
            check("the job's WidgetInfo was registered in self._widgets", job_id in win._widgets)
            check("the registered WidgetInfo carries the declared capabilities", win._widgets[job_id].capabilities == ["workspace"])
            check("the registered WidgetInfo is tempui_only (excluded from the spawn menu)", win._widgets[job_id].tempui_only is True)
            check("mount_html_widget registered it on the real server too", job_id in handle.widgets)
            frame = None
            for f in win.view._frames:
                if f.instance_id == job_id:
                    frame = f
            check("the placed frame's content is a real ChromiumWidget", frame is not None and isinstance(frame.content, ChromiumWidget))
            check("on_status fired 'executing' immediately", statuses[0] == ("executing", ""))

            pump(3)
            check("on_status eventually fired 'done' (real loadFinished)", any(s == ("done", "") for s in statuses))

            console_log = frame.content.get_console_log()
            info_entries = [e for e in console_log if e.level == "info"]
            check("the job's script logged its results", len(info_entries) >= 1)
            if info_entries:
                results = json.loads(info_entries[-1].message)
                check("the declared 'workspace' capability call succeeded", results.get("workspace") == "ok")
                check(
                    "the undeclared 'fs' capability call was rejected with a real 403",
                    results.get("fs") == "error:403",
                )
        finally:
            handle.stop()


def test_start_html_job_reports_errored_for_malformed_script():
    import tempfile

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d) / "project"
        directory.mkdir()
        widgets_dir = Path(d) / "widgets"
        widgets_dir.mkdir()
        handle = start_server(widgets_dir=widgets_dir)
        try:
            win = _FakeWindowWithView(directory, handle)
            handle.gui_bridge.attach(win)
            bad_definition = JobDefinition(
                kind="html", summary="Bad job", script_b64="not-valid-base64!!!", capabilities=[]
            )
            statuses = []
            win.start_html_job("bad-job", bad_definition, lambda status, detail: statuses.append((status, detail)))
            check("a malformed script reports errored, not a crash", statuses == [("errored", "Failed to decode this Job's script content.")])
            check("nothing was registered for a job that failed to materialize", "bad-job" not in win._widgets)
        finally:
            handle.stop()


test_start_html_job_materializes_mounts_registers_and_places()
test_start_html_job_reports_errored_for_malformed_script()

# os._exit(), not sys.exit(): this script places a real ChromiumWidget
# (real QWebEngineProfile) -- see
# verify_kind_html_auth_token_and_profile_isolation.py's identical
# comment (TODO a5f66cc) for why.
print(f"\n{passed} passed, {failed} failed")
sys.stdout.flush()
os._exit(1 if failed else 0)
