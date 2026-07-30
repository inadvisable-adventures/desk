import importlib.util
import logging
import sys
import traceback
from pathlib import Path
from types import ModuleType

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from desk.hotreload import HotReloadBroker

logger = logging.getLogger("desk.shell.python_widget")


def _load_widget_module(widget_id: str, widget_path: Path, entry: str) -> ModuleType:
    module_path = widget_path / entry
    spec = importlib.util.spec_from_file_location(f"desk_widget_{widget_id}", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load widget module at {module_path}")
    module = importlib.util.module_from_spec(spec)

    # Loading writes a __pycache__/*.pyc into the widget's own directory by
    # default, which the WidgetWatcher then sees as a source change and
    # spuriously triggers a rebuild. Suppress that for this exec only.
    previous_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous_dont_write_bytecode

    return module


class PythonWidgetHost(QWidget):
    """The default building block for a widget: hosts the QWidget returned
    by a widget's own widget.py:build(), loaded directly in-process — no
    local server, no HTTP, no browser. On hot reload, re-imports the
    module fresh (no caching) and swaps in a newly-built widget. See
    design-docs/architecture.md#widget-model."""

    # TODO d4d6c71: (True, traceback text) when _rebuild's own try/except
    # below catches a failed build() (already caught, just not previously
    # surfaced anywhere but the log); (False, "") on a subsequent
    # successful rebuild. Drives the titlebar [ERROR] indicator -- see
    # DeskWindow._bind_error_indicator. Deliberately does NOT attempt to
    # cover a runtime exception from this widget's own code after a
    # successful build (e.g. a button's click handler) -- confirmed
    # directly that any such exception is intercepted by PyQt6 at the
    # point it escapes a Python slot/virtual-method override (calling
    # sys.excepthook and aborting the process, see LEARNINGS.md's
    # "uncaught Python exception escaping a Qt-signal-invoked slot" entry)
    # before it could ever reach any single centralized handler here,
    # regardless of mechanism -- there is no live WidgetFrame left to show
    # an indicator on by that point anyway.
    build_error_changed = pyqtSignal(bool, str)

    def __init__(
        self,
        widget_id: str,
        widget_path: Path,
        entry: str,
        broker: HotReloadBroker,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.widget_id = widget_id
        self.widget_path = widget_path
        self.entry = entry
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._current: QWidget | None = None
        # Mirrors ChromiumWidget's own error-state tracking shape: ""
        # means no error, else the traceback text of the last failed
        # build. Checked immediately after binding by
        # DeskWindow._bind_error_indicator -- this can already be
        # non-empty by the time that binding happens, since _rebuild
        # below runs synchronously during this very __init__, before any
        # WidgetFrame wrapping this host even exists yet to bind to.
        self.build_error: str = ""

        self._rebuild()
        broker.widget_changed.connect(self._on_widget_changed)

    def _rebuild(self) -> None:
        # A broken rebuild must never propagate out of here: this runs
        # inside a Qt slot (_on_widget_changed, connected to the Hot
        # Reload Broker's signal), and an uncaught exception there is
        # fatal to the whole process in this PyQt6 setup -- confirmed via
        # a real crash, not theoretical. Since this app's own core
        # purpose is running `claude` to edit Desk's own widget code
        # live, a transient broken intermediate save is routine, not a
        # rare edge case. See plans/isolate-hot-reload-crash.md.
        try:
            module = _load_widget_module(self.widget_id, self.widget_path, self.entry)
            widget = module.build()
        except Exception:
            logger.error(
                "Failed to rebuild widget %s; keeping the previous version in place",
                self.widget_id,
                exc_info=True,
            )
            self.build_error = traceback.format_exc()
            self.build_error_changed.emit(True, self.build_error)
            if self._current is None:
                # No previous version to fall back to (this was the
                # first build) -- show something rather than an entirely
                # blank widget with no indication anything went wrong.
                self._current = self._build_error_placeholder()
                self._layout.addWidget(self._current)
            return

        if self._current is not None:
            self._layout.removeWidget(self._current)
            self._current.deleteLater()
        self._layout.addWidget(widget)
        self._current = widget
        self.build_error = ""
        self.build_error_changed.emit(False, "")

    @property
    def current(self) -> QWidget | None:
        """The widget instance currently hosted (whatever the last
        successful `build()` returned) -- exposed so callers that place a
        widget programmatically (e.g. `DeskWindow.open_widget_content`)
        can immediately configure the real content, not just its host."""
        return self._current

    @staticmethod
    def _build_error_placeholder() -> QWidget:
        label = QLabel("Failed to build this widget — check the log for details.")
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        return label

    def _on_widget_changed(self, changed_widget_id: str) -> None:
        if changed_widget_id == self.widget_id:
            logger.info("Rebuilding widget %s", self.widget_id)
            self._rebuild()
