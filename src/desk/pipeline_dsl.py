"""The pipe-chained verb DSL (TODO `63bfd42`), implementing the language
`plans/pipe-chained-verb-dsl.md` (TODO `765bd2a`) designed in full --
read that plan for the "why" behind every rule enforced here; this
module is deliberately just the "how."

`run_pipeline(text)` is the only entry point most callers need: parses
and validates `text` as a `|`-chained sequence of verb/`py:` stages
(raising `ValueError` immediately for anything structural -- an unknown
verb, a malformed `py:` prefix, unbalanced quoting), then executes it
fail-fast, returning the plan's own `{"ok", "stages", "value",
"traceback"}` result contract. See `desk.shell.desk_mcp_server`'s
`desk_run_pipeline` tool for the one transport wired up so far.
"""

import base64
import binascii
import inspect
import shlex
import traceback
import uuid
from collections.abc import Callable
from typing import Any

from desk.shell import current_context
from desk.temp_ui import TEMP_UI_DIRNAME

_PY_STAGE_PREFIX = "py:"


class _ParsedStage:
    __slots__ = ("kind", "verb", "args", "py_source")

    def __init__(self, kind: str, verb: str | None = None, args: list[str] | None = None, py_source: str | None = None):
        self.kind = kind
        self.verb = verb
        self.args = args
        self.py_source = py_source


def _tokenize(text: str) -> list[str]:
    """Splits the whole pipeline string into a flat token list, a bare
    `|` its own token, using `shlex`'s own posix quoting rules for
    everything else (Sec. 1 of the design plan) -- `shlex` itself raises
    `ValueError` for unbalanced quoting, exactly the upfront structural
    error Sec. 6 calls for."""
    lexer = shlex.shlex(text, posix=True, punctuation_chars="|")
    lexer.whitespace_split = True
    return list(lexer)


def _group_stages(tokens: list[str]) -> list[list[str]]:
    stages: list[list[str]] = [[]]
    for token in tokens:
        if token == "|":
            stages.append([])
        else:
            stages[-1].append(token)
    return stages


def _decode_py_source(token: str) -> str:
    encoded = token[len(_PY_STAGE_PREFIX):]
    try:
        return base64.b64decode(encoded.encode("ascii"), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError) as e:
        raise ValueError(f"malformed py: stage (bad base64): {e}") from e


def _parse_stages(text: str, registry: dict[str, Callable]) -> list[_ParsedStage]:
    tokens = _tokenize(text)
    if not tokens:
        raise ValueError("empty pipeline")
    groups = _group_stages(tokens)
    parsed = []
    for i, group in enumerate(groups, start=1):
        if not group:
            raise ValueError(f"empty stage at position {i}")
        if len(group) == 1 and group[0].startswith(_PY_STAGE_PREFIX):
            parsed.append(_ParsedStage(kind="py", py_source=_decode_py_source(group[0])))
            continue
        verb_name, *args = group
        if verb_name not in registry:
            raise ValueError(f"unknown verb {verb_name!r}")
        parsed.append(_ParsedStage(kind="verb", verb=verb_name, args=args))
    return parsed


def _coerce(raw: str, annotation: Any) -> Any:
    if annotation in (str, inspect.Parameter.empty):
        return raw
    if annotation is int:
        return int(raw)
    if annotation is float:
        return float(raw)
    if annotation is bool:
        lowered = raw.lower()
        if lowered not in ("true", "false"):
            raise ValueError(f"expected 'true'/'false' for a bool argument, got {raw!r}")
        return lowered == "true"
    return raw


def _run_verb_stage(stage: _ParsedStage, piped_value: Any, registry: dict[str, Callable]) -> Any:
    fn = registry[stage.verb]
    params = list(inspect.signature(fn).parameters.values())[1:]  # skip the piped-value parameter
    coerced = []
    for i, raw in enumerate(stage.args):
        annotation = params[i].annotation if i < len(params) else inspect.Parameter.empty
        coerced.append(_coerce(raw, annotation))
    return fn(piped_value, *coerced)


def _run_py_stage(stage: _ParsedStage, piped_value: Any) -> Any:
    # An empty globals dict still gets a real __builtins__ inserted by
    # eval() itself -- builtins only, no injected Desk object (Sec. 5).
    result = eval(stage.py_source, {})
    if callable(result):
        return result(piped_value)
    return result


