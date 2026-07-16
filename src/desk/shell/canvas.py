import math
from pathlib import Path

from PyQt6.QtCore import QEvent, QPointF, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QGraphicsProxyWidget,
    QGraphicsScene,
    QGraphicsView,
    QWidget,
)

from desk.shell.desk_picker import DeskPicker
from desk.shell.qt_utils import deferred
from desk.shell.temp_ui_notifications import TempUiNotificationStack
from desk.shell.widget_frame import (
    MIN_HEIGHT,
    MIN_WIDTH,
    WidgetFrame,
    _BringToFrontButton,
    _CloseButton,
    _EyeButton,
    _LockButton,
    _ResizeHandle,
    _SendToBackButton,
    _StaleIndicatorButton,
    _TempuiPromoteButton,
    _TitleBar,
    _UnlockButton,
)
from desk.shell.widget_spawn_menu import WidgetSpawnMenu
from desk.shell.zoom_control import ZoomControl
from desk.widgets import WidgetInfo

MIN_SCALE = 0.1
MAX_SCALE = 4.0
DEFAULT_WIDGET_SIZE = (680, 520)
WHEEL_ZOOM_SENSITIVITY = 0.0025
FIT_MARGIN_FRACTION = 0.001  # 0.1%, per design-docs/widget-ux.md
WIDGET_ZOOM_MARGIN_FRACTION = 0.2  # 20%, per TODO 33d3e8d -- see zoom_to_widget
ZOOM_CONTROL_MARGIN = 12
DESK_PICKER_MARGIN = 12
TEMP_UI_NOTIFICATIONS_MARGIN = 12
SCALE_EPSILON = 1e-6

# Chrome buttons handled as an ordinary click (press-then-release-on
# -the-same-button), not a drag -- see _hit_test_chrome/mousePressEvent/
# mouseReleaseEvent (TODO cdf45cb generalized this from just "close").
# "greeked" (TODO 33d3e8d) is a click-anywhere-on-the-frame variant of the
# same shape, not tied to one specific chrome sub-widget -- see
# _hit_test_chrome's greeked short-circuit.
_BUTTON_KINDS = {
    "close",
    "bring_to_front",
    "send_to_back",
    "lock",
    "unlock",
    "tempui_promote",
    "stale",
    "eye",
    "greeked",
}

# Max total mouse displacement (view-space px) between a titlebar press
# and its release still counted as a click (TODO a1c701d), not a drag.
TITLEBAR_CLICK_THRESHOLD = 4

# A large, fixed bound for the "infinite" canvas. Without this,
# QGraphicsView derives its scene rect from the current items' bounding
# box, which clamps centerOn() to wherever widgets currently are —
# breaking Desk pan-state restoration for any point not near that box.
CANVAS_BOUNDS = 100_000


