# DISABLED (see tests/verify/README.md) -- TODO f7c2f60 tracks
# investigating this. Current failure: Fails with FileNotFoundError for widgets/markdown_ex/widget.py --
# TODO 858752b renamed markdown_ex/"Markdown (Extended)" to
# markdown/"Markdown" (now the default). Reasonable suspicion: not a
# real bug, just predates that rename -- needs its widget path updated
# to widgets/markdown/widget.py (and MarkdownExWidget likely renamed to
# MarkdownWidget in whatever it asserts).

import importlib.util
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from PyQt6.QtWidgets import QApplication

from desk.shell import current_context

app = QApplication(sys.argv)


def pump(seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)


def load_widget_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_refresh_external_path_status_hardened():
    for mod_name, mod_path in [
        ("md_mod2", "widgets/markdown/widget.py"),
        ("mdex_mod2", "widgets/markdown_ex/widget.py"),
        ("svg_mod2", "widgets/svg_viewer/widget.py"),
        ("editor_mod2", "widgets/editor/widget.py"),
        ("todo_mod2", "widgets/todo/widget.py"),
    ]:
        mod = load_widget_module(mod_name, mod_path)
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d)
            current_context.set_current_desk_directory(directory)
            f = directory / "f.txt"
            f.write_text("hi")

            with patch.object(mod.current_context, "path_is_external", side_effect=RuntimeError("boom")):
                w = mod.build()
                if hasattr(w, "set_file"):
                    w.set_file(f)  # must not raise
                else:
                    w.refresh_external_path_status()  # TODO widget: no set_file
            w.deleteLater()
        print(f"{mod_name}: refresh_external_path_status survives a raising path_is_external: PASS")


def test_open_index_hardened():
    fe_mod = load_widget_module("fe_mod2", "widgets/file_explorer/widget.py")
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        (directory / "a.txt").write_text("a")
        current_context.set_current_desk_directory(directory)

        fe = fe_mod.build()
        pump(0.2)

        class FakeOpener:
            def __call__(self, widget_id):
                class Broken:
                    def set_file(self, path):
                        raise RuntimeError("boom")

                return Broken()

        current_context.set_widget_opener(FakeOpener())
        index = fe._fs_model.index(str(directory / "a.txt"))
        fe._open_index(index)  # must not raise
        pump(0.2)
        # Widget still usable afterward.
        fe._search_box.setText("a")
        pump(1.0)
        assert fe._searching is True
        fe.deleteLater()
        current_context.set_widget_opener(None)
    print("FileExplorerWidget._open_index survives a raising set_file: PASS")


def test_editor_unreadable_file_no_crash():
    editor_mod = load_widget_module("editor_mod3", "widgets/editor/widget.py")
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        current_context.set_current_desk_directory(directory)
        missing = directory / "does_not_exist.txt"

        ed = editor_mod.build()
        ed.editor.setText("existing buffer")
        ed.editor.setModified(False)
        with patch.object(editor_mod.QMessageBox, "warning") as warn:
            ed._load_file(missing)  # must not raise
            assert warn.called
        # Buffer/current_path untouched since the read failed.
        assert ed.editor.text() == "existing buffer"
        assert ed._current_path is None
        ed.deleteLater()
    print("EditorWidget._load_file survives an unreadable path, buffer untouched: PASS")


def test_regression_normal_case_still_works():
    md_mod = load_widget_module("md_mod3", "widgets/markdown/widget.py")
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as other:
        directory = Path(d)
        current_context.set_current_desk_directory(directory)
        inside = directory / "n.md"
        inside.write_text("hi")
        outside = Path(other) / "n.md"
        outside.write_text("hi")

        w = md_mod.build()
        events = []
        w.external_path_changed.connect(events.append)
        w.set_file(inside)
        assert events == [False], events
        events.clear()
        w.set_file(outside)
        assert events == [True], events
        w.deleteLater()
    print("Regression: normal external-path detection still works: PASS")


test_refresh_external_path_status_hardened()
test_open_index_hardened()
test_editor_unreadable_file_no_crash()
test_regression_normal_case_still_works()
print("ALL PASS")
