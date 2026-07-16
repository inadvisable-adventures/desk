import importlib.util
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from desk.terminal_widget import TerminalWidget  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)


def load_widget_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_pwd_output(widget, timeout=5.0):
    widget.type_into_shell("pwd\n")
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        text = widget.toPlainText()
        if "pwd" in text and text.strip().splitlines():
            # Give the shell a moment to actually finish writing the line.
            time.sleep(0.05)
            app.processEvents()
            return widget.toPlainText()
        time.sleep(0.05)
    return widget.toPlainText()


def test_terminal_widget_respects_cwd():
    with tempfile.TemporaryDirectory() as d:
        target = Path(d).resolve()
        widget = TerminalWidget(cwd=target)
        try:
            output = read_pwd_output(widget)
            assert str(target) in output, output
        finally:
            widget._process.terminate()
    print("TerminalWidget(cwd=...) spawns bash in that directory: PASS")


def test_terminal_widget_default_cwd_is_unchanged():
    widget = TerminalWidget()
    try:
        output = read_pwd_output(widget)
        assert str(Path.cwd()) in output, output
    finally:
        widget._process.terminate()
    print("TerminalWidget() with no cwd still inherits the process's own cwd: PASS")


def test_console_widget_passes_current_desk_directory():
    console_mod = load_widget_module("console_cwd_verify_mod", "widgets/console/widget.py")
    with tempfile.TemporaryDirectory() as d:
        target = Path(d)
        with patch.object(console_mod.current_context, "get_current_desk_directory", return_value=target):
            widget = console_mod.build()
            try:
                output = read_pwd_output(widget)
                assert str(target.resolve()) in output, output
            finally:
                widget._process.terminate()
    print("Console widget's build() passes current_desk_directory as cwd: PASS")


def test_claude_widget_passes_current_desk_directory():
    claude_mod = load_widget_module("claude_cwd_verify_mod", "widgets/claude/widget.py")
    with tempfile.TemporaryDirectory() as d:
        target = Path(d)
        with patch.object(claude_mod.current_context, "get_current_desk_directory", return_value=target):
            widget = claude_mod.build()
            try:
                output = read_pwd_output(widget)
                assert str(target.resolve()) in output, output
            finally:
                widget._process.terminate()
    print("Claude widget's ClaudeWidget() passes current_desk_directory as cwd: PASS")


test_terminal_widget_respects_cwd()
test_terminal_widget_default_cwd_is_unchanged()
test_console_widget_passes_current_desk_directory()
test_claude_widget_passes_current_desk_directory()
print("ALL PASS")
