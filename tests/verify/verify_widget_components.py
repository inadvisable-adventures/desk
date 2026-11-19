"""TODO d34f8ed: shared web components -- a widget lists `"components"` in
widget.json and the build compiles each component's .ts ahead of its own files
and injects the component's template.html. Two libraries: desk-wide (Desk's
shared-components/, static) and per-project (desk_widgets/_shared/components/,
mutable). Covers resolution rules and errors, the real build (run in a
QtWebEngine page), the generated .desk_temp/build_widget.py producing
byte-identical HTML, and staleness-watch inputs."""
import base64
import json
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

import desk.shell.window  # noqa: E402,F401  (must precede QApplication)

from PyQt6.QtCore import QCoreApplication, QEvent, QUrl  # noqa: E402
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from desk.custom_widgets import (  # noqa: E402
    SourceBuildError, build_from_source, external_source_files, resolve_components,
)
from desk.temp_ui import _BUILD_WIDGET_SCRIPT  # noqa: E402

app = QApplication(sys.argv)
passed = failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


def pump(seconds=0.2, until=None):
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        if until and until():
            return True
        time.sleep(0.01)
    return until() if until else None


def run_js(view, code):
    box = {}
    view.page().runJavaScript(f"JSON.stringify((function(){{{code}}})())", lambda r: box.setdefault("r", r))
    pump(2.0, until=lambda: "r" in box)
    return json.loads(box["r"]) if box.get("r") is not None else None


PILL_TS = '''class PillLabel extends HTMLElement {
  constructor() {
    super();
    const template = document.getElementById("pill-label-template") as HTMLTemplateElement;
    this.attachShadow({ mode: "open" }).appendChild(template.content.cloneNode(true));
  }
  connectedCallback(): void {
    (this.shadowRoot!.querySelector("span") as HTMLElement).textContent = this.getAttribute("text") ?? "";
  }
}
customElements.define("pill-label", PillLabel);
'''
PILL_TEMPLATE = '<template id="pill-label-template"><span class="pill"></span></template>\n'
DEMO_TS = '''const mount = document.getElementById("mount") as HTMLElement;
const sel = document.createElement("desk-select") as HTMLElement & { value: string };
sel.innerHTML = '<option value="a">Alpha</option><option value="b">Beta</option>';
sel.value = "b";
mount.appendChild(sel);
const pill = document.createElement("pill-label");
pill.setAttribute("text", "hello");
mount.appendChild(pill);
'''
HTML = '<!doctype html>\n<html><body>\n<div id="mount"></div>\n<script>\n/* BUILD:COMPILED_JS */\n</script>\n</body></html>\n'


def make_project(root: Path, *, with_files=True, components=("desk-select", "pill-label"), html=HTML):
    lib = root / "desk_widgets/_shared/components/pill-label"
    lib.mkdir(parents=True, exist_ok=True)
    (lib / "pill-label.ts").write_text(PILL_TS)
    (lib / "template.html").write_text(PILL_TEMPLATE)
    w = root / "desk_widgets/demo"
    w.mkdir(parents=True, exist_ok=True)
    (w / "demo.ts").write_text(DEMO_TS)
    (w / "widget.html").write_text(html)
    cfg = {"compilerOptions": {"target": "es2020", "lib": ["es2020", "dom"], "strict": True, "outDir": "out"}}
    if with_files:
        cfg["files"] = ["demo.ts"]
    (w / "tsconfig.json").write_text(json.dumps(cfg))
    (w / "widget.json").write_text(json.dumps(
        {"keyword": "Demo", "label": "Demo", "width": 300, "height": 200, "components": list(components)}))
    return w


