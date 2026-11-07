"""TODO 99ed232: clicking a link in the Markdown widget never replaces the block's text."""
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from PyQt6.QtCore import QPoint, Qt, QUrl  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from desk.shell import current_context  # noqa: E402

app = QApplication.instance() or QApplication([])
spec = importlib.util.spec_from_file_location("markdown_widget", REPO_ROOT / "widgets/markdown/widget.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

passed = failed = 0


def check(name, ok):
    global passed, failed
    if ok:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


opened = []
current_context.set_editor_or_scrap_opener(lambda p: opened.append(p))

with tempfile.TemporaryDirectory() as d:
    base = Path(d)
    (base / "LICENSE").write_text("PROJECT LICENSE")
    text = "See [LICENSE](./LICENSE) for the full text.\n"
    b = mod._AutoHeightTextBrowser(text, base)
    b.resize(600, 200)
    b.show()
    before = b.toPlainText()

    pos = next(
        (QPoint(x, y) for x in range(0, 400, 4) for y in range(0, 80, 4) if b.anchorAt(QPoint(x, y))),
        None,
    )
    check("found the link in the rendered block", pos is not None)
    QTest.mouseClick(b.viewport(), Qt.MouseButton.LeftButton, pos=pos)
    check("clicking a relative link leaves the block's text alone", b.toPlainText() == before)
    check("relative link opens the file resolved against the markdown's directory", opened == [base / "LICENSE"])

    opened.clear()
    b._on_anchor_clicked(QUrl("./MISSING"))
    check("missing target opens nothing", opened == [])
    b._on_anchor_clicked(QUrl(f"file://{base}/LICENSE"))
    check("file: URL opens that file", opened == [base / "LICENSE"])

    launched = []
    orig = mod.QDesktopServices.openUrl
    mod.QDesktopServices.openUrl = staticmethod(lambda u: launched.append(u.toString()) or True)
    try:
        b._on_anchor_clicked(QUrl("https://example.com/x"))
    finally:
        mod.QDesktopServices.openUrl = orig
    check("http link goes to the system handler", launched == ["https://example.com/x"])
    opened.clear()
    b._on_anchor_clicked(QUrl("#section"))
    check("fragment-only link opens no file", opened == [] and b.toPlainText() == before)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
