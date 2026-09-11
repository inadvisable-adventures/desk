"""Materializes a tempui-DSL-defined one-shot "Desk Proc" (TODO
97bd090, desk.temp_ui.DeskProcDefinition) base64-encoded script onto
disk -- mirrors desk.jobs exactly, but under its own `desk_procs/`
cache subdir rather than `jobs/`, since a Desk Proc is a distinct
tempui kind from a Job (see DeskProcDefinition's own docstring for
why). Disposable, like desk.jobs/desk.custom_widgets: the actual source
of truth is the Desk Proc's own tempui file, regenerated fresh
whenever needed."""

import base64
import binascii
import logging
from pathlib import Path

from desk.temp_ui import DeskProcDefinition

logger = logging.getLogger(__name__)

DESK_PROC_CACHE_DIRNAME = "desk_procs"
PYTHON_DESK_PROC_ENTRY_FILENAME = "script.py"
# View Code's own plain-text copy (mirrors desk.jobs.SOURCE_VIEW_FILENAMES)
# -- deliberately named differently from the execution entry above so
# the two never collide inside the same desk_proc_dir, even though
# today they'd actually be byte-identical (a Desk Proc has no
# html-kind wrapping step the way a Job does) -- keeping the same
# two-file convention avoids a special case in materialize_script_body
# below and matches desk.jobs's own shape exactly.
SOURCE_VIEW_FILENAME = "desk_proc_source.py"


def desk_proc_dir(desk_temp_dir: Path, proc_id: str) -> Path:
    return desk_temp_dir / DESK_PROC_CACHE_DIRNAME / proc_id


def _decode(script_b64: str, proc_id: str) -> str | None:
    try:
        return base64.b64decode(script_b64.encode("ascii"), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        logger.error(
            "Failed to decode Desk Proc %r's script_b64 -- malformed base64/UTF-8",
            proc_id,
            exc_info=True,
        )
        return None


def materialize(desk_temp_dir: Path, proc_id: str, definition: DeskProcDefinition) -> Path | None:
    """Decodes `definition.script_b64` to a real, execution-ready
    `script.py` at desk_proc_dir(desk_temp_dir, proc_id). Returns the
    proc's directory, or None (logged, not raised) for malformed
    base64/UTF-8 -- one bad Desk Proc shouldn't take down anything
    else."""
    script = _decode(definition.script_b64, proc_id)
    if script is None:
        return None
    target_dir = desk_proc_dir(desk_temp_dir, proc_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / PYTHON_DESK_PROC_ENTRY_FILENAME).write_text(script)
    return target_dir


def materialize_script_body(desk_temp_dir: Path, proc_id: str, definition: DeskProcDefinition) -> Path | None:
    """The "View Code" button's own plain-text copy -- independent of
    materialize() above, same reasoning as desk.jobs
    .materialize_script_body. Returns None (logged, not raised) for the
    same malformed-content reason as materialize()."""
    script = _decode(definition.script_b64, proc_id)
    if script is None:
        return None
    target_dir = desk_proc_dir(desk_temp_dir, proc_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / SOURCE_VIEW_FILENAME
    path.write_text(script)
    return path
