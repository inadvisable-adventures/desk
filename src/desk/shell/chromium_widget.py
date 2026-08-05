import logging
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from PyQt6 import sip
from PyQt6.QtCore import QUrl, pyqtSignal
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEngineScript, QWebEnginePage
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

    # TODO d4d6c71: an "error"-level message here is either an explicit
    # console.error() call *or* an uncaught JS exception/unhandled
    # promise rejection -- QtWebEngine (like a real devtools console)
    # surfaces both through this same callback at ErrorMessageLevel, so
    # this one signal covers everything the titlebar error indicator
    # needs without any separate window.onerror/unhandledrejection
    # listener injected into the page itself.
    error_logged = pyqtSignal(str)

    def __init__(self, profile: QWebEngineProfile, parent=None) -> None:
        super().__init__(profile, parent)
        self.console_log: deque[ConsoleLogEntry] = deque(maxlen=CONSOLE_LOG_MAX_ENTRIES)

    def javaScriptConsoleMessage(self, level, message, line_number, source_id) -> None:
        level_name = _LEVEL_NAMES.get(level, "info")
        self.console_log.append(
            ConsoleLogEntry(
                level=level_name,
                message=message or "",
                line=line_number,
                source=source_id or "",
            )
        )
        if level_name == "error":
            self.error_logged.emit(message or "")


class ChromiumWidget(QWebEngineView):
    """The generic building block for hosting a hot-loaded SPA on the
    Workspace Canvas: a QWebEngineView pointed at one widget's URL, which
    reloads itself when the Local Web Server's file watcher reports that
    widget's source changed. See design-docs/architecture.md#widget-model.

    Also injects the Desk Bridge API's client library (window.desk.*) --
    see plans/desk-bridge-api.md -- before any of the page's own scripts
    run, so it's always available.

    TODO a5f66cc: uses its own persistent QWebEngineProfile (storage
    under profile_dir), not Qt's shared default profile -- every
    kind:"html" widget instance previously shared one profile/cookie
    jar, which would have made the per-launch auth-token cookie
    (below) leak across every widget instance on the origin (cookies
    are scoped by host+path, not port -- RFC 6265 -- and every
    kind:"html" widget already shares one origin). Per-instance
    profiles also extend this class's own "isolation from each other"
    claim (see architecture.md) down to storage/cookies/cache, not
    just the renderer process. Not shared with widgets/browser
    /widget.py's BrowserWidget, which is a separate class using its
    own plain QWebEngineView with Qt's default profile -- real,
    persisted browsing (logins, cookies) is exactly what that widget
    wants, unaffected by this."""

    # TODO d4d6c71: one signal covering both directions -- (True, message)
    # when the page logs an error, (False, "") on reload (a fresh page
    # load starts fresh, same "reload clears stale-style state"
    # convention the [STALE] indicator already uses) -- so
    # DeskWindow._bind_error_indicator only needs one
    # `connect(frame.set_error)` whose (bool, str) signature already
    # matches WidgetFrame.set_error's own positionally.
    error_state_changed = pyqtSignal(bool, str)

    def __init__(
        self,
        widget_id: str,
        instance_id: str,
        url: str,
        token: str,
        broker: HotReloadBroker,
        profile_dir: Path,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.widget_id = widget_id
        self.instance_id = instance_id

        # A named (non-off-the-record) profile persists to disk, but
        # only under the path setPersistentStoragePath/setCachePath
        # explicitly point at below -- otherwise Qt derives one from
        # the storage name under the OS's own app-data directory,
        # which wouldn't travel with the project.
        #
        # Deliberately NOT parented to self (Qt's usual "child gets
        # destroyed with its parent" mechanism would apply here too,
        # but with no ordering guarantee relative to _logging_page --
        # also a child of self): confirmed directly, a real segfault,
        # that QWebEngineProfile must outlive every QWebEnginePage
        # using it, and Qt's own QObject child-destruction order
        # between two siblings isn't something to rely on for that.
        # self.destroyed only fires once ~QObject() has already torn
        # down every child (including _logging_page), so deferring the
        # profile's own deleteLater() to that signal -- via a closure
        # holding the only strong reference, not self._profile, since
        # self's own attributes may already be gone by then -- is what
        # actually guarantees the required ordering.
        # Without the destroyed-signal deferral above, real teardown
        # (construct, navigate, then delete) segfaulted -- confirmed
        # directly, this fixes that. A separate QtWebEngine console
        # warning ("Release of profile requested but WebEnginePage
        # still not deleted") can still print during teardown in a
        # headless test harness specifically -- that one turned out to
        # be a different issue (a synthetic processEvents() pump loop
        # not draining DeferredDelete events, not this class's own
        # destruction ordering; see LEARNINGS.md's TODO a5f66cc entry
        # and tests/verify/verify_kind_html_auth_token_and_profile
        # _isolation.py's own pump() helper) -- fixed at the test-harness
        # level, not by anything here.
        profile = QWebEngineProfile(f"widget-{instance_id}")
        profile.setPersistentStoragePath(str(profile_dir / "storage"))
        profile.setCachePath(str(profile_dir / "cache"))
        self._profile = profile
        # sip.isdeleted() guard: confirmed directly (a real, if
        # infrequent, RuntimeError -- "wrapped C/C++ object of type
        # QWebEngineProfile has been deleted" -- escaping this lambda
        # otherwise) that the underlying C++ profile can already be
        # gone by the time this fires, e.g. during interpreter
        # shutdown, when Python's own module/global teardown can
        # release the last reference to `profile` out from under this
        # closure in an order Qt's own object-tree destruction doesn't
        # control. An uncaught exception escaping a Qt-signal-invoked
        # slot can crash the whole process, not just raise (see
        # LEARNINGS.md) -- guarded here instead of relying on this
        # never happening.
        self.destroyed.connect(lambda: None if sip.isdeleted(profile) else profile.deleteLater())

        self._logging_page = _LoggingWebEnginePage(profile, self)
        self.setPage(self._logging_page)
        self._logging_page.error_logged.connect(self._on_console_error)

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

    def _on_console_error(self, message: str) -> None:
        self.error_state_changed.emit(True, message)

    def reload(self) -> None:
        """Overridden (not just called) so both existing reload paths --
        the hot-reload broker (_on_widget_changed) and the [STALE]
        button's "Reload Now" (DeskWindow._on_widget_stale_clicked,
        which calls frame.content.reload() directly) -- clear this
        instance's error indicator for free (TODO d4d6c71): a freshly
        (re)loaded page hasn't had a chance to log anything yet."""
        self.error_state_changed.emit(False, "")
        super().reload()

    def get_console_log(self) -> list[ConsoleLogEntry]:
        """A snapshot (not a live view) of this page's captured console
        output, oldest first -- used by the introspect Bridge capability
        (TODO 9767c1a)."""
        return list(self._logging_page.console_log)
