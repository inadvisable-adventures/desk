"""TODO b04682e / 5ee7493: the shared-component catalog and vendoring --
copying the desk-wide components a widget uses into the project library and
pinning them, so a build needs nothing from the opening Desk."""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.window  # noqa: E402,F401  (must precede QApplication)

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from desk.custom_widgets import SourceBuildError, build_from_source, resolve_components  # noqa: E402
from desk.shell import current_context  # noqa: E402
from desk.shell.desk_mcp_server import _list_shared_components, _vendor_widget_components  # noqa: E402
from desk.widget_components import (  # noqa: E402
    catalog_signature, list_catalog, vendor_component, vendor_widget_components,
)

passed = failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


def text(result):
    return result["content"][0]["text"]


def write_widget(root: Path, rel: str, components):
    w = root / rel
    w.mkdir(parents=True, exist_ok=True)
    (w / "widget.json").write_text(json.dumps({"keyword": "K", "label": "L", "width": 1, "height": 1, "components": components}))
    (w / f"{w.name}.ts").write_text("document.body.dataset.x = '1';\n")
    (w / "widget.html").write_text('<html><body><script>\n/* BUILD:COMPILED_JS */\n</script></body></html>\n')
    (w / "tsconfig.json").write_text(json.dumps({"compilerOptions": {"target": "es2020", "lib": ["es2020", "dom"], "outDir": "out"}, "files": [w.name + ".ts"]}))
    return w


