# `rust` kind for Installed Jobs, with confirmed GPU access and declared `desk.state` needs (TODO `94a2fa2`)

## Summary

Installed Jobs (TODO `7dca383`, `src/desk/installed_jobs.py`) currently
support exactly one shape: `desk-installed-jobs/<name>/main.py`, `exec`'d
in-process. This plan adds a second, `rust`-kind shape --
`desk-installed-jobs/<name>/Cargo.toml` (+ `src/`) -- for
computationally-intensive work that wants a compiled language and,
where useful, direct GPU access, mirroring the on-demand-build shape
`desk_services.transforms` already uses for TypeScript.

Also adds a small, kind-agnostic "declared needs" mechanism: a job can
list which `desk.state.*` keys it wants, and Desk resolves just those
and hands the job a file to read them from before it runs. This is
necessary for a `rust`-kind job (a real, separate OS process with no
path into this app's own Python memory at all) and is offered to
`python`-kind jobs too, replacing their only current option -- an
undocumented, fragile `import` into this process's live state.

## Investigation: does a Rust program actually have GPU access here?

Confirmed directly, not assumed. `rustc`/`cargo` are already installed
(`rustup`, at `~/.cargo/bin` -- not on this shell's default `PATH`,
see Key tradeoffs). A real Cargo project using the `wgpu` crate
(cross-platform: Metal/Vulkan/DX12/GL, actively maintained, the most
widely used Rust GPU-compute crate) was built and run:

1. `wgpu::Instance::request_adapter` found a real adapter: `name=Apple
   M2 Pro backend=Metal`.
2. Beyond just detecting an adapter, an actual WGSL **compute shader**
   was authored, compiled, dispatched against a real input buffer, and
   its output read back: a 16-element `f32` array doubled entirely on
   the GPU, verified byte-for-byte against the expected result
   (`SHADER_RESULT_CORRECT=true`).
3. First `cargo build --release` (fetching + compiling `wgpu` and its
   ~40-crate dependency tree from crates.io) took ~33s; a source-only
   change rebuilds in under a second.

Conclusion: yes, a Rust job on this machine can author and run real
GPU/shader programs via `wgpu`, with no exotic setup beyond a normal
`cargo build`. `wgpu` is documented as the recommended crate (not
hard-required -- see Key tradeoffs) in the doc update below.

## Design decisions

- **Kind is detected from job_dir contents, not stored.** `install_job`
  already only checks "does the expected entry file exist"; extending
  that to "`main.py` XOR `Cargo.toml`" needs no new persisted field, no
  `.desk` file schema migration, and no change to
  `InstalledJobDefinition`/`desks.py` serialization at all. Both
  present, or neither, is a clear install-time error (ambiguous/
  missing), not a guess.
- **Build lazily, at run time, mtime-cached** -- exactly
  `desk_services.transforms._resolve_js_entry`'s own shape (an
  on-demand `tsc -p <dir>` there; here, an on-demand `cargo build
  --release`), for the same reason: a `cargo build` (worse, its first
  one, fetching a real dependency tree) is a slow, blocking subprocess
  call that must never run on the GUI thread, and `install_job` is a
  synchronous GUI-thread call today. Installing a `rust`-kind job stays
  exactly as fast as installing a `python`-kind one; the first `run`
  pays the build cost once.
- **`compute_version_hash` must exclude `target/`.** It hashes every
  regular file under `job_dir` -- `cargo build`'s own output directory
  would otherwise make a job's version hash change on every build,
  immediately breaking `get_installed_job_for_run`'s "source on disk
  still matches what was installed" check the very first time a
  freshly-installed `rust` job is run (a real correctness bug, not a
  hypothetical -- confirmed by reasoning through the exact call
  sequence `install_job` -> `run_installed_job` -> build -> next
  `run_installed_job` -> hash check). Fixed by skipping any path with a
  `target` directory component, unconditionally (harmless for
  `python`-kind jobs, which have no reason to ever have one).
- **No hard timeout on the build or the run.** Matches this codebase's
  own existing convention for jobs specifically (as opposed to
  transforms, which do have `NODE_TIMEOUT_SECONDS`): `run_script`
  (python-kind) has no subprocess timeout today, only the *Bridge
  API's* synchronous-wait bound (`INSTALLED_JOB_RUN_TIMEOUT_SECONDS`,
  which doesn't stop the job, just stops waiting for it). The whole
  motivation here is letting a genuinely long-running, computationally
  -heavy job finish -- an artificial timeout on the build or the
  compiled binary itself would directly undercut that.
