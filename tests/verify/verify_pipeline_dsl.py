import base64
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from desk import pipeline_dsl  # noqa: E402
from desk.shell import current_context  # noqa: E402
from desk.temp_ui import TEMP_UI_DIRNAME  # noqa: E402

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


def b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


class _FakeWindow:
    def __init__(self):
        self.calls = []
        self._state = {
            "widgets": [
                {"instance_id": "abc", "kind": "editor"},
                {"instance_id": "def", "kind": "console"},
                {"instance_id": "ghi", "kind": "editor"},
            ]
        }

    def zoom_to_widget_by_instance_id(self, instance_id):
        self.calls.append(("zoom", instance_id))
        return instance_id in ("abc", "def", "ghi")

    def screenshot_widget_instance(self, instance_id, path):
        self.calls.append(("screenshot_widget", instance_id, path))
        return instance_id in ("abc", "def", "ghi")

    def screenshot_desk(self, path):
        self.calls.append(("screenshot_desk", path))
        return True

    def get_state_dict(self):
        self.calls.append(("get_state_dict",))
        return self._state


def _register_fake_window():
    window = _FakeWindow()
    current_context.set_main_window(window)
    current_context.set_gui_thread_caller(lambda fn: fn())
    return window


def _clear_context():
    current_context.set_main_window(None)
    current_context.set_gui_thread_caller(None)
    current_context.set_current_desk_directory(None)


# -- Stage splitting -------------------------------------------------

def test_quoted_pipe_stays_in_one_stage():
    result = pipeline_dsl.run_pipeline("echo 'a | b'", {"echo": lambda _, s: s})
    check("one stage only", len(result["stages"]) == 1)
    check("the quoted '|' survived as part of the single argument", result["value"] == "a | b")


def test_unquoted_pipe_splits_stages():
    result = pipeline_dsl.run_pipeline("echo a | echo b", {"echo": lambda _, s: s})
    check("two stages", len(result["stages"]) == 2)
    check("final value is the second stage's own output", result["value"] == "b")


def test_py_stage_base64_with_plus_and_slash_survives_tokenization():
    data = bytes([251, 239, 190, 255, 250, 0, 1, 2, 3])
    token = "py:" + base64.b64encode(data).decode()
    check("token really contains + and /", "+" in token and "/" in token)
    # A malformed-as-UTF-8 decode is still a structural ValueError, but it
    # must be *this* error (bad UTF-8), not a tokenization split -- proving
    # the +/- and / survived as one token rather than being treated as
    # pipeline punctuation.
    try:
        pipeline_dsl.run_pipeline(token, {})
        check("expected a ValueError", False)
    except ValueError as e:
        check("fails on decode, not on unknown-verb/extra-stage", "malformed py:" in str(e))


def test_unbalanced_quoting_raises_value_error():
    try:
        pipeline_dsl.run_pipeline("echo 'oops", {"echo": lambda _, s: s})
        check("unbalanced quoting should raise", False)
    except ValueError:
        check("unbalanced quoting raises ValueError", True)


def test_empty_pipeline_raises_value_error():
    try:
        pipeline_dsl.run_pipeline("", {})
        check("empty pipeline should raise", False)
    except ValueError:
        check("empty pipeline raises ValueError", True)


def test_empty_stage_raises_value_error():
    try:
        pipeline_dsl.run_pipeline("echo a | | echo b", {"echo": lambda _, s: s})
        check("empty stage should raise", False)
    except ValueError:
        check("empty stage (adjacent pipes) raises ValueError", True)


def test_unknown_verb_raises_upfront_before_any_stage_runs():
    calls = []

    def _side_effect(_, x):
        calls.append(x)
        return x

    try:
        pipeline_dsl.run_pipeline("side_effect a | nonexistent_verb | side_effect b", {"side_effect": _side_effect})
        check("unknown verb should raise", False)
    except ValueError as e:
        check("unknown verb raises ValueError", "nonexistent_verb" in str(e))
    check("no stage actually ran -- validated for the whole pipeline upfront", calls == [])


