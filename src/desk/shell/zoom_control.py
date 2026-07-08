from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QSlider, QWidget

MIN_PERCENT = 10
MAX_PERCENT = 400
SLIDER_WIDTH = 100


class ZoomControl(QWidget):
    """A small HUD floating over the Workspace Canvas's lower-right corner
    (a plain child widget of the viewport, not a scene item, so it renders
    in screen space unaffected by the canvas's zoom/pan). Shown only when
    the canvas is at non-unity zoom. See design-docs/widget-ux.md."""

    fit_requested = pyqtSignal()
    reset_requested = pyqtSignal()
    zoom_changed = pyqtSignal(float)  # absolute target scale, e.g. 1.5 for 150%

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            "background-color: rgba(40, 42, 46, 220); border-radius: 6px; color: #e8e8e8;"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        fit_button = QPushButton("Fit")
        fit_button.setFlat(True)
        fit_button.clicked.connect(self.fit_requested)
        layout.addWidget(fit_button)

        reset_button = QPushButton("100%")
        reset_button.setFlat(True)
        reset_button.clicked.connect(self.reset_requested)
        layout.addWidget(reset_button)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(MIN_PERCENT, MAX_PERCENT)
        self._slider.setFixedWidth(SLIDER_WIDTH)
        self._slider.setValue(100)
        self._slider.valueChanged.connect(self._on_slider_changed)
        layout.addWidget(self._slider)

        self._updating = False

    def _on_slider_changed(self, percent: int) -> None:
        if not self._updating:
            self.zoom_changed.emit(percent / 100)

    def set_zoom(self, scale: float) -> None:
        self._updating = True
        try:
            self._slider.setValue(round(max(MIN_PERCENT, min(MAX_PERCENT, scale * 100))))
        finally:
            self._updating = False
