import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")
sys.path.insert(0, "widgets/claude")

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

import widget as claude_mod  # noqa: E402


def test_prompt_says_follow_links_only_as_needed_not_unconditionally():
    prompt = claude_mod.CLAUDE_WIDGET_PROMPT
    assert "only" in prompt and "if you" in prompt, "should state a conditional, not unconditional, instruction"
    assert "lightning round" in prompt.lower(), "should give the concrete example from the request"
    assert "not unconditionally" in prompt
    # The old, corrected wording -- "follow those links too" -- must be gone.
    assert "follow those links too" not in prompt
    print("CLAUDE_WIDGET_PROMPT: tells the agent to follow tempui doc links only as needed, with an example: PASS")


def _load_claude_desk_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("claude_desk_widget", "widgets/claude_desk/widget.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_prompts_say_reading_docs_is_orientation_only():
    # TODO b78e7b8: reading the docs must not read as a request to start working.
    desk_mod = _load_claude_desk_module()
    for name, prompt in (("claude", claude_mod.CLAUDE_WIDGET_PROMPT), ("claude_desk", desk_mod.CLAUDE_WIDGET_PROMPT)):
        flat = " ".join(prompt.split())
        assert "orientation only" in flat, name
        assert "not itself a task" in flat, name
        assert "unless the message from the user separately asks for it" in flat, name
    # Only the PTY widget passes its prompt through a shell command line.
    assert "\n" not in claude_mod.CLAUDE_WIDGET_PROMPT and "'" not in claude_mod.CLAUDE_WIDGET_PROMPT
    # The trailing desk_get_next_todo_item sentence is now conditional on the user asking for TODO work.
    flat = " ".join(desk_mod.CLAUDE_WIDGET_PROMPT.split())
    assert "when the user has asked you to work on TODO items, check desk_get_next_todo_item" in flat
    assert "In particular, check desk_get_next_todo_item" not in flat
    print("both CLAUDE_WIDGET_PROMPTs: reading docs is orientation only, TODO check is conditional: PASS")


test_prompt_says_follow_links_only_as_needed_not_unconditionally()
test_prompts_say_reading_docs_is_orientation_only()
print("ALL PASS")