# -- Argument coercion -------------------------------------------------

def test_int_and_float_coercion():
    def _identity_int(_, a: int) -> int:
        return a

    result = pipeline_dsl.run_pipeline("add 2", {"add": _identity_int})
    check("single int arg coerced", result["value"] == 2)

    def _sum(_, a: int, b: int) -> int:
        return a + b

    result = pipeline_dsl.run_pipeline("sum 2 3", {"sum": _sum})
    check("int-annotated args both coerced and summed", result["value"] == 5)

    def _scale(_, x: float) -> float:
        return x * 2

    result = pipeline_dsl.run_pipeline("scale 1.5", {"scale": _scale})
    check("float-annotated arg coerced", result["value"] == 3.0)


def test_bool_coercion_case_insensitive_and_strict():
    def _flag(_, on: bool) -> dict:
        return {"ok": True, "on": on}

    registry = {"flag": _flag}
    result = pipeline_dsl.run_pipeline("flag true", registry)
    check("'true' coerces to True", result["stages"][0]["output"]["on"] is True)
    result = pipeline_dsl.run_pipeline("flag FALSE", registry)
    check("'FALSE' coerces to False (case-insensitive)", result["stages"][0]["output"]["on"] is False)

    result = pipeline_dsl.run_pipeline("flag nah", registry)
    check("a non-true/false bool argument is a per-stage runtime failure, not a crash", result["ok"] is False)
    check("error names the bad value", "nah" in result["stages"][0]["error"])


def test_unannotated_and_str_annotated_pass_through_raw():
    result = pipeline_dsl.run_pipeline("echo hello", {"echo": lambda _, s: s})
    check("unannotated string arg passed through raw", result["value"] == "hello")

    def _echo_str(_, s: str) -> str:
        return s

    result = pipeline_dsl.run_pipeline("echo hello", {"echo": _echo_str})
    check("str-annotated arg passed through raw", result["value"] == "hello")


def test_wrong_argument_count_is_a_runtime_failure_not_a_crash():
    window = _register_fake_window()
    result = pipeline_dsl.run_pipeline("reveal_widget abc extra_unexpected_arg")
    check("wrong arg count doesn't crash the caller", result["ok"] is False)
    check("reported as a TypeError", result["stages"][0]["error"].startswith("TypeError"))
    check("the verb was never actually reached", window.calls == [])
    _clear_context()


# -- The py: escape hatch ------------------------------------------------

def test_py_stage_expression_ignores_piped_value():
    result = pipeline_dsl.run_pipeline(f"py:{b64('1 + 1')}", {})
    check("expression-only py: stage evaluates directly", result["value"] == 2)


def test_py_stage_callable_receives_piped_value():
    result = pipeline_dsl.run_pipeline(f"echo x | py:{b64('lambda v: v.upper()')}", {"echo": lambda _, s: s})
    check("callable py: stage is invoked with the piped value", result["value"] == "X")


def test_py_stage_malformed_base64_raises_upfront():
    try:
        pipeline_dsl.run_pipeline("py:not-valid-base64!!!", {})
        check("malformed base64 should raise", False)
    except ValueError as e:
        check("malformed py: base64 raises ValueError", "malformed py:" in str(e))


def test_py_stage_invalid_python_is_a_runtime_failure():
    result = pipeline_dsl.run_pipeline(f"py:{b64('1 +')}", {})
    check("a syntactically invalid but validly-decoded py: stage doesn't raise to the caller", result["ok"] is False)
    check("reported as a SyntaxError", "SyntaxError" in result["stages"][0]["error"])


def test_worked_example_2_filter_lambda_over_list_widget_instances():
    _register_fake_window()
    filter_src = "lambda ws: [w for w in ws if w['kind'] == 'editor']"
    result = pipeline_dsl.run_pipeline(f"list_widget_instances | py:{b64(filter_src)}")
    check("pipeline succeeded", result["ok"] is True)
    check("only the editor-kind instances survive", result["value"] == [
        {"instance_id": "abc", "kind": "editor"},
        {"instance_id": "ghi", "kind": "editor"},
    ])
    _clear_context()


