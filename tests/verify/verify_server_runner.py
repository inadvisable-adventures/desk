import os
import sys
import tempfile
import urllib.request
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")

from desk.server.runner import start_server  # noqa: E402
from desk.widgets import WidgetInfo  # noqa: E402

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


def _info(widget_id):
    return WidgetInfo(
        id=widget_id, path=Path("."), kind="html", name="Test", entry="index.html", capabilities=[], default_size=None
    )


def test_remounting_a_different_directory_serves_the_new_content():
    """TODO 4eb3d9e: the confirmed root cause behind
    FEEDBACK-DESK-promoted-widgets-no-stale-marker-2026-09-15-1744.md's
    "[STALE] shown, but stale content served anyway" -- Starlette's
    Router.mount only ever appends a route, so a second mount_html_widget
    call for the same widget_id at a *different* directory used to be
    silently shadowed forever behind the first one ever registered."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        dir1 = tmp / "v1"
        dir1.mkdir()
        (dir1 / "index.html").write_text("VERSION ONE")
        dir2 = tmp / "v2"
        dir2.mkdir()
        (dir2 / "index.html").write_text("VERSION TWO")

        handle = start_server(widgets_dir=tmp)
        try:
            info = _info("testw")
            handle.mount_html_widget("testw", dir1, info)
            url = handle.widget_url("testw")
            body1 = urllib.request.urlopen(url).read().decode()
            check("first mount serves its own directory's content", body1 == "VERSION ONE")

            handle.mount_html_widget("testw", dir2, info)
            body2 = urllib.request.urlopen(url).read().decode()
            check("remounting a *different* directory now serves the new content", body2 == "VERSION TWO")

            # Overwriting the same (currently-mounted) directory's file
            # in place -- the other, already-working case -- must keep
            # working exactly as before.
            (dir2 / "index.html").write_text("VERSION TWO, EDITED IN PLACE")
            body3 = urllib.request.urlopen(url).read().decode()
            check("editing the currently-mounted directory's file in place is still served fresh", body3 == "VERSION TWO, EDITED IN PLACE")

            check(
                "only one route remains registered for this widget_id, not two accumulated",
                sum(1 for route in handle._app.router.routes if getattr(route, "name", None) == "widget-testw") == 1,
            )
        finally:
            handle.stop()


def test_remounting_a_different_widget_id_is_unaffected():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        dir_a = tmp / "a"
        dir_a.mkdir()
        (dir_a / "index.html").write_text("A")
        dir_b = tmp / "b"
        dir_b.mkdir()
        (dir_b / "index.html").write_text("B")

        handle = start_server(widgets_dir=tmp)
        try:
            handle.mount_html_widget("widget_a", dir_a, _info("widget_a"))
            handle.mount_html_widget("widget_b", dir_b, _info("widget_b"))
            check("widget_a serves its own content", urllib.request.urlopen(handle.widget_url("widget_a")).read().decode() == "A")
            check("widget_b serves its own content", urllib.request.urlopen(handle.widget_url("widget_b")).read().decode() == "B")
        finally:
            handle.stop()


test_remounting_a_different_directory_serves_the_new_content()
test_remounting_a_different_widget_id_is_unaffected()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