- **Declared needs: a small `job.json` manifest, `{"needs": [<state
  key>, ...]}`, optional.** Resolved on the GUI thread (the only thread
  `DeskWindow.get_state` -- the exact method `desk.state.get`'s Bridge
  route already calls -- is safe to call from) inside
  `run_installed_job`, before the background thread that actually runs
  the job is spawned -- the same "resolve synchronously up front" shape
  `resolve_config_path` already has. Writes `{key: {"value":...,
  "edit":...}, ...}` (the identical per-key shape `get_state` already
  returns) to `.desk_temp/installed-job-needs/<name>.json` -- ephemeral,
  regenerated every run, already-gitignored territory (`.desk_temp/`),
  not inside the job's own durable source directory. No manifest, or an
  empty/missing `needs` list, resolves nothing and writes nothing --
  fully backward compatible with every job that predates this.
- **How a job reads it: `CONFIG_PATH`'s own convention, generalized and
  made kind-agnostic.** A `python`-kind job already gets `CONFIG_PATH`
  as an `exec()` global; it now also gets `NEEDS_PATH` the same way. A
  `rust`-kind job (a real subprocess, no shared Python globals to hand
  it) gets the equivalent as real environment variables:
  `DESK_JOB_CONFIG_PATH`/`DESK_JOB_NEEDS_PATH`, only set when the
  corresponding value is not `None` (so `std::env::var(...).ok()` reads
  as idiomatic "wasn't given" rather than an empty-string sentinel).
  One mechanism, two equally-natural bindings for the two execution
  models -- not two different concepts.
- **`desk.state.*` only, not the in-process Desk MCP server or any
  other live channel.** The motivating gap is specifically "a
  `python`-kind job's own imports can incidentally reach this
  process's live state, and a `rust`-kind job structurally can't reach
  *anything* at all" -- `desk.state.*` is this app's own existing,
  intentional cross-widget/cross-job data-sharing surface (TODO
  `f68383f`), so that's the one thing worth exposing a declared-access
  path to. Nothing else (event subscription, other widgets' internal
  state, the filesystem beyond `job_dir`/`CONFIG_PATH`) is in scope.

## Affected files

- `src/desk/installed_jobs.py` -- `detect_kind`, `RUST_MANIFEST_FILENAME`,
  `run_script` gains a `needs_path` parameter, new `run_rust_job`
  (build-on-demand + subprocess run), `_resolve_cargo_binary`,
  `JOB_MANIFEST_FILENAME`/`INSTALLED_JOB_NEEDS_DIRNAME` constants,
  `compute_version_hash` excludes `target/`.
- `src/desk/shell/window.py` -- `install_job` validates via
  `detect_kind` instead of a hardcoded `main.py` check;
  `run_installed_job` dispatches on kind, adds `_resolve_job_needs`;
  calls `ensure_installed_jobs_gitignore_entry` (new, in `temp_ui.py`)
  at the same two moments `ensure_desk_widgets_gitignore_entry` already
  is.
- `src/desk/temp_ui.py` -- `INSTALLED_JOBS_RUST_TARGET_GITIGNORE_ENTRY`/
  `ensure_installed_jobs_gitignore_entry` (mirrors
  `DESK_WIDGETS_BUILD_GITIGNORE_ENTRY`/
  `ensure_desk_widgets_gitignore_entry` exactly); `_INSTALLED_JOBS_DOC`
  gets a new "Rust jobs and the GPU" + "Declaring what a job needs"
  section; new tag `"rust installed jobs + declared state needs
  #739624"` added to `CURRENT_TAGS`, with a matching `_NEW_FEATURES`
  entry.
- `src/desk/shell/desk_mcp_server.py` -- `desk_install_job`/
  `desk_run_installed_job` tool descriptions mention the `rust` kind
  and declared needs.
