# TODO 5928ae6: SheetWidget gains set_file(path) so it participates in
# the file-type-registry view-handler dispatch and drag-and-drop like
# Markdown/Image Viewer/Editor already do, with the same read-error
# robustness Editor has (a popup, not an inline message -- Sheet is
# editable, same reasoning EditorWidget._load_file's own docstring
# gives). Also .tsv/.tab added to EXTERNAL_DROP_WIDGET_BY_SUFFIX.
import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.widget_frame  # noqa: E402  (imported before QApplication -- WebEngine ordering)
import desk.shell.canvas  # noqa: E402
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402,F401

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk.shell import current_context  # noqa: E402

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


def load_widget_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sheet_mod = load_widget_module("sheet_widget_set_file_verify_mod", str(REPO_ROOT / "widgets" / "sheet" / "widget.py"))


def _grid_text(widget):
    return [
        [widget._table.item(r, c).text() for c in range(widget._table.columnCount())]
        for r in range(widget._table.rowCount())
    ]


def test_has_set_file_the_file_type_registry_dispatch_actually_checks():
    widget = sheet_mod.SheetWidget()
    check("hasattr(widget, 'set_file') is True -- the actual dispatch precondition", hasattr(widget, "set_file"))
    widget.deleteLater()


def test_set_file_loads_real_tsv_content():
    widget = sheet_mod.SheetWidget()
    with __import__("tempfile").TemporaryDirectory() as d:
        path = Path(d) / "data.tsv"
        path.write_text("a\tb\tc\n1\t2\t3\n")

        widget.set_file(path)

        check("set_file loads the same content _open_file's own dialog flow would", _grid_text(widget) == [["a", "b", "c"], ["1", "2", "3"]])
        check("set_file records the current path, matching _load_file", widget._current_path == path)
        check("a freshly loaded file is not dirty", widget._dirty is False)
    widget.deleteLater()


def test_set_file_matches_open_file_dialog_result():
    # set_file(path) must be indistinguishable from what _open_file's own
    # QFileDialog-driven flow already produces for the same file.
    with __import__("tempfile").TemporaryDirectory() as d:
        path = Path(d) / "data.tsv"
        path.write_text("x\ty\n1\t2\n")

        via_dialog = sheet_mod.SheetWidget()
        via_dialog._load_file(path)  # _open_file's own inner call, once QFileDialog returns a filename

        via_set_file = sheet_mod.SheetWidget()
        via_set_file.set_file(path)

        check("set_file produces the exact same grid as the dialog-driven path", _grid_text(via_dialog) == _grid_text(via_set_file))
        via_dialog.deleteLater()
        via_set_file.deleteLater()


def test_unreadable_path_shows_a_popup_and_leaves_state_untouched():
    widget = sheet_mod.SheetWidget()
    with __import__("tempfile").TemporaryDirectory() as d:
        existing = Path(d) / "existing.tsv"
        existing.write_text("keep\tme\n")
        widget.set_file(existing)
        before = _grid_text(widget)

        missing = Path(d) / "does_not_exist.tsv"
        with patch.object(current_context, "get_popup_opener", return_value=lambda *a: "OK") as get_opener:
            widget.set_file(missing)  # must not raise
            check("an unreadable path shows a popup, matching EditorWidget's own convention", get_opener.called)

        check("the grid is untouched after a failed open", _grid_text(widget) == before)
        check("current_path is untouched after a failed open", widget._current_path == existing)
    widget.deleteLater()


def test_unreadable_path_does_not_raise_with_no_popup_opener_registered():
    widget = sheet_mod.SheetWidget()
    with __import__("tempfile").TemporaryDirectory() as d:
        missing = Path(d) / "does_not_exist.tsv"
        with patch.object(current_context, "get_popup_opener", return_value=None):
            try:
                widget.set_file(missing)
                check("no popup opener registered: still doesn't raise", True)
            except Exception as e:  # noqa: BLE001
                check(f"no popup opener registered: still doesn't raise (raised {e!r})", False)
    widget.deleteLater()


def test_drop_suffix_map_includes_tsv_and_tab_not_txt_or_csv():
    import desk.shell.window as window_mod

    check("EXTERNAL_DROP_WIDGET_BY_SUFFIX maps .tsv to Sheet", window_mod.EXTERNAL_DROP_WIDGET_BY_SUFFIX.get(".tsv") == window_mod.SHEET_WIDGET_ID)
    check("EXTERNAL_DROP_WIDGET_BY_SUFFIX maps .tab to Sheet", window_mod.EXTERNAL_DROP_WIDGET_BY_SUFFIX.get(".tab") == window_mod.SHEET_WIDGET_ID)
    check("regression: .txt is deliberately NOT mapped to Sheet (stays on the Editor default)", ".txt" not in window_mod.EXTERNAL_DROP_WIDGET_BY_SUFFIX)
    check("regression: .csv is not mapped either (Sheet only parses tabs)", ".csv" not in window_mod.EXTERNAL_DROP_WIDGET_BY_SUFFIX)
    check("regression: the two pre-existing mappings are unchanged", window_mod.EXTERNAL_DROP_WIDGET_BY_SUFFIX.get(".md") == window_mod.MARKDOWN_WIDGET_ID and window_mod.EXTERNAL_DROP_WIDGET_BY_SUFFIX.get(".svg") == window_mod.IMAGE_VIEWER_WIDGET_ID)
    check("SHEET_WIDGET_ID matches the widget's own directory/discovery id", window_mod.SHEET_WIDGET_ID == "sheet")


test_has_set_file_the_file_type_registry_dispatch_actually_checks()
test_set_file_loads_real_tsv_content()
test_set_file_matches_open_file_dialog_result()
test_unreadable_path_shows_a_popup_and_leaves_state_untouched()
test_unreadable_path_does_not_raise_with_no_popup_opener_registered()
test_drop_suffix_map_includes_tsv_and_tab_not_txt_or_csv()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
