import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "app_dsl"))

from codegen import generate  # noqa: E402
from parse import parse_app_definition  # noqa: E402

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


DOM_STUB_JS = """
class Evt {
  constructor(type, opts) {
    this.type = type;
    this.detail = opts && opts.detail;
  }
}
class StubElement {
  constructor(tagName) {
    this.tagName = tagName;
    this.children = [];
    this.parentNode = null;
    this.className = "";
    this.style = { cssText: "" };
    this._listeners = new Map();
  }
  appendChild(child) { this.children.push(child); child.parentNode = this; return child; }
  addEventListener(type, handler) {
    const arr = this._listeners.get(type) || [];
    arr.push(handler);
    this._listeners.set(type, arr);
  }
  dispatchEvent(event) {
    const arr = this._listeners.get(event.type) || [];
    for (const h of arr) h(event);
  }
  querySelectorAll(tag) {
    const results = [];
    const walk = (el) => { for (const c of el.children) { if (c.tagName === tag) results.push(c); walk(c); } };
    walk(this);
    return { forEach: (fn) => results.forEach(fn), length: results.length };
  }
  querySelector(tag) {
    const results = [];
    const walk = (el) => { for (const c of el.children) { if (c.tagName === tag) results.push(c); walk(c); } };
    walk(this);
    return results.length > 0 ? results[0] : null;
  }
}
const registry = new Map();
global.Evt = Evt;
global.HTMLElement = StubElement;
global.customElements = { define(tag, ctor) { registry.set(tag, ctor); }, get(tag) { return registry.get(tag); } };
global.document = {
  createElement(tag) {
    const Ctor = registry.get(tag) || StubElement;
    const instance = new Ctor();
    instance.tagName = tag;
    instance.children = instance.children || [];
    instance._listeners = instance._listeners || new Map();
    for (const key of ["appendChild", "addEventListener", "dispatchEvent", "querySelectorAll", "querySelector"]) {
      if (!instance[key]) instance[key] = StubElement.prototype[key].bind(instance);
    }
    if (!instance.parentNode) instance.parentNode = null;
    if (instance.className === undefined) instance.className = "";
    if (!instance.style) instance.style = { cssText: "" };
    return instance;
  },
};
"""


def test_escape_hatch_handler_is_imported_and_called_for_real():
    if shutil.which("tsc") is None or shutil.which("node") is None:
        check("tsc and node available for this real compile+run check", False)
        return
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        components_dir = project_dir / "components"
        out_dir = project_dir / "out"
        components_dir.mkdir()

        (components_dir / "map-panel.ts").write_text(
            "export default class MapPanelElement extends HTMLElement {}\n"
        )
        (components_dir / "handlers.ts").write_text(
            "export const calls: string[] = [];\n"
            "export function handleWeirdCase(arg: string): void {\n"
            "  calls.push(arg);\n"
            "}\n"
        )

        definition_dict = {
            "components": [{"tag": "map-panel", "source": "map-panel.ts"}],
            "handlers": {"onWeird": {"module": "handlers.ts", "export": "handleWeirdCase"}},
            "events": [
                {
                    "event": "weird-thing",
                    "from": "map-panel",
                    "actions": [{"call": "escape:onWeird", "method": "unused", "args": ['"from-the-dsl"']}],
                }
            ],
            "state": [],
        }
        definition = parse_app_definition(json.dumps(definition_dict))
        outputs = generate(definition, str(components_dir), str(out_dir))
        out_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in outputs.items():
            (out_dir / filename).write_text(content)

        wiring_text = outputs["app-wiring.ts"]
        check("generated code imports the handler's real export", "handleWeirdCase as onWeird" in wiring_text)
        check("generated code calls the handler directly (no querySelector for an escape target)", 'querySelector("escape:onWeird")' not in wiring_text)

        tsconfig = {
            "compilerOptions": {
                "target": "ES2019", "module": "CommonJS", "lib": ["DOM", "ES2019"],
                "strict": True, "outDir": "build", "rootDir": ".",
            },
            "include": ["components/**/*.ts", "out/**/*.ts"],
        }
        (project_dir / "tsconfig.json").write_text(json.dumps(tsconfig))
        result = subprocess.run(["tsc", "-p", "."], cwd=project_dir, capture_output=True, text=True)
        check("generated code referencing a hand-written handler module compiles for real", result.returncode == 0)
        if result.returncode != 0:
            print(result.stdout, result.stderr)
            return

        driver = (
            DOM_STUB_JS
            + '\nconst handlers = require("./build/components/handlers.js");\n'
            + 'const wiring = require("./build/out/app-wiring.js");\n'
            + "const root = document.createElement(\"div\");\n"
            + 'root.appendChild(document.createElement("map-panel"));\n'
            + "wiring.wireEvents(root);\n"
            + 'root.querySelector("map-panel").dispatchEvent(new Evt("weird-thing", {}));\n'
            + "console.log(JSON.stringify({ calls: handlers.calls }));\n"
        )
        (project_dir / "driver.js").write_text(driver)
        run_result = subprocess.run(["node", "driver.js"], cwd=project_dir, capture_output=True, text=True)
        check("driver ran without error", run_result.returncode == 0)
        if run_result.returncode != 0:
            print(run_result.stdout, run_result.stderr)
            return
        output = json.loads(run_result.stdout.strip().splitlines()[-1])
        check(
            "the real hand-written handler was actually invoked with the DSL-declared arg, once",
            output["calls"] == ["from-the-dsl"],
        )


