# Desk — Isolation and Trust Tiers

TODO `2924940`. The model Desk's isolation work is built on: what we defend
against, what runs where today, and the order we close gaps in. Written
2026-10-03 after reading the code (each "today" statement below was checked
against the source, not assumed). It deliberately describes *v1*; the long-term
vision is larger.

## Vision and non-goals

**Vision:** a zero-friction, zero-trust environment for running widgets -- the
user does nothing and an untrusted widget still can't hurt them -- with a mix of
fine- and coarse-grained permission models layered on top for the cases that
legitimately need more.

**v1 is far more modest:** close the cheapest, highest-value gaps, put the
mechanisms in place (one confinement interface, scoped capabilities), and be
honest in the docs about which tier a thing runs in. Not goals for v1:
containers or VMs as a local isolation layer, Linux/Windows backends, isolating
in-process Python widgets.

## Threats in scope

| | Threat | Exposure today |
|---|---|---|
| (a) | A buggy or malicious widget, job or transform harming the host | `kind: "python"` widgets, python transforms, tempui `Job` (python) and `DeskProc` scripts, and **python installed jobs** all run in Desk's own process with full user access. Only hmsvc services and Rust installed jobs are separate processes, and none of them is confined. |
| (b) | One project reading another's files | `desk.fs.*` takes any absolute path; `desk.documents` (TODO `8e4711e`) likewise; a subprocess can read anything the user can. |
| (c) | The Claude agent acting beyond its project | The Claude (Desk) widget runs `claude` with the user's permissions. `ClaudeSession`'s scoped mode (`allowed_paths`) is a real boundary only for the tools its `PreToolUse` hook covers, and deliberately excludes Bash. |

## What runs where today (verified)

| Thing | Runs | Reaches Desk through |
|---|---|---|
| `kind: "python"` widget (built-in or `desk_widgets/`) | In-process, GUI thread | Direct Python (`current_context`, signals) |
| `kind: "html"` widget | QtWebEngine (Chromium), own profile directory per instance; no `--no-sandbox` or similar flags found in `src/` | The Bridge API over loopback HTTP, capabilities from its manifest |
| Python transform | In-process (`importlib` in `desk_services/transforms`) | Direct |
| Node/TypeScript transform | Subprocess | Stdin/stdout |
| tempui `Job` (python) / `DeskProc` | `exec()` in-process (`job_runner`, `desk_proc_runner`) | Direct |
| Installed job, `main.py` | `exec`'d **in-process** (`desk/installed_jobs.py`) | Direct, plus declared needs |
| Installed job, Rust | Real subprocess (`cargo build`, then the binary) | Declared needs only |
| hmsvc service | Subprocess (`python -m desk.hmsvc_host`) on a loopback port | The Bridge API as caller `hmsvc:<name>`, capabilities from `service.json` |
| `claude` (Claude widgets) | Subprocess | The Agent SDK stream; Desk's in-process MCP server |

## Findings that shape the plan

1. **The Bridge is already the single server-side choke point** for html
   widgets and hmsvc services: every route goes through
   `require_caller(capability)`. That is the right place to enforce scopes.
2. **The Bridge now binds identity (TODO `929e730`).** Each placed instance and
   each hmsvc service has its own credential; the server maps it to the caller's
   identity and ignores any identity headers the caller sends, and the credential
   is revoked on close, Desk switch or service stop. Capability checks are
   therefore a real boundary between callers. A request that tries to rely on the
   old shared launch token for identity is a tombstone (refused and reported; see
   [deprecation-process.md](./deprecation-process.md)).
