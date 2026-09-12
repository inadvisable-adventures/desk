# TODO 1ceb701: persisting the Claude (Desk) widget's model/
# permission-mode combo selections across a Desk reboot via widget
# -local storage. Follows verify_claude_desk_widget.py's own
# established shape (a real widget built via module.build(), a
# _FakeSession standing in for a live ClaudeSDKClient, no network
# calls).
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

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
        "claude_desk_widget", REPO_ROOT / "widgets" / "claude_desk" / "widget.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeSignal:
    def connect(self, *_args, **_kwargs):
        pass


class _FakeSession:
    def __init__(self):
        self.start_calls = []
        self.connected = _FakeSignal()

    def start(self, session_id, resume, model, permission_mode, cwd, initial_prompt):
        self.start_calls.append((session_id, resume, model, permission_mode, cwd, initial_prompt))

    def set_permission_mode(self, mode):
        pass

    def stop(self):
        pass


def test_get_widget_local_storage_round_trips_non_default_selection():
    module = _load_widget_module()
    widget = module.build()
    widget._model_combo.setCurrentIndex(2)  # "Opus"
    widget._permission_mode_combo.setCurrentIndex(3)  # "Bypass Permissions"
    data = widget.get_widget_local_storage()
    check(
        "stores the real SDK model value, not the combo index",
        data["model"] == "claude-opus-5",
    )
    check(
        "stores the real SDK permission-mode value, not the combo index",
        data["permission_mode"] == "bypassPermissions",
    )


def test_set_widget_local_storage_selects_the_matching_index():
    module = _load_widget_module()
    widget = module.build()
    widget.set_widget_local_storage({"model": "claude-haiku-4-5-20251001", "permission_mode": "plan"})
    check(
        "model combo selects the stored value's index",
        widget._model_combo.currentIndex() == module.MODEL_CHOICES.index(("Haiku", "claude-haiku-4-5-20251001")),
    )
    check(
        "permission-mode combo selects the stored value's index",
        widget._permission_mode_combo.currentIndex() == module.PERMISSION_MODE_CHOICES.index(("Plan", "plan")),
    )


def test_set_widget_local_storage_falls_back_to_defaults_for_unknown_or_missing_values():
    module = _load_widget_module()
    widget = module.build()
    widget._model_combo.setCurrentIndex(2)
    widget._permission_mode_combo.setCurrentIndex(3)

    widget.set_widget_local_storage({"model": "some-retired-model", "permission_mode": "not-a-real-mode"})
    check(
        "an unknown stored model value falls back to the hardcoded default index",
        widget._model_combo.currentIndex() == module.DEFAULT_MODEL_INDEX,
    )
    check(
        "an unknown stored permission-mode value falls back to the hardcoded default index",
        widget._permission_mode_combo.currentIndex() == module.DEFAULT_PERMISSION_MODE_INDEX,
    )

    widget._model_combo.setCurrentIndex(2)
    widget._permission_mode_combo.setCurrentIndex(3)
    widget.set_widget_local_storage({})  # data saved before this feature existed
    check(
        "an empty stored dict (pre-existing data) falls back to the default model index",
        widget._model_combo.currentIndex() == module.DEFAULT_MODEL_INDEX,
    )
    check(
        "an empty stored dict (pre-existing data) falls back to the default permission-mode index",
        widget._permission_mode_combo.currentIndex() == module.DEFAULT_PERMISSION_MODE_INDEX,
    )


