from PyQt6.QtWidgets import QWidget

from desk.shell import current_context
from desk.terminal_widget import TerminalWidget


def build() -> QWidget:
    # cwd defaults to the current Desk's own directory (TODO f447303),
    # not wherever the Desk process itself happens to be running from.
    return TerminalWidget(cwd=current_context.get_current_desk_directory())
