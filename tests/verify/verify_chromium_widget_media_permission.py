"""TODO 2dbfd55: ChromiumWidget answers QWebEnginePage.featurePermission
Requested instead of leaving it pending forever (the "blank view" the
report traced a getUserMedia call back to). Only a widget declaring the
`media` capability is granted MediaAudioCapture/MediaVideoCapture/
MediaAudioVideoCapture; every other feature (Notifications tested here as
a stand-in for the rest) is always denied, capability or not."""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# A "granted" media permission must not actually reach for real
# hardware during a routine regression sweep (see LEARNINGS.md/TODO
# b2ab79f's disabled_verify_voice_*.py precedent, which disabled tests
# that activated the real system mic) -- a fake device satisfies
# getUserMedia's own success path without touching anything real.
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--use-fake-device-for-media-stream")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.window  # noqa: E402,F401  (must precede QApplication)

from PyQt6.QtCore import QCoreApplication, QEvent, QUrl  # noqa: E402
from PyQt6.QtWebEngineCore import QWebEnginePage  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from desk.hotreload import HotReloadBroker  # noqa: E402
from desk.server.runner import start_server  # noqa: E402
from desk.shell.chromium_widget import ChromiumWidget  # noqa: E402

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


def pump(seconds=1.0, until=None):
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        if until and until():
            return True
        time.sleep(0.02)
    return until() if until else None


def read_js(widget, expression):
    result = {}

    def collect(value):
        result["value"] = value
        result["got"] = True

    widget.page().runJavaScript(expression, collect)
    pump(2, until=lambda: result.get("got"))
    return result.get("value")


def wait_for_js(widget, expression, seconds=5.0):
    """Polls `expression` at arm's length from `pump`'s own event loop --
    calling read_js() *from inside* a pump(until=...) lambda re-enters
    processEvents() while a runJavaScript() callback from the previous
    iteration may still be in flight, which was observed to starve that
    callback indefinitely. One read_js() call per already-completed pump
    tick instead."""
    deadline = time.time() + seconds
    value = read_js(widget, expression)
    while value in (None, "pending") and time.time() < deadline:
        pump(0.1)
        value = read_js(widget, expression)
    return value


PAGE_HTML = """<html><body><script>
window.__media = "pending";
window.__notif = "pending";
navigator.mediaDevices.getUserMedia({audio: true}).then(() => {
  window.__media = "granted";
}).catch((e) => {
  window.__media = "denied:" + e.name;
});
Notification.requestPermission().then((p) => { window.__notif = p; });
</script></body></html>"""


