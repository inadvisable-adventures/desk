# Note: the mic-button test (starts a real MicRecorder capture -- a
# real QAudioSource against the actual default microphone) was split
# out to tests/verify/disabled_verify_claude_desk_widget_mic.py and
# disabled there (TODO b2ab79f); the tests that run real Claude API
# turns (a real ClaudeSession, real network calls/API cost) were split
# out to tests/verify/disabled_verify_claude_desk_widget_claude_api.py
# and disabled there (TODO 9bc522b). Both were making calls this
# project doesn't want happening automatically during routine
# regression sweeps. Every test remaining here never touches the
# microphone or the live Claude API and keeps running normally.
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

# desk.shell.window (imported by widget.py's DeskWindow-adjacent pieces
# indirectly) must be importable before QApplication is constructed --
# see LEARNINGS.md-worthy gotcha confirmed directly while writing this
# script: desk.shell.chromium_widget's QtWebEngineWidgets import fails
# with "must be imported... before a QCoreApplication instance is
# created" otherwise. Importing desk.shell.window first (even though
# this script doesn't exercise DeskWindow itself) sidesteps it, same
# as every other verify script here that touches window.py.
import desk.shell.window  # noqa: E402,F401

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtGui import QTextCursor  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
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


def test_widget_json_is_well_formed():
    manifest = json.loads((REPO_ROOT / "widgets" / "claude_desk" / "widget.json").read_text())
    check("widget.json declares kind: python", manifest["kind"] == "python")
    check("widget.json entry is widget.py", manifest["entry"] == "widget.py")
    check("widget.json name is Claude (Desk)", manifest["name"] == "Claude (Desk)")


def test_window_wiring():
    import desk.shell.window as window_mod
    from desk.shell.python_widget import PythonWidgetHost
    from PyQt6.QtWidgets import QWidget

    check(
        "CLAUDE_DESK_WIDGET_ID is a distinct id from CLAUDE_WIDGET_ID",
        window_mod.CLAUDE_DESK_WIDGET_ID == "claude_desk" and window_mod.CLAUDE_DESK_WIDGET_ID != window_mod.CLAUDE_WIDGET_ID,
    )
    check("DeskWindow._bind_claude_desk_widget exists", hasattr(window_mod.DeskWindow, "_bind_claude_desk_widget"))

    class _FakeContent:
        def __init__(self):
            self.calls = []

        def start_session(self, instance_id, resume, extra_instructions=""):
            self.calls.append((instance_id, resume, extra_instructions))

    class _FakeHost(PythonWidgetHost):
        def __init__(self, current):
            QWidget.__init__(self)
            self._current = current
            self.widget_id = window_mod.CLAUDE_DESK_WIDGET_ID

    class _FakeFrame:
        def __init__(self, content, instance_id):
            self.content = content
            self.instance_id = instance_id

    content = _FakeContent()
    frame = _FakeFrame(_FakeHost(content), "fake-instance-id")
    # DeskWindow.__new__(DeskWindow), not object.__new__(DeskWindow): the
    # latter raises TypeError ("not safe") since DeskWindow's effective
    # __new__ (inherited through QMainWindow) differs from object's --
    # confirmed directly. Skips __init__ (no real window construction
    # needed just to call one duck-typed method), matching this
    # project's own ChromiumWidget.__new__(ChromiumWidget) precedent
    # elsewhere in tests/verify/.
    fake_window = window_mod.DeskWindow.__new__(window_mod.DeskWindow)
    window_mod.DeskWindow._bind_claude_desk_widget(fake_window, frame, resume=True, extra_instructions="extra")
    check(
        "_bind_claude_desk_widget duck-types on start_session exactly like _bind_claude_widget",
        content.calls == [("fake-instance-id", True, "extra")],
    )


