import base64
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from desk.temp_ui import (  # noqa: E402
    DESK_PROC_KEYWORD,
    RESERVED_TEMPUI_KEYWORDS,
    detect_temp_ui_kind,
    parse_desk_proc,
)

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


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def test_desk_proc_keyword_is_reserved():
    check("DeskProc is a reserved DSL keyword", DESK_PROC_KEYWORD in RESERVED_TEMPUI_KEYWORDS)


def test_detect_temp_ui_kind_recognizes_desk_proc():
    text = f"DeskProc\tDo a thing\nScript\t{_b64('print(1)')}\n"
    check("detect_temp_ui_kind returns 'desk_proc'", detect_temp_ui_kind(text) == "desk_proc")


def test_parse_desk_proc_single_chunk():
    script = "print('hello')"
    text = f"DeskProc\tA quick one-off script\nScript\t{_b64(script)}\n"
    definition = parse_desk_proc(text)
    check("parse succeeds", definition is not None)
    check("summary round-trips", definition.summary == "A quick one-off script")
    decoded = base64.b64decode(definition.script_b64).decode("utf-8")
    check("script content round-trips", decoded == script)


def test_parse_desk_proc_multi_chunk_script():
    script = "x" * 5000  # long enough that a real author would plausibly chunk it
    full_b64 = _b64(script)
    chunk_a = full_b64[: len(full_b64) // 2]
    chunk_b = full_b64[len(full_b64) // 2 :]
    text = f"DeskProc\tFetch things\nScript\t{chunk_a}\nScript\t{chunk_b}\n"
    definition = parse_desk_proc(text)
    check("multi-chunk parse succeeds", definition is not None)
    decoded = base64.b64decode(definition.script_b64).decode("utf-8")
    check("multi-chunk script content concatenates and round-trips", decoded == script)


def test_parse_desk_proc_no_summary_defaults_to_empty():
    text = f"DeskProc\nScript\t{_b64('pass')}\n"
    definition = parse_desk_proc(text)
    check(
        "missing summary field parses as empty string, not a crash",
        definition is not None and definition.summary == "",
    )


def test_parse_desk_proc_rejects_garbage():
    check("no keyword at all -> None", parse_desk_proc("") is None)
    check("wrong keyword -> None", parse_desk_proc("NotADeskProc\thi\n") is None)
    check("no Script lines at all -> None", parse_desk_proc("DeskProc\thi\n") is None)


def test_desk_proc_has_no_kind_or_capability_fields():
    """Unlike Job, DeskProc is always a plain Python script -- a stray
    Capability line (copy-pasted from a Job file by mistake) is simply
    ignored, not an error, since parse_desk_proc never looks for it."""
    text = f"DeskProc\thi\nCapability\tworkspace\nScript\t{_b64('pass')}\n"
    definition = parse_desk_proc(text)
    check("parse still succeeds with a stray Capability line", definition is not None)
    check("no capabilities attribute leaks onto the definition", not hasattr(definition, "capabilities"))
    check("no kind attribute leaks onto the definition", not hasattr(definition, "kind"))


test_desk_proc_keyword_is_reserved()
test_detect_temp_ui_kind_recognizes_desk_proc()
test_parse_desk_proc_single_chunk()
test_parse_desk_proc_multi_chunk_script()
test_parse_desk_proc_no_summary_defaults_to_empty()
test_parse_desk_proc_rejects_garbage()
test_desk_proc_has_no_kind_or_capability_fields()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
