"""Verifies TODO `10b4d7d`: top-level tool results (real-shaped
UserMessages) reach the history, content is flattened, images stay behind a
clickable [image] placeholder. No live API/GUI."""

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

import claude_agent_sdk as sdk  # noqa: E402

from desk.claude_session import ClaudeSession  # noqa: E402
from desk.claude_tool_result import IMAGE_SENTINEL, NO_OUTPUT_TEXT, flatten_tool_result, plain, save_image  # noqa: E402
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

    spec = importlib.util.spec_from_file_location("tr_check", REPO_ROOT / "widgets" / "claude_desk" / "widget.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


module = _module()
PNG = b"\x89PNG\r\n\x1a\nfakebytes"
B64 = base64.b64encode(PNG).decode()


class _FakeSession:
    def send_prompt(self, t):
        pass

    def stop(self):
        pass


def image_block(data=B64, media="image/png"):
    return {"type": "image", "source": {"type": "base64", "media_type": media, "data": data}}


# -- flattening ---------------------------------------------------------------------


def test_flatten_cases():
    check("None -> (no output)", flatten_tool_result(None) == (NO_OUTPUT_TEXT, []))
    check("empty string -> (no output)", flatten_tool_result("")[0] == NO_OUTPUT_TEXT)
    check("empty list -> (no output)", flatten_tool_result([])[0] == NO_OUTPUT_TEXT)
    check("a plain string is verbatim", flatten_tool_result("hello") == ("hello", []))
    text, images = flatten_tool_result([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}])
    check("text blocks are joined, not repr'd", text == "a\nb" and images == [])
    text, images = flatten_tool_result([{"type": "text", "text": "before"}, image_block(), {"type": "text", "text": "after"}])
    check("an image becomes one sentinel in order, text kept", text == f"before\n{IMAGE_SENTINEL}\nafter")
    check("the original bytes and type are kept", len(images) == 1 and images[0].data == PNG and images[0].media_type == "image/png")
    check("plain() shows the readable placeholder", plain(text) == "before\n[image]\nafter")
    text, images = flatten_tool_result([{"type": "text", "text": "literal [image] text"}])
    check("a literal '[image]' in the text is not a placeholder", IMAGE_SENTINEL not in text and images == [])
    text, images = flatten_tool_result([{"type": "image", "source": {"type": "url", "url": "http://x/y.png"}}])
    check("a url image is named, never fetched, no attachment", text == "[image: http://x/y.png]" and images == [])
    text, images = flatten_tool_result([image_block(data="!!notbase64!!")])
    check("undecodable data still yields a placeholder without raising", IMAGE_SENTINEL in text and len(images) == 1)
    check("an unknown block type is named", flatten_tool_result([{"type": "weird"}])[0] == "[weird]")


def test_save_image_is_idempotent_and_content_addressed():
    from desk.claude_tool_result import ImageAttachment

    with tempfile.TemporaryDirectory() as d:
        a = save_image(Path(d) / "x", ImageAttachment(data=PNG))
        b = save_image(Path(d) / "x", ImageAttachment(data=PNG))
        check("same bytes -> same path with the right extension", a == b and a.suffix == ".png" and a.read_bytes() == PNG)
        check("a url attachment has nothing to save", save_image(Path(d), ImageAttachment(url="http://x")) is None)


# -- session ---------------------------------------------------------------------------


def test_top_level_user_message_tool_results_reach_the_signal():
    session = ClaudeSession()
    events, results = [], []
    session.session_event.connect(events.append)
    session.tool_result.connect(lambda *a: results.append(a))
    msg = sdk.UserMessage(
        content=[sdk.ToolResultBlock(tool_use_id="u1", content="out"), sdk.ToolResultBlock(tool_use_id="u2", content=[{"type": "text", "text": "x"}], is_error=True)]
    )
    session._handle_message(msg, 3, True)
    check("legacy signal fires per block with real-shaped content", results == [("u1", "out", False), ("u2", [{"type": "text", "text": "x"}], True)])
    check("matching session_events with the turn id", [(e["kind"], e["turn_id"], e["data"]["tool_use_id"]) for e in events] == [("tool_result", 3, "u1"), ("tool_result", 3, "u2")])
    check("no parent key at top level", all("parent_tool_use_id" not in e["data"] for e in events))
    session._handle_message(sdk.UserMessage(content="just text"), 3, True)
    check("a text-only UserMessage is still ignored", len(results) == 2)


def test_parsed_wire_message_end_to_end():
    from claude_agent_sdk._internal.message_parser import parse_message

    wire = {
        "type": "user",
        "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": [{"type": "text", "text": "ls output"}]}]},
        "parent_tool_use_id": None,
    }
    session = ClaudeSession()
    results = []
    session.tool_result.connect(lambda *a: results.append(a))
    session._handle_message(parse_message(wire), 1, True)
    check("a message parsed from the real wire shape reaches tool_result", results == [("toolu_1", [{"type": "text", "text": "ls output"}], False)])