# -- Fail-fast + the result contract (design plan's worked example 3) ----

def test_worked_example_3_fail_fast_on_ok_false():
    window = _register_fake_window()
    result = pipeline_dsl.run_pipeline("reveal_widget does-not-exist | screenshot_widget does-not-exist shots/x.png")
    check("overall ok is False", result["ok"] is False)
    check("only the first stage was attempted", len(result["stages"]) == 1)
    check("the second stage never actually ran", ("screenshot_widget", "does-not-exist", "shots/x.png") not in window.calls)
    check("value is None", result["value"] is None)
    check("no traceback -- this wasn't a raised exception", result["traceback"] is None)
    stage = result["stages"][0]
    check("stage 1 shape matches the design plan exactly", stage == {
        "stage": 1,
        "kind": "verb",
        "verb": "reveal_widget",
        "args": ["does-not-exist"],
        "ok": False,
        "output": None,
        "error": "verb reported ok: false",
    })
    _clear_context()


# -- Worked example 1: full happy path, real open_image side effect ------

def test_worked_example_1_full_happy_path_writes_a_real_open_image_tempui_file():
    _register_fake_window()
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        (directory / TEMP_UI_DIRNAME).mkdir()
        current_context.set_current_desk_directory(directory)

        result = pipeline_dsl.run_pipeline(
            "reveal_widget abc | screenshot_widget abc shots/x.png | open_image"
        )
        check("the full pipeline succeeds", result["ok"] is True)
        check("three stages all ran", len(result["stages"]) == 3)
        check("final value matches the design plan's own expected result", result["value"] == {"ok": True})

        written = list((directory / TEMP_UI_DIRNAME).glob("*"))
        check("exactly one OpenImage tempui file was written", len(written) == 1)
        content = written[0].read_text()
        check("it points at the screenshot's own path", content.strip() == "OpenImage shots/x.png")
    _clear_context()


# -- Individual built-in verbs -------------------------------------------

def test_reveal_widget_and_screenshot_verbs():
    window = _register_fake_window()
    result = pipeline_dsl.run_pipeline("reveal_widget abc")
    check("reveal_widget found -> ok True", result["value"] == {"ok": True})
    result = pipeline_dsl.run_pipeline("reveal_widget nope")
    check("reveal_widget not found -> stage fails (ok: False)", result["ok"] is False)

    result = pipeline_dsl.run_pipeline("screenshot_widget abc shots/x.png")
    check("screenshot_widget result shape", result["value"] == {"ok": True, "path": "shots/x.png"})
    check("routed through the fake window", ("screenshot_widget", "abc", "shots/x.png") in window.calls)

    result = pipeline_dsl.run_pipeline("screenshot_desk canvas.png")
    check("screenshot_desk result shape", result["value"] == {"ok": True, "path": "canvas.png"})
    _clear_context()


def test_verbs_report_not_ready_instead_of_crashing():
    _clear_context()
    for pipeline in ["reveal_widget abc", "screenshot_widget abc x.png", "screenshot_desk x.png", "list_widget_instances"]:
        result = pipeline_dsl.run_pipeline(pipeline)
        check(f"{pipeline!r} reports not-ready as a stage failure, not a crash", result["ok"] is False)
        check(f"{pipeline!r} names the reason", "not ready" in result["stages"][0]["error"] or "available" in result["stages"][0]["error"])


def test_open_image_reports_ok_false_with_no_desk_directory():
    _clear_context()
    result = pipeline_dsl.open_image({"path": "x.png"})
    check("no current Desk directory known -> ok False, not a crash", result == {"ok": False})


# -- The map verb (TODO e4d73dc) -----------------------------------------

