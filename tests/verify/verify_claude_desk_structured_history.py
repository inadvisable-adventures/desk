"""Verifies TODO `dffb428`: the Claude (Desk) widget's structured
history -- per-entry kind/turn/source metadata, turn separation,
user-entry reload, auto-follow. See
plans/claude-desk-structured-history.md."""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

# desk.shell.window must be importable before QApplication is
# constructed -- see verify_claude_desk_widget.py's own comment.
import desk.shell.window  # noqa: E402,F401

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

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


def _load_widget_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "claude_desk_history_check", REPO_ROOT / "widgets" / "claude_desk" / "widget.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeSession:
    def __init__(self):
        self.sent = []

    def send_prompt(self, text):
        self.sent.append(text)


module = _load_widget_module()

LONG_SINGLE_LINE = "x" * 200
LONG_CONTENT = "line one is reasonably long on its own right here\n" + "line two follows after a real newline"

from desk.claude_history_view import HistoryEntry, HistoryView  # noqa: E402


def _event(kind, turn_id, solicited=True, seq=1):
    return {"seq": seq, "ts": 1.0, "turn_id": turn_id, "solicited": solicited, "kind": kind, "data": {}}


def test_every_entry_is_its_own_framed_widget_with_metadata():
    widget = module.build()
    widget._on_assistant_text("hi")
    widget._on_tool_use("id1", "Read", {"path": "x"})
    entries = widget._history.entries()
    check("two entries -> two HistoryEntry widgets", len(entries) == 2 and all(isinstance(e, HistoryEntry) for e in entries))
    check("each carries its kind", [e.meta.kind for e in entries] == ["assistant", "tool"])
    check("each carries a timestamp", all(e.meta.ts > 0 for e in entries))
    check("the history is no longer a text document", isinstance(widget._history, HistoryView) and not hasattr(widget._history, "document"))


def test_user_prompt_gets_its_turn_id_from_turn_started():
    widget = module.build()
    widget._session = _FakeSession()
    widget._send_now("hello")
    user = widget._history.entries()[0]
    check("user entry starts a turn (strong rule) and has no id yet", user.turn_start and user.meta.turn_id is None)
    widget._on_session_event(_event("turn_started", 7))
    check("turn_started assigns the pending user entry its turn id", user.meta.turn_id == 7)
    check("the id shows in the entry's metadata label", "turn 7" in user._meta_label.text())


def test_stream_entries_take_turn_id_from_the_preceding_event():
    widget = module.build()
    widget._on_session_event(_event("turn_started", 3))
    widget._on_session_event(_event("assistant_text", 3))
    widget._on_assistant_text("reply")
    widget._on_session_event(_event("tool_use", 3))
    widget._on_tool_use("id1", "Read", {"path": "x"})
    check("assistant and tool entries are filed under turn 3", [e.meta.turn_id for e in widget._history.entries()] == [3, 3])
    check("they are solicited (no source tag)", all(e.meta.source == "" for e in widget._history.entries()))


def test_unsolicited_output_is_tagged_and_starts_a_new_turn_block():
    widget = module.build()
    widget._on_session_event(_event("unsolicited_turn_started", 9, solicited=False))
    widget._on_session_event(_event("assistant_text", 9, solicited=False))
    widget._on_assistant_text("wakeup output")
    widget._on_session_event(_event("assistant_text", 9, solicited=False))
    widget._on_assistant_text("more wakeup output")
    first, second = widget._history.entries()
    check("source is unsolicited", first.meta.source == "unsolicited" and second.meta.source == "unsolicited")
    check("the first entry of the unsolicited turn is a turn start", first.turn_start and not second.turn_start)
    check("it carries the unsolicited turn id", first.meta.turn_id == 9)
    check("the metadata label says unsolicited", "unsolicited" in first._meta_label.text())


def test_permission_and_question_entries_attach_to_the_active_turn():
    widget = module.build()
    widget._session = _FakeSession()
    widget._on_session_event(_event("turn_started", 4))
    widget._pending_permissions.append(("r1", "Bash", {}))
    widget._session.respond_to_permission = lambda *a: None
    widget._resolve_current_permission(True)
    check("permission decision is filed under the in-flight turn", widget._history.entries()[-1].meta.turn_id == 4)
    widget._on_session_event(_event("turn_complete", 4))
    widget._add_entry("notice", "after")
    check("after turn_complete nothing is attributed to the finished turn", widget._history.entries()[-1].meta.turn_id is None)


