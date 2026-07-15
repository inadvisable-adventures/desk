import logging
from collections import deque
from dataclasses import dataclass

from PyQt6.QtCore import QUrl
from PyQt6.QtWebEngineCore import QWebEngineScript, QWebEnginePage
from PyQt6.QtWebEngineWidgets import QWebEngineView

from desk.hotreload import HotReloadBroker
from desk.server.bridge_client import render_bridge_client

logger = logging.getLogger("desk.shell.chromium_widget")

# Bounded so a chatty page's console output can't grow this without
# limit -- every kind:"html" widget carries one of these unconditionally
# (TODO 9767c1a's introspect capability queries it on demand), so the
# per-widget cost needs to stay small and fixed regardless of whether
# anyone ever actually asks for it.
CONSOLE_LOG_MAX_ENTRIES = 200

_LEVEL_NAMES = {
    QWebEnginePage.JavaScriptConsoleMessageLevel.InfoMessageLevel: "info",
    QWebEnginePage.JavaScriptConsoleMessageLevel.WarningMessageLevel: "warning",
    QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel: "error",
}


@dataclass
class ConsoleLogEntry:
    level: str
    message: str
    line: int
    source: str


class _LoggingWebEnginePage(QWebEnginePage):
    """A `QWebEnginePage` that captures its own `console.log`/`warn`/
    `error` output into a bounded rolling buffer (TODO 9767c1a) --
    `javaScriptConsoleMessage` is a virtual method to override, not a
    Qt signal, so this subclass is the only way to observe it at all."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.console_log: deque[ConsoleLogEntry] = deque(maxlen=CONSOLE_LOG_MAX_ENTRIES)

    def javaScriptConsoleMessage(self, level, message, line_number, source_id) -> None:
        self.console_log.append(
            ConsoleLogEntry(
                level=_LEVEL_NAMES.get(level, "info"),
                message=message or "",
                line=line_number,
                source=source_id or "",
            )
        )


class ChromiumWidget(QWebEngineView):
    """The generic building block for hosting a hot-loaded SPA on the
    Workspace Canvas: a QWebEngineView pointed at one widget's URL, which
    reloads itself when the Local Web Server's file watcher reports that
    widget's source changed. See design-docs/architecture.md#widget-model.

    Also injects the Desk Bridge API's client library (window.desk.*) --
    see plans/desk-bridge-api.md -- before any of the page's own scripts
    run, so it's always available."""

    def __init__(
        self,
        widget_id: str,
        instance_id: str,
        url: str,
        token: str,
        broker: HotReloadBroker,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.widget_id = widget_id
        self.instance_id = instance_id

        self._logging_page = _LoggingWebEnginePage(self)
        self.setPage(self._logging_page)

        script = QWebEngineScript()
        script.setName(f"desk-bridge-client-{widget_id}")
        script.setSourceCode(render_bridge_client(widget_id, instance_id, token))
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

    def get_console_log(self) -> list[ConsoleLogEntry]:
        """A snapshot (not a live view) of this page's captured console
        output, oldest first -- used by the introspect Bridge capability
        (TODO 9767c1a)."""
        return list(self._logging_page.console_log)