# -- widget ------------------------------------------------------------------------------


def make_widget():
    widget = module.build()
    widget._session = _FakeSession()
    return widget


def test_widget_renders_flattened_results():
    widget = make_widget()
    widget._on_tool_result("a", [{"type": "text", "text": "line"}], False)
    widget._on_tool_result("b", None, True)
    widget._on_tool_result("c", "ok", False)
    texts = [(e.meta.kind, e.text) for e in widget._history.entries()]
    check("list content is joined, None is (no output), strings verbatim", texts == [("tool_result", "line"), ("tool_error", NO_OUTPUT_TEXT), ("tool_result", "ok")])


def test_image_entry_renders_a_link_and_keeps_the_image():
    widget = make_widget()
    widget._on_tool_result("a", [{"type": "text", "text": "shot <1>"}, image_block()], False)
    entry = widget._history.entries()[0]
    check("the image is kept on the entry", len(entry.images) == 1 and entry.images[0].data == PNG)
    body = entry._body.text()
    check("the body is rich text with a link to image 0", 'href="image:0"' in body and "[image]" in body)
    check("surrounding text is escaped", "shot &lt;1&gt;" in body)
    check("toPlainText shows the readable placeholder, never the sentinel", "[image]" in widget._history.toPlainText() and IMAGE_SENTINEL not in widget._history.toPlainText())
    plain_entry = make_widget()
    plain_entry._on_tool_result("a", "no images", False)
    check("entries without images stay plain text", plain_entry._history.entries()[0]._body.text() == "no images")


def test_collapsed_preview_keeps_cut_off_images_reachable():
    widget = make_widget()
    lines = [{"type": "text", "text": "\n".join(f"l{i}" for i in range(10))}, image_block()]
    widget._on_tool_result("a", lines, False)
    entry = widget._history.entries()[0]
    check("a long result with a trailing image is collapsed", entry.collapsible and not entry.expanded)
    check("the collapsed body still offers the cut-off image's link", 'href="image:0"' in entry._body.text() and "l9" not in entry._body.text())
    entry.toggle()
    check("expanded, the link sits inline in the full text", 'href="image:0"' in entry._body.text() and "l9" in entry._body.text() and entry._body.text().count("href") == 1)


def test_clicking_the_link_saves_and_opens_the_image():
    widget = make_widget()
    widget._session_id = "sess-1"
    widget._on_tool_result("a", [image_block()], False)
    entry = widget._history.entries()[0]
    opened = []
    previous = current_context.get_centered_widget_opener()
    previous_dir = current_context.get_current_desk_directory()
    with tempfile.TemporaryDirectory() as d:
        current_context.set_current_desk_directory(Path(d))
        current_context.set_centered_widget_opener(lambda wid, path: opened.append((wid, path)))
        try:
            entry._body.linkActivated.emit("image:0")
            check("opens the image viewer on a saved file", len(opened) == 1 and opened[0][0] == "image_viewer")
            path = opened[0][1]
            check("the file holds the original bytes under .desk_temp, per session", path.read_bytes() == PNG and ".desk_temp" in str(path) and "sess-1" in str(path))
            entry._body.linkActivated.emit("image:7")
            entry._body.linkActivated.emit("image:abc")
            entry._body.linkActivated.emit("http://elsewhere")
            check("bad or foreign links are ignored", len(opened) == 1)
        finally:
            if previous is not None:
                current_context.set_centered_widget_opener(previous)
            if previous_dir is not None:
                current_context.set_current_desk_directory(previous_dir)


def test_sub_agent_results_use_the_flattener():
    widget = make_widget()
    widget._on_task_event("t1", {"description": "d", "status": "running", "tool_use_id": "toolu_task"})
    ev = {"seq": 1, "ts": 1.0, "turn_id": 1, "solicited": True, "kind": "tool_result", "data": {"tool_use_id": "z", "content": [{"type": "text", "text": "hi"}, image_block()], "is_error": False, "parent_tool_use_id": "toolu_task"}}
    widget._on_session_event(ev)
    check("a routed result is flattened, image degraded to [image]", widget._task_logs["t1"][-1]["text"] == "hi\n[image]")


test_flatten_cases()
test_save_image_is_idempotent_and_content_addressed()
test_top_level_user_message_tool_results_reach_the_signal()
test_parsed_wire_message_end_to_end()
test_widget_renders_flattened_results()
test_image_entry_renders_a_link_and_keeps_the_image()
test_collapsed_preview_keeps_cut_off_images_reachable()
test_clicking_the_link_saves_and_opens_the_image()
test_sub_agent_results_use_the_flattener()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
