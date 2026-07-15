from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtWebEngineCore import QWebEngineNewWindowRequest
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

DEFAULT_URL = "about:blank"
MAIN_PAGE_INDEX = 0
POPUP_PAGE_INDEX = 1


class BrowserWidget(QWidget):
    """A simple embedded browser: an address bar plus back/forward/reload,
    for browsing arbitrary URLs from the canvas -- distinct from
    ChromiumWidget, which loads one fixed kind:"html" widget's own bundled
    page, not arbitrary user-navigable ones. A `python`-kind widget using
    QWebEngineView directly, the same "python widgets can use any PyQt6
    module directly" pattern the Console (`pty`) and Editor (`QScintilla`)
    widgets already established. See plans/browser-widget.md.

    A pop-up (`window.open()`, `target="_blank"`, ...) is contained
    within this widget's own frame rather than escaping into a separate
    OS-level window (TODO `e35bcf0`) -- see `_on_new_window_requested`."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._view = QWebEngineView()
        self._view.urlChanged.connect(self._on_url_changed)
        self._view.page().newWindowRequested.connect(self._on_new_window_requested)

        self._back_button = QPushButton("◀")
        self._back_button.clicked.connect(self._view.back)
        self._forward_button = QPushButton("▶")
        self._forward_button.clicked.connect(self._view.forward)
        self._reload_button = QPushButton("⟳")
        self._reload_button.clicked.connect(self._view.reload)

        self._address_bar = QLineEdit()
        self._address_bar.returnPressed.connect(self._navigate_to_address_bar)

        main_toolbar = QHBoxLayout()
        main_toolbar.addWidget(self._back_button)
        main_toolbar.addWidget(self._forward_button)
        main_toolbar.addWidget(self._reload_button)
        main_toolbar.addWidget(self._address_bar, stretch=1)

        main_page = QWidget()
        main_layout = QVBoxLayout(main_page)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addLayout(main_toolbar)
        main_layout.addWidget(self._view, stretch=1)

        # The pop-up panel: not a stack of many simultaneous pop-ups --
        # opening a new one while one is already showing just replaces it
        # -- shown in place of the main page rather than as a second
        # canvas widget or OS window. self._popup_view is None until the
        # first pop-up actually opens; a *fresh* QWebEngineView/page is
        # created for every open (see _replace_popup_view) rather than
        # reusing one across opens -- confirmed directly that reusing the
        # same page as the target of a second, rapid newWindowRequested
        # redirect can hit an internal Chromium consistency assertion
        # during that page's later teardown (a real, reproducible crash
        # in this environment, not just a theoretical concern).
        self._popup_view: QWebEngineView | None = None
        self._popup_url_label = QLabel()
        self._popup_url_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        close_popup_button = QPushButton("✕ Close pop-up")
        close_popup_button.clicked.connect(self._close_popup)

        popup_toolbar = QHBoxLayout()
        popup_toolbar.addWidget(self._popup_url_label, stretch=1)
        popup_toolbar.addWidget(close_popup_button)

        self._popup_page = QWidget()
        self._popup_layout = QVBoxLayout(self._popup_page)
        self._popup_layout.setContentsMargins(0, 0, 0, 0)
        self._popup_layout.setSpacing(0)
        self._popup_layout.addLayout(popup_toolbar)
        # The pop-up view itself is inserted/removed by
        # _replace_popup_view/_close_popup, always at index 1 (after the
        # toolbar layout above, which stays at index 0).

        self._stack = QStackedWidget()
        self._stack.addWidget(main_page)
        self._stack.addWidget(self._popup_page)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._stack)

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

    def _on_new_window_requested(self, request: QWebEngineNewWindowRequest) -> None:
        """Redirects a page's request for a new browsing context --
        `window.open()`, `target="_blank"`, a modifier-click on a link,
        etc., regardless of `request.destination()` -- into this widget's
        own embedded pop-up view instead of leaving Qt WebEngine to
        create a genuinely separate, unmanaged top-level OS window (its
        default behavior when nothing connects to `newWindowRequested`
        at all, which is what TODO `e35bcf0` reported). Same pattern
        Qt's own `simplebrowser` example uses to open a new tab in
        -process rather than a new window."""
        self._replace_popup_view()
        request.openIn(self._popup_view.page())
        self._stack.setCurrentIndex(POPUP_PAGE_INDEX)

    def _replace_popup_view(self) -> None:
        """Tears down any existing pop-up view/page and creates a fresh
        one -- a new `QWebEnginePage` is the actual target of every
        `openIn()` redirect, never a reused one (see the pop-up-panel
        setup comment in `__init__` for why)."""
        if self._popup_view is not None:
            self._popup_layout.removeWidget(self._popup_view)
            self._popup_view.deleteLater()
        self._popup_view = QWebEngineView()
        self._popup_view.urlChanged.connect(self._on_popup_url_changed)
        self._popup_view.page().windowCloseRequested.connect(self._close_popup)
        self._popup_layout.insertWidget(1, self._popup_view, stretch=1)

    def _on_popup_url_changed(self, url: QUrl) -> None:
        self._popup_url_label.setText(url.toString())

    def _close_popup(self) -> None:
        self._stack.setCurrentIndex(MAIN_PAGE_INDEX)
        if self._popup_view is not None:
            self._popup_layout.removeWidget(self._popup_view)
            self._popup_view.deleteLater()
            self._popup_view = None
            self._popup_url_label.clear()


def build() -> QWidget:
    return BrowserWidget()
