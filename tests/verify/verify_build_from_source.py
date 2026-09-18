import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from desk.custom_widgets import SOURCE_BUILD_CACHE_DIRNAME, build_from_source  # noqa: E402

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


def _write_widget_source(rel_path, keyword="Hello"):
    widget_dir = project_dir / rel_path
    widget_dir.mkdir(parents=True, exist_ok=True)
    (widget_dir / "tsconfig.json").write_text('{"compilerOptions": {"outDir": "build"}}')
    (widget_dir / f"{widget_dir.name}.ts").write_text(f'console.log("{keyword}");\n')
    (widget_dir / "widget.html").write_text(
        "<!doctype html>\n<html><head>\n"
        "<script>\n/* BUILD:COMPILED_JS */\n</script>\n"
        "</head><body></body></html>\n"
    )
    return widget_dir


# Test 1: a real, successful build -- writes .build/index.html, no
# leftover base64/tempui artifacts (this is the whole point of
# build_from_source vs. materialize/build_widget.py: no round trip
# through a DefineWidget file).
if shutil.which("tsc") is None:
    check("tsc available for this script's own checks", False)
else:
    rel = "desk_widgets/hello"
    _write_widget_source(rel)
    build_dir = build_from_source(project_dir, rel)
    check("build_from_source returns the .build directory", build_dir == project_dir / rel / SOURCE_BUILD_CACHE_DIRNAME)
    check("build_dir is named .build", build_dir.name == ".build")
    index_html = build_dir / "index.html"
    check("index.html was written", index_html.is_file())
    content = index_html.read_text()
    check("marker replaced with compiled JS", "BUILD:COMPILED_JS" not in content and "console.log" in content)

    # Rebuilding is idempotent -- a stale .build/ from a previous run
    # doesn't leak into a fresh one.
    build_dir_again = build_from_source(project_dir, rel)
    check("rebuilding returns the same directory", build_dir_again == build_dir)

# Test 2: missing tsconfig.json -> logged, returns None (not raised).
missing_tsconfig_rel = "desk_widgets/missing_tsconfig"
(project_dir / missing_tsconfig_rel).mkdir(parents=True)
check("missing tsconfig.json returns None", build_from_source(project_dir, missing_tsconfig_rel) is None)

# Test 3: tsconfig.json with no outDir -> logged, returns None.
no_outdir_rel = "desk_widgets/no_outdir"
no_outdir_dir = project_dir / no_outdir_rel
no_outdir_dir.mkdir(parents=True)
(no_outdir_dir / "tsconfig.json").write_text("{}")
check("tsconfig.json missing outDir returns None", build_from_source(project_dir, no_outdir_rel) is None)

# Test 4: tsc missing from PATH -> logged, returns None (simulate via
# monkeypatch, mirroring verify_build_widget.py's own Test 5).
tsc_missing_rel = "desk_widgets/tsc_missing"
_write_widget_source(tsc_missing_rel)
real_which = shutil.which
shutil.which = lambda name: None if name == "tsc" else real_which(name)
try:
    check("tsc missing from PATH returns None", build_from_source(project_dir, tsc_missing_rel) is None)
finally:
    shutil.which = real_which

# Test 5: nonexistent source_path entirely -> logged, returns None.
check("nonexistent source directory returns None", build_from_source(project_dir, "desk_widgets/does-not-exist") is None)

tempdir.cleanup()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
