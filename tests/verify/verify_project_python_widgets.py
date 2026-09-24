import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.widget_frame  # noqa: E402  (imported before QApplication -- WebEngine ordering)
import desk.shell.canvas  # noqa: E402
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402,F401

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

import desk.temp_ui as temp_ui  # noqa: E402
from desk.hotreload import HotReloadBroker  # noqa: E402
from desk.shell.python_widget import PythonWidgetHost  # noqa: E402
from desk.shell.window import DeskWindow  # noqa: E402
from desk.widgets import WidgetInfo, discover_project_widgets  # noqa: E402

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


def _write_manifest(path, manifest):
    path.mkdir(parents=True)
    (path / "widget.json").write_text(json.dumps(manifest))


# ---------- discover_project_widgets ----------


def test_discovers_valid_python_widget():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        root = Path(d)
        widget_dir = root / "my-widget"
        _write_manifest(widget_dir, {"name": "My Widget", "kind": "python"})
        (widget_dir / "widget.py").write_text("def build():\n    pass\n")
        result = discover_project_widgets(root)
        check("valid python widget discovered", "my-widget" in result)
        check("kind is python", result["my-widget"].kind == "python")
        check("entry defaults to widget.py", result["my-widget"].entry == "widget.py")


def test_skips_tempui_promoted_source_shape():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        root = Path(d)
        _write_manifest(
            root / "Promoted",
            {"keyword": "Promoted", "label": "x", "width": 200, "height": 200},
        )
        result = discover_project_widgets(root)
        check("no-'kind' widget.json (promoted tempui source) is skipped, not an error", result == {})


def test_html_kind_not_yet_supported():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        root = Path(d)
        _write_manifest(root / "my-html-widget", {"name": "HTML", "kind": "html"})
        result = discover_project_widgets(root)
        check("kind:html project widget is skipped (not wired up yet)", result == {})


def test_invalid_kind_skipped_not_raised():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        root = Path(d)
        _write_manifest(root / "bad-kind", {"name": "bad", "kind": "rust"})
        result = discover_project_widgets(root)
        check("invalid kind value is skipped rather than raising", result == {})


def test_malformed_json_skipped_not_raised():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        root = Path(d)
        (root / "malformed").mkdir()
        (root / "malformed" / "widget.json").write_text("{not json")
        result = discover_project_widgets(root)
        check("malformed widget.json is skipped rather than raising", result == {})


def test_missing_directory_returns_empty():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        missing = Path(d) / "desk_widgets"
        check("missing desk_widgets/ returns {}", discover_project_widgets(missing) == {})


# ---------- DeskWindow._load_project_widgets ----------


class _FakeView:
    def set_widget_catalog(self, catalog):
        pass


class _FakeWindow:
    def __init__(self, widgets=None):
        self._widgets = widgets if widgets is not None else {}
        self._widgets_dir = Path(".")
        self._broker = HotReloadBroker()
        self._project_widget_ids = set()
        self._project_widget_watcher = None
        self.view = _FakeView()


_FakeWindow._load_project_widgets = DeskWindow._load_project_widgets


def _make_project_python_widget(project_dir, name):
    widget_dir = project_dir / temp_ui.PROMOTED_WIDGET_SRC_DIRNAME / name
    _write_manifest(widget_dir, {"name": name, "kind": "python"})
    (widget_dir / "widget.py").write_text("def build():\n    pass\n")


def test_load_project_widgets_merges_into_catalog():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        project_dir = Path(d)
        _make_project_python_widget(project_dir, "my-widget")
        win = _FakeWindow()
        desk = type("D", (), {"directory": project_dir})()
        win._load_project_widgets(desk)
        check("project widget merged into self._widgets", "my-widget" in win._widgets)
        check("project widget id tracked", "my-widget" in win._project_widget_ids)
        check("watcher created", win._project_widget_watcher is not None)
        win._project_widget_watcher.stop()


