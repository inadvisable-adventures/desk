"""TODO b0dd8e1: shared-components/desk-select -- a <select>
replacement whose dropdown is ordinary DOM, exercised in a real
QtWebEngine page: the compiled component, inside a scrollable
(overflow:auto) ancestor and a shadow root, opens a list positioned
under its button, commits by click and by keyboard, fires `change`, and
closes on outside click / Escape / scroll."""
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

from desk.temp_ui import CURRENT_TAGS, SHARED_COMPONENTS_DIRNAME, _NEW_FEATURES, SPLIT_DOC_CONTENT, sync_shared_components  # noqa: E402

app = QApplication(sys.argv)

COMPONENT_DIR = REPO_ROOT / "shared-components" / "desk-select"
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
<div id="scroller" style="height:140px;overflow:auto;border:1px solid red;margin:20px">
  <div style="height:30px">spacer</div>
  <div id="host"></div>
  <div style="height:400px">more</div>
</div>
<div id="plain" style="margin:10px 20px">
  <desk-select id="plainSel" value="b"><option value="a">Alpha</option><option value="b">Beta</option><option>Gamma</option><option value="d" disabled>Delta</option></desk-select>
</div>
<script>{out.read_text() if out.is_file() else ""}</script>
<script>
  // A select living inside a shadow root inside an overflow:auto ancestor.
  const root = document.getElementById("host").attachShadow({{mode: "open"}});
  root.innerHTML = '<desk-select id="inner"><option value="major">Major</option><option value="minor" selected>Minor</option><option value="free">Free</option></desk-select>';
  window.changes = [];
  document.addEventListener("change", (e) => window.changes.push(e.composedPath()[0].id + ":" + e.composedPath()[0].value));
