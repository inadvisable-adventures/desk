import base64
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")

from desk.temp_ui import (  # noqa: E402
    JOB_KEYWORD,
    RESERVED_TEMPUI_KEYWORDS,
    detect_temp_ui_kind,
    parse_job,
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


def test_job_keyword_is_reserved():
    check("Job is a reserved DSL keyword", JOB_KEYWORD in RESERVED_TEMPUI_KEYWORDS)


def test_detect_temp_ui_kind_recognizes_job():
    text = f"Job\thtml\tDo a thing\nScript\t{_b64('<html></html>')}\n"
    check("detect_temp_ui_kind returns 'job'", detect_temp_ui_kind(text) == "job")


def test_parse_job_single_chunk():
    script = "print('hello')"
    text = f"Job\tpython\tA quick one-off script\nCapability\tfs\nScript\t{_b64(script)}\n"
    definition = parse_job(text)
    check("parse succeeds", definition is not None)
    check("kind round-trips", definition.kind == "python")
    check("summary round-trips", definition.summary == "A quick one-off script")
    check("capabilities round-trip", definition.capabilities == ["fs"])
    decoded = base64.b64decode(definition.script_b64).decode("utf-8")
    check("script content round-trips", decoded == script)


def test_parse_job_multi_chunk_script_and_multiple_capabilities():
    script = "x" * 5000  # long enough that a real author would plausibly chunk it
    chunk_a = _b64(script)[: len(_b64(script)) // 2]
    chunk_b = _b64(script)[len(_b64(script)) // 2 :]
    text = (
        "Job\thtml\tFetch things\n"
        "Capability\tworkspace\n"
        "Capability\tfs\n"
        f"Script\t{chunk_a}\n"
        f"Script\t{chunk_b}\n"
    )
    definition = parse_job(text)
    check("multi-chunk parse succeeds", definition is not None)
    check("both capabilities collected in order", definition.capabilities == ["workspace", "fs"])
    decoded = base64.b64decode(definition.script_b64).decode("utf-8")
    check("multi-chunk script content concatenates and round-trips", decoded == script)


def test_parse_job_no_summary_defaults_to_empty():
    text = f"Job\tpython\nScript\t{_b64('pass')}\n"
    definition = parse_job(text)
    check("missing summary field parses as empty string, not a crash", definition is not None and definition.summary == "")


def test_parse_job_rejects_garbage():
    check("no keyword at all -> None", parse_job("") is None)
    check("wrong keyword -> None", parse_job("NotAJob\tpython\thi\n") is None)
    check("missing kind -> None", parse_job("Job\n") is None)
    check("invalid kind -> None", parse_job(f"Job\tjavascript\thi\nScript\t{_b64('x')}\n") is None)
    check("no Script lines at all -> None", parse_job("Job\tpython\thi\n") is None)


def test_capability_lines_collected_regardless_of_kind():
    """Harmless-but-collected for python (TODO d7e66f6's own design
    decision -- simpler than branching the parser on kind for a field
    that's just unused at execution time)."""
    text = f"Job\tpython\thi\nCapability\tworkspace\nScript\t{_b64('pass')}\n"
    definition = parse_job(text)
    check("Capability lines are collected even for a python-kind job", definition.capabilities == ["workspace"])


test_job_keyword_is_reserved()
test_detect_temp_ui_kind_recognizes_job()
test_parse_job_single_chunk()
test_parse_job_multi_chunk_script_and_multiple_capabilities()
test_parse_job_no_summary_defaults_to_empty()
test_parse_job_rejects_garbage()
test_capability_lines_collected_regardless_of_kind()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
