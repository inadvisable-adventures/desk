import importlib.util
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from PyQt6.QtGui import QColor  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
spec = importlib.util.spec_from_file_location("editor_find_verify_mod", "widgets/editor/widget.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

w = mod.EditorWidget()
w.editor.setText("alpha beta\ngamma beta\ndelta beta\n")
w.editor.setCursorPosition(1, 0)
w._find_box.setText("beta")
assert w.editor.getSelection() == (1, 6, 1, 10), w.editor.getSelection()
w._find_step(True)
assert w.editor.getSelection() == (2, 6, 2, 10), w.editor.getSelection()
w._find_step(True)  # wraps
assert w.editor.getSelection() == (0, 6, 0, 10), w.editor.getSelection()
w._find_step(False)  # wraps backwards
assert w.editor.getSelection() == (2, 6, 2, 10), w.editor.getSelection()
w._find_step(False)
assert w.editor.getSelection() == (1, 6, 1, 10), w.editor.getSelection()
w._find_box.setText("zzz")
assert w._find_box.styleSheet() == mod.FIND_NOT_FOUND_STYLE
w._find_box.setText("gam")
assert w.editor.getSelection()[:2] == (1, 0)
assert w._find_box.styleSheet() == ""
print("live find, next, previous, wrap, not-found: PASS")

for hexcolor in ("#000000", "#303030", "#0000ff", "#000080"):
    out = mod.legible_on_dark(QColor(hexcolor))
    assert out.lightnessF() >= mod.MIN_TOKEN_LIGHTNESS - 0.01, (hexcolor, out.name())
print("dark/blue token colors lightened: PASS")

from pathlib import Path  # noqa: E402
w._current_path = Path("x.py")
w._apply_lexer(w._current_path)
lexer = w.editor.lexer()
for style in range(mod.MAX_LEXER_STYLE):
    if lexer.description(style):
        assert lexer.color(style).lightnessF() >= mod.MIN_TOKEN_LIGHTNESS - 0.01, style
        assert lexer.paper(style) == QColor(mod.EDITOR_BACKGROUND), style
print("python lexer styles all legible on dark paper: PASS")
