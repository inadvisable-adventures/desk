"""Verifies TODO `9d52dc4`'s additions to `desk.pipeline_dsl`: the
`split_channels` verb, `run_pipeline`'s new `initial_value` param, and
the new public `parse_pipeline`/`StageInfo` introspection API. See
`plans/pipeline-widget.md`. The Pipeline widget itself (mermaid
generation, drop target) is covered separately by
`verify_pipeline_widget.py`; the canvas drop-delegation mechanism by
`verify_canvas_drop_delegation.py`."""

import base64
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from PyQt6.QtGui import QColor, QImage  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

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


def _clear_context():
    current_context.set_current_desk_directory(None)


def _make_test_image(path: Path) -> None:
    """A tiny 2x2 image with distinct, known RGBA pixels -- enough to
    directly check per-pixel channel zeroing without needing a real
    fixture file on disk."""
    image = QImage(2, 2, QImage.Format.Format_RGBA8888)
    image.setPixelColor(0, 0, QColor(200, 50, 10, 255))
    image.setPixelColor(1, 0, QColor(10, 200, 50, 128))
    image.setPixelColor(0, 1, QColor(50, 10, 200, 0))
    image.setPixelColor(1, 1, QColor(1, 2, 3, 254))
    assert image.save(str(path), "PNG")


# -- split_channels -------------------------------------------------


def test_split_channels_keeps_only_the_named_channel_per_pixel():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        (directory / TEMP_UI_DIRNAME).mkdir()
        current_context.set_current_desk_directory(directory)
        src_path = directory / "src.png"
        _make_test_image(src_path)

        results = pipeline_dsl.split_channels({"path": str(src_path)})
        check("returns a 3-item list", len(results) == 3)
        check("R/G/B order", [r["channel"] for r in results] == ["R", "G", "B"])

        source_size = QImage(str(src_path)).size()
        for r in results:
            check(f"{r['channel']} output written under .desk_temp/", Path(r["path"]).parent == directory / TEMP_UI_DIRNAME)

        by_channel = {r["channel"]: QImage(r["path"]) for r in results}
        for channel, out in by_channel.items():
            check(f"{channel} output is same size as source", out.size() == source_size)

        src_pixels = [(0, 0, 200, 50, 10, 255), (1, 0, 10, 200, 50, 128), (0, 1, 50, 10, 200, 0), (1, 1, 1, 2, 3, 254)]
        for x, y, r, g, b, a in src_pixels:
            r_color = by_channel["R"].pixelColor(x, y)
            check(f"R-channel keeps R at ({x},{y})", (r_color.red(), r_color.green(), r_color.blue()) == (r, 0, 0))
            check(f"R-channel keeps alpha at ({x},{y})", r_color.alpha() == a)

            g_color = by_channel["G"].pixelColor(x, y)
            check(f"G-channel keeps G at ({x},{y})", (g_color.red(), g_color.green(), g_color.blue()) == (0, g, 0))
            check(f"G-channel keeps alpha at ({x},{y})", g_color.alpha() == a)

            b_color = by_channel["B"].pixelColor(x, y)
            check(f"B-channel keeps B at ({x},{y})", (b_color.red(), b_color.green(), b_color.blue()) == (0, 0, b))
            check(f"B-channel keeps alpha at ({x},{y})", b_color.alpha() == a)
        _clear_context()


def test_split_channels_raises_value_error_for_a_non_image_file():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        (directory / TEMP_UI_DIRNAME).mkdir()
        current_context.set_current_desk_directory(directory)
        not_an_image = directory / "notes.txt"
        not_an_image.write_text("hello")
        try:
            pipeline_dsl.split_channels({"path": str(not_an_image)})
            check("expected a ValueError for a non-image file", False)
        except ValueError as e:
            check("names the unloadable file", "notes.txt" in str(e))
        _clear_context()


def test_split_channels_raises_runtime_error_with_no_desk_directory():
    _clear_context()
    with tempfile.TemporaryDirectory() as d:
        src_path = Path(d) / "src.png"
        _make_test_image(src_path)
        try:
            pipeline_dsl.split_channels({"path": str(src_path)})
            check("expected a RuntimeError with no current Desk directory", False)
        except RuntimeError as e:
            check("names the missing directory", "Desk directory" in str(e))


def test_split_channels_raises_runtime_error_with_no_desk_temp_dir():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        current_context.set_current_desk_directory(directory)  # no .desk_temp/ created
        src_path = directory / "src.png"
        _make_test_image(src_path)
        try:
            pipeline_dsl.split_channels({"path": str(src_path)})
            check("expected a RuntimeError with no .desk_temp/", False)
        except RuntimeError as e:
            check("names .desk_temp", "desk_temp" in str(e))
        _clear_context()


def test_split_channels_registered_in_verb_registry():
    check("split_channels is in VERB_REGISTRY", pipeline_dsl.VERB_REGISTRY.get("split_channels") is pipeline_dsl.split_channels)


