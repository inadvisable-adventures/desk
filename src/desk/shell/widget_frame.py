import uuid

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QFontMetrics
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

TITLEBAR_HEIGHT = 28
HANDLE_THICKNESS = 6
TITLEBAR_FONT_PT = 10
CLOSE_BUTTON_SIZE = 18
MIN_WIDTH = 200
MIN_HEIGHT = 120
BORDER_THICKNESS = 1
BORDER_COLOR = "#4a4d51"
UNFOCUSED_TITLEBAR_COLOR = "#3a3d41"
FOCUSED_TITLEBAR_COLOR = "#4a4e54"

# TODO 8afef71: forces every canvas-embedded widget's QPushButton/
# QToolButton/QLineEdit chrome (background, border) to be painted by
# Qt's own CSS engine instead of the native platform style, which
# doesn't respect the Workspace Canvas's QGraphicsView zoom transform
# once composited through a QGraphicsProxyWidget (see LEARNINGS.md's "A
# native-style-drawn control ... can visually desync ..." entry).
# Colors match this file's own chrome palette (BORDER_COLOR,
# *_TITLEBAR_COLOR) for visual consistency with the rest of a widget's
# frame. Deliberately NOT done via QStyleFactory.create("Fusion") +
# per-widget setStyle() (TODO 465c404/593a464's original approach) --
# confirmed directly that setStyle() on a descendant is silently
# overridden the moment *any* ancestor has its own setStyleSheet()
# called (which WidgetFrame itself already does, for its border, via
# _apply_border_scale below), regardless of call order. A stylesheet
# set directly on `content`, by contrast, cascades correctly to every
# descendant -- present *and* future (a widget that tears down and
# rebuilds its own child buttons on every render, e.g.
# widgets/lightning_round/widget.py, needs no special handling) --
# confirmed by pixel-sampling rendered buttons, not just introspecting
# style()/objectName() (which turned out to be an unreliable signal
# here: PyQt reports both the platform default and an explicitly
# -created Fusion QStyle as indistinguishable QCommonStyle wrappers
# under this environment's offscreen platform). Scoped to `content`
# only, not applied anywhere in WidgetFrame's own chrome -- that chrome
# is already hand-painted (_TitlebarButton draws its own background/
# glyph via plain QWidget/QLabel, not QPushButton) and was never
# subject to this bug. A widget's own more-specific per-control
# stylesheet (e.g. widgets/todo/widget.py's FILTER_BUTTON_STYLE) still
# takes precedence over this one, same as normal CSS cascade.
CONTENT_ZOOM_SAFE_STYLESHEET = f"""
QPushButton, QToolButton {{
    background-color: {BORDER_COLOR};
    border: 1px solid #6a6e73;
    border-radius: 3px;
    padding: 4px 10px;
}}
QPushButton:hover, QToolButton:hover {{
    background-color: {FOCUSED_TITLEBAR_COLOR};
}}
QPushButton:pressed, QToolButton:pressed {{
    background-color: {UNFOCUSED_TITLEBAR_COLOR};
}}
QPushButton:checked, QToolButton:checked {{
    background-color: #3daee9;
    border-color: #2a8cc4;
}}
QPushButton:disabled, QToolButton:disabled {{
    color: #888888;
    background-color: {UNFOCUSED_TITLEBAR_COLOR};
}}
QLineEdit {{
    background-color: #2b2d30;
    border: 1px solid #6a6e73;
    border-radius: 3px;
    padding: 2px 4px;
}}
QLineEdit:focus {{
    border-color: #3daee9;
}}
"""

# TODO 33d3e8d: titlebar degrade sequence (full -> title_only -> greeked) --
# see design-docs/widget-ux.md's "Titlebar Degrade + Greeking" section.
TITLEBAR_CONTENT_MARGIN = 8  # matches _TitleBar's own layout.setContentsMargins
TITLEBAR_BUTTON_SPACING = 4  # explicit (not style-default) so the fit math below is deterministic
TEMPUI_BUTTON_MARGIN = 4  # matches _TempuiPromoteButton's own layout.setContentsMargins
MIN_TITLE_WIDTH = 40  # on-screen px -- enough room to read a few characters of title text
NORMAL_PAGE_INDEX = 0
GREEK_PAGE_INDEX = 1


