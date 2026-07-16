import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from PyQt6.QtWidgets import QApplication, QListWidgetItem  # noqa: E402

app = QApplication(sys.argv)


def load_widget_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


questions_mod = load_widget_module("questions_widget_verify_mod", "widgets/questions/widget.py")

SAMPLE = """# Questions with optional answers

## TODO `aaaaaaa`: first question

Some body text for the first question.

(Answer: )

## TODO `bbbbbbb`/`ccccccc`: second question, two ids

Body for the second, with a sub-bullet:

- one
- two

(Answer: already answered here)

"""


class _FakeContext:
    def __init__(self, directory):
        self._directory = directory

    def get_current_desk_directory(self):
        return self._directory

    def path_is_external(self, path):
        return False

    def get_widget_opener(self):
        return None


def make_git_repo(directory):
    subprocess.run(["git", "init", "-q"], cwd=directory, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=directory, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=directory, check=True)


def test_reload_and_filter():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        path = directory / "QUESTIONS.md"
        path.write_text(SAMPLE)
        make_git_repo(directory)
        subprocess.run(["git", "add", "QUESTIONS.md"], cwd=directory, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=directory, check=True)

        with patch.object(questions_mod, "current_context", _FakeContext(directory)):
            widget = questions_mod.QuestionsWidget()
            assert widget._list.count() == 1  # default filter: unanswered only
            widget._filter_buttons["all"].setChecked(True)
            assert widget._list.count() == 2
            widget._filter_buttons["all"].setChecked(False)
            widget._filter_buttons["unanswered"].setChecked(False)
            widget._filter_buttons["answered"].setChecked(True)
            assert widget._list.count() == 1
            assert "second" in widget._list.item(0).data(questions_mod.ENTRY_ROLE).title
    print("reload + filter: PASS")


def test_answer_writes_and_commits():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        path = directory / "QUESTIONS.md"
        path.write_text(SAMPLE)
        make_git_repo(directory)
        subprocess.run(["git", "add", "QUESTIONS.md"], cwd=directory, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=directory, check=True)

        with patch.object(questions_mod, "current_context", _FakeContext(directory)):
            widget = questions_mod.QuestionsWidget()
            entry = next(e for e in widget._state["entries"] if e.todo_ids == ["aaaaaaa"])
            widget._save_answer(entry, "here is the answer")

            # The file write is synchronous; the git commit happens on a
            # background thread. Poll git log for the new commit rather
            # than the file content (which is already updated by the
            # time _save_answer returns).
            import time

            for _ in range(50):
                log = subprocess.run(
                    ["git", "log", "--oneline"], cwd=directory, capture_output=True, text=True, check=True
                )
                if "Answer question" in log.stdout:
                    break
                time.sleep(0.05)

            text = path.read_text()
            assert "(Answer: here is the answer)" in text
            assert "(Answer: already answered here)" in text  # other entry untouched

            log = subprocess.run(
                ["git", "log", "-1", "--pretty=%s"], cwd=directory, capture_output=True, text=True, check=True
            )
            assert "Answer question: aaaaaaa" in log.stdout
    print("answer writes to disk + commits: PASS")


def test_no_questions_file():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        with patch.object(questions_mod, "current_context", _FakeContext(directory)):
            widget = questions_mod.QuestionsWidget()
            assert widget._list.count() == 0
            assert "No QUESTIONS.md found" in widget._status_label.text()
    print("no QUESTIONS.md found: PASS")


def test_external_change_reload():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        path = directory / "QUESTIONS.md"
        path.write_text(SAMPLE)
        make_git_repo(directory)

        with patch.object(questions_mod, "current_context", _FakeContext(directory)):
            widget = questions_mod.QuestionsWidget()
            assert widget._list.count() == 1

            path.write_text(
                SAMPLE
                + "## TODO `ddddddd`: third question\n\nnew body\n\n(Answer: )\n\n"
            )
            widget._on_external_change()
            assert widget._list.count() == 2
    print("external change triggers reload: PASS")


test_reload_and_filter()
test_answer_writes_and_commits()
test_no_questions_file()
test_external_change_reload()
print("ALL PASS")
