# TODO fd2c1ba: the [RELOAD] titlebar button. Visibility rules (web
# widget only, replaced by [STALE], hidden while locked/popup/title_only),
# button-kind recognition, and the handler reloading only the clicked frame.
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.widget_frame  # noqa: E402  (imported before QApplication -- WebEngine ordering)
import desk.shell.canvas as canvas_mod  # noqa: E402
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402,F401
from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk.shell.widget_frame import WidgetFrame, _ReloadButton, _TitleBar, _button_target_width  # noqa: E402
from desk.shell.window import DeskWindow  # noqa: E402

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


class _ReloadableContent(QWidget):
    widget_id = "Fake"

    def __init__(self):
        super().__init__()
        self.reloads = 0

    def reload(self):
        self.reloads += 1


class _PlainContent(QWidget):
    widget_id = "Plain"


bar = _TitleBar("T")
bar.show()
check("hidden by default (not reloadable)", not bar.reload_button.isVisible())
bar.set_reloadable(True)
check("shown when reloadable", bar.reload_button.isVisible())
bar.set_stale(True)
check("[STALE] replaces [RELOAD]", bar.stale_button.isVisible() and not bar.reload_button.isVisible())
w_stale = bar.min_full_width_px()
bar.set_stale(False)
check("[RELOAD] back when not stale", bar.reload_button.isVisible() and not bar.stale_button.isVisible())
check("full-width bookkeeping counts exactly one of the two", abs(bar.min_full_width_px() - w_stale) < 20)
check("target width is text-sized, not a square", _button_target_width(bar.reload_button) > 40)
bar.set_locked(True)
check("still shown while locked (same slot rules as [STALE])", bar.reload_button.isVisible())
bar.set_locked(False)
bar.set_buttons_hidden(True)
check("hidden in title_only", not bar.reload_button.isVisible())
bar.set_buttons_hidden(False)
popup = _TitleBar("P", is_popup=True)
popup.set_reloadable(True)
popup.show()
check("never on a popup", not popup.reload_button.isVisible())
check("not user-selectable label", not bool(bar.reload_button._label.textInteractionFlags()))

check('"reload" is a recognized button kind', "reload" in canvas_mod._BUTTON_KINDS)

web = _ReloadableContent()
frame = WidgetFrame("Web", web)
check("frame over a content with reload() is reloadable", frame._titlebar._reloadable)
check("frame over a python-style content is not", not WidgetFrame("Py", _PlainContent())._titlebar._reloadable)

other = _ReloadableContent()
other_frame = WidgetFrame("Other", other)
DeskWindow._on_widget_reload_clicked(None, frame)
check("handler reloads the clicked frame only", web.reloads == 1 and other.reloads == 0)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
