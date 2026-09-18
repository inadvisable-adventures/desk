import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.widget_frame  # noqa: E402  (imported before QApplication -- WebEngine ordering)
import desk.shell.canvas  # noqa: E402
# TODO 78bfa41: canvas.py's own QWebEngineView import (previously used
# by the now-removed _scrollable_at) was the thing actually satisfying
# the "import WebEngine before QApplication" ordering requirement above
# -- import it explicitly instead of depending on that as an incidental
# side effect of an unrelated module.
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402,F401

from PyQt6.QtCore import QUrl  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk.shell.temp_ui_manager import TempUiManager  # noqa: E402
from desk.temp_ui import (  # noqa: E402
    NEW_FEATURES_DOC_FILENAME,
    SHARED_COMPONENTS_DIRNAME,
    TEMPUI_DOC_VERSION,
    SPLIT_DOC_CONTENT,
    _repo_shared_components_dir,
    sync_shared_components,
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


# ---------- shared-components/ itself, checked into this repo ----------


def test_hsv_color_picker_files_exist():
    component_dir = REPO_ROOT / "shared-components" / "hsv-color-picker"
    check("hsv-color-picker.ts exists", (component_dir / "hsv-color-picker.ts").is_file())
    check("template.html exists", (component_dir / "template.html").is_file())
    check("README.md exists", (component_dir / "README.md").is_file())
    check("shared-components/README.md (top-level) exists", (REPO_ROOT / "shared-components" / "README.md").is_file())


test_hsv_color_picker_files_exist()


# ---------- sync_shared_components ----------


def test_sync_shared_components_copies_the_real_library():
    with tempfile.TemporaryDirectory() as d:
        temp_dir = Path(d) / ".desk_temp"
        temp_dir.mkdir()
        sync_shared_components(temp_dir)
        destination = temp_dir / SHARED_COMPONENTS_DIRNAME
        check("hsv-color-picker/ copied", (destination / "hsv-color-picker" / "hsv-color-picker.ts").is_file())
        check("component README copied", (destination / "hsv-color-picker" / "README.md").is_file())
        check(
            "copied .ts content matches the source exactly",
            (destination / "hsv-color-picker" / "hsv-color-picker.ts").read_text()
            == (_repo_shared_components_dir() / "hsv-color-picker" / "hsv-color-picker.ts").read_text(),
        )


test_sync_shared_components_copies_the_real_library()


def test_sync_shared_components_is_a_full_mirror_not_an_additive_merge():
    with tempfile.TemporaryDirectory() as d:
        temp_dir = Path(d) / ".desk_temp"
        temp_dir.mkdir()
        sync_shared_components(temp_dir)
        destination = temp_dir / SHARED_COMPONENTS_DIRNAME
        stale_marker = destination / "some-removed-component" / "old.ts"
        stale_marker.parent.mkdir(parents=True)
        stale_marker.write_text("leftover from a component that no longer exists")

        sync_shared_components(temp_dir)
        check("a stale leftover file is gone after a second sync (full mirror)", not stale_marker.exists())
        check("the real component is still there", (destination / "hsv-color-picker" / "hsv-color-picker.ts").is_file())


test_sync_shared_components_is_a_full_mirror_not_an_additive_merge()


def test_sync_shared_components_missing_source_is_a_clean_noop():
    import desk.temp_ui as temp_ui_module

    original = temp_ui_module._repo_shared_components_dir
    try:
        temp_ui_module._repo_shared_components_dir = lambda: Path("/nonexistent/shared-components")
        with tempfile.TemporaryDirectory() as d:
            temp_dir = Path(d) / ".desk_temp"
            temp_dir.mkdir()
            temp_ui_module.sync_shared_components(temp_dir)  # must not raise
            check("no shared-components dir created when the source doesn't exist", not (temp_dir / SHARED_COMPONENTS_DIRNAME).exists())
    finally:
        temp_ui_module._repo_shared_components_dir = original


test_sync_shared_components_missing_source_is_a_clean_noop()


def test_provision_mirrors_shared_components():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        mgr = TempUiManager()
        try:
            temp_dir = mgr.provision(directory, lambda: True, lambda: True)
            check("provision returned a real temp_dir", temp_dir is not None)
            check(
                "provision's own .desk_temp/shared-components/hsv-color-picker is real",
                (temp_dir / SHARED_COMPONENTS_DIRNAME / "hsv-color-picker" / "hsv-color-picker.ts").is_file(),
            )
        finally:
            mgr.stop()


test_provision_mirrors_shared_components()


# ---------- doc version / new-features bump ----------


def test_doc_version_and_new_features_entry():
    check("TEMPUI_DOC_VERSION is >= 23", TEMPUI_DOC_VERSION >= 23)
    new_features_text = SPLIT_DOC_CONTENT[NEW_FEATURES_DOC_FILENAME]
    check("new-features doc mentions shared-components", "shared-components" in new_features_text)
    check("new-features doc mentions hsv-color-picker", "hsv-color-picker" in new_features_text)

    from desk.temp_ui import _CUSTOM_WIDGETS_DOC

    check("custom-widgets doc has a Reusable UI components section", "Reusable UI components" in _CUSTOM_WIDGETS_DOC)
    # TODO 3fc5331: the section's own wording was revised again once
    # build_widget.py's concatenation-order hazard (TODO d4368bd's own
    # reason to recommend copy-paste-only for a base class) was fixed
    # via tsconfig.json's own "files" array -- import vs.
    # copy+paste+modify is unconditionally fine again, for every
    # component, as long as a base class gets a "files" entry ahead of
    # its subclass's.
    # Whitespace-normalized (collapses this doc's own line-wrapping)
    # before substring matching -- the real wrapped prose breaks a
    # naive multi-word substring check at whichever point it happens to
    # wrap, which isn't what this check cares about.
    normalized_doc = " ".join(_CUSTOM_WIDGETS_DOC.split())
    check(
        "custom-widgets doc explains both import and copy+paste+modify are fine, with the files array for load order",
        "import its file directly" in normalized_doc and '"files"' in normalized_doc and "ahead of" in normalized_doc,
    )


test_doc_version_and_new_features_entry()


# ---------- real tsc compile + real headless-Chrome interaction ----------


def _tsc_available():
    return shutil.which("tsc") is not None


def test_hsv_color_picker_compiles_and_works_in_a_real_browser():
    if not _tsc_available():
        print("SKIP: tsc not available on PATH -- cannot compile-check hsv-color-picker.ts")
        return

    component_dir = REPO_ROOT / "shared-components" / "hsv-color-picker"
    with tempfile.TemporaryDirectory() as d:
        scratch = Path(d)
        shutil.copy(component_dir / "hsv-color-picker.ts", scratch / "hsv-color-picker.ts")
        (scratch / "tsconfig.json").write_text(
            """
            {
              "compilerOptions": {
                "target": "ES2019",
                "lib": ["DOM", "ES2019"],
                "strict": true,
                "noImplicitReturns": true,
                "noUnusedLocals": true,
                "noUnusedParameters": true,
                "module": "none",
                "outDir": "build",
                "noEmitOnError": true
              },
              "files": ["hsv-color-picker.ts"]
            }
            """
        )
        result = subprocess.run(["tsc", "-p", str(scratch)], capture_output=True, text=True)
        check("hsv-color-picker.ts compiles cleanly with tsc --strict", result.returncode == 0)
        if result.returncode != 0:
            print(result.stdout, result.stderr)
            return

        compiled_js = (scratch / "build" / "hsv-color-picker.js").read_text()
        template_html = (component_dir / "template.html").read_text()
        page_path = scratch / "page.html"
        page_path.write_text(
            f"""<!doctype html>
<html><body>
{template_html}
<hsv-color-picker value="#3daee9"></hsv-color-picker>
<script>
{compiled_js}
</script>
</body></html>"""
        )

        view = QWebEngineView()
        view.resize(500, 500)
        loaded = []
        view.loadFinished.connect(lambda ok: loaded.append(ok))
        view.load(QUrl.fromLocalFile(str(page_path)))

        deadline = time.time() + 10
        while time.time() < deadline and not loaded:
            app.processEvents()
            time.sleep(0.02)
        check("real page (compiled component + template) loaded", bool(loaded) and loaded[0])

        # Real synthetic PointerEvents on the wheel/brightness bar --
        # deliberately no real "active pointer" for the browser to
        # capture, exactly the edge case hsv-color-picker.ts's own
        # bindDrag try/catch around setPointerCapture exists for.
        test_js = """
        (function() {
          window.testResult = window.testResult || {};
          var picker = document.querySelector("hsv-color-picker");
          if (!picker) { window.testResult.error = "no picker"; window.testResult.done = true; return; }
          picker.addEventListener("colorchange", function(e) {
            window.testResult.eventCount = (window.testResult.eventCount || 0) + 1;
          });
          window.testResult.initialValue = picker.value;

          var wheel = picker.shadowRoot.getElementById("wheel");
          var rect = wheel.getBoundingClientRect();
          var down = new PointerEvent("pointerdown", {
            clientX: rect.left + rect.width - 1,
            clientY: rect.top + rect.height / 2,
            pointerId: 1,
            bubbles: true
          });
          wheel.dispatchEvent(down);
          window.testResult.afterWheelValue = picker.value;
          window.testResult.eventCountAfterWheel = window.testResult.eventCount;

          var countBefore = window.testResult.eventCount;
          picker.value = "#123456";
          window.testResult.programmaticValue = picker.value;
          window.testResult.eventCountAfterProgrammaticSet = window.testResult.eventCount;
          window.testResult.countBeforeProgrammaticSet = countBefore;
          window.testResult.done = true;
        })();
        """
        view.page().runJavaScript(test_js)

        result_holder = []

        def poll():
            view.page().runJavaScript("JSON.stringify(window.testResult || {})", lambda r: result_holder.append(r))

        deadline = time.time() + 10
        done = False
        while time.time() < deadline and not done:
            poll()
            app.processEvents()
            time.sleep(0.05)
            if result_holder and '"done":true' in result_holder[-1]:
                done = True

        check("test script finished", done)
        import json

        result = json.loads(result_holder[-1]) if result_holder else {}
        check("no JS error running the test script", "error" not in result)
        check("initial .value reflects the value= attribute", result.get("initialValue") == "#3daee9")
        check(
            "dragging the wheel (synthetic PointerEvent) changes .value",
            result.get("afterWheelValue") not in (None, "#3daee9"),
        )
        check("dragging the wheel fires exactly one colorchange event", result.get("eventCountAfterWheel") == 1)
        check(
            "setting .value programmatically updates the value",
            result.get("programmaticValue") == "#123456",
        )
        check(
            "setting .value programmatically does NOT fire colorchange",
            result.get("eventCountAfterProgrammaticSet") == result.get("countBeforeProgrammaticSet"),
        )


test_hsv_color_picker_compiles_and_works_in_a_real_browser()


print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