</script></body></html>"""

    view = QWebEngineView()
    view.resize(500, 500)
    loaded = {}
    view.loadFinished.connect(lambda ok: loaded.setdefault("ok", ok))
    view.setHtml(html, QUrl("http://localhost/"))
    view.show()
    pump(10.0, until=lambda: "ok" in loaded)
    check("page loaded", loaded.get("ok") is True)

    PREAMBLE = """
      const inner = document.getElementById('host').shadowRoot.getElementById('inner');
      const plain = document.getElementById('plainSel');
      const btn = (el) => el.shadowRoot.querySelector('.button');
      const list = (el) => el.shadowRoot.querySelector('.list');
    """

    r = run_js(view, PREAMBLE + "return {defined: !!customElements.get('desk-select'), pv: plain.value, pi: plain.selectedIndex, iv: inner.value, label: btn(inner).textContent.trim(), gammaValue: plain.options[2].value};")
    check("custom element registered", r and r["defined"])
    check("value attribute selects initially", r and r["pv"] == "b" and r["pi"] == 1)
    check("`selected` option attribute selects initially (inside a shadow root)", r and r["iv"] == "minor" and r["label"].startswith("Minor"))

    # Open: list is ordinary DOM, visible, directly under the button, not clipped by the scroller.
    r = run_js(view, PREAMBLE + """
      btn(inner).click();
      const b = btn(inner).getBoundingClientRect(), l = list(inner).getBoundingClientRect();
      return {hidden: list(inner).hidden, expanded: btn(inner).getAttribute('aria-expanded'),
              top: l.top, bottom: b.bottom, left: l.left, bleft: b.left, width: l.width, bwidth: b.width,
              scrollerBottom: document.getElementById('scroller').getBoundingClientRect().bottom,
              fixed: getComputedStyle(list(inner)).position, n: list(inner).children.length};
    """)
    check("click opens the list", r and r["hidden"] is False and r["expanded"] == "true")
    check("list is position:fixed ordinary DOM", r and r["fixed"] == "fixed" and r["n"] == 3)
    check("list sits just under the button and lines up on the left", r and abs(r["top"] - (r["bottom"] + 2)) < 1.5 and abs(r["left"] - r["bleft"]) < 1.5)
    check("list is at least as wide as the button", r and r["width"] >= r["bwidth"] - 1)
    check("list isn't clipped by the overflow:auto ancestor (extends past its bottom edge)", r and r["top"] + 40 > 0 and r["top"] < r["scrollerBottom"] + 200)

    # Hit-test: the point at the center of option 0 resolves to that option (it is on top).
    r = run_js(view, PREAMBLE + """
      const opt = list(inner).children[0].getBoundingClientRect();
      const hit = document.elementsFromPoint(opt.left + 5, opt.top + opt.height / 2);
      return {onTop: hit[0] && hit[0].id === 'host'};  // retargeted to the outer shadow host
    """)
    check("list is on top of the page (hit test lands on the shadow host, not the content beneath)", r and r["onTop"])

    # Click an option commits + fires change.
    r = run_js(view, PREAMBLE + """
      list(inner).children[2].click();
      return {v: inner.value, hidden: list(inner).hidden, changes: window.changes, label: btn(inner).textContent.trim()};
    """)
    check("clicking an option sets value, closes, and fires change (composed, bubbles to document)", r and r["v"] == "free" and r["hidden"] is True and r["changes"] == ["inner:free"] and r["label"].startswith("Free"))

    r = run_js(view, PREAMBLE + """
      btn(inner).click(); list(inner).children[2].click();
      return {changes: window.changes};
    """)
    check("re-selecting the same option fires no change", r and r["changes"] == ["inner:free"])

    # Keyboard.
    r = run_js(view, PREAMBLE + """
      const key = (el, k) => btn(el).dispatchEvent(new KeyboardEvent('keydown', {key: k, bubbles: true, cancelable: true}));
      key(plain, 'ArrowDown');            // opens
      const opened = !list(plain).hidden;
      key(plain, 'ArrowDown');            // Beta -> Gamma
      key(plain, 'ArrowDown');            // Delta is disabled: stays on Gamma
      key(plain, 'Enter');
      return {opened, v: plain.value, hidden: list(plain).hidden, changes: window.changes};
    """)
    check("ArrowDown opens, skips disabled, Enter commits", r and r["opened"] and r["v"] == "Gamma" and r["hidden"] and r["changes"][-1] == "plainSel:Gamma")

    r = run_js(view, PREAMBLE + """
      const key = (el, k) => btn(el).dispatchEvent(new KeyboardEvent('keydown', {key: k, bubbles: true, cancelable: true}));
      key(plain, ' '); key(plain, 'Home'); key(plain, 'Escape');
      return {hidden: list(plain).hidden, v: plain.value};
    """)
    check("Escape closes without changing the value", r and r["hidden"] and r["v"] == "Gamma")

    r = run_js(view, PREAMBLE + """
      const key = (el, k) => btn(el).dispatchEvent(new KeyboardEvent('keydown', {key: k, bubbles: true, cancelable: true}));
      key(plain, 'a');
      return {v: plain.value};
    """)
    check("type-ahead selects a matching option while closed", r and r["v"] == "a")

    # Outside click closes; scroll closes.
    r = run_js(view, PREAMBLE + """
      btn(plain).click();
      const wasOpen = !list(plain).hidden;
      document.body.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true, composed: true}));
      return {wasOpen, hidden: list(plain).hidden};
    """)
    check("pointerdown outside closes it", r and r["wasOpen"] and r["hidden"])

    r = run_js(view, PREAMBLE + """
      btn(inner).click();
      const wasOpen = !list(inner).hidden;
      document.getElementById('scroller').dispatchEvent(new Event('scroll'));
      return {wasOpen, hidden: list(inner).hidden};
    """)
    # scroll doesn't bubble, but the capturing document listener sees it on the way down
    check("scrolling an ancestor closes it", r and r["wasOpen"] and r["hidden"])

    # Programmatic API, dynamic options, disabled.
    r = run_js(view, PREAMBLE + """
      plain.value = 'd';             // disabled option still settable programmatically, like <select>
      const setDisabledOpt = plain.value;
      plain.value = 'nope';
      const unknown = {v: plain.value, i: plain.selectedIndex, label: btn(plain).textContent.trim()};
      plain.selectedIndex = 0;
      const o = document.createElement('option'); o.value = 'z'; o.textContent = 'Zed'; plain.appendChild(o);
      return {setDisabledOpt, unknown, keptSelection: plain.value, count: plain.options.length};
    """)
    pump(0.3)
    r2 = run_js(view, PREAMBLE + "return {n: list(plain).children.length, v: plain.value};")
    check("value= with an unknown value selects nothing (value '')", r and r["unknown"]["v"] == "" and r["unknown"]["i"] == -1 and r["unknown"]["label"] == "")
    check("appending an <option> updates the list and keeps the selection", r2 and r2["n"] == 5 and r2["v"] == "a")

    r = run_js(view, PREAMBLE + """
      plain.disabled = true;
      btn(plain).click();
      const stayedClosed = list(plain).hidden;
      plain.disabled = false;
      return {stayedClosed, attr: plain.hasAttribute('disabled')};
    """)
    check("disabled select doesn't open", r and r["stayedClosed"] and r["attr"] is False)

    view.close()

# ---- docs, tag, mirroring -----------------------------------------------

TAG = "desk-select replaces native select in html widgets #821015"
check("tag registered", TAG in CURRENT_TAGS)
check("changelog entry exists", TAG in _NEW_FEATURES and "desk-select" in _NEW_FEATURES[TAG])
custom_doc = next((v for k, v in SPLIT_DOC_CONTENT.items() if "custom-widgets" in k), "")
check("tempui-custom-widgets.md tells html widget authors not to use a native <select>", "<desk-select>" in custom_doc and "native `<select>`" in custom_doc)
check("components README lists desk-select", "desk-select/README.md" in (REPO_ROOT / "shared-components" / "README.md").read_text())
with tempfile.TemporaryDirectory() as d:
    temp_dir = Path(d) / ".desk_temp"
    temp_dir.mkdir()
    sync_shared_components(temp_dir)
    check("desk-select is mirrored into .desk_temp/shared-components", (temp_dir / SHARED_COMPONENTS_DIRNAME / "desk-select" / "desk-select.ts").is_file())

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
