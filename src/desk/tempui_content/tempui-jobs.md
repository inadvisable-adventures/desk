# TempUI DSL: Job

See `desk-temporary-ui.md` (in this same directory) for this
directory's own overview and its current set of tags -- this file
just covers the `Job` keyword.

For running a **one-time script** with real widget-context
capabilities -- notably Bridge API access, which nothing else lets you
reach outside a real `kind: "html"` widget's own JS -- without
building a full `DefineWidget` (a reusable, promotable widget *kind*)
or a `widgets/<id>/` registration just for one throwaway task. If what
you actually want is a reusable widget *kind* placeable many times, or
something that stays running (a background service, a long,
checkpointed pipeline), a `Job` is the wrong tool -- it's a single
one-shot run, no more.

- The first line is `Job<TAB>kind<TAB>summary` -- `kind` is `python`
  or `html`; `summary` is shown in the notification and the placed Job
  Runner widget, never executed.
- Zero or more `Capability<TAB>name` lines -- only meaningful for
  `kind: "html"` (ignored, but harmless, for `kind: "python"`): the
  same coarse Bridge API capability names a `DefineWidget`'s own
  `Capability` lines use (`workspace`, `fs`, `widgets`, `events`,
  `filetypes`, `editor`, `popups`, `transforms`, `introspect`,
  `installed_jobs`, `launch_agent`, `media` -- see "The Desk Bridge API" in
  `tempui-custom-widgets.md` for what each one actually grants).
  Declare only what your script actually calls
  -- an undeclared capability's Bridge call gets a real HTTP 403, not
  silent success.
- One or more `Script<TAB>base64-chunk` lines -- your script's entire
  source, base64-encoded (chunk it across several `Script` lines for a
  long script; they're concatenated in file order before decoding,
  the same convention `DefineWidget`'s own `Html` lines use). For
  `kind: "html"`, this is a complete, self-contained HTML document
  (same shape as a `DefineWidget`'s own content) -- your page's JS gets
  `window.desk.*` injected automatically, scoped to exactly the
  `Capability` lines you declared above. For `kind: "python"`, this is
  a plain Python script, executed directly (no `desk` package import
  needed beyond what you'd already use in any other Python code in
  this environment) -- there is no capability scoping for `kind:
  "python"` at all; it runs with the same access any other code
  already running in this process has.

Clicking the resulting notification places a **Job Runner** widget,
showing your declared summary, a "View Code" button (opens your
script's own source in a real editor), and a "Start" button --
**nothing runs until Start is clicked**. Once started, Start becomes
disabled and stays that way (even across a Desk reload) -- a `Job` is
a one-shot run, not a repeatable tool; write a new `Job` file for a
second run.

**"Done" means the page finished loading, not that every async Bridge
call your script's own JS kicked off has resolved.** There is no
generic way for Desk to know an arbitrary web page's own async work
has actually finished -- if your `kind: "html"` script fires off a
Bridge call and returns immediately, the Job Runner widget may show
"Done" before that call's effect is visible elsewhere. If you need to
know a specific call actually completed, have your own script make
that visible some other way (e.g. render its own result in the page),
rather than relying on the Job Runner's status display as a strict
completion signal.

You don't have to hand-write the base64/`Script` line(s) below
yourself -- `.desk_temp/build_job_or_desk_proc.py` (mirroring
`build_widget.py`'s convenience for `DefineWidget`) builds a real `Job`
file for you from a plain script file:

```
python3 .desk_temp/build_job_or_desk_proc.py job python "Delete .desk_temp/jobs/ entries older than 7 days" cleanup.py
python3 .desk_temp/build_job_or_desk_proc.py job html "Talk to the Bridge API" widget.html --capability workspace
```

prints the path of the tempui file it wrote, ready to be picked up the
same as any other `.desk_temp/` file.

Example (`kind: "python"`, script shown decoded/unwrapped for
readability -- the real file's `Script` line(s) would carry it
base64-encoded):

```
Job	python	Delete .desk_temp/jobs/ entries older than 7 days
Script	<base64-encoded script text>
```

```python
import time
from pathlib import Path

cutoff = time.time() - 7 * 24 * 60 * 60
jobs_dir = Path(".desk_temp/jobs")
for entry in jobs_dir.iterdir() if jobs_dir.is_dir() else []:
    if entry.stat().st_mtime < cutoff:
        print(f"would remove {entry}")
```