- `widgets/installed_jobs/widget.py` -- row label shows kind;
  `_view_source` skips anything under a `target/` directory (it
  `rglob("*")`s the whole job dir today -- would otherwise try to open
  every build artifact file after a `rust` job's first run).
- `tests/verify/` -- new fast coverage (a dependency-free Rust job, see
  Verification) plus one slow, real-`wgpu` opt-in script.
- `LEARNINGS.md` -- the `cargo`-not-on-`PATH` gotcha (see Key
  tradeoffs).

## Step-by-step implementation

1. `installed_jobs.py`: add `RUST_MANIFEST_FILENAME = "Cargo.toml"`,
   `JOB_MANIFEST_FILENAME = "job.json"`,
   `INSTALLED_JOB_NEEDS_DIRNAME = "installed-job-needs"`.
2. `detect_kind(job_dir) -> str | None`: `"python"`/`"rust"`/`None`
   (missing or ambiguous) based on `ENTRY_FILENAME`/
   `RUST_MANIFEST_FILENAME` presence.
3. `compute_version_hash`: skip any `path` whose `.relative_to(job_dir)
   .parts` contains `"target"`.
4. `_resolve_cargo_binary() -> str`: `shutil.which("cargo")`, falling
   back to `~/.cargo/bin/cargo` if that exists, else raise a clear
   `RustJobError` naming both what was tried and the rustup install
   URL.
5. `_rust_binary_path(job_dir) -> Path`: `tomllib.loads((job_dir /
   RUST_MANIFEST_FILENAME).read_text())["package"]["name"]` ->
   `job_dir / "target" / "release" / <name>`.
6. `_ensure_rust_binary_built(job_dir, cargo) -> Path`: mtime-compares
   the binary against `Cargo.toml`/`Cargo.lock`/every `src/**/*.rs`;
   runs `cargo build --release` (`cwd=job_dir`, no timeout) only if
   stale/missing; raises `RustJobError` with combined stdout/stderr on
   a nonzero return code or a missing output binary.
7. `run_rust_job(job_dir, config_path, needs_path) -> tuple[bool, str,
   str, str]`: resolves cargo + the binary (catching `RustJobError` ->
   `(False, "", <message>, "")`), runs the binary (`cwd=job_dir`, env =
   current environment plus `DESK_JOB_CONFIG_PATH`/
   `DESK_JOB_NEEDS_PATH` only when given, no timeout), returns `(returncode
   == 0, stdout, stderr, "" or f"process exited with code {returncode}")`.
8. `run_script` (existing, python-kind): add `needs_path: str | None`
   parameter, add `"NEEDS_PATH": needs_path` to the `exec()` globals
   dict alongside `CONFIG_PATH`.
9. `temp_ui.py`: `INSTALLED_JOBS_RUST_TARGET_GITIGNORE_ENTRY =
   f"{INSTALLED_JOBS_DIRNAME}/**/target/"` (import
   `INSTALLED_JOBS_DIRNAME` from `installed_jobs.py`);
   `ensure_installed_jobs_gitignore_entry(directory, ask)` -- copy of
   `ensure_desk_widgets_gitignore_entry`'s body, conditioned on
   `directory / INSTALLED_JOBS_DIRNAME` existing instead of
   `PROMOTED_WIDGET_SRC_DIRNAME`.
10. `window.py`:
    - `install_job`: replace the hardcoded `entry_path.is_file()` check
      with `detect_kind(directory)`; `None` -> the same
      `(False, message)` shape, message naming both possible entry
      files. On success, also call
      `ensure_installed_jobs_gitignore_entry` (mirrors the two
      `ensure_desk_widgets_gitignore_entry` call sites exactly -- add
      the call in `install_job` itself, and alongside the existing one
      in `_provision_temp_ui`).
    - New `_resolve_job_needs(self, name, job_dir) -> str | None` per
      Design decisions above.
    - `run_installed_job`: call `_resolve_job_needs`; branch on
      `detect_kind(job_dir)` (`None` here -- despite `
      get_installed_job_for_run`'s hash check making it practically
      unreachable -- reports a clear error via `on_result` rather than
      raising); python branch passes `needs_path` through to
      `run_installed_job_script`; rust branch calls the new
      `run_rust_job` (imported as `run_rust_installed_job`, mirroring
      the existing `run_script as run_installed_job_script` alias).
11. `desk_mcp_server.py`: update both tool descriptions (mention the
    `rust` kind + `Cargo.toml`, and `job.json`'s `needs` list +
    `NEEDS_PATH`/`DESK_JOB_NEEDS_PATH`).
12. `widgets/installed_jobs/widget.py`: `_build_row`'s label includes
    kind (`detect_kind` needs `job_dir`, already resolvable via
    `installed_job_dir(current_context.get_current_desk_directory(),
    job["name"])` -- read lazily per row, not added to the provider
    dict, to avoid a wider payload-shape change for one label);
    `_view_source` skips any path under a `target/` component.
13. `temp_ui.py`'s `_INSTALLED_JOBS_DOC`: new "Rust jobs and the GPU"
    section (entry shape, `wgpu` recommendation + the confirmed-working
    minimal example, build caching, no capability list/sandboxing any
    more than `python`-kind already has) and "Declaring what a job
    needs" section (`job.json`, `NEEDS_PATH`/`DESK_JOB_NEEDS_PATH`
    shape, applies to both kinds). Mint the tag, add to `CURRENT_TAGS`,
    add the matching `_NEW_FEATURES` entry.
