import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path("/Users/mphair/inadvisable-adventures/desk")
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


# A minimal, hand-written DOM stand-in -- this script runs the
# generated code under plain `node`, not a browser, so there's no real
# `document`/`HTMLElement`/`customElements` to use. Deliberately not a
# real dependency (no jsdom/similar): just enough of EventTarget/
# HTMLElement/customElements/document for the specific patterns
# codegen.py actually emits (createElement, appendChild, className,
# style.cssText, addEventListener/dispatchEvent, querySelector(All)).
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
  appendChild(child) {
    this.children.push(child);
    child.parentNode = this;
    return child;
  }
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
    const walk = (el) => {
      for (const c of el.children) {
        if (c.tagName === tag) results.push(c);
        walk(c);
      }
    };
    walk(this);
    return { forEach: (fn) => results.forEach(fn), length: results.length };
  }
  querySelector(tag) {
    const results = [];
    const walk = (el) => {
      for (const c of el.children) {
        if (c.tagName === tag) results.push(c);
        walk(c);
      }
    };
    walk(this);
    return results.length > 0 ? results[0] : null;
  }
}

const registry = new Map();
global.Evt = Evt;
global.HTMLElement = StubElement;
global.customElements = {
  define(tag, ctor) { registry.set(tag, ctor); },
  get(tag) { return registry.get(tag); },
};
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


def _tsc_node_available():
    return shutil.which("tsc") is not None and shutil.which("node") is not None


REPRESENTATIVE_DEFINITION = {
    "components": [
        {"tag": "map-panel", "source": "map-panel.ts"},
        {"tag": "timeline-view", "source": "timeline-view.ts"},
    ],
    "state": [{"name": "selectedId", "type": "string | null", "default": None}],
    "layout": {
        "type": "split",
        "variants": {
            "default": {
                "type": "hsplit",
                "children": [
                    {"type": "pane", "widget": "map-panel"},
                    {"type": "pane", "widget": "timeline-view"},
                ],
            }
        },
        "default_variant": "default",
    },
    "events": [
        {
            "event": "marker-selected",
            "from": "map-panel",
            "actions": [
                {"set": "selectedId", "from": "event.detail.id"},
                {"call": "timeline-view", "method": "highlightEvent", "args": ["event.detail.id"]},
            ],
        }
    ],
}


def test_generated_code_compiles_and_runs_correctly():
    if not _tsc_node_available():
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
        (components_dir / "timeline-view.ts").write_text(
            "export default class TimelineViewElement extends HTMLElement {\n"
            "  lastHighlighted: string | null = null;\n"
            "  highlightEvent(id: string): void {\n"
            "    this.lastHighlighted = id;\n"
            "  }\n"
            "}\n"
        )

        definition = parse_app_definition(json.dumps(REPRESENTATIVE_DEFINITION))
        outputs = generate(definition, str(components_dir), str(out_dir))
        out_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in outputs.items():
            (out_dir / filename).write_text(content)

        check("app-wiring.ts was generated", (out_dir / "app-wiring.ts").is_file())
        check("app-layout.css was generated for a split layout", (out_dir / "app-layout.css").is_file())

        tsconfig = {
            "compilerOptions": {
                "target": "ES2019",
                "module": "CommonJS",
                "lib": ["DOM", "ES2019"],
                "strict": True,
                "outDir": "build",
                "rootDir": ".",
            },
            "include": ["components/**/*.ts", "out/**/*.ts"],
        }
        (project_dir / "tsconfig.json").write_text(json.dumps(tsconfig))

        result = subprocess.run(["tsc", "-p", "."], cwd=project_dir, capture_output=True, text=True)
        check("the generated code (plus real component fixtures) compiles with a real tsc", result.returncode == 0)
        if result.returncode != 0:
            print(result.stdout)
            print(result.stderr)
            return

        driver = (
            DOM_STUB_JS
            + '\nconst wiring = require("./build/out/app-wiring.js");\n'
            + "const root = wiring.buildLayout(wiring.DEFAULT_LAYOUT_VARIANT);\n"
            + "wiring.wireEvents(root);\n"
            + 'const mapPanel = root.querySelector("map-panel");\n'
            + 'const timeline = root.querySelector("timeline-view");\n'
            + 'mapPanel.dispatchEvent(new Evt("marker-selected", { detail: { id: "e42" } }));\n'
            + "console.log(JSON.stringify({\n"
            + "  selectedId: wiring.selectedId,\n"
            + "  lastHighlighted: timeline.lastHighlighted,\n"
            + "}));\n"
        )
        (project_dir / "driver.js").write_text(driver)
        run_result = subprocess.run(["node", "driver.js"], cwd=project_dir, capture_output=True, text=True)
        check("the compiled output runs under real node without error", run_result.returncode == 0)
        if run_result.returncode != 0:
            print(run_result.stdout)
            print(run_result.stderr)
            return
        output = json.loads(run_result.stdout.strip().splitlines()[-1])
        check(
            "a real dispatched event correctly mutated the generated state slot",
            output["selectedId"] == "e42",
        )
        check(
            "the same event correctly fanned out to the second action's real method call",
            output["lastHighlighted"] == "e42",
        )


def test_windowed_layout_codegen_not_implemented_yet_raises_a_clear_error():
    definition_dict = {
        "components": [{"tag": "map-panel", "source": "map-panel.ts"}],
        "layout": {
            "type": "windowed",
            "windows": [{"widget": "map-panel", "x": 0, "y": 0, "width": 400, "height": 300}],
        },
        "events": [],
        "state": [],
    }
    definition = parse_app_definition(json.dumps(definition_dict))
    from schema import DslError

    try:
        generate(definition, "components", "out")
        check("windowed layout codegen raises a clear not-yet-implemented error", False)
    except DslError as e:
        check("windowed layout codegen raises a clear not-yet-implemented error", "windowed" in str(e) and "not implemented" in str(e))


def test_no_layout_generates_registry_state_and_events_only():
    definition_dict = {
        "components": [{"tag": "map-panel", "source": "map-panel.ts"}],
        "events": [],
        "state": [{"name": "x", "type": "number", "default": 0}],
    }
    definition = parse_app_definition(json.dumps(definition_dict))
    outputs = generate(definition, "components", "out")
    check("no layout -> no CSS file generated", "app-layout.css" not in outputs)
    check("no layout -> still generates the registry/state TS", "customElements.define" in outputs["app-wiring.ts"])


test_generated_code_compiles_and_runs_correctly()
test_windowed_layout_codegen_not_implemented_yet_raises_a_clear_error()
test_no_layout_generates_registry_state_and_events_only()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
