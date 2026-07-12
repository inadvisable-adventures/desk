import fcntl
import logging
import os
import pty
import struct
import subprocess
import termios
from pathlib import Path

import pyte
from PyQt6.QtCore import Qt, QSocketNotifier, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import QPlainTextEdit

PTY_ROWS = 24
PTY_COLS = 80

KEY_BYTES = {
    Qt.Key.Key_Return: b"\r",
    Qt.Key.Key_Enter: b"\r",
    Qt.Key.Key_Backspace: b"\x7f",
    Qt.Key.Key_Tab: b"\x09",
    Qt.Key.Key_Backtab: b"\x1b[Z",  # Shift+Tab -> CSI Z (back-tab)
    Qt.Key.Key_Escape: b"\x1b",
    Qt.Key.Key_Delete: b"\x1b[3~",
    Qt.Key.Key_Insert: b"\x1b[2~",
    Qt.Key.Key_PageUp: b"\x1b[5~",
    Qt.Key.Key_PageDown: b"\x1b[6~",
}

# Cursor keys and Home/End have two encodings: normal (CSI, `ESC [`) and
# application-cursor-keys mode (SS3, `ESC O`), selected by DECCKM. The
# byte here is the final letter; the prefix is chosen at press time. Many
# full-screen TUIs (claude included) enable DECCKM and only recognize the
# SS3 form, so honoring it is what makes their arrow navigation work.
CURSOR_KEYS = {
    Qt.Key.Key_Up: b"A",
    Qt.Key.Key_Down: b"B",
    Qt.Key.Key_Right: b"C",
    Qt.Key.Key_Left: b"D",
    Qt.Key.Key_Home: b"H",
    Qt.Key.Key_End: b"F",
}

# pyte encodes a private mode `N` in `screen.mode` as `N << 5`; DECCKM
# (application cursor keys) is private mode 1, so it appears as `1 << 5`.
# A test enables it via `ESC [ ? 1 h` and asserts arrows switch to SS3,
# which would catch any change to this encoding.
DECCKM = 1 << 5

# pyte reports the standard 8 ANSI colors by name; everything else (256-color
# and truecolor SGR sequences) comes through as a raw hex string with no "#",
# which QColor accepts directly once prefixed.
ANSI_COLOR_MAP = {
    "black": "#000000",
    "red": "#cc0000",
    "green": "#4e9a06",
    "brown": "#c4a000",
    "yellow": "#c4a000",
    "blue": "#3465a4",
    "magenta": "#75507b",
    "cyan": "#06989a",
    "white": "#d3d7cf",
}

# "Bright" (bold/high-intensity) SGR colors (ESC[90-97m foreground,
# ESC[100-107m background) -- pyte reports these as separate names
# ("brightred", etc.), not variants of the base 8. Includes
# "bfightmagenta": a confirmed typo in pyte 0.8.2 itself (missing the "r")
# for background bright magenta -- see LEARNINGS.md.
BRIGHT_COLOR_MAP = {
    "brightblack": "#555753",
    "brightred": "#ef2929",
    "brightgreen": "#8ae234",
    "brightbrown": "#fce94f",
    "brightyellow": "#fce94f",
    "brightblue": "#729fcf",
    "brightmagenta": "#ad7fa8",
    "bfightmagenta": "#ad7fa8",
    "brightcyan": "#34e2e2",
    "brightwhite": "#eeeeec",
}

DEFAULT_FOREGROUND = "#e8e8e8"
DEFAULT_BACKGROUND = "#1e1e1e"


def _resolve_color(name, default_hex):
    """Always returns a concrete color, never None -- critical for reverse
    video (ESC[7m): it swaps fg/bg *before* this resolves them, so if
    unset colors resolved to None instead of a real default, swapping two
    Nones would render nothing. See plans/console-widget-highlight-cursor-
    rendering.md."""
    if not name or name == "default":
        return QColor(default_hex)
    if name in ANSI_COLOR_MAP:
        return QColor(ANSI_COLOR_MAP[name])
    if name in BRIGHT_COLOR_MAP:
        return QColor(BRIGHT_COLOR_MAP[name])
    if len(name) == 6:
        try:
            return QColor(f"#{name}")
        except ValueError:
            return QColor(default_hex)
    return QColor(default_hex)


