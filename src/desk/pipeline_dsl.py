"""The pipe-chained verb DSL (TODO `63bfd42`), implementing the language
`plans/pipe-chained-verb-dsl.md` (TODO `765bd2a`) designed in full --
read that plan for the "why" behind every rule enforced here; this
module is deliberately just the "how."

`run_pipeline(text)` is the only entry point most callers need: parses
and validates `text` as a `|`-chained sequence of verb/`py:`/`map`
stages (raising `ValueError` immediately for anything structural -- an
unknown verb, a malformed `py:` prefix, unbalanced quoting), then
executes it fail-fast, returning the plan's own `{"ok", "stages",
"value", "traceback"}` result contract. `map +| verb1 | verb2 |+`
(TODO `e4d73dc`, `plans/pipeline-dsl-map-verb.md`) runs the sub
-pipeline between its `+|`/`|+` delimiters once per item of a list
-shaped piped value, recombining the per-item results into a new list.
See `desk.shell.desk_mcp_server`'s `desk_run_pipeline` tool for the one
transport wired up so far. `run_pipeline` also takes an optional
`initial_value` (TODO `9d52dc4`) to seed the first stage with
something other than `None`.

`parse_pipeline(text) -> list[StageInfo]` (TODO `9d52dc4`) exposes
just the parse step -- a pipeline's structure without running it --
for a caller (the Pipeline widget's Mermaid diagram, so far) that
needs the shape, not the result.
"""

import base64
import binascii
import inspect
import shlex
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PyQt6.QtGui import QImage

from desk.shell import current_context
from desk.temp_ui import TEMP_UI_DIRNAME

_PY_STAGE_PREFIX = "py:"


_MAP_KEYWORD = "map"
_MAP_OPEN = "+|"
_MAP_CLOSE = "|+"


class _ParsedStage:
    __slots__ = ("kind", "verb", "args", "py_source", "sub_stages")

    def __init__(
        self,
        kind: str,
        verb: str | None = None,
        args: list[str] | None = None,
        py_source: str | None = None,
        sub_stages: list["_ParsedStage"] | None = None,
    ):
        self.kind = kind
        self.verb = verb
        self.args = args
        self.py_source = py_source
        self.sub_stages = sub_stages


def _tokenize(text: str) -> list[str]:
    """Splits the whole pipeline string into a flat token list, a bare
    `|` its own token, using `shlex`'s own posix quoting rules for
    everything else (Sec. 1 of the design plan) -- `shlex` itself raises
    `ValueError` for unbalanced quoting, exactly the upfront structural
    error Sec. 6 calls for. Deliberately doesn't add `+` to
    `punctuation_chars` too (which would let `shlex` merge a `map`
    stage's own `+|`/`|+` delimiters for us) -- `shlex` punctuation
    characters split on every occurrence, not just adjacent runs at
    word boundaries, which would corrupt an ordinary verb argument or a
    `py:` base64 payload containing a literal `+` (base64's own
    alphabet includes it). See `_group_top_level_stages` for how
    `+|`/`|+` are recognized instead, at the grouping step."""
    lexer = shlex.shlex(text, posix=True, punctuation_chars="|")
    lexer.whitespace_split = True
    tokens = []
    for token in lexer:
        # shlex merges adjacent punctuation characters into one token
        # (e.g. an unspaced 'map +||+', an empty map sub-pipeline,
        # tokenizes '||' as a single two-character token) -- expand any
        # all-'|' token back into individual '|' tokens so the grouping
        # step below sees the same shape it would from spaced-out input.
        if len(token) > 1 and set(token) == {"|"}:
            tokens.extend(["|"] * len(token))
        else:
            tokens.append(token)
    return tokens


def _group_top_level_stages(tokens: list[str]) -> list[list[str]]:
    """Groups tokens into stages by bare `|`, except inside a `map`
    stage's own `+| ... |+` span (plans/pipeline-dsl-map-verb.md's
    "Grammar and tokenizing") -- a `+` token immediately followed by a
    `|` token only opens a span when it directly follows a `map`
    keyword that itself began a (sub-)stage (`just_saw_map_keyword`,
    set only when `map` was appended while `at_stage_start` was true),
    so an ordinary verb argument that happens to be spelled "map" is
    never misread as this keyword. A `|` token immediately followed by
    a `+` token always closes the innermost open span. A bare `|`
    encountered inside an open span is kept in place (it's the
    sub-pipeline's own separator, resolved when that span's tokens are
    recursively re-grouped by _parse_stage_group)."""
    stages: list[list[str]] = [[]]
    map_depth = 0
    at_stage_start = True
    just_saw_map_keyword = False
    i = 0
    n = len(tokens)
    while i < n:
        token = tokens[i]

        if just_saw_map_keyword and token == "+" and i + 1 < n and tokens[i + 1] == "|":
            stages[-1].append(_MAP_OPEN)
            map_depth += 1
            at_stage_start = True
            just_saw_map_keyword = False
            i += 2
            continue
        just_saw_map_keyword = False

        if map_depth > 0 and token == "|" and i + 1 < n and tokens[i + 1] == "+":
            stages[-1].append(_MAP_CLOSE)
            map_depth -= 1
            at_stage_start = False
            i += 2
            continue

        if token == "|" and map_depth == 0:
            stages.append([])
            at_stage_start = True
            i += 1
            continue

        if token == "|":  # map_depth > 0 -- an inner stage separator, kept in place
            stages[-1].append(token)
            at_stage_start = True
            i += 1
            continue

        stages[-1].append(token)
        just_saw_map_keyword = at_stage_start and token == _MAP_KEYWORD
        at_stage_start = False
        i += 1

    if map_depth != 0:
        raise ValueError("unmatched 'map +|' -- missing closing '|+'")
    return stages


