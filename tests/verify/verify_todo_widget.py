import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")
sys.path.insert(0, "widgets/todo")

from PyQt6.QtWidgets import QApplication

from desk.shell import current_context
from desk_services.file_watcher import get_service

app = QApplication(sys.argv)


def pump(seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)


with tempfile.TemporaryDirectory() as d:
    directory = Path(d)
    todo_path = directory / "TODO.md"
    todo_path.write_text("a1b2c3d. First item.\nb2c3d4e. Second item.\n")

    current_context.set_current_desk_directory(directory)

    import widget as todo_widget_module

    w = todo_widget_module.build()
    w.reload()
    pump(0.3)
    assert w._state["todo_path"] == todo_path.resolve() or w._state["todo_path"] == todo_path, w._state["todo_path"]
    assert len(w._state["items"]) == 2, w._state["items"]
    print("initial load: PASS")

    # Simulate an add (writes + commits, sets last_written_text) and
    # confirm the watcher doesn't misfire as an "external change".
    reload_calls = []
    orig_reload = w.reload
    w.reload = lambda *a, **kw: (reload_calls.append(1), orig_reload(*a, **kw))

    from widget import _write_and_commit, REPRIORITIZE_MESSAGE

    thread = _write_and_commit(w._state, REPRIORITIZE_MESSAGE)
    if thread is not None:
        thread.join()
    pump(1.0)
    assert not reload_calls, f"own write should not trigger a reload via _on_external_change, got {reload_calls}"
    print("self-write suppression: PASS")

    # Now edit TODO.md externally with the widget "open" -- confirm it reloads.
    external_text = "a1b2c3d. First item.\nb2c3d4e. Second item.\nc3d4e5f. Third item.\n"
    todo_path.write_text(external_text)
    pump(1.0)
    assert len(w._state["items"]) == 3, f"external edit should reload, got {w._state['items']}"
    print("external change reload: PASS")

    w.deleteLater()
    app.processEvents()
    get_service().stop()
    print("ALL PASS")