def test_map_groups_correctly_around_its_own_inner_pipes():
    # An empty list means the map's own sub-pipeline never actually runs
    # (nothing to apply it to) -- this test is purely about how the
    # surrounding text groups into stages, not about running the inner
    # verbs, so their real signatures don't matter here.
    result = pipeline_dsl.run_pipeline(
        f"py:{b64('[]')} | map +| echo x | echo y |+ | echo after",
        {"echo": lambda _, s=None: s},
    )
    check("pipeline succeeded", result["ok"] is True)
    check("three top-level stages, not sliced apart by the map's own inner '|'s", len(result["stages"]) == 3)
    check("stage 2 is the map stage", result["stages"][1]["kind"] == "map")
    check("stage 3 is the ordinary stage after the map, not part of it", result["stages"][2]["verb"] == "echo")


def test_map_missing_close_raises_upfront():
    try:
        pipeline_dsl.run_pipeline("map +| echo x", {"echo": lambda _, s: s})
        check("missing '|+' should raise", False)
    except ValueError as e:
        check("missing '|+' raises ValueError", "missing closing" in str(e))


def test_map_empty_sub_pipeline_raises_upfront():
    try:
        pipeline_dsl.run_pipeline("echo a | map +| |+", {"echo": lambda _, s: s})
        check("an empty map sub-pipeline should raise", False)
    except ValueError as e:
        check("empty map sub-pipeline raises ValueError", "empty" in str(e))


def test_map_empty_sub_pipeline_with_no_separating_space_also_raises():
    # '+||+', with no space at all between the delimiters, is a single
    # '||' token straight out of shlex (adjacent punctuation characters
    # merge) -- _tokenize expands any all-'|' token back into individual
    # '|' tokens so this degenerate-but-plausible spelling still parses
    # (and still correctly rejects as empty) rather than silently
    # misgrouping.
    try:
        pipeline_dsl.run_pipeline("echo a | map +||+", {"echo": lambda _, s: s})
        check("an empty map sub-pipeline (no separating space) should raise", False)
    except ValueError as e:
        check("empty map sub-pipeline (no separating space) raises ValueError", "empty" in str(e))


def test_map_as_a_literal_argument_is_not_misparsed_as_the_keyword():
    def _accepts_any_args(_, *args):
        return list(args)

    registry = {"some_verb": _accepts_any_args, "other_verb": _accepts_any_args}
    result = pipeline_dsl.run_pipeline("some_verb map + | other_verb", registry)
    check("two ordinary stages, not a misparsed map", len(result["stages"]) == 2)
    check("'map' passed through as a literal argument, not a keyword", result["stages"][0]["args"] == ["map", "+"])
    check("second stage is the real 'other_verb' call", result["stages"][1]["verb"] == "other_verb")


def test_map_doubles_each_item_of_a_list():
    def double(item: int) -> int:
        return item * 2

    result = pipeline_dsl.run_pipeline(f"py:{b64('[1, 2, 3]')} | map +| double |+", {"double": double})
    check("map recombines the per-item results in order", result["value"] == [2, 4, 6])


def test_map_accepts_a_tuple_and_always_outputs_a_list():
    def double(item: int) -> int:
        return item * 2

    result = pipeline_dsl.run_pipeline(f"py:{b64('(1, 2, 3)')} | map +| double |+", {"double": double})
    check("a tuple input succeeds", result["ok"] is True)
    check("output is always a real list", result["value"] == [2, 4, 6] and isinstance(result["value"], list))


def test_map_rejects_a_non_sequence_piped_value():
    def double(item: int) -> int:
        return item * 2

    result = pipeline_dsl.run_pipeline(f"py:{b64('5')} | map +| double |+", {"double": double})
    check("a non-list/tuple piped value is a per-stage failure, not a crash", result["ok"] is False)
    check("reported as a TypeError", "TypeError" in result["stages"][-1]["error"])


def test_map_each_sub_pipeline_receives_its_own_item_not_none_or_the_outer_value():
    seen = []

    def record(item):
        seen.append(item)
        return item

    pipeline_dsl.run_pipeline(f"py:{b64('[10, 20, 30]')} | map +| record |+", {"record": record})
    check("each sub-pipeline saw its own item, in order", seen == [10, 20, 30])


