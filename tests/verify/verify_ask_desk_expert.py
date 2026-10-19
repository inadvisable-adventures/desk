"""TODO c4ef727: desk_ask_desk_expert MCP tool + its Claude (Desk) session prompt."""
import asyncio
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from desk.shell import current_context  # noqa: E402
from desk.shell.desk_mcp_server import _TOOLS, _ask_desk_expert  # noqa: E402
from desk.shell.window import DeskWindow  # noqa: E402

passed = failed = 0


def check(name, ok):
    global passed, failed
    if ok:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


spec = importlib.util.spec_from_file_location("claude_desk_widget", REPO_ROOT / "widgets/claude_desk/widget.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

# ---- prompt pieces ----
check("CLAUDE_WIDGET_PROMPT unchanged composition", mod.CLAUDE_WIDGET_PROMPT == mod._PROMPT_INTRO + mod._PROMPT_ORIENTATION_ONLY + mod._PROMPT_TOOLS)

with tempfile.TemporaryDirectory() as d:
    directory = Path(d)
    (directory / "development-process.md").write_text("x")
    current_context.set_current_desk_directory(directory)
    check("dev-process pointer drops the don't-start-working caveat when answering",
          "orientation only" not in mod._development_process_instruction(True) and str(directory / "development-process.md") in mod._development_process_instruction(True))
    check("default dev-process pointer unchanged", "orientation only" in mod._development_process_instruction())

    captured = {}

    class _Cap:
        def __init__(self, v=0):
            self.v = v

        def currentIndex(self):
            return self.v

        def setText(self, t):
            pass

    class _Sess:
        class connected:
            @staticmethod
            def connect(f):
                pass

        def start(self, *a):
            captured["prompt"] = a[-1]

    class _Fake:
        _model_combo = _Cap()
        _permission_mode_combo = _Cap()
        _status_label = _Cap()
        _session = _Sess()

        def _set_busy(self, b):
            pass

        def _add_user_entry(self, a, b):
            pass

        def _finish_busy_period(self, *a):
            pass

    mod.ClaudeDeskWidget.start_session(_Fake(), "sid", False, "EXTRA-QUESTION", answer_question=True)
    p = captured["prompt"]
    check("answer mode: no 'orientation only' wording", "orientation only" not in p)
    check("answer mode: still has the in-Desk intro and tools", "You are running inside of Desk" in p and "desk_git_commit" in p)
    check("answer mode: extra instructions appended", p.endswith("EXTRA-QUESTION"))
    mod.ClaudeDeskWidget.start_session(_Fake(), "sid", False, "EXTRA", answer_question=False)
    check("default mode keeps 'orientation only'", "orientation only" in captured["prompt"])

    # ---- DeskWindow.ask_desk_expert via the real methods ----
    class _FakeFrame:
        instance_id = "exp-1"

    class _FakeWin:
        placed = []

        def __init__(self, with_widget=True):
            self._widgets = {"claude_desk": type("W", (), {"default_size": (400, 300)})()} if with_widget else {}
            self.view = type("V", (), {
                "mapToScene": lambda s, p: type("P", (), {"x": lambda s: 1.0, "y": lambda s: 2.0})(),
                "viewport": lambda s: type("VP", (), {"rect": lambda s: type("R", (), {"center": lambda s: None})()})(),
            })()

        def _place_widget(self, *a, **k):
            self.placed.append((a, k))
            return _FakeFrame()

    _FakeWin._write_claude_instructions_file = DeskWindow._write_claude_instructions_file
    _FakeWin._build_desk_expert_instructions = DeskWindow._build_desk_expert_instructions
    _FakeWin.ask_desk_expert = DeskWindow.ask_desk_expert

    win = _FakeWin()
    iid = win.ask_desk_expert("Why did desk_install_job time out?")
    check("returns the new widget's instance_id", iid == "exp-1")
    args, kwargs = win.placed[0]
    check("placed a claude_desk widget in answer mode", args[0] == "claude_desk" and kwargs["claude_answer_question"] is True)
    instructions_path = Path(kwargs["claude_extra_instructions"].split(" Read the file at ")[1].split(" now")[0])
    body = instructions_path.read_text()
    check("question included verbatim, tagged as from another agent", "Why did desk_install_job time out?" in body and "Another agent, running in this same session of Desk" in body)
    check("points at Desk's source checkout and docs", str(REPO_ROOT) in body and "design-docs" in body)
    check("encourages diagnostic python widgets", 'kind: "python"' in body)
    check("tells it to answer, with no 'wait for the user' wording", "answer it" in body and "wait for" not in body.lower())

    try:
        _FakeWin(with_widget=False).ask_desk_expert("q")
        check("missing widget kind raises ValueError", False)
    except ValueError:
        check("missing widget kind raises ValueError", True)

    # ---- MCP tool handler ----
    check("tool registered", _ask_desk_expert in _TOOLS and _ask_desk_expert.name == "desk_ask_desk_expert")
    calls = []
    window = type("W", (), {"ask_desk_expert": lambda s, q: calls.append(q) or "iid-9"})()
    current_context.set_main_window(window)
    current_context.set_gui_thread_caller(lambda fn: fn())
    res = asyncio.run(_ask_desk_expert.handler({"question": "  hello  "}))
    check("handler passes the stripped question and reports the id",
          calls == ["hello"] and "iid-9" in res["content"][0]["text"] and not res["is_error"])
    res = asyncio.run(_ask_desk_expert.handler({"question": "   "}))
    check("empty question is an error", res["is_error"] is True)
    current_context.set_main_window(None)
    current_context.set_gui_thread_caller(None)
    current_context.set_current_desk_directory(None)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
