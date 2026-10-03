"""Verifies TODO `6ff3be8`: the hover "Markdown View" button on agent-turn
history entries and the turn -> markdown rendering. No live API/GUI."""

import base64
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.window  # noqa: E402,F401

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from desk.claude_history_view import HistoryView  # noqa: E402
from desk.claude_tool_result import IMAGE_SENTINEL, ImageAttachment  # noqa: E402
from desk.claude_turn_markdown import render_turn  # noqa: E402
from desk.shell import current_context  # noqa: E402

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

    spec = importlib.util.spec_from_file_location("md_check", REPO_ROOT / "widgets" / "claude_desk" / "widget.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


module = _module()
PNG = b"\x89PNG\r\n\x1a\nbytes"


class _FakeSession:
    def send_prompt(self, t):
        pass

    def stop(self):
        pass


def entry_set(kinds):
    """Entries built through a real HistoryView."""
    view = HistoryView()
    out = []
    for kind, text, turn, extra in kinds:
        out.append(view.add_entry(kind, text, turn_id=turn, ts=1_700_000_000.0, **extra))
    return out


# -- renderer ----------------------------------------------------------------------


def test_render_structure_and_order():
    entries = entry_set(
        [
            ("user", "please list", 4, {}),
            ("assistant", "Sure, **listing**.", 4, {}),
            ("tool", "Bash(command='ls')", 4, {}),
            ("tool_result", "a.txt\nb.txt", 4, {}),
            ("tool_error", "boom", 4, {}),
            ("assistant", "Done.", 4, {}),
        ]
    )
    md = render_turn(entries, lambda i: "x.png").markdown
    check("heading names the turn", md.startswith("# Turn 4\n"))
    check("prompt is a blockquote", "> please list" in md)
    check("assistant text is passed through as markdown", "Sure, **listing**." in md)
    check("tool call and result are fenced under labels", "**Tool**\n\n```\nBash(command='ls')\n```" in md and "**Result**\n\n```\na.txt\nb.txt\n```" in md)
    check("errors are labelled", "**Error**\n\n```\nboom\n```" in md)
    order = [md.index(s) for s in ("> please list", "Sure,", "**Tool**", "**Result**", "boom", "Done.")]
    check("entries keep their order", order == sorted(order))


def test_fence_survives_backticks():
    (entry,) = entry_set([("tool_result", "code:\n```py\nx=1\n```", 1, {})])
    md = render_turn([entry], lambda i: "x").markdown
    check("the fence is longer than any backtick run in the text", "````\ncode:\n```py\nx=1\n```\n````" in md)


def test_images_are_real_markdown_images_between_fences():
    attachment = ImageAttachment(data=PNG)
    (entry,) = entry_set([("tool_result", f"before\n{IMAGE_SENTINEL}\nafter", 1, {"images": [attachment]})])
    names = []
    rendered = render_turn([entry], lambda image: names.append(image) or "abc.png")
    md = rendered.markdown
    check("the image is a relative markdown image, outside any fence", "![image](images/abc.png)" in md)
    check("text before and after is fenced separately around it", md.index("before") < md.index("![image]") < md.index("after"))
    check("the attachment is handed back to be written", rendered.images == {"abc.png": attachment} and names == [attachment])
    (bare,) = entry_set([("tool_result", f"{IMAGE_SENTINEL}", 1, {"images": [ImageAttachment(url="http://x")]})])
    check("an image with no bytes is marked unavailable, not a broken link", "image unavailable" in render_turn([bare], lambda i: "x").markdown)


# -- button ------------------------------------------------------------------------------


def test_button_only_on_assistant_entries_and_only_on_hover():
    view = HistoryView()
    calls = []
    view.on_markdown = calls.append
    assistant = view.add_entry("assistant", "hi")
    tool = view.add_entry("tool", "Read()")
    user = view.add_entry("user", "q", reload_text="q")
    check("hidden until hover", assistant._markdown_button.isHidden())
    assistant.enterEvent(None)
    check("hover reveals it on an assistant entry", not assistant._markdown_button.isHidden())
    assistant._markdown_button.click()
    check("clicking passes the entry back", calls == [assistant])
    assistant.leaveEvent(None)
    check("leaving hides it", assistant._markdown_button.isHidden())
    tool.enterEvent(None)
    user.enterEvent(None)
    check("tool and user entries never show it", tool._markdown_button.isHidden() and user._markdown_button.isHidden())
    check("the header puts it after the stretch, so it is right-aligned", assistant.layout().itemAt(0).layout().indexOf(assistant._markdown_button) > assistant.layout().itemAt(0).layout().indexOf(assistant._meta_label))


# -- widget -------------------------------------------------------------------------------


def test_widget_renders_the_whole_turn_and_opens_the_markdown_widget():
    widget = module.build()
    widget._session = _FakeSession()
    widget._session_id = "sess-9"
    ev = lambda kind, turn: {"seq": 1, "ts": 1.0, "turn_id": turn, "solicited": True, "kind": kind, "data": {}}
    widget._send_now("what is here")
    widget._on_session_event(ev("turn_started", 6))
    widget._on_session_event(ev("assistant_text", 6))
    widget._on_assistant_text("Let me look.")
    widget._on_session_event(ev("tool_use", 6))
    widget._on_tool_use("t1", "Read", {"path": "a"})
    b64 = base64.b64encode(PNG).decode()
    widget._on_session_event(ev("tool_result", 6))
    widget._on_tool_result("t1", [{"type": "text", "text": "file"}, {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}}], False)
    # A different turn that must not leak in.
    widget._on_session_event(ev("turn_started", 7))
    widget._on_session_event(ev("assistant_text", 7))
    widget._on_assistant_text("Other turn.")

    first_assistant = [e for e in widget._history.entries() if e.meta.kind == "assistant"][0]
    opened = []
    previous = current_context.get_centered_widget_opener()
    previous_dir = current_context.get_current_desk_directory()
    with tempfile.TemporaryDirectory() as d:
        current_context.set_current_desk_directory(Path(d))
        current_context.set_centered_widget_opener(lambda wid, path: opened.append((wid, path)))
        try:
            first_assistant._markdown_button.click()
            check("opens the markdown widget on a file", len(opened) == 1 and opened[0][0] == "markdown")
            path = opened[0][1]
            md = path.read_text(encoding="utf-8")
            check("file lives under .desk_temp/claude_desk_turns/<session>/", ".desk_temp" in str(path) and "claude_desk_turns" in str(path) and "sess-9" in str(path) and path.name == "turn-6.md")
            check("the whole turn is in it: prompt, text, tool, result", all(s in md for s in ("what is here", "Let me look.", "Read(path='a')", "file")))
            check("another turn's entries are not", "Other turn." not in md)
            images = list((path.parent / "images").glob("*.png"))
            check("the image was written beside it and is referenced relatively", len(images) == 1 and images[0].read_bytes() == PNG and f"![image](images/{images[0].name})" in md)
            md_module = __import__("importlib.util").util
            spec = md_module.spec_from_file_location("real_markdown", REPO_ROOT / "widgets" / "markdown" / "widget.py")
            real = md_module.module_from_spec(spec)
            spec.loader.exec_module(real)
            viewer = real.build()
            viewer.set_file(path)
            check("the real Markdown widget loads the generated file without error", True)
            first_assistant._markdown_button.click()
            check("re-clicking overwrites the same file", len(opened) == 2 and opened[1][1] == path and len(list(path.parent.glob("*.md"))) == 1)
        finally:
            if previous is not None:
                current_context.set_centered_widget_opener(previous)
            if previous_dir is not None:
                current_context.set_current_desk_directory(previous_dir)


def test_entry_without_a_turn_id_renders_alone():
    widget = module.build()
    widget._session = _FakeSession()
    widget._on_assistant_text("lonely")
    widget._on_assistant_text("neighbor")
    entry = widget._history.entries()[0]
    check("with no turn id, only the clicked entry", widget._turn_entries(entry) == [entry])


test_render_structure_and_order()
test_fence_survives_backticks()
test_images_are_real_markdown_images_between_fences()
test_button_only_on_assistant_entries_and_only_on_hover()
test_widget_renders_the_whole_turn_and_opens_the_markdown_widget()
test_entry_without_a_turn_id_renders_alone()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