def _char_format(char, invert: bool = False) -> QTextCharFormat:
    fmt = QTextCharFormat()
    # Resolve each color against its *own* proper default first, then swap
    # the resolved colors for reverse video -- swapping the pre-resolution
    # name strings instead (an earlier version of this fix) is a no-op
    # when both are literally the string "default", since "default" carries
    # no information about which slot (fg vs bg) it belongs to once
    # extracted as a bare string.
    fg = _resolve_color(char.fg, DEFAULT_FOREGROUND)
    bg = _resolve_color(char.bg, DEFAULT_BACKGROUND)
    if char.reverse:
        fg, bg = bg, fg
    # `invert` (the terminal cursor cell -- see _redraw) is a second,
    # independent swap on top of any reverse-video already applied, not a
    # replacement for it: a reverse-video character sitting under the
    # cursor should render as plain video, cursor-highlighted, matching
    # real terminal emulators.
    if invert:
        fg, bg = bg, fg
    fmt.setForeground(fg)
    fmt.setBackground(bg)
    if char.bold:
        fmt.setFontWeight(QFont.Weight.Bold)
    if char.underscore:
        fmt.setFontUnderline(True)
    if char.strikethrough:
        fmt.setFontStrikeOut(True)
    return fmt


class _ResilientStream(pyte.Stream):
    """A `pyte.Stream` whose `feed()` recovers from a single bad escape
    sequence instead of losing the rest of the chunk. `pyte.Stream.feed()`
    lets any exception from dispatching one CSI sequence propagate straight
    out of the whole `feed()` call -- `_send_to_parser` already resets the
    parser's internal state on exception (see its docstring, PR #101) so the
    *stream* stays usable afterward, but the *rest of the current chunk*
    (everything after the offending sequence, up to the next `feed()` call
    from the next PTY read) is silently dropped, since `feed()`'s own loop
    aborts along with the exception. This override is otherwise an exact
    copy of `Stream.feed()`, guarding only the per-character dispatch call so
    one bad sequence (see LEARNINGS.md: pyte 0.8.2's DEC-private CSI
    dispatch gap) is skipped without taking the rest of the buffer with it.
    """

    def feed(self, data: str) -> None:
        if self.listener is None:
            raise RuntimeError("Listener is not set")

        draw = self.listener.draw
        match_text = self._text_pattern.match
        taking_plain_text = self._taking_plain_text

        length = len(data)
        offset = 0
        while offset < length:
            if taking_plain_text:
                match = match_text(data, offset)
                if match:
                    start, offset = match.span()
                    draw(data[start:offset])
                else:
                    taking_plain_text = False
            else:
                try:
                    taking_plain_text = self._send_to_parser(data[offset:offset + 1])
                except Exception:
                    # DEBUG, no traceback: a well-understood, expected,
                    # non-fatal condition (pyte 0.8.2's private-CSI
                    # dispatch gap, see LEARNINGS.md) that real programs
                    # (confirmed: claude) trigger routinely, sometimes on
                    # every startup -- a WARNING-level stack trace per
                    # occurrence was appropriate while this was newly
                    # diagnosed, not now that it's fully understood. See
                    # plans/pyte-private-csi-investigation.md for why
                    # skip-and-log (not patching pyte's affected Screen
                    # methods) is the permanent behavior, not a stopgap.
                    logging.getLogger(__name__).debug(
                        "pyte failed to dispatch a terminal escape sequence; skipping it"
                    )
                    taking_plain_text = True
                offset += 1

        self._taking_plain_text = taking_plain_text


class _PtyScreen(pyte.Screen):
    """A `pyte.Screen` that actually replies to device-status-report queries
    (cursor position / terminal status) by writing back to the real PTY,
    rather than pyte's default no-op `write_process_input`. Otherwise
    identical to `pyte.Screen`."""

    def __init__(self, columns: int, lines: int, master_fd: int) -> None:
        super().__init__(columns, lines)
        self._master_fd = master_fd

    def write_process_input(self, data: str) -> None:
        try:
            os.write(self._master_fd, data.encode("utf-8"))
        except OSError:
            pass


