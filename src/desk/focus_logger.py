"""Focus logging inside Desk (TODO b4d99a1; plans/focus-logging-in-desk.md;
investigations/text-focus-stability.md).

A switchable, off-by-default recorder of everything focus-relevant that
happens on the canvas -- scene focus changes, focus moving between the
controls of one widget, the key and mouse input just before each change,
how close neighbouring frames are, z-order changes -- written as one-line
`kind key=value ...` entries to the named widget log `FOCUS_LOG_NAME`
(`desk.widget_logs`), so an agent can read it with `desk_query_widget_log`.

Everything is attached only while enabled (`enable()`/`disable()`): an
app-level event filter (it sees every event in the process, so it
quick-rejects by type) plus the scene's `focusItemChanged`. Other modules
report their own moments through the module-level `note()`, a no-op when
no logger is enabled.

Printable characters are never recorded -- the log is agent-readable --
only counted (`typing n=...`); non-printable keys are recorded by name.
"""

import json
import math
import re
import sys
import time
from collections import deque
from typing import Any

from PyQt6.QtCore import QEvent, QObject, QTimer, Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication, QGraphicsProxyWidget, QWidget

from desk.widget_logs import WidgetLogStore, now_ms

FOCUS_LOG_NAME = "desk-focus"
TYPING_FLUSH_MS = 500
MAX_STACK_FRAMES = 6
EVENT_RING = 24  # dispatched events remembered; the newest few distinct ones are logged as `ev=`
EVENTS_LOGGED = 4
PAINT_WINDOW_MS = 100  # a frame counts as `painted=` on a focus entry if it painted this recently

_BARE_VALUE = re.compile(r'[^\s="]+')
_FRAME_CLASS_NAME = "WidgetFrame"

# Frames from the library/stdlib/frozen code are noise; everything else (Desk, widgets,
# project widgets, scripts) can be the caller of a programmatic setFocus().
_SKIP_PATH_PARTS = ("site-packages", "/lib/python", "<frozen")

# Events that can *drive* the loop into changing focus; `ev=` lists only these (plus user-defined
# event types), because everything else (palette/font changes, paint, hover, ...) fires constantly and
# would bury them. Paint is tracked separately (`painted=`); focus events have their own entries.
_DRIVER_EVENTS = frozenset(
    getattr(QEvent.Type, name)
    for name in (
        "KeyPress", "KeyRelease", "ShortcutOverride", "Shortcut",
        "MouseButtonPress", "MouseButtonRelease", "MouseButtonDblClick", "Wheel",
        "TouchBegin", "TouchUpdate", "TouchEnd", "NativeGesture", "InputMethod",
        "GraphicsSceneMousePress", "GraphicsSceneMouseRelease", "GraphicsSceneMouseDoubleClick",
        "GraphicsSceneWheel", "Timer", "MetaCall", "DeferredDelete",
        "WindowActivate", "WindowDeactivate", "ActivationChange", "ApplicationActivate",
        "ApplicationDeactivate", "WindowStateChange", "WindowBlocked", "WindowUnblocked",
        "Show", "Hide", "ShowToParent", "HideToParent", "Close", "EnabledChange", "ParentChange",
        "ZOrderChange", "Resize", "Move",
    )
    if hasattr(QEvent.Type, name)
)
_USER_EVENT = int(QEvent.Type.User)

_active: "FocusLogger | None" = None

# (code object, line) of the Python frames beneath the Qt event loop, outermost first; see
# `_capture_loop_base`. Empty until captured, in which case nothing is stripped.
_loop_base: tuple[tuple[Any, int], ...] = ()


def note(kind: str, **fields: Any) -> None:
    """Records an entry from outside this module; free when logging is off."""
    logger = _active
    if logger is not None:
        logger.record(kind, **fields)


def _fmt(value: Any) -> str:
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float):
        return f"{value:.1f}"
    text = str(value)
    return text if _BARE_VALUE.fullmatch(text) else json.dumps(text)


def describe_widget(widget: QWidget | None) -> str:
    if widget is None:
        return "none"
    name = widget.objectName()
    return f"{type(widget).__name__}#{name}" if name else type(widget).__name__


def _is_frame(obj: object) -> bool:
    return any(cls.__name__ == _FRAME_CLASS_NAME for cls in type(obj).__mro__)


def _frame_of_widget(widget: QWidget | None) -> QWidget | None:
    current = widget
    while current is not None:
        if _is_frame(current):
            return current
        current = current.parentWidget()
    return None


def _frame_of_item(item: object) -> QWidget | None:
    if not isinstance(item, QGraphicsProxyWidget):
        return None
    widget = item.widget()
    return widget if _is_frame(widget) else None


