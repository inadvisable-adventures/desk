"""Installed Jobs (TODO 7dca383) -- a durable, versioned alternative to
the ephemeral tempui-DSL `Job` mechanism (TODO d7e66f6, desk.jobs). An
agent writes real source directly to
`desk-installed-jobs/<name>/main.py` (project-root-relative, a sibling
of `.desk_temp`, not inside it -- this source is meant to persist, not
be regenerated from a tempui file the way a Job's cache is), then
installs it via the `desk_install_job` MCP tool
(desk.shell.desk_mcp_server). Once installed, it can be run repeatedly
with no further approval prompt -- either by an agent, via the
`desk_run_installed_job` MCP tool, or by a `kind: "html"` widget with
the `installed_jobs` capability, via `desk.installedJobs.run(name,
configPath)` (TODO 888b537). Both entry points call through
desk.shell.window.DeskWindow.run_installed_job -- see its own docstring
for the safety argument ("no reapproval on every run" relies on the
on-disk source never silently diverging from what was actually
installed/approved) this single shared implementation exists to
protect; run_script/resolve_config_path below are its two building
blocks, factored out here (rather than duplicated once per entry
point) for exactly that reason.

Registration lives in-memory on DeskWindow
(desk.shell.window.DeskWindow.install_job/uninstall_job) and is
mirrored into the current .desk file's own `installed_jobs` section
(desk.desks.Desk.installed_jobs) via the existing save_current_desk()
write path -- there is no separate write path, so the two can never
drift."""

import contextlib
import hashlib
import io
import sys
import threading
import traceback
from dataclasses import dataclass
from pathlib import Path

INSTALLED_JOBS_DIRNAME = "desk-installed-jobs"
ENTRY_FILENAME = "main.py"

# Bounds only the Bridge API's synchronous wait for a run
# (src.desk.server.app's installed_jobs_run route, via
# GuiBridge.call_async's own `timeout`) -- the MCP path
# (desk_run_installed_job) awaits with no bound at all, since it isn't
# a synchronous HTTP request/response. A job whose own run genuinely
# takes longer than this should be run via the MCP/agent-initiated path
# instead; note that a Bridge-side timeout does NOT stop the job itself
# -- it keeps running to completion in the background regardless, the
# caller just stops waiting for the result.
INSTALLED_JOB_RUN_TIMEOUT_SECONDS = 120.0

# Published by DeskWindow.install_job/uninstall_job whenever
# self.current_desk.installed_jobs changes, payload {"jobs": [...]}
# (the same shape get_installed_jobs_dicts returns) -- mirrors
# desk.file_type_registry.FILE_TYPE_REGISTRY_UPDATED_EVENT's exact
# publish-on-mutation/subscribe-via-EventSubscription pattern, so the
# Installed Jobs widget stays current after an install/uninstall that
# happened elsewhere (e.g. an MCP tool call) without polling.
INSTALLED_JOBS_UPDATED_EVENT = "desk.installed_jobs.updated"


@dataclass
class InstalledJobDefinition:
    name: str
    version_hash: str
    installed_at: str  # ISO 8601 (datetime.now().isoformat()), display-only


def installed_job_dir(project_directory: Path, name: str) -> Path:
    return project_directory / INSTALLED_JOBS_DIRNAME / name


def compute_version_hash(job_dir: Path) -> str:
    """A reasonable-sized (12 hex chars), deterministic hash of every
    regular file under job_dir -- a direct multi-file extension of the
    single-blob `hashlib.md5(...).hexdigest()[:12]` convention
    desk.shell.window.DeskWindow's own custom-widget staleness check
    already established (TODO 5995ffd, window.py's
    _custom_widget_content_hash), not a new hashing convention. Each
    file's path (sorted, so file discovery order never matters) and
    content are both folded in, so renaming a file changes the version
    even if no file's content did."""
    digest = hashlib.md5()
    for path in sorted(p for p in job_dir.rglob("*") if p.is_file()):
        digest.update(path.relative_to(job_dir).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:12]


def resolve_config_path(directory: Path, raw: str | None) -> str | None:
    """The shared "a relative config_path resolves against the current
    Desk's own directory" rule -- `raw` is whatever a caller (the MCP
    tool's `config_path` argument, or the Bridge API route's
    `config_path` body field) passed, verbatim; `None`/empty stays
    `None` (the job's own CONFIG_PATH global, see run_script below).
    An already-absolute path is used as-is."""
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = directory / path
    return str(path)


# sys.path is process-global -- serializes concurrent installed-job
# runs (each already on its own background thread) against each other
# so one job's temporary sys.path entry can never leak into a second
# job's own import resolution if two runs happen to overlap (e.g. one
# via the MCP tool, one via the Bridge API, or two calls in the same
# agent turn). Installed Jobs are not meant to be a high-throughput
# concurrent system -- serializing here is a minimal, correct fix, not
# a performance concession that costs anything in practice.
_RUN_LOCK = threading.Lock()


def run_script(script_text: str, job_dir: Path, config_path: str | None) -> tuple[bool, str, str, str]:
    """Runs on a background thread (spawned by
    desk.shell.window.DeskWindow.run_installed_job -- never the GUI
    thread, same "no Qt access from inside the job" rule a regular
    Job's own `_run_python_job`, widgets/job_runner/widget.py, already
    follows). `job_dir` is put on sys.path for the duration so main.py
    can import sibling files in its own directory; CONFIG_PATH is the
    documented way a script reads its own already-resolved
    config-file argument (see resolve_config_path above and
    tempui-installed-jobs.md) -- None if the caller didn't pass one.
    Returns (ok, stdout, stderr, traceback) rather than raising,
    mirroring _run_python_job's own relay payload shape."""
    stdout = io.StringIO()
    stderr = io.StringIO()
    job_dir_str = str(job_dir)
    with _RUN_LOCK:
        sys.path.insert(0, job_dir_str)
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exec(
                    compile(script_text, "<installed_job>", "exec"),
                    {"__name__": "__installed_job__", "CONFIG_PATH": config_path},
                )
            return True, stdout.getvalue(), stderr.getvalue(), ""
        except Exception:
            return False, stdout.getvalue(), stderr.getvalue(), traceback.format_exc()
        finally:
            with contextlib.suppress(ValueError):
                sys.path.remove(job_dir_str)