class TerminalWidget(QPlainTextEdit):
    """A real PTY running a shell command (`bash` by default), rendered via
    a `pyte` VT100/ANSI screen emulator: each read feeds pyte's stream
    parser, then `_redraw()` repaints the widget from pyte's current
    screen-buffer state (not an appended log), so full-screen, redraw-in
    -place programs (`claude` included) display correctly. Shared by the
    Console widget (`widgets/console/`, plain `bash`) and the Claude widget
    (`widgets/claude/`, `bash` with `claude` typed into it), both of
    which pass `cwd` (TODO f447303) as the current Desk's own directory
    -- widget
    directories can't import each other directly, so this lives in
    `desk.` proper, the same "shared logic, thin widget.py entry points"
    pattern as `desk.todo_file`/`desk.temp_ui`. See
    design-docs/architecture.md's Key Design Decisions and
    plans/claude-widget.md."""

    # Emitted once when the PTY's child process exits (read hits EOF). The
    # Console widget ignores it (just shows "[process exited]"); the Claude
    # widget's DeskWindow binding uses it to close the widget (TODO
    # 5ddbef0).
    process_exited = pyqtSignal()

    def __init__(
        self, parent=None, command: list[str] | None = None, cwd: Path | None = None
    ) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setUndoRedoEnabled(False)
        self.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setStyleSheet(f"background-color: {DEFAULT_BACKGROUND}; color: {DEFAULT_FOREGROUND};")

        self._master_fd, slave_fd = pty.openpty()
        fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, struct.pack("HHHH", PTY_ROWS, PTY_COLS, 0, 0))

        self._screen = _PtyScreen(PTY_COLS, PTY_ROWS, self._master_fd)
        self._stream = _ResilientStream(self._screen)

        self._process = subprocess.Popen(
            command or ["bash"],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            # None (the default) inherits this process's own cwd, same as
            # before `cwd` existed as a parameter -- correct fallback for
            # the one caller-side edge case (no current Desk directory
            # known yet), not a bug to work around here. TODO f447303:
            # the Console/Claude widgets pass the current Desk's own
            # directory instead of leaving this unset.
            cwd=cwd,
            # start_new_session=True (not preexec_fn=os.setsid): preexec_fn
            # runs arbitrary Python between fork() and exec() and is unsafe
            # in a multi-threaded process -- which a running PyQt app is.
            # Confirmed directly: with preexec_fn, bash never actually
            # became a child process when run inside the real app (silent
            # failure, no exception); start_new_session achieves the same
            # "new session leader" result via a safe path. See LEARNINGS.md.
            start_new_session=True,
            env={**os.environ, "TERM": "xterm-256color"},
            close_fds=True,
        )
        os.close(slave_fd)
        os.set_blocking(self._master_fd, False)

        self._notifier = QSocketNotifier(self._master_fd, QSocketNotifier.Type.Read, self)
        self._notifier.activated.connect(self._on_readable)

        # Deliberately NOT `self.destroyed.connect(self._cleanup)`: connecting
        # an object's own `destroyed` signal to one of its own bound methods
        # never actually fires the slot (confirmed directly) -- by the time
        # `destroyed` is emitted, Qt no longer considers the emitting object
        # a valid receiver for its own signal. Closing over plain local
        # values and calling a staticmethod (no `self` involved at all) does
        # work correctly.
        master_fd = self._master_fd
        process = self._process
        self.destroyed.connect(lambda: TerminalWidget._cleanup_resources(master_fd, process))

    def type_into_shell(self, text: str) -> None:
        """Feeds text to the PTY's input exactly as if it had been typed
        via keyPressEvent -- e.g. to auto-launch a program in a freshly
        -spawned shell (see the Claude widget) rather than exec-ing it as
        the PTY's own process directly, so the shell's own startup/profile
        (PATH, aliases, etc.) loads first, the same way a user typing at a
        real terminal would get it."""
        try:
            os.write(self._master_fd, text.encode("utf-8"))
        except OSError:
            pass

    def _on_readable(self) -> None:
        try:
            data = os.read(self._master_fd, 4096)
        except OSError:
            data = b""
        if not data:
            self._notifier.setEnabled(False)
            self.appendPlainText("\n[process exited]")
            self.process_exited.emit()
            return
        self._stream.feed(data.decode("utf-8", errors="replace"))
        self._redraw()

    def _redraw(self) -> None:
        # Preserve any active mouse selection across the full-document
        # rebuild below. _redraw runs on every PTY read, and a live TUI
        # (claude) repaints near-continuously -- without this, a selection
        # is wiped almost as soon as it's made. The rebuild always
        # produces the same fixed grid (PTY_ROWS x PTY_COLS), so a
        # character offset denotes the same screen cell before and after,
        # making anchor/position stable to restore. See TODO 846303c.
        previous = self.textCursor()
        had_selection = previous.hasSelection()
        saved_anchor = previous.anchor()
        saved_position = previous.position()

        cursor = self.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.removeSelectedText()

        # The terminal cursor is rendered as a reverse-video block over its
        # cell (see _char_format's `invert`), not via QPlainTextEdit's own
        # native text cursor -- setReadOnly(True) strips
        # Qt.TextInteractionFlag.TextEditable from this widget's
        # interaction flags, and Qt never paints its native blinking
        # caret without that flag, no matter the cursor width/position/
        # focus state. See LEARNINGS.md / plans/console-widget-cursor
        # -visibility.md.
        screen_cursor = self._screen.cursor
        cursor_visible = not screen_cursor.hidden

        for y in range(PTY_ROWS):
            if y > 0:
                cursor.insertBlock()
            row = self._screen.buffer[y]
            run_text = ""
            run_format = None
            for x in range(PTY_COLS):
                char = row[x]
                is_cursor_cell = cursor_visible and y == screen_cursor.y and x == screen_cursor.x
                fmt = _char_format(char, invert=is_cursor_cell)
                if run_format is not None and fmt == run_format:
                    run_text += char.data
                else:
                    if run_text:
                        cursor.insertText(run_text, run_format)
                    run_text = char.data
                    run_format = fmt
            if run_text:
                cursor.insertText(run_text, run_format)

        if had_selection:
            last = self.document().characterCount() - 1
            restored = self.textCursor()
            restored.setPosition(min(saved_anchor, last))
            restored.setPosition(min(saved_position, last), QTextCursor.MoveMode.KeepAnchor)
            self.setTextCursor(restored)

    def _key_to_bytes(self, event) -> bytes | None:
        # event.key() is an int, but Qt.Key members compare/hash equal to
        # their int value, so the enum-keyed maps resolve directly.
        key = event.key()
        # Cursor keys / Home / End first: their prefix depends on whether
        # the app has enabled DECCKM (application cursor keys).
        letter = CURSOR_KEYS.get(key)
        if letter is not None:
            prefix = b"\x1bO" if DECCKM in self._screen.mode else b"\x1b["
            return prefix + letter
        data = KEY_BYTES.get(key)
        if data is not None:
            return data
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and (
            Qt.Key.Key_A.value <= key <= Qt.Key.Key_Z.value
        ):
            # Ctrl+A..Z -> control bytes 0x01..0x1a (Ctrl+C == 0x03 etc.)
            return bytes([key - Qt.Key.Key_A.value + 1])
        if event.text():
            return event.text().encode("utf-8")
        return None

    def keyPressEvent(self, event) -> None:
        # Ctrl+C copies when there's a selection, interrupts otherwise --
        # the standard terminal convention (and it sidesteps macOS's
        # Cmd->Control mapping, so whichever key Qt reports as Ctrl+C
        # copies a live selection). With no selection it falls through to
        # _key_to_bytes, which sends 0x03 (SIGINT) as before. See TODO
        # 846303c.
        if (
            event.modifiers() & Qt.KeyboardModifier.ControlModifier
            and event.key() == Qt.Key.Key_C
            and self.textCursor().hasSelection()
        ):
            self.copy()
            return
        data = self._key_to_bytes(event)
        if data:
            try:
                os.write(self._master_fd, data)
            except OSError:
                pass

    @staticmethod
    def _cleanup_resources(master_fd: int, process: subprocess.Popen) -> None:
        try:
            os.close(master_fd)
        except OSError:
            pass
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