class _TitlebarButton(QWidget):
    """Purely visual: background, cursor shape, and a glyph label.
    Clicking is handled centrally by WorkspaceView (not by this widget
    itself) -- see design-docs/widget-ux.md for why. Shared base for
    the close, bring-to-front, and send-to-back buttons -- each is
    otherwise identical (a constant-screen-size glyph, counter-scaled
    the same way as the rest of the chrome)."""

    def __init__(self, glyph: str, parent=None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._label = QLabel(glyph)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        layout.addWidget(self._label)

        self.apply_scale(1.0)

    def apply_scale(self, view_scale: float) -> None:
        """See _TitleBar.apply_scale: keeps this button a constant
        on-screen size regardless of the WorkspaceView's current zoom."""
        view_scale = view_scale or 1.0
        size = max(1, round(CLOSE_BUTTON_SIZE / view_scale))
        self.setFixedSize(size, size)
        font_pt = max(1, round(TITLEBAR_FONT_PT / view_scale))
        self._label.setStyleSheet(f"color: #e8e8e8; font-size: {font_pt}pt;")


class _CloseButton(_TitlebarButton):
    def __init__(self, parent=None) -> None:
        super().__init__("✕", parent)


class _BringToFrontButton(_TitlebarButton):
    def __init__(self, parent=None) -> None:
        super().__init__("▲", parent)


class _SendToBackButton(_TitlebarButton):
    def __init__(self, parent=None) -> None:
        super().__init__("▼", parent)


class _LockButton(_TitlebarButton):
    def __init__(self, parent=None) -> None:
        super().__init__("🔒", parent)


class _UnlockButton(_TitlebarButton):
    def __init__(self, parent=None) -> None:
        super().__init__("🔓", parent)


class _EyeButton(_TitlebarButton):
    """TODO 33d3e8d: zoom/pan the Workspace Canvas so this widget fills the
    view (20% margin) -- the same action a click on a "greeked" widget
    triggers (see WorkspaceView.zoom_to_widget), but always present on
    every titlebar regardless of current chrome/zoom state."""

    def __init__(self, parent=None) -> None:
        super().__init__("👁", parent)


class _TempuiPromoteButton(QWidget):
    """Shown only on a placed instance of a tempui-DSL-defined custom
    widget (TODO 91b3f42) -- offers to promote it into the current
    .desk file. Unlike _TitlebarButton (a fixed-square single glyph:
    ✕/▲/▼/🔒/🔓), this shows the literal, longer "[TEMPUI]" label, so
    it isn't a _TitlebarButton subclass -- fixed height (matches the
    titlebar), width sized to its own text instead of a fixed square.
    Clicking is handled centrally by WorkspaceView, same as every other
    titlebar button -- see design-docs/widget-ux.md."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(TEMPUI_BUTTON_MARGIN, 0, TEMPUI_BUTTON_MARGIN, 0)
        self._label = QLabel("[TEMPUI]")
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        layout.addWidget(self._label)

        self.apply_scale(1.0)

    def apply_scale(self, view_scale: float) -> None:
        """See _TitleBar.apply_scale: keeps this button a constant
        on-screen size regardless of the WorkspaceView's current zoom."""
        view_scale = view_scale or 1.0
        self.setFixedHeight(max(1, round(TITLEBAR_HEIGHT / view_scale)))
        font_pt = max(1, round(TITLEBAR_FONT_PT / view_scale))
        self._label.setStyleSheet(f"color: #e8e8e8; font-size: {font_pt}pt;")


def _button_target_width(button: QWidget) -> int:
    """TODO 33d3e8d: this button's own fixed on-screen width -- the same
    width it always renders at once counter-scaled (apply_scale), so this
    is measured independent of the WorkspaceView's current zoom. Every
    _TitlebarButton (close/lock/unlock/bring-to-front/send-to-back/eye)
    is a fixed CLOSE_BUTTON_SIZE square; _TempuiPromoteButton is sized to
    its own "[TEMPUI]" text at the titlebar's fixed on-screen font size."""
    if isinstance(button, _TempuiPromoteButton):
        font = QFont()
        font.setPointSize(TITLEBAR_FONT_PT)
        text_width = QFontMetrics(font).horizontalAdvance("[TEMPUI]")
        return text_width + TEMPUI_BUTTON_MARGIN * 2
    return CLOSE_BUTTON_SIZE


class _TitleBar(QWidget):
    """Purely visual: background, cursor shape, and a non-selectable title
    label. Dragging is handled centrally by WorkspaceView (not by this
    widget itself) — see design-docs/widget-ux.md for why."""

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self._title = title
        self._external = False
        self._locked = False
        self._tempui_promotable = False
        self._buttons_hidden = False  # True in the title_only chrome state (TODO 33d3e8d)
        self.set_focused(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(TITLEBAR_CONTENT_MARGIN, 0, TITLEBAR_CONTENT_MARGIN, 0)
        layout.setSpacing(TITLEBAR_BUTTON_SPACING)
        self._label = QLabel()
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._update_label_text()
        layout.addWidget(self._label)
        layout.addStretch()
        self.tempui_promote_button = _TempuiPromoteButton()
        layout.addWidget(self.tempui_promote_button)
        self.lock_button = _LockButton()
        layout.addWidget(self.lock_button)
        self.bring_to_front_button = _BringToFrontButton()
        layout.addWidget(self.bring_to_front_button)
        self.send_to_back_button = _SendToBackButton()
        layout.addWidget(self.send_to_back_button)
        self.close_button = _CloseButton()
        layout.addWidget(self.close_button)
        self.eye_button = _EyeButton()
        layout.addWidget(self.eye_button)
        self.unlock_button = _UnlockButton()
        layout.addWidget(self.unlock_button)
        self._refresh_button_visibility()

        self.apply_scale(1.0)

    def _update_label_text(self) -> None:
        self._label.setText(f"{self._title} [EXTERNAL]" if self._external else self._title)

    def set_external(self, is_external: bool) -> None:
        """Shows/hides the "[EXTERNAL]" marker (TODO a053e3a) -- for a
        widget whose loaded file is outside the current Desk's
        directory."""
        self._external = is_external
        self._update_label_text()

    def set_focused(self, focused: bool) -> None:
        """A subtle background-color shift (TODO 397770c) -- deliberately
        small, not a bold color swap that would compete with the
        widget's own default border (TODO ff6514a) or read as an
        error/warning state. Driven by WorkspaceView's app-wide
        QGraphicsScene.focusItemChanged tracking, not anything this
        class decides on its own."""
        color = FOCUSED_TITLEBAR_COLOR if focused else UNFOCUSED_TITLEBAR_COLOR
        self.setStyleSheet(f"background-color: {color};")

    def set_locked(self, locked: bool) -> None:
        """Shows only the title and an unlock icon while locked (TODO
        8d05920) -- every other button (including the eye button, TODO
        33d3e8d) collapses away (a hidden QHBoxLayout child takes zero
        space by default), not just visually de-emphasized."""
        self._locked = locked
        self._refresh_button_visibility()

    def set_tempui_promotable(self, promotable: bool) -> None:
        """Shows/hides the [TEMPUI] button (TODO 91b3f42) -- set once,
        right after a custom widget's frame is placed
        (DeskWindow._place_widget), never toggled off afterward even
        once promoted (a second click on an already-promoted instance
        just shows an informational message -- see
        DeskWindow._on_tempui_promote_requested)."""
        self._tempui_promotable = promotable
        self._refresh_button_visibility()

    def set_buttons_hidden(self, hidden: bool) -> None:
        """TODO 33d3e8d: the title_only chrome state -- the titlebar
        itself still renders (background, title label), but every
        action button hides regardless of lock/promotable state, since
        there isn't enough on-screen width for any of them. Driven by
        WidgetFrame._update_chrome_state, not decided here."""
        self._buttons_hidden = hidden
        self._refresh_button_visibility()

    def _refresh_button_visibility(self) -> None:
        show = not self._buttons_hidden
        self.tempui_promote_button.setVisible(show and self._tempui_promotable)
        self.lock_button.setVisible(show and not self._locked)
        self.bring_to_front_button.setVisible(show and not self._locked)
        self.send_to_back_button.setVisible(show and not self._locked)
        self.close_button.setVisible(show and not self._locked)
        self.eye_button.setVisible(show and not self._locked)
        self.unlock_button.setVisible(show and self._locked)

    def _visible_button_widgets_for_full_state(self) -> list[QWidget]:
        """The buttons that would actually show if this titlebar had
        unlimited width -- i.e. show=True in _refresh_button_visibility
        above. Used by min_full_width_px to compute how much on-screen
        width "full" chrome genuinely needs (TODO 33d3e8d) -- deliberately
        mirrors _refresh_button_visibility's own show/hide logic rather
        than reading .isVisible() off the buttons themselves, since this
        needs the answer for show=True regardless of the titlebar's
        *current* _buttons_hidden state (that's exactly what's being
        decided)."""
        buttons: list[QWidget] = []
        if self._tempui_promotable:
            buttons.append(self.tempui_promote_button)
        if self._locked:
            buttons.append(self.unlock_button)
        else:
            buttons.extend(
                [
                    self.lock_button,
                    self.bring_to_front_button,
                    self.send_to_back_button,
                    self.close_button,
                    self.eye_button,
                ]
            )
        return buttons

    def min_title_only_width_px(self) -> int:
        """On-screen px: the minimum width at which the title label
        alone (no buttons) is still readable -- below this, there's
        nothing left to show and the widget greeks (TODO 33d3e8d)."""
        return TITLEBAR_CONTENT_MARGIN * 2 + MIN_TITLE_WIDTH

    def min_full_width_px(self) -> int:
        """On-screen px: the minimum width needed to show every
        currently-relevant button at its fixed on-screen size, plus a
        minimum readable title (TODO 33d3e8d). Below this (but at or
        above min_title_only_width_px), chrome degrades to title_only."""
        buttons = self._visible_button_widgets_for_full_state()
        button_width = sum(_button_target_width(b) for b in buttons)
        gaps = len(buttons) * TITLEBAR_BUTTON_SPACING
        return self.min_title_only_width_px() + gaps + button_width

    def apply_scale(self, view_scale: float) -> None:
        """Counter-scales this titlebar's local height/font so that, once
        the WorkspaceView multiplies by view_scale when rendering, it lands
        back at a constant on-screen size regardless of zoom. See
        design-docs/widget-ux.md."""
        view_scale = view_scale or 1.0
        self.setFixedHeight(max(1, round(TITLEBAR_HEIGHT / view_scale)))
        font_pt = max(1, round(TITLEBAR_FONT_PT / view_scale))
        self._label.setStyleSheet(f"color: #e8e8e8; font-size: {font_pt}pt;")
        self.tempui_promote_button.apply_scale(view_scale)
        self.lock_button.apply_scale(view_scale)
        self.bring_to_front_button.apply_scale(view_scale)
        self.send_to_back_button.apply_scale(view_scale)
        self.close_button.apply_scale(view_scale)
        self.eye_button.apply_scale(view_scale)
        self.unlock_button.apply_scale(view_scale)


class _ResizeHandle(QWidget):
    """Purely visual: background and cursor shape. Resizing is handled
    centrally by WorkspaceView (not by this widget itself) — see
    design-docs/widget-ux.md for why."""

    def __init__(self, edge: str, parent=None) -> None:
        super().__init__(parent)
        self.edge = edge
        self.setStyleSheet("background-color: #2a2d2f;")
        if edge in ("left", "right"):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        else:
            self.setCursor(Qt.CursorShape.SizeVerCursor)

        self.apply_scale(1.0)

    def apply_scale(self, view_scale: float) -> None:
        """See _TitleBar.apply_scale: keeps this handle a constant on-screen
        thickness regardless of the WorkspaceView's current zoom."""
        view_scale = view_scale or 1.0
        thickness = max(1, round(HANDLE_THICKNESS / view_scale))
        if self.edge in ("left", "right"):
            self.setFixedWidth(thickness)
        else:
            self.setFixedHeight(thickness)


class WidgetFrame(QWidget):
    """Wraps any widget content (a PythonWidgetHost or ChromiumWidget) with
    the common Desk widget chrome: a draggable titlebar and left/right/
    bottom resize handles. Built once at the canvas-integration layer
    (WorkspaceView.add_widget) rather than duplicated per widget kind. See
    design-docs/widget-ux.md.

    The chrome (titlebar, resize handles) stays a constant size on screen
    regardless of the Workspace Canvas's zoom level — see set_view_scale.
    Only the wrapped content zooms/pans with the view.

    Note: the chrome widgets here are purely visual. Drag/resize
    interaction is handled centrally by WorkspaceView's own mouse events,
    not by these embedded widgets' own mouse events — see
    design-docs/widget-ux.md for why (embedded-widget mouse events don't
    reliably reflect real screen coordinates at non-unity view scale)."""

    def __init__(
        self, title: str, content: QWidget, instance_id: str | None = None, parent=None
    ) -> None:
        super().__init__(parent)
        self.instance_id = instance_id or uuid.uuid4().hex[:8]
        content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        # TODO 33d3e8d audit finding: without this, Qt's layout system
        # forcibly grows this widget back up to its layout's minimum size
        # hint whenever that hint changes (e.g. any apply_scale() call
        # below, which uses setFixedSize/setFixedHeight on chrome
        # children) -- confirmed directly, and pre-existing (reproduces
        # with only the original apply_scale counter-scaling, no
        # QStackedWidget/chrome-state code involved). At small enough
        # view_scale, counter-scaled *local* chrome sizes (CONST /
        # view_scale) balloon well past this frame's own actual local
        # size, so left unconstrained, the frame would keep silently
        # growing itself back to full size on screen -- defeating both
        # the on-screen-size math this class relies on (_update_chrome
        # _state) and the whole point of shrinking a widget down small on
        # screen in the first place. SetNoConstraint stops the layout
        # from ever resizing this widget on its own; only explicit
        # resize() calls (initial placement, WorkspaceView's resize-drag)
        # change its size, same as before this fix.
        outer.setSizeConstraint(QVBoxLayout.SizeConstraint.SetNoConstraint)

        # TODO 33d3e8d: a QStackedWidget swaps between normal chrome+content
        # and a plain "greeked" placeholder page once this frame is too
        # small on screen to show anything meaningful -- same page-swap
        # shape the Browser widget's pop-up containment (TODO e35bcf0)
        # already established. See _update_chrome_state/_set_greeked.
        self._stack = QStackedWidget()
        outer.addWidget(self._stack, stretch=1)

        normal_page = QWidget()
        normal_layout = QVBoxLayout(normal_page)
        normal_layout.setContentsMargins(0, 0, 0, 0)
        normal_layout.setSpacing(0)

        self._titlebar = _TitleBar(title)
        normal_layout.addWidget(self._titlebar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self._left_handle = _ResizeHandle("left")
        body.addWidget(self._left_handle)
        body.addWidget(content, stretch=1)
        self._right_handle = _ResizeHandle("right")
        body.addWidget(self._right_handle)
        normal_layout.addLayout(body, stretch=1)

        self._bottom_handle = _ResizeHandle("bottom")
        normal_layout.addWidget(self._bottom_handle)

        self._greek_page = QWidget()
        self._greek_page.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._greek_page.setStyleSheet(f"background-color: {BORDER_COLOR};")

        self._stack.addWidget(normal_page)
        self._stack.addWidget(self._greek_page)
        self._stack.setCurrentIndex(NORMAL_PAGE_INDEX)

        self.content = content
        # See CONTENT_ZOOM_SAFE_STYLESHEET's own comment for why this is
        # a stylesheet rather than a per-control setStyle() call.
        content.setStyleSheet(CONTENT_ZOOM_SAFE_STYLESHEET)
        self._last_focused_widget: QWidget | None = None
        self.locked = False
        self._view_scale = 1.0
        self._chrome_state = "full"
        self._apply_border_scale(1.0)

    def _apply_border_scale(self, view_scale: float) -> None:
        """A small default border (TODO ff6514a) distinguishing this
        widget from the canvas and from adjacent widgets -- counter
        -scaled to a constant on-screen thickness, same convention as
        every other piece of chrome here (see _TitleBar.apply_scale).
        Scoped to the `WidgetFrame` class name, not a bare `QWidget`
        selector, since an unscoped QWidget stylesheet rule cascades
        to every nested child widget (buttons, fields, ...) inside
        arbitrary widget content."""
        view_scale = view_scale or 1.0
        thickness = max(1, round(BORDER_THICKNESS / view_scale))
        self.setStyleSheet(f"WidgetFrame {{ border: {thickness}px solid {BORDER_COLOR}; }}")

    def set_view_scale(self, view_scale: float) -> None:
        self._view_scale = view_scale or 1.0
        pre_scale_size = self.size()
        for chrome in (self._titlebar, self._left_handle, self._right_handle, self._bottom_handle):
            chrome.apply_scale(self._view_scale)
        self._apply_border_scale(self._view_scale)
        self._update_chrome_state()
        # TODO 33d3e8d audit finding: the counter-scaling above changes
        # chrome children's *local* fixed sizes (larger, the more zoomed
        # out -- CONST / view_scale), which can grow past this frame's
        # own local size at low enough view_scale. Confirmed directly:
        # something in this widget's QGraphicsProxyWidget embedding
        # silently grows this widget back up to fit that larger local
        # minimum -- not synchronously (the _update_chrome_state() call
        # just above still sees the correct pre-grown size, so it's
        # already computed the right chrome_state), but on a *later*,
        # deferred event-loop turn, which would then fire a genuine
        # resizeEvent and recompute chrome_state wrong (against a
        # ballooned size that doesn't reflect reality). SetNoConstraint
        # above (see __init__) already stops one path to this, but not
        # this one -- QGraphicsProxyWidget's own embedding sync is
        # independent of this widget's own QLayout::SizeConstraint.
        # Reasserting the real size one event-loop turn later is the
        # same "deferred singleShot(0) reassertion" shape already used
        # for the Desk picker/zoom control HUD drift bug (TODO
        # 82d66c0/4adfcad/1f9bd34) -- confirmed directly that a
        # synchronous resize() here doesn't stick (the regrowth hasn't
        # happened yet), while this deferred one does, and that it
        # doesn't fight a genuine concurrent resize (nothing else
        # legitimately resizes this widget within this same window).
        QTimer.singleShot(0, lambda: self._reassert_size(pre_scale_size))

    def _reassert_size(self, size) -> None:
        if self.size() != size:
            self.resize(size)

    def set_external(self, is_external: bool) -> None:
        """Shows/hides the titlebar's "[EXTERNAL]" marker (TODO
        a053e3a). See `desk.shell.window.DeskWindow`'s generic
        `external_changed`-signal binding in `_place_widget`."""
        self._titlebar.set_external(is_external)

    def set_focused(self, focused: bool) -> None:
        """TODO 397770c -- called by WorkspaceView's app-wide
        QGraphicsScene.focusItemChanged tracking, not decided by this
        class itself."""
        self._titlebar.set_focused(focused)

    def set_locked(self, locked: bool) -> None:
        """Locks/unlocks this widget in place (TODO 8d05920): while
        locked, its titlebar shows only the title and an unlock icon
        (`_TitleBar.set_locked`), and WorkspaceView's mouse handling
        skips starting a drag or resize for it (still allows a
        titlebar click to focus its content, TODO a1c701d)."""
        self.locked = locked
        self._titlebar.set_locked(locked)
        self._update_chrome_state()

    def set_tempui_promotable(self, promotable: bool) -> None:
        """Shows/hides the [TEMPUI] button (TODO 91b3f42) -- see
        `desk.shell.window.DeskWindow._place_widget`."""
        self._titlebar.set_tempui_promotable(promotable)
        self._update_chrome_state()

    @property
    def title(self) -> str:
        """Public read access to this widget's own title (TODO
        f2aede6's UI-element path descriptions want it) -- previously
        only reachable via the private `_titlebar._title`."""
        return self._titlebar._title

    @property
    def chrome_state(self) -> str:
        """One of "full"/"title_only"/"greeked" (TODO 33d3e8d) -- see
        _update_chrome_state."""
        return self._chrome_state

    @property
    def is_greeked(self) -> bool:
        """Convenience for WorkspaceView._hit_test_chrome's greeked
        short-circuit (TODO 33d3e8d)."""
        return self._chrome_state == "greeked"

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # hasattr guard: QWidget layouts can fire resize events during
        # this class's own __init__, before _titlebar exists yet -- same
        # shape as WorkspaceView.scrollContentsBy's existing guard.
        if hasattr(self, "_titlebar"):
            self._update_chrome_state()

    def _update_chrome_state(self) -> None:
        """TODO 33d3e8d: recomputes this frame's chrome degrade state
        from its current on-screen size (local size * the WorkspaceView's
        current zoom) -- fires on every zoom change (set_view_scale,
        already called on every zoom change) *and* on this frame's own
        resizeEvent (a manual resize-handle drag changes on-screen size
        too, without any set_view_scale call). See
        design-docs/widget-ux.md's "Titlebar Degrade + Greeking"."""
        on_screen_width = self.width() * self._view_scale
        on_screen_height = self.height() * self._view_scale
        if on_screen_height < TITLEBAR_HEIGHT or on_screen_width < self._titlebar.min_title_only_width_px():
            new_state = "greeked"
        elif on_screen_width < self._titlebar.min_full_width_px():
            new_state = "title_only"
        else:
            new_state = "full"

        if new_state == self._chrome_state:
            return
        self._chrome_state = new_state
        self._titlebar.set_buttons_hidden(new_state != "full")
        self._stack.setCurrentIndex(GREEK_PAGE_INDEX if new_state == "greeked" else NORMAL_PAGE_INDEX)

    def remember_focused_widget(self, widget: QWidget) -> None:
        """Records the most recently focused descendant inside
        `content` (TODO 397770c) -- also called by WorkspaceView's
        app-wide focus tracking, for `focus_last_widget` (TODO
        a1c701d) to restore later."""
        self._last_focused_widget = widget

    def focus_last_widget(self) -> None:
        """Re-focuses whichever control most recently had focus inside
        this widget (TODO a1c701d) -- triggered by a titlebar click, not
        a drag (see WorkspaceView.mouseReleaseEvent). Falls back to
        `content` itself if nothing has been focused inside this widget
        yet -- harmless even for a widget with no explicit focus proxy
        (Qt just makes the container itself the focus item), correct
        and useful for one that has."""
        target = self._last_focused_widget or self.content
        target.setFocus(Qt.FocusReason.MouseFocusReason)

    def focusNextPrevChild(self, next: bool) -> bool:
        """Traps Tab/Shift+Tab within this widget's own content (TODO
        e69f209) instead of letting Qt's default handling escalate an
        exhausted local search out to the next/previous item in the
        shared canvas `QGraphicsScene` -- every widget here is meant to
        behave like an independent floating window, not a tab stop in
        some canvas-wide sequence, and the default escalation can hand
        keyboard focus to a completely unrelated widget elsewhere on
        the canvas. Especially easy to miss mid-typing when that widget
        happens to visually overlap this one -- see LEARNINGS.md.

        The escape isn't reliably visible synchronously here (confirmed
        directly: `super().focusNextPrevChild()` can return `True` --
        "handled, nothing to escalate" -- while the actual scene-level
        handoff to a sibling item still happens moments later; the same
        "QGraphicsProxyWidget's own focus resolution runs after this
        call, not during it" shape already documented for the Lightning
        Round widget's click-to-focus fix). So this always claims the
        event, then defers one event-loop iteration and reclaims focus
        if it landed outside this widget's own subtree -- there's no
        case where handing focus to a sibling WidgetFrame is actually
        wanted, so there's nothing to conditionally allow."""
        target_before = self.focusWidget()
        super().focusNextPrevChild(next)
        QTimer.singleShot(0, lambda: self._reclaim_focus_if_escaped(next, target_before))
        return True

    def _reclaim_focus_if_escaped(self, next: bool, fallback: QWidget | None) -> None:
        proxy = self.graphicsProxyWidget()
        if proxy is None:
            return
        scene = proxy.scene()
        if scene is None or scene.focusItem() is proxy:
            return
        focusable = [
            w
            for w in self.findChildren(QWidget)
            if w.focusPolicy() != Qt.FocusPolicy.NoFocus and w.isVisible()
        ]
        target = (focusable[0] if next else focusable[-1]) if focusable else fallback
        if target is not None:
            target.setFocus(Qt.FocusReason.TabFocusReason)
