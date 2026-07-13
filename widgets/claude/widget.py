import shlex

from PyQt6.QtWidgets import QWidget

from desk.shell import current_context
from desk.temp_ui import DOC_FILENAME, TEMP_UI_DIRNAME
from desk.terminal_widget import TerminalWidget

CLAUDE_WIDGET_PROMPT = (
    "You are running inside of Desk. Please read this document to "
    "understand the implications of that: {doc_path} -- it links to "
    "further tempui-*.md files (in that same directory) for specific "
    "capabilities; follow those links too, not just this one file."
)

# claude's --permission-mode has an "auto" choice; launching with it puts
# the session in auto mode from the start (TODO 2dca4c8).
PERMISSION_MODE_ARGS = "--permission-mode auto"


def _doc_path() -> str:
    directory = current_context.get_current_desk_directory()
    if directory is not None:
        return str(directory / TEMP_UI_DIRNAME / DOC_FILENAME)
    # No current Desk directory known yet (an edge case, not the normal
    # path) -- a plain relative-path description is still a reasonable
    # thing to tell claude, rather than crashing the whole widget build.
    return f"{TEMP_UI_DIRNAME}/{DOC_FILENAME}"


DEVELOPMENT_PROCESS_FILENAME = "development-process.md"


def _development_process_instruction() -> str:
    """Empty unless the current project actually has its own
    development-process.md (TODO fbd0554) -- appended as a second
    sentence onto CLAUDE_WIDGET_PROMPT when non-empty, not a
    placeholder/negative statement when there isn't one."""
    directory = current_context.get_current_desk_directory()
    if directory is None:
        return ""
    path = directory / DEVELOPMENT_PROCESS_FILENAME
    if not path.is_file():
        return ""
    return f" This project also has its own {DEVELOPMENT_PROCESS_FILENAME} at {path} -- please read that too."


class ClaudeWidget(TerminalWidget):
    """A bash shell that auto-launches `claude` bound to a specific
    session id, so the session can be resumed across a Desk reload. The
    session id is the widget's own Desk instance_id (a persisted, per
    -instance identifier -- the same instance_id-as-durable-identity
    pattern the Temporary UI widgets use), passed in post-build by
    DeskWindow._bind_claude_widget rather than known at build() time.
    See plans/claude-widget-session-resume.md."""

    def __init__(self) -> None:
        # cwd defaults to the current Desk's own directory (TODO
        # f447303), not wherever the Desk process itself happens to be
        # running from -- exec-ing claude afterward keeps this same cwd,
        # since exec replaces the process image in place without forking.
        super().__init__(command=["bash"], cwd=current_context.get_current_desk_directory())

    def start_session(self, session_id: str, resume: bool) -> None:
        # `exec` so bash loads its profile (PATH/aliases/nvm/...) and then
        # replaces itself with claude in the same PTY process: quitting
        # claude ends the PTY (so the widget can close, TODO 5ddbef0)
        # rather than dropping back to a shell. If claude isn't found,
        # bash's exec fails and the interactive shell stays usable, which
        # preserves the original claude-not-found safety (TODO 6907120).
        if resume:
            # Reload: reconnect to the existing session, and (per TODO
            # 1d7331b) do not re-send the initial Desk prompt.
            command = f"exec claude --resume {shlex.quote(session_id)} {PERMISSION_MODE_ARGS}\n"
        else:
            # Fresh launch: assign the session id up front (so a later
            # reload can --resume it) and send the initial Desk prompt.
            prompt = CLAUDE_WIDGET_PROMPT.format(doc_path=_doc_path()) + _development_process_instruction()
            command = (
                f"exec claude --session-id {shlex.quote(session_id)} "
                f"{PERMISSION_MODE_ARGS} {shlex.quote(prompt)}\n"
            )
        # Typed into the freshly-spawned shell rather than exec-ing
        # `claude` directly as the PTY's own process -- see
        # plans/claude-widget.md -- so the shell's own startup/profile
        # (PATH, aliases, etc.) loads first, same as a user launching it
        # from a real terminal.
        self.type_into_shell(command)


def build() -> QWidget:
    # Just the shell; the `claude` command (fresh vs. resume) is issued
    # by DeskWindow._bind_claude_widget once the session id is known.
    return ClaudeWidget()
