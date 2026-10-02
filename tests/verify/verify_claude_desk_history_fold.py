"""Verifies TODOs `ed5c62f` (tool-invocation folding) and `dffb428`
(generalized to every entry type) in the Claude (Desk) widget's
structured history. See plans/claude-desk-history-fold.md and
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

from desk.claude_history_view import collapse_preview  # noqa: E402


def test_collapse_preview_rules():
    check("short single-line tool text is never collapsed", collapse_preview("tool", "short") is None)
    check("long single-line tool text collapses to a capped preview", collapse_preview("tool", LONG_SINGLE_LINE) == ("x" * 80) + "…")
    check("a short first line with more lines after still collapses", collapse_preview("tool_result", "fits\nmore") == "fits…")
    check("short assistant text is never collapsed", collapse_preview("assistant", "hello\nthere") is None)
    long_reply = "\n".join(f"line {i}" for i in range(10))
    preview = collapse_preview("assistant", long_reply)
    check("a long multi-line assistant reply collapses to its first 3 lines", preview == "line 0\nline 1\nline 2…")
    check("a very long single-line assistant reply collapses too", collapse_preview("assistant", "y" * 1000) is not None)


def test_short_tool_entries_are_not_collapsible():
    widget = module.build()
    widget._on_tool_use("id1", "Write", {"path": "x"})
    widget._on_tool_result("id1", "ok", False)
    entries = widget._history.entries()
    check("short tool call/result entries have no fold affordance", not any(e.collapsible for e in entries))
    check("they read exactly as before", widget._history.toPlainText() == "[tool] Write(path='x')\n[tool result] ok")


def test_long_tool_entries_start_collapsed_and_keep_full_text():
    for is_error, kind in [(False, "tool_result"), (True, "tool_error")]:
        widget = module.build()
        widget._on_tool_result("id1", LONG_CONTENT, is_error)
        entry = widget._history.entries()[0]
        check(f"{kind}: kind recorded", entry.meta.kind == kind)
        check(f"{kind}: collapsible and starts collapsed", entry.collapsible and not entry.expanded)
        check(f"{kind}: collapsed body shows only the first line", "line two" not in entry.shown_text and entry.shown_text.endswith("…"))
        check(f"{kind}: full text still present in toPlainText", "line two follows" in widget._history.toPlainText())
    widget = module.build()
    widget._on_tool_use("id1", "Write", {"content": LONG_SINGLE_LINE})
    entry = widget._history.entries()[0]
    check("long tool call starts collapsed", entry.collapsible and not entry.expanded)
    check("its collapsed body hides the full args", LONG_SINGLE_LINE not in entry.shown_text)


def test_toggle_expands_and_collapses():
    widget = module.build()
    widget._on_tool_use("id1", "Write", {"content": LONG_SINGLE_LINE})
    entry = widget._history.entries()[0]
    entry._toggle.click()
    check("clicking the header expands", entry.expanded and LONG_SINGLE_LINE in entry.shown_text)
    check("the arrow reflects the expanded state", entry._toggle.text().startswith("▾"))
    entry._toggle.click()
    check("clicking again collapses", not entry.expanded and LONG_SINGLE_LINE not in entry.shown_text)
    check("the arrow reflects the collapsed state", entry._toggle.text().startswith("▸"))


def test_long_assistant_replies_collapse_by_default():
    widget = module.build()
    reply = "\n".join(f"paragraph {i}" for i in range(12))
    widget._on_assistant_text(reply)
    widget._on_assistant_text("short reply")
    long_entry, short_entry = widget._history.entries()
    check("a long reply is collapsible and starts collapsed", long_entry.collapsible and not long_entry.expanded)
    check("collapsed shows only a couple of lines", "paragraph 5" not in long_entry.shown_text and "paragraph 0" in long_entry.shown_text)
    check("a short reply is shown in full with no fold affordance", not short_entry.collapsible and short_entry.shown_text == "short reply")
    check("expanding shows everything", (long_entry.toggle(), reply == long_entry.shown_text)[1])


def test_toggling_never_changes_other_entries():
    widget = module.build()
    widget._on_tool_use("id1", "Write", {"content": LONG_SINGLE_LINE})
    widget._on_tool_result("id2", LONG_CONTENT, False)
    first, second = widget._history.entries()
    first.toggle()
    check("toggling one entry leaves the other collapsed", first.expanded and not second.expanded)


test_collapse_preview_rules()
test_short_tool_entries_are_not_collapsible()
test_long_tool_entries_start_collapsed_and_keep_full_text()
test_toggle_expands_and_collapses()
test_long_assistant_replies_collapse_by_default()
test_toggling_never_changes_other_entries()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