def run_pipeline(text: str, registry: dict[str, Callable] | None = None) -> dict:
    """Parses and runs a full pipeline string. Raises `ValueError`
    immediately for a structural problem (Sec. 6) before any stage
    runs. Otherwise always returns the result-contract dict, never
    raises for a stage's own runtime failure."""
    if registry is None:
        registry = VERB_REGISTRY
    stages = _parse_stages(text, registry)

    result_stages: list[dict] = []
    value: Any = None
    piped_value: Any = None
    overall_ok = True
    tb_text: str | None = None

    for i, stage in enumerate(stages, start=1):
        entry: dict[str, Any] = {
            "stage": i,
            "kind": stage.kind,
            "verb": stage.verb,
            "args": stage.args,
            "ok": True,
            "output": None,
            "error": None,
        }
        try:
            if stage.kind == "verb":
                output = _run_verb_stage(stage, piped_value, registry)
            else:
                output = _run_py_stage(stage, piped_value)
        except Exception as e:
            entry["ok"] = False
            entry["error"] = f"{type(e).__name__}: {e}"
            tb_text = traceback.format_exc()
            result_stages.append(entry)
            overall_ok = False
            break

        if isinstance(output, dict) and output.get("ok") is False:
            entry["ok"] = False
            entry["error"] = "verb reported ok: false"
            result_stages.append(entry)
            overall_ok = False
            break

        entry["output"] = output
        result_stages.append(entry)
        piped_value = output
        value = output

    return {
        "ok": overall_ok,
        "stages": result_stages,
        "value": value if overall_ok else None,
        "traceback": tb_text,
    }


# -- Built-in verb registry (Sec. 4's illustrative starter catalog, all
#    five backed for real -- see plans/pipe-chained-verb-dsl-
#    implementation.md's "Key design decisions" for why all five, not a
#    subset) -----------------------------------------------------------

_NOT_READY_MESSAGE = "no Desk window/GUI thread caller available yet"


def _call_gui(fn: Callable[[Any], Any]) -> Any:
    window = current_context.get_main_window()
    if window is None:
        raise RuntimeError(_NOT_READY_MESSAGE)
    caller = current_context.get_gui_thread_caller()
    if caller is None:
        raise RuntimeError(_NOT_READY_MESSAGE)
    return caller(lambda: fn(window))


def reveal_widget(_: Any, instance_id: str) -> dict:
    found = _call_gui(lambda window: window.zoom_to_widget_by_instance_id(instance_id))
    return {"ok": bool(found)}


def screenshot_widget(_: Any, instance_id: str, path: str) -> dict:
    ok = _call_gui(lambda window: window.screenshot_widget_instance(instance_id, path))
    return {"ok": bool(ok), "path": path}


def screenshot_desk(_: Any, path: str) -> dict:
    ok = _call_gui(lambda window: window.screenshot_desk(path))
    return {"ok": bool(ok), "path": path}


def list_widget_instances(_: Any) -> list:
    state = _call_gui(lambda window: window.get_state_dict())
    return state.get("widgets", [])


def open_image(piped: dict) -> dict:
    """No pre-existing synchronous "do it and get a real result back"
    primitive exists for this one (unlike the four above) -- reuses the
    existing, already-safe `OpenImage` tempui-file mechanism
    (`tempui-image.md`) instead of adding a new privileged direct
    -placement method."""
    path = piped["path"]
    directory = current_context.get_current_desk_directory()
    if directory is None:
        return {"ok": False}
    temp_dir = directory / TEMP_UI_DIRNAME
    if not temp_dir.is_dir():
        return {"ok": False}
    try:
        (temp_dir / uuid.uuid4().hex).write_text(f"OpenImage {path}\n")
    except OSError:
        return {"ok": False}
    return {"ok": True}


VERB_REGISTRY: dict[str, Callable] = {
    "reveal_widget": reveal_widget,
    "screenshot_widget": screenshot_widget,
    "screenshot_desk": screenshot_desk,
    "list_widget_instances": list_widget_instances,
    "open_image": open_image,
}
