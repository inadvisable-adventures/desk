"""Verifies TODO `53779f4`: the Open Widgets widget and the signals/hooks
behind it. Real WorkspaceView for the signals; stub providers for the widget."""

import os
import sys
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.window  # noqa: E402,F401  (must precede QApplication)

from PyQt6.QtWidgets import QApplication, QLabel  # noqa: E402

app = QApplication(sys.argv)

from desk.event_mediator import EventMediator  # noqa: E402
from desk.shell import current_context  # noqa: E402
from desk.shell.canvas import WorkspaceView  # noqa: E402
from desk.widget_overview import WIDGET_OVERVIEW_CHANGED_EVENT  # noqa: E402

_KEEP_ALIVE = []


def _keep(mediator):
    """An EventSubscription's destroyed-callback calls mediator.unsubscribe_all
    when the widget is garbage collected; if the mediator was collected first
    (interpreter shutdown order is arbitrary) that raises and aborts the
    process. Keep every test mediator alive for the whole run."""
    _KEEP_ALIVE.append(mediator)
    return mediator


passed = 0
failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


def _module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("ow_check", REPO_ROOT / "widgets" / "open_widgets" / "widget.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


module = _module()


# -- signals ---------------------------------------------------------------------------


def test_frames_changed_signal():
    view = WorkspaceView()
    hits = []
    view.frames_changed.connect(lambda: hits.append(1))
    proxy = view.add_widget(QLabel("a"), title="a")
    check("adding a widget signals", len(hits) == 1)
    frame = proxy.widget()
    frame.set_stale(True)
    check("a stale flip signals", len(hits) == 2)
    frame.set_stale(True)
    check("setting the same stale value again does not", len(hits) == 2)
    frame.set_stale(False)
    check("flipping back signals", len(hits) == 3)
    view.remove_widget(frame)
    check("removing signals", len(hits) == 4)
    view.add_widget(QLabel("b"), title="b")
    view.clear_widgets()
    check("clearing signals", len(hits) == 6)


# -- widget ---------------------------------------------------------------------------------


def overview(*rows):
    return [{"instance_id": i, "widget_id": w, "title": t, "kind": k, "stale": s} for i, w, t, k, s in rows]


def with_hooks(rows, zoomer=None, reloader=None):
    saved = (
        current_context.get_widget_overview_provider(),
        current_context.get_widget_zoomer(),
        current_context.get_stale_widgets_reloader(),
    )
    current_context.set_widget_overview_provider(lambda: rows)
    current_context.set_widget_zoomer(zoomer or (lambda iid: True))
    current_context.set_stale_widgets_reloader(reloader or (lambda: 0))
    return saved


def restore(saved):
    for setter, value in zip((current_context.set_widget_overview_provider, current_context.set_widget_zoomer, current_context.set_stale_widgets_reloader), saved):
        if value is not None:
            setter(value)


def cell(widget, row, col):
    return widget._table.item(row, col).text()


def test_initial_load_and_columns():
    rows = overview(("a1", "editor", "Editor (a1)", "python", False), ("b2", "custom", "Custom (b2)", "html", True))
    saved = with_hooks(rows)
    try:
        widget = module.build()
        check("a row per instance", widget._table.rowCount() == 2)
        check("columns hold title, kind, instance and stale", [cell(widget, 1, c) for c in range(4)] == ["Custom (b2)", "html", "b2", "STALE"] and cell(widget, 0, 3) == "")
        check("the summary counts stale ones", widget._status_label.text() == "2 widget(s), 1 stale.")
        check("the reload button is enabled when something is stale", widget._reload_button.isEnabled())
    finally:
        restore(saved)


def test_live_updates_replace_the_table():
    saved = with_hooks(overview(("a1", "editor", "E", "python", False)))
    try:
        widget = module.build()
        mediator = _keep(EventMediator())
        widget.bind_event_mediator("ow-1", mediator)
        check("no stale -> the reload button is disabled", not widget._reload_button.isEnabled())
        mediator.publish(WIDGET_OVERVIEW_CHANGED_EVENT, {"widgets": overview(("a1", "editor", "E", "python", False), ("c3", "x", "X", "html", True))}, "desk")
        widget._subscription._poll()
        check("an event replaces the rows", widget._table.rowCount() == 2 and cell(widget, 1, 2) == "c3")
        check("and enables the reload button", widget._reload_button.isEnabled())
        mediator.publish(WIDGET_OVERVIEW_CHANGED_EVENT, {"widgets": []}, "desk")
        widget._subscription._poll()
        check("removal empties the table", widget._table.rowCount() == 0)
        widget._on_mediated_event("other.event", {"widgets": overview(("z", "z", "z", "z", False))}, "x")
        check("unrelated events are ignored", widget._table.rowCount() == 0)
    finally:
        restore(saved)


def test_double_click_zooms_and_reload_button_calls_the_hook():
    zooms, reloads = [], []
    saved = with_hooks(overview(("a1", "e", "E", "python", False), ("b2", "e", "E", "python", True)), zoomer=lambda iid: zooms.append(iid) or True, reloader=lambda: reloads.append(1) or 1)
    try:
        widget = module.build()
        widget._table.cellDoubleClicked.emit(1, 0)
        check("double-clicking a row zooms to that instance", zooms == ["b2"])
        widget._on_row_double_clicked(9, 0)
        check("an out-of-range row is ignored", zooms == ["b2"])
        widget._reload_button.click()
        check("the button calls the stale-reloader hook", reloads == [1])
    finally:
        restore(saved)


# -- window ------------------------------------------------------------------------------------


def fake_window(frames, widgets=None):
    DeskWindow = desk.shell.window.DeskWindow
    published = []
    fake = types.SimpleNamespace(
        view=types.SimpleNamespace(_frames=frames),
        _widgets=widgets or {},
        _event_mediator=types.SimpleNamespace(publish=lambda *a: published.append(a)),
        _overview_publish_pending=False,
        _promoted_widget_source_dirty=set(),
        _custom_widget_content_hash={},
        _custom_widget_definitions={},
    )
    fake._display_name_for_instance = lambda iid: f"name-{iid}"
    fake._reload_stale_frame = lambda frame: DeskWindow._reload_stale_frame(fake, frame)
    fake.get_widget_overview = lambda: DeskWindow.get_widget_overview(fake)
    fake._published = published
    return DeskWindow, fake


class _Content:
    def __init__(self, widget_id):
        self.widget_id = widget_id
        self.reloads = 0

    def reload(self):
        self.reloads += 1


class _Frame:
    def __init__(self, instance_id, widget_id, stale=False):
        self.instance_id = instance_id
        self.content = _Content(widget_id)
        self._stale = stale
        self.placed_content_hash = "old"

    def is_stale(self):
        return self._stale

    def set_stale(self, value):
        self._stale = value


def test_window_overview_and_publish():
    DeskWindow, fake = fake_window([_Frame("a1", "editor"), _Frame("b2", "custom", stale=True)], {"editor": types.SimpleNamespace(kind="python")})
    result = DeskWindow.get_widget_overview(fake)
    check("overview has every instance in order with title, kind and stale", result == [
        {"instance_id": "a1", "widget_id": "editor", "title": "name-a1", "kind": "python", "stale": False},
        {"instance_id": "b2", "widget_id": "custom", "title": "name-b2", "kind": "unknown", "stale": True},
    ])
    DeskWindow._publish_widget_overview(fake)
    name, payload, sender = fake._published[0]
    check("publishing sends the full overview under the documented event, from 'desk'", name == WIDGET_OVERVIEW_CHANGED_EVENT and payload == {"widgets": result} and sender == "desk")


def test_schedule_coalesces():
    DeskWindow, fake = fake_window([])
    from PyQt6.QtCore import QTimer

    fake._publish_widget_overview = lambda: DeskWindow._publish_widget_overview(fake)
    scheduled = []
    real = QTimer.singleShot
    QTimer.singleShot = staticmethod(lambda ms, fn: scheduled.append(fn))
    try:
        DeskWindow._schedule_overview_publish(fake)
        DeskWindow._schedule_overview_publish(fake)
        DeskWindow._schedule_overview_publish(fake)
    finally:
        QTimer.singleShot = real
    check("a burst schedules exactly one publish", len(scheduled) == 1 and fake._overview_publish_pending)
    scheduled[0]()
    check("running it publishes once and re-arms", len(fake._published) == 1 and not fake._overview_publish_pending)


def test_reload_all_stale():
    DeskWindow = desk.shell.window.DeskWindow
    ChromiumWidget = desk.shell.window.ChromiumWidget

    class _Chromium(ChromiumWidget):  # a stand-in that passes isinstance
        def __init__(self, widget_id):
            self.widget_id = widget_id
            self.reloads = 0

        def reload(self):
            self.reloads += 1

    def frame(iid, keyword, stale):
        f = _Frame(iid, keyword, stale)
        f.content = _Chromium(keyword)
        return f

    frames = [frame("s1", "k", True), frame("s2", "k", True), frame("ok", "k", False)]
    _w, fake = fake_window(frames)
    fake._custom_widget_content_hash = {"k": "new"}
    asked = []
    fake._confirm_reload_all_stale = lambda n: asked.append(n) or True
    count = DeskWindow.reload_all_stale_widgets(fake)
    check("one confirmation for the whole batch, with the right count", asked == [2])
    check("every stale instance was reloaded onto the current hash and cleared", count == 2 and all(f.content.reloads == 1 and f.placed_content_hash == "new" and not f.is_stale() for f in frames[:2]))
    check("a non-stale instance is untouched", frames[2].content.reloads == 0 and frames[2].placed_content_hash == "old")

    frames = [frame("s1", "k", True)]
    _w, fake = fake_window(frames)
    fake._confirm_reload_all_stale = lambda n: False
    check("declining reloads nothing", DeskWindow.reload_all_stale_widgets(fake) == 0 and frames[0].content.reloads == 0)
    _w, fake = fake_window([frame("ok", "k", False)])
    fake._confirm_reload_all_stale = lambda n: (_ for _ in ()).throw(AssertionError("must not ask when nothing is stale"))
    check("with nothing stale it neither asks nor reloads", DeskWindow.reload_all_stale_widgets(fake) == 0)


def test_zoom_by_instance_id_raises():
    DeskWindow = desk.shell.window.DeskWindow
    calls = []
    target = object()
    fake = types.SimpleNamespace(
        find_frame_by_instance_id=lambda iid: target if iid == "x" else None,
        view=types.SimpleNamespace(bring_to_front=lambda f: calls.append(("front", f)), zoom_to_widget=lambda f: calls.append(("zoom", f))),
    )
    check("zoom-by-id raises then zooms", DeskWindow.zoom_to_widget_by_instance_id(fake, "x") is True and calls == [("front", target), ("zoom", target)])
    check("an unknown id returns False", DeskWindow.zoom_to_widget_by_instance_id(fake, "nope") is False)


test_frames_changed_signal()
test_initial_load_and_columns()
test_live_updates_replace_the_table()
test_double_click_zooms_and_reload_button_calls_the_hook()
test_window_overview_and_publish()
test_schedule_coalesces()
test_reload_all_stale()
test_zoom_by_instance_id_raises()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
