"""TODO c8bb4eb: <desk-select> built the way a house-convention widget
builds controls -- cloned out of a <template> (inert, NOT upgraded), a
property set on the clone, THEN inserted -- must behave like any other
construction order. Before the fix, `.value = x` on the un-upgraded clone
made an own property that shadowed the real accessor forever, so user
picks never reported a changed `value`. Also covers `value` /
`selectedIndex` set on a createElement'd element before it is connected
(was a no-op), an explicit non-matching `value` (no silent fallback to
the first option), and records what customElements.upgrade() really does
in this embedded browser (informational)."""
import json
import os
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

app = QApplication(sys.argv)
COMPONENT_DIR = REPO_ROOT / "shared-components" / "desk-select"
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


with tempfile.TemporaryDirectory() as d:
    out = Path(d) / "out.js"
    proc = subprocess.run(
        ["tsc", "--strict", "--target", "es2020", "--lib", "es2020,dom", "--outFile", str(out),
         str(COMPONENT_DIR / "desk-select.ts")],
        capture_output=True, text=True,
    )
    check("desk-select.ts compiles under tsc --strict", proc.returncode == 0 and out.is_file())
    template = (COMPONENT_DIR / "template.html").read_text()
    html = f"""<!doctype html><html><body style="margin:0">
{template}
<template id="row"><desk-select><option value="major">Major</option><option value="minor">Minor</option><option value="free">Free</option></desk-select></template>
<div id="mount"></div>
<script>{out.read_text() if out.is_file() else ""}</script>
<script>
  window.changes = [];
  document.addEventListener("change", (e) => window.changes.push(e.target.value));
  window.cloneRow = () => document.getElementById("row").content.firstElementChild.cloneNode(true);
</script></body></html>"""
    view = QWebEngineView()
    view.resize(500, 400)
    loaded = {}
    view.loadFinished.connect(lambda ok: loaded.setdefault("ok", ok))
    view.setHtml(html, QUrl("http://localhost/"))
    view.show()
    pump(10.0, until=lambda: "ok" in loaded)
    check("page loaded", loaded.get("ok") is True)

    # 1. The reported pattern: clone from <template>, set value, insert.
    r = run_js(view, """
      const el = cloneRow();
      const wasUpgraded = el instanceof customElements.get('desk-select');
      el.value = 'free';
      document.getElementById('mount').appendChild(el);
      window.el1 = el;
      return {wasUpgraded, value: el.value, own: Object.prototype.hasOwnProperty.call(el, 'value'),
              label: el.shadowRoot.querySelector('.label').textContent.trim()};
    """)
    check("(info) a template clone starts un-upgraded", r and r["wasUpgraded"] is False)
    check("value set on the clone survives insertion", r and r["value"] == "free")
    check("no own `value` property left shadowing the accessor", r and r["own"] is False)
    check("label shows the pre-set value", r and r["label"] == "Free")
    r = run_js(view, """
      const el = window.el1;
      el.shadowRoot.querySelector('.button').click();
      el.shadowRoot.querySelector('#option-0').click();
      return {value: el.value, changes: window.changes.slice()};
    """)
    check("picking a different option updates `value` (the reported bug)", r and r["value"] == "major")
    check("and the change event reported the new value", r and r["changes"] == ["major"])

    # 2. selectedIndex + disabled on a clone.
    r = run_js(view, """
      const el = cloneRow();
      el.selectedIndex = 2; el.disabled = true;
      document.getElementById('mount').appendChild(el);
      return {value: el.value, index: el.selectedIndex, disabled: el.disabled,
              attr: el.hasAttribute('disabled'), btn: el.shadowRoot.querySelector('.button').disabled,
              own: ['selectedIndex','disabled'].filter(k => Object.prototype.hasOwnProperty.call(el, k))};
    """)
    check("selectedIndex set on a clone is honored", r and r["index"] == 2 and r["value"] == "free")
    check("disabled set on a clone reaches the attribute and the button",
          r and r["disabled"] is True and r["attr"] is True and r["btn"] is True)
    check("no shadowing own properties for selectedIndex/disabled", r and r["own"] == [])

    # 3. createElement, set before connecting (options added afterwards).
    r = run_js(view, """
      const el = document.createElement('desk-select');
      el.value = 'minor';
      for (const [v, t] of [['major','Major'],['minor','Minor'],['free','Free']]) {
        const o = document.createElement('option'); o.value = v; o.textContent = t; el.appendChild(o);
      }
      document.getElementById('mount').appendChild(el);
      const a = {value: el.value};
      const el2 = document.createElement('desk-select');
      el2.selectedIndex = 1;
      for (const v of ['x','y']) { const o = document.createElement('option'); o.value = v; o.textContent = v; el2.appendChild(o); }
      document.getElementById('mount').appendChild(el2);
      return {a, b: el2.value};
    """)
    check("value set before connect applies once options exist", r and r["a"]["value"] == "minor")
    check("selectedIndex set before connect applies once options exist", r and r["b"] == "y")

    # 4. An explicit value that matches nothing selects nothing (like <select>),
    #    but no value at all still defaults to the first enabled option.
    r = run_js(view, """
      const el = cloneRow(); el.value = 'nope';
      document.getElementById('mount').appendChild(el);
      const none = cloneRow();
      document.getElementById('mount').appendChild(none);
      return {explicit: el.value, explicitIndex: el.selectedIndex, dflt: none.value};
    """)
    check("an explicit non-matching value selects nothing", r and r["explicit"] == "" and r["explicitIndex"] == -1)
    check("no value specified still defaults to the first option", r and r["dflt"] == "major")

    # 5. Existing behaviour: post-connect assignment still works and a later
    #    option mutation keeps the user's choice.
    r = run_js(view, """
      const el = cloneRow();
      document.getElementById('mount').appendChild(el);
      el.value = 'free';
      return {value: el.value};
    """)
    check("assignment after connecting still works", r and r["value"] == "free")

    # 6. Informational: does customElements.upgrade() upgrade a template clone here?
    r = run_js(view, """
      const el = cloneRow();
      customElements.upgrade(el);
      const direct = el instanceof customElements.get('desk-select');
      const adopted = document.importNode(document.getElementById('row').content.firstElementChild, true);
      return {direct, imported: adopted instanceof customElements.get('desk-select'), ua: navigator.userAgent};
    """)
    print(f"INFO: customElements.upgrade(clone) upgraded: {r and r['direct']}; document.importNode upgraded: {r and r['imported']}")
    print(f"INFO: {r and r['ua']}")

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
