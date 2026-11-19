# Installed Jobs

See `desk-temporary-ui.md` (in this same directory) for this
directory's own overview and its current set of tags -- this file
covers Installed Jobs, which are **not** a tempui-DSL file type (there
is no dropped-file keyword for this -- see that overview's own "a few
more files" paragraph).

A `Job` (see `tempui-jobs.md`) is a one-shot script, re-approved every
single time you drop a fresh tempui file for it. An **Installed Job**
is the durable, versioned alternative for a script you expect to run
*repeatedly*: install it once (one approval prompt), then run it as
many times as you like with no further prompt at all.

## Installing

Two kinds, told apart purely by which file is present:

- **`python`** -- write your script to
  `desk-installed-jobs/<name>/main.py` (project-root-relative, a
  sibling of `.desk_temp/`, not inside it -- this is real, durable
  source, not disposable cache). You can add other files alongside it
  and `import` them from `main.py` -- the job's own directory is put on
  `sys.path` for the duration of a run. There is no capability list and
  no `html` variant: `main.py` runs with the same unrestricted,
  no-sandboxing in-process access any other Python code already running
  in this process has (the same trust level a `Job`'s own
  `kind: "python"` already has).
- **`rust`** -- write a real Cargo project to
  `desk-installed-jobs/<name>/` (`Cargo.toml` + `src/`), same
  project-root-relative, durable-source placement. For
  computationally-intensive work, or anything that wants the GPU -- see
  "Rust jobs and the GPU" below. Same trust level as `python`: no
  sandboxing, your `Cargo.toml` can depend on whatever crates it needs
  (`cargo build` fetches and compiles them, no separate install step).
  Having both `main.py` and `Cargo.toml` present (or neither) is a
  install-time error, not a guess.

Then call the `desk_install_job` MCP tool with `name` (the directory
name under `desk-installed-jobs/`). This computes a version hash over
your job's current source and registers it -- **this is the only
approval prompt you'll see for this job.** For a `rust`-kind job, this
does **not** build it yet (a first build can be slow -- see below); it
only validates and registers.

## Self-managed venvs

A python job may build its own venv (conventionally at
`desk-installed-jobs/<name>/.venv/`, created by `main.py` itself). The
version hash **skips that top-level `.venv/` directory**: its installed
contents are generated, can be huge, and would make installing and
running slow. Pin your dependency versions in `requirements.txt` (or a
lockfile) **outside** `.venv/` -- those files are hashed, so changing a
version still gives the job a new version and a fresh approval. A venv
with nothing pinning its versions means a dependency change can happen
without re-approval; pin them. Only the job's own top-level `.venv/` is
skipped, not a directory of that name elsewhere in the job's source.

## Running

Call the `desk_run_installed_job` MCP tool with `name` and, optionally,
`config_path` -- a path to a config file your job wants to read. A
relative `config_path` resolves against the current Desk's own
directory. There's no fixed default filename Desk invents on your
behalf -- if you want a config file, put it wherever makes sense for
your job and pass its path; it should generally live under
`.desk_temp/` (ephemeral, per-project scratch space) unless there's a
specific reason for it to live elsewhere. How your job reads it depends
on its kind:

- **`python`**: the `CONFIG_PATH` global (a plain string, or `None` if
  you didn't pass one).
- **`rust`**: the `DESK_JOB_CONFIG_PATH` environment variable, only set
  at all when a `config_path` was actually given (read it as
  `std::env::var("DESK_JOB_CONFIG_PATH").ok()`).

**This never prompts for approval.** That's the entire point of
installing a job instead of dropping a fresh `Job` file every time you
want to run it. It does mean the tool refuses to run if your job's
on-disk source no longer matches the version that was actually
approved at install time (someone edited it after installing) -- call
`desk_install_job` again first in that case, which re-approves the new
version. For a `rust`-kind job, `cargo`'s own `target/` build output
doesn't count as "source" for this check -- rebuilding never requires
re-approval.

The tool returns `{"ok": ..., "stdout": ..., "stderr": ..., "traceback": ...}` as JSON --
your job's captured stdout/stderr, plus a Python traceback if a
`python`-kind job raised (for `rust`, `traceback` is just a plain
"process exited with code N" note when `ok` is `false` -- a compiled
binary has no Python traceback to give back; put your own diagnostics
on stderr).

## Rust jobs and the GPU

A `rust`-kind job is built with `cargo build --release` the first time
it's run (not at install time -- a first build can take a while, see
below), then cached: a later run only rebuilds if a source file
(`Cargo.toml`/`Cargo.lock`/anything under `src/`) is newer than the
last compiled binary. The compiled binary is then run directly as a
real subprocess, `cwd` set to the job's own directory -- no timeout on
either the build or the run, so a genuinely long, computationally
-heavy job is free to actually take that long.

For GPU access, use the [`wgpu`](https://crates.io/crates/wgpu) crate
(add it to `[dependencies]` in your `Cargo.toml`) -- confirmed directly
working on this machine: a real WGSL compute shader was authored,
dispatched, and its output read back correctly against the real GPU
(`Metal` backend). `wgpu` is cross-platform (Metal/Vulkan/DX12/GL) and
is this ecosystem's most widely used GPU-compute crate, but it's a
recommendation, not a requirement -- your `Cargo.toml` can depend on
anything on crates.io; `cargo build` fetches and compiles it, no
separate install step. A minimal, confirmed-working shape:

```rust
let instance = wgpu::Instance::new(wgpu::InstanceDescriptor {
    backends: wgpu::Backends::all(),
    ..Default::default()
});
let adapter = pollster::block_on(instance.request_adapter(&wgpu::RequestAdapterOptions {
    power_preference: wgpu::PowerPreference::HighPerformance,
    compatible_surface: None,
    force_fallback_adapter: false,
})).expect("no adapter");
let (device, queue) = pollster::block_on(adapter.request_device(&Default::default(), None))
    .expect("no device");
// device.create_shader_module(...) with a WGSL compute shader,
// device.create_compute_pipeline(...), dispatch, then read a result
// buffer back -- see wgpu's own compute example for the full pipeline
// setup (bind groups, buffers, encoder, submit).
```

## Declaring what a job needs (`desk.state.*`)

A `python`-kind job's own code runs inside this same process, so it
can, incidentally, reach this app's live Python state via whatever it
imports -- undocumented, fragile, and not something to rely on. A
`rust`-kind job is a genuinely separate OS process and structurally
*can't* reach any of that at all. Either way, the supported way for a
job to receive data it doesn't already have is to **declare** which
"Shared, project-scoped state" (see `tempui-custom-widgets.md`) keys it
needs, and let Desk resolve them for you:

Add `desk-installed-jobs/<name>/job.json`:

```json
{"needs": ["some_state_key", "another_state_key"]}
```

On every run, Desk resolves each listed key via the same lookup
`desk.state.get` itself uses, and writes `{"some_state_key": {"value":
..., "edit": ...}, "another_state_key": {"value": ..., "edit": ...}}`
to a fresh file (a key nothing has ever `set()` comes back as `{"value":
null, "edit": null}`, same as `desk.state.get` itself) -- handed to your
job the same way `config_path` is:

- **`python`**: the `NEEDS_PATH` global (a plain string, or `None` if
  `job.json` is absent or declares no `needs`).
- **`rust`**: the `DESK_JOB_NEEDS_PATH` environment variable, only set
  when there's actually something to read.

No `job.json` at all is the common case and needs no change -- every
job written before this existed keeps working exactly as it did.

## Invoking another job from a `python`-kind job

A `python`-kind job's own code gets one more global: `RUN_INSTALLED_JOB(name,
config_path=None) -> {"ok", "stdout", "stderr", "traceback"}` -- the
exact same shape `desk_run_installed_job` itself returns. Call it to
run another already-installed job (`python`- or `rust`-kind, uniformly
-- your own code never needs to know or care which) as part of your
own job's work, e.g. a `python`-kind job doing scene setup that wants
to hand its GPU-heavy inner loop off to a `rust`-kind job:

```python
result = RUN_INSTALLED_JOB("gpu_inner_loop", config_path="/path/to/config.json")
if result["ok"]:
    print(result["stdout"])
else:
    print("nested job failed:", result["stderr"])
```

Same no-reapproval/stale-source-refusal rules apply to the nested job
as to any other run -- a failure there (not installed, or its source
changed since its own install) comes back as `{"ok": false, ...}`,
never as a Python exception raised into your own code. Nesting is
unrestricted -- a `python`-kind job invoked this way gets its own
`RUN_INSTALLED_JOB` too, so it can invoke a further job in turn, to
whatever depth you actually write.

**Only `python`-kind jobs can invoke another job.** A `rust`-kind job
has no equivalent -- it's a real, separate OS process with no path
back into Desk's own state to make this call at all. If you need a
`rust`-kind job's own inner work broken into steps, structure that
inside the Rust program itself.

## Running from a `kind: "html"` widget

An unrelated `kind: "html"` widget (declaring the `installed_jobs`
capability) can run an Installed Job too, via
`desk.installedJobs.run(name, configPath)` -- see "The Desk Bridge
API" in `tempui-custom-widgets.md` for its exact call shape. Same
no-reapproval-on-run/stale-hash-refusal behavior as the MCP tool
above, but bounded to 120 seconds (a synchronous HTTP request/response
can't wait forever the way an agent's own `await` can) -- a job
expected to run longer than that belongs on the MCP/agent path
instead.

## The Installed Jobs widget

Placeable like any other widget: lists every installed job (name, kind,
+ version hash), with a "View Source" button (opens each of the job's
own files in a real editor widget -- a `rust`-kind job's `target/`
build output is skipped, not opened one file at a time) and an
"Uninstall" button (behind a confirmation) per row. Uninstalling only
removes the registration -- your source under
`desk-installed-jobs/<name>/` is left on disk, so installing the same
name again later just re-approves it.
