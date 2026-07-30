import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")

import desk.shell.widget_frame  # noqa: E402  (imported before QApplication -- WebEngine ordering)
import desk.shell.canvas  # noqa: E402
# TODO 78bfa41: canvas.py's own QWebEngineView import (previously used
# by the now-removed _scrollable_at) was the thing actually satisfying
# the "import WebEngine before QApplication" ordering requirement above
# -- import it explicitly instead of depending on that as an incidental
# side effect of an unrelated module.
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402,F401

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk.hotreload import HotReloadBroker  # noqa: E402
from desk.server.runner import start_server  # noqa: E402
from desk.shell.chromium_widget import ChromiumWidget  # noqa: E402
from desk.temp_ui import (  # noqa: E402
    NEW_FEATURES_DOC_FILENAME,
    SPLIT_DOC_CONTENT,
    TEMPUI_DOC_VERSION,
    _CUSTOM_WIDGETS_DOC,
)

REPO_ROOT = Path("/Users/mphair/inadvisable-adventures/desk")
COMPONENT_DIR = REPO_ROOT / "shared-components" / "document-editor-base"

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


def pump(seconds=2.0):
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)


def pump_until(predicate, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        app.processEvents()
        time.sleep(0.02)
    return predicate()


# ---------- files / docs ----------


def test_document_editor_base_files_exist():
    check("document-editor-base.ts exists", (COMPONENT_DIR / "document-editor-base.ts").is_file())
    check("README.md exists", (COMPONENT_DIR / "README.md").is_file())


test_document_editor_base_files_exist()


def test_doc_mentions_the_new_component():
    check("TEMPUI_DOC_VERSION is >= 25", TEMPUI_DOC_VERSION >= 25)
    # The "Reusable UI components" section describes components
    # generically (it didn't name "hsv-color-picker" literally either)
    # -- but it does explain the copy-vs-import distinction this
    # component's own README relies on.
    check(
        "custom-widgets doc explains the copy-source-in vs. separate-file distinction",
        "concatenates a widget's compiled" in _CUSTOM_WIDGETS_DOC,
    )
    new_features_doc = SPLIT_DOC_CONTENT[NEW_FEATURES_DOC_FILENAME]
    check("new-features doc has a Version 25 entry for document-editor-base", "Version 25" in new_features_doc and "document-editor-base" in new_features_doc)


test_doc_mentions_the_new_component()


# ---------- real tsc compile + real end-to-end Bridge-driven test ----------

TEST_SUBCLASS_TS = """
interface NotesDoc {
  title: string;
  body: string;
}

class TestNotesElement extends DocumentEditorBase<NotesDoc> {
  protected readonly directory = "test-notes-docs";
  protected readonly extension = "md";

  private titleInput: HTMLInputElement | null = null;
  private bodyInput: HTMLTextAreaElement | null = null;
  private errorEl: HTMLElement | null = null;
  private unlockedEl: HTMLElement | null = null;
  private lockedEl: HTMLElement | null = null;

  protected emptyDoc(title: string): NotesDoc {
    return { title, body: "" };
  }

  protected parse(text: string, fallbackTitle: string): NotesDoc {
    const lines = text.split("\\n");
    const titleLine = (lines[0] ?? "").replace(/^#\\s*/, "");
    const body = lines.slice(1).join("\\n").replace(/^\\n+/, "");
    return { title: titleLine || fallbackTitle, body };
  }

  protected serialize(doc: NotesDoc): string {
    return `# ${doc.title}\\n\\n${doc.body}`;
  }

  protected onConnected(): void {
    const template = document.getElementById("test-notes-template");
    if (!(template instanceof HTMLTemplateElement)) throw new Error("template not found");
    const shadow = this.attachShadow({ mode: "open" });
    shadow.appendChild(template.content.cloneNode(true));

    this.titleInput = shadow.getElementById("title-input") as HTMLInputElement;
    this.bodyInput = shadow.getElementById("body-input") as HTMLTextAreaElement;
    this.errorEl = shadow.getElementById("error");
    this.unlockedEl = shadow.getElementById("unlocked");
    this.lockedEl = shadow.getElementById("locked");

    shadow.getElementById("create-btn")?.addEventListener("click", () => {
      void this.create(this.titleInput?.value ?? "");
    });
    shadow.getElementById("load-btn")?.addEventListener("click", () => {
      void this.load(this.titleInput?.value ?? "");
    });
    this.bodyInput?.addEventListener("input", () => {
      this.doc.body = this.bodyInput?.value ?? "";
      void this.save();
    });
  }

  protected onEnterLocked(): void {
    if (this.unlockedEl) this.unlockedEl.style.display = "none";
    if (this.lockedEl) this.lockedEl.style.display = "";
    if (this.bodyInput) this.bodyInput.value = this.doc.body;
  }

  protected onEnterUnlocked(): void {
    if (this.unlockedEl) this.unlockedEl.style.display = "";
    if (this.lockedEl) this.lockedEl.style.display = "none";
  }

  protected onError(message: string): void {
    if (this.errorEl) {
      this.errorEl.textContent = message;
      this.errorEl.setAttribute("data-visible", "true");
    }
  }
}

customElements.define("test-notes", TestNotesElement);
"""

TSCONFIG = """
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
  "files": ["document-editor-base.ts", "test-notes.ts"]
}
"""

TEST_NOTES_TEMPLATE_HTML = """
<template id="test-notes-template">
  <input id="title-input" type="text" />
  <div id="unlocked">
    <button id="create-btn">Create</button>
    <button id="load-btn">Load</button>
  </div>
  <div id="locked" style="display:none">
    <textarea id="body-input"></textarea>
  </div>
  <div id="error" data-visible="false"></div>
</template>
<test-notes></test-notes>
"""


class _FakeDesk:
    def __init__(self, directory):
        self.directory = directory


class _FakeGuiWindow:
    def __init__(self, desk_directory):
        self.current_desk = _FakeDesk(desk_directory)
        self._storage = {}

    def get_html_widget_local_storage(self, instance_id):
        return self._storage.get(instance_id, {})

    def set_html_widget_local_storage(self, instance_id, data):
        self._storage[instance_id] = data


def _build_test_widget_directory(build_root: Path) -> Path:
    """Real tsc --strict compile of the shared document-editor-base.ts
    plus a small real subclass (mirroring the base-class-first-in-files
    ordering its own README recommends verifying), assembled into a
    real kind:"html" widget directory `start_server` can serve."""
    src_dir = build_root / "src"
    src_dir.mkdir()
    shutil.copy(COMPONENT_DIR / "document-editor-base.ts", src_dir / "document-editor-base.ts")
    (src_dir / "test-notes.ts").write_text(TEST_SUBCLASS_TS)
    (src_dir / "tsconfig.json").write_text(TSCONFIG)
    result = subprocess.run(["tsc", "-p", str(src_dir)], capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(f"tsc failed:\n{result.stdout}{result.stderr}")

    # Mirrors build_widget.py's own concatenation shape exactly: every
    # compiled .js file, sorted alphabetically -- confirms real
    # base-before-subclass ordering for these two specific filenames,
    # the same thing the README warns isn't guaranteed in general.
    js_files = sorted((src_dir / "build").glob("*.js"))
    combined_js = "".join(p.read_text() for p in js_files)

    widgets_dir = build_root / "widgets"
    widget_dir = widgets_dir / "test-notes"
    widget_dir.mkdir(parents=True)
    (widget_dir / "widget.json").write_text(json.dumps({"kind": "html", "name": "Test Notes", "capabilities": ["fs"]}))
    (widget_dir / "index.html").write_text(
        f"<!doctype html><html><body>{TEST_NOTES_TEMPLATE_HTML}<script>{combined_js}</script></body></html>"
    )
    return widgets_dir


def _click(widget, selector):
    widget.page().runJavaScript(
        f"document.querySelector('test-notes').shadowRoot.querySelector('{selector}').click();"
    )


def _set_value(widget, selector, value):
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    widget.page().runJavaScript(
        f"""
        (function() {{
          const el = document.querySelector('test-notes').shadowRoot.querySelector('{selector}');
          el.value = '{escaped}';
          el.dispatchEvent(new Event('input', {{bubbles: true}}));
        }})();
        """
    )


def _read(widget, js_expr, timeout=8.0):
    holder = []
    widget.page().runJavaScript(js_expr, lambda r: holder.append(r))
    pump_until(lambda: bool(holder), timeout=timeout)
    return holder[-1] if holder else None


def test_document_editor_base_full_lifecycle_real_browser_real_bridge_calls():
    with tempfile.TemporaryDirectory() as d:
        build_root = Path(d) / "build"
        build_root.mkdir()
        widgets_dir = _build_test_widget_directory(build_root)
        check("tsc --strict compiled the base class + a real subclass cleanly", True)

        desk_dir = Path(d) / "my-project"
        desk_dir.mkdir()
        handle = start_server(widgets_dir=widgets_dir)
        fake_window = _FakeGuiWindow(desk_dir)
        handle.gui_bridge.attach(fake_window)
        try:
            broker = HotReloadBroker()

            # This is the exact bug shape TODO ad20867 fixes and this
            # base class relies on: test-notes-docs/ doesn't exist
            # anywhere under desk_dir yet.
            check("the target directory genuinely doesn't exist yet", not (desk_dir / "test-notes-docs").exists())

            widget = ChromiumWidget("test-notes", "inst-1", handle.widget_url("test-notes"), handle.token, broker)
            pump(2)

            _set_value(widget, "#title-input", "My First Note")
            _click(widget, "#create-btn")
            pump(2)

            expected_path = desk_dir / "test-notes-docs" / "my-first-note.md"
            check("create() derived the right kebab-case path and created the missing directory", expected_path.is_file())
            check("the new document has the expected initial content", expected_path.read_text() == "# My First Note\n\n")
            locked_display = _read(widget, "document.querySelector('test-notes').shadowRoot.getElementById('locked').style.display")
            check("the widget entered the locked (editor) state after create", locked_display == "")

            _set_value(widget, "#body-input", "hello world")
            pump(2)
            check("editing the body auto-saved for real", expected_path.read_text() == "# My First Note\n\nhello world")

            # A second instance trying to create the same title again
            # must refuse -- never silently clobber.
            widget2 = ChromiumWidget("test-notes", "inst-2", handle.widget_url("test-notes"), handle.token, broker)
            pump(2)
            _set_value(widget2, "#title-input", "My First Note")
            _click(widget2, "#create-btn")
            pump(2)
            error_visible = _read(widget2, "document.querySelector('test-notes').shadowRoot.getElementById('error').getAttribute('data-visible')")
            check("creating over an already-existing document is refused, not silently clobbered", error_visible == "true")
            check("the original document's content is untouched by the refused create", expected_path.read_text() == "# My First Note\n\nhello world")

            # A fresh instance loading the same title gets the real content back.
            widget3 = ChromiumWidget("test-notes", "inst-3", handle.widget_url("test-notes"), handle.token, broker)
            pump(2)
            _set_value(widget3, "#title-input", "My First Note")
            _click(widget3, "#load-btn")
            pump(2)
            loaded_body = _read(widget3, "document.querySelector('test-notes').shadowRoot.getElementById('body-input').value")
            check("load() restores the real saved content into a fresh instance", loaded_body == "hello world")

            # A fresh page load reusing the SAME instance id (e.g.
            # reopening Desk) auto-restores into the locked state,
            # without an explicit Load click.
            widget4 = ChromiumWidget("test-notes", "inst-1", handle.widget_url("test-notes"), handle.token, broker)
            pump(2)
            restored_locked_display = _read(widget4, "document.querySelector('test-notes').shadowRoot.getElementById('locked').style.display")
            check("a fresh instance sharing the same instance id auto-restores the last-open document", restored_locked_display == "")
        finally:
            handle.stop()


test_document_editor_base_full_lifecycle_real_browser_real_bridge_calls()


print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
