from PyQt6.QtWidgets import QWidget

from desk.terminal_widget import TerminalWidget


def build() -> QWidget:
    return TerminalWidget()
