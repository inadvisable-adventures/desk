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


test_prompt_says_follow_links_only_as_needed_not_unconditionally()
print("ALL PASS")
