import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402

from desk.shell.canvas import WorkspaceView  # noqa: E402

app = QApplication(sys.argv)


class _MultiField(QWidget):
    def __init__(self):
        super().__init__()
        self.field1 = QLineEdit()
        self.field2 = QLineEdit()
        layout = QVBoxLayout(self)
        layout.addWidget(self.field1)
        layout.addWidget(self.field2)


def _scene_focus_frame(view):
    item = view.scene().focusItem()
    return item.widget() if item is not None else None


def test_typing_never_moves_focus_between_overlapping_widgets():
    view = WorkspaceView()
    view.resize(800, 600)
    view.show()
    content_a = QLineEdit()
    content_b = QLineEdit()
    proxy_a = view.add_widget(content_a, "A", pos=(0, 0), size=(400, 300))
    view.add_widget(content_b, "B", pos=(100, 100), size=(400, 300))  # visually overlaps A

    content_a.setFocus(Qt.FocusReason.MouseFocusReason)
    app.processEvents()
    assert _scene_focus_frame(view) is proxy_a.widget()

    QTest.keyClicks(content_a, "The quick brown fox 1234567890")
    app.processEvents()
    assert _scene_focus_frame(view) is proxy_a.widget()
    assert content_a.text() == "The quick brown fox 1234567890"
    assert content_b.text() == ""
    print("typing ordinary characters never moves focus between overlapping widgets: PASS")


def test_tab_never_escapes_to_overlapping_sibling_single_field():
    view = WorkspaceView()
    view.resize(800, 600)
    view.show()
    content_a = QLineEdit()
    content_b = QLineEdit()
    proxy_a = view.add_widget(content_a, "A", pos=(0, 0), size=(400, 300))
    proxy_b = view.add_widget(content_b, "B", pos=(100, 100), size=(400, 300))
    frame_a, frame_b = proxy_a.widget(), proxy_b.widget()

    content_a.setFocus(Qt.FocusReason.MouseFocusReason)
    app.processEvents()

    for _ in range(3):
        QTest.keyClick(content_a, Qt.Key.Key_Tab)
        app.processEvents()
        assert content_a.hasFocus(), "Tab should leave the sole field focused, not clear it"
        assert _scene_focus_frame(view) is frame_a
        assert _scene_focus_frame(view) is not frame_b

    QTest.keyClicks(content_a, "still here")
    app.processEvents()
    assert content_a.text() == "still here"
    assert content_b.text() == ""
    print("repeated Tab on a single-field widget never leaks focus to an overlapping sibling: PASS")


def test_tab_wraps_within_multi_field_widget_without_escaping():
    view = WorkspaceView()
    view.resize(800, 600)
    view.show()
    content_a = _MultiField()
    content_b = QLineEdit()
    proxy_a = view.add_widget(content_a, "A", pos=(0, 0), size=(400, 300))
    proxy_b = view.add_widget(content_b, "B", pos=(100, 100), size=(400, 300))
    frame_a, frame_b = proxy_a.widget(), proxy_b.widget()

    content_a.field1.setFocus(Qt.FocusReason.MouseFocusReason)
    app.processEvents()

    QTest.keyClick(content_a.field1, Qt.Key.Key_Tab)
    app.processEvents()
    assert content_a.field2.hasFocus()
    assert _scene_focus_frame(view) is frame_a

    # Boundary: nothing further locally -- must wrap back to field1,
    # never escape to the overlapping sibling (frame_b).
    QTest.keyClick(content_a.field2, Qt.Key.Key_Tab)
    app.processEvents()
    assert content_a.field1.hasFocus(), "Tab from the last field should wrap to the first"
    assert _scene_focus_frame(view) is frame_a
    assert _scene_focus_frame(view) is not frame_b

    # Normal backward step still works.
    content_a.field2.setFocus(Qt.FocusReason.MouseFocusReason)
    app.processEvents()
    QTest.keyClick(content_a.field2, Qt.Key.Key_Backtab)
    app.processEvents()
    assert content_a.field1.hasFocus()
    assert _scene_focus_frame(view) is frame_a

    QTest.keyClicks(content_a.field1, "x")
    app.processEvents()
    assert content_a.field1.text() == "x"
    assert content_b.text() == ""
    print("Tab wraps between a widget's own multiple fields without ever escaping to a sibling: PASS")


def test_plain_text_edit_content_unaffected_regression():
    """QPlainTextEdit already consumes Tab itself (inserts a tab
    character) -- confirms this fix doesn't change that pre-existing,
    unrelated behavior."""
    view = WorkspaceView()
    view.resize(800, 600)
    view.show()
    content_a = QPlainTextEdit()
    content_b = QPlainTextEdit()
    view.add_widget(content_a, "A", pos=(0, 0), size=(400, 300))
    view.add_widget(content_b, "B", pos=(100, 100), size=(400, 300))

    content_a.setFocus(Qt.FocusReason.MouseFocusReason)
    app.processEvents()
    QTest.keyClick(content_a, Qt.Key.Key_Tab)
    app.processEvents()
    assert content_a.hasFocus()
    assert "\t" in content_a.toPlainText()
    assert content_b.toPlainText() == ""
    print("QPlainTextEdit's own Tab-inserts-a-tab-character behavior is unchanged: PASS")


test_typing_never_moves_focus_between_overlapping_widgets()
test_tab_never_escapes_to_overlapping_sibling_single_field()
test_tab_wraps_within_multi_field_widget_without_escaping()
test_plain_text_edit_content_unaffected_regression()
print("ALL PASS")
