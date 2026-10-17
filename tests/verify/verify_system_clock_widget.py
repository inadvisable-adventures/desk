"""TODO ba11954: the built-in Python System Clock widget. Headless."""
import importlib.util
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from PyQt6.QtCore import QDate, QDateTime, QLocale, QTime, QTimeZone, Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
app = QApplication(sys.argv)
failed = 0


def check(name, ok):
    global failed
    print(("PASS" if ok else "FAIL"), name)
    failed += 0 if ok else 1


spec = importlib.util.spec_from_file_location("system_clock_check", REPO_ROOT / "widgets" / "system_clock" / "widget.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

widget = module.build()
fixed = QDateTime(QDate(2026, 10, 16), QTime(9, 5, 7))
widget.refresh(fixed)
check("time is zero-padded HH:MM:SS", widget._clock.text() == "09:05:07")
check("date is the long form including the weekday",
      QLocale().dayName(5, QLocale.FormatType.LongFormat) in widget._date.text() and "2026" in widget._date.text())
zone = bytes(QTimeZone.systemTimeZoneId()).decode()
check("zone line names the system IANA zone", widget._zone.text() == f"{zone} (system clock)" and zone != "")
check("labels are not user-selectable",
      all(label.textInteractionFlags() == Qt.TextInteractionFlag.NoTextInteraction
          for label in (widget._clock, widget._date, widget._zone)))
check("original sizes (56/15/11 px) and green clock colour kept",
      (widget._clock.font().pixelSize(), widget._date.font().pixelSize(), widget._zone.font().pixelSize()) == (56, 15, 11)
      and widget._clock.palette().windowText().color().name() == "#7cfc9a")
check("background is the charcoal #111418", widget.palette().window().color().name() == "#111418" and widget.autoFillBackground())

check("not ticking while hidden", not widget._timer.isActive())
widget.show()
app.processEvents()
check("ticks while visible", widget._timer.isActive())
check("live refresh replaces the fixed time", widget._clock.text() != "09:05:07")
widget.hide()
check("stops ticking when hidden", not widget._timer.isActive())

manifest = (REPO_ROOT / "widgets" / "system_clock" / "widget.json").read_text()
check("manifest is a capability-free python widget", '"kind": "python"' in manifest and '"capabilities": []' in manifest)
sys.exit(1 if failed else 0)
