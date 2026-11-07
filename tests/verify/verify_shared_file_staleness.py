"""TODO 8a65056 -- see plans/shared-file-staleness.md.
Cites ../FEEDBACK/FEEDBACK-DESK-shared-widget-file-edits-may-not-mark-dependents-stale-2026-10-21-0038.md.

A promoted widget's staleness watch also follows the files its
tsconfig.json "files" array references from outside its own directory."""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk.custom_widgets import external_source_files  # noqa: E402
from desk.shell.promoted_widget_source_watcher import DEBOUNCE_SECONDS, PromotedWidgetSourceWatcher  # noqa: E402

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


def pump(seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)


def wait_for(predicate, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        app.processEvents()
        time.sleep(0.02)
    return predicate()


def write_widget(widget_dir, files):
    widget_dir.mkdir(parents=True, exist_ok=True)
    (widget_dir / "tsconfig.json").write_text(json.dumps({"compilerOptions": {"outDir": ".build"}, "files": files}))
    (widget_dir / f"{widget_dir.name}.ts").write_text("// widget\n")


# ---- external_source_files ---------------------------------------------

with tempfile.TemporaryDirectory() as d:
    root = Path(d).resolve()
    widget = root / "desk_widgets" / "alpha"
    write_widget(widget, ["../_shared/base.ts", "./helper.ts", "alpha.ts", "../_shared/base.ts", "../../top.ts", 7])
    got = external_source_files(widget)
    check("only entries outside the widget dir, normalized, de-duplicated", got == [root / "desk_widgets" / "_shared" / "base.ts", root / "top.ts"])
    check("no tsconfig -> empty", external_source_files(root / "nowhere") == [])
    (widget / "tsconfig.json").write_text("{ not json")
    check("malformed tsconfig -> empty", external_source_files(widget) == [])
    (widget / "tsconfig.json").write_text(json.dumps({"compilerOptions": {"outDir": ".build"}}))
    check("no `files` key -> empty", external_source_files(widget) == [])

# ---- the watcher --------------------------------------------------------

with tempfile.TemporaryDirectory() as d:
    root = Path(d).resolve()
    shared = root / "desk_widgets" / "_shared"
    shared.mkdir(parents=True)
    (shared / "base.ts").write_text("// base v1\n")
    (shared / "unrelated.ts").write_text("// not referenced\n")
    (shared / "later.ts").write_text("// referenced later\n")
    alpha, beta, gamma = (root / "desk_widgets" / n for n in ("alpha", "beta", "gamma"))
    write_widget(alpha, ["../_shared/base.ts", "alpha.ts"])
    write_widget(beta, ["../_shared/base.ts", "beta.ts"])
    write_widget(gamma, ["gamma.ts"])  # no shared dependency

    pump(1.0)  # let the setup writes above age out of the OS's event-coalescing window
    watcher = PromotedWidgetSourceWatcher()
    seen = []
    watcher.changed.connect(seen.append)
    try:
        for kw, wd in (("Alpha", alpha), ("Beta", beta), ("Gamma", gamma)):
            watcher.watch(kw, wd)

        (shared / "base.ts").write_text("// base v2\n")
        check("editing a shared file marks every widget that lists it", wait_for(lambda: {"Alpha", "Beta"} <= set(seen)))
        pump(DEBOUNCE_SECONDS + 0.4)
        check("...and not a widget that doesn't", "Gamma" not in seen)

        seen.clear()
        (shared / "unrelated.ts").write_text("// edited\n")
        pump(DEBOUNCE_SECONDS + 0.6)
        check("editing a sibling file in the shared dir that nobody lists fires nothing", seen == [])

        seen.clear()
        (alpha / "alpha.ts").write_text("// own edit\n")
        check("a widget's own-directory edit still fires", wait_for(lambda: seen == ["Alpha"]))

        # Adding a shared file to tsconfig re-arms the watch.
        pump(DEBOUNCE_SECONDS + 0.4)
        seen.clear()
        write_widget(alpha, ["../_shared/base.ts", "../_shared/later.ts", "alpha.ts"])
        check("a tsconfig edit fires", wait_for(lambda: seen == ["Alpha"]))
        pump(DEBOUNCE_SECONDS + 0.4)
        seen.clear()
        (shared / "later.ts").write_text("// later v2\n")
        check("a shared file added to tsconfig afterward is followed without re-registering", wait_for(lambda: seen == ["Alpha"]))

        # Re-watching the same keyword doesn't leak duplicate subscriptions.
        watcher.watch("Alpha", alpha)
        watcher.watch("Alpha", alpha)
        pump(DEBOUNCE_SECONDS + 0.4)
        seen.clear()
        (shared / "base.ts").write_text("// base v3\n")
        pump(DEBOUNCE_SECONDS + 0.8)
        check("re-watching is idempotent (one signal per widget per edit)", sorted(seen) == ["Alpha", "Beta"])

        # stop_watching stops the shared watch too.
        watcher.stop_watching("Alpha")
        pump(0.3)
        seen.clear()
        (shared / "base.ts").write_text("// base v4\n")
        pump(DEBOUNCE_SECONDS + 0.8)
        check("stop_watching also stops following shared files", "Alpha" not in seen and "Beta" in seen)
    finally:
        watcher.stop_all()

    seen.clear()
    (shared / "base.ts").write_text("// base v5\n")
    pump(DEBOUNCE_SECONDS + 0.6)
    check("stop_all stops everything", seen == [])

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