# ---------------- resolution ----------------
with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    make_project(root)
    got = resolve_components(["desk-select", "pill-label", "desk:desk-select"], root)
    check("bare names resolve to their library; duplicates dropped",
          [(c.name, c.scope) for c in got] == [("desk-select", "desk"), ("pill-label", "project")])
    check("component paths", got[0].ts == REPO_ROOT / "shared-components/desk-select/desk-select.ts" and got[1].template is not None)
    check("a component without template.html (document-editor-base) has template None",
          resolve_components(["document-editor-base"], root)[0].template is None)

    def fails(names, fragment, project=root):
        try:
            resolve_components(names, project)
        except SourceBuildError as e:
            return fragment in str(e)
        return False

    check("unknown name is an error", fails(["nope"], "not found"))
    check("invalid names are errors", fails(["Bad_Name"], "invalid component") and fails(["other:x"], "invalid component"))
    check("project: prefix won't find a desk-wide one", fails(["project:desk-select"], "not found"))
    # same name in both libraries -> ambiguous unless pinned
    clash = root / "desk_widgets/_shared/components/desk-select"
    clash.mkdir(parents=True)
    (clash / "desk-select.ts").write_text("// project override\n")
    shadow = resolve_components(["desk-select"], root)[0]
    check("a bare name in both libraries resolves to the project copy", shadow.scope == "project" and shadow.directory == clash)
    pinned = resolve_components(["desk:desk-select", "project:desk-select"], root)
    check("prefixes pin each scope", [(c.name, c.scope) for c in pinned] == [("desk-select", "desk"), ("desk-select", "project")])
    shutil.rmtree(clash)