def test_escape_hatch_handler_global_mode_calls_the_real_export_name_directly():
    """mode="global" has no import/alias step -- the generated call
    site must reference HandlerRef.export (the handler's real global
    function name) directly, not the DSL's own local handler key
    (which mode="module" only gets away with because its generated
    import aliases the real export to that key)."""
    if shutil.which("tsc") is None or shutil.which("node") is None:
        check("tsc and node available for this real compile+concatenate+run check", False)
        return
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        components_dir = project_dir / "components"
        out_dir = project_dir / "out"
        components_dir.mkdir()

        (components_dir / "map-panel.ts").write_text("class MapPanelElement extends HTMLElement {}\n")
        (components_dir / "handlers.ts").write_text(
            "const calls: string[] = [];\n"
            "function handleWeirdCase(arg: string): void {\n"
            "  calls.push(arg);\n"
            "}\n"
        )

        definition_dict = {
            "components": [{"tag": "map-panel", "source": "map-panel.ts"}],
            # The DSL's own local key ("onWeird") deliberately differs
            # from the handler's real global name ("handleWeirdCase")
            # -- global mode must resolve to the latter, not the former.
            "handlers": {"onWeird": {"module": "handlers.ts", "export": "handleWeirdCase"}},
            "events": [
                {
                    "event": "weird-thing",
                    "from": "map-panel",
                    "actions": [{"call": "escape:onWeird", "method": "unused", "args": ['"from-the-dsl"']}],
                }
            ],
            "state": [],
        }
        definition = parse_app_definition(json.dumps(definition_dict))
        outputs = generate(definition, str(components_dir), str(out_dir), mode="global")
        out_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in outputs.items():
            (out_dir / filename).write_text(content)

        wiring_text = outputs["app-wiring.ts"]
        check("global mode calls the handler's real export name directly", "handleWeirdCase(" in wiring_text)
        check("global mode never references the DSL's own local handler key as an identifier", "onWeird(" not in wiring_text)
        check("global mode emits no import for the handler", "import " not in wiring_text)

        tsconfig = {
            "compilerOptions": {
                "target": "ES2019", "lib": ["DOM", "ES2019"], "strict": True,
                "outDir": "build", "rootDir": ".",
            },
            "files": ["components/handlers.ts", "components/map-panel.ts", "out/app-wiring.ts"],
        }
        (project_dir / "tsconfig.json").write_text(json.dumps(tsconfig))
        result = subprocess.run(["tsc", "-p", "."], cwd=project_dir, capture_output=True, text=True)
        check("global-mode escape-hatch output compiles for real", result.returncode == 0)
        if result.returncode != 0:
            print(result.stdout, result.stderr)
            return

        compiled_files = [
            project_dir / "build" / "components" / "handlers.js",
            project_dir / "build" / "components" / "map-panel.js",
            project_dir / "build" / "out" / "app-wiring.js",
        ]
        concatenated = "\n".join(f.read_text() for f in compiled_files)
        (project_dir / "concatenated.js").write_text(concatenated)

        driver = (
            DOM_STUB_JS
            + "\nconst vm = require(\"vm\");\n"
            + "const fs = require(\"fs\");\n"
            + 'const code = fs.readFileSync("./concatenated.js", "utf8");\n'
            + 'vm.runInThisContext(code, { filename: "concatenated.js" });\n'
            + 'const root = document.createElement("div");\n'
            + 'root.appendChild(document.createElement("map-panel"));\n'
            + "wireEvents(root);\n"
            + 'root.querySelector("map-panel").dispatchEvent(new Evt("weird-thing", {}));\n'
            + "console.log(JSON.stringify({ calls }));\n"
        )
        (project_dir / "driver.js").write_text(driver)
        run_result = subprocess.run(["node", "driver.js"], cwd=project_dir, capture_output=True, text=True)
        check("concatenated global-mode escape-hatch output runs under real node", run_result.returncode == 0)
        if run_result.returncode != 0:
            print(run_result.stdout, run_result.stderr)
            return
        output = json.loads(run_result.stdout.strip().splitlines()[-1])
        check(
            "the real handler (referenced by its real global name) was actually invoked",
            output["calls"] == ["from-the-dsl"],
        )


test_escape_hatch_handler_is_imported_and_called_for_real()
test_escape_hatch_handler_global_mode_calls_the_real_export_name_directly()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
