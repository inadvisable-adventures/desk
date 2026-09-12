"""Installed Jobs (TODO 7dca383) -- a durable, versioned alternative to
the ephemeral tempui-DSL `Job` mechanism (TODO d7e66f6, desk.jobs). An
agent writes real source directly to
`desk-installed-jobs/<name>/main.py` (project-root-relative, a sibling
of `.desk_temp`, not inside it -- this source is meant to persist, not
be regenerated from a tempui file the way a Job's cache is), then
installs it via the `desk_install_job` MCP tool
(desk.shell.desk_mcp_server). Once installed, `desk_run_installed_job`
can run it repeatedly with no further approval prompt -- see that
tool's own module docstring for the safety argument this relies on.

Registration lives in-memory on DeskWindow
(desk.shell.window.DeskWindow.install_job/uninstall_job) and is
mirrored into the current .desk file's own `installed_jobs` section
(desk.desks.Desk.installed_jobs) via the existing save_current_desk()
write path -- there is no separate write path, so the two can never
drift."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

INSTALLED_JOBS_DIRNAME = "desk-installed-jobs"
ENTRY_FILENAME = "main.py"

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