with tempfile.TemporaryDirectory() as d:
    widgets_dir = Path(d) / "widgets"
    wdir = widgets_dir / "mediawidget"
    wdir.mkdir(parents=True)
    (wdir / "widget.json").write_text(
        json.dumps({"name": "Media Widget", "kind": "html", "entry": "index.html", "capabilities": []})
    )
    (wdir / "index.html").write_text(PAGE_HTML)
    handle = start_server(widgets_dir=widgets_dir)
    try:
        # Sanity, before trusting the checks below: confirmed directly
        # that without this fix's connection, the request really is
        # left hanging (Chromium's own undocumented default) rather
        # than settling on its own regardless of what this widget does.
        sanity = ChromiumWidget(
            "mediawidget", "inst-sanity", handle.widget_url("mediawidget"), handle.token,
            HotReloadBroker(), Path(d) / "profile-sanity",
        )
        sanity.resize(200, 200)
        sanity.show()
        sanity._logging_page.featurePermissionRequested.disconnect(sanity._on_feature_permission_requested)
        pump(3)
        check(
            "sanity: without connecting featurePermissionRequested, the request is left pending forever",
            read_js(sanity, "window.__media") == "pending",
        )
        sanity.deleteLater()
        pump(1)

        # --- end-to-end: real getUserMedia()/Notification.requestPermission() ---
        no_media = ChromiumWidget(
            "mediawidget", "inst-no-media", handle.widget_url("mediawidget"), handle.token,
            HotReloadBroker(), Path(d) / "profile-no-media",
        )
        no_media.resize(200, 200)
        no_media.show()
        check(
            # Confirmed directly: which DOMException name a denied
            # getUserMedia() rejects with is this QtWebEngine/Chromium
            # build's own implementation detail (AbortError here, not
            # the spec-typical NotAllowedError) -- what this TODO
            # actually fixes, and what's worth asserting, is that the
            # promise settles (rejects) at all instead of hanging
            # forever unanswered, which is the real bug the report
            # traced the blank view back to.
            "no 'media' capability: getUserMedia() is rejected (a catchable error), not left hanging",
            (wait_for_js(no_media, "window.__media") or "").startswith("denied:"),
        )
        check("no capabilities: Notification.requestPermission() still resolves 'denied'", wait_for_js(no_media, "window.__notif") == "denied")

        with_media = ChromiumWidget(
            "mediawidget", "inst-with-media", handle.widget_url("mediawidget"), handle.token,
            HotReloadBroker(), Path(d) / "profile-with-media", capabilities=["media"],
        )
        with_media.resize(200, 200)
        with_media.show()
        check("'media' capability: getUserMedia() resolves (fake device, no real hardware touched)", wait_for_js(with_media, "window.__media") == "granted")
        check(
            "'media' capability grants only media features -- Notifications still denied",
            wait_for_js(with_media, "window.__notif") == "denied",
        )

        # --- direct call: exact setFeaturePermission policy per feature ---
        Feature = QWebEnginePage.Feature
        Policy = QWebEnginePage.PermissionPolicy
        for label, widget, expect_media_granted in (
            ("no capabilities", no_media, False),
            ("media capability", with_media, True),
        ):
            calls = []
            widget._logging_page.setFeaturePermission = lambda origin, feature, policy: calls.append((feature, policy))
            for feature in (Feature.MediaAudioCapture, Feature.MediaVideoCapture, Feature.MediaAudioVideoCapture, Feature.Notifications):
                widget._on_feature_permission_requested(QUrl("http://example.test"), feature)
            expected_media_policy = Policy.PermissionGrantedByUser if expect_media_granted else Policy.PermissionDeniedByUser
            check(
                f"{label}: all three media features get the same policy ({'granted' if expect_media_granted else 'denied'})",
                calls[:3] == [(f, expected_media_policy) for f in (Feature.MediaAudioCapture, Feature.MediaVideoCapture, Feature.MediaAudioVideoCapture)],
            )
            check(f"{label}: Notifications is always denied", calls[3] == (Feature.Notifications, Policy.PermissionDeniedByUser))

        no_media.deleteLater()
        with_media.deleteLater()
        pump(1)
    finally:
        handle.stop()

sys.path.insert(0, "src")
from desk.temp_ui import CURRENT_TAGS, _CUSTOM_WIDGETS_DOC, _NEW_FEATURES  # noqa: E402

TAG = "media capability gates mic and camera #407103"
check("tempui doc documents the media capability", "## Media (mic/camera) access" in _CUSTOM_WIDGETS_DOC)
check("tempui doc names getUserMedia", "getUserMedia()" in _CUSTOM_WIDGETS_DOC)
check("tag is in CURRENT_TAGS with a _NEW_FEATURES entry", TAG in CURRENT_TAGS and TAG in _NEW_FEATURES)

# Same os._exit() ending as verify_chromium_widget_crash_restart.py's own
# sibling scripts (see LEARNINGS.md's TODO a5f66cc entry): real
# QWebEngineProfile/QWebEnginePage teardown can segfault at normal
# interpreter shutdown, unrelated to anything checked above.
print(f"\n{passed} passed, {failed} failed")
sys.stdout.flush()
os._exit(1 if failed else 0)
