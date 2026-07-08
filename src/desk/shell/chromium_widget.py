import logging

from PyQt6.QtCore import QUrl
from PyQt6.QtWebEngineCore import QWebEngineScript
from PyQt6.QtWebEngineWidgets import QWebEngineView

from desk.hotreload import HotReloadBroker
from desk.server.bridge_client import render_bridge_client

logger = logging.getLogger("desk.shell.chromium_widget")


class ChromiumWidget(QWebEngineView):
    """The generic building block for hosting a hot-loaded SPA on the
    Workspace Canvas: a QWebEngineView pointed at one widget's URL, which
    reloads itself when the Local Web Server's file watcher reports that
    widget's source changed. See design-docs/architecture.md#widget-model.

    Also injects the Desk Bridge API's client library (window.desk.*) --
    see plans/desk-bridge-api.md -- before any of the page's own scripts
    run, so it's always available."""

    def __init__(
        self, widget_id: str, url: str, token: str, broker: HotReloadBroker, parent=None
    ) -> None:
        super().__init__(parent)
        self.widget_id = widget_id

        script = QWebEngineScript()
        script.setName(f"desk-bridge-client-{widget_id}")
        script.setSourceCode(render_bridge_client(widget_id, token))
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        script.setRunsOnSubFrames(False)
        self.page().scripts().insert(script)

        self.load(QUrl(url))
        broker.widget_changed.connect(self._on_widget_changed)

    def _on_widget_changed(self, changed_widget_id: str) -> None:
        if changed_widget_id == self.widget_id:
            logger.info("Reloading widget %s", self.widget_id)
            self.reload()
