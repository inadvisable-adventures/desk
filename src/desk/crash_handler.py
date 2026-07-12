"""A global, best-effort crash logger (TODO 95f7ce9). Installs a
`sys.excepthook` that appends any uncaught exception's traceback to a
`DESK-CRASH-<timestamp>.log` file in "the project folder"'s
`.desk_temp` directory (TODO 7f51230) -- the current Desk's directory
if one is known yet (`desk.shell.current_context`), else the process's
current working directory (the same fallback `desk.app.main()` itself
uses for the default project root before any Desk is loaded).
`.desk_temp` is created if it doesn't exist yet -- unlike
`TempUiManager.provision`'s own creation of the same directory, this
never prompts for consent first: crash logging is a different,
non-negotiable diagnostic concern that must never block or fail (see
below).

Confirmed directly (not assumed): `sys.excepthook` fires for an
uncaught exception raised inside a Qt slot, both a same-thread direct
connection and a cross-thread queued connection (the shape a
background `watchdog`-thread callback delivering into a GUI-thread
slot actually has) -- so installing this once, globally, is a
sufficient general mechanism for "an uncaught exception anywhere in
the app," not just plain synchronous code.

This handler's only job is additive logging. It must never itself
introduce a new failure -- the whole body is one broad `except
Exception: pass`, and the previously-installed hook (normally Python's
own `sys.__excepthook__`) is always still called afterward, so existing
stderr-traceback behavior is preserved, not replaced."""

import sys
import traceback
from datetime import datetime
from pathlib import Path

from desk.shell import current_context
from desk.temp_ui import TEMP_UI_DIRNAME

_previous_excepthook = None


def _log_path() -> Path:
    directory = current_context.get_current_desk_directory() or Path.cwd()
    temp_dir = directory / TEMP_UI_DIRNAME
    temp_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    return temp_dir / f"DESK-CRASH-{timestamp}.log"


def _handle_exception(exc_type, exc_value, tb) -> None:
    try:
        text = "".join(traceback.format_exception(exc_type, exc_value, tb))
        with open(_log_path(), "a") as f:
            f.write(text)
    except Exception:
        pass
    if _previous_excepthook is not None:
        _previous_excepthook(exc_type, exc_value, tb)


def install() -> None:
    """Idempotent -- calling this more than once (e.g. across tests)
    never double-chains or loses the original hook."""
    global _previous_excepthook
    if _previous_excepthook is not None:
        return
    _previous_excepthook = sys.excepthook
    sys.excepthook = _handle_exception