# ---------------- the real build, in a browser page ----------------
with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    widget = make_project(root)
    build_dir = build_from_source(root, "desk_widgets/demo")
    check("build succeeds", build_dir is not None and (build_dir / "index.html").is_file())
    html = (build_dir / "index.html").read_text() if build_dir else ""
    check("both templates injected right after <body>", html.index('id="desk-select-template"') < html.index('id="pill-label-template"') < html.index('id="mount"'))
    check("component compiled ahead of the widget's own code",
          html.index('customElements.define("desk-select"') < html.index('customElements.define("pill-label"') < html.index('document.getElementById("mount")'))
    check("the widget's tsconfig `files` still governs: demo.ts compiled once", html.count('const sel = document.createElement("desk-select")') == 1)
    view = QWebEngineView()
    view.resize(400, 300)
    loaded = {}
    view.loadFinished.connect(lambda ok: loaded.setdefault("ok", ok))
    view.setHtml(html, QUrl("http://localhost/"))
    view.show()
    pump(10.0, until=lambda: "ok" in loaded)
    r = run_js(view, """
      const sel = document.querySelector('desk-select'); const pill = document.querySelector('pill-label');
      return {value: sel.value, label: sel.shadowRoot.querySelector('.label').textContent.trim(),
              pill: pill.shadowRoot.querySelector('span').textContent};
    """)
    check("desk-wide component works with no hand-pasted template (value set from attribute-less markup)", r and r["value"] == "b" and r["label"] == "Beta")
    check("project component works too", r and r["pill"] == "hello")

    # watch inputs: project-library files only (desk-wide is static)
    ext = {p.as_posix() for p in external_source_files(widget)}
    lib = (root / "desk_widgets/_shared/components/pill-label").as_posix()
    check("project component .ts and template are watched", f"{lib}/pill-label.ts" in ext and f"{lib}/template.html" in ext)
    check("desk-wide component files are not", not any("shared-components" in p for p in ext))

    # the generated .desk_temp/build_widget.py builds byte-identical HTML
    temp = root / ".desk_temp"
    temp.mkdir()
    (temp / "build_widget.py").write_text(_BUILD_WIDGET_SCRIPT)
    shutil.copytree(REPO_ROOT / "shared-components", temp / "shared-components")
    proc = subprocess.run([sys.executable, str(temp / "build_widget.py"), "desk_widgets/demo"], cwd=root, capture_output=True, text=True)
    check("generated build_widget.py succeeds", proc.returncode == 0)
    if proc.returncode == 0:
        text = Path(root / proc.stdout.strip()).read_text()
        b64 = "".join(line.split("\t", 1)[1] for line in text.splitlines() if line.startswith("Html\t"))
        check("...and produces byte-identical HTML to Desk's own build", base64.b64decode(b64).decode() == html)
    else:
        print(proc.stderr)

    # without a tsconfig "files" list (all .ts under the directory), components still lead
    w2 = make_project(root, with_files=False)
    b2 = build_from_source(root, "desk_widgets/demo")
    h2 = (b2 / "index.html").read_text() if b2 else ""
    check("no `files` list: build succeeds, components still first",
          b2 is not None and h2.index('customElements.define("desk-select"') < h2.index('document.getElementById("mount")'))
    shutil.rmtree(w2 / "out", ignore_errors=True)

    # marker placement, and an already hand-pasted template is not duplicated
    placed = HTML.replace('<div id="mount">', '<!-- BUILD:COMPONENT_TEMPLATES -->\n<div id="mount">')
    make_project(root, html=placed)
    h3 = (build_from_source(root, "desk_widgets/demo") / "index.html").read_text()
    check("BUILD:COMPONENT_TEMPLATES marker controls placement", "BUILD:COMPONENT_TEMPLATES" not in h3 and h3.index('id="pill-label-template"') < h3.index('id="mount"'))
    pasted = HTML.replace('<div id="mount">', PILL_TEMPLATE + '<div id="mount">')
    make_project(root, html=pasted)
    h4 = (build_from_source(root, "desk_widgets/demo") / "index.html").read_text()
    check("a template the widget already pastes is not injected twice", h4.count('id="pill-label-template"') == 1 and h4.count('id="desk-select-template"') == 1)

    # failures are clean (None), not a crash
    make_project(root, components=("does-not-exist",))
    check("an unknown component fails the build cleanly", build_from_source(root, "desk_widgets/demo") is None)
    make_project(root, html="<div></div>\n<script>\n/* BUILD:COMPILED_JS */\n</script>\n")
    check("no <body> and no marker: clean failure", build_from_source(root, "desk_widgets/demo") is None)
    (root / "desk_widgets/demo/widget.json").write_text(json.dumps({"keyword": "D", "label": "D", "width": 1, "height": 1, "components": "desk-select"}))
    check("malformed components value fails cleanly", build_from_source(root, "desk_widgets/demo") is None)

    # a widget with no components is untouched
    (root / "desk_widgets/demo/widget.json").write_text(json.dumps({"keyword": "D", "label": "D", "width": 1, "height": 1}))
    (root / "desk_widgets/demo/widget.html").write_text(HTML)
    (root / "desk_widgets/demo/demo.ts").write_text("document.body.dataset.ok = '1';\n")
    shutil.rmtree(root / "desk_widgets/demo/.build", ignore_errors=True)
    plain = build_from_source(root, "desk_widgets/demo")
    check("no components: plain build, no injected templates, no generated tsconfig",
          plain is not None and "<template" not in (plain / "index.html").read_text()
          and not (plain / "tsconfig.components.json").exists())

# ---------------- docs ----------------
from desk.temp_ui import CURRENT_TAGS, SPLIT_DOC_CONTENT, _NEW_FEATURES  # noqa: E402
_CUSTOM_WIDGETS_DOC = SPLIT_DOC_CONTENT["tempui-custom-widgets.md"]

doc = _CUSTOM_WIDGETS_DOC
check("doc explains the widget.json field, both libraries and the precedence rule",
      '"components"' in doc and "desk_widgets/_shared/components/<name>/" in doc and "desk:<name>" in doc and "project:<name>" in doc)
check("doc covers the placement marker and the authoring contract",
      "BUILD:COMPONENT_TEMPLATES" in doc and "Authoring a component" in doc and "innerHTML" in doc)
tag = next((t for t in CURRENT_TAGS if t.endswith("#d34f8ed")), None)
check("tagged and in the changelog", tag is not None and tag in _NEW_FEATURES)
check("generated build_widget.py documents/supports components", "components" in _BUILD_WIDGET_SCRIPT and "BUILD:COMPONENT_TEMPLATES" in _BUILD_WIDGET_SCRIPT)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
