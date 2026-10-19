from PyQt6.QtCore import QDateTime, QLocale, Qt, QTimeZone, QTimer
from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

TICK_INTERVAL_MS = 200

BACKGROUND = QColor("#111418")
CLOCK_COLOR = QColor("#7cfc9a")
DATE_COLOR = QColor("#9fb3a8")
ZONE_COLOR = QColor("#5f7268")
MONOSPACE_FAMILIES = ["SF Mono", "Menlo", "Courier New", "monospace"]


def _label(pixel_size: int, color: QColor, *, weight=QFont.Weight.Normal, letter_spacing: float = 0.0) -> QLabel:
    """A centered, non-selectable monospace label in a flat colour."""
    label = QLabel()
    font = QFont()
    font.setFamilies(MONOSPACE_FAMILIES)
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPixelSize(pixel_size)
    font.setWeight(weight)
    if letter_spacing:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, letter_spacing)
    label.setFont(font)
    palette = label.palette()
    palette.setColor(QPalette.ColorRole.WindowText, color)
    label.setPalette(palette)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
    return label


class SystemClockWidget(QWidget):
    """A plain live clock: HH:MM:SS, the long-form date and the system's IANA time zone name,
    in green-on-charcoal monospace. No state to persist and nothing to coordinate with other
    widgets (the Python port of the HTML System Clock from
    FEEDBACK-DESK-system-clock-widget-source-2026-10-16-2122.md). Ticks only while visible."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, BACKGROUND)
        self.setPalette(palette)

        self._clock = _label(56, CLOCK_COLOR, weight=QFont.Weight.DemiBold, letter_spacing=3.0)
        self._date = _label(15, DATE_COLOR, letter_spacing=1.0)
        self._zone = _label(11, ZONE_COLOR)
        layout = QVBoxLayout(self)
        layout.addStretch(1)
        layout.addWidget(self._clock)
        layout.addSpacing(10)
        layout.addWidget(self._date)
        layout.addSpacing(4)
        layout.addWidget(self._zone)
        layout.addStretch(1)

        self._timer = QTimer(self)
        self._timer.setInterval(TICK_INTERVAL_MS)
        self._timer.timeout.connect(self.refresh)
        self.refresh()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._timer.start()
        self.refresh()

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def refresh(self, now: QDateTime | None = None) -> None:
        now = now if now is not None else QDateTime.currentDateTime()
        self._set_text(self._clock, now.toString("HH:mm:ss"))
        self._set_text(self._date, self._long_date(now))
        zone = bytes(QTimeZone.systemTimeZoneId()).decode(errors="replace")
        self._set_text(self._zone, f"{zone} (system clock)")

    @staticmethod
    def _long_date(now: QDateTime) -> str:
        """The locale's long date, always with the weekday (Qt's long format omits it in some
        locales, e.g. en_US: `October 16, 2026`)."""
        locale = QLocale()
        date_format = locale.dateFormat(QLocale.FormatType.LongFormat)
        if "dddd" not in date_format:
            date_format = f"dddd, {date_format}"
        return locale.toString(now.date(), date_format)

    @staticmethod
    def _set_text(label: QLabel, text: str) -> None:
        if label.text() != text:
            label.setText(text)


def build() -> QWidget:
    return SystemClockWidget()