def _receiver_name(obj: object) -> str:
    """Class of an event's receiver; a QTimer also names its parent, since the timer is just the
    messenger and the owner is what a reader wants."""
    try:
        name = type(obj).__name__
        if isinstance(obj, QTimer) and obj.parent() is not None:
            name += f"^{type(obj.parent()).__name__}"
        return name
    except RuntimeError:
        return "deleted"


def _frame_id(frame: QWidget | None) -> str:
    return frame.instance_id if frame is not None else "none"


def _python_stack() -> str:
    """Non-library Python frames above the focus slot, innermost first. A
    programmatic setFocus() shows its caller here (the focus signals are
    delivered synchronously); `native` means Qt itself caused the change."""
    frames = []
    try:
        frame = sys._getframe(2)
    except ValueError:  # a focus change with no Python frame beneath the slot (e.g. at teardown)
        frame = None
    while frame is not None:
        frames.append(frame)
        frame = frame.f_back
    # Outermost frames identical to the ones beneath the event loop are not a caller of anything.
    base = _loop_base
    keep = len(frames)
    while keep and len(frames) - keep < len(base):
        outer = frames[keep - 1]
        if (outer.f_code, outer.f_lineno) != base[len(frames) - keep]:
            break
        keep -= 1
    parts: list[str] = []
    for frame in frames[:keep]:
        path = frame.f_code.co_filename
        if not any(skip in path for skip in _SKIP_PATH_PARTS) and path.rsplit("/", 1)[-1] != "focus_logger.py":
            parts.append(f"{path.rsplit('/', 1)[-1]}:{frame.f_lineno}:{frame.f_code.co_name}")
            if len(parts) == MAX_STACK_FRAMES:
                break
    return "<".join(parts) if parts else "native"


def _key_name(event) -> str:
    try:
        return Qt.Key(event.key()).name
    except ValueError:
        return f"0x{event.key():x}"


def _modifier_names(event) -> str:
    mods = event.modifiers()
    names = [
        label
        for flag, label in (
            (Qt.KeyboardModifier.ControlModifier, "Ctrl"),
            (Qt.KeyboardModifier.ShiftModifier, "Shift"),
            (Qt.KeyboardModifier.AltModifier, "Alt"),
            (Qt.KeyboardModifier.MetaModifier, "Meta"),
        )
        if mods & flag
    ]
    return "+".join(names) if names else "none"


def _is_printable(event) -> bool:
    text = event.text()
    if not text or not text.isprintable():
        return False
    return not event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier)


