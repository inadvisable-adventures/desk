import importlib.util
import logging
import sys
from pathlib import Path
from types import ModuleType

from PyQt6.QtCore import Qt
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