14. `LEARNINGS.md`: the `cargo`/`PATH` gotcha (see Key tradeoffs).
15. Verification (below).

## Key tradeoffs / deliberately out of scope

- **`rust` is not added to the ephemeral tempui `Job` mechanism** (TODO
  `d7e66f6`, `desk.jobs`/`JobDefinition`) -- that format is a single
  base64-encoded script body, which has no way to represent a
  multi-file Cargo project (`Cargo.toml` + `src/` + generated
  `Cargo.lock`). Installed Jobs already durably store real multi-file
  source on disk, which is what a Cargo project actually needs --
  extending the one-shot mechanism instead would mean inventing a
  second, worse multi-file format for no real benefit.
- **`wgpu` is documented as the recommended crate, not hard-enforced.**
  A `rust`-kind job is a real Cargo project with its own `Cargo.toml`
  -- same as how a TypeScript transform can use anything Node's global
  object already exposes, a Rust job can declare whatever crates.io
  dependencies it wants (`cargo build` fetches and compiles them in one
  step; there's no separate "install" phase to add, unlike what an
  analogous npm-based TS/JS story would have needed -- this is *less*
  new machinery than it might look like, not more). Desk doesn't
  gate or vet which crates a job pulls in, matching the exact same
  trust level `python`-kind jobs already have ("the same unrestricted,
  no-sandboxing in-process access any other Python code already
  running in this process has").
- **`cargo`/`rustc` found at `~/.cargo/bin`, not on this shell tool's
  own `PATH`.** A real, reproducible environment gap -- worth a
  `LEARNINGS.md` entry and the `_resolve_cargo_binary` fallback (step
  4) rather than assuming `subprocess.run(["cargo", ...])` will just
  work the way `["node", ...]`/`["tsc", ...]` already reliably do for
  transforms.
- **No new capability-list/sandboxing story for `rust` jobs** -- same
  trust level `python`-kind Installed Jobs already have (full local
  execution, one approval at install time, no re-prompt on run). The
  compiled binary is not run inside a sandbox; this is a deliberate,
  explicit continuation of the existing trust model, not a new gap
  introduced by this change.
- **`needs` only covers `desk.state.*`**, not arbitrary other
  Desk-internal state -- see Design decisions.

## Verification

1. Fast, always-run coverage (`tests/verify/verify_installed_jobs_rust.py`):
   a minimal, dependency-free Rust job (no external crates -- keeps
   this in the normal, fast sweep) installed and run through the real
   `DeskWindow.install_job`/`run_installed_job` pipeline (a temp
   project directory, same shape `verify_installed_jobs.py` already
   uses for the python case):
   - Installs successfully; `detect_kind` reports `"rust"`.
   - First run builds and executes; stdout/exit code round-trip
     correctly; a second run (no source change) does not rebuild
     (compiled-binary mtime unchanged) and still runs correctly.
   - Editing a source file after install makes `run_installed_job`
     refuse (stale hash), exactly like the python case already does;
     re-installing clears the refusal.
   - After a build has happened, `compute_version_hash` before/after
     is unchanged (confirms `target/` exclusion actually holds, not
     just "the code path was added").
   - `CONFIG_PATH`/`NEEDS_PATH` (via a `job.json` with one declared
     `desk.state.*` key, set via `window.set_state` first) arrive as
     the correct env vars, with the needs file's content matching what
     `get_state` itself returns for that key.
   - The Installed Jobs widget's `_view_source` does not try to open
     anything under `target/`.
2. Slow, opt-in coverage (`disabled_verify_installed_jobs_rust_gpu.py`,
   disabled for wall-clock build cost, not flakiness -- documented
   plainly in its own header, distinct from the existing hardware/
   network/API-cost `disabled_` scripts and their still-open TODOs
   `b2ab79f`/`9bc522b`/`0d91c74`/`b6abde2`): installs and runs a real
   `wgpu`-based compute-shader job (the confirmed-working probe from
   the Investigation section above, adapted into the Installed Jobs
   shape) end to end, asserting the actual GPU-computed result.
3. Full `tests/verify/` regression suite (non-`disabled_` scripts)
   still passes, 0 failures.