# -- End-to-end: split_channels | map +| open_image |+ -------------------


def test_end_to_end_split_and_display_via_map():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        (directory / TEMP_UI_DIRNAME).mkdir()
        current_context.set_current_desk_directory(directory)
        src_path = directory / "src.png"
        _make_test_image(src_path)

        result = pipeline_dsl.run_pipeline(
            "split_channels | map +| open_image |+", initial_value={"path": str(src_path)}
        )
        check("the full pipeline succeeds", result["ok"] is True)
        check("two top-level stages ran", len(result["stages"]) == 2)
        check("map's own output is a 3-item list of {'ok': True}", result["value"] == [{"ok": True}] * 3)

        written = sorted((directory / TEMP_UI_DIRNAME).glob("*"))
        # 3 channel PNGs (from split_channels) + 3 OpenImage tempui files (from open_image)
        png_files = [p for p in written if p.suffix == ".png"]
        open_image_files = [p for p in written if p not in png_files and p.read_text().startswith("OpenImage ")]
        check("three channel PNGs were written", len(png_files) == 3)
        check("three OpenImage tempui files were written", len(open_image_files) == 3)
        for tempui_file in open_image_files:
            pointed_path = Path(tempui_file.read_text().strip()[len("OpenImage "):])
            check(f"{tempui_file.name} points at one of the real channel PNGs", pointed_path in png_files)
        _clear_context()


# -- run_pipeline's initial_value param -----------------------------------


def test_initial_value_defaults_to_none_unchanged():
    result = pipeline_dsl.run_pipeline("echo", {"echo": lambda piped: piped})
    check("omitted initial_value still starts from None, as before", result["value"] is None)


def test_initial_value_seeds_the_first_stage():
    result = pipeline_dsl.run_pipeline("echo", {"echo": lambda piped: piped}, initial_value={"path": "x.png"})
    check("first stage receives initial_value instead of None", result["value"] == {"path": "x.png"})


# -- parse_pipeline / StageInfo --------------------------------------------


def test_parse_pipeline_matches_run_pipeline_shape_for_a_plain_pipeline():
    registry = {"a": lambda _: None, "b": lambda _, x: None}
    stages = pipeline_dsl.parse_pipeline("a | b 1", registry)
    check("two stages parsed", len(stages) == 2)
    check("stage 1 is verb 'a' with no args", stages[0].kind == "verb" and stages[0].verb == "a" and stages[0].args == [])
    check("stage 2 is verb 'b' with args ['1']", stages[1].kind == "verb" and stages[1].verb == "b" and stages[1].args == ["1"])
    check("no sub_stages on a plain verb stage", stages[0].sub_stages is None)


def test_parse_pipeline_py_stage():
    stages = pipeline_dsl.parse_pipeline(f"py:{b64('1')}", {})
    check("one py stage", len(stages) == 1 and stages[0].kind == "py")
    check("py stage has no verb/args/sub_stages", stages[0].verb is None and stages[0].args is None and stages[0].sub_stages is None)


def test_parse_pipeline_nested_map():
    registry = {"echo": lambda _, s=None: s}
    stages = pipeline_dsl.parse_pipeline("map +| map +| echo x |+ |+", registry)
    check("one top-level map stage", len(stages) == 1 and stages[0].kind == "map")
    check("outer map has one sub-stage", len(stages[0].sub_stages) == 1)
    inner = stages[0].sub_stages[0]
    check("nested map is itself a map with its own sub-stage", inner.kind == "map" and len(inner.sub_stages) == 1)
    check("innermost stage is the echo verb", inner.sub_stages[0].kind == "verb" and inner.sub_stages[0].verb == "echo")


def test_parse_pipeline_raises_same_errors_as_run_pipeline():
    for text, registry in [
        ("", {}),
        ("echo 'oops", {"echo": lambda _, s: s}),
        ("nonexistent_verb", {}),
        ("map +| |+", {}),
    ]:
        try:
            pipeline_dsl.parse_pipeline(text, registry)
            check(f"parse_pipeline({text!r}) should raise ValueError", False)
        except ValueError:
            check(f"parse_pipeline({text!r}) raises ValueError, same as run_pipeline", True)


test_split_channels_keeps_only_the_named_channel_per_pixel()
test_split_channels_raises_value_error_for_a_non_image_file()
test_split_channels_raises_runtime_error_with_no_desk_directory()
test_split_channels_raises_runtime_error_with_no_desk_temp_dir()
test_split_channels_registered_in_verb_registry()
test_end_to_end_split_and_display_via_map()
test_initial_value_defaults_to_none_unchanged()
test_initial_value_seeds_the_first_stage()
test_parse_pipeline_matches_run_pipeline_shape_for_a_plain_pipeline()
test_parse_pipeline_py_stage()
test_parse_pipeline_nested_map()
test_parse_pipeline_raises_same_errors_as_run_pipeline()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
