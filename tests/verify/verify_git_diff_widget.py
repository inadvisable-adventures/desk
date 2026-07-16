import importlib.util
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")

from PyQt6.QtWidgets import QApplication, QListWidgetItem  # noqa: E402

from desk.file_type_registry import GIT_DIFF_WIDGET_ID, FileTypeHandler, FileTypeRegistryEntry, find_git_diff_handler  # noqa: E402

app = QApplication(sys.argv)

REPO_ROOT = Path("/Users/mphair/inadvisable-adventures/desk")

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


def load_module(name, relative_path):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True)


def init_repo(root):
    run_git(root, "init", "-q")
    run_git(root, "config", "user.email", "test@example.com")
    run_git(root, "config", "user.name", "Test")


def wait_for_result(widget, path, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if widget._path == path and widget._text_view.toPlainText() != git_diff_mod.LOADING_MESSAGE:
            return
        time.sleep(0.02)


# ---------- desk.file_type_registry.find_git_diff_handler ----------


def test_find_git_diff_handler_dynamic_registry_hit():
    registry = [FileTypeRegistryEntry(extensions=[".foo"], handlers=[FileTypeHandler(widget_id="custom_diff", role="git-diff")])]
    result = find_git_diff_handler(registry, Path("thing.foo"))
    check("find_git_diff_handler returns a registered git-diff handler", result == "custom_diff")


def test_find_git_diff_handler_falls_back_to_builtin():
    result = find_git_diff_handler([], Path("anything.xyz"))
    check(
        "find_git_diff_handler always resolves (never None) -- falls back to the builtin widget",
        result == GIT_DIFF_WIDGET_ID,
    )


test_find_git_diff_handler_dynamic_registry_hit()
test_find_git_diff_handler_falls_back_to_builtin()


# ---------- widgets/git_status/widget.py: parsing + click wiring ----------

git_status_mod = load_module("git_status_mod", "widgets/git_status/widget.py")


def test_path_from_status_line_plain():
    root = Path("/repo")
    path = git_status_mod._path_from_status_line(root, " M some/file.py")
    check("plain modified-file porcelain line resolves the right path", path == root / "some/file.py")


def test_path_from_status_line_rename():
    root = Path("/repo")
    path = git_status_mod._path_from_status_line(root, "R  old_name.py -> new_name.py")
    check("rename porcelain line resolves to the *new* path", path == root / "new_name.py")


def test_path_from_status_line_garbage():
    check("too-short/garbage line resolves to no path", git_status_mod._path_from_status_line(Path("/repo"), "??") is None)


test_path_from_status_line_plain()
test_path_from_status_line_rename()
test_path_from_status_line_garbage()


def test_populate_list_stashes_path_and_clean_placeholder_has_none():
    w = git_status_mod.GitStatusWidget()
    w._root = Path("/repo")
    w._populate_list(" M some/file.py\n")
    item = w._list.item(0)
    check("a real status row's item carries the resolved Path", item.data(git_status_mod.PATH_ROLE) == Path("/repo/some/file.py"))

    w._populate_list("")
    clean_item = w._list.item(0)
    check(
        "the clean-working-tree placeholder row carries no path (clicking it is a no-op)",
        clean_item.text() == git_status_mod.CLEAN_PLACEHOLDER and clean_item.data(git_status_mod.PATH_ROLE) is None,
    )
    w.deleteLater()


def test_click_handler_opens_git_diff_for_a_real_row_not_the_placeholder():
    w = git_status_mod.GitStatusWidget()
    w._root = Path("/repo")
    opened = []
    from desk.shell import current_context

    current_context.set_git_diff_opener(lambda path: opened.append(path))
    try:
        w._populate_list(" M some/file.py\n")
        w._on_item_clicked(w._list.item(0))
        check("clicking a real status row calls the git-diff opener with its path", opened == [Path("/repo/some/file.py")])

        opened.clear()
        w._populate_list("")
        w._on_item_clicked(w._list.item(0))
        check("clicking the clean-placeholder row does not call the opener", opened == [])
    finally:
        current_context.set_git_diff_opener(None)
        w.deleteLater()


test_populate_list_stashes_path_and_clean_placeholder_has_none()
test_click_handler_opens_git_diff_for_a_real_row_not_the_placeholder()


# ---------- widgets/git_diff/widget.py: real end-to-end against a real repo ----------

git_diff_mod = load_module("git_diff_mod", "widgets/git_diff/widget.py")


def test_set_file_shows_a_real_uncommitted_change():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        init_repo(root)
        target = root / "hello.txt"
        target.write_text("line one\nline two\n")
        run_git(root, "add", "hello.txt")
        run_git(root, "commit", "-q", "-m", "initial")

        target.write_text("line one\nline TWO changed\n")

        w = git_diff_mod.build()
        w.set_file(target)
        wait_for_result(w, target)

        text = w._text_view.toPlainText()
        check(
            "a real uncommitted text change renders as a real diff (has a - and a + line)",
            "-line two" in text and "+line TWO changed" in text,
        )
        w.deleteLater()


def test_set_file_binary_change_shows_binary_message():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        init_repo(root)
        target = root / "image.bin"
        target.write_bytes(b"\x00\x01\x02\x03binarydata")
        run_git(root, "add", "image.bin")
        run_git(root, "commit", "-q", "-m", "initial")

        target.write_bytes(b"\x00\x01\x02\x03different binary data")

        w = git_diff_mod.build()
        w.set_file(target)
        wait_for_result(w, target)

        check(
            "a binary file change shows the binary placeholder, not a raw diff",
            w._text_view.toPlainText() == git_diff_mod.BINARY_MESSAGE,
        )
        w.deleteLater()


def test_set_file_deleted_file_still_shows_real_diff():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        init_repo(root)
        target = root / "goodbye.txt"
        target.write_text("this content is going away\n")
        run_git(root, "add", "goodbye.txt")
        run_git(root, "commit", "-q", "-m", "initial")
        target.unlink()

        w = git_diff_mod.build()
        w.set_file(target)
        wait_for_result(w, target)

        text = w._text_view.toPlainText()
        check(
            "a deleted file's real diff still renders -- looks_like_text_file's False (file "
            "doesn't exist) must not be mistaken for binary",
            "-this content is going away" in text and text != git_diff_mod.BINARY_MESSAGE,
        )
        w.deleteLater()


def test_set_file_no_changes_shows_no_diff_message():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        init_repo(root)
        target = root / "unchanged.txt"
        target.write_text("nothing changes here\n")
        run_git(root, "add", "unchanged.txt")
        run_git(root, "commit", "-q", "-m", "initial")

        w = git_diff_mod.build()
        w.set_file(target)
        wait_for_result(w, target)

        check("an unchanged file shows the no-differences message", w._text_view.toPlainText() == git_diff_mod.NO_DIFF_MESSAGE)
        w.deleteLater()


def test_set_file_not_a_repo():
    with tempfile.TemporaryDirectory() as d:
        target = Path(d) / "lonely.txt"
        target.write_text("not in any repo\n")

        w = git_diff_mod.build()
        w.set_file(target)
        wait_for_result(w, target)

        check("a file outside any git repo shows the not-a-repo message", w._text_view.toPlainText() == git_diff_mod.NOT_A_REPO_MESSAGE)
        w.deleteLater()


def test_widget_local_storage_round_trip():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        init_repo(root)
        target = root / "restored.txt"
        target.write_text("content\n")
        run_git(root, "add", "restored.txt")
        run_git(root, "commit", "-q", "-m", "initial")

        w = git_diff_mod.build()
        w.set_file(target)
        wait_for_result(w, target)
        storage = w.get_widget_local_storage()
        check("get_widget_local_storage persists the path", storage == {"path": str(target)})

        w2 = git_diff_mod.build()
        w2.set_widget_local_storage(storage)
        wait_for_result(w2, target)
        check("set_widget_local_storage restores and re-loads the same file", w2._path == target)
        w.deleteLater()
        w2.deleteLater()


test_set_file_shows_a_real_uncommitted_change()
test_set_file_binary_change_shows_binary_message()
test_set_file_deleted_file_still_shows_real_diff()
test_set_file_no_changes_shows_no_diff_message()
test_set_file_not_a_repo()
test_widget_local_storage_round_trip()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
