from PyQt6.QtCore import QUrl
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QVBoxLayout, QWidget

DEFAULT_URL = "about:blank"


class BrowserWidget(QWidget):
    """A simple embedded browser: an address bar plus back/forward/reload,
    for browsing arbitrary URLs from the canvas -- distinct from
    ChromiumWidget, which loads one fixed kind:"html" widget's own bundled
    page, not arbitrary user-navigable ones. A `python`-kind widget using
    QWebEngineView directly, the same "python widgets can use any PyQt6
    module directly" pattern the Console (`pty`) and Editor (`QScintilla`)
    widgets already established. See plans/browser-widget.md."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._view = QWebEngineView()
        self._view.urlChanged.connect(self._on_url_changed)

        self._back_button = QPushButton("◀")
        self._back_button.clicked.connect(self._view.back)
        self._forward_button = QPushButton("▶")
        self._forward_button.clicked.connect(self._view.forward)
        self._reload_button = QPushButton("⟳")
        self._reload_button.clicked.connect(self._view.reload)

        self._address_bar = QLineEdit()
        self._address_bar.returnPressed.connect(self._navigate_to_address_bar)

        toolbar = QHBoxLayout()
        toolbar.addWidget(self._back_button)
        toolbar.addWidget(self._forward_button)
        toolbar.addWidget(self._reload_button)
        toolbar.addWidget(self._address_bar, stretch=1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(toolbar)
        layout.addWidget(self._view, stretch=1)

        self._view.setUrl(QUrl(DEFAULT_URL))
        self._update_nav_buttons()

    def _navigate_to_address_bar(self) -> None:
        text = self._address_bar.text().strip()
        if not text:
            return
        # Qt's own standard address-bar-style URL interpretation (a full
        # URL, a bare hostname like "example.com", etc.) rather than
        # hand-rolled URL-guessing heuristics.
        self._view.setUrl(QUrl.fromUserInput(text))

    def _on_url_changed(self, url: QUrl) -> None:
        self._address_bar.setText(url.toString())
        self._update_nav_buttons()

    def _update_nav_buttons(self) -> None:
        history = self._view.history()
        self._back_button.setEnabled(history.canGoBack())
        self._forward_button.setEnabled(history.canGoForward())


def build() -> QWidget:
    return BrowserWidget()
