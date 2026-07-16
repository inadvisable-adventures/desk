import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from PyQt6.QtCore import QEvent, QPoint, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication

from desk.shell.widget_spawn_menu import WidgetSpawnMenu
from desk.widgets import WidgetInfo

app = QApplication(sys.argv)


def make_info(name, deprecated=False):
    return WidgetInfo(
        id=name.lower(), path=Path("."), kind="python", name=name, entry="widget.py",
        capabilities=[], default_size=None, deprecated=deprecated,
    )


CATALOG = {
    "todo": make_info("TODO"),
    "markdown": make_info("Markdown"),
    "old_markdown": make_info("Old Markdown", deprecated=True),
    "old_editor": make_info("Old Editor", deprecated=True),
}


def key_event(key):
    return QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)


def test_default_expand_state_and_grouping():
    menu = WidgetSpawnMenu(CATALOG)
    active = menu._group_items["Active"]
    deprecated = menu._group_items["Deprecated"]
    assert active.isExpanded() is True
    assert deprecated.isExpanded() is False
    assert active.childCount() == 2, active.childCount()
    assert deprecated.childCount() == 2, deprecated.childCount()
    names_active = {active.child(i).text(0) for i in range(active.childCount())}
    assert names_active == {"TODO", "Markdown"}, names_active
    menu.close()
    print("default expand state + correct grouping: PASS")


def test_filter_match_in_collapsed_group_stays_collapsed():
    menu = WidgetSpawnMenu(CATALOG)
    menu._filter.setText("old")
    deprecated = menu._group_items["Deprecated"]
    active = menu._group_items["Active"]
    assert deprecated.isExpanded() is False, "should not auto-expand"
    assert deprecated.childCount() == 2
    assert active.isHidden() is True, "Active should hide with zero matches"
    menu.close()
    print("filter match inside collapsed group stays collapsed, empty group hidden: PASS")


def test_manual_expand_survives_filter_typing():
    menu = WidgetSpawnMenu(CATALOG)
    deprecated = menu._group_items["Deprecated"]
    deprecated.setExpanded(True)
    menu._filter.setText("e")  # triggers _apply_filter -> _populate
    assert deprecated.isExpanded() is True, "manual expand should survive re-populate"
    menu.close()
    print("manually-expanded group survives filter re-populate: PASS")


def test_keyboard_nav_skips_headers_and_collapsed_entries():
    menu = WidgetSpawnMenu(CATALOG)
    # Deprecated is collapsed by default -- Down should only walk Active's
    # two entries (TODO, Markdown come out sorted by name: Markdown, TODO).
    visible = menu._visible_entries()
    names = [item.text(0) for item in visible]
    assert names == ["Markdown", "TODO"], names
    assert menu._list.currentItem().text(0) == "Markdown", "initial selection is the first visible entry"

    menu.eventFilter(menu._filter, key_event(Qt.Key.Key_Down))
    after_one_down = menu._list.currentItem()
    assert after_one_down.text(0) == "TODO", after_one_down.text(0)

    # Already at the last visible entry -- a second Down clamps, doesn't
    # wrap or fall through to a group header / a collapsed entry.
    menu.eventFilter(menu._filter, key_event(Qt.Key.Key_Down))
    after_two_down = menu._list.currentItem()
    assert after_two_down.text(0) == "TODO", after_two_down.text(0)

    menu.eventFilter(menu._filter, key_event(Qt.Key.Key_Up))
    after_up = menu._list.currentItem()
    assert after_up.text(0) == "Markdown", after_up.text(0)
    menu.close()
    print("keyboard nav walks only visible leaf entries, skipping headers, clamped at ends: PASS")


def test_enter_activates_and_closes():
    menu = WidgetSpawnMenu(CATALOG)
    chosen = []
    menu.widget_chosen.connect(chosen.append)
    menu._list.setCurrentItem(menu._visible_entries()[0])
    menu.eventFilter(menu._filter, key_event(Qt.Key.Key_Return))
    assert len(chosen) == 1
    assert chosen[0] in CATALOG
    print("Enter activates the current entry and emits widget_chosen: PASS")


def test_deprecated_defaults_false():
    from desk.widgets import _parse_manifest
    import json
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        wdir = Path(d) / "somewidget"
        wdir.mkdir()
        (wdir / "widget.json").write_text(json.dumps({"kind": "python", "name": "X"}))
        info = _parse_manifest(wdir / "widget.json")
        assert info.deprecated is False

        (wdir / "widget.json").write_text(json.dumps({"kind": "python", "name": "X", "deprecated": True}))
        info2 = _parse_manifest(wdir / "widget.json")
        assert info2.deprecated is True
    print("WidgetInfo.deprecated defaults False, honors explicit True: PASS")


test_default_expand_state_and_grouping()
test_filter_match_in_collapsed_group_stays_collapsed()
test_manual_expand_survives_filter_typing()
test_keyboard_nav_skips_headers_and_collapsed_entries()
test_enter_activates_and_closes()
test_deprecated_defaults_false()
print("ALL PASS")