class FocusLogger(QObject):
    """Owned by DeskWindow, reachable via `current_context.get_focus_logger()`.
    `view` is the WorkspaceView (duck-typed: `scene()`, `viewport()`, `itemAt`,
    `mapToScene`, `placed_frames()`, `chrome_at()`)."""

    def __init__(self, view, store: WidgetLogStore, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._view = view
        self._store = store
        self._enabled = False
        self._tag: str | None = None
        self._last_input_monotonic: float | None = None
        self._last_focus_widget = "none"
        self._events: deque = deque(maxlen=EVENT_RING)  # (monotonic, QEvent.Type, receiver)
        self._painted: dict[str, float] = {}  # frame id (or "canvas") -> monotonic of its last paint
        self._typing_count = 0
        self._typing_first_ms = 0
        self._typing_timer = QTimer(self)
        self._typing_timer.setSingleShot(True)
        self._typing_timer.setInterval(TYPING_FLUSH_MS)
        self._typing_timer.timeout.connect(self._flush_typing)

    # --- control -----------------------------------------------------

    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def tag(self) -> str | None:
        return self._tag

    def set_tag(self, tag: str | None) -> None:
        """Marks every following entry `rec=<tag>` (a recording id), so the
        log lines up with a timecoded transcript."""
        self._tag = tag

    def enable(self, tag: str | None = None) -> None:
        global _active
        if self._enabled:
            self._tag = tag if tag is not None else self._tag
            return
        self._enabled = True
        self._tag = tag
        _active = self
        self._events.clear()
        self._painted.clear()
        QTimer.singleShot(0, self._capture_loop_base)
        focus_frame = _frame_of_item(self._view.scene().focusItem())
        self._last_focus_widget = describe_widget(focus_frame.focusWidget() if focus_frame is not None else None)
        QApplication.instance().installEventFilter(self)
        self._view.scene().focusItemChanged.connect(self._on_focus_item_changed)
        app = QGuiApplication.instance()
        app.applicationStateChanged.connect(self._on_application_state_changed)
        app.focusWindowChanged.connect(self._on_focus_window_changed)
        self.record("session_start")

    def disable(self) -> None:
        global _active, _loop_base
        if not self._enabled:
            return
        self.record("session_stop")
        self._flush_typing()
        self._enabled = False
        if _active is self:
            _active = None
            _loop_base = ()
        self._events.clear()
        self._painted.clear()
        QApplication.instance().removeEventFilter(self)
        app = QGuiApplication.instance()
        for signal, slot in (
            (self._view.scene().focusItemChanged, self._on_focus_item_changed),
            (app.applicationStateChanged, self._on_application_state_changed),
            (app.focusWindowChanged, self._on_focus_window_changed),
        ):
            try:
                signal.disconnect(slot)
            except TypeError:
                pass
        self._tag = None

    # --- recording -----------------------------------------------------

    def record(self, kind: str, **fields: Any) -> None:
        if not self._enabled:
            return
        if kind != "typing":
            self._flush_typing()
        self._append(kind, fields, None)

    def _append(self, kind: str, fields: dict[str, Any], t: int | None) -> None:
        if self._tag is not None:
            fields = {**fields, "rec": self._tag}
        text = kind + "".join(f" {key}={_fmt(value)}" for key, value in fields.items())
        self._store.append(FOCUS_LOG_NAME, [(t, text)])

    def _flush_typing(self) -> None:
        if self._typing_count:
            count, first = self._typing_count, self._typing_first_ms
            self._typing_count = 0
            self._append("typing", {"n": count}, first)

    def _capture_loop_base(self) -> None:
        """Runs from the event loop, so its callers are exactly the Python frames beneath Qt
        dispatch (`main`, `<module>`): the part of every later `py=` stack that is not a caller."""
        global _loop_base
        if not self._enabled:
            return
        base = []
        frame = sys._getframe(1)
        while frame is not None:
            base.append((frame.f_code, frame.f_lineno))
            frame = frame.f_back
        _loop_base = tuple(reversed(base))

    def _since_input_ms(self) -> int | None:
        if self._last_input_monotonic is None:
            return None
        return int((time.monotonic() - self._last_input_monotonic) * 1000)

    # --- geometry --------------------------------------------------------

    def _neighbour_fields(self, frame: QWidget | None) -> dict[str, Any]:
        """`gap` (scene units to the nearest other frame, 0 when they
        intersect), `nbr` (its instance id), `overlap` (1 if intersecting)."""
        proxy = frame.graphicsProxyWidget() if frame is not None else None
        if proxy is None:
            return {}
        rect = proxy.sceneBoundingRect()
        best: tuple[float, str, bool] | None = None
        for other in self._view.placed_frames():
            if other is frame:
                continue
            other_proxy = other.graphicsProxyWidget()
            if other_proxy is None:
                continue
            other_rect = other_proxy.sceneBoundingRect()
            dx = max(0.0, other_rect.left() - rect.right(), rect.left() - other_rect.right())
            dy = max(0.0, other_rect.top() - rect.bottom(), rect.top() - other_rect.bottom())
            gap = math.hypot(dx, dy)
            if best is None or gap < best[0]:
                best = (gap, other.instance_id, rect.intersects(other_rect))
        if best is None:
            return {}
        return {"gap": best[0], "nbr": best[1], "overlap": best[2]}

    def _frames_at(self, scene_pos) -> str:
        """Instance ids of every frame containing the point, front to back."""
        hits = []
        for frame in self._view.placed_frames():
            proxy = frame.graphicsProxyWidget()
            if proxy is not None and proxy.sceneBoundingRect().contains(scene_pos):
                hits.append((proxy.zValue(), frame.instance_id))
        hits.sort(reverse=True)
        return ">".join(instance_id for _z, instance_id in hits) or "none"

    def _cause_fields(self) -> dict[str, Any]:
        """`ev` (the newest few distinct non-noise events dispatched before now, as
        `Type:Receiver:age_ms`) and `painted` (frames repainted within PAINT_WINDOW_MS, as
        `id:age_ms`): what the loop was doing just before a focus change, to tell a change Qt
        made on its own from one an input event or a neighbour's repaint led to."""
        now = time.monotonic()
        fields: dict[str, Any] = {}
        seen: list[str] = []
        for t, kind, obj in reversed(self._events):
            label = f"{getattr(kind, 'name', kind)}:{_receiver_name(obj)}"
            if seen and seen[-1].startswith(label + ":"):
                continue  # the same event propagating through several receivers
            seen.append(f"{label}:{int((now - t) * 1000)}")
            if len(seen) == EVENTS_LOGGED:
                break
        if seen:
            fields["ev"] = "<".join(seen)
        recent = sorted(
            (now - t, frame_id) for frame_id, t in self._painted.items() if (now - t) * 1000 <= PAINT_WINDOW_MS
        )
        if recent:
            fields["painted"] = ",".join(f"{frame_id}:{int(age * 1000)}" for age, frame_id in recent)
        return fields

    # --- Qt hooks --------------------------------------------------------

    def _on_focus_item_changed(self, new_item, old_item, reason) -> None:
        new_frame, old_frame = _frame_of_item(new_item), _frame_of_item(old_item)
        self.record(
            "focus_item",
            old=_frame_id(old_frame),
            new=_frame_id(new_frame),
            reason=reason.name,
            widget=describe_widget(new_frame.focusWidget()) if new_frame is not None else "none",
            since_input=self._since_input_ms(),
            py=_python_stack(),
            **self._neighbour_fields(new_frame),
            **self._cause_fields(),
        )
        reported = new_item
        QTimer.singleShot(0, lambda: self._check_settled(reported))

    def _check_settled(self, reported) -> None:
        """Scene focus is resolved after the triggering event (LEARNINGS), so
        compare where focus really ended up with what the signal reported."""
        if not self._enabled:
            return
        actual = self._view.scene().focusItem()
        if actual is not reported:
            self.record("focus_settled", reported=_frame_id(_frame_of_item(reported)), now=_frame_id(_frame_of_item(actual)))

    def _on_application_state_changed(self, state) -> None:
        self.record("app_state", state=state.name)

    def _on_focus_window_changed(self, window) -> None:
        self.record("focus_window", window=window.title() if window is not None else None)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 -- Qt override
        try:
            self._dispatch(obj, event)
        except RuntimeError:
            pass  # the view is being torn down; nothing left to observe
        return False

    def _dispatch(self, obj, event) -> None:
        kind = event.type()
        if kind == QEvent.Type.Paint:
            self._on_paint(obj)
            return
        if kind in _DRIVER_EVENTS or int(kind) >= _USER_EVENT:
            self._events.append((time.monotonic(), kind, obj))
        if kind in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
            self._on_widget_focus(obj, event, kind == QEvent.Type.FocusIn)
        elif obj is self._view:
            if kind == QEvent.Type.KeyPress:
                self._on_key_press(event)
            elif kind == QEvent.Type.InputMethod:
                self._last_input_monotonic = time.monotonic()
                self.record("ime")
        elif obj is self._view.viewport() and kind == QEvent.Type.MouseButtonPress:
            self._on_mouse_press(event)

    def _on_paint(self, obj) -> None:
        if not isinstance(obj, QWidget):
            return
        frame = _frame_of_widget(obj)
        if frame is not None:
            self._painted[_frame_id(frame)] = time.monotonic()
        elif obj is self._view or obj is self._view.viewport():
            self._painted["canvas"] = time.monotonic()

    def _on_widget_focus(self, obj, event, gained: bool) -> None:
        if not isinstance(obj, QWidget):
            return
        frame = _frame_of_widget(obj)
        if frame is None and obj is not self._view and obj is not self._view.viewport():
            return  # chrome-less widgets outside the canvas (dialogs, popups' own windows)
        described = describe_widget(obj)
        fields: dict[str, Any] = {
            "frame": _frame_id(frame) if frame is not None else "canvas",
            "widget": described,
            "reason": event.reason().name,
        }
        if gained:
            fields["from"] = self._last_focus_widget
            fields["py"] = _python_stack()
            fields.update(self._cause_fields())
        else:
            self._last_focus_widget = described  # the "from" of the next focus_in
        self.record("focus_in" if gained else "focus_out", **fields)

    def _on_key_press(self, event) -> None:
        self._last_input_monotonic = time.monotonic()
        if event.isAutoRepeat():
            return
        if _is_printable(event):
            if not self._typing_count:
                self._typing_first_ms = now_ms()
            self._typing_count += 1
            self._typing_timer.start()
            return
        self.record("key", key=_key_name(event), mods=_modifier_names(event))

    def _on_mouse_press(self, event) -> None:
        self._last_input_monotonic = time.monotonic()
        view_pos = event.position()
        scene_pos = self._view.mapToScene(view_pos.toPoint())
        chrome = self._view.chrome_at(view_pos)
        item = self._view.itemAt(view_pos.toPoint())
        frame = _frame_of_item(item)
        fields: dict[str, Any] = {
            "button": event.button().name,
            "frame": chrome[0] if chrome is not None else _frame_id(frame),
            "chrome": chrome[1] if chrome is not None else ("content" if frame is not None else "canvas"),
            "stack": self._frames_at(scene_pos),
        }
        hit_frame = frame
        if chrome is not None:
            hit_frame = next((f for f in self._view.placed_frames() if f.instance_id == chrome[0]), frame)
        fields.update(self._neighbour_fields(hit_frame))
        self.record("mouse_press", **fields)
