# DISABLED (see tests/verify/README.md) -- TODO 1082bd4 tracks
# investigating this. Current failure: Fails at import time: `import build_widget` expects
# scripts/build_widget.py importable directly, but TODO 029047b deleted
# that file and moved its content into src/desk/temp_ui.py as a
# generated string (_BUILD_WIDGET_SCRIPT), written into
# .desk_temp/build_widget.py at runtime instead of living as a static
# repo file. Reasonable suspicion: this test covers functionality that
# no longer exists at this location -- needs a full rewrite against the
# generated script, or deletion if later scripts already cover it.

import base64
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/scripts")

import build_widget  # noqa: E402
from desk.temp_ui import detect_temp_ui_kind, parse_define_widget  # noqa: E402

FIXTURE = Path("/private/tmp/claude-501/-Users-mphair-inadvisable-adventures-desk/123d4867-e017-40b8-b12a-cae0cb9117ae/scratchpad/build_widget_test")

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


# Test 1: round-trip through the real parser.
widget_dir = FIXTURE / "custom_widget_src" / "hello"
text = build_widget.build_widget(widget_dir)
check("detect_temp_ui_kind sees define_widget", detect_temp_ui_kind(text) == "define_widget")
definition = parse_define_widget(text)
check("parse succeeds", definition is not None)
check("keyword round-trips", definition.keyword == "HelloWidget")
check("label round-trips", definition.label == "Hello Widget")
check("size round-trips", definition.default_size == (300, 200))
decoded = base64.b64decode(definition.html_b64).decode("utf-8")
check("decoded html has compiled JS, not the marker", "BUILD:COMPILED_JS" not in decoded and "HelloWidget extends HTMLElement" in decoded)

# Test 2: missing manifest key -> clear BuildError.
bad_dir = FIXTURE / "custom_widget_src" / "bad_manifest"
bad_dir.mkdir(parents=True, exist_ok=True)
(bad_dir / "widget.json").write_text('{"keyword": "X", "label": "X"}')
try:
    build_widget.build_widget(bad_dir)
    check("missing manifest keys raises", False)
except build_widget.BuildError as e:
    check("missing manifest keys raises", "width" in str(e) and "height" in str(e))

# Test 3: missing .ts file -> clear BuildError.
missing_ts_dir = FIXTURE / "custom_widget_src" / "missing_ts"
missing_ts_dir.mkdir(parents=True, exist_ok=True)
(missing_ts_dir / "widget.json").write_text('{"keyword": "X", "label": "X", "width": 1, "height": 1}')
(missing_ts_dir / "tsconfig.json").write_text('{"compilerOptions": {"outDir": "build"}}')
try:
    build_widget.build_widget(missing_ts_dir)
    check("missing .ts file raises", False)
except build_widget.BuildError as e:
    check("missing .ts file raises", "missing_ts.ts" in str(e))

# Test 4: marker not found in widget.html -> clear BuildError.
no_marker_dir = FIXTURE / "custom_widget_src" / "no_marker"
no_marker_dir.mkdir(parents=True, exist_ok=True)
(no_marker_dir / "widget.json").write_text('{"keyword": "X", "label": "X", "width": 1, "height": 1}')
(no_marker_dir / "tsconfig.json").write_text('{"compilerOptions": {"outDir": "build"}}')
(no_marker_dir / "no_marker.ts").write_text("console.log(1);")
(no_marker_dir / "widget.html").write_text("<html><script></script></html>")
try:
    build_widget.build_widget(no_marker_dir)
    check("missing marker raises", False)
except build_widget.BuildError as e:
    check("missing marker raises", "BUILD:COMPILED_JS" in str(e))

# Test 5: tsc missing from PATH -> clear BuildError (simulate via monkeypatch).
real_which = shutil.which
shutil.which = lambda name: None if name == "tsc" else real_which(name)
try:
    build_widget.build_widget(widget_dir)
    check("tsc-missing raises", False)
except build_widget.BuildError as e:
    check("tsc-missing raises", "tsc" in str(e) and "PATH" in str(e))
finally:
    shutil.which = real_which

# Test 6: never falls back to npx (the doc comment mentions "npx" by
# name as a cautionary note, so check for an actual invocation instead).
check("no npx subprocess invocation in source", '"npx"' not in Path("/Users/mphair/inadvisable-adventures/desk/scripts/build_widget.py").read_text())

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
