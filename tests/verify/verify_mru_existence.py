import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from desk.shell.window import DeskWindow  # noqa: E402
import desk.recent_desks as recent_desks  # noqa: E402

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)


def test_prune_rewrites_when_something_missing():
    with tempfile.TemporaryDirectory() as d:
        mru_path = Path(d) / "recent_desks.json"
        keep = Path(d) / "keep.desk"
        keep.write_text("{}")
        gone = Path(d) / "gone.desk"
        mru_path.write_text(json.dumps([str(keep), str(gone)]))

        with patch.object(recent_desks, "MRU_PATH", mru_path):
            result = recent_desks.prune_missing_mru_entries()
            assert result == [keep]
            on_disk = json.loads(mru_path.read_text())
            assert on_disk == [str(keep)]
    print("prune_missing_mru_entries rewrites the file when something is missing: PASS")


def test_prune_does_not_rewrite_when_nothing_missing():
    with tempfile.TemporaryDirectory() as d:
        mru_path = Path(d) / "recent_desks.json"
        keep = Path(d) / "keep.desk"
        keep.write_text("{}")
        mru_path.write_text(json.dumps([str(keep)]))
        before_mtime = mru_path.stat().st_mtime_ns

        with patch.object(recent_desks, "MRU_PATH", mru_path):
            result = recent_desks.prune_missing_mru_entries()
            assert result == [keep]
            after_mtime = mru_path.stat().st_mtime_ns
            assert before_mtime == after_mtime, "file was rewritten even though nothing was pruned"
    print("prune_missing_mru_entries does not rewrite when nothing is missing: PASS")


def test_load_mru_still_pure_read():
    with tempfile.TemporaryDirectory() as d:
        mru_path = Path(d) / "recent_desks.json"
        keep = Path(d) / "keep.desk"
        keep.write_text("{}")
        gone = Path(d) / "gone.desk"
        mru_path.write_text(json.dumps([str(keep), str(gone)]))

        with patch.object(recent_desks, "MRU_PATH", mru_path):
            result = recent_desks.load_mru()
            assert result == [keep]
            on_disk = json.loads(mru_path.read_text())
            assert on_disk == [str(keep), str(gone)], "load_mru must not persist any change"
    print("load_mru remains a pure, side-effect-free read: PASS")


class _FakeWindow:
    def __init__(self):
        self.switch_desk_calls = []
        self.warn_calls = []
        self.refresh_calls = 0

    def switch_desk(self, path):
        self.switch_desk_calls.append(path)

    def _warn_with_selectable_text(self, title, message):
        self.warn_calls.append((title, message))

    def _refresh_picker(self):
        self.refresh_calls += 1


_FakeWindow._on_desk_chosen = DeskWindow._on_desk_chosen


def test_on_desk_chosen_existing_file_switches():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "x.desk"
        path.write_text("{}")
        win = _FakeWindow()
        win._on_desk_chosen(path)
        assert win.switch_desk_calls == [path]
        assert win.warn_calls == []
        assert win.refresh_calls == 0
    print("_on_desk_chosen with an existing file calls switch_desk: PASS")


def test_on_desk_chosen_missing_file_warns_and_refreshes():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "missing.desk"
        win = _FakeWindow()
        win._on_desk_chosen(path)
        assert win.switch_desk_calls == []
        assert len(win.warn_calls) == 1
        assert str(path) in win.warn_calls[0][1]
        assert win.refresh_calls == 1
    print("_on_desk_chosen with a missing file warns, never switches, refreshes picker: PASS")


test_prune_rewrites_when_something_missing()
test_prune_does_not_rewrite_when_nothing_missing()
test_load_mru_still_pure_read()
test_on_desk_chosen_existing_file_switches()
test_on_desk_chosen_missing_file_warns_and_refreshes()
print("ALL PASS")
