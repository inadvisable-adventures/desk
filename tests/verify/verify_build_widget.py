import base64
import importlib.util
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")

from desk.temp_ui import (  # noqa: E402
    BUILD_WIDGET_SCRIPT_FILENAME,
    detect_temp_ui_kind,
    parse_define_widget,
    write_tempui_docs,
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


tempdir = tempfile.TemporaryDirectory()
project_dir = Path(tempdir.name)
temp_ui_dir = project_dir / ".desk_temp"
temp_ui_dir.mkdir()
write_tempui_docs(temp_ui_dir)
script_path = temp_ui_dir / BUILD_WIDGET_SCRIPT_FILENAME

spec = importlib.util.spec_from_file_location("build_widget_verify_mod", script_path)
build_widget = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_widget)

widget_src_root = project_dir / "custom_widget_src"

# Test 1: round-trip through the real parser.
widget_dir = widget_src_root / "hello"
widget_dir.mkdir(parents=True)
(widget_dir / "widget.json").write_text(
    '{"keyword": "HelloWidget", "label": "Hello Widget", "width": 300, "height": 200}'
)
(widget_dir / "tsconfig.json").write_text(
    '{"compilerOptions": {"strict": true, "target": "ES2019", "lib": ["DOM", "ES2019"], "outDir": "build"}}'
)
(widget_dir / "hello.ts").write_text(
    "class HelloWidget extends HTMLElement {\n"
    "  connectedCallback(): void {\n"
    '    const template = document.getElementById("hello-template") as HTMLTemplateElement;\n'
    '    const shadow = this.attachShadow({ mode: "open" });\n'
    "    shadow.appendChild(template.content.cloneNode(true));\n"
    "  }\n"
    "}\n"
    'customElements.define("hello-widget", HelloWidget);\n'
)
(widget_dir / "widget.html").write_text(
    "<!doctype html>\n<html>\n<head>\n"
    '<template id="hello-template">\n'
    "  <style>h1 { color: blue; }</style>\n"
    "  <h1>Hello</h1>\n"
    "</template>\n"
    "<script>\n/* BUILD:COMPILED_JS */\n</script>\n"
    "</head>\n<body>\n<hello-widget></hello-widget>\n</body>\n</html>\n"
)

if shutil.which("tsc") is None:
    check("tsc available for this script's own checks", False)
else:
    text = build_widget.build_widget(widget_dir)
    check("detect_temp_ui_kind sees define_widget", detect_temp_ui_kind(text) == "define_widget")
    definition = parse_define_widget(text)
    check("parse succeeds", definition is not None)
    check("keyword round-trips", definition.keyword == "HelloWidget")
    check("label round-trips", definition.label == "Hello Widget")
    check("size round-trips", definition.default_size == (300, 200))
    check(
        "no capabilities key in widget.json -> no Capability lines (backward compatible, TODO 31db3f6)",
        definition.capabilities == [],
    )
    decoded = base64.b64decode(definition.html_b64).decode("utf-8")
    check(
        "decoded html has compiled JS, not the marker",
        "BUILD:COMPILED_JS" not in decoded and "HelloWidget extends HTMLElement" in decoded,
    )

# Test 2: missing manifest key -> clear BuildError.
bad_dir = widget_src_root / "bad_manifest"
bad_dir.mkdir(parents=True, exist_ok=True)
(bad_dir / "widget.json").write_text('{"keyword": "X", "label": "X"}')
try:
    build_widget.build_widget(bad_dir)
    check("missing manifest keys raises", False)
except build_widget.BuildError as e:
    check("missing manifest keys raises", "width" in str(e) and "height" in str(e))

# Test 3: missing .ts file -> clear BuildError.
missing_ts_dir = widget_src_root / "missing_ts"
missing_ts_dir.mkdir(parents=True, exist_ok=True)
(missing_ts_dir / "widget.json").write_text('{"keyword": "X", "label": "X", "width": 1, "height": 1}')
(missing_ts_dir / "tsconfig.json").write_text('{"compilerOptions": {"outDir": "build"}}')
try:
    build_widget.build_widget(missing_ts_dir)
    check("missing .ts file raises", False)
except build_widget.BuildError as e:
    check("missing .ts file raises", "missing_ts.ts" in str(e))

# Test 4: marker not found in widget.html -> clear BuildError.
no_marker_dir = widget_src_root / "no_marker"
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
check("no npx subprocess invocation in source", '"npx"' not in script_path.read_text())

# Test 7 (TODO 31db3f6): widget.json's optional "capabilities" list is
# read and emitted as Capability<TAB>name lines -- real round-trip
# through the real generated script + the real parser, not mocked.
if shutil.which("tsc") is None:
    check("tsc available for the capabilities check", False)
else:
    caps_dir = widget_src_root / "with_caps"
    caps_dir.mkdir(parents=True, exist_ok=True)
    (caps_dir / "widget.json").write_text(
        '{"keyword": "WithCaps", "label": "With Caps", "width": 300, "height": 200, '
        '"capabilities": ["fs", "editor"]}'
    )
    (caps_dir / "tsconfig.json").write_text('{"compilerOptions": {"outDir": "build"}}')
    (caps_dir / "with_caps.ts").write_text("console.log(1);\n")
    (caps_dir / "widget.html").write_text("<html><script>\n/* BUILD:COMPILED_JS */\n</script></html>")

    caps_text = build_widget.build_widget(caps_dir)
    check(
        "widget.json's capabilities produce Capability<TAB>name lines in the generated file",
        "Capability\tfs" in caps_text and "Capability\teditor" in caps_text,
    )
    caps_definition = parse_define_widget(caps_text)
    check(
        "the real parser round-trips both declared capabilities",
        caps_definition is not None and caps_definition.capabilities == ["fs", "editor"],
    )

tempdir.cleanup()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