def _decode_py_source(token: str) -> str:
    encoded = token[len(_PY_STAGE_PREFIX):]
    try:
        return base64.b64decode(encoded.encode("ascii"), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError) as e:
        raise ValueError(f"malformed py: stage (bad base64): {e}") from e


def _parse_stage_group(group: list[str], registry: dict[str, Callable]) -> _ParsedStage:
    if len(group) == 1 and group[0].startswith(_PY_STAGE_PREFIX):
        return _ParsedStage(kind="py", py_source=_decode_py_source(group[0]))
    if group[0] == _MAP_KEYWORD:
        if len(group) < 3 or group[1] != _MAP_OPEN or group[-1] != _MAP_CLOSE:
            raise ValueError("malformed map stage -- expected 'map +| ... |+'")
        inner_tokens = group[2:-1]
        if not inner_tokens:
            raise ValueError("map's sub-pipeline is empty")
        sub_stages = _parse_stages_from_tokens(inner_tokens, registry)
        return _ParsedStage(kind="map", sub_stages=sub_stages)
    verb_name, *args = group
    if verb_name not in registry:
        raise ValueError(f"unknown verb {verb_name!r}")
    return _ParsedStage(kind="verb", verb=verb_name, args=args)


def _parse_stages_from_tokens(tokens: list[str], registry: dict[str, Callable]) -> list[_ParsedStage]:
    if not tokens:
        raise ValueError("empty pipeline")
    groups = _group_top_level_stages(tokens)
    parsed = []
    for i, group in enumerate(groups, start=1):
        if not group:
            raise ValueError(f"empty stage at position {i}")
        parsed.append(_parse_stage_group(group, registry))
    return parsed


def _parse_stages(text: str, registry: dict[str, Callable]) -> list[_ParsedStage]:
    return _parse_stages_from_tokens(_tokenize(text), registry)


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


def _run_map_stage(stage: _ParsedStage, piped_value: Any, registry: dict[str, Callable]) -> list:
    """Runs `stage.sub_stages` once per item of `piped_value` (a `list`
    or `tuple` -- anything else is a TypeError, caught by the caller's
    own per-stage try/except exactly like any other verb's raised
    exception), recombining the per-item results into a new list, in
    order. Fail-fast, one level up: the first item whose own
    sub-pipeline doesn't succeed raises immediately, making the whole
    `map` stage a single failed stage in the outer pipeline's result
    (plans/pipeline-dsl-map-verb.md's "Key design decisions" -- no
    partial-results mode of its own)."""
    if not isinstance(piped_value, (list, tuple)):
        raise TypeError(f"map requires a list/array piped value, got {type(piped_value).__name__}")
    results = []
    for index, item in enumerate(piped_value):
        sub_result = _execute_stages(stage.sub_stages, item, registry)
        if not sub_result["ok"]:
            failing_stage = sub_result["stages"][-1]
            raise RuntimeError(f"map item {index}: {failing_stage['error']}")
        results.append(sub_result["value"])
    return results


def _execute_stages(stages: list[_ParsedStage], piped_value: Any, registry: dict[str, Callable]) -> dict:
    """Runs already-parsed `stages` fail-fast, returning the plan's own
    `{"ok", "stages", "value", "traceback"}` result contract (Sec. 6).
    Recursive: a `map` stage calls this once per item (`_run_map_stage`
    above)."""
    result_stages: list[dict] = []
    value: Any = None
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
            elif stage.kind == "map":
                output = _run_map_stage(stage, piped_value, registry)
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


def run_pipeline(
    text: str, registry: dict[str, Callable] | None = None, initial_value: Any = None
) -> dict:
    """Parses and runs a full pipeline string. Raises `ValueError`
    immediately for a structural problem (Sec. 6) before any stage
    runs. Otherwise always returns the result-contract dict, never
    raises for a stage's own runtime failure. `initial_value` (TODO
    `9d52dc4`, the Pipeline widget's drag-and-dropped "Input") is what
    the first stage receives as its piped value -- `None` (the
    pre-existing, still-default behavior every other caller keeps
    getting) means "no real input," exactly as before."""
    if registry is None:
        registry = VERB_REGISTRY
    stages = _parse_stages(text, registry)
    return _execute_stages(stages, initial_value, registry)


