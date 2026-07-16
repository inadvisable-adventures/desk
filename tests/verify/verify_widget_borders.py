import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from desk.shell.widget_frame import WidgetFrame, BORDER_COLOR  # noqa: E402
from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402

app = QApplication(sys.argv)


def test_border_present_by_default():
    frame = WidgetFrame("Test", QWidget())
    style = frame.styleSheet()
    assert "border:" in style
    assert BORDER_COLOR in style
    assert "1px" in style
    print("WidgetFrame has a border by default: PASS")


def test_border_scoped_to_class_name():
    frame = WidgetFrame("Test", QWidget())
    style = frame.styleSheet()
    assert style.strip().startswith("WidgetFrame {"), style
    print("border rule is scoped to the WidgetFrame class name: PASS")


def test_border_counter_scales_with_zoom():
    frame = WidgetFrame("Test", QWidget())
    frame.set_view_scale(2.0)
    style_2x = frame.styleSheet()
    frame.set_view_scale(0.5)
    style_half = frame.styleSheet()
    # At 2x zoom the local thickness should be thinner (rounds to a
    # smaller or equal local px) than at 0.5x zoom.
    import re

    px_2x = int(re.search(r"(\d+)px", style_2x).group(1))
    px_half = int(re.search(r"(\d+)px", style_half).group(1))
    assert px_2x <= px_half, (px_2x, px_half)
    assert px_2x >= 1
    print("border thickness counter-scales with view zoom: PASS")


test_border_present_by_default()
test_border_scoped_to_class_name()
test_border_counter_scales_with_zoom()
print("ALL PASS")