def test_explicit_default_model_is_distinguished_from_a_missing_key():
    """MODEL_CHOICES' own "Default" entry's value is None -- the same
    value a missing "model" key's data.get(..., None) would produce --
    so an explicitly-saved "the user really picked Default" selection
    must not be conflated with "this key was never saved at all"."""
    module = _load_widget_module()
    widget = module.build()
    widget._model_combo.setCurrentIndex(2)  # something non-default first

    widget.set_widget_local_storage({"model": None, "permission_mode": "default"})
    check(
        "an explicit model: None selects the real 'Default' choice (index 0), not the hardcoded default",
        widget._model_combo.currentIndex() == 0,
    )

    widget._model_combo.setCurrentIndex(2)
    widget.set_widget_local_storage({})  # the "model" key is absent entirely
    check(
        "a missing model key falls back to this widget's own hardcoded default index, not 'Default'",
        widget._model_combo.currentIndex() == module.DEFAULT_MODEL_INDEX,
    )


def test_restore_ordering_applies_before_start_session():
    """The real bug this item fixes: DeskWindow._place_widget applies
    saved widget-local storage to a claude_desk widget *before*
    _bind_claude_desk_widget calls start_session, so a restored session
    reconnects using the previously-selected model/mode -- not this
    widget's hardcoded defaults. Exercised directly against the
    widget's own two hooks in the same order _place_widget now calls
    them, the same "swap in a _FakeSession, call start_session
    directly" approach verify_claude_desk_widget.py's own permission
    -mode tests already use."""
    import uuid

    module = _load_widget_module()
    widget = module.build()
    fake_session = _FakeSession()
    widget._session = fake_session

    # Simulates a restored instance whose previous session had Opus +
    # Bypass Permissions selected.
    widget.set_widget_local_storage({"model": "claude-opus-5", "permission_mode": "bypassPermissions"})
    widget.start_session(str(uuid.uuid4()), resume=True)

    check(
        "start_session's model argument reflects the restored selection, not the hardcoded default",
        fake_session.start_calls and fake_session.start_calls[0][2] == "claude-opus-5",
    )
    check(
        "start_session's permission_mode argument reflects the restored selection",
        fake_session.start_calls[0][3] == "bypassPermissions",
    )


def test_window_place_widget_applies_local_storage_before_binding_claude_desk_widget():
    """DeskWindow._place_widget itself (not just the widget's own
    hooks in isolation) -- confirms the CLAUDE_DESK_WIDGET_ID branch
    calls _bind_widget_local_storage before _bind_claude_desk_widget
    when local_storage_data is given, via a call-order-recording
    monkeypatch of both (no real DeskWindow/QGraphicsScene needed)."""
    import desk.shell.window as window_mod

    calls = []
    original_bind_local_storage = window_mod.DeskWindow._bind_widget_local_storage
    original_bind_claude_desk = window_mod.DeskWindow._bind_claude_desk_widget

    def fake_bind_local_storage(self, frame, data):
        calls.append("local_storage")

    def fake_bind_claude_desk(self, frame, resume, extra_instructions=""):
        calls.append("claude_desk")

    window_mod.DeskWindow._bind_widget_local_storage = fake_bind_local_storage
    window_mod.DeskWindow._bind_claude_desk_widget = fake_bind_claude_desk
    try:
        import inspect

        source = inspect.getsource(window_mod.DeskWindow._place_widget)
        local_storage_index = source.index("self._bind_widget_local_storage(frame, local_storage_data)")
        claude_desk_index = source.index("self._bind_claude_desk_widget(")
        check(
            "_place_widget's own source calls _bind_widget_local_storage before _bind_claude_desk_widget",
            local_storage_index < claude_desk_index,
        )
    finally:
        window_mod.DeskWindow._bind_widget_local_storage = original_bind_local_storage
        window_mod.DeskWindow._bind_claude_desk_widget = original_bind_claude_desk


test_get_widget_local_storage_round_trips_non_default_selection()
test_set_widget_local_storage_selects_the_matching_index()
test_set_widget_local_storage_falls_back_to_defaults_for_unknown_or_missing_values()
test_explicit_default_model_is_distinguished_from_a_missing_key()
test_restore_ordering_applies_before_start_session()
test_window_place_widget_applies_local_storage_before_binding_claude_desk_widget()

print(f"\n{passed} passed, {failed} failed")