@dataclass
class StageInfo:
    """A pipeline's parsed *structure*, without running anything --
    the same grammar `run_pipeline` uses, minus `_ParsedStage`'s
    `py_source` (a `py:` stage is only ever shown as a fixed "N. py:"
    label by the Pipeline widget's diagram, TODO `9d52dc4`, never
    rendered as decoded source). Public and stable so a caller other
    than `run_pipeline` itself (so far, just that widget) can build
    something from a pipeline's shape without duplicating any grammar
    logic here."""

    kind: str  # "verb" | "py" | "map"
    verb: str | None = None
    args: list[str] | None = None
    sub_stages: list["StageInfo"] | None = None


def _to_stage_info(stage: _ParsedStage) -> StageInfo:
    return StageInfo(
        kind=stage.kind,
        verb=stage.verb,
        args=list(stage.args) if stage.args is not None else None,
        sub_stages=[_to_stage_info(s) for s in stage.sub_stages] if stage.sub_stages is not None else None,
    )


def parse_pipeline(text: str, registry: dict[str, Callable] | None = None) -> list[StageInfo]:
    """Parses (never executes) `text` into a list of `StageInfo` --
    this *is* `run_pipeline`'s own parse step, exposed on its own.
    Raises the same `ValueError`s `run_pipeline` raises upfront, for
    the same reasons."""
    if registry is None:
        registry = VERB_REGISTRY
    return [_to_stage_info(s) for s in _parse_stages(text, registry)]


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


_IMAGE_CHANNELS: tuple[str, ...] = ("R", "G", "B")
# Format_RGBA8888 is Qt's one *byte-ordered* 32-bit image format: the
# in-memory byte order is always R, G, B, A on every platform (unlike
# Format_ARGB32, a packed-int format whose byte order depends on host
# endianness) -- so these offsets need no endianness handling. Each
# tuple names the two byte offsets to zero to keep only that channel
# (plus alpha, offset 3, always left alone).
_CHANNEL_ZERO_OFFSETS: dict[str, tuple[int, int]] = {
    "R": (1, 2),
    "G": (0, 2),
    "B": (0, 1),
}


def split_channels(piped: dict) -> list[dict]:
    """Splits `piped["path"]` into a 3-item `[{"path", "channel"}, ...]`
    list, R/G/B order (TODO `9d52dc4`): each result is a full image of
    the same type/size/content as the source, except with the other
    two color channels zeroed out (alpha untouched) -- an R-channel
    result looks like the source rendered in red only, etc. Each
    entry's "path" is exactly the shape `open_image` already expects,
    so `split_channels | map +| open_image |+` displays all three
    without either verb knowing about the other.

    Uses `QImage` (already a Desk dependency via PyQt6 -- CLAUDE.md's
    "avoid adding dependencies, prefer bespoke solutions" -- no
    Pillow/numpy) rather than a per-pixel Python loop: a nested-loop
    `setPixelColor` version was tried first and was slow enough on a
    real several-megapixel photo to be a real problem, not a
    hypothetical one, so this zeroes two of every four bytes with one
    strided `bytearray` slice assignment per channel instead."""
    source_path = Path(piped["path"])
    image = QImage(str(source_path))
    if image.isNull():
        raise ValueError(f"not a loadable image file: {source_path}")
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    width, height = image.width(), image.height()
    bits = image.constBits()
    bits.setsize(image.sizeInBytes())
    raw = bytes(bits)

    directory = current_context.get_current_desk_directory()
    if directory is None:
        raise RuntimeError("no current Desk directory to write channel images into")
    temp_dir = directory / TEMP_UI_DIRNAME
    if not temp_dir.is_dir():
        raise RuntimeError("no .desk_temp directory for the current Desk")

    zeros = bytes(width * height)
    results = []
    for channel in _IMAGE_CHANNELS:
        buf = bytearray(raw)
        for offset in _CHANNEL_ZERO_OFFSETS[channel]:
            buf[offset::4] = zeros
        channel_image = QImage(bytes(buf), width, height, image.bytesPerLine(), QImage.Format.Format_RGBA8888)
        out_path = temp_dir / f"{uuid.uuid4().hex[:8]}-{source_path.stem}-{channel}.png"
        if not channel_image.save(str(out_path), "PNG"):
            raise RuntimeError(f"failed to save {channel} channel image to {out_path}")
        results.append({"path": str(out_path), "channel": channel})
    return results


VERB_REGISTRY: dict[str, Callable] = {
    "reveal_widget": reveal_widget,
    "screenshot_widget": screenshot_widget,
    "screenshot_desk": screenshot_desk,
    "list_widget_instances": list_widget_instances,
    "open_image": open_image,
    "split_channels": split_channels,
}
