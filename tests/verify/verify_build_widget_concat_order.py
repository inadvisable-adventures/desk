import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from desk.temp_ui import BUILD_WIDGET_SCRIPT_FILENAME, write_tempui_docs  # noqa: E402

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


if shutil.which("tsc") is None or shutil.which("node") is None:
    check("tsc and node available for this script's own checks", False)
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)

tempdir = tempfile.TemporaryDirectory()
project_dir = Path(tempdir.name)
temp_ui_dir = project_dir / ".desk_temp"
temp_ui_dir.mkdir()
write_tempui_docs(temp_ui_dir)
script_path = temp_ui_dir / BUILD_WIDGET_SCRIPT_FILENAME

spec = importlib.util.spec_from_file_location("build_widget_concat_order_verify_mod", script_path)
build_widget = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_widget)

widget_src_root = project_dir / "custom_widget_src"

# Directory (and therefore the required <dirname>.ts entry file, per
# _compile_typescript) deliberately named so plain alphabetical order
# puts the *subclass* before the base class -- "aaa_widget.ts" sorts
# before "zzz_base.ts" -- reproducing the exact failure TODO 3fc5331
# describes (a subclass whose file happens to sort first throws
# ReferenceError: Cannot access 'Base' before initialization) unless
# the "files" array's own declared order (base first) is respected.
widget_dir = widget_src_root / "aaa_widget"
widget_dir.mkdir(parents=True)
(widget_dir / "widget.json").write_text(
    '{"keyword": "AaaWidget", "label": "Aaa Widget", "width": 300, "height": 200}'
)
(widget_dir / "tsconfig.json").write_text(
    '{"compilerOptions": {"strict": true, "target": "ES2019", "outDir": "build"}, '
    '"files": ["zzz_base.ts", "aaa_widget.ts"]}'
)
(widget_dir / "zzz_base.ts").write_text(
    "class BaseClass {\n"
    "  greeting(): string { return \"hello from base\"; }\n"
    "}\n"
)
(widget_dir / "aaa_widget.ts").write_text(
    "class SubClass extends BaseClass {\n"
    "  shout(): string { return this.greeting().toUpperCase(); }\n"
    "}\n"
    "(globalThis as any).__TEST_RESULT__ = new SubClass().shout();\n"
)
(widget_dir / "widget.html").write_text(
    "<!doctype html>\n<html><head>\n"
    "<script>\n/* BUILD:COMPILED_JS */\n</script>\n"
    "</head><body></body></html>\n"
)


def test_files_array_order_is_respected():
    """Real (not mocked) tsc compile + concatenation + node execution.
    Note, not re-tested live: plain sorted(out_dir.rglob("*.js")) would
    put aaa_widget.js before zzz_base.js here (alphabetical), which is
    exactly the ordering this fixture was built to defeat -- confirmed
    separately, before this fix existed, via a standalone reproduction
    (see TODO 3fc5331/LEARNINGS.md), not re-asserted as a live check
    against old code that no longer exists in this script."""
    tsconfig = build_widget._read_tsconfig(widget_dir)
    out_dir = build_widget._read_out_dir(widget_dir, tsconfig)
    ordered_stems = build_widget._read_ordered_stems(tsconfig)
    check("ordered_stems reads tsconfig.json's files array in declared order", ordered_stems == ["zzz_base", "aaa_widget"])

    build_widget._compile_typescript(widget_dir)
    compiled_js = build_widget._concatenate_compiled_js(out_dir, ordered_stems)
    check("base class source appears before the subclass's in the concatenated output", compiled_js.index("class BaseClass") < compiled_js.index("class SubClass"))

    result = subprocess.run(["node", "-e", compiled_js + "\nconsole.log(globalThis.__TEST_RESULT__);"], capture_output=True, text=True)
    check("running the concatenated output under real node succeeds (no ReferenceError)", result.returncode == 0 and "ReferenceError" not in result.stderr)
    check("the executed output is correct (base class method actually ran)", result.stdout.strip() == "HELLO FROM BASE")

    return out_dir, ordered_stems


def test_missing_stem_raises_clear_error(out_dir):
    try:
        build_widget._concatenate_compiled_js(out_dir, ["zzz_base", "aaa_widget", "does_not_exist"])
        check("a files entry with no matching compiled .js raises BuildError", False)
    except build_widget.BuildError as e:
        check("a files entry with no matching compiled .js raises BuildError", "does_not_exist" in str(e))


def test_unlisted_stem_raises_clear_error(out_dir):
    try:
        build_widget._concatenate_compiled_js(out_dir, ["zzz_base"])
        check("a compiled .js not listed in files raises BuildError", False)
    except build_widget.BuildError as e:
        check("a compiled .js not listed in files raises BuildError", "aaa_widget" in str(e))


def test_duplicate_stem_raises_clear_error():
    dup_root = project_dir / "dup_out"
    (dup_root / "sub_a").mkdir(parents=True)
    (dup_root / "sub_b").mkdir(parents=True)
    (dup_root / "sub_a" / "dup.js").write_text("// a\n")
    (dup_root / "sub_b" / "dup.js").write_text("// b\n")
    try:
        build_widget._concatenate_compiled_js(dup_root, ["dup"])
        check("two same-named compiled files in different directories raises BuildError", False)
    except build_widget.BuildError as e:
        check("two same-named compiled files in different directories raises BuildError", "dup" in str(e))


def test_no_files_key_is_unaffected():
    check("no files key -> _read_ordered_stems returns None (unchanged, alphabetical, behavior)", build_widget._read_ordered_stems({"compilerOptions": {"outDir": "build"}}) is None)
    check("an empty files list also returns None", build_widget._read_ordered_stems({"files": []}) is None)


out_dir, _ordered_stems = test_files_array_order_is_respected()
test_missing_stem_raises_clear_error(out_dir)
test_unlisted_stem_raises_clear_error(out_dir)
test_duplicate_stem_raises_clear_error()
test_no_files_key_is_unaffected()

tempdir.cleanup()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
