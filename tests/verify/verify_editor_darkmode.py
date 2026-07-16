import importlib.util
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from PyQt6.Qsci import QsciScintilla  # noqa: E402
from PyQt6.QtGui import QColor  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)


def load_widget_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


editor_mod = load_widget_module("editor_darkmode_verify_mod", "widgets/editor/widget.py")


def scintilla_bgr_to_qcolor(value: int) -> QColor:
    """QsciScintilla exposes no getter for caret color; SCI_GETCARETFORE
    returns a raw Scintilla "colour" int, which is BGR-ordered (0x00BBGGRR)
    -- confirmed directly by round-tripping a known QColor through
    setCaretForegroundColor/SendScintilla(SCI_GETCARETFORE)."""
    b = (value >> 16) & 0xFF
    g = (value >> 8) & 0xFF
    r = value & 0xFF
    return QColor(r, g, b)


def test_base_colors_and_caret():
    widget = editor_mod.EditorWidget()
    editor = widget.editor
    assert editor.color() == QColor(editor_mod.EDITOR_FOREGROUND)
    assert editor.paper() == QColor(editor_mod.EDITOR_BACKGROUND)
    caret_color = scintilla_bgr_to_qcolor(editor.SendScintilla(QsciScintilla.SCI_GETCARETFORE))
    assert caret_color == QColor(editor_mod.CARET_COLOR), caret_color.name()
    print("base text/background colors and caret color set correctly: PASS")


def test_line_number_color_differs_from_main_text():
    widget = editor_mod.EditorWidget()
    editor = widget.editor
    # setMarginsForegroundColor has no getter -- it sets STYLE_LINENUMBER's
    # foreground (SCI_STYLESETFORE), read back via SCI_STYLEGETFORE.
    raw = editor.SendScintilla(QsciScintilla.SCI_STYLEGETFORE, QsciScintilla.STYLE_LINENUMBER)
    margin_fg = scintilla_bgr_to_qcolor(raw)
    assert margin_fg != editor.color()
    assert margin_fg == QColor(editor_mod.LINE_NUMBER_COLOR), margin_fg.name()
    print("line-number color is a distinct, dimmer shade of the main text color: PASS")


def test_margin_background_matches_editor_no_white_block():
    widget = editor_mod.EditorWidget()
    editor = widget.editor
    # setMarginsBackgroundColor sets STYLE_LINENUMBER's background
    # (SCI_STYLESETBACK) for a NumberMargin -- SCI_SETMARGINBACKN (what
    # marginBackgroundColor() reads) only applies to a SC_MARGIN_COLOUR
    # -typed margin (confirmed directly: margin 0's marginBackgroundColor
    # was untouched/default, not what setMarginsBackgroundColor set).
    raw = editor.SendScintilla(QsciScintilla.SCI_STYLEGETBACK, QsciScintilla.STYLE_LINENUMBER)
    margin_bg = scintilla_bgr_to_qcolor(raw)
    assert margin_bg == editor.paper(), margin_bg.name()
    assert margin_bg != QColor("white")
    print("number margin background matches the editor's own (no white block): PASS")


def test_divider_margin_is_distinct():
    widget = editor_mod.EditorWidget()
    editor = widget.editor
    assert editor.marginType(1) == QsciScintilla.MarginType.SymbolMarginColor
    assert editor.marginWidth(1) > 0
    divider_color = editor.marginBackgroundColor(1)
    number_margin_bg = scintilla_bgr_to_qcolor(
        editor.SendScintilla(QsciScintilla.SCI_STYLEGETBACK, QsciScintilla.STYLE_LINENUMBER)
    )
    assert divider_color != number_margin_bg
    assert divider_color != editor.paper()
    assert divider_color == QColor(editor_mod.MARGIN_DIVIDER_COLOR)
    print("divider margin is a genuinely distinct color from both the number margin and editor bg: PASS")


def test_wrap_mode_enabled():
    widget = editor_mod.EditorWidget()
    assert widget.editor.wrapMode() == QsciScintilla.WrapMode.WrapWord
    print("word wrap is enabled by default: PASS")


def test_open_and_lex_real_file_still_works():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "example.py"
        path.write_text("def f():\n    return 1\n")
        widget = editor_mod.EditorWidget()
        widget.set_file(path)
        assert widget.editor.text() == "def f():\n    return 1\n"
        assert widget.editor.lexer() is not None
        # Colors from this change persist after opening a real, lexed file.
        assert widget.editor.paper() == QColor(editor_mod.EDITOR_BACKGROUND)
        caret_color = scintilla_bgr_to_qcolor(widget.editor.SendScintilla(QsciScintilla.SCI_GETCARETFORE))
        assert caret_color == QColor(editor_mod.CARET_COLOR)
    print("opening/lexing a real file still works with the new colors set: PASS")


test_base_colors_and_caret()
test_line_number_color_differs_from_main_text()
test_margin_background_matches_editor_no_white_block()
test_divider_margin_is_distinct()
test_wrap_mode_enabled()
test_open_and_lex_real_file_still_works()
print("ALL PASS")