def _load_widget_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("claude_desk_widget", REPO_ROOT / "widgets" / "claude_desk" / "widget.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeSession:
    """A recording stand-in for desk.claude_session.ClaudeSession (TODO
    e9eddba) -- swapped in after the real widget is built (its own
    __init__ already constructed and wired a real ClaudeSession, but
    that object's own .start() is never called here, so nothing about
    swapping it out afterward leaves anything real running) so
    start_session/the permission-mode combo can be tested without a
    real ClaudeSDKClient/network call."""

    def __init__(self):
        self.start_calls = []
        self.permission_mode_calls = []
        self.send_prompt_calls = []

    def start(self, session_id, resume, model, permission_mode, cwd, initial_prompt):
        self.start_calls.append((session_id, resume, model, permission_mode, cwd, initial_prompt))

    def set_permission_mode(self, mode):
        self.permission_mode_calls.append(mode)

    def send_prompt(self, text):
        self.send_prompt_calls.append(text)

    def stop(self):
        # The widget's own __init__ connects self.destroyed to
        # self._session.stop() -- fires for any teardown, including at
        # interpreter exit for a widget this script never explicitly
        # closes, regardless of which session object is currently
        # installed.
        pass


def test_permission_mode_combo_present_and_defaults_to_default():
    module = _load_widget_module()
    widget = module.build()
    labels = [widget._permission_mode_combo.itemText(i) for i in range(widget._permission_mode_combo.count())]
    check(
        "the permission-mode combo offers all six real SDK modes",
        labels == ["Default", "Accept Edits", "Plan", "Bypass Permissions", "Don't Ask", "Auto"],
    )
    check("the permission-mode combo defaults to Default", widget._permission_mode_combo.currentIndex() == 0)


def test_start_session_passes_the_selected_permission_mode():
    import uuid

    module = _load_widget_module()
    for index, (label, value) in enumerate(module.PERMISSION_MODE_CHOICES):
        widget = module.build()
        fake_session = _FakeSession()
        widget._session = fake_session
        widget._permission_mode_combo.setCurrentIndex(index)
        widget.start_session(str(uuid.uuid4()), resume=False)
        check(
            f"start_session passes the real SDK value for {label!r}, not the label",
            fake_session.start_calls and fake_session.start_calls[0][3] == value,
        )


def test_changing_the_combo_calls_set_permission_mode_live():
    module = _load_widget_module()
    widget = module.build()
    fake_session = _FakeSession()
    widget._session = fake_session

    widget._permission_mode_combo.setCurrentIndex(1)
    check(
        "changing the combo calls set_permission_mode with the newly-selected value",
        fake_session.permission_mode_calls == ["acceptEdits"],
    )
    widget._permission_mode_combo.setCurrentIndex(4)
    check(
        "a second change calls it again with the new value",
        fake_session.permission_mode_calls == ["acceptEdits", "dontAsk"],
    )


def test_set_permission_mode_is_a_real_no_op_before_start():
    from desk.claude_session import ClaudeSession

    session = ClaudeSession()
    session.set_permission_mode("acceptEdits")  # must not raise
    check("ClaudeSession.set_permission_mode no-ops before any session has started", True)


def test_prompt_input_is_a_wrapping_multiline_box():
    module = _load_widget_module()
    widget = module.build()
    check(
        "_prompt_input is the new word-wrapping _PromptInput class, not a QLineEdit",
        isinstance(widget._prompt_input, module._PromptInput),
    )
    from PyQt6.QtWidgets import QPlainTextEdit

    check("_PromptInput is a QPlainTextEdit subclass", isinstance(widget._prompt_input, QPlainTextEdit))


def test_plain_enter_sends_without_inserting_a_newline():
    # A standalone _PromptInput, not a full built widget -- the real
    # ClaudeDeskWidget already wires send_requested to
    # _on_send_clicked, which clears the box as part of actually
    # sending, so testing through the full widget would conflate "was
    # a newline ever inserted" with "did the send handler clear
    # afterward". This isolates the class's own key handling.
    box = _load_widget_module()._PromptInput()
    box.setPlainText("hello")
    sent = []
    box.send_requested.connect(lambda: sent.append(True))

    QTest.keyClick(box, Qt.Key.Key_Return)

    check("plain Enter emits send_requested", sent == [True])
    check("plain Enter does not insert a newline", box.toPlainText() == "hello")


def test_shift_enter_inserts_a_newline_without_sending():
    box = _load_widget_module()._PromptInput()
    box.setPlainText("hello")
    box.moveCursor(box.textCursor().MoveOperation.End)
    sent = []
    box.send_requested.connect(lambda: sent.append(True))

    QTest.keyClick(box, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)

    check("Shift+Enter does not emit send_requested", sent == [])
    check("Shift+Enter inserts a newline", box.toPlainText() == "hello\n")


def test_on_send_clicked_reads_and_clears_the_multiline_box():
    widget = _load_widget_module().build()
    fake_session = _FakeSession()
    widget._session = fake_session
    widget._session_id = "fake-instance-id"

    widget._prompt_input.setPlainText("first line\nsecond line")
    widget._on_send_clicked()

    check("_on_send_clicked strips/sends the full multi-line text", "first line\nsecond line" in widget._history.toPlainText())
    check("_on_send_clicked clears the box afterward", widget._prompt_input.toPlainText() == "")


def test_mic_transcription_sets_text_via_setplaintext():
    from desk.speech import TranscriptionResult

    widget = _load_widget_module().build()
    widget._on_mic_transcription_finished(TranscriptionResult(text="dictated text", words=[]), None)
    check(
        "dictated text lands in _prompt_input via the new setPlainText/toPlainText API",
        widget._prompt_input.toPlainText() == "dictated text",
    )


def _selection_texts(widget) -> list[str]:
    """The plain text each of widget._history's current extra
    selections covers, with Qt's own U+2029 paragraph-separator
    (what QTextCursor.selectedText() uses in place of "\n" across a
    multi-block selection) converted back to "\n" for comparison
    against the original appended text."""
    return [selection.cursor.selectedText().replace(" ", "\n") for selection in widget._history.extraSelections()]


def test_send_now_highlights_the_user_line():
    module = _load_widget_module()
    widget = module.build()
    widget._session = _FakeSession()

    widget._send_now("hello there")

    check("sending a message adds exactly one extra selection", len(widget._history.extraSelections()) == 1)
    check("the selection covers exactly the appended '> ' line", _selection_texts(widget) == ["> hello there"])
    fmt = widget._history.extraSelections()[0].format
    check("the selection uses USER_MESSAGE_COLOR", fmt.foreground().color() == module.USER_MESSAGE_COLOR)
    check("the selection is demi-bold", fmt.fontWeight() == module.QFont.Weight.DemiBold)


def test_queued_message_highlights_the_user_line():
    widget = _load_widget_module().build()
    widget._session = _FakeSession()
    widget._busy = True

    widget._prompt_input.setPlainText("queue me")
    widget._on_send_clicked()

    check("queueing a message adds exactly one extra selection", len(widget._history.extraSelections()) == 1)
    check("the selection covers exactly the '[queued] ' line", _selection_texts(widget) == ["[queued] queue me"])


def test_non_user_lines_add_no_selection():
    widget = _load_widget_module().build()

    widget._on_assistant_text("an assistant reply")
    widget._on_tool_use("id1", "Write", {"path": "x"})
    widget._on_tool_result("id1", "ok", False)
    widget._on_session_error("boom")

    check("no extra selections come from non-user lines", widget._history.extraSelections() == [])
    check(
        "the lines still appear as plain text",
        all(
            line in widget._history.toPlainText()
            for line in ["an assistant reply", "[tool] Write(path='x')", "[tool result] ok", "[error] boom"]
        ),
    )


def test_multiline_user_text_gets_a_single_selection():
    widget = _load_widget_module().build()

    widget._append_history("line one\nline two\nline three", is_user=True)

    check(
        "a multi-line user append is covered by exactly one selection spanning the whole text",
        _selection_texts(widget) == ["line one\nline two\nline three"],
    )


def test_history_plain_text_matches_pre_styling_output():
    widget = _load_widget_module().build()
    widget._session = _FakeSession()

    widget._send_now("hi")
    widget._on_assistant_text("hello back")
    widget._on_tool_use("id1", "Write", {"path": "x"})
    widget._on_tool_result("id1", "ok", False)
    widget._busy = True
    widget._prompt_input.setPlainText("queued one")
    widget._on_send_clicked()
    widget._on_session_error("boom")

    check(
        "the styling overlay leaves toPlainText() exactly what the old unstyled code produced",
        widget._history.toPlainText()
        == "\n".join(
            [
                "> hi",
                "hello back",
                "[tool] Write(path='x')",
                "[tool result] ok",
                "[queued] queued one",
                "[error] boom",
            ]
        ),
    )


# -- hover-triggered history reload control (TODO a4c3dec) -----------


def test_reload_text_defaults_to_text_when_omitted():
    widget = _load_widget_module().build()

    widget._append_history("line one\nline two", is_user=True)

    check(
        "an is_user append with no reload_text falls back to the full displayed text",
        widget._history_user_entries and widget._history_user_entries[-1][2] == "line one\nline two",
    )


def test_send_now_records_bare_prompt_as_reload_text():
    widget = _load_widget_module().build()
    widget._session = _FakeSession()

    widget._send_now("hello there")

    check("exactly one history entry is recorded", len(widget._history_user_entries) == 1)
    start, end, reload_text = widget._history_user_entries[0]
    check("the recorded reload_text is the bare prompt, not '> hello there'", reload_text == "hello there")
    check(
        "the recorded (start, end) matches the extra selection's own range",
        (start, end) == (
            widget._history.extraSelections()[0].cursor.selectionStart(),
            widget._history.extraSelections()[0].cursor.selectionEnd(),
        ),
    )


def test_queued_message_records_bare_prompt_as_reload_text():
    widget = _load_widget_module().build()
    widget._session = _FakeSession()
    widget._busy = True

    widget._prompt_input.setPlainText("queue me")
    widget._on_send_clicked()

    check("exactly one history entry is recorded", len(widget._history_user_entries) == 1)
    check(
        "the recorded reload_text is the bare prompt, not '[queued] queue me'",
        widget._history_user_entries[0][2] == "queue me",
    )


def test_non_user_lines_add_no_reload_entry():
    widget = _load_widget_module().build()

    widget._on_assistant_text("an assistant reply")
    widget._on_tool_use("id1", "Write", {"path": "x"})
    widget._on_tool_result("id1", "ok", False)
    widget._on_session_error("boom")

    check("no reload entries come from non-user lines", widget._history_user_entries == [])


def test_update_reload_button_shows_over_a_user_line_and_hides_elsewhere():
    widget = _load_widget_module().build()
    widget._session = _FakeSession()
    widget._send_now("hello there")

    start, _end, _reload_text = widget._history_user_entries[0]
    inside_cursor = QTextCursor(widget._history.document())
    inside_cursor.setPosition(start + 1)
    inside_pos = widget._history.cursorRect(inside_cursor).center()

    widget._update_reload_button(inside_pos)
    check(
        "hovering inside the user line's range records it as hovered",
        widget._hovered_reload_entry == widget._history_user_entries[0],
    )
    # isHidden(), not isVisible(): the latter also depends on the
    # whole ancestor chain actually being shown (widget.show() is
    # never called in this headless suite), so it would read False
    # regardless of the button's own explicit show()/hide() state --
    # isHidden() reflects only that explicit state.
    check("hovering inside the user line's range shows the reload button", not widget._reload_button.isHidden())

    widget._hide_reload_button()
    check("_hide_reload_button clears the hovered entry", widget._hovered_reload_entry is None)
    check("_hide_reload_button hides the button", widget._reload_button.isHidden())


def test_update_reload_button_ignores_non_user_text():
    widget = _load_widget_module().build()
    widget._on_assistant_text("an assistant reply")

    end_cursor = QTextCursor(widget._history.document())
    end_cursor.movePosition(QTextCursor.MoveOperation.End)
    pos = widget._history.cursorRect(end_cursor).center()

    widget._update_reload_button(pos)
    check("hovering over a non-user line never shows the reload button", widget._reload_button.isHidden())
    check("hovering over a non-user line records no hovered entry", widget._hovered_reload_entry is None)


def test_on_reload_clicked_loads_the_bare_prompt_into_prompt_input():
    widget = _load_widget_module().build()
    widget._session = _FakeSession()
    widget._send_now("edit and resend me")
    widget._hovered_reload_entry = widget._history_user_entries[0]

    widget._prompt_input.setPlainText("something typed in the meantime")
    widget._on_reload_clicked()

    check(
        "clicking reload replaces _prompt_input's text with the original bare prompt",
        widget._prompt_input.toPlainText() == "edit and resend me",
    )
    check("clicking reload hides the button afterward", widget._reload_button.isHidden())
    check("clicking reload clears the hovered entry", widget._hovered_reload_entry is None)


def test_on_reload_clicked_is_a_no_op_with_no_hovered_entry():
    widget = _load_widget_module().build()
    widget._prompt_input.setPlainText("untouched")

    widget._on_reload_clicked()

    check(
        "clicking reload with nothing hovered leaves _prompt_input untouched",
        widget._prompt_input.toPlainText() == "untouched",
    )


def test_reload_button_parented_to_history_viewport_only():
    widget = _load_widget_module().build()

    check(
        "the reload button's parent is _history's own viewport, not _prompt_input or the widget itself",
        widget._reload_button.parent() is widget._history.viewport(),
    )


test_widget_json_is_well_formed()
test_window_wiring()
test_permission_mode_combo_present_and_defaults_to_default()
test_start_session_passes_the_selected_permission_mode()
test_changing_the_combo_calls_set_permission_mode_live()
test_set_permission_mode_is_a_real_no_op_before_start()
test_prompt_input_is_a_wrapping_multiline_box()
test_plain_enter_sends_without_inserting_a_newline()
test_shift_enter_inserts_a_newline_without_sending()
test_on_send_clicked_reads_and_clears_the_multiline_box()
test_mic_transcription_sets_text_via_setplaintext()
test_send_now_highlights_the_user_line()
test_queued_message_highlights_the_user_line()
test_non_user_lines_add_no_selection()
test_multiline_user_text_gets_a_single_selection()
test_history_plain_text_matches_pre_styling_output()
test_reload_text_defaults_to_text_when_omitted()
test_send_now_records_bare_prompt_as_reload_text()
test_queued_message_records_bare_prompt_as_reload_text()
test_non_user_lines_add_no_reload_entry()
test_update_reload_button_shows_over_a_user_line_and_hides_elsewhere()
test_update_reload_button_ignores_non_user_text()
test_on_reload_clicked_loads_the_bare_prompt_into_prompt_input()
test_on_reload_clicked_is_a_no_op_with_no_hovered_entry()
test_reload_button_parented_to_history_viewport_only()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