class WorkspaceView(QGraphicsView):
    """The native Workspace Canvas: a pannable/zoomable Qt surface hosting
    widgets as QGraphicsProxyWidget items. Replaces the previous
    browser-based Workspace SPA — see design-docs/architecture.md.

    Widget chrome stays a constant on-screen size regardless of zoom (see
    WidgetFrame.set_view_scale); only widget content zooms/pans with the
    view. See design-docs/widget-ux.md."""

    widget_add_requested = pyqtSignal(str, QPointF)  # widget_id, scene pos
    widget_close_requested = pyqtSignal(WidgetFrame)
    files_dropped = pyqtSignal(list, QPointF)  # list[Path], scene pos
    paste_requested = pyqtSignal(QPointF)  # scene pos of the click that opened the menu
    tempui_promote_requested = pyqtSignal(WidgetFrame)  # TODO 91b3f42
    widget_stale_clicked = pyqtSignal(WidgetFrame)  # TODO 3e2c4f2

    def __init__(self, parent=None) -> None:
        super().__init__(QGraphicsScene(parent), parent)
        self.setSceneRect(-CANVAS_BOUNDS, -CANVAS_BOUNDS, 2 * CANVAS_BOUNDS, 2 * CANVAS_BOUNDS)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setAcceptDrops(True)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._scale = 1.0
        self._frames: list[WidgetFrame] = []
        self._widget_catalog: dict[str, WidgetInfo] = {}

        self._drag_frame: WidgetFrame | None = None
        self._drag_edge: str | None = None
        self._drag_last_pos: QPointF | None = None
        # Which chrome button ("close", "bring_to_front", "send_to_back")
        # was pressed and on which frame -- a press-then-release-on-the
        # -same-button click, generalized from what was previously just
        # "the" close button (see _hit_test_chrome/mousePressEvent/
        # mouseReleaseEvent below).
        self._button_press: tuple[WidgetFrame, str] | None = None
        self._forwarding_wheel = False
        # A titlebar press is always tracked here (TODO a1c701d),
        # separately from _drag_frame -- so a locked widget's titlebar
        # (TODO 8d05920, which skips setting _drag_frame) still supports
        # click-to-focus even though it never drags.
        self._titlebar_click_frame: WidgetFrame | None = None
        self._titlebar_click_pos: QPointF | None = None

        # Not QApplication.focusChanged: confirmed directly that it
        # reports the QGraphicsView itself (not the embedded widget) for
        # any QGraphicsProxyWidget-embedded content, since the proxy is
        # the one real top-level-focusable native widget as far as
        # QApplication's own focus tracking is concerned. QGraphicsScene
        # .focusItemChanged is the right level: it reports exactly the
        # QGraphicsProxyWidget whose *embedded* hierarchy now holds
        # focus, and that widget's own .focusWidget() (a QWidget method,
        # not QApplication's) correctly returns the specific focused
        # descendant within it. See LEARNINGS.md and TODO 397770c.
        self.scene().focusItemChanged.connect(self._on_scene_focus_item_changed)

        self.zoom_control = ZoomControl(self.viewport())
        self.zoom_control.fit_requested.connect(self.zoom_to_fit)
        self.zoom_control.reset_requested.connect(self.reset_zoom)
        self.zoom_control.zoom_changed.connect(self._apply_zoom_centered)
        self.zoom_control.hide()
        self._position_zoom_control()

        self.desk_picker = DeskPicker(self.viewport())
        self._position_desk_picker()

        self.temp_ui_notifications = TempUiNotificationStack(self.viewport())
        self._position_temp_ui_notifications()

    def add_widget(
        self,
        content: QWidget,
        title: str,
        pos: tuple[float, float] = (0, 0),
        size: tuple[int, int] | None = None,
        instance_id: str | None = None,
    ) -> QGraphicsProxyWidget:
        """Wraps content in the common widget chrome (see
        design-docs/widget-ux.md) and places it on the canvas."""
        frame = WidgetFrame(title, content, instance_id=instance_id)
        frame.resize(*(size or DEFAULT_WIDGET_SIZE))
        frame.set_view_scale(self._scale)
        proxy = self.scene().addWidget(frame)
        proxy.setPos(*pos)
        self._frames.append(frame)
        return proxy

    def set_widget_catalog(self, catalog: dict[str, WidgetInfo]) -> None:
        """Registers the discovered widget types offered by the right-click
        add-widget menu (see contextMenuEvent). The view otherwise has no
        reason to know about the wider widget catalog — this is the only
        piece of that knowledge it needs. See design-docs/widget-ux.md."""
        self._widget_catalog = catalog

    def contextMenuEvent(self, event) -> None:
        # TODO 3846190: a right-click landing on a placed widget's own
        # content (not chrome -- a right-click on a titlebar/button has
        # no sensible "widget's own context menu" meaning) goes to the
        # widget itself (e.g. a QTextEdit's copy/paste menu, a
        # QWebEngineView's browser menu) via Qt's normal scene delivery,
        # instead of this always showing Desk's own add-widget menu on
        # top of it regardless of what's under the cursor.
        if self._hit_test_chrome(QPointF(event.pos())) is None and self._frame_at(QPointF(event.pos())) is not None:
            super().contextMenuEvent(event)
            return
        scene_pos = self.mapToScene(event.pos())
        # Excludes tempui-DSL-defined custom widgets (TODO 91b3f42,
        # WidgetInfo.tempui_only) -- those can only ever be placed via
        # tempui, never this menu. Filtered here (the one place this
        # menu is constructed), not inside WidgetSpawnMenu itself, so
        # the "who's allowed to see this" decision stays in one place.
        spawnable_catalog = {
            widget_id: info for widget_id, info in self._widget_catalog.items() if not info.tempui_only
        }
        menu = WidgetSpawnMenu(spawnable_catalog, self)
        # Deferred (TODO 8c9436b): WidgetSpawnMenu, like _DeskListPopup,
        # is a WA_DeleteOnClose QAbstractItemView (QTreeWidget)-based
        # popup that closes itself right before emitting -- the same
        # vulnerable shape, even though neither handler shows a modal
        # dialog today. See qt_utils.deferred and LEARNINGS.md.
        menu.widget_chosen.connect(
            deferred(lambda widget_id: self.widget_add_requested.emit(widget_id, scene_pos))
        )
        menu.paste_requested.connect(deferred(lambda: self.paste_requested.emit(scene_pos)))
        menu.move(event.globalPos())
        menu.show()

    @staticmethod
    def _local_file_urls(mime_data) -> list:
        return [url for url in mime_data.urls() if url.isLocalFile()]

    def dragEnterEvent(self, event) -> None:
        if self._local_file_urls(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if self._local_file_urls(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        urls = self._local_file_urls(event.mimeData())
        if not urls:
            super().dropEvent(event)
            return
        paths = [Path(url.toLocalFile()) for url in urls]
        scene_pos = self.mapToScene(event.position().toPoint())
        event.acceptProposedAction()
        self.files_dropped.emit(paths, scene_pos)

    def clear_widgets(self) -> None:
        """Removes every placed widget from the canvas (used when switching
        to a different Desk — see desk.shell.window.DeskWindow)."""
        for frame in self._frames:
            proxy = frame.graphicsProxyWidget()
            if proxy is not None:
                self.scene().removeItem(proxy)
        self._frames = []

    def remove_widget(self, frame: WidgetFrame) -> None:
        """Removes a single widget from the canvas (used by the close
        button — see desk.shell.window.DeskWindow). Unlike clear_widgets,
        explicitly deleteLater()s the frame: a widget like the Console
        widget depends on its destroyed signal actually firing to clean up
        its PTY/subprocess (see LEARNINGS.md), which needs a real
        deleteLater() in a running event loop."""
        proxy = frame.graphicsProxyWidget()
        if proxy is not None:
            self.scene().removeItem(proxy)
        if frame in self._frames:
            self._frames.remove(frame)
        frame.deleteLater()

    def get_view_state(self) -> tuple[float, float, float]:
        """Returns (scene_x, scene_y, scale) for the point currently
        centered in the viewport, for Desk.pan_x/pan_y/scale."""
        center = self.mapToScene(self.viewport().rect().center())
        return center.x(), center.y(), self._scale

    def set_view_state(self, pan_x: float, pan_y: float, scale: float) -> None:
        self._rescale(scale)
        self.centerOn(QPointF(pan_x, pan_y))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_zoom_control()
        self._position_desk_picker()
        self._position_temp_ui_notifications()

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        """Panning (and, less obviously, zoom operations that re-center the
        view -- zoom_to_fit/reset_zoom) drift the Desk picker/zoom control
        away from their pinned corners (TODO 82d66c0) for a precise,
        confirmed reason: QAbstractScrollArea (which QGraphicsView is)
        implements fast scrolling via QWidget.scroll(dx, dy) on the
        viewport, and QWidget.scroll() also moves any child widget whose
        geometry lies fully inside the scrolled area by that same delta --
        the Desk picker/zoom control are exactly that, plain QWidget
        children of self.viewport(), not scene items. This is very likely
        the same actual mechanism behind TODO 4adfcad/TODO 1f9bd34's
        resize-time drift too (the very first resize already fires this
        with nonzero deltas, given the huge/infinite scene rect), though
        that fix (reassert via resizeEvent, deferred with
        QTimer.singleShot(0, ...) since a synchronous reassertion there was
        confirmed too early) is left as-is -- it's still independently
        needed since the zoom control's target position depends on the
        viewport's current width/height. Reasserting synchronously here
        (unlike resizeEvent) is confirmed to stick with no further drift --
        this callback *is* the mechanism doing the moving, not a step
        ahead of some later pass. See plans/fix-hover-ui-scroll-zoom-drift.md.

        Guarded with hasattr: QGraphicsView.__init__ itself can invoke
        scrollContentsBy during its own internal setup, before this
        subclass's __init__ has constructed desk_picker/zoom_control yet."""
        super().scrollContentsBy(dx, dy)
        if hasattr(self, "desk_picker"):
            self._position_desk_picker()
        if hasattr(self, "zoom_control"):
            self._position_zoom_control()
        if hasattr(self, "temp_ui_notifications"):
            self._position_temp_ui_notifications()

    def _position_desk_picker(self) -> None:
        """Reasserts the Desk picker's fixed top-left position -- a
        recurring internal Qt layout pass (plausibly QGraphicsView's own
        scrollbar/viewport geometry recalculation) silently displaces this
        manually-positioned, non-layout-managed child widget on every
        resize, including the first one at initial .show() (confirmed
        directly; see plans/fix-desk-picker-positioning.md). Deferred via
        singleShot(0) rather than reasserted synchronously inline:
        confirmed directly that Qt's own displacement happens as a
        *separate, later* queued layout pass within the same event-loop
        iteration, so a synchronous reassertion at the end of resizeEvent
        still gets overwritten afterward -- scheduling this to run after
        anything else queued during the same iteration is what actually
        sticks."""
        QTimer.singleShot(0, lambda: self.desk_picker.move(DESK_PICKER_MARGIN, DESK_PICKER_MARGIN))

    def _position_temp_ui_notifications(self) -> None:
        """Same reasoning/shape as _position_zoom_control (top-right
        anchor instead of bottom-right) -- also needs the scrollContentsBy
        treatment below, since it's the same kind of manually-positioned
        viewport child (see TODO 82d66c0)."""

        def _apply() -> None:
            hint = self.temp_ui_notifications.sizeHint()
            x = self.viewport().width() - hint.width() - TEMP_UI_NOTIFICATIONS_MARGIN
            self.temp_ui_notifications.move(max(0, x), TEMP_UI_NOTIFICATIONS_MARGIN)
            self.temp_ui_notifications.resize(hint)

        QTimer.singleShot(0, _apply)

    def notify_temp_ui(self, path, text: str, on_clicked) -> None:
        """Adds/replaces a temp-UI notification and immediately
        repositions the stack, since its size (and therefore its
        top-right-anchored x) changes with its content -- see
        desk.shell.temp_ui_notifications.TempUiNotificationStack.notify."""
        self.temp_ui_notifications.notify(path, text, on_clicked)
        self._position_temp_ui_notifications()

    def _position_zoom_control(self) -> None:
        """Deferred via singleShot(0), same reasoning and same confirmed
        bug as _position_desk_picker: the control starts hidden and only
        becomes visible later (the first time zoom leaves 1.0x), so its
        first real visible position isn't confirmed correct until that
        moment -- confirmed directly that it's stale then without this
        deferral, for the identical reason the Desk picker was. See
        plans/fix-zoom-control-positioning.md."""

        def _apply() -> None:
            hint = self.zoom_control.sizeHint()
            x = self.viewport().width() - hint.width() - ZOOM_CONTROL_MARGIN
            y = self.viewport().height() - hint.height() - ZOOM_CONTROL_MARGIN
            self.zoom_control.move(max(0, x), max(0, y))
            self.zoom_control.resize(hint)

        QTimer.singleShot(0, _apply)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            hit = self._hit_test_chrome(event.position())
            if hit is not None:
                frame, edge = hit
                if edge in _BUTTON_KINDS:
                    self._button_press = (frame, edge)
                    event.accept()
                    return
                if edge is None:
                    # Titlebar: always tracked as a click candidate
                    # (TODO a1c701d), independent of whether a drag
                    # also starts below -- a locked widget (TODO
                    # 8d05920) skips the drag but keeps click-to-focus.
                    self._titlebar_click_frame = frame
                    self._titlebar_click_pos = event.position()
                    if frame.locked:
                        event.accept()
                        return
                elif frame.locked:
                    # A resize-handle press on a locked widget (TODO
                    # 8d05920): swallow it, no resize.
                    event.accept()
                    return
                self._drag_frame, self._drag_edge = hit
                self._drag_last_pos = event.position()
                event.accept()
                return
            if self._frame_at(event.position()) is not None:
                # TODO 3846190: the press landed inside some placed
                # widget's own content (not chrome, not empty canvas).
                # Qt's own ScrollHandDrag fallback (see __init__) only
                # starts hand-panning the canvas when the scene doesn't
                # itself accept the press -- a "passive" widget that
                # never overrides mousePressEvent (a QLabel, a
                # paint-only view, empty background inside a nested
                # QGraphicsView, ...) leaves it unaccepted, which
                # otherwise bubbles all the way up to this view's own
                # hand-scroll start. Disabling drag mode for the
                # duration of just this one call prevents that decision
                # from ever engaging, while scene delivery to the
                # embedded widget still happens completely normally in
                # the same call -- confirmed directly (a real
                # press/move/release sequence no longer moves this
                # view's own scrollbars when it lands inside a widget's
                # bounds). Truly empty canvas (_frame_at returns None)
                # is untouched -- background drag-to-pan still works.
                self.setDragMode(QGraphicsView.DragMode.NoDrag)
                try:
                    super().mousePressEvent(event)
                finally:
                    self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_frame is not None:
            current = event.position()
            dx = (current.x() - self._drag_last_pos.x()) / self._scale
            dy = (current.y() - self._drag_last_pos.y()) / self._scale
            self._drag_last_pos = current
            proxy = self._drag_frame.graphicsProxyWidget()
            if proxy is not None:
                self._apply_drag(proxy, self._drag_edge, dx, dy)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._button_press is not None:
            frame, kind = self._button_press
            self._button_press = None
            hit = self._hit_test_chrome(event.position())
            if hit is not None and hit[0] is frame and hit[1] == kind:
                if kind == "close":
                    self.widget_close_requested.emit(frame)
                elif kind == "bring_to_front":
                    self.bring_to_front(frame)
                elif kind == "send_to_back":
                    self.send_to_back(frame)
                elif kind == "lock":
                    frame.set_locked(True)
                elif kind == "unlock":
                    frame.set_locked(False)
                elif kind == "tempui_promote":
                    self.tempui_promote_requested.emit(frame)
                elif kind == "stale":
                    self.widget_stale_clicked.emit(frame)
                elif kind in ("eye", "greeked"):
                    self.zoom_to_widget(frame)
            event.accept()
            return
        if self._drag_frame is not None:
            self._drag_frame = None
            self._drag_edge = None
            self._drag_last_pos = None
            event.accept()
        if self._titlebar_click_frame is not None:
            # TODO a1c701d: a titlebar press that ends with little-to-no
            # movement counts as a click (re-focuses the widget's last
            # -focused inner control), not a drag -- checked here rather
            # than in mouseMoveEvent so a drag that returns almost to its
            # start still counts as a drag, not a click.
            frame = self._titlebar_click_frame
            start = self._titlebar_click_pos
            self._titlebar_click_frame = None
            self._titlebar_click_pos = None
            if start is not None and (event.position() - start).manhattanLength() <= TITLEBAR_CLICK_THRESHOLD:
                frame.focus_last_widget()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _on_scene_focus_item_changed(self, new_item, old_item, _reason) -> None:
        """TODO 397770c: whenever scene-level focus moves, mark whichever
        WidgetFrame the newly-focused item is (and the previously
        -focused one, if different) as focused/unfocused, and remember
        the specific embedded widget that now has focus for TODO
        a1c701d's titlebar-click-to-focus. A focus change not involving
        any WidgetFrame at all (e.g. no item, or a chrome-only proxy)
        just leaves both frames as `None` -- harmless, no styling
        changes applied."""
        old_frame = self._frame_for_item(old_item)
        new_frame = self._frame_for_item(new_item)
        if old_frame is not None and old_frame is not new_frame:
            old_frame.set_focused(False)
        if new_frame is not None:
            new_frame.set_focused(True)
            focused_widget = new_frame.focusWidget()
            if focused_widget is not None:
                new_frame.remember_focused_widget(focused_widget)

    @staticmethod
    def _frame_for_item(item) -> WidgetFrame | None:
        if not isinstance(item, QGraphicsProxyWidget):
            return None
        widget = item.widget()
        return widget if isinstance(widget, WidgetFrame) else None

    def _hit_test_chrome(self, view_pos: QPointF) -> tuple[WidgetFrame, str | None] | None:
        """Determines whether a press at this viewport position landed on a
        widget's titlebar or a resize handle. Done here (not in the chrome
        widgets' own mouse events) deliberately — see
        design-docs/widget-ux.md."""
        item = self.itemAt(view_pos.toPoint())
        if not isinstance(item, QGraphicsProxyWidget):
            return None
        frame = item.widget()
        if not isinstance(frame, WidgetFrame):
            return None

        if frame.is_greeked:
            # TODO 33d3e8d: a greeked frame's titlebar/handles are
            # stacked away (see WidgetFrame's QStackedWidget) -- there's
            # nothing meaningful to walk into below, and any press
            # anywhere within the frame's bounds should be treated as a
            # click on the greeked placeholder itself.
            return frame, "greeked"

        scene_pos = self.mapToScene(view_pos.toPoint())
        local_point = (scene_pos - item.pos()).toPoint()
        child = frame.childAt(local_point)
        while child is not None and not isinstance(
            child,
            (
                _CloseButton,
                _BringToFrontButton,
                _SendToBackButton,
                _LockButton,
                _UnlockButton,
                _TempuiPromoteButton,
                _StaleIndicatorButton,
                _EyeButton,
                _TitleBar,
                _ResizeHandle,
            ),
        ):
            child = child.parentWidget()

        if isinstance(child, _CloseButton):
            return frame, "close"
        if isinstance(child, _BringToFrontButton):
            return frame, "bring_to_front"
        if isinstance(child, _SendToBackButton):
            return frame, "send_to_back"
        if isinstance(child, _LockButton):
            return frame, "lock"
        if isinstance(child, _UnlockButton):
            return frame, "unlock"
        if isinstance(child, _TempuiPromoteButton):
            return frame, "tempui_promote"
        if isinstance(child, _StaleIndicatorButton):
            return frame, "stale"
        if isinstance(child, _EyeButton):
            return frame, "eye"
        if isinstance(child, _TitleBar):
            return frame, None
        if isinstance(child, _ResizeHandle):
            return frame, child.edge
        return None

    def describe_widget_at_global_pos(self, global_pos) -> str | None:
        """A human-readable "identifying UI path" (TODO f2aede6) for
        whichever widget is at `global_pos` (real screen coordinates,
        e.g. from a QMouseEvent.globalPosition()) -- wired to
        `current_context.set_widget_path_resolver` by `DeskWindow`.

        Not `QApplication.widgetAt`: confirmed directly (see
        LEARNINGS.md) that it doesn't resolve into anything embedded
        via `QGraphicsProxyWidget` -- the same category of gotcha
        already documented for `QApplication.focusChanged`. Goes
        through the same `itemAt`/`childAt` shape `_hit_test_chrome`
        already uses, generalized to *any* widget, not just recognized
        chrome types; falls back to plain `childAt`/`parentWidget`
        walking for anything that isn't a scene item at all (the
        floating HUD chrome -- Desk picker, zoom control, ...)."""
        viewport_pos = self.viewport().mapFromGlobal(global_pos)
        if not self.viewport().rect().contains(viewport_pos):
            return None
        item = self.itemAt(viewport_pos)
        if isinstance(item, QGraphicsProxyWidget):
            frame = item.widget()
            if not isinstance(frame, WidgetFrame):
                return None
            scene_pos = self.mapToScene(viewport_pos)
            local_point = (scene_pos - item.pos()).toPoint()
            widget = frame.childAt(local_point) or frame
            return self._describe_widget_chain(widget, frame)
        # The floating HUD chrome (Desk picker, zoom control, ...) are
        # children of the viewport, not of the view itself -- childAt
        # must be called on the same widget viewport_pos is relative to.
        widget = self.viewport().childAt(viewport_pos)
        if widget is None:
            return None
        return self._describe_widget_chain(widget, self.viewport())

    @staticmethod
    def _describe_widget(widget: QWidget) -> str:
        cls = type(widget).__name__
        if isinstance(widget, WidgetFrame):
            return f'{cls}["{widget.title}"]'
        text_fn = getattr(widget, "text", None)
        if callable(text_fn):
            try:
                text = text_fn()
            except TypeError:
                text = None
            if text:
                return f'{cls}["{text}"]'
        return cls

    def _describe_widget_chain(self, widget: QWidget, stop_at: QWidget) -> str:
        parts = []
        current = widget
        while current is not None:
            parts.append(self._describe_widget(current))
            if current is stop_at:
                break
            current = current.parentWidget()
        parts.reverse()
        return " > ".join(parts)

    def bring_to_front(self, frame: WidgetFrame) -> None:
        proxy = frame.graphicsProxyWidget()
        if proxy is None:
            return
        max_z = max((z for z in self._frame_z_values()), default=0.0)
        proxy.setZValue(max_z + 1)

    def send_to_back(self, frame: WidgetFrame) -> None:
        proxy = frame.graphicsProxyWidget()
        if proxy is None:
            return
        min_z = min((z for z in self._frame_z_values()), default=0.0)
        proxy.setZValue(min_z - 1)

    def _frame_z_values(self):
        for other in self._frames:
            other_proxy = other.graphicsProxyWidget()
            if other_proxy is not None:
                yield other_proxy.zValue()

    @staticmethod
    def _apply_drag(proxy: QGraphicsProxyWidget, edge: str | None, dx: float, dy: float) -> None:
        if edge is None:
            proxy.moveBy(dx, dy)
            return
        size = proxy.size()
        width, height = size.width(), size.height()
        if edge == "right":
            proxy.resize(max(MIN_WIDTH, width + dx), height)
        elif edge == "bottom":
            proxy.resize(width, max(MIN_HEIGHT, height + dy))
        elif edge == "left":
            new_width = max(MIN_WIDTH, width - dx)
            proxy.resize(new_width, height)
            proxy.moveBy(width - new_width, 0)

    def wheelEvent(self, event) -> None:
        if self._frame_at(event.position()) is not None:
            # TODO 78bfa41: any placed widget under the cursor wins,
            # not just a scrollable one (TODO 3846190's original,
            # narrower _scrollable_at gate) -- explicit user decision,
            # trading away some canvas zoom/pan reachability in
            # exchange for a widget never having wheel-scroll stolen
            # out from under it. A widget that doesn't itself handle
            # wheel (most of them, today) simply does nothing with it,
            # same as any other unhandled event -- the canvas just
            # doesn't zoom either.
            if self._forwarding_wheel:
                # Re-entrant delivery: an embedded widget (a QWebEngineView,
                # or any QGraphicsProxyWidget-hosted widget that ignores the
                # event -- e.g. a scroll area already at its scroll limit)
                # bounces a wheel event it couldn't consume back up to its
                # parent chain, which reaches this handler again while
                # we're still inside the super().wheelEvent() call below.
                # Re-forwarding would recurse until the stack overflows;
                # zooming on a bounce-back would be wrong too -- so just
                # stop here. See TODO c44e88f.
                event.accept()
                return
            # Let Qt's normal scene-forwarding deliver the event to the
            # embedded widget so it can scroll its own content, instead of
            # this view treating it as a canvas zoom gesture -- see
            # plans/todo-widget-scrollable.md.
            #
            # TODO 86ba292: QGraphicsView.wheelEvent (the base class
            # implementation invoked below) falls back to panning *this
            # view's own* scrollbars -- i.e. panning the whole Desk canvas
            # -- whenever the scene doesn't consume the forwarded event.
            # That happens for any widget that ignores wheel input, which
            # includes every non-scrollable widget and any scroll area
            # already at the end of its scroll direction: exactly the
            # "events pass through" leak the user found (both by reading
            # back the Event Recorder's own recording, and independently
            # by scrolling a real scrollable widget past its limit).
            # `_forwarding_wheel`'s accept() alone doesn't stop it, since
            # the pan already happened synchronously inside the call below
            # -- so capture this view's own scrollbar positions first and
            # restore them afterward. A widget under the cursor owns this
            # event full stop (TODO 78bfa41): whatever the embedded widget
            # did or didn't do with it, the canvas itself must not move.
            # The embedded widget's own scrollbars (if any) are separate
            # objects, untouched by this.
            hbar, vbar = self.horizontalScrollBar(), self.verticalScrollBar()
            before_scroll = (hbar.value(), vbar.value())
            self._forwarding_wheel = True
            try:
                super().wheelEvent(event)
            finally:
                self._forwarding_wheel = False
            hbar.setValue(before_scroll[0])
            vbar.setValue(before_scroll[1])
            event.accept()
            return
        delta = event.pixelDelta().y()
        if delta == 0:
            delta = event.angleDelta().y() / 8
        factor = math.exp(delta * WHEEL_ZOOM_SENSITIVITY)
        self._apply_zoom(factor)

    def _frame_at(self, view_pos: QPointF) -> WidgetFrame | None:
        """The placed WidgetFrame (if any) whose bounds contain this
        viewport position -- true for *any* widget's own content, not
        just chrome (see _hit_test_chrome). Used to tell "over some
        widget's content" apart from "truly empty canvas" (TODO
        3846190), for the interactions that should never fall back to
        canvas-level pan/zoom just because the specific spot under the
        cursor doesn't itself consume the event -- as of TODO 78bfa41,
        that's every one of them (click-drag, right-click,
        wheel-scroll, pinch-zoom): a widget under the cursor always
        wins, full stop, not just a scrollable one."""
        item = self.itemAt(view_pos.toPoint())
        if not isinstance(item, QGraphicsProxyWidget):
            return None
        frame = item.widget()
        return frame if isinstance(frame, WidgetFrame) else None

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.NativeGesture:
            if event.gestureType() == Qt.NativeGestureType.ZoomNativeGesture:
                # TODO 78bfa41: any placed widget under the cursor wins
                # (same _frame_at gate wheelEvent/mousePressEvent/
                # contextMenuEvent all use) -- previously only a
                # scrollable/QWebEngineView widget (TODO 3846190),
                # deliberately kept consistent with wheel's own
                # then-existing behavior; broadened per explicit user
                # decision. No widget implements its own pinch handling
                # today, so this still just means "the canvas doesn't
                # steal it" for pinch specifically, not genuine
                # forwarding -- there's nothing to forward to yet.
                if self._frame_at(event.position()) is None:
                    self._apply_zoom(1.0 + event.value())
                return True
        return super().event(event)

    def zoom_to_fit(self) -> None:
        self._fit_rect(self.scene().itemsBoundingRect(), FIT_MARGIN_FRACTION)

    def zoom_to_widget(self, frame: WidgetFrame, margin_fraction: float = WIDGET_ZOOM_MARGIN_FRACTION) -> None:
        """TODO 33d3e8d: zoom/pan so this frame fills the viewport, with a
        margin_fraction margin on all sides -- triggered by either a
        click anywhere on a "greeked" frame or its titlebar's eye button
        (see _hit_test_chrome/mouseReleaseEvent)."""
        proxy = frame.graphicsProxyWidget()
        if proxy is None:
            return
        self._fit_rect(proxy.sceneBoundingRect(), margin_fraction)

    def _fit_rect(self, rect, margin_fraction: float) -> None:
        """Shared core of zoom_to_fit/zoom_to_widget: fits `rect` in the
        viewport with a margin of margin_fraction of its own width/height
        on each side, clamps the resulting scale to [MIN_SCALE, MAX_SCALE],
        and updates chrome/HUD for the new scale."""
        if rect.isEmpty():
            return
        margin_x = rect.width() * margin_fraction
        margin_y = rect.height() * margin_fraction
        rect = rect.adjusted(-margin_x, -margin_y, margin_x, margin_y)

        previous_anchor = self.transformationAnchor()
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        try:
            self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
            raw_scale = self.transform().m11()
            clamped_scale = max(MIN_SCALE, min(MAX_SCALE, raw_scale))
            if clamped_scale != raw_scale:
                correction = clamped_scale / raw_scale
                self.scale(correction, correction)
            self._scale = clamped_scale
        finally:
            self.setTransformationAnchor(previous_anchor)
        self._on_scale_changed()

    def reset_zoom(self) -> None:
        self._apply_zoom_centered(1.0)

    def _apply_zoom(self, factor: float) -> None:
        """Wheel/pinch: relative factor, anchored under the cursor."""
        self._rescale(self._scale * factor)

    def _apply_zoom_centered(self, target_scale: float) -> None:
        """HUD-triggered (slider/reset): absolute target, anchored at the
        view center rather than wherever the cursor happens to be over the
        HUD itself."""
        previous_anchor = self.transformationAnchor()
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        try:
            self._rescale(target_scale)
        finally:
            self.setTransformationAnchor(previous_anchor)

    def _rescale(self, target_scale: float) -> None:
        new_scale = max(MIN_SCALE, min(MAX_SCALE, target_scale))
        factor = new_scale / self._scale
        if factor != 1.0:
            self.scale(factor, factor)
            self._scale = new_scale
            self._on_scale_changed()

    def _on_scale_changed(self) -> None:
        for frame in self._frames:
            frame.set_view_scale(self._scale)
        self.zoom_control.set_zoom(self._scale)
        self.zoom_control.setVisible(abs(self._scale - 1.0) > SCALE_EPSILON)