def test_unsolicited_turn_complete_does_not_clear_the_active_turn():
    widget = module.build()
    widget._on_session_event(_event("turn_started", 5))
    widget._on_session_event(_event("turn_complete", 4, solicited=False))
    check("an unsolicited result leaves the real in-flight turn active", widget._active_turn_id == 5)


def test_reload_button_loads_the_bare_prompt():
    widget = module.build()
    widget._session = _FakeSession()
    widget._send_now("edit and resend me")
    user = widget._history.entries()[0]
    check("the user entry records the bare prompt as reload text", user.reload_text == "edit and resend me")
    widget._prompt_input.setPlainText("typed meanwhile")
    user._reload_button.click()
    check("clicking reload replaces the prompt box text", widget._prompt_input.toPlainText() == "edit and resend me")


def test_queued_entry_reloads_bare_prompt_and_non_user_entries_cannot_reload():
    widget = module.build()
    widget._session = _FakeSession()
    widget._busy = True
    widget._prompt_input.setPlainText("queue me")
    widget._on_send_clicked()
    queued = widget._history.entries()[0]
    check("queued entry kind and reload text", queued.meta.kind == "queued" and queued.reload_text == "queue me")
    widget._on_assistant_text("reply")
    widget._on_session_error("boom")
    check("assistant/error entries have no reload text", all(e.reload_text is None for e in widget._history.entries()[1:]))


def test_turn_boundaries_use_a_stronger_rule_than_ordinary_entries():
    widget = module.build()
    widget._session = _FakeSession()
    widget._send_now("hi")
    widget._on_assistant_text("hello")
    user, reply = widget._history.entries()
    check("a user entry's stylesheet has the heavy turn rule", "2px" in user.styleSheet())
    check("an ordinary entry's stylesheet has the light rule", "1px" in reply.styleSheet() and "2px" not in reply.styleSheet())


def test_entry_bodies_are_selectable_but_chrome_is_not():
    widget = module.build()
    widget._on_assistant_text("hello")
    entry = widget._history.entries()[0]
    from PyQt6.QtCore import Qt

    check("body text is selectable", bool(entry._body.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse))
    check("the metadata label is not selectable", not (entry._meta_label.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse))


def _settle():
    # Layout of newly added entries (and the scrollbar range change
    # that drives auto-follow) takes a few event-loop passes.
    for _ in range(5):
        app.processEvents()


def test_history_follows_the_bottom_until_the_user_scrolls_away():
    widget = module.build()
    widget.resize(400, 300)
    widget.show()
    app.processEvents()
    for i in range(60):
        widget._on_assistant_text(f"message {i}")
    _settle()
    bar = widget._history.verticalScrollBar()
    check("history scrolled to the bottom as entries arrived", bar.value() == bar.maximum() and bar.maximum() > 0)
    bar.setValue(0)
    _settle()
    widget._on_assistant_text("one more")
    _settle()
    check("after scrolling away, new entries don't yank the view", bar.value() == 0)


def test_copy_all_action_exists():
    widget = module.build()
    check("a 'Copy all history' action is offered", any(a.text() == "Copy all history" for a in widget._history.actions()))


test_every_entry_is_its_own_framed_widget_with_metadata()
test_user_prompt_gets_its_turn_id_from_turn_started()
test_stream_entries_take_turn_id_from_the_preceding_event()
test_unsolicited_output_is_tagged_and_starts_a_new_turn_block()
test_permission_and_question_entries_attach_to_the_active_turn()
test_unsolicited_turn_complete_does_not_clear_the_active_turn()
test_reload_button_loads_the_bare_prompt()
test_queued_entry_reloads_bare_prompt_and_non_user_entries_cannot_reload()
test_turn_boundaries_use_a_stronger_rule_than_ordinary_entries()
test_entry_bodies_are_selectable_but_chrome_is_not()
test_history_follows_the_bottom_until_the_user_scrolls_away()
test_copy_all_action_exists()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