3. **Several things assumed to be "already subprocesses" are not**: python
   installed jobs and tempui python `Job`s run in-process. Confining them means
   moving them out of process first (TODO `d35f298`'s spike now covers this).
4. **`kind: "html"` is the natural zero-trust tier**: Chromium's own sandbox plus
   the Bridge as the only door. What it lacks is finer-grained scopes and
   approval (TODO `b195218`).

## Trust tiers

1. **Trusted, in-process.** `kind: "python"` widgets, python transforms,
   in-process Jobs/DeskProc/installed jobs. Full access; documented as the
   trusted tier ("only run code you would run as yourself"). v1 does not try to
   confine this tier; it tries to *shrink* it (TODO `d35f298` investigates moving
   pieces out of process).
2. **Confined subprocess.** hmsvc services, Rust installed jobs, (later) python
   installed jobs and Jobs, and the `claude` subprocess, run through one
   confinement interface (TODO `6e51e9f`): project directory and `.desk_temp`
   readable/writable, other user files denied, network opt-in.
3. **Zero-trust html.** `kind: "html"` widgets. Allowed to do only what the Bridge
   grants, with per-instance credentials (TODO `929e730`), project-scoped paths by
   default (TODO `73e375f`) and scoped, user-approved capabilities (TODO
   `b195218`).

Defaults by tier: tier 3 gets the most restrictive defaults and widening is
explicit (a manifest declaration plus user approval); tier 2 gets a
project-scoped sandbox; tier 1 is trusted and says so.

## Mechanisms and feasibility (macOS first)

| Mechanism | Verdict for Desk |
|---|---|
| Sandboxing a subprocess (macOS Seatbelt via `sandbox-exec`) | **Best near-term fit.** Deprecated by Apple but still functional and used by comparable tools; a per-run profile is cheap. Wrap behind one `confine` interface so other OSes can slot in. |
| Containers | Feasible but heavy: on macOS a container is a Linux VM underneath (Docker Desktop, Colima, Apple's `container` tool); file access, startup time and the dependency burden are real costs. A fit for services, not widgets; conflicts with the no-new-dependencies rule unless the user already has the runtime. |
| VMs | Feasible, heaviest. Treat as the *remote workspace* story (see `investigations/hosting-for-always-on-agent-sessions.md`, TODO `be2ce4e`), not a local isolation layer. |
| Out-of-process Python widgets | Needs a process split and proxying the Qt UI; unknown cost, hence a timeboxed spike (TODO `d35f298`). Until then python widgets stay trusted. |

**Other platforms (ballpark, not immediate):** Linux is roughly comparable to
macOS for subprocess confinement (bubblewrap or Landlock behind the same
interface, on the order of a few days of work plus testing). Windows is
meaningfully harder (AppContainer or job objects, more platform-specific edge
cases), roughly several times the Linux effort. macOS first.

## Order of work

1. **`929e730`** -- bind Bridge credentials to the calling instance (done).
2. **`73e375f`** -- project-scoped path allow-lists for `desk.fs` and
   `desk.documents` (cheapest, covers threat (b) for html widgets and services).
3. **`6e51e9f`** -- the confined subprocess runner, Seatbelt backend.
4. **`172b236`** -- confine the `claude` subprocess (threat (c)).
5. **`b195218`** -- scoped capabilities, approval flow and per-tier defaults.
6. **`d35f298`** -- the out-of-process spike for python widgets, transforms and
   in-process jobs (threat (a), the expensive part).
7. **`be2ce4e`** -- the remote session daemon (a separate track that wants
   confinement on whatever machine hosts it).

## Principles

- **Zero friction by default.** The safe behavior is the default; widening is
  explicit, rare and remembered.
- **One choke point per tier** (the Bridge; the confinement interface), not
  scattered checks.
- **Never silently weaken.** If a sandbox can't start, fail loudly; don't run the
  thing unconfined.
- **Tell the truth in the docs** about which tier a thing runs in and what that
  does and does not protect.
- Verify mechanisms with real runs (a denied read really is denied), not by
  assuming the profile does what it says.

## Open questions

- How should the trusted tier be presented to the user (a badge on python
  widgets?) so trust is visible rather than implicit?
- Is a user-facing "run this untrusted widget confined" option worth it once
  out-of-process python widgets exist?
