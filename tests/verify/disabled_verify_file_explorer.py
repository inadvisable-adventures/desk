# DISABLED (see tests/verify/README.md) -- TODO 294f8a2 tracks
# investigating this. Current failure: Fails at import time: `import widget as fe_module` expects a
# file_explorer widget directory, but TODO 8385dcc renamed it to
# project_files (ProjectFilesWidget). Reasonable suspicion: not a real
# bug, just predates the rename -- verify_rename_project_files.py/
# verify_file_explorer_fallback_chain.py-style scripts already cover the
# renamed widget's behavior, so this one is likely safe to delete.

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")
sys.path.insert(0, "widgets/file_explorer")

from PyQt6.QtWidgets import QApplication, QFileDialog

from desk.shell import current_context

app = QApplication(sys.argv)


def pump(seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)


import widget as fe_module

with tempfile.TemporaryDirectory() as d:
    directory = Path(d)
    (directory / "alpha.txt").write_text("a")
    (directory / "beta.txt").write_text("b")
    current_context.set_current_desk_directory(directory)

    w = fe_module.build()
    pump(0.2)

    # Style applied and kept alive (no crash / no dangling QStyle).
    assert w._toolbar_style is not None
    from PyQt6.QtWidgets import QPushButton, QLineEdit

    open_btn = w.findChild(QPushButton)
    assert open_btn is not None
    assert open_btn.style().objectName() == "fusion", open_btn.style().objectName()
    assert w._search_box.style().objectName() == "fusion", w._search_box.style().objectName()
    print("fusion style applied to both controls: PASS")

    # Open Folder button still wired to _choose_root (patch the file
    # dialog so it doesn't actually block on a real dialog).
    chosen = []
    orig_choose_root = w._choose_root

    def fake_choose_root():
        chosen.append(1)

    w._choose_root = fake_choose_root
    open_btn.clicked.disconnect()
    open_btn.clicked.connect(w._choose_root)
    open_btn.click()
    pump(0.2)
    assert chosen == [1]
    print("Open Folder button still clickable: PASS")

    # Search box still filters the tree (unchanged behavior).
    w._search_box.setText("alpha")
    pump(1.0)
    assert w._searching is True
    print("search still functions: PASS")

    w.deleteLater()
    app.processEvents()

print("ALL PASS")
