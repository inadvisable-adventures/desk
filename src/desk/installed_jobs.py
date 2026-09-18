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
drift.

A second kind (TODO 94a2fa2): `desk-installed-jobs/<name>/Cargo.toml`
(+ `src/`) is a `rust`-kind job -- for computationally-intensive work
that wants a compiled language and, where useful, direct GPU access
(confirmed directly, a real `wgpu` compute shader dispatched and its
output read back correctly against this machine's Metal backend --
see plans/installed-jobs-rust-gpu.md). Kind is never persisted --
detect_kind() below sniffs it from which entry file is present, the
same "check job_dir's own contents" approach install_job already used
for the python-only case, so no `.desk` file schema migration was
needed. A `rust`-kind job is built on demand (cargo build --release,
mtime-cached against its own source, same on-demand-build shape
desk_services.transforms already uses for TypeScript) and run as a
real subprocess -- see run_rust_job below. `main.py` is exec'd
in-process and so can, incidentally, reach this process's own live
Python state via whatever it imports (undocumented, fragile); a
compiled Rust job structurally cannot reach any of that at all, which
is what motivates the declared-needs mechanism a few paragraphs down."""

import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import threading
import tomllib
import traceback
from dataclasses import dataclass
from pathlib import Path

INSTALLED_JOBS_DIRNAME = "desk-installed-jobs"
ENTRY_FILENAME = "main.py"
RUST_MANIFEST_FILENAME = "Cargo.toml"
# TODO 94a2fa2: an optional per-job manifest -- currently just
# {"needs": [<desk.state.* key>, ...]} -- kept separate from
# ENTRY_FILENAME/RUST_MANIFEST_FILENAME since it's orthogonal to kind
# (a python-kind job can declare needs too, see
# desk.shell.window.DeskWindow._resolve_job_needs).
JOB_MANIFEST_FILENAME = "job.json"
# TODO 94a2fa2: where a run's resolved `needs` values are written --
# under .desk_temp/ (already-gitignored, ephemeral, per-project scratch
# space), never inside the job's own durable desk-installed-jobs/<name>/
# source directory, and regenerated fresh on every run rather than kept
# around.
INSTALLED_JOB_NEEDS_DIRNAME = "installed-job-needs"

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


def detect_kind(job_dir: Path) -> str | None:
    """TODO 94a2fa2: `"python"`/`"rust"`/`None` (neither, or both --
    ambiguous) based purely on which entry marker is present under
    job_dir -- the same "check the directory's own contents" approach
    install_job already used when it only ever checked for
    ENTRY_FILENAME. Never persisted (see this module's own docstring):
    called fresh by install_job (to validate) and run_installed_job (to
    dispatch), so there's nothing to keep in sync if a job's own files
    change between an install and a later run -- get_installed_job_for_run's
    hash check already refuses a run in that case anyway."""
    has_python = (job_dir / ENTRY_FILENAME).is_file()
    has_rust = (job_dir / RUST_MANIFEST_FILENAME).is_file()
    if has_python and not has_rust:
        return "python"
    if has_rust and not has_python:
        return "rust"
    return None


def compute_version_hash(job_dir: Path) -> str:
    """A reasonable-sized (12 hex chars), deterministic hash of every
    regular file under job_dir -- a direct multi-file extension of the
    single-blob `hashlib.md5(...).hexdigest()[:12]` convention
    desk.shell.window.DeskWindow's own custom-widget staleness check
    already established (TODO 5995ffd, window.py's
    _custom_widget_content_hash), not a new hashing convention. Each
    file's path (sorted, so file discovery order never matters) and
    content are both folded in, so renaming a file changes the version
    even if no file's content did.

    TODO 94a2fa2: skips anything under a `target/` path component
    (cargo's own build-output directory for a rust-kind job) and a
    root-level `Cargo.lock`. Without the `target/` exclusion, the very
    first `cargo build` a run ever triggers would change the hash out
    from under the version that was actually approved at install time,
    permanently breaking that job's "no reapproval on every run"
    guarantee the moment it's first run -- confirmed the hard way (a
    real second-run failure during this item's own verification, not
    just reasoned about): `cargo build` *also* writes/updates
    `Cargo.lock` at the project root -- outside `target/` -- the first
    time it runs without one already present, which hit the exact same
    bug for a second, easy-to-miss reason. `Cargo.lock` is otherwise
    real content (pinned dependency versions), so this is a deliberate,
    narrow exception, not a blanket "ignore lock files" rule -- see
    LEARNINGS.md. Both exclusions are harmless for a python-kind job,
    which has no reason to ever have either of its own."""
    digest = hashlib.md5()
    for path in sorted(p for p in job_dir.rglob("*") if p.is_file()):
        relative = path.relative_to(job_dir)
        if "target" in relative.parts[:-1] or relative == Path("Cargo.lock"):
            continue
        digest.update(relative.as_posix().encode("utf-8"))
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


def run_script(
    script_text: str, job_dir: Path, config_path: str | None, needs_path: str | None = None
) -> tuple[bool, str, str, str]:
    """Runs on a background thread (spawned by
    desk.shell.window.DeskWindow.run_installed_job -- never the GUI
    thread, same "no Qt access from inside the job" rule a regular
    Job's own `_run_python_job`, widgets/job_runner/widget.py, already
    follows). `job_dir` is put on sys.path for the duration so main.py
    can import sibling files in its own directory; CONFIG_PATH is the
    documented way a script reads its own already-resolved
    config-file argument (see resolve_config_path above and
    tempui-installed-jobs.md) -- None if the caller didn't pass one.
    NEEDS_PATH (TODO 94a2fa2) is the same idea for a job.json-declared
    desk.state.* needs file -- see
    desk.shell.window.DeskWindow._resolve_job_needs -- None if the job
    declared no needs. Returns (ok, stdout, stderr, traceback) rather
    than raising, mirroring _run_python_job's own relay payload shape."""
    stdout = io.StringIO()
    stderr = io.StringIO()
    job_dir_str = str(job_dir)
    with _RUN_LOCK:
        sys.path.insert(0, job_dir_str)
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exec(
                    compile(script_text, "<installed_job>", "exec"),
                    {"__name__": "__installed_job__", "CONFIG_PATH": config_path, "NEEDS_PATH": needs_path},
                )
            return True, stdout.getvalue(), stderr.getvalue(), ""
        except Exception:
            return False, stdout.getvalue(), stderr.getvalue(), traceback.format_exc()
        finally:
            with contextlib.suppress(ValueError):
                sys.path.remove(job_dir_str)


class RustJobError(Exception):
    pass


def _resolve_cargo_binary() -> str:
    """TODO 94a2fa2: `cargo` was found reliably installed via `rustup`
    at `~/.cargo/bin/cargo` on the machine this was developed against,
    but *not* on every shell/process's own `PATH` -- rustup's installer
    adds it to interactive shells' startup files, which a GUI app
    launched some other way won't necessarily have sourced. Checking
    `shutil.which` first (works whenever it genuinely is on PATH) and
    falling back to the well-known rustup install location (rather than
    assuming `["cargo", ...]` will just resolve, the way transforms'
    `["node", ...]`/`["tsc", ...]` calls do) avoids a confusing
    FileNotFoundError for a toolchain that actually is installed. See
    LEARNINGS.md."""
    found = shutil.which("cargo")
    if found is not None:
        return found
    fallback = Path.home() / ".cargo" / "bin" / "cargo"
    if fallback.is_file():
        return str(fallback)
    raise RustJobError(
        "cargo not found (checked PATH and ~/.cargo/bin/cargo) -- install Rust via https://rustup.rs"
    )


def _rust_binary_path(job_dir: Path) -> Path:
    manifest_path = job_dir / RUST_MANIFEST_FILENAME
    try:
        manifest = tomllib.loads(manifest_path.read_text())
        package_name = manifest["package"]["name"]
    except (OSError, tomllib.TOMLDecodeError, KeyError) as e:
        raise RustJobError(f"couldn't read {manifest_path}'s [package].name: {e}") from e
    return job_dir / "target" / "release" / package_name


def _ensure_rust_binary_built(job_dir: Path, cargo: str) -> Path:
    """Mirrors desk_services.transforms._resolve_js_entry's own
    on-demand-build shape exactly (an on-demand `tsc -p <dir>` there, an
    on-demand `cargo build --release` here): builds only if the
    compiled binary is missing or older than any of the job's own
    source files (Cargo.toml/Cargo.lock/every src/**/*.rs) -- a no-op,
    fast check on every run after the first. No timeout on the build
    itself (TODO 94a2fa2's whole motivation is letting a genuinely
    long, computationally-heavy job finish -- see run_rust_job's own
    docstring for why the run itself is also unbounded)."""
    binary = _rust_binary_path(job_dir)
    source_files = [job_dir / RUST_MANIFEST_FILENAME, job_dir / "Cargo.lock", *(job_dir / "src").rglob("*.rs")]
    source_mtimes = [p.stat().st_mtime for p in source_files if p.is_file()]
    needs_build = not binary.is_file() or (source_mtimes and max(source_mtimes) > binary.stat().st_mtime)
    if needs_build:
        result = subprocess.run([cargo, "build", "--release"], cwd=job_dir, capture_output=True, text=True)
        if result.returncode != 0:
            raise RustJobError(f"cargo build failed:\n{result.stdout}\n{result.stderr}")
    if not binary.is_file():
        raise RustJobError(f"cargo build did not produce the expected binary at {binary}")
    return binary


def run_rust_job(job_dir: Path, config_path: str | None, needs_path: str | None) -> tuple[bool, str, str, str]:
    """TODO 94a2fa2: the rust-kind counterpart to run_script above --
    same (ok, stdout, stderr, traceback) shape and the same "runs on a
    background thread, never the GUI thread" calling convention (the
    build step alone is a slow, blocking subprocess call). Unlike
    run_script, this is a real, separate OS process -- CONFIG_PATH/
    NEEDS_PATH become real environment variables
    (DESK_JOB_CONFIG_PATH/DESK_JOB_NEEDS_PATH), only set when given (so
    a job reads `std::env::var(...).ok()` as idiomatic "wasn't given"
    rather than an empty-string sentinel), and `traceback` is a plain
    "exited with code N" note rather than a real Python traceback,
    since a compiled binary has no equivalent to hand back -- stderr is
    where the job's own diagnostic output belongs. No timeout on the
    run itself, matching run_script's own unbounded execution (only
    the Bridge API's synchronous-wait layer above either path is
    time-bounded, see INSTALLED_JOB_RUN_TIMEOUT_SECONDS)."""
    try:
        cargo = _resolve_cargo_binary()
        binary = _ensure_rust_binary_built(job_dir, cargo)
    except RustJobError as e:
        return False, "", str(e), ""
    env = dict(os.environ)
    if config_path is not None:
        env["DESK_JOB_CONFIG_PATH"] = config_path
    if needs_path is not None:
        env["DESK_JOB_NEEDS_PATH"] = needs_path
    try:
        result = subprocess.run([str(binary)], cwd=job_dir, capture_output=True, text=True, env=env)
    except OSError as e:
        return False, "", str(e), ""
    ok = result.returncode == 0
    return ok, result.stdout, result.stderr, "" if ok else f"process exited with code {result.returncode}"
