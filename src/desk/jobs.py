"""Materializes a tempui-DSL-defined one-shot agent Job's (TODO
d7e66f6, desk.temp_ui.JobDefinition) base64-encoded script onto disk --
mirrors desk.custom_widgets, but under its own `jobs/` cache subdir
rather than `custom_widgets/`, since a Job is never a reusable widget
*kind* the way a `DefineWidget` is (see desk.temp_ui.JobDefinition's
own docstring). Disposable, like desk.custom_widgets: the actual
source of truth is the Job's own tempui file, regenerated fresh
whenever needed."""

import base64
import binascii
import logging
from pathlib import Path

from desk.temp_ui import JobDefinition

logger = logging.getLogger(__name__)

JOBS_CACHE_DIRNAME = "jobs"
HTML_JOB_ENTRY_FILENAME = "index.html"
PYTHON_JOB_ENTRY_FILENAME = "script.py"
# View Code's own plain-text copy (TODO d7e66f6) -- deliberately named
# differently from the html-kind execution entry above, so the two
# never collide inside the same job_dir: index.html is what the
# server actually serves; job_source.* exists purely to give
# desk.editor.openOrScrap a real file to open.
SOURCE_VIEW_FILENAMES = {"python": "job_source.py", "html": "job_source.html"}


def job_dir(desk_temp_dir: Path, job_id: str) -> Path:
    return desk_temp_dir / JOBS_CACHE_DIRNAME / job_id


def _decode(script_b64: str, job_id: str) -> str | None:
    try:
        return base64.b64decode(script_b64.encode("ascii"), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        logger.error(
            "Failed to decode Job %r's script_b64 -- malformed base64/UTF-8",
            job_id,
            exc_info=True,
        )
        return None


def materialize(desk_temp_dir: Path, job_id: str, definition: JobDefinition) -> Path | None:
    """Decodes `definition.script_b64` to a real, execution-ready file
    at job_dir(desk_temp_dir, job_id) -- `index.html` for `kind ==
    "html"` (so it can be mounted and served exactly like any other
    `kind: "html"` widget), `script.py` for `kind == "python"`.
    Returns the job's directory, or None (logged, not raised) for
    malformed base64/UTF-8 -- one bad Job shouldn't take down anything
    else."""
    script = _decode(definition.script_b64, job_id)
    if script is None:
        return None
    target_dir = job_dir(desk_temp_dir, job_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    entry = HTML_JOB_ENTRY_FILENAME if definition.kind == "html" else PYTHON_JOB_ENTRY_FILENAME
    (target_dir / entry).write_text(script)
    return target_dir


def materialize_script_body(desk_temp_dir: Path, job_id: str, definition: JobDefinition) -> Path | None:
    """The "View Code" button's own plain-text copy (TODO d7e66f6) --
    independent of materialize() above (which writes an
    execution-ready index.html for the html case, not a plain-text
    view of the source). Returns None (logged, not raised) for the
    same malformed-content reason as materialize()."""
    script = _decode(definition.script_b64, job_id)
    if script is None:
        return None
    target_dir = job_dir(desk_temp_dir, job_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = SOURCE_VIEW_FILENAMES[definition.kind]
    path = target_dir / filename
    path.write_text(script)
    return path
