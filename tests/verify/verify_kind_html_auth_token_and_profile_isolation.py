import inspect
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path("/Users/mphair/inadvisable-adventures/desk")
sys.path.insert(0, str(REPO_ROOT / "src"))

# desk.shell.window (imports desk.shell.chromium_widget, which imports
# QtWebEngineWidgets) must be importable before QApplication is
# constructed -- see other verify scripts' identical comment on this
# same gotcha.
import desk.shell.window  # noqa: E402,F401

from PyQt6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from PyQt6.QtWebEngineCore import QWebEngineProfile  # noqa: E402
from desk.desks import Desk  # noqa: E402
from desk.hotreload import HotReloadBroker  # noqa: E402
from desk.server.runner import start_server  # noqa: E402
from desk.shell.canvas import WorkspaceView  # noqa: E402
from desk.shell.chromium_widget import ChromiumWidget  # noqa: E402
from desk.shell.window import DeskWindow  # noqa: E402

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


def pump(seconds=1.0):
    """See LEARNINGS.md's "A headless QApplication.processEvents() loop
    doesn't reliably run a deleteLater()-scheduled deletion" -- a plain
    processEvents() loop alone can leave DeferredDelete events
    unprocessed indefinitely. Draining DeferredDelete explicitly here
    fixes exactly that (real, needed for the sip.isdeleted() check in
    test_multi_file_widget_actually_loads to reflect real completed
    deletion, not just a scheduled one). It is *not*, on its own,
    sufficient to prevent every ChromiumWidget/QWebEngineProfile
    teardown segfault this script can hit at interpreter exit once
    several profiles are involved -- see this file's own os._exit()
    at the bottom (and LEARNINGS.md's fuller TODO a5f66cc entry) for
    the fix that actually is."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        time.sleep(0.02)


def _make_widget_dir(widgets_dir, widget_id, external_script):
    """A real multi-file kind:"html" widget: index.html loads a
    sibling main.js via an ordinary relative <script src> -- the exact
    shape that used to 401 silently (TODO 4ab5875)."""
    wdir = widgets_dir / widget_id
    wdir.mkdir()
    (wdir / "widget.json").write_text(
        json.dumps({"name": "Test", "kind": "html", "entry": "index.html", "capabilities": []})
    )
    (wdir / "index.html").write_text(
        '<html><body><test-el></test-el><script src="main.js"></script></body></html>'
    )
    (wdir / "main.js").write_text(external_script)
    return wdir


CUSTOM_ELEMENT_JS = """
class TestEl extends HTMLElement {
  connectedCallback() {
    this.attachShadow({mode: "open"});
    this.shadowRoot.innerHTML = "<p>loaded</p>";
  }
}
customElements.define("test-el", TestEl);
"""


# ---------- HTTP-level: cookie is set, cookie-only requests authenticate, unauth still rejected ----------


def test_widget_page_response_sets_auth_cookie():
    with tempfile.TemporaryDirectory() as d:
        widgets_dir = Path(d)
        _make_widget_dir(widgets_dir, "cookietest", CUSTOM_ELEMENT_JS)
        handle = start_server(widgets_dir=widgets_dir)
        try:
            url = handle.widget_url("cookietest")
            cj = CookieJar()
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
            resp = opener.open(url)
            check("the widget page request succeeds", resp.status == 200)
            cookie_names = [c.name for c in cj]
            check("the response sets a desk_token cookie", "desk_token" in cookie_names)
            token_cookie = next(c for c in cj if c.name == "desk_token")
            check("the cookie carries the real per-launch token", token_cookie.value == handle.token)

            base = url.split("?")[0]
            sub_resource_req = urllib.request.Request(base + "main.js")
            sub_resp = opener.open(sub_resource_req)
            check("a sub-resource request with only the cookie (no query param) is accepted", sub_resp.status == 200)

            try:
                urllib.request.urlopen(base + "main.js")
                check("a request with no credentials at all is rejected", False)
            except urllib.error.HTTPError as e:
                check("a request with no credentials at all is rejected", e.code == 401)
        finally:
            handle.stop()


# ---------- Real ChromiumWidget: a multi-file widget now actually loads ----------


def test_multi_file_widget_actually_loads():
    with tempfile.TemporaryDirectory() as d:
        widgets_dir = Path(d)
        _make_widget_dir(widgets_dir, "loadtest", CUSTOM_ELEMENT_JS)
        handle = start_server(widgets_dir=widgets_dir)
        try:
            broker = HotReloadBroker()
            profile_dir = Path(d) / "profile"
            widget = ChromiumWidget(
                "loadtest", "inst-1", handle.widget_url("loadtest"), handle.token, broker, profile_dir
            )
            pump(2)

            result = {}

            def _capture(value):
                result["shadow_html"] = value

            widget.page().runJavaScript(
                "document.querySelector('test-el') && document.querySelector('test-el').shadowRoot"
                " && document.querySelector('test-el').shadowRoot.innerHTML",
                _capture,
            )
            pump(1)
            check(
                "the custom element's shadowRoot is populated (module graph actually finished loading)",
                result.get("shadow_html") == "<p>loaded</p>",
            )
            widget.deleteLater()
            pump(1)
            from PyQt6 import sip

            check("the widget (and its profile/page) is actually, fully deleted, not just scheduled", sip.isdeleted(widget))
        finally:
            handle.stop()


# ---------- Per-instance profile isolation ----------


def test_two_instances_get_distinct_profile_directories():
    with tempfile.TemporaryDirectory() as d:
        widgets_dir = Path(d)
        _make_widget_dir(widgets_dir, "sharedkind", CUSTOM_ELEMENT_JS)
        handle = start_server(widgets_dir=widgets_dir)
        try:
            broker = HotReloadBroker()
            profile_dir_1 = Path(d) / "profiles" / "inst-a"
            profile_dir_2 = Path(d) / "profiles" / "inst-b"
            widget1 = ChromiumWidget(
                "sharedkind", "inst-a", handle.widget_url("sharedkind"), handle.token, broker, profile_dir_1
            )
            widget2 = ChromiumWidget(
                "sharedkind", "inst-b", handle.widget_url("sharedkind"), handle.token, broker, profile_dir_2
            )
            pump(2)
            check("instance 1's profile directory was actually created on disk", profile_dir_1.is_dir())
            check("instance 2's profile directory was actually created on disk", profile_dir_2.is_dir())
            check("the two instances' profile directories are distinct paths", profile_dir_1 != profile_dir_2)
            widget1.deleteLater()
            widget2.deleteLater()
            pump(0.5)
        finally:
            handle.stop()


def test_chromium_profile_dir_helper():
    with tempfile.TemporaryDirectory() as d:
        fake_window = DeskWindow.__new__(DeskWindow)
        fake_window.current_desk = Desk(path=Path(d) / "test.desk")
        computed = fake_window._chromium_profile_dir("some-instance")
        check(
            "_chromium_profile_dir keys the path by instance_id under .desk_temp/chromium-profiles",
            computed == Path(d) / ".desk_temp" / "chromium-profiles" / "some-instance",
        )


def test_schedule_chromium_profile_cleanup_deletes_only_the_target_instance():
    with tempfile.TemporaryDirectory() as d:
        fake_window = DeskWindow.__new__(DeskWindow)
        fake_window.current_desk = Desk(path=Path(d) / "test.desk")

        target_dir = fake_window._chromium_profile_dir("closed-instance")
        other_dir = fake_window._chromium_profile_dir("still-open-instance")
        target_dir.mkdir(parents=True)
        other_dir.mkdir(parents=True)
        (target_dir / "marker.txt").write_text("x")

        fake_window._schedule_chromium_profile_cleanup("closed-instance")
        pump(0.5)

        check("the closed instance's profile directory is gone", not target_dir.exists())
        check("a different, still-open instance's profile directory is untouched", other_dir.is_dir())


def test_schedule_chromium_profile_cleanup_is_a_noop_for_a_widget_with_no_profile():
    with tempfile.TemporaryDirectory() as d:
        fake_window = DeskWindow.__new__(DeskWindow)
        fake_window.current_desk = Desk(path=Path(d) / "test.desk")
        # A kind:"python" widget instance never had a profile directory
        # in the first place -- must not raise.
        fake_window._schedule_chromium_profile_cleanup("python-widget-instance")
        pump(0.2)
        check("no exception raised cleaning up an instance with no profile directory", True)


def test_close_widget_triggers_cleanup_but_clear_widgets_does_not():
    """DeskWindow.close_widget (permanent removal) must call the
    cleanup; WorkspaceView.clear_widgets (Desk-switch -- the widget may
    come back) must not reference Chromium profiles at all. Confirmed
    by reading each method's real source (close_widget's own
    machinery -- save_current_desk, the confirm dialog, _capture_desk_
    state's dependency on a fully-wired DeskWindow/desk_picker/event
    mediator -- is disproportionate to construct just to observe this
    one side effect), not merely asserted."""
    close_widget_source = inspect.getsource(DeskWindow.close_widget)
    check(
        "close_widget calls _schedule_chromium_profile_cleanup",
        "_schedule_chromium_profile_cleanup" in close_widget_source,
    )
    clear_widgets_source = inspect.getsource(WorkspaceView.clear_widgets)
    check(
        "clear_widgets does not reference Chromium profiles at all",
        "profile" not in clear_widgets_source.lower() and "chromium" not in clear_widgets_source.lower(),
    )


# ---------- BrowserWidget is unaffected ----------


def test_browser_widget_still_uses_the_default_profile():
    import importlib.util

    spec = importlib.util.spec_from_file_location("browser_widget_verify_mod", REPO_ROOT / "widgets" / "browser" / "widget.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    widget = module.build()
    check(
        "BrowserWidget's QWebEngineView still uses Qt's shared default profile, unaffected by ChromiumWidget's per-instance profiles",
        widget._view.page().profile() is QWebEngineProfile.defaultProfile(),
    )
    widget.deleteLater()
    pump(0.5)


test_widget_page_response_sets_auth_cookie()
test_multi_file_widget_actually_loads()
test_two_instances_get_distinct_profile_directories()
test_chromium_profile_dir_helper()
test_schedule_chromium_profile_cleanup_deletes_only_the_target_instance()
test_schedule_chromium_profile_cleanup_is_a_noop_for_a_widget_with_no_profile()
test_close_widget_triggers_cleanup_but_clear_widgets_does_not()
test_browser_widget_still_uses_the_default_profile()

# os._exit(), not sys.exit(): this script places several kind:"html"
# (ChromiumWidget-backed) widgets across its test functions, each with
# its own real QWebEngineProfile. Confirmed directly (see
# LEARNINGS.md's TODO a5f66cc entry): once every check() above has
# already passed correctly, normal Python interpreter shutdown can
# still segfault tearing down 2+ such profiles/pages -- a real,
# reproducible Qt/WebEngine internals race specific to that shutdown
# path, not a bug in anything this script actually verifies (draining
# DeferredDelete events, per the pump() docstring above, fixes a
# related but distinct issue -- it does not reliably prevent this one
# once several distinct profiles are involved). os._exit() terminates
# immediately, skipping that teardown path entirely (the same way
# force-quitting a process does), so the reported exit code reliably
# reflects the real check() results above instead of being clobbered
# by an unrelated crash.
print(f"\n{passed} passed, {failed} failed")
sys.stdout.flush()
os._exit(1 if failed else 0)
