import base64
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")

from desk.temp_ui import (  # noqa: E402
    BUILD_WIDGET_SCRIPT_FILENAME,
    CUSTOM_WIDGETS_DOC_FILENAME,
    SPLIT_DOC_CONTENT,
    TEMPUI_DOC_VERSION,
    ensure_docs_current,
    render_static_doc,
    write_tempui_docs,
)
from desk.shell.window import DeskWindow  # noqa: E402

REPO_ROOT = Path("/Users/mphair/inadvisable-adventures/desk")

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


check("scripts/build_widget.py no longer exists", not (REPO_ROOT / "scripts" / "build_widget.py").exists())
check("DeskWindow._seed_build_widget_script no longer exists", not hasattr(DeskWindow, "_seed_build_widget_script"))
check("build_widget.py registered in SPLIT_DOC_CONTENT", BUILD_WIDGET_SCRIPT_FILENAME in SPLIT_DOC_CONTENT)
check("TEMPUI_DOC_VERSION bumped to at least 17", TEMPUI_DOC_VERSION >= 17)

breaking = SPLIT_DOC_CONTENT["tempui-breaking-changes.md"]
check("breaking-changes doc has a Version 17 entry", "## Version 17" in breaking)
check("Version 17 entry mentions the relocation", ".desk_temp/build_widget.py" in breaking and "scripts/build_widget.py" in breaking)

custom_widgets_doc = SPLIT_DOC_CONTENT[CUSTOM_WIDGETS_DOC_FILENAME]
check(
    "custom-widgets doc's invocation examples point at the new location",
    "python3 .desk_temp/build_widget.py .desk_temp/widgets/<name>" in custom_widgets_doc,
)
check(
    "custom-widgets doc's post-promotion example also updated",
    "python3 .desk_temp/build_widget.py\ndesk_widgets/<name>" in custom_widgets_doc,
)
check("custom-widgets doc no longer tells you to run scripts/build_widget.py", "scripts/build_widget.py" not in custom_widgets_doc)

main_doc = render_static_doc()
check("main doc references build_widget.py (satisfies the every-split-file-linked invariant)", "build_widget.py" in main_doc)


# ---------- write_tempui_docs writes the script into a fresh .desk_temp ----------


def test_write_tempui_docs_writes_the_script():
    with tempfile.TemporaryDirectory() as d:
        temp_dir = Path(d) / ".desk_temp"
        temp_dir.mkdir()
        write_tempui_docs(temp_dir)
        script_path = temp_dir / BUILD_WIDGET_SCRIPT_FILENAME
        check("build_widget.py written to a fresh .desk_temp", script_path.is_file())
        check("written content matches SPLIT_DOC_CONTENT", script_path.read_text() == SPLIT_DOC_CONTENT[BUILD_WIDGET_SCRIPT_FILENAME])


def test_ensure_docs_current_refreshes_a_missing_script():
    with tempfile.TemporaryDirectory() as d:
        temp_dir = Path(d) / ".desk_temp"
        temp_dir.mkdir()
        write_tempui_docs(temp_dir)
        script_path = temp_dir / BUILD_WIDGET_SCRIPT_FILENAME
        script_path.unlink()
        check("script removed for this test", not script_path.exists())
        ensure_docs_current(temp_dir)
        check("ensure_docs_current restores the missing script", script_path.is_file())


def test_ensure_docs_current_refreshes_a_stale_script():
    with tempfile.TemporaryDirectory() as d:
        temp_dir = Path(d) / ".desk_temp"
        temp_dir.mkdir()
        write_tempui_docs(temp_dir)
        script_path = temp_dir / BUILD_WIDGET_SCRIPT_FILENAME
        script_path.write_text("# an old, stale copy of the script\n")
        # Simulate an older version by rewriting the main doc's own
        # version marker down, matching how ensure_docs_current detects
        # staleness for the whole set.
        doc_path = temp_dir / "desk-temporary-ui.md"
        stale_text = doc_path.read_text().replace(f"version: {TEMPUI_DOC_VERSION}", "version: 1")
        doc_path.write_text(stale_text)
        ensure_docs_current(temp_dir)
        check("ensure_docs_current refreshes a stale script back to current content", script_path.read_text() == SPLIT_DOC_CONTENT[BUILD_WIDGET_SCRIPT_FILENAME])


def test_generated_script_actually_runs_end_to_end():
    if not subprocess.run(["which", "tsc"], capture_output=True).returncode == 0:
        check("tsc available for end-to-end check", False)
        return
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        temp_dir = project_dir / ".desk_temp"
        temp_dir.mkdir()
        write_tempui_docs(temp_dir)
        script_path = temp_dir / BUILD_WIDGET_SCRIPT_FILENAME

        widget_dir = temp_dir / "widgets" / "hello3"
        widget_dir.mkdir(parents=True)
        (widget_dir / "widget.json").write_text(
            json.dumps({"keyword": "Hello3Widget", "label": "Hello3", "width": 300, "height": 200})
        )
        (widget_dir / "tsconfig.json").write_text(
            json.dumps({"compilerOptions": {"strict": True, "target": "ES2019", "lib": ["DOM", "ES2019"], "outDir": "build"}})
        )
        (widget_dir / "hello3.ts").write_text(
            "class Hello3Widget extends HTMLElement {\n"
            "  connectedCallback(): void {\n"
            '    const t = document.getElementById("hello3-template") as HTMLTemplateElement;\n'
            '    this.attachShadow({ mode: "open" }).appendChild(t.content.cloneNode(true));\n'
            "  }\n"
            "}\n"
            'customElements.define("hello3-widget", Hello3Widget);\n'
        )
        (widget_dir / "widget.html").write_text(
            "<!doctype html><html><head>"
            '<template id="hello3-template"><h1>Hello3</h1></template>'
            "<script>\n/* BUILD:COMPILED_JS */\n</script>"
            "</head><body><hello3-widget></hello3-widget></body></html>"
        )

        result = subprocess.run(
            [sys.executable, str(script_path), str(widget_dir.relative_to(project_dir))],
            cwd=project_dir, capture_output=True, text=True,
        )
        check("generated script ran successfully", result.returncode == 0)
        out_path_line = result.stdout.strip()
        check("script printed the written tempui file's path", out_path_line != "")
        written_path = project_dir / out_path_line
        check("the printed path actually exists", written_path.is_file())
        content = written_path.read_text()
        check("output is a valid DefineWidget tempui file", content.startswith("DefineWidget\tHello3Widget\tHello3"))
        html_b64 = "".join(
            line.split("\t", 1)[1] for line in content.splitlines() if line.startswith("Html\t")
        )
        decoded = base64.b64decode(html_b64).decode("utf-8")
        check("compiled JS was substituted into the output HTML", "Hello3Widget extends HTMLElement" in decoded)


test_write_tempui_docs_writes_the_script()
test_ensure_docs_current_refreshes_a_missing_script()
test_ensure_docs_current_refreshes_a_stale_script()
test_generated_script_actually_runs_end_to_end()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