def test_load_project_widgets_refuses_to_shadow_existing_id():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        project_dir = Path(d)
        _make_project_python_widget(project_dir, "todo")
        sentinel = WidgetInfo(
            id="todo", path=Path("/builtin"), kind="python", name="TODO",
            entry="widget.py", capabilities=[], default_size=None,
        )
        win = _FakeWindow(widgets={"todo": sentinel})
        desk = type("D", (), {"directory": project_dir})()
        win._load_project_widgets(desk)
        check("colliding project widget id is refused", win._widgets["todo"] is sentinel)
        check("colliding id is not tracked as a project widget", "todo" not in win._project_widget_ids)
        win._project_widget_watcher.stop()


def test_load_project_widgets_reuses_watcher_for_same_directory():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        project_dir = Path(d)
        _make_project_python_widget(project_dir, "my-widget")
        win = _FakeWindow()
        desk = type("D", (), {"directory": project_dir})()
        win._load_project_widgets(desk)
        first_watcher = win._project_widget_watcher
        win._load_project_widgets(desk)
        check("same project directory: watcher instance reused", win._project_widget_watcher is first_watcher)
        win._project_widget_watcher.stop()


def test_load_project_widgets_repoints_watcher_on_directory_change():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d1, \
            tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d2:
        project_dir_1 = Path(d1)
        project_dir_2 = Path(d2)
        _make_project_python_widget(project_dir_1, "widget-one")
        _make_project_python_widget(project_dir_2, "widget-two")
        win = _FakeWindow()
        win._load_project_widgets(type("D", (), {"directory": project_dir_1})())
        first_watcher = win._project_widget_watcher
        # Simulate switch_desk's own cleanup of the previous Desk's entries.
        for widget_id in list(win._project_widget_ids):
            win._widgets.pop(widget_id, None)
        win._project_widget_ids.clear()
        win._load_project_widgets(type("D", (), {"directory": project_dir_2})())
        check("different project directory: a new watcher is created", win._project_widget_watcher is not first_watcher)
        check("old project widget dropped after simulated switch", "widget-one" not in win._widgets)
        check("new project's widget picked up", "widget-two" in win._widgets)
        win._project_widget_watcher.stop()


# ---------- End-to-end: PythonWidgetHost loads a project-authored widget.py ----------


def test_python_widget_host_loads_arbitrary_project_path():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        widget_dir = Path(d)
        (widget_dir / "widget.py").write_text(
            "from PyQt6.QtWidgets import QLabel\n"
            "def build():\n"
            "    return QLabel('hi from a project widget')\n"
        )
        host = PythonWidgetHost("my-widget", widget_dir, "widget.py", HotReloadBroker())
        check("no build error for a valid project-authored widget.py", host.build_error == "")
        check("QWidget built from a path outside Desk's own repo tree", host._current.text() == "hi from a project widget")


# ---------- tempui changelog (development-process.md's "keep the tempui changelog docs current") ----------


def test_tempui_tag_registered():
    tag_id = "project-authored python widgets in desk_widgets #473197"
    check("new tag is in CURRENT_TAGS", tag_id in temp_ui.CURRENT_TAGS)
    check("new tag has a _NEW_FEATURES entry", tag_id in temp_ui._NEW_FEATURES)


def test_tempui_docs_render_the_new_section():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        temp_dir = Path(d) / temp_ui.TEMP_UI_DIRNAME
        temp_dir.mkdir()
        temp_ui.write_tempui_docs(temp_dir)
        doc = (temp_dir / temp_ui.DOC_FILENAME).read_text()
        check("desk-temporary-ui.md documents Project widgets", "Project widgets" in doc)
        new_features = (temp_dir / "tempui-new-features.md").read_text()
        check(
            "tempui-new-features.md includes the new tag's entry",
            "project-authored python widgets in desk_widgets" in new_features,
        )


test_discovers_valid_python_widget()
test_skips_tempui_promoted_source_shape()
test_html_kind_not_yet_supported()
test_invalid_kind_skipped_not_raised()
test_malformed_json_skipped_not_raised()
test_missing_directory_returns_empty()
test_load_project_widgets_merges_into_catalog()
test_load_project_widgets_refuses_to_shadow_existing_id()
test_load_project_widgets_reuses_watcher_for_same_directory()
test_load_project_widgets_repoints_watcher_on_directory_change()
test_python_widget_host_loads_arbitrary_project_path()
test_tempui_tag_registered()
test_tempui_docs_render_the_new_section()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