with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    desk_lib = root / "fake-desk-lib"
    for name, readme in (("alpha", "# alpha\n\nAn alpha element.\nSecond line.\n\nMore.\n"), ("beta", None)):
        (desk_lib / name).mkdir(parents=True)
        (desk_lib / name / f"{name}.ts").write_text(f"class {name.title()} extends HTMLElement {{}}\n")
        if readme:
            (desk_lib / name / "README.md").write_text(readme)
    (desk_lib / "alpha" / "template.html").write_text('<template id="alpha-template"><i></i></template>\n')
    proj_comp = root / "desk_widgets/_shared/components/gamma"
    proj_comp.mkdir(parents=True)
    (proj_comp / "gamma.ts").write_text("class Gamma extends HTMLElement {}\n")
    write_widget(root, "desk_widgets/demo", ["alpha", "gamma"])
    write_widget(root, ".desk_temp/widgets/other", ["beta"])

    # ---- catalog ----
    cat = {(e.scope, e.name): e for e in list_catalog(root, desk_lib)}
    check("catalog has both libraries", set(cat) == {("desk", "alpha"), ("desk", "beta"), ("project", "gamma")})
    check("summary is the README's first prose paragraph, joined", cat[("desk", "alpha")].summary == "An alpha element. Second line.")
    check("no README -> empty summary; flags and files", cat[("desk", "beta")].summary == "" and cat[("desk", "alpha")].has_template and cat[("desk", "alpha")].files == ["README.md", "alpha.ts", "template.html"])
    check("used_by lists promoted and not-yet-promoted source widgets",
          cat[("desk", "alpha")].used_by == ["desk_widgets/demo"] and cat[("project", "gamma")].used_by == ["desk_widgets/demo"]
          and cat[("desk", "beta")].used_by == [".desk_temp/widgets/other"])
    check("nothing vendored yet", not any(e.vendored for e in cat.values()))

    # ---- the real shared library is listed too ----
    real = {e.name for e in list_catalog(root)}
    check("default desk library is Desk's own shared-components/", {"desk-select", "hsv-color-picker", "document-editor-base"} <= real)

    # ---- vendor a component ----
    dest, outcome = vendor_component(root, "alpha", desk_lib)
    check("copies the whole directory", outcome == "copied" and (dest / "alpha.ts").is_file() and (dest / "template.html").is_file() and (dest / "README.md").is_file())
    check("a second vendor is a no-op", vendor_component(root, "alpha", desk_lib)[1] == "unchanged")
    (dest / "alpha.ts").write_text("// customized\n")
    try:
        vendor_component(root, "alpha", desk_lib)
        check("a customized project copy is never overwritten silently", False)
    except SourceBuildError as e:
        check("a customized project copy is never overwritten silently", "customized" in str(e) and (dest / "alpha.ts").read_text() == "// customized\n")
    vendor_component(root, "alpha", desk_lib, overwrite=True)
    check("overwrite restores Desk's copy", "extends HTMLElement" in (dest / "alpha.ts").read_text())
    try:
        vendor_component(root, "nope", desk_lib)
        check("unknown component errors", False)
    except SourceBuildError as e:
        check("unknown component errors", "no desk-wide component" in str(e))
    check("vendored flag shows in the catalog", {e.name: e.vendored for e in list_catalog(root, desk_lib) if e.scope == "desk"} == {"alpha": True, "beta": False})
    import shutil  # noqa: E402
    shutil.rmtree(dest)

    # ---- vendor a widget's components ----
    result = vendor_widget_components(root, "desk_widgets/demo", desk_lib)
    manifest = json.loads((root / "desk_widgets/demo/widget.json").read_text())
    check("copies only desk-wide components; leaves project ones", result.copied == ["alpha"] and result.pinned == ["alpha"])
    check("widget.json pins vendored entries, keeps the rest and its other keys", manifest["components"] == ["project:alpha", "gamma"] and manifest["keyword"] == "K")
    check("describe() reports it", "copied into the project library: alpha" in result.describe() and "project:alpha" in result.describe())
    again = vendor_widget_components(root, "desk_widgets/demo", desk_lib)
    check("idempotent: nothing left to vendor", not again.pinned and "nothing to vendor" in again.describe())
    # the point: resolution no longer needs the opening Desk's library at all
    empty = root / "empty-desk-lib"
    empty.mkdir()
    resolved = resolve_components(manifest["components"], root, empty)
    check("resolves with an EMPTY desk-wide library", [(c.name, c.scope) for c in resolved] == [("alpha", "project"), ("gamma", "project")])
    try:
        resolve_components(["alpha", "gamma"], root / "elsewhere", empty)
        check("(control) an un-vendored widget cannot", False)
    except SourceBuildError:
        check("(control) an un-vendored widget cannot", True)
    shutil.rmtree(root / "desk_widgets/_shared/components/alpha")
    try:
        resolve_components(["project:alpha"], root, desk_lib)
        check("a pinned entry fails loudly if the project copy is removed (no silent fallback to Desk's)", False)
    except SourceBuildError as e:
        check("a pinned entry fails loudly if the project copy is removed (no silent fallback to Desk's)", "not found" in str(e))
    vendor_component(root, "alpha", desk_lib)  # put it back

    # ---- signature changes when a library file changes ----
    before = catalog_signature(root, desk_lib)
    (root / "desk_widgets/_shared/components/gamma/README.md").write_text("# gamma\n\nNew.\n")
    check("catalog_signature changes on an edit", catalog_signature(root, desk_lib) != before)

    # ---- MCP tools ----
    current_context.set_current_desk_directory(root)
    listed = json.loads(text(asyncio.run(_list_shared_components.handler({}))))
    check("desk_list_shared_components lists both scopes with usage",
          {(e["scope"], e["name"]) for e in listed} >= {("project", "gamma"), ("project", "alpha"), ("desk", "desk-select")}
          and next(e for e in listed if e["name"] == "gamma")["summary"] == "New.")
    write_widget(root, "desk_widgets/demo2", ["desk-select", "hsv-color-picker"])
    res = asyncio.run(_vendor_widget_components.handler({"source_path": "desk_widgets/demo2"}))
    check("desk_vendor_widget_components vendors Desk's real components", not res["is_error"] and "desk-select" in text(res))
    check("...copies real files and pins them",
          (root / "desk_widgets/_shared/components/desk-select/template.html").is_file()
          and json.loads((root / "desk_widgets/demo2/widget.json").read_text())["components"] == ["project:desk-select", "project:hsv-color-picker"])
    check("a bad path is a clean tool error", asyncio.run(_vendor_widget_components.handler({"source_path": "desk_widgets/none"}))["is_error"])
    current_context.set_current_desk_directory(None)
    check("no Desk directory is a clean tool error", asyncio.run(_vendor_widget_components.handler({"source_path": "x"}))["is_error"])

    # ---- the deployed build: nothing but project files ----
    built = build_from_source(root, "desk_widgets/demo2")
    html = (built / "index.html").read_text() if built else ""
    check("a vendored widget builds, with both components", built is not None and 'id="desk-select-template"' in html and "hsv-color-picker" in html)
    (root / "desk_widgets/_shared/components/desk-select/desk-select.ts").write_text(
        (root / "desk_widgets/_shared/components/desk-select/desk-select.ts").read_text() + "\n// PROJECT-COPY-MARKER\n")
    rebuilt = build_from_source(root, "desk_widgets/demo2")
    check("editing the project copy changes the build (it is what's built, not Desk's)", rebuilt is not None and "PROJECT-COPY-MARKER" in (rebuilt / "index.html").read_text()
          and "PROJECT-COPY-MARKER" not in (REPO_ROOT / "shared-components/desk-select/desk-select.ts").read_text())

# ---------------- docs ----------------
from desk.temp_ui import CURRENT_TAGS, _CUSTOM_WIDGETS_DOC, _NEW_FEATURES  # noqa: E402

for suffix in ("#5ee7493", "#b04682e"):
    tag = next((t for t in CURRENT_TAGS if t.endswith(suffix)), None)
    check(f"tag {suffix} is registered with a changelog entry", tag is not None and tag in _NEW_FEATURES)
check("doc covers the catalog widget, the MCP tools and deploy/vendoring",
      "**Components** widget" in _CUSTOM_WIDGETS_DOC and "desk_list_shared_components" in _CUSTOM_WIDGETS_DOC
      and "desk_vendor_widget_components" in _CUSTOM_WIDGETS_DOC and "Deploying a project" in _CUSTOM_WIDGETS_DOC)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