def test_map_fail_fast_names_the_failing_item_and_reason_with_no_partial_output():
    def fail_on_three(item: int) -> dict:
        if item == 3:
            return {"ok": False}
        return {"ok": True}

    result = pipeline_dsl.run_pipeline(f"py:{b64('[1, 2, 3, 4]')} | map +| fail_on_three |+", {"fail_on_three": fail_on_three})
    check("the whole map stage fails", result["ok"] is False)
    map_entry = result["stages"][-1]
    check("no partial output", map_entry["output"] is None)
    check("names the failing item's index (0-based, third item)", "item 2" in map_entry["error"])
    check("names the underlying reason", "verb reported ok: false" in map_entry["error"])


def test_nested_map():
    def double(item: int) -> int:
        return item * 2

    result = pipeline_dsl.run_pipeline(
        f"py:{b64('[[1, 2], [3, 4]]')} | map +| map +| double |+ |+", {"double": double}
    )
    check("nested map recombines correctly at both levels", result["value"] == [[2, 4], [6, 8]])


def test_map_end_to_end_against_a_fake_window():
    # reveal_widget's own real argument (instance_id) comes from a
    # plain shlex-parsed string, not the piped value it deliberately
    # ignores (Sec. 3) -- this small adapter verb is what a real
    # pipeline author would write to run it once per piped item inside
    # a map, exercising the real pipeline_dsl.reveal_widget/_call_gui
    # routing against the fake window underneath.
    def reveal_by_id(instance_id: str) -> dict:
        return pipeline_dsl.reveal_widget(None, instance_id)

    _register_fake_window()
    result = pipeline_dsl.run_pipeline(
        f"py:{b64('[\"abc\", \"def\", \"ghi\"]')} | map +| reveal_by_id |+",
        {"reveal_by_id": reveal_by_id},
    )
    check("map over real instance ids succeeds", result["ok"] is True)
    check(
        "recombined into a list of each reveal_widget call's own result",
        result["value"] == [{"ok": True}, {"ok": True}, {"ok": True}],
    )
    _clear_context()


test_quoted_pipe_stays_in_one_stage()
test_unquoted_pipe_splits_stages()
test_py_stage_base64_with_plus_and_slash_survives_tokenization()
test_unbalanced_quoting_raises_value_error()
test_empty_pipeline_raises_value_error()
test_empty_stage_raises_value_error()
test_unknown_verb_raises_upfront_before_any_stage_runs()
test_int_and_float_coercion()
test_bool_coercion_case_insensitive_and_strict()
test_unannotated_and_str_annotated_pass_through_raw()
test_wrong_argument_count_is_a_runtime_failure_not_a_crash()
test_py_stage_expression_ignores_piped_value()
test_py_stage_callable_receives_piped_value()
test_py_stage_malformed_base64_raises_upfront()
test_py_stage_invalid_python_is_a_runtime_failure()
test_worked_example_2_filter_lambda_over_list_widget_instances()
test_worked_example_3_fail_fast_on_ok_false()
test_worked_example_1_full_happy_path_writes_a_real_open_image_tempui_file()
test_reveal_widget_and_screenshot_verbs()
test_verbs_report_not_ready_instead_of_crashing()
test_open_image_reports_ok_false_with_no_desk_directory()
test_map_groups_correctly_around_its_own_inner_pipes()
test_map_missing_close_raises_upfront()
test_map_empty_sub_pipeline_raises_upfront()
test_map_empty_sub_pipeline_with_no_separating_space_also_raises()
test_map_as_a_literal_argument_is_not_misparsed_as_the_keyword()
test_map_doubles_each_item_of_a_list()
test_map_accepts_a_tuple_and_always_outputs_a_list()
test_map_rejects_a_non_sequence_piped_value()
test_map_each_sub_pipeline_receives_its_own_item_not_none_or_the_outer_value()
test_map_fail_fast_names_the_failing_item_and_reason_with_no_partial_output()
test_nested_map()
test_map_end_to_end_against_a_fake_window()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
