from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QSlider, QWidget

MIN_PERCENT = 10
MAX_PERCENT = 400
SLIDER_WIDTH = 100


class ZoomControl(QWidget):
    """A small HUD floating over the Workspace Canvas's lower-right corner
    (a plain child widget of the viewport, not a scene item, so it renders
    in screen space unaffected by the canvas's zoom/pan). Always visible
    (TODO e4662a5), matching the Desk picker's own always-visible HUD.
    See design-docs/widget-ux.md."""

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
        # TODO e4662a5: now that this HUD is always visible (not just
        # while hidden), a keyboard-focusable QPushButton here would
        # otherwise steal the application's initial focus on the very
        # first view.show() -- confirmed directly this broke the canvas's
        # own scene-focus tracking (WorkspaceView._on_scene_focus_item_
        # changed never fired for a real widget's setFocus() because a
        # native sibling widget, not the canvas, already held focus).
        # This HUD is mouse-only by design (matching DeskPicker's
        # NoTextInteraction labels), so it never needs to hold focus.
        fit_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        fit_button.clicked.connect(self.fit_requested)
        layout.addWidget(fit_button)

        reset_button = QPushButton("100%")
        reset_button.setFlat(True)
        reset_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        reset_button.clicked.connect(self.reset_requested)
        layout.addWidget(reset_button)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(MIN_PERCENT, MAX_PERCENT)
        self._slider.setFixedWidth(SLIDER_WIDTH)
        self._slider.setValue(100)
        self._slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
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
